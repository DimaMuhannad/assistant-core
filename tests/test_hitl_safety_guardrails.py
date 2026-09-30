import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import InlineKeyboardMarkup

from src.storage.db import Database
from src.notifier.bot_handler import EmailBotHandler


@pytest.mark.asyncio
async def test_dialog_history_hitl_and_undo(tmp_path):
    db_file = tmp_path / "test_hitl.db"
    db = Database(f"sqlite+aiosqlite:///{db_file}")
    await db.init_db()

    user_id = 999111

    # Insert 5 dialog turns
    for i in range(5):
        await db.save_dialog_message(user_id=user_id, role="user", content=f"User question {i}")
        await db.save_dialog_message(user_id=user_id, role="model", content=f"Answer {i}")

    # 1. Check active dialog count
    active_count = await db.get_active_dialog_count(user_id)
    assert active_count == 10

    # 2. Clear dialog history (Soft-delete / archive)
    archived_count = await db.clear_dialog_history(user_id)
    assert archived_count == 10

    # 3. Check active count is now 0
    assert await db.get_active_dialog_count(user_id) == 0

    # 4. Restore dialog history (Undo)
    restored_count = await db.restore_dialog_history(user_id)
    assert restored_count == 10

    # 5. Check active count is back to 10
    assert await db.get_active_dialog_count(user_id) == 10


@pytest.mark.asyncio
async def test_bot_handler_clear_dialog_hitl_card(tmp_path):
    db_file = tmp_path / "test_hitl_bot.db"
    db = Database(f"sqlite+aiosqlite:///{db_file}")
    await db.init_db()

    user_id = 12345
    # Insert 2 turns
    await db.save_dialog_message(user_id=user_id, role="user", content="Hello")
    await db.save_dialog_message(user_id=user_id, role="model", content="Hi")

    handler = EmailBotHandler(
        bot=MagicMock(),
        db=db,
        allowed_user_id=user_id,
    )

    # Mock Message
    msg = MagicMock()
    msg.from_user.id = user_id
    msg.chat.id = user_id
    msg.answer = AsyncMock()

    # User calls /clear
    await handler.handle_cmd_clear_dialog(msg)

    # Database should NOT be cleared yet! HITL confirmation card must be shown.
    active_count = await db.get_active_dialog_count(user_id)
    assert active_count == 2

    # Verify confirmation card was sent with inline buttons
    msg.answer.assert_called_once()
    args, kwargs = msg.answer.call_args
    assert "⚠️ **Подтверждение деструктивного действия" in args[0]
    reply_markup = kwargs.get("reply_markup")
    assert isinstance(reply_markup, InlineKeyboardMarkup)
    callbacks = [btn.callback_data for row in reply_markup.inline_keyboard for btn in row]
    assert "dlg:confirm_clear" in callbacks
    assert "dlg:cancel_clear" in callbacks


@pytest.mark.asyncio
async def test_bot_handler_confirm_cancel_undo_callbacks(tmp_path):
    db_file = tmp_path / "test_hitl_cb.db"
    db = Database(f"sqlite+aiosqlite:///{db_file}")
    await db.init_db()

    user_id = 12345
    await db.save_dialog_message(user_id=user_id, role="user", content="Turn 1")

    handler = EmailBotHandler(
        bot=MagicMock(),
        db=db,
        allowed_user_id=user_id,
    )

    # 1. Test Cancel Callback
    cb_cancel = MagicMock()
    cb_cancel.from_user.id = user_id
    cb_cancel.message.edit_text = AsyncMock()
    cb_cancel.answer = AsyncMock()

    await handler.cb_dlg_cancel_clear(cb_cancel)
    cb_cancel.message.edit_text.assert_called_once()
    assert "Очистка памяти отменена" in cb_cancel.message.edit_text.call_args[0][0]
    assert await db.get_active_dialog_count(user_id) == 1

    # 2. Test Confirm Callback
    cb_confirm = MagicMock()
    cb_confirm.from_user.id = user_id
    cb_confirm.message.edit_text = AsyncMock()
    cb_confirm.answer = AsyncMock()

    await handler.cb_dlg_confirm_clear(cb_confirm)
    cb_confirm.message.edit_text.assert_called_once()
    assert "Память диалога успешно очищена" in cb_confirm.message.edit_text.call_args[0][0]
    assert await db.get_active_dialog_count(user_id) == 0

    # Verify undo button is present
    reply_markup = cb_confirm.message.edit_text.call_args[1].get("reply_markup")
    assert reply_markup is not None
    callbacks = [btn.callback_data for row in reply_markup.inline_keyboard for btn in row]
    assert "dlg:undo_clear" in callbacks

    # 3. Test Undo Callback
    cb_undo = MagicMock()
    cb_undo.from_user.id = user_id
    cb_undo.message.edit_text = AsyncMock()
    cb_undo.answer = AsyncMock()

    await handler.cb_dlg_undo_clear(cb_undo)
    cb_undo.message.edit_text.assert_called_once()
    assert "Контекст диалога успешно восстановлен" in cb_undo.message.edit_text.call_args[0][0]
    assert await db.get_active_dialog_count(user_id) == 1
