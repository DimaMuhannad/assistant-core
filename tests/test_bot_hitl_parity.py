"""Интеграционные тесты паритета HITL-карточек и callback-обработчиков Telegram бота (HIT-02, D-01, D-06)."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message

from assistant_shared.db.migrator import run_migrations
from assistant_shared.hitl import (
    ConfirmationChannel,
    ConfirmationStatus,
    ConfirmationStore,
)
from src.notifier.bot_handler import EmailBotHandler
from src.storage.db import Database


@pytest.fixture
def test_db(tmp_path: Path) -> Database:
    db_file = tmp_path / "test_bot_hitl.db"
    run_migrations(db_file)
    db = Database(str(db_file))
    return db


@pytest.mark.asyncio
async def test_send_web_hitl_card(test_db: Database):
    """Проверяет формирование и отправку карточки подтверждения Web-действия в Telegram (D-01)."""
    store = ConfirmationStore(test_db.db_path)
    conf = await store.create_confirmation(
        persona_id="popov-da-default",
        action_type="delete_task",
        target_id="105",
        payload={"task_id": 105, "title": "Подготовка лабораторной работы"},
        channel=ConfirmationChannel.WEB,
        ttl_minutes=10,
    )

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    handler = EmailBotHandler(
        bot=mock_bot,
        db=test_db,
        allowed_user_id=12345,
    )

    await handler.send_web_hitl_card(conf.id, chat_id=12345)

    mock_bot.send_message.assert_called_once()
    call_kwargs = mock_bot.send_message.call_args[1]
    assert call_kwargs["chat_id"] == 12345
    text = call_kwargs["text"]
    assert "Запрос на удаление из Web-интерфейса" in text
    assert "Задача" in text
    assert "«Подготовка лабораторной работы»" in text
    assert "#105" in text

    kb = call_kwargs["reply_markup"]
    buttons = kb.inline_keyboard[0]
    assert len(buttons) == 2
    assert buttons[0].text == "🗑 Да, удалить"
    assert buttons[0].callback_data == f"hitl:confirm:{conf.id}"
    assert buttons[1].text == "❌ Отклонить"
    assert buttons[1].callback_data == f"hitl:reject:{conf.id}"


@pytest.mark.asyncio
async def test_cb_hitl_confirm_authorized(test_db: Database):
    """Проверяет подтверждение Web-удаления авторизованным владельцем."""
    # 1. Создаем реальную задачу в БД
    now_iso = datetime.now(timezone.utc).isoformat()
    async with test_db.connection() as conn:
        cursor = await conn.execute(
            """
            INSERT INTO tasks (title, area, priority, status, created_at, updated_at)
            VALUES ('Удаляемая задача', 'ГУАП', 'P2', 'todo', ?, ?);
            """,
            (now_iso, now_iso),
        )
        await conn.commit()
        task_id = cursor.lastrowid

    # 2. Создаем подтверждение в ConfirmationStore
    store = ConfirmationStore(test_db.db_path)
    conf = await store.create_confirmation(
        persona_id="popov-da-default",
        action_type="delete_task",
        target_id=str(task_id),
        payload={"task_id": task_id, "title": "Удаляемая задача"},
        channel=ConfirmationChannel.WEB,
    )

    user_id = 12345
    handler = EmailBotHandler(
        bot=MagicMock(),
        db=test_db,
        allowed_user_id=user_id,
    )

    cb = MagicMock(spec=CallbackQuery)
    cb.data = f"hitl:confirm:{conf.id}"
    cb.from_user = MagicMock()
    cb.from_user.id = user_id
    cb.from_user.first_name = "Дмитрий"
    cb.answer = AsyncMock()
    cb.message = MagicMock(spec=Message)
    cb.message.edit_text = AsyncMock()

    await handler.cb_hitl_confirm(cb)

    # Проверяем успешный ответ и редактирование
    cb.answer.assert_called_once_with("Удалено")
    cb.message.edit_text.assert_called_once()
    assert "успешно удален(а)" in cb.message.edit_text.call_args[0][0]

    # Задача физически удалена из БД
    async with test_db.connection() as conn:
        cur = await conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,))
        assert await cur.fetchone() is None

    # Статус подтверждения стал confirmed
    updated_conf = await store.get_confirmation(conf.id)
    assert updated_conf.status == ConfirmationStatus.CONFIRMED
    assert updated_conf.confirmed_by == str(user_id)


@pytest.mark.asyncio
async def test_cb_hitl_confirm_unauthorized(test_db: Database):
    """Проверяет блокировку подтверждения от неавторизованного пользователя (T-05-05)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    async with test_db.connection() as conn:
        cursor = await conn.execute(
            """
            INSERT INTO tasks (title, area, priority, status, created_at, updated_at)
            VALUES ('Защищенная задача', 'ГУАП', 'P2', 'todo', ?, ?);
            """,
            (now_iso, now_iso),
        )
        await conn.commit()
        task_id = cursor.lastrowid

    store = ConfirmationStore(test_db.db_path)
    conf = await store.create_confirmation(
        persona_id="popov-da-default",
        action_type="delete_task",
        target_id=str(task_id),
        payload={"task_id": task_id, "title": "Защищенная задача"},
    )

    owner_id = 12345
    intruder_id = 99999
    handler = EmailBotHandler(
        bot=MagicMock(),
        db=test_db,
        allowed_user_id=owner_id,
    )

    cb = MagicMock(spec=CallbackQuery)
    cb.data = f"hitl:confirm:{conf.id}"
    cb.from_user = MagicMock()
    cb.from_user.id = intruder_id
    cb.answer = AsyncMock()
    cb.message = MagicMock(spec=Message)
    cb.message.edit_text = AsyncMock()

    await handler.cb_hitl_confirm(cb)

    # Доступ отклонен
    cb.answer.assert_called_once_with("⛔ Доступ запрещен", show_alert=True)
    cb.message.edit_text.assert_not_called()

    # Задача осталась в БД
    async with test_db.connection() as conn:
        cur = await conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,))
        assert await cur.fetchone() is not None

    # Статус подтверждения остался pending
    check_conf = await store.get_confirmation(conf.id)
    assert check_conf.status == ConfirmationStatus.PENDING


