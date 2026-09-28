import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from src.models.schedule import Lesson, LessonType, ScheduleDiff
from src.storage.db import Database

logger = logging.getLogger(__name__)

SUBJECT_SHORT_NAMES: dict[str, str] = {
    "физические основы нанотехнологий": "ФОНТ",
    "основы проектной деятельности в профессии": "ОПДвП",
    "основы проектной деятельности": "ОПД",
    "физика": "Физика",
}

LESSON_TYPE_SHORT: dict[LessonType, str] = {
    LessonType.LECTURE: "Лек",
    LessonType.LAB: "Лаб",
    LessonType.PRACTICE: "Пр",
    LessonType.EXAM: "Экз",
    LessonType.UNKNOWN: "Занятие",
}

LESSON_TYPE_LONG: dict[LessonType, str] = {
    LessonType.LECTURE: "Лекция",
    LessonType.LAB: "Лабораторное занятие",
    LessonType.PRACTICE: "Практическое занятие",
    LessonType.EXAM: "Экзамен",
    LessonType.UNKNOWN: "Занятие",
}


class GoogleCalendarClient:
    """Manages synchronization between local schedule and Google Calendar."""

    def __init__(
        self,
        credentials_file: str = "./credentials.json",
        token_file: str = "./token.json",
        timezone_str: str = "Europe/Moscow",
        dry_run: bool = False,
    ):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.timezone_str = timezone_str
        self.dry_run = dry_run
        self.service = None
        self._init_service()

    def _init_service(self) -> None:
        """Initialize Google Calendar API service if valid tokens exist."""
        if self.dry_run:
            logger.info("GoogleCalendarClient running in DRY-RUN mode.")
            return

        token_path = Path(self.token_file)
        if not token_path.exists():
            logger.warning(
                "Google token file '%s' not found. Operating in MOCK / DRY-RUN mode until credentials are provided.",
                self.token_file,
            )
            self.dry_run = True
            return

        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            creds = Credentials.from_authorized_user_file(str(token_path))
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_path, "w") as token_out:
                    token_out.write(creds.to_json())

            self.service = build("calendar", "v3", credentials=creds)
            logger.info("Google Calendar service initialized successfully.")
        except Exception as e:
            logger.warning(
                "Failed to initialize Google Calendar API: %s. Falling back to DRY-RUN mode.",
                e,
            )
            self.dry_run = True

    @classmethod
    def format_summary(cls, lesson: Lesson) -> str:
        """Format event summary matching Dmitry's standard: [Group] Subject (Type)."""
        subj_clean = lesson.subject.strip()
        short_subj = SUBJECT_SHORT_NAMES.get(subj_clean.lower(), subj_clean)
        short_type = LESSON_TYPE_SHORT.get(lesson.lesson_type, "Занятие")
        if lesson.group:
            return f"[{lesson.group}] {short_subj} ({short_type})"
        return f"{short_subj} ({short_type})"

    @classmethod
    def format_description(cls, lesson: Lesson) -> str:
        """Format event description matching Dmitry's structured calendar format."""
        slot_map = {
            (9, 30): 1,
            (11, 10): 2,
            (13, 0): 3,
            (15, 10): 4,
            (17, 0): 5,
            (18, 40): 6,
        }
        slot_num = slot_map.get((lesson.start_time.hour, lesson.start_time.minute))
        time_str = f"{lesson.start_time.strftime('%H:%M')}—{lesson.end_time.strftime('%H:%M')}"
        lines = []
        if slot_num:
            lines.append(f"Пара: {slot_num} ({time_str})")
        if lesson.group:
            lines.append(f"Группа: {lesson.group}")
        subj_clean = lesson.subject.strip()
        short_subj = SUBJECT_SHORT_NAMES.get(subj_clean.lower(), subj_clean)
        short_type = LESSON_TYPE_SHORT.get(lesson.lesson_type, "Занятие")
        long_type = LESSON_TYPE_LONG.get(lesson.lesson_type, "Занятие")
        lines.append(f"Предмет: {lesson.subject} ({short_subj})")
        lines.append(f"Тип занятия: {long_type} ({short_type})")
        if lesson.teacher:
            lines.append(f"Преподаватель: {lesson.teacher}")
        lines.append(f"Аудитория: {lesson.room}")
        lines.append(f"Хэш слота: {lesson.deterministic_hash}")
        return "\n".join(lines)

    async def find_existing_event(self, calendar_id: str, lesson: Lesson) -> dict[str, Any] | None:
        """Find an existing calendar event for the lesson slot to prevent duplication."""
        if self.dry_run or self.service is None:
            return None

        # Query events on the given date (day bounds)
        time_min = f"{lesson.date.isoformat()}T00:00:00Z"
        time_max = f"{lesson.date.isoformat()}T23:59:59Z"

        try:
            res = self.service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
            ).execute()

            items = res.get("items", [])
            target_start_prefix = f"{lesson.date.isoformat()}T{lesson.start_time.strftime('%H:%M')}"
            short_subj = SUBJECT_SHORT_NAMES.get(lesson.subject.strip().lower(), lesson.subject.strip()).lower()
            for item in items:
                start_dt = item.get("start", {}).get("dateTime", "")
                if start_dt.startswith(target_start_prefix):
                    ev_summary = (item.get("summary") or "").lower()
                    if short_subj in ev_summary or lesson.subject.strip().lower() in ev_summary:
                        return item
                    if lesson.group and lesson.group.lower() in ev_summary:
                        return item
        except Exception as e:
            logger.warning("Failed to query Google Calendar for existing events on %s: %s", lesson.date, e)

        return None

    async def create_event(self, calendar_id: str, lesson: Lesson) -> str:
        """Create an event in Google Calendar and return its ID."""
        summary = self.format_summary(lesson)
        description = self.format_description(lesson)
        start_iso = f"{lesson.date.isoformat()}T{lesson.start_time.isoformat()}"
        end_iso = f"{lesson.date.isoformat()}T{lesson.end_time.isoformat()}"

        event_body = {
            "summary": summary,
            "location": lesson.room,
            "description": description,
            "start": {
                "dateTime": start_iso,
                "timeZone": self.timezone_str,
            },
            "end": {
                "dateTime": end_iso,
                "timeZone": self.timezone_str,
            },
        }

        if self.dry_run or self.service is None:
            # Generate deterministic mock ID based on slot hash
            mock_id = f"mock_{lesson.deterministic_hash[:16]}"
            logger.info("[DRY-RUN] Created Google Calendar event '%s' (%s - %s) -> id: %s", summary, start_iso, end_iso, mock_id)
            return mock_id

        try:
            created = self.service.events().insert(calendarId=calendar_id, body=event_body).execute()
            google_id = created.get("id")
            logger.info("Created Google Calendar event '%s' -> %s", summary, google_id)
            return google_id
        except Exception as e:
            logger.error("Failed to create Google Calendar event '%s': %s", summary, e)
            raise

    async def delete_event(self, calendar_id: str, google_event_id: str) -> bool:
        """Delete an event from Google Calendar."""
        if self.dry_run or self.service is None:
            logger.info("[DRY-RUN] Deleted Google Calendar event %s", google_event_id)
            return True

        try:
            self.service.events().delete(calendarId=calendar_id, eventId=google_event_id).execute()
            logger.info("Deleted Google Calendar event %s", google_event_id)
            return True
        except Exception as e:
            logger.error("Failed to delete Google Calendar event %s: %s", google_event_id, e)
            return False

    async def sync_schedule(
        self,
        calendar_id: str,
        diff: ScheduleDiff,
        db: Database,
    ) -> dict[str, int]:
        """Synchronize schedule diff with Google Calendar idempotently.
        
        Guarantees 0 duplicate entries upon repeated runs.
        """
        stats = {"created": 0, "cancelled": 0, "skipped": 0}

        # 1. Process added lessons
        for lesson in diff.added_lessons:
            slot_id = lesson.deterministic_hash
            existing_record = await db.get_calendar_sync_record(slot_id)

            if existing_record and existing_record["status"] == "active":
                logger.debug("Event %s already synced as %s. Skipping (idempotency).", slot_id[:8], existing_record["google_event_id"])
                stats["skipped"] += 1
                continue

            summary = self.format_summary(lesson)
            start_dt = datetime.combine(lesson.date, lesson.start_time)
            end_dt = datetime.combine(lesson.date, lesson.end_time)

            # Check if an event already covers this time slot in Google Calendar (e.g. recurring event from series)
            existing_event = await self.find_existing_event(calendar_id, lesson)
            if existing_event:
                logger.info(
                    "Event already exists in calendar: '%s' (id: %s). Linking record, skipping duplicate creation.",
                    existing_event.get("summary"),
                    existing_event.get("id"),
                )
                await db.record_calendar_sync(
                    source_event_id=slot_id,
                    google_event_id=existing_event.get("id"),
                    calendar_id=calendar_id,
                    event_start=start_dt,
                    event_end=end_dt,
                    summary=existing_event.get("summary") or summary,
                    status="active",
                )
                stats["skipped"] += 1
                continue

            # Create event in Google Calendar
            google_id = await self.create_event(calendar_id, lesson)

            await db.record_calendar_sync(
                source_event_id=slot_id,
                google_event_id=google_id,
                calendar_id=calendar_id,
                event_start=start_dt,
                event_end=end_dt,
                summary=summary,
                status="active",
            )
            stats["created"] += 1

        # 2. Process removed lessons
        for lesson in diff.removed_lessons:
            slot_id = lesson.deterministic_hash
            existing_record = await db.get_calendar_sync_record(slot_id)

            if existing_record and existing_record["status"] == "active":
                await self.delete_event(calendar_id, existing_record["google_event_id"])
                start_dt = datetime.combine(lesson.date, lesson.start_time)
                end_dt = datetime.combine(lesson.date, lesson.end_time)

                await db.record_calendar_sync(
                    source_event_id=slot_id,
                    google_event_id=existing_record["google_event_id"],
                    calendar_id=calendar_id,
                    event_start=start_dt,
                    event_end=end_dt,
                    summary=existing_record["summary"],
                    status="cancelled",
                )
                stats["cancelled"] += 1

        logger.info(
            "Calendar sync finished: +%d created, -%d cancelled, %d skipped.",
            stats["created"],
            stats["cancelled"],
            stats["skipped"],
        )
        return stats
