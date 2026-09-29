"""AADHk Time Recording SQLite parser and cross-validation service."""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src import config
from src.models.schedule import SchedulePayload, Lesson
from src.storage.db import Database

logger = logging.getLogger(__name__)


def parse_timestamp_val(val: Any, tz_str: str = config.TZ) -> datetime | None:
    """Parse various timestamp representations (millis, seconds, strings)."""
    if val is None:
        return None
    try:
        # Numeric timestamp
        if isinstance(val, (int, float)):
            if val > 1e11:  # Milliseconds
                return datetime.fromtimestamp(val / 1000.0, tz=ZoneInfo(tz_str))
            elif val > 1e8:  # Seconds
                return datetime.fromtimestamp(val, tz=ZoneInfo(tz_str))

        # String representation
        s = str(val).strip()
        if s.isdigit():
            num = int(s)
            if num > 1e11:
                return datetime.fromtimestamp(num / 1000.0, tz=ZoneInfo(tz_str))
            return datetime.fromtimestamp(num, tz=ZoneInfo(tz_str))

        # Date string formats
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%d",
        ):
            try:
                dt = datetime.strptime(s, fmt)
                return dt.replace(tzinfo=ZoneInfo(tz_str))
            except ValueError:
                continue
    except Exception as e:
        logger.debug("Failed to parse timestamp '%s': %s", val, e)
    return None


