import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.storage.db import Database
from src.notifier.telegram import (
    TelegramNotifier,
    build_lms_tasks_keyboard,
    build_lms_pub_hide_keyboard,
)
from src.notifier.bot_handler import EmailBotHandler
from src.main import run_lms_monitor_cycle


@pytest.fixture
async def in_memory_db():
    db = Database(":memory:")
    await db.init_db()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_lms_submissions_db_crud(in_memory_db: Database):
    # 1. Insert new student submission
    inserted = await in_memory_db.record_lms_submission(
        report_id=501,
        task_id=3418,
        task_title="Попов: Лабораторная работа №1",
        student_name="Иванов Иван Иванович",
        group_name="1632",
        status="Ожидает проверки",
        upload_date="2026-09-29 18:30",
        download_url="/inside/professor/reports/501/download",
    )
    assert inserted is True

    # 2. Insert duplicate report_id (should ignore and return False)
    dup = await in_memory_db.record_lms_submission(
        report_id=501,
        task_id=3418,
        task_title="Попов: Лабораторная работа №1",
        student_name="Иванов Иван Иванович",
        group_name="1632",
        status="Ожидает проверки",
    )
    assert dup is False

    # 3. Check unnotified submissions
    unnotified = await in_memory_db.get_unnotified_lms_submissions()
    assert len(unnotified) == 1
    assert unnotified[0]["report_id"] == 501
    assert unnotified[0]["student_name"] == "Иванов Иван Иванович"
    assert unnotified[0]["notified_at"] is None

    # 4. Mark notified
    await in_memory_db.mark_lms_submission_notified(501)
    unnotified_after = await in_memory_db.get_unnotified_lms_submissions()
    assert len(unnotified_after) == 0

    # 5. List submissions
    all_subs = await in_memory_db.list_lms_submissions(limit=10)
    assert len(all_subs) == 1
    assert all_subs[0]["notified_at"] is not None


def test_lms_keyboards_structure():
    kb = build_lms_tasks_keyboard()
    rows = kb.inline_keyboard
    assert len(rows) == 3
    assert rows[0][0].text == "👁️ Опубликовать..."
    assert rows[0][0].callback_data == "lms:pub_menu"
    assert rows[0][1].text == "🔒 Скрыть..."
    assert rows[0][1].callback_data == "lms:hide_menu"
    assert rows[1][0].text == "➕ Создать задание"
    assert rows[1][0].callback_data == "lms:create_menu"
    assert rows[1][1].text == "🗑️ Удалить задание"
    assert rows[1][1].callback_data == "lms:del_prompt"
    assert rows[2][0].text == "📥 Сданные отчеты"
    assert rows[2][0].callback_data == "lms:reports"

    pub_kb = build_lms_pub_hide_keyboard("lms:pub:")
    pub_rows = pub_kb.inline_keyboard
    assert len(pub_rows) == 4
    assert pub_rows[0][0].text == "Лаб №1"
    assert pub_rows[0][0].callback_data == "lms:pub:1"
    assert pub_rows[2][0].text == "⚡ Все лабораторные"
    assert pub_rows[2][0].callback_data == "lms:pub:all"


def test_lms_tasks_overview_formatter(in_memory_db: Database):
    notifier = TelegramNotifier(bot_token="fake:token", user_id="12345")
    handler = EmailBotHandler(db=in_memory_db, notifier=notifier, allowed_user_id=12345)

    sample_tasks = [
        {"id": 3418, "title": "Попов: Лабораторная работа №1", "subject": "Физика (1632)", "is_public": True},
        {"id": 3419, "title": "Попов: Лабораторная работа №2", "subject": "Физика (1632)", "is_public": False},
        {"id": 3420, "title": "Попов: Лабораторная работа №1", "subject": "Физика (М562)", "is_public": True},
    ]

    overview = handler._format_lms_tasks_overview(sample_tasks)
    assert "Всего заданий в ЛК: **3**" in overview
    assert "Опубликовано (видно студентам): **2** 👁️" in overview
    assert "Скрыто (в черновиках): **1** 🔒" in overview
    assert "Гр. 1632" in overview
    assert "👁️ №1 (`3418`)" in overview
    assert "🔒 №2 (`3419`)" in overview


