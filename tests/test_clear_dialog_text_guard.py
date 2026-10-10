"""SAFE-01 (D-01..D-04): очистка памяти диалога только через /clear с HITL-карточкой.

Текст, голос и движок диалога не очищают память и не показывают карточку:
бот отвечает предупреждением с командой /clear.
"""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import InlineKeyboardMarkup

from src.brain.dialog_safety import (
    CLEAR_DIALOG_TEXT_WARNING,
    CLEAR_DIALOG_TRIGGERS,
    is_clear_dialog_request,
)
from src.brain.intent_router import FastIntentRouter, IntentResult
from src.brain.secretary_dialog import SecretaryDialogEngine
from src.notifier.bot_handler import EmailBotHandler
from src.storage.db import Database

SECRETARY_DIALOG_PATH = Path(__file__).resolve().parent.parent / "src" / "brain" / "secretary_dialog.py"

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
@pytest.mark.parametrize("phrase", ["очисти диалог", "забудь контекст", "сброс", "Очисти диалог!"])
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


def _llm_route_to_clear(handler: EmailBotHandler) -> None:
    """Подменить маршрутизатор: LLM-распознавание свободной фразы даёт clear_dialog."""
    handler.intent_router.route = AsyncMock(
        return_value=IntentResult(
            action="clear_dialog", confidence=0.9, reason="LLM", model="test", latency_ms=1.0
        )
    )


@pytest.mark.asyncio
async def test_llm_clear_dialog_route_warns_and_keeps_history(tmp_path):
    db = await _make_db(tmp_path)
    handler = _make_handler(db)
    _llm_route_to_clear(handler)

    msg = _make_message("давай начнём всё с чистого листа")
    await handler.handle_user_text(msg)

    assert await db.get_active_dialog_count(USER_ID) == 4
    _assert_warning_without_card(msg)


@pytest.mark.asyncio
async def test_unauthorized_user_gets_no_reply(tmp_path):
    db = await _make_db(tmp_path)
    handler = _make_handler(db, allowed_user_id=USER_ID)

    msg = _make_message("очисти диалог", user_id=USER_ID + 1)
    await handler.handle_user_text(msg)
    await handler._warn_clear_requires_slash(msg)

    msg.answer.assert_not_called()
    assert await db.get_active_dialog_count(USER_ID) == 4


@pytest.mark.asyncio
async def test_voice_clear_phrase_warns_and_keeps_history(tmp_path):
    db = await _make_db(tmp_path)
    handler = _make_handler(db)
    handler.bot.get_file = AsyncMock(return_value=SimpleNamespace(file_path="voice/x.ogg"))
    handler.bot.download_file = AsyncMock()
    handler.voice_processor.transcribe = AsyncMock(
        return_value=SimpleNamespace(success=True, transcription="сброс")
    )

    msg = _make_message(None)
    msg.voice.file_id = "file-id"
    msg.voice.duration = 2
    await handler.handle_user_voice(msg)

    assert await db.get_active_dialog_count(USER_ID) == 4
    cards = [
        call
        for call in msg.answer.call_args_list
        if isinstance(call.kwargs.get("reply_markup"), InlineKeyboardMarkup)
    ]
    assert cards == []
    last_args, _ = msg.answer.call_args
    assert last_args[0] == CLEAR_DIALOG_TEXT_WARNING


@pytest.mark.asyncio
@pytest.mark.parametrize("phrase", CLEAR_DIALOG_TRIGGERS)
@pytest.mark.parametrize(
    ("return_files", "return_proposal"),
    [(False, False), (True, False), (False, True), (True, True)],
)
async def test_engine_never_clears_history(phrase, return_files, return_proposal):
    db = Database(db_path=":memory:")
    await db.init_db()
    engine = SecretaryDialogEngine(db=db, api_key="")
    await db.save_dialog_message(user_id=USER_ID, role="user", content="Вопрос")
    before = await db.get_recent_dialog_history(USER_ID)

    res = await engine.answer_user_message(
        user_id=USER_ID,
        message_text=phrase,
        return_files=return_files,
        return_proposal=return_proposal,
    )

    text = res[0] if isinstance(res, tuple) else res
    assert text == CLEAR_DIALOG_TEXT_WARNING
    if return_proposal:
        assert isinstance(res, tuple) and res[-1] is None
    if return_files and isinstance(res, tuple):
        assert res[1] == []
    assert await db.get_recent_dialog_history(USER_ID) == before
    assert await db.get_active_dialog_count(USER_ID) == 1
    await db.close()


@pytest.mark.asyncio
async def test_router_recognises_clear_phrase_with_punctuation_and_case(tmp_path):
    db = await _make_db(tmp_path)
    router = FastIntentRouter(db=db, api_key="")

    res = await router.route(user_id=USER_ID, message_text="Очисти диалог!")

    assert res.action == "clear_dialog"
    assert res.model == "fast-rule"


@pytest.mark.asyncio
async def test_slash_form_in_text_handler_keeps_hitl_card(tmp_path):
    db = await _make_db(tmp_path)
    handler = _make_handler(db)
    _llm_route_to_clear(handler)

    msg = _make_message("/clear@secretary_bot")
    await handler.handle_user_text(msg)

    assert await db.get_active_dialog_count(USER_ID) == 4
    msg.answer.assert_called_once()
    _, kwargs = msg.answer.call_args
    markup = kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)
    callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "dlg:confirm_clear" in callbacks
    assert "dlg:cancel_clear" in callbacks


@pytest.mark.asyncio
async def test_slash_form_with_empty_history_says_context_is_empty(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}")
    await db.init_db()
    handler = _make_handler(db)
    _llm_route_to_clear(handler)

    msg = _make_message("/clear@secretary_bot")
    await handler.handle_user_text(msg)

    msg.answer.assert_called_once()
    args, kwargs = msg.answer.call_args
    assert "уже пуст" in args[0]
    assert kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_slash_command_card_shows_without_confirmation_history_stays(tmp_path):
    db = await _make_db(tmp_path)
    handler = _make_handler(db)

    msg = _make_message("/clear")
    await handler.handle_cmd_clear_dialog(msg)

    assert await db.get_active_dialog_count(USER_ID) == 4
    _, kwargs = msg.answer.call_args
    assert isinstance(kwargs.get("reply_markup"), InlineKeyboardMarkup)


def test_secretary_dialog_has_no_clear_dialog_history_call():
    tree = ast.parse(SECRETARY_DIALOG_PATH.read_text(encoding="utf-8"))
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "clear_dialog_history"
    ]
    assert offenders == [], f"clear_dialog_history вызван в secretary_dialog.py: строки {offenders}"


@pytest.mark.asyncio
async def test_clear_and_text_voice_handlers_are_registered(tmp_path):
    db = await _make_db(tmp_path)
    handler = _make_handler(db)

    callbacks = [h.callback for h in handler.router.message.handlers]

    assert handler.handle_cmd_clear_dialog in callbacks
    assert handler.handle_user_text in callbacks
    assert handler.handle_user_voice in callbacks
