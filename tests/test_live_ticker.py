import pytest
from datetime import date, time, datetime, timezone
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, MagicMock

from src import config
from src.storage.db import Database
from src.models.schedule import SchedulePayload, ScheduleDay, Lesson, LessonType
from src.notifier.live_ticker import (
    LiveTickerService,
    build_ticker_keyboard,
    SCREEN_SCHEDULE,
    SCREEN_EMAILS,
    SCREEN_TIMESHEET,
    SCREEN_SYSTEM,
)
from src.notifier.bot_handler import EmailBotHandler


@pytest.fixture
def mock_now():
    return datetime(2026, 10, 1, 12, 0, 0, tzinfo=ZoneInfo(config.TZ))


def test_build_ticker_keyboard():
    kb_sched = build_ticker_keyboard(SCREEN_SCHEDULE)
    assert len(kb_sched.inline_keyboard) == 3
    # Check that schedule button is highlighted
    row0_texts = [btn.text for btn in kb_sched.inline_keyboard[0]]
    assert "• 🎓 Пары •" in row0_texts[0]
    assert "📬 Почта" == row0_texts[1]

    kb_mail = build_ticker_keyboard(SCREEN_EMAILS)
    row0_mail_texts = [btn.text for btn in kb_mail.inline_keyboard[0]]
    assert "🎓 Пары" == row0_mail_texts[0]
    assert "• 📬 Почта •" in row0_mail_texts[1]


def test_compute_ticker_line_no_lessons(mock_now):
    service = LiveTickerService(db=MagicMock())
    email_metrics = {"pending_count": 0, "pending_actionable": []}
    timesheet_metrics = {"morning_delta": 1.5, "worked_hours": 20.0}

    line = service.compute_ticker_line([], email_metrics, timesheet_metrics, mock_now)
    assert "⚡ Пар нет" in line
    assert "📬 0 треб." in line
    assert "⏱️ Тидекс: +1.5ч" in line


def test_compute_ticker_line_current_lesson(mock_now):
    service = LiveTickerService(db=MagicMock())
    lessons = [
        Lesson(
            subject="Физика",
            lesson_type=LessonType.LAB,
            room="13-04 (Гастелло 15)",
            group="1241",
            date=mock_now.date(),
            start_time=time(11, 10),
            end_time=time(12, 45),
        )
    ]
    email_metrics = {"pending_count": 0, "pending_actionable": []}
    timesheet_metrics = {"morning_delta": -0.5, "worked_hours": 15.0}

    line = service.compute_ticker_line(lessons, email_metrics, timesheet_metrics, mock_now)
    assert "⚡ СЕЙЧАС: [Лаб] Физика (13-04)" in line
    assert "📬 0 треб." in line
    assert "⏱️ Тидекс: -0.5ч" in line


def test_compute_ticker_line_upcoming_lesson(mock_now):
    service = LiveTickerService(db=MagicMock())
    # 30 minutes from mock_now (12:00 -> 12:30)
    lessons = [
        Lesson(
            subject="Физические основы нанотехнологий",
            lesson_type=LessonType.LECTURE,
            room="13-02",
            group="М631К",
            date=mock_now.date(),
            start_time=time(12, 30),
            end_time=time(14, 0),
        )
    ]
    email_metrics = {
        "pending_count": 2,
        "pending_actionable": [{"sender_name": "Виталий Лавров", "subject": "Re: Доступ"}],
    }
    timesheet_metrics = {"morning_delta": 0.0, "worked_hours": 25.0}

    line = service.compute_ticker_line(lessons, email_metrics, timesheet_metrics, mock_now)
    assert "⚡ 12:30 [Лек] ФОНТ (через 30м, 13-02)" in line
    assert "⚠️ 📬 2 треб. ответ (Виталий)" in line
    assert "⏱️ Тидекс: 25.0ч" in line


def test_compute_ticker_line_all_past(mock_now):
    service = LiveTickerService(db=MagicMock())
    lessons = [
        Lesson(
            subject="Физика",
            lesson_type=LessonType.PRACTICE,
            room="13-08",
            group="1242",
            date=mock_now.date(),
            start_time=time(9, 30),
            end_time=time(11, 0),
        )
    ]
    email_metrics = {"pending_count": 0, "pending_actionable": []}
    timesheet_metrics = {"morning_delta": 0.0, "worked_hours": 0.0}

    line = service.compute_ticker_line(lessons, email_metrics, timesheet_metrics, mock_now)
    assert "⚡ Все пары завершены" in line


@pytest.mark.asyncio
async def test_db_live_ticker_persistence(tmp_path):
    db_file = tmp_path / "test_ticker.db"
    db = Database(f"sqlite+aiosqlite:///{db_file}")
    await db.init_db()

    # Empty initially
    assert await db.get_live_ticker(12345) is None
    assert await db.list_all_live_tickers() == []

    # Insert
    await db.set_live_ticker(chat_id=12345, message_id=999, current_screen="schedule")
    record = await db.get_live_ticker(12345)
    assert record is not None
    assert record["chat_id"] == 12345
    assert record["message_id"] == 999
    assert record["current_screen"] == "schedule"

    # Update screen
    await db.update_live_ticker_screen(12345, "emails")
    record = await db.get_live_ticker(12345)
    assert record["current_screen"] == "emails"

    # Upsert with new message_id
    await db.set_live_ticker(chat_id=12345, message_id=1001, current_screen="timesheet")
    record = await db.get_live_ticker(12345)
    assert record["message_id"] == 1001
    assert record["current_screen"] == "timesheet"

    # List
    all_tickers = await db.list_all_live_tickers()
    assert len(all_tickers) == 1

    # Delete
    await db.delete_live_ticker(12345)
    assert await db.get_live_ticker(12345) is None


