import hashlib
import json
import pytest
from datetime import datetime, timezone, date, time

from src.models.schedule import Lesson, LessonType, ScheduleDay, SchedulePayload, ScheduleDiff
from src.detector.diff import ScheduleChangeDetector
from src.storage.db import Database
from src.parser.schedule_parser import ScheduleParser, FetchResult


# ---------------------------------------------------------
# 1. Pydantic v2 Models & Deterministic Hash Tests
# ---------------------------------------------------------

def test_lesson_model_validation():
    """Verify Lesson model validation, defaults, and deterministic hashing."""
    test_date = date(2026, 9, 28)
    test_start = time(9, 30)
    test_end = time(11, 0)

    lesson = Lesson(
        subject="Базы данных",
        lesson_type=LessonType.PRACTICE,
        date=test_date,
        start_time=test_start,
        end_time=test_end,
        room="13-05",
        teacher="Петров П.П.",
    )

    assert lesson.subject == "Базы данных"
    assert lesson.lesson_type == LessonType.PRACTICE
    assert lesson.room == "13-05"

    # Verify SHA-256 hash
    expected_raw_key = f"{test_date.isoformat()}_{test_start.isoformat()}_Базы данных_13-05"
    expected_hash = hashlib.sha256(expected_raw_key.encode("utf-8")).hexdigest()
    assert lesson.deterministic_hash == expected_hash

    # Verify defaults
    lesson_defaults = Lesson(
        subject="Физика",
        date=test_date,
        start_time=test_start,
        end_time=test_end,
    )
    assert lesson_defaults.lesson_type == LessonType.UNKNOWN
    assert lesson_defaults.room == "Не указана"


def test_schedule_payload_hash_stability():
    """Verify SchedulePayload stable hashing and serialization."""
    d1 = date(2026, 9, 28)
    d2 = date(2026, 9, 29)

    l1 = Lesson(
        subject="Математика",
        lesson_type=LessonType.LECTURE,
        date=d1,
        start_time=time(9, 30),
        end_time=time(11, 0),
        room="12-01",
    )
    l2 = Lesson(
        subject="Физика",
        lesson_type=LessonType.LAB,
        date=d2,
        start_time=time(11, 10),
        end_time=time(12, 40),
        room="12-02",
    )

    payload = SchedulePayload(
        group_or_teacher_id="group_4321",
        fetched_at=datetime(2026, 9, 28, 10, 0, 0),
        days=[
            ScheduleDay(date=d1, lessons=[l1]),
            ScheduleDay(date=d2, lessons=[l2]),
        ],
    )

    # Hashes sorted
    all_hashes = "".join(sorted([l1.deterministic_hash, l2.deterministic_hash]))
    expected_payload_hash = hashlib.sha256(all_hashes.encode("utf-8")).hexdigest()

    assert payload.payload_hash == expected_payload_hash

    # Test JSON round-trip
    payload_json = payload.model_dump_json()
    restored = SchedulePayload.model_validate_json(payload_json)
    assert restored.payload_hash == payload.payload_hash
    assert len(restored.days) == 2


# ---------------------------------------------------------
# 2. Change Detector (Diff) Tests
# ---------------------------------------------------------

def test_change_detector_zero_duplicates_on_unchanged():
    """Verify that comparing identical schedules returns has_changes=False."""
    d = date(2026, 9, 28)
    lesson = Lesson(
        subject="История",
        date=d,
        start_time=time(9, 30),
        end_time=time(11, 0),
        room="11-01",
    )
    payload_v1 = SchedulePayload(
        group_or_teacher_id="test_group",
        fetched_at=datetime.now(timezone.utc),
        days=[ScheduleDay(date=d, lessons=[lesson])],
    )
    payload_v2 = SchedulePayload(
        group_or_teacher_id="test_group",
        fetched_at=datetime.now(timezone.utc),
        days=[ScheduleDay(date=d, lessons=[lesson])],
    )

    diff = ScheduleChangeDetector.compare(payload_v1, payload_v2)
    assert diff.has_changes is False
    assert len(diff.added_lessons) == 0
    assert len(diff.removed_lessons) == 0
    assert diff.unchanged_count == 1


