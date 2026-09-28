from datetime import datetime, timezone
import pytest
from src.detector.tg_filter import TelegramMessageFilter
from src.models.message import TelegramMessage
from src.storage.db import Database


@pytest.fixture
def message_filter() -> TelegramMessageFilter:
    return TelegramMessageFilter()


@pytest.fixture
async def db() -> Database:
    test_db = Database(":memory:")
    await test_db.init_db()
    yield test_db
    await test_db.close()


def create_msg(msg_id: int, text: str, has_media: bool = False) -> TelegramMessage:
    return TelegramMessage(
        message_id=msg_id,
        chat_id=-100123456789,
        chat_title="Учебная группа 3526",
        sender_id=922302501,
        sender_name="Dmitry Popov",
        text=text,
        date=datetime.now(timezone.utc),
        has_media=has_media,
    )


def test_filter_noise_messages(message_filter: TelegramMessageFilter) -> None:
    noise_texts = ["ок", "ок!", "Спасибо", "принято", "+", "ладно", "договорились"]
    for text in noise_texts:
        msg = create_msg(1, text)
        res = message_filter.filter_message(msg)
        assert not res.is_relevant, f"Expected '{text}' to be filtered out as noise"


def test_filter_short_messages(message_filter: TelegramMessageFilter) -> None:
    msg = create_msg(2, "тест")
    res = message_filter.filter_message(msg)
    assert not res.is_relevant


def test_filter_deadline_detection(message_filter: TelegramMessageFilter) -> None:
    text = "Срочно! Дедлайн по отчету по лабораторной работе - сдать до 25.10 включительно."
    msg = create_msg(3, text)
    res = message_filter.filter_message(msg)
    assert res.is_relevant
    assert res.priority == 3
    assert res.category == "deadline"
    assert any("дедлайн" in k.lower() or "сдать до" in k.lower() for k in res.matched_keywords)


def test_filter_schedule_change_detection(message_filter: TelegramMessageFilter) -> None:
    text = "Пара переносится на дистант в онлайн, вместо пары в ауд. 13-05."
    msg = create_msg(4, text)
    res = message_filter.filter_message(msg)
    assert res.is_relevant
    assert res.priority == 3
    assert res.category == "schedule_change"


def test_filter_exam_session_detection(message_filter: TelegramMessageFilter) -> None:
    text = "Зачет и экзамен по дисциплине пройдут в пятницу, консультация в 10:00."
    msg = create_msg(5, text)
    res = message_filter.filter_message(msg)
    assert res.is_relevant
    assert res.priority == 3
    assert res.category == "exam_session"


def test_filter_faculty_notice_detection(message_filter: TelegramMessageFilter) -> None:
    text = "Распоряжение деканата ГУАП: всем старостам явиться на собрание кафедры."
    msg = create_msg(6, text)
    res = message_filter.filter_message(msg)
    assert res.is_relevant
    assert res.priority == 2
    assert res.category == "faculty_notice"


@pytest.mark.asyncio
async def test_db_snapshot_deduplication_and_action_item(db: Database) -> None:
    source_id = "tg_-100123456789"
    await db.upsert_monitored_source(
        source_id=source_id,
        source_type="telegram_group",
        display_name="Тестовый чат",
        config={"peer": "-100123456789"},
    )

    msg = create_msg(101, "Внимание! Срочный дедлайн сдать до 12.10 проект.")
    raw_payload = msg.model_dump_json()

    # 1. Save first snapshot
    snap_id1 = await db.save_snapshot(source_id, msg.content_hash, raw_payload)
    assert snap_id1 > 0

    # 2. Check existence by hash
    existing = await db.get_content_snapshot_by_hash(source_id, msg.content_hash)
    assert existing is not None
    assert existing["id"] == snap_id1

    # 3. Save action item
    action_id = await db.save_action_item(
        source_type="telegram_group",
        priority_score=3,
        summary_text="[DEADLINE] Срочный дедлайн сдать до 12.10 проект.",
        payload={"message_id": msg.message_id, "chat_id": msg.chat_id},
        status="pending",
    )
    assert action_id > 0

    # 4. Fetch pending items
    items = await db.get_pending_action_items()
    assert len(items) == 1
    assert items[0]["priority_score"] == 3
    assert "DEADLINE" in items[0]["summary_text"]

    # 5. Update status
    await db.update_action_item_status(action_id, "processed")
    pending_after = await db.get_pending_action_items()
    assert len(pending_after) == 0


def test_temporal_classifier_past_and_future() -> None:
    from datetime import date, datetime
    from src.detector.temporal import TemporalClassifier

    ref = date(2026, 9, 28)

    # 1. Past online lesson from 21.09
    past_msg = "давайте сегодня проведем пару онлайн"
    t1 = TemporalClassifier.analyze(past_msg, datetime(2026, 9, 21), reference_date=ref)
    assert t1.is_expired
    assert t1.freshness_label == "EXPIRED"

    # 2. Rescheduling from 25.09
    resched_msg = "Завтра занятие в аудитории там и обсудим переносы"
    t2 = TemporalClassifier.analyze(resched_msg, datetime(2026, 9, 25), reference_date=ref)
    assert t2.is_expired
    assert t2.freshness_label == "EXPIRED"

    # 3. Future deadline to 03.10
    future_dl = "Домашнее задание к 03.10"
    t3 = TemporalClassifier.analyze(future_dl, datetime(2026, 9, 26), reference_date=ref)
    assert not t3.is_expired
    assert t3.freshness_label == "ACTIVE_FUTURE"
    assert t3.days_remaining == 5

    # 4. Past deadline to 26.09
    past_dl = "Домашнее задание к 26.09"
    t4 = TemporalClassifier.analyze(past_dl, datetime(2026, 9, 21), reference_date=ref)
    assert t4.is_expired
    assert t4.freshness_label == "EXPIRED"

