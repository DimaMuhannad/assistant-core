"""Unit tests for SecretaryDialogEngine and Conversational Telegram Assistant."""

from pathlib import Path

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from src.storage.db import Database
from src.brain.secretary_dialog import SecretaryDialogEngine
from src.notifier.bot_handler import EmailBotHandler
from src.persona.bindings import methodist_settings


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
    
    # SAFE-01: движок память не очищает, только предупреждает про ручной /clear с карточкой
    res = await engine.answer_user_message(user_id=user_id, message_text="/clear")
    assert "/clear" in res

    hist = await db.get_recent_dialog_history(user_id)
    assert len(hist) == 1

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


@pytest.mark.asyncio
async def test_db_search_emails_stemming():
    db = Database(db_path=":memory:")
    await db.init_db()

    now = datetime.now(timezone.utc)
    await db.upsert_email_message(
        message_id="msg-nov-1@yandex.ru",
        account_id="mailru",
        folder="INBOX",
        sender_name="Новикова Юлиана",
        sender_email="Nov-Jliana@yandex.ru",
        recipients_json='["scipopov@mail.ru"]',
        subject="Эффективные контракты",
        date_sent=now,
        body_plain="Уважаемые коллеги! Отправляю форму отчета по эффективному контракту.",
        body_html=None,
        snippet="Отправляю форму отчета",
        has_attachments=False,
        attachments_json="[]",
        in_reply_to=None,
        references_text=None,
        thread_id="th-1",
        category="guap_dept",
        requires_action=False,
    )

    # Search with inflected Russian words
    res = await db.search_emails("эффективный контракт Новиковой")
    assert len(res) == 1
    assert res[0]["subject"] == "Эффективные контракты"
    assert res[0]["sender_name"] == "Новикова Юлиана"

    await db.close()


def test_search_local_files_catalog():
    db = Database(db_path=":memory:")
    engine = SecretaryDialogEngine(db=db, api_key="")
    ctx, files = engine._search_local_files_context("скинь шаблон эффективного контракта")
    # BCK-02, D-17: ожидаемое имя бланка берётся из каталога персоны по умолчанию
    entry = next(e for e in methodist_settings().file_catalog if "контракт" in e.keywords)
    expected_name = Path(entry.relpath).stem
    assert len(files) >= 1
    assert any(expected_name in f["name"] for f in files)
    assert "ДОСТУПНЫЕ ЛОКАЛЬНЫЕ ФАЙЛЫ" in ctx