@pytest.mark.asyncio
async def test_cmd_lms_tasks(in_memory_db: Database):
    notifier = TelegramNotifier(bot_token="fake:token", user_id="12345")
    mock_lms = MagicMock()
    mock_lms.list_tasks.return_value = [
        {"id": 3418, "title": "Попов: Лабораторная работа №1", "subject": "Физика (1632)", "is_public": True},
        {"id": 3419, "title": "Попов: Лабораторная работа №2", "subject": "Физика (1632)", "is_public": False},
    ]
    handler = EmailBotHandler(db=in_memory_db, notifier=notifier, allowed_user_id=12345, lms_client=mock_lms)

    mock_msg = MagicMock()
    mock_msg.from_user.id = 12345
    status_msg = AsyncMock()
    mock_msg.answer = AsyncMock(return_value=status_msg)

    await handler.handle_cmd_lms_tasks(mock_msg)
    mock_msg.answer.assert_called_once()
    status_msg.edit_text.assert_called_once()
    args, kwargs = status_msg.edit_text.call_args
    assert "Гр. 1632" in args[0]
    assert kwargs.get("reply_markup") is not None


@pytest.mark.asyncio
async def test_lms_visibility_toggle(in_memory_db: Database):
    notifier = TelegramNotifier(bot_token="fake:token", user_id="12345")
    mock_lms = MagicMock()
    mock_lms.list_tasks.return_value = [
        {"id": 3418, "title": "Попов: Лабораторная работа №1", "is_public": True},
        {"id": 3419, "title": "Попов: Лабораторная работа №2", "is_public": False},
        {"id": 3420, "title": "Попов: Лабораторная работа №2", "is_public": False},
    ]
    mock_lms.set_task_visibility.return_value = True

    handler = EmailBotHandler(db=in_memory_db, notifier=notifier, allowed_user_id=12345, lms_client=mock_lms)

    mock_msg = MagicMock()
    mock_msg.from_user.id = 12345
    status_msg = AsyncMock()
    mock_msg.answer = AsyncMock(return_value=status_msg)

    # Publish Lab 2
    await handler._execute_visibility_change(mock_msg, target_code="2", is_public=True)

    assert mock_lms.set_task_visibility.call_count == 2
    mock_lms.set_task_visibility.assert_any_call(3419, True)
    mock_lms.set_task_visibility.assert_any_call(3420, True)

    status_args, _ = status_msg.edit_text.call_args
    assert "Обновлено заданий: **2**" in status_args[0]


@pytest.mark.asyncio
async def test_lms_create_task_flow(in_memory_db: Database):
    notifier = TelegramNotifier(bot_token="fake:token", user_id="12345")
    mock_lms = MagicMock()
    mock_lms.get_disciplines.return_value = [
        {
            "id": 3444128,
            "text": "Физика (1632)",
            "semester": 28,
            "groups": [{"id": 8008, "text": "1632"}],
        }
    ]
    mock_lms.create_task.return_value = {
        "status": "success",
        "created_id": 9999,
        "name": "Попов: Лабораторная работа №5",
    }

    mock_bot = AsyncMock()
    status_msg = AsyncMock()
    mock_bot.send_message.return_value = status_msg

    handler = EmailBotHandler(
        db=in_memory_db,
        notifier=notifier,
        bot=mock_bot,
        allowed_user_id=12345,
        lms_client=mock_lms,
    )

    await handler._create_task_from_params(chat_id=12345, group_name="1632", task_title="Попов: Лабораторная работа №5")

    mock_lms.create_task.assert_called_once_with(
        name="Попов: Лабораторная работа №5",
        subject_id=3444128,
        group_ids=[8008],
        semester_id=28,
        is_public=False,
    )
    status_args, _ = status_msg.edit_text.call_args
    assert "Задание успешно создано!" in status_args[0]
    assert "9999" in status_args[0]