@pytest.mark.asyncio
async def test_live_ticker_service_build_message(tmp_path, mock_now):
    db_file = tmp_path / "test_service.db"
    db = Database(f"sqlite+aiosqlite:///{db_file}")
    await db.init_db()

    # Seed snapshot
    payload = SchedulePayload(
        group_or_teacher_id="123",
        fetched_at=mock_now,
        days=[
            ScheduleDay(
                date=mock_now.date(),
                lessons=[
                    Lesson(
                        subject="Физика",
                        lesson_type=LessonType.LAB,
                        room="13-05",
                        group="1241",
                        date=mock_now.date(),
                        start_time=time(13, 0),
                        end_time=time(14, 30),
                    )
                ],
            )
        ],
    )
    source_id = f"rasp_guap_{config.SCHEDULE_TARGET_ID}"
    await db.upsert_monitored_source(source_id, "schedule_guap", "Test Schedule", {})
    await db.save_snapshot(source_id, "hash_test", payload.model_dump_json())

    service = LiveTickerService(db=db)

    # 1. Schedule screen
    text, kb = await service.build_ticker_message(current_screen=SCREEN_SCHEDULE, now_dt=mock_now)
    assert "⚡" in text
    assert "РАСПИСАНИЕ ГУАП НА СЕГОДНЯ" in text
    assert "Физика" in text
    assert "13-05" in text
    assert len(kb.inline_keyboard) == 3

    # 2. Emails screen
    text_em, kb_em = await service.build_ticker_message(current_screen=SCREEN_EMAILS, now_dt=mock_now)
    assert "ЦЕНТР ВХОДЯЩЕЙ ПОЧТЫ" in text_em
    assert "Всего поступило" in text_em

    # 3. Timesheet screen
    text_ts, kb_ts = await service.build_ticker_message(current_screen=SCREEN_TIMESHEET, now_dt=mock_now)
    assert "ТАБЕЛЬ И БАЛАНС ЧАСОВ" in text_ts
    assert "ООО «ТИДЕКС»" in text_ts

    # 4. System screen
    text_sys, kb_sys = await service.build_ticker_message(current_screen=SCREEN_SYSTEM, now_dt=mock_now)
    assert "СТАТУС СИСТЕМ И ДЕМОНОВ" in text_sys
    assert "assistant-worker.service" in text_sys


@pytest.mark.asyncio
async def test_bot_handler_ticker_command_and_callbacks(tmp_path):
    db_file = tmp_path / "test_handler_ticker.db"
    db = Database(f"sqlite+aiosqlite:///{db_file}")
    await db.init_db()

    mock_bot = MagicMock()
    mock_bot.pin_chat_message = AsyncMock(return_value=True)

    mock_notifier = MagicMock()
    mock_notifier.send_message = AsyncMock(return_value=[888])
    mock_notifier.edit_rich_message = AsyncMock(return_value=True)

    handler = EmailBotHandler(
        bot=mock_bot,
        db=db,
        notifier=mock_notifier,
        allowed_user_id=12345,
    )

    msg = MagicMock()
    msg.from_user.id = 12345
    msg.chat.id = 12345
    msg.answer = AsyncMock()

    # 1. First invocation: sends new message and pins it
    await handler.handle_cmd_ticker(msg)
    assert mock_notifier.send_message.called
    assert mock_bot.pin_chat_message.called
    assert mock_bot.pin_chat_message.call_args[1]["message_id"] == 888

    stored = await db.get_live_ticker(12345)
    assert stored is not None
    assert stored["message_id"] == 888

    # 2. Second invocation: edits existing message in-place
    mock_notifier.send_message.reset_mock()
    await handler.handle_cmd_ticker(msg)
    assert not mock_notifier.send_message.called
    assert mock_notifier.edit_rich_message.called
    assert mock_notifier.edit_rich_message.call_args[1]["message_id"] == 888

    # 3. Callback screen switch to 'emails'
    cb = MagicMock()
    cb.from_user.id = 12345
    cb.message.chat.id = 12345
    cb.message.message_id = 888
    cb.data = "tk:sc:emails"
    cb.answer = AsyncMock()

    await handler.cb_ticker_switch_screen(cb)
    assert mock_notifier.edit_rich_message.called
    assert cb.answer.called
    stored = await db.get_live_ticker(12345)
    assert stored["current_screen"] == "emails"

    # 4. Callback refresh
    cb_ref = MagicMock()
    cb_ref.from_user.id = 12345
    cb_ref.message.chat.id = 12345
    cb_ref.message.message_id = 888
    cb_ref.data = "tk:refresh"
    cb_ref.answer = AsyncMock()

    await handler.cb_ticker_refresh(cb_ref)
    assert mock_notifier.edit_rich_message.called
    assert cb_ref.answer.called