@pytest.mark.asyncio
async def test_cb_hitl_reject(test_db: Database):
    """Проверяет отклонение удаления в Telegram (D-01)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    async with test_db.connection() as conn:
        cursor = await conn.execute(
            """
            INSERT INTO projects (name, area, status, created_at, updated_at)
            VALUES ('Проект без удаления', 'ГУАП', 'active', ?, ?);
            """,
            (now_iso, now_iso),
        )
        await conn.commit()
        proj_id = cursor.lastrowid

    store = ConfirmationStore(test_db.db_path)
    conf = await store.create_confirmation(
        persona_id="popov-da-default",
        action_type="delete_project",
        target_id=str(proj_id),
        payload={"project_id": proj_id, "name": "Проект без удаления"},
    )

    user_id = 12345
    handler = EmailBotHandler(
        bot=MagicMock(),
        db=test_db,
        allowed_user_id=user_id,
    )

    cb = MagicMock(spec=CallbackQuery)
    cb.data = f"hitl:reject:{conf.id}"
    cb.from_user = MagicMock()
    cb.from_user.id = user_id
    cb.answer = AsyncMock()
    cb.message = MagicMock(spec=Message)
    cb.message.edit_text = AsyncMock()

    await handler.cb_hitl_reject(cb)

    cb.answer.assert_called_once_with("Отклонено")
    assert "Удаление отклонено" in cb.message.edit_text.call_args[0][0]

    # Проект сохранен
    async with test_db.connection() as conn:
        cur = await conn.execute("SELECT id FROM projects WHERE id = ?", (proj_id,))
        assert await cur.fetchone() is not None

    # Статус стал rejected
    updated = await store.get_confirmation(conf.id)
    assert updated.status == ConfirmationStatus.REJECTED


@pytest.mark.asyncio
async def test_cb_hitl_confirm_expired(test_db: Database):
    """Проверяет блокировку подтверждения устаревшего запроса (D-03)."""
    store = ConfirmationStore(test_db.db_path)
    conf = await store.create_confirmation(
        persona_id="popov-da-default",
        action_type="delete_task",
        target_id="1",
        payload={"task_id": 1, "title": "Устаревшая задача"},
    )

    # Искусственно сдвигаем expires_at в прошлое
    expired_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    with sqlite3.connect(test_db.db_path) as conn:
        conn.execute("UPDATE pending_confirmations SET expires_at = ? WHERE id = ?", (expired_time, conf.id))

    user_id = 12345
    handler = EmailBotHandler(
        bot=MagicMock(),
        db=test_db,
        allowed_user_id=user_id,
    )

    cb = MagicMock(spec=CallbackQuery)
    cb.data = f"hitl:confirm:{conf.id}"
    cb.from_user = MagicMock()
    cb.from_user.id = user_id
    cb.answer = AsyncMock()
    cb.message = MagicMock(spec=Message)
    cb.message.edit_text = AsyncMock()

    await handler.cb_hitl_confirm(cb)

    cb.answer.assert_called_once_with("Срок действия запроса истек", show_alert=True)
    assert "Срок действия запроса истек" in cb.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_dlg_clear_registers_in_confirmation_store(test_db: Database):
    """Проверяет фиксацию dlg:confirm_clear в ConfirmationStore при сохранении 1:1 UX (D-06)."""
    user_id = 12345
    await test_db.save_dialog_message(user_id=user_id, role="user", content="Привет")

    handler = EmailBotHandler(
        bot=MagicMock(),
        db=test_db,
        allowed_user_id=user_id,
    )

    cb = MagicMock(spec=CallbackQuery)
    cb.from_user = MagicMock()
    cb.from_user.id = user_id
    cb.answer = AsyncMock()
    cb.message = MagicMock(spec=Message)
    cb.message.edit_text = AsyncMock()

    await handler.cb_dlg_confirm_clear(cb)

    # UX диалога сохранен 1:1
    cb.answer.assert_called_once_with("Память очищена")
    assert "Память диалога успешно очищена" in cb.message.edit_text.call_args[0][0]
    assert await test_db.get_active_dialog_count(user_id) == 0

    # Проверяем, что в ConfirmationStore появилась запись со статусом confirmed
    store = ConfirmationStore(test_db.db_path)
    with sqlite3.connect(test_db.db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT action_type, target_id, status, channel FROM pending_confirmations WHERE action_type = 'clear_dialog'"
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "clear_dialog"
        assert row[1] == str(user_id)
        assert row[2] == "confirmed"
        assert row[3] == "telegram"