@pytest.mark.asyncio
async def test_lms_delete_task_flow(in_memory_db: Database):
    notifier = TelegramNotifier(bot_token="fake:token", user_id="12345")
    mock_lms = MagicMock()
    mock_lms.delete_task.return_value = True

    handler = EmailBotHandler(db=in_memory_db, notifier=notifier, allowed_user_id=12345, lms_client=mock_lms)

    cb = AsyncMock()
    cb.from_user.id = 12345
    cb.data = "lms:del_confirm:3425"
    cb.message = AsyncMock()

    await handler.cb_lms_del_confirm(cb)
    mock_lms.delete_task.assert_called_once_with(3425)
    cb.message.edit_text.assert_called_once()
    assert "успешно удалено" in cb.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_lms_monitor_cycle(in_memory_db: Database):
    mock_notifier = AsyncMock()
    mock_lms = MagicMock()
    mock_lms.list_tasks.return_value = [
        {"id": 3418, "title": "Попов: Лабораторная работа №1", "is_public": True},
        {"id": 3419, "title": "Попов: Лабораторная работа №2", "is_public": False},
    ]
    mock_lms.get_task_details.return_value = {
        "task_id": 3418,
        "reports": [
            {
                "report_id": 777,
                "student_name": "Петров Петр",
                "group": "1632",
                "status": "Ожидает проверки",
                "upload_date": "2026-09-29 19:00",
                "download_url": "/inside/professor/reports/777/download",
            }
        ],
    }

    # Run monitor cycle
    await run_lms_monitor_cycle(in_memory_db, mock_lms, mock_notifier)

    # 1. Should query task details only for public tasks
    mock_lms.get_task_details.assert_called_once_with(3418)

    # 2. Should dispatch notification to user
    mock_notifier.send_message.assert_called_once()
    notif_text = mock_notifier.send_message.call_args[0][0]
    assert "Петров Петр" in notif_text
    assert "гр. 1632" in notif_text
    assert "Лабораторная работа №1" in notif_text

    # 3. Check DB marked as notified
    unnotified = await in_memory_db.get_unnotified_lms_submissions()
    assert len(unnotified) == 0

    # 4. Running a second time should NOT resend notification
    mock_notifier.send_message.reset_mock()
    await run_lms_monitor_cycle(in_memory_db, mock_lms, mock_notifier)
    mock_notifier.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_lms_natural_language_triggers(in_memory_db: Database):
    notifier = TelegramNotifier(bot_token="fake:token", user_id="12345")
    mock_lms = MagicMock()
    mock_lms.list_tasks.return_value = [
        {"id": 3418, "title": "Попов: Лабораторная работа №1", "is_public": True},
    ]
    handler = EmailBotHandler(db=in_memory_db, notifier=notifier, allowed_user_id=12345, lms_client=mock_lms)

    # "задания"
    msg_tasks = AsyncMock()
    msg_tasks.from_user.id = 12345
    msg_tasks.text = "задания"
    msg_tasks.answer = AsyncMock(return_value=AsyncMock())

    await handler.handle_user_text(msg_tasks)
    mock_lms.list_tasks.assert_called()

    # "опубликуй лаб 2"
    msg_pub = AsyncMock()
    msg_pub.from_user.id = 12345
    msg_pub.text = "опубликуй лаб 2"
    msg_pub.answer = AsyncMock(return_value=AsyncMock())

    await handler.handle_user_text(msg_pub)
    # Checks visibility change call


@pytest.mark.asyncio
async def test_cmd_lms_reports_instant_cached_response(in_memory_db: Database):
    """Verify that /reports returns instantly from SQLite without blocking network scraping."""
    await in_memory_db.record_lms_submission(
        report_id=888,
        task_id=3418,
        task_title="Попов: Лабораторная работа №1",
        student_name="Сидоров Сидор",
        group_name="1632",
        status="Ожидает проверки",
        upload_date="2026-09-30 11:00",
        download_url="/inside/professor/reports/888/download",
    )

    mock_lms = MagicMock()
    notifier = TelegramNotifier(bot_token="fake:token", user_id="12345")
    handler = EmailBotHandler(db=in_memory_db, notifier=notifier, allowed_user_id=12345, lms_client=mock_lms)

    mock_msg = AsyncMock()
    mock_msg.from_user.id = 12345

    await handler.handle_cmd_lms_reports(mock_msg)

    # Crucial check: LMS client network scraping was NOT called
    mock_lms.list_tasks.assert_not_called()
    mock_lms.get_task_details.assert_not_called()

    # Message answered with cached submissions
    mock_msg.answer.assert_called_once()
    answer_text = mock_msg.answer.call_args[0][0]
    assert "Сидоров Сидор" in answer_text
    assert "Лабораторная работа №1" in answer_text
    assert "Всего отчетов: **1**" in answer_text
    assert "lms:sync_reports" in str(mock_msg.answer.call_args[1].get("reply_markup"))