def test_change_detector_identifies_added_and_removed():
    """Verify detection of added and removed lessons."""
    d = date(2026, 9, 28)
    l1 = Lesson(subject="Математика", date=d, start_time=time(9, 30), end_time=time(11, 0), room="101")
    l2 = Lesson(subject="Физика", date=d, start_time=time(11, 10), end_time=time(12, 40), room="102")
    l3 = Lesson(subject="Химия", date=d, start_time=time(13, 0), end_time=time(14, 30), room="103")

    old_payload = SchedulePayload(
        group_or_teacher_id="test_group",
        fetched_at=datetime.now(timezone.utc),
        days=[ScheduleDay(date=d, lessons=[l1, l2])],
    )
    new_payload = SchedulePayload(
        group_or_teacher_id="test_group",
        fetched_at=datetime.now(timezone.utc),
        days=[ScheduleDay(date=d, lessons=[l2, l3])],
    )

    diff = ScheduleChangeDetector.compare(old_payload, new_payload)
    assert diff.has_changes is True
    assert len(diff.added_lessons) == 1
    assert diff.added_lessons[0].subject == "Химия"
    assert len(diff.removed_lessons) == 1
    assert diff.removed_lessons[0].subject == "Математика"
    assert diff.unchanged_count == 1


# ---------------------------------------------------------
# 3. Async SQLite Storage Tests
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_sqlite_storage_lifecycle():
    """Verify table creation, source registration, and snapshot storage in SQLite."""
    # Use in-memory SQLite for test isolation
    db = Database(db_path=":memory:")
    await db.init_db()

    # 1. Monitored source upsert
    source_id = "test_schedule_source"
    await db.upsert_monitored_source(
        source_id=source_id,
        source_type="schedule_guap",
        display_name="Тестовое расписание",
        config={"target_id": "1234"},
    )

    # 2. Save snapshot
    raw_payload_str = json.dumps({"test": "data", "status": "ok"})
    test_hash = "abc123hash"
    snap_id = await db.save_snapshot(
        source_id=source_id,
        content_hash=test_hash,
        raw_payload=raw_payload_str,
    )
    assert snap_id is not None
    assert snap_id > 0

    # 3. Retrieve latest snapshot
    latest = await db.get_latest_snapshot(source_id)
    assert latest is not None
    assert latest["source_id"] == source_id
    assert latest["content_hash"] == test_hash
    assert latest["raw_payload"] == raw_payload_str

    # 4. Record calendar sync
    sync_id = await db.record_calendar_sync(
        source_event_id="slot_001",
        google_event_id="g_event_001",
        calendar_id="primary",
        event_start=datetime(2026, 9, 28, 9, 30),
        event_end=datetime(2026, 9, 28, 11, 0),
        summary="Базы данных",
    )
    assert sync_id is not None
    record = await db.get_calendar_sync_record("slot_001")
    assert record is not None
    assert record["google_event_id"] == "g_event_001"
    assert record["summary"] == "Базы данных"
    await db.close()


# ---------------------------------------------------------
# 4. HTTP Parser Resilience & JSON Parsing Tests
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_parser_resilience_on_invalid_endpoint():
    """Verify that network errors do not raise unhandled exceptions and return FetchResult."""
    parser = ScheduleParser(base_url="http://non-existent-host-12345.local", timeout_seconds=1.0, max_retries=1)
    result = await parser.fetch_schedule_raw(target_id="123")
    assert result.success is False
    assert result.error_message is not None


def test_parser_json_payload():
    """Verify parsing structured JSON into SchedulePayload."""
    parser = ScheduleParser()
    raw_data = {
        "days": [
            {
                "date": "2026-09-28",
                "lessons": [
                    {
                        "subject": "Информатика",
                        "lesson_type": "LECTURE",
                        "start_time": "09:30:00",
                        "end_time": "11:00:00",
                        "room": "14-01",
                        "teacher": "Сидоров С.С.",
                    }
                ],
            }
        ]
    }
    payload = parser.parse_json_payload(json.dumps(raw_data), group_or_teacher_id="grp_1")
    assert payload.group_or_teacher_id == "grp_1"
    assert len(payload.days) == 1
    assert payload.days[0].lessons[0].subject == "Информатика"
    assert payload.days[0].lessons[0].lesson_type == LessonType.LECTURE
