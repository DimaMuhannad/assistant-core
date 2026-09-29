"""Tests for AADHk Time Recording parser and SUAI schedule cross-validation."""

import sqlite3
import pytest
from datetime import datetime, date, time
from pathlib import Path

from src.connectors.aadhk.parser import AadhkIngestionService, parse_timestamp_val
from src.models.schedule import SchedulePayload, ScheduleDay, Lesson, LessonType
from src.storage.db import Database


def test_parse_timestamp_val():
    # Milliseconds
    ts_ms = 1759140000000
    dt1 = parse_timestamp_val(ts_ms)
    assert dt1 is not None

    # String format
    dt2 = parse_timestamp_val("2026-09-30 09:30:00")
    assert dt2 is not None
    assert dt2.year == 2026
    assert dt2.hour == 9
    assert dt2.minute == 30

    # Invalid
    assert parse_timestamp_val("invalid-time") is None
    assert parse_timestamp_val(None) is None


@pytest.mark.asyncio
async def test_aadhk_ingestion_and_conflict_detection(tmp_path: Path):
    # 1. Create mock assistant DB
    asst_db_path = tmp_path / "assistant.db"
    db = Database(str(asst_db_path))
    await db.init_db()

    # Seed mock SUAI schedule into assistant DB
    mock_payload = SchedulePayload(
        group_or_teacher_id="2903",
        fetched_at=datetime.now(),
        days=[
            ScheduleDay(
                date=date(2026, 9, 30),
                lessons=[
                    Lesson(
                        subject="Физические основы нанотехнологий",
                        lesson_type=LessonType.LECTURE,
                        date=date(2026, 9, 30),
                        start_time=time(9, 30),
                        end_time=time(11, 0),
                        room="31-04а",
                        group="м431к",
                    )
                ],
            )
        ],
    )
    await db.upsert_monitored_source(
        source_id="rasp_guap_2903",
        source_type="schedule_guap",
        display_name="Расписание ГУАП",
        config={"target_id": "2903"},
    )
    await db.save_snapshot("rasp_guap_2903", "hash_test", mock_payload.model_dump_json())

    # 2. Create mock AADHk SQLite backup
    aadhk_file = tmp_path / "aadhk_backup.db"
    conn = sqlite3.connect(str(aadhk_file))
    cur = conn.cursor()
    cur.execute("CREATE TABLE project (_id INTEGER PRIMARY KEY, name TEXT);")
    cur.execute("CREATE TABLE task (_id INTEGER PRIMARY KEY, name TEXT, project_id INTEGER);")
    cur.execute(
        """
        CREATE TABLE time_record (
            _id INTEGER PRIMARY KEY,
            startTime TEXT,
            endTime TEXT,
            project_id INTEGER,
            task_id INTEGER,
            note TEXT
        );
        """
    )
    cur.execute("INSERT INTO project VALUES (1, 'ООО Тидекс');")
    cur.execute("INSERT INTO task VALUES (1, 'Юстировка ТГц интерферометра', 1);")

    # Shift 1: 2026-09-29 14:00 - 18:00 (No conflict)
    cur.execute(
        "INSERT INTO time_record VALUES (101, '2026-09-29 14:00:00', '2026-09-29 18:00:00', 1, 1, 'Калибровка лазера');"
    )
    # Shift 2: 2026-09-30 09:00 - 12:00 (Overlaps with SUAI lesson 09:30-11:00!)
    cur.execute(
        "INSERT INTO time_record VALUES (102, '2026-09-30 09:00:00', '2026-09-30 12:00:00', 1, 1, 'Стендовые измерения');"
    )
    conn.commit()
    conn.close()

    # 3. Test ingestion
    service = AadhkIngestionService(db)
    res = await service.ingest_backup_file(aadhk_file)

    assert res["parsed_count"] == 2
    assert res["new_inserted_count"] == 2
    assert res["conflicts_count"] == 1
    assert res["total_hours"] == 7.0  # 4h + 3h

    # 4. Check DB records
    records = await db.list_timesheet_records()
    assert len(records) == 2

    conflicts = await db.get_timesheet_conflicts()
    assert len(conflicts) == 1
    assert "Пересечение с парой ГУАП" in conflicts[0]["conflict_details"]
    assert "31-04а" in conflicts[0]["conflict_details"]

    # 5. Idempotency test (re-import should not create duplicates)
    res2 = await service.ingest_backup_file(aadhk_file)
    assert res2["new_inserted_count"] == 0

    await db.close()


