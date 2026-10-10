"""SAFE-01 (D-01..D-04): очистка памяти диалога только через /clear с HITL-карточкой.

Текст, голос и движок диалога не очищают память и не показывают карточку:
бот отвечает предупреждением с командой /clear.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import InlineKeyboardMarkup

from src.brain.dialog_safety import (
    CLEAR_DIALOG_TEXT_WARNING,
    CLEAR_DIALOG_TRIGGERS,
    is_clear_dialog_request,
)
from src.notifier.bot_handler import EmailBotHandler
from src.storage.db import Database

USER_ID = 424242


async def _make_db(tmp_path, name: str = "guard.db") -> Database:
    db = Database(f"sqlite+aiosqlite:///{tmp_path / name}")
    await db.init_db()
    for i in range(2):
        await db.save_dialog_message(user_id=USER_ID, role="user", content=f"Вопрос {i}")
        await db.save_dialog_message(user_id=USER_ID, role="model", content=f"Ответ {i}")
    return db


def _make_handler(db: Database, allowed_user_id: int = USER_ID) -> EmailBotHandler:
    return EmailBotHandler(bot=MagicMock(), db=db, allowed_user_id=allowed_user_id)


def _make_message(text: str | None, user_id: int = USER_ID) -> MagicMock:
    msg = MagicMock()
    msg.from_user.id = user_id
    msg.chat.id = user_id
    msg.chat.type = "private"
    msg.text = text
    msg.answer = AsyncMock()
    return msg


def _assert_warning_without_card(msg: MagicMock) -> None:
    msg.answer.assert_called_once()
    args, kwargs = msg.answer.call_args
    assert "/clear" in args[0]
    assert not isinstance(kwargs.get("reply_markup"), InlineKeyboardMarkup)


@pytest.mark.asyncio
@pytest.mark.parametrize("phrase", ["очисти диалог", "забудь контекст", "сброс"])
async def test_text_clear_phrase_warns_and_keeps_history(tmp_path, phrase):
    db = await _make_db(tmp_path)
    handler = _make_handler(db)
    assert await db.get_active_dialog_count(USER_ID) == 4

    msg = _make_message(phrase)
    await handler.handle_user_text(msg)

    assert await db.get_active_dialog_count(USER_ID) == 4
    _assert_warning_without_card(msg)
    assert msg.answer.call_args.args[0] == CLEAR_DIALOG_TEXT_WARNING


def test_warning_text_mentions_manual_slash_command():
    assert "/clear" in CLEAR_DIALOG_TEXT_WARNING
    assert "вручную" in CLEAR_DIALOG_TEXT_WARNING


@pytest.mark.parametrize("phrase", CLEAR_DIALOG_TRIGGERS)
def test_is_clear_dialog_request_recognises_every_trigger(phrase):
    assert is_clear_dialog_request(phrase)
    assert is_clear_dialog_request(phrase.upper())
    assert is_clear_dialog_request(f"  {phrase}!  ")


@pytest.mark.parametrize("phrase", ["", "   ", None, "привет", "очисти диалог с Иваном", "сбросить"])
def test_is_clear_dialog_request_rejects_other_text(phrase):
    assert not is_clear_dialog_request(phrase)
