import pytest
from datetime import date, time, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.storage.db import Database
from src.notifier.bot_handler import EmailBotHandler
from src.models.schedule import SchedulePayload, ScheduleDay, Lesson, LessonType


@pytest.mark.asyncio
async def test_setup_bot_commands(tmp_path):
    db_file = tmp_path / "test_menu.db"
    db = Database(f"sqlite+aiosqlite:///{db_file}")
    await db.init_db()

    mock_bot = MagicMock()
    mock_bot.set_my_commands = AsyncMock(return_value=True)

    handler = EmailBotHandler(
        bot=mock_bot,
        db=db,
        allowed_user_id=12345,
    )

    await handler.setup_bot_commands()
    assert mock_bot.set_my_commands.called
    called_commands = mock_bot.set_my_commands.call_args[0][0]
    assert len(called_commands) == 10
    cmd_names = [c.command for c in called_commands]
    assert "ticker" in cmd_names
    assert "timesheet" in cmd_names
    assert "today" in cmd_names
    assert "git" in cmd_names
    assert "lms" in cmd_names
    assert "emails" in cmd_names
    assert "methodist" in cmd_names
    assert "evening" in cmd_names
    assert "undo_clear" in cmd_names
    assert "help" in cmd_names


@pytest.mark.asyncio
async def test_handle_cmd_today_no_lessons(tmp_path):
    db_file = tmp_path / "test_today_empty.db"
    db = Database(f"sqlite+aiosqlite:///{db_file}")
    await db.init_db()

    mock_bot = MagicMock()
    mock_notifier = MagicMock()
    mock_notifier.send_message = AsyncMock()

    handler = EmailBotHandler(
        bot=mock_bot,
        db=db,
        notifier=mock_notifier,
        allowed_user_id=12345,
    )

    msg = MagicMock()
    msg.from_user.id = 12345
    msg.chat.id = 12345
    msg.answer = AsyncMock(return_value=MagicMock(delete=AsyncMock()))

    await handler.handle_cmd_today(msg)

    assert mock_notifier.send_message.called
    sent_text = mock_notifier.send_message.call_args[0][0]
    assert "Расписание ГУАП на сегодня" in sent_text
    assert "Пар в расписании нет" in sent_text


@pytest.mark.asyncio
async def test_handle_cmd_today_with_lessons(tmp_path):
    db_file = tmp_path / "test_today_lessons.db"
    db = Database(f"sqlite+aiosqlite:///{db_file}")
    await db.init_db()

    today = date.today()
    payload = SchedulePayload(
        group_or_teacher_id="123",
        fetched_at=datetime.now(timezone.utc),
        days=[
            ScheduleDay(
                date=today,
                lessons=[
                    Lesson(
                        subject="Физика",
                        lesson_type=LessonType.LAB,
                        room="13-05",
                        group="1241",
                        date=today,
                        start_time=time(9, 30),
                        end_time=time(11, 0),
                    )
                ]
            )
        ]
    )
    from src import config
    source_id = f"rasp_guap_{config.SCHEDULE_TARGET_ID}"
    await db.upsert_monitored_source(source_id, "schedule_guap", "Test Schedule", {})
    await db.save_snapshot(source_id, "hash123", payload.model_dump_json())

    mock_bot = MagicMock()
    mock_notifier = MagicMock()
    mock_notifier.send_message = AsyncMock()

    handler = EmailBotHandler(
        bot=mock_bot,
        db=db,
        notifier=mock_notifier,
        allowed_user_id=12345,
    )

    msg = MagicMock()
    msg.from_user.id = 12345
    msg.chat.id = 12345
    msg.answer = AsyncMock(return_value=MagicMock(delete=AsyncMock()))

    await handler.handle_cmd_today(msg)

    assert mock_notifier.send_message.called
    sent_text = mock_notifier.send_message.call_args[0][0]
    assert "Расписание ГУАП на сегодня" in sent_text
    assert "Физика" in sent_text
    assert "13-05" in sent_text
    assert "1241" in sent_text
