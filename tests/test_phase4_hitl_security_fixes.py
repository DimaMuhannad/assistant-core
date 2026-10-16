"""Дефекты безопасности и HITL фазы 4 (ревизия 04-REVISION, раздел 4): регрессии на каждый пункт."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from assistant_shared.hitl import ConfirmationStatus, ConfirmationStore
from src.brain.git_evaluator import GitProgressEvaluator
from src.core.domain.entities import Persona, Workspace, WorkspaceClearance
from src.notifier.bot_handler import EmailBotHandler
from src.storage.db import Database

USER_ID = 100000001
NOTION_PROJECT = "11111111111111111111111111111111"
NOTION_DB = "22222222222222222222222222222222"


@pytest.fixture
async def fx(tmp_path: Path):
    db_file = tmp_path / "phase4_sec.db"
    db = Database(f"sqlite+aiosqlite:///{db_file}")
    await db.init_db()
    ws = Workspace(
        id="ws_sec",
        name="Sec Project",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(tmp_path / "repo"),
        remote="git@github.com:example/repo.git",
        notion_project=NOTION_PROJECT,
    )
    persona = Persona(id="p_owner", name="Owner", workspaces=(ws,))
    store = ConfirmationStore(str(db_file))
    notion = AsyncMock()
    notion.is_configured = True
    notion.find_project_activity = AsyncMock(return_value=None)
    notion.log_project_activity = AsyncMock(return_value={"id": "page-1"})
    evaluator = GitProgressEvaluator(
        git_provider=AsyncMock(),
        notion_client=notion,
        confirmation_store=store,
        persona=persona,
        default_activity_db_id=NOTION_DB,
    )
    handler = EmailBotHandler(
        bot=AsyncMock(), db=db, allowed_user_id=USER_ID, git_evaluator=evaluator, notifier=AsyncMock()
    )
    return SimpleNamespace(db=db, store=store, notion=notion, handler=handler)


async def _pending(f):
    return await f.store.create_confirmation(
        persona_id="p_owner",
        action_type="notion_project_sync",
        payload={
            "workspace_id": "ws_sec",
            "notion_project_id": NOTION_PROJECT,
            "database_id": NOTION_DB,
            "date_iso": "2026-10-12",
        },
    )


def _cb(conf_id: str, kind: str, user_id: int = USER_ID):
    cb = AsyncMock()
    cb.from_user.id = user_id
    cb.data = f"ntn:{kind}:{conf_id}"
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


async def test_ntn_confirm_ui_failure_does_not_reopen_done_write(fx):
    """Сбой edit_text после записи в Notion не откатывает карточку в pending (повтор дал бы дубль)."""
    conf = await _pending(fx)
    cb = _cb(conf.id, "conf")
    cb.message.edit_text.side_effect = RuntimeError("telegram недоступен")

    await fx.handler.cb_ntn_confirm(cb)

    assert (await fx.store.get_confirmation(conf.id)).status == ConfirmationStatus.CONFIRMED
    assert fx.notion.log_project_activity.await_count == 1


def test_is_authorized_fails_closed_without_owner(fx_none=None):
    """Без настроенного владельца доступ закрыт всем (fail-closed)."""
    handler = EmailBotHandler(bot=MagicMock(), db=MagicMock(), allowed_user_id=None)
    assert handler._is_authorized(USER_ID) is False
    assert handler._is_authorized(0) is False


async def test_ntn_confirm_denied_without_owner(fx):
    """Колбэк подтверждения Notion без владельца отвечает отказом и ничего не пишет."""
    conf = await _pending(fx)
    handler = EmailBotHandler(bot=MagicMock(), db=fx.db, allowed_user_id=None, git_evaluator=fx.handler.git_evaluator)
    cb = _cb(conf.id, "conf", user_id=42)

    await handler.cb_ntn_confirm(cb)

    cb.answer.assert_awaited_once_with("⛔ Доступ запрещен", show_alert=True)
    fx.notion.log_project_activity.assert_not_awaited()
    assert (await fx.store.get_confirmation(conf.id)).status == ConfirmationStatus.PENDING


async def test_ntn_reject_after_confirm_says_already_confirmed(fx):
    """Отклонение уже подтверждённой карточки: «Уже подтверждено», статус и данные не меняются."""
    conf = await _pending(fx)
    await fx.handler.cb_ntn_confirm(_cb(conf.id, "conf"))
    assert (await fx.store.get_confirmation(conf.id)).status == ConfirmationStatus.CONFIRMED

    rej = _cb(conf.id, "rej")
    await fx.handler.cb_ntn_reject(rej)

    rej.answer.assert_awaited_once_with("Уже подтверждено", show_alert=True)
    rej.message.edit_text.assert_not_called()
    assert (await fx.store.get_confirmation(conf.id)).status == ConfirmationStatus.CONFIRMED


async def test_ntn_reject_pending_still_rejects(fx):
    """Отклонение карточки в pending работает как раньше."""
    conf = await _pending(fx)
    rej = _cb(conf.id, "rej")

    await fx.handler.cb_ntn_reject(rej)

    rej.answer.assert_awaited_once_with("Отклонено")
    assert (await fx.store.get_confirmation(conf.id)).status == ConfirmationStatus.REJECTED


async def test_ntn_confirm_notion_failure_returns_card_to_pending(fx):
    """Сбой Notion при подтверждении: карточка снова pending, владелец может повторить (reopen_action)."""
    fx.notion.log_project_activity.side_effect = RuntimeError("Notion API 500")
    conf = await _pending(fx)
    cb = _cb(conf.id, "conf")

    await fx.handler.cb_ntn_confirm(cb)

    cb.answer.assert_awaited_once_with("Не записано в Notion, повторите", show_alert=True)
    assert (await fx.store.get_confirmation(conf.id)).status == ConfirmationStatus.PENDING

    fx.notion.log_project_activity.side_effect = None
    retry = _cb(conf.id, "conf")
    await fx.handler.cb_ntn_confirm(retry)
    assert (await fx.store.get_confirmation(conf.id)).status == ConfirmationStatus.CONFIRMED


async def test_no_notion_calls_between_card_and_confirm(fx):
    """Пока владелец не нажал «подтвердить», в Notion нет ни чтения, ни записи."""
    conf = await _pending(fx)

    fx.notion.find_project_activity.assert_not_called()
    fx.notion.log_project_activity.assert_not_called()

    await fx.handler.cb_ntn_confirm(_cb(conf.id, "conf"))

    fx.notion.log_project_activity.assert_awaited_once()


async def test_ntn_confirm_after_reject_writes_nothing(fx):
    """Подтверждение отклонённой карточки ничего не пишет в Notion, статус остаётся rejected."""
    conf = await _pending(fx)
    await fx.handler.cb_ntn_reject(_cb(conf.id, "rej"))

    cb = _cb(conf.id, "conf")
    await fx.handler.cb_ntn_confirm(cb)

    cb.answer.assert_awaited_once()
    assert "уже обработан" in cb.answer.call_args[0][0].lower()
    fx.notion.log_project_activity.assert_not_called()
    assert (await fx.store.get_confirmation(conf.id)).status == ConfirmationStatus.REJECTED