@pytest.mark.asyncio
async def test_aadhk_mobile_times_schema_and_reconciliation(tmp_path: Path):
    asst_db_path = tmp_path / "assistant_times.db"
    db = Database(str(asst_db_path))
    await db.init_db()

    # 1. Create mock AADHk backup using mobile TIMES schema
    aadhk_file = tmp_path / "com.aadhk.time_mobile.db"
    conn = sqlite3.connect(str(aadhk_file))
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE TIMES (
            projectName TEXT,
            notes TEXT,
            remark TEXT,
            amountPerhour FLOAT,
            date1 TEXT,
            date2 TEXT,
            working INTEGER,
            amount FLOAT
        );
        """
    )
    # Shift 1: 2026-09-28 10:00 - 14:00 (4 hours, 1882 rub)
    cur.execute(
        """
        INSERT INTO TIMES VALUES (
            'Работа', 'Эксперименты на терагерцовом спектрометре', '', 470.5,
            '2026-09-28 10:00', '2026-09-28 14:00', 240, 1882.0
        );
        """
    )
    # Shift 2: 2026-09-29 15:00 - 18:00 (3 hours, 1411.5 rub)
    cur.execute(
        """
        INSERT INTO TIMES VALUES (
            'Тидекс', 'Обработка спектров пропускания', '', 470.5,
            '2026-09-29 15:00', '2026-09-29 18:00', 180, 1411.5
        );
        """
    )
    conn.commit()
    conn.close()

    service = AadhkIngestionService(db)
    res = await service.ingest_backup_file(aadhk_file)
    assert res["parsed_count"] == 2
    assert res["new_inserted_count"] == 2
    assert res["conflicts_count"] == 0  # No schedule in DB yet

    summary = await db.get_timesheet_summary()
    assert summary["total_shifts"] == 2
    assert summary["total_hours"] == 7.0
    assert summary["clean_hours"] == 7.0
    assert summary["conflict_hours"] == 0.0
    assert summary["total_amount"] == 3293.5

    # 2. Add schedule snapshot covering 2026-09-28 (11:10 - 12:40 lab work)
    sched_payload = SchedulePayload(
        group_or_teacher_id="2903",
        fetched_at=datetime.now(),
        days=[
            ScheduleDay(
                date=date(2026, 9, 28),
                lessons=[
                    Lesson(
                        subject="Распределенные системы",
                        lesson_type=LessonType.LAB,
                        date=date(2026, 9, 28),
                        start_time=time(11, 10),
                        end_time=time(12, 40),
                        room="12-04",
                        group="2241",
                    )
                ],
            )
        ],
    )
    await db.upsert_monitored_source(
        source_id="rasp_guap_2903",
        source_type="schedule_guap",
        display_name="Расписание ГУАП",
        config={"target_id": "2903"},
    )
    await db.save_snapshot("rasp_guap_2903", "hash_2903_28", sched_payload.model_dump_json())


    # 3. Run reconciliation
    rec_res = await service.reconcile_all_conflicts()
    assert rec_res["total_checked"] == 2
    assert rec_res["conflicts_found"] == 1
    assert rec_res["clean_hours"] == 3.0  # Shift 2 is clean
    assert rec_res["conflict_hours"] == 4.0  # Shift 1 overlaps (90 min overlap)

    # 4. Check detailed report
    report = await service.get_timesheet_report()
    assert len(report["conflicts"]) == 1
    conflict_desc = report["conflicts"][0]["conflict_details"]
    assert "Распределенные системы" in conflict_desc
    assert "90 мин" in conflict_desc
    assert "12-04" in conflict_desc

    await db.close()

