"""Unit tests for SecretaryDialogEngine and Conversational Telegram Assistant."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from src.storage.db import Database
from src.brain.secretary_dialog import SecretaryDialogEngine
from src.notifier.bot_handler import EmailBotHandler


@pytest.mark.asyncio
async def test_dialog_history_persistence():
    db = Database(db_path=":memory:")
    await db.init_db()

    user_id = 12345
    # Initially history is empty
    hist = await db.get_recent_dialog_history(user_id)
    assert len(hist) == 0

    # Save turn
    await db.save_dialog_message(user_id=user_id, role="user", content="Привет, секретарь!")
    await db.save_dialog_message(user_id=user_id, role="model", content="Здравствуйте, Дмитрий Александрович!")

    hist = await db.get_recent_dialog_history(user_id)
    assert len(hist) == 2
    assert hist[0]["role"] == "user"
    assert hist[0]["content"] == "Привет, секретарь!"
    assert hist[1]["role"] == "model"
    assert hist[1]["content"] == "Здравствуйте, Дмитрий Александрович!"

    # Clear history
    await db.clear_dialog_history(user_id)
    hist_cleared = await db.get_recent_dialog_history(user_id)
    assert len(hist_cleared) == 0

    await db.close()


@pytest.mark.asyncio
async def test_secretary_dialog_clear_command():
    db = Database(db_path=":memory:")
    await db.init_db()

    engine = SecretaryDialogEngine(db=db, api_key="")
    user_id = 999
    await db.save_dialog_message(user_id=user_id, role="user", content="Вопрос")
    
    # Process /clear
    res = await engine.answer_user_message(user_id=user_id, message_text="/clear")
    assert "очищен" in res.lower()

    hist = await db.get_recent_dialog_history(user_id)
    assert len(hist) == 0

    await db.close()


@pytest.mark.asyncio
async def test_secretary_dialog_grounding_and_fallback():
    db = Database(db_path=":memory:")
    await db.init_db()

    engine = SecretaryDialogEngine(db=db, api_key="")
    user_id = 1001

    # When API key is empty, it returns deterministic fallback containing grounding summary
    ans = await engine.answer_user_message(user_id=user_id, message_text="Что у меня по расписанию?")
    assert "Краткая оперативная сводка" in ans or "расписание" in ans.lower()

    # Interaction must be logged to history
    hist = await db.get_recent_dialog_history(user_id)
    assert len(hist) == 2
    assert hist[0]["content"] == "Что у меня по расписанию?"

    await db.close()


@pytest.mark.asyncio
async def test_bot_handler_free_form_text_delegation():
    db = Database(db_path=":memory:")
    await db.init_db()

    mock_notifier = AsyncMock()
    mock_notifier.send_message = AsyncMock(return_value=[1])

    handler = EmailBotHandler(
        db=db,
        notifier=mock_notifier,
        allowed_user_id=123,
    )

    mock_msg = MagicMock()
    mock_msg.from_user.id = 123
    mock_msg.chat.id = 123
    mock_msg.text = "Привет! Напомни, сколько пар у меня завтра?"

    with patch.object(handler, "_handle_secretary_dialog", new_callable=AsyncMock) as mock_dialog:
        await handler.handle_user_text(mock_msg)
        mock_dialog.assert_called_once_with(mock_msg, "Привет! Напомни, сколько пар у меня завтра?")

    await db.close()