class AadhkIngestionService:
    """Service for parsing AADHk Time Recording SQLite databases and validating with SUAI."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def ingest_backup_file(
        self,
        backup_file_path: str | Path,
        default_project: str = "Тидекс",
    ) -> dict[str, Any]:
        """Parse AADHk backup SQLite file, cross-validate with SUAI timetable, and save to db."""
        p = Path(backup_file_path)
        if not p.is_file():
            raise FileNotFoundError(f"Backup file not found: {backup_file_path}")

        # 1. Fetch current SUAI schedule for cross-validation
        suai_lessons_by_date = await self._load_suai_lessons()

        # 2. Extract records from AADHk SQLite
        parsed_shifts = self._extract_shifts_from_sqlite(p, default_project=default_project)
        logger.info("Extracted %d shifts from AADHk file %s", len(parsed_shifts), p.name)

        # 3. Cross-validate with SUAI schedule
        conflicts_count = 0
        for shift in parsed_shifts:
            conflict_msg = self._check_schedule_conflict(shift, suai_lessons_by_date)
            if conflict_msg:
                shift["has_guap_conflict"] = True
                shift["conflict_details"] = conflict_msg
                conflicts_count += 1

        # 4. Save to database
        saved_count = await self.db.save_timesheet_records_batch(parsed_shifts)
        logger.info("Saved %d new timesheet records into database (%d conflicts)", saved_count, conflicts_count)

        # 5. Calculate summary metrics
        summary = await self.db.get_timesheet_summary()
        return {
            "parsed_count": len(parsed_shifts),
            "new_inserted_count": saved_count,
            "conflicts_count": conflicts_count,
            "total_hours": summary.get("total_hours", 0.0),
            "by_task": summary.get("by_task", {}),
        }

    def _extract_shifts_from_sqlite(
        self,
        db_path: Path,
        default_project: str = "Тидекс",
    ) -> list[dict[str, Any]]:
        """Connect to SQLite backup and dynamically map tables."""
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row["name"].lower() for row in cursor.fetchall()]

            # Determine projects mapping
            projects_map: dict[Any, str] = {}
            for t_proj in ("project", "projects", "tbl_project"):
                if t_proj in tables:
                    try:
                        cursor.execute(f"SELECT * FROM {t_proj};")
                        for r in cursor.fetchall():
                            keys = r.keys()
                            pid = r["_id"] if "_id" in keys else (r["id"] if "id" in keys else None)
                            name = r["name"] if "name" in keys else (r["title"] if "title" in keys else default_project)
                            if pid is not None and name:
                                projects_map[pid] = str(name)
                        break
                    except Exception as e:
                        logger.debug("Failed querying project table %s: %s", t_proj, e)

            # Determine tasks mapping
            tasks_map: dict[Any, str] = {}
            for t_task in ("task", "tasks", "tbl_task"):
                if t_task in tables:
                    try:
                        cursor.execute(f"SELECT * FROM {t_task};")
                        for r in cursor.fetchall():
                            keys = r.keys()
                            tid = r["_id"] if "_id" in keys else (r["id"] if "id" in keys else None)
                            name = r["name"] if "name" in keys else (r["title"] if "title" in keys else None)
                            if tid is not None and name:
                                tasks_map[tid] = str(name)
                        break
                    except Exception as e:
                        logger.debug("Failed querying task table %s: %s", t_task, e)

            # Find time records table
            records_table = None
            for cand in (
                "times",
                "time_record",
                "time_records",
                "timerecord",
                "timerecords",
                "records",
                "record",
                "tbl_time_record",
                "tbl_times",
            ):
                if cand in tables:
                    records_table = cand
                    break

            if not records_table:
                # If no standard name found, look for table with date1/date2 or start/end columns
                for t in tables:
                    if t.startswith("sqlite_") or t.startswith("android_"):
                        continue
                    cursor.execute(f"PRAGMA table_info({t});")
                    cols = [c[1].lower() for c in cursor.fetchall()]
                    if (any("start" in c for c in cols) and any("end" in c for c in cols)) or (
                        "date1" in cols and "date2" in cols
                    ):
                        records_table = t
                        break

            if not records_table:
                logger.warning("Could not identify time records table in %s (found: %s)", db_path.name, tables)
                return []

            cursor.execute(f"SELECT rowid, * FROM {records_table};")
            raw_rows = cursor.fetchall()
            results: list[dict[str, Any]] = []

            for r in raw_rows:
                keys = r.keys()
                # Find ID
                ext_id = None
                for k in ("rowid", "_id", "id", "record_id", "recordId"):
                    if k in keys and r[k] is not None:
                        ext_id = str(r[k])
                        break

                # Find Start Time
                start_val = None
                for k in ("date1", "start_time", "startTime", "start", "check_in", "checkIn"):
                    if k in keys and r[k]:
                        start_val = r[k]
                        break

                # Find End Time
                end_val = None
                for k in ("date2", "end_time", "endTime", "end", "check_out", "checkOut"):
                    if k in keys and r[k]:
                        end_val = r[k]
                        break

                dt_start = parse_timestamp_val(start_val)
                dt_end = parse_timestamp_val(end_val)

                if not dt_start or not dt_end:
                    continue

                if dt_end < dt_start:
                    continue

                duration_min = 0
                if "working" in keys and r["working"] is not None and int(r["working"]) > 0:
                    duration_min = int(r["working"])
                else:
                    duration_min = int((dt_end - dt_start).total_seconds() / 60)

                # Rate and Amount
                rate = 0.0
                if "amountPerhour" in keys and r["amountPerhour"] is not None:
                    try:
                        rate = float(r["amountPerhour"])
                    except (ValueError, TypeError):
                        rate = 0.0

                amount = 0.0
                if "amount" in keys and r["amount"] is not None:
                    try:
                        amount = float(r["amount"])
                    except (ValueError, TypeError):
                        amount = 0.0
                elif rate > 0 and duration_min > 0:
                    amount = round(duration_min / 60.0 * rate, 2)

                if duration_min <= 0 and amount <= 0:
                    continue

                # Project
                proj_name = default_project
                if "projectName" in keys and r["projectName"]:
                    p_val = str(r["projectName"]).strip()
                    proj_name = default_project if p_val == "Работа" else p_val
                else:
                    for k in ("project_id", "projectId", "project"):
                        if k in keys and r[k] in projects_map:
                            p_val = projects_map[r[k]]
                            proj_name = default_project if p_val == "Работа" else p_val
                            break

                # Task
                task_name = "Исследования и разработка"
                for k in ("task_id", "taskId", "task"):
                    if k in keys and r[k] in tasks_map:
                        task_name = tasks_map[r[k]]
                        break

                # Note / description / remark
                note = ""
                for k in ("notes", "remark", "note", "description", "comment"):
                    if k in keys and r[k]:
                        note = str(r[k]).strip()
                        if note:
                            break

                results.append({
                    "source": "aadhk",
                    "external_record_id": ext_id or f"gen_{int(dt_start.timestamp())}",
                    "project_name": proj_name,
                    "task_name": task_name,
                    "start_time": dt_start.isoformat(),
                    "end_time": dt_end.isoformat(),
                    "duration_minutes": duration_min,
                    "hourly_rate": rate,
                    "amount": amount,
                    "note": note,
                    "has_guap_conflict": False,
                    "conflict_details": "",
                })

            return results
        finally:
            conn.close()

    async def _load_suai_lessons(self) -> dict[str, list[dict[str, Any]]]:
        """Loads SUAI schedule lessons mapped by ISO date (YYYY-MM-DD) across all snapshots."""
        lessons_by_date: dict[str, list[dict[str, Any]]] = {}
        seen_lessons: set[tuple[str, str, str, str]] = set()

        snapshots = []
        if hasattr(self.db, "list_snapshots_by_prefix"):
            snapshots = await self.db.list_snapshots_by_prefix("rasp_guap_")
        if not snapshots:
            snap = await self.db.get_latest_snapshot(f"rasp_guap_{config.SCHEDULE_TARGET_ID}")
            if snap:
                snapshots = [snap]

        for snap in snapshots:
            if not snap or not snap.get("raw_payload"):
                continue
            try:
                payload = SchedulePayload.model_validate_json(snap["raw_payload"])
                for day in payload.days:
                    date_str = day.date.isoformat()
                    if date_str not in lessons_by_date:
                        lessons_by_date[date_str] = []
                    for les in day.lessons:
                        dedup_key = (date_str, str(les.start_time), les.subject, les.room or "")
                        if dedup_key in seen_lessons:
                            continue
                        seen_lessons.add(dedup_key)

                        start_dt = datetime.combine(les.date, les.start_time, tzinfo=ZoneInfo(config.TZ))
                        end_dt = datetime.combine(les.date, les.end_time, tzinfo=ZoneInfo(config.TZ))
                        lessons_by_date[date_str].append({
                            "subject": les.subject,
                            "type": les.lesson_type.value if hasattr(les.lesson_type, "value") else str(les.lesson_type),
                            "room": les.room or "",
                            "group": les.group or "",
                            "start": start_dt,
                            "end": end_dt,
                        })
            except Exception as e:
                logger.warning("Failed parsing SUAI schedule snapshot: %s", e)
        return lessons_by_date

    def _check_schedule_conflict(
        self,
        shift: dict[str, Any],
        suai_lessons: dict[str, list[dict[str, Any]]],
    ) -> str | None:
        """Check if a Tydex shift intersects with any SUAI lesson."""
        try:
            start_dt = datetime.fromisoformat(str(shift["start_time"]))
            end_dt = datetime.fromisoformat(str(shift["end_time"]))
            date_key = start_dt.date().isoformat()

            day_lessons = suai_lessons.get(date_key, [])
            for les in day_lessons:
                l_start = les["start"]
                l_end = les["end"]
                # Check interval overlap: max(start1, start2) < min(end1, end2)
                overlap_start = max(start_dt, l_start)
                overlap_end = min(end_dt, l_end)
                if overlap_start < overlap_end:
                    overlap_minutes = int((overlap_end - overlap_start).total_seconds() / 60)
                    return (
                        f"Пересечение с парой ГУАП ({overlap_minutes} мин): "
                        f"{les['subject']} ({les['type']}), ауд. {les['room']} [{les['group']}]"
                    )
        except Exception as e:
            logger.debug("Error checking shift conflict: %s", e)
        return None

    async def reconcile_all_conflicts(self) -> dict[str, Any]:
        """Re-evaluate SUAI schedule conflicts across all timesheet records in database."""
        suai_lessons_by_date = await self._load_suai_lessons()
        records = await self.db.list_timesheet_records(limit=10000)

        total_checked = len(records)
        conflicts_found = 0
        resolved_count = 0
        updated_count = 0

        for r in records:
            rec_id = r["id"]
            conflict_msg = self._check_schedule_conflict(r, suai_lessons_by_date)
            new_conflict = bool(conflict_msg)
            new_details = conflict_msg or ""

            old_conflict = bool(r.get("has_guap_conflict"))
            old_details = r.get("conflict_details") or ""

            if new_conflict != old_conflict or (new_conflict and old_details != new_details):
                await self.db.update_timesheet_conflict(rec_id, new_conflict, new_details)
                updated_count += 1

            if new_conflict:
                conflicts_found += 1
            elif old_conflict and not new_conflict:
                resolved_count += 1

        summary = await self.db.get_timesheet_summary()
        logger.info(
            "Reconciled %d timesheet records: %d conflicts, %d resolved, %d updated",
            total_checked,
            conflicts_found,
            resolved_count,
            updated_count,
        )
        return {
            "total_checked": total_checked,
            "conflicts_found": conflicts_found,
            "resolved_count": resolved_count,
            "updated_count": updated_count,
            "total_hours": summary.get("total_hours", 0.0),
            "clean_hours": summary.get("clean_hours", 0.0),
            "conflict_hours": summary.get("conflict_hours", 0.0),
            "total_amount": summary.get("total_amount", 0.0),
        }

    async def get_timesheet_report(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        project_name: str | None = "Тидекс",
    ) -> dict[str, Any]:
        """Generate comprehensive timesheet report with conflict details and daily breakdown."""
        summary = await self.db.get_timesheet_summary(
            start_date=start_date,
            end_date=end_date,
            project_name=project_name,
        )
        conflicts = await self.db.get_timesheet_conflicts(limit=20)
        return {
            "summary": summary,
            "conflicts": conflicts,
            "filter": {
                "start_date": start_date,
                "end_date": end_date,
                "project_name": project_name,
            },
        }

