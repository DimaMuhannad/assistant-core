"""Тесты обработчиков бота для команды git, HITL-колбэков и диспетчеризации (GIT-03, NTN-02).

Проверяет:
1. Сбой Notion при подтверждении вызывает reopen_action и оставляет кнопки (D-09).
2. Повторное подтверждение после сбоя успешно записывает в Notion ровно один раз.
3. LookupError при подтверждении также откатывает действие через reopen_action.
4. Повторное нажатие по уже обработанному запросу выводит предупреждение.
5. Запрос карточки cb_ntn_request при существующей карточке учитывает её статус (D-08).
6. Диспетчеризация текста «гит» / «коммиты» направляется в handle_cmd_git.
7. Регистрация команды Command("git") строго предшествует общему обработчику F.text.
8. Голосовое сообщение с действием git направляется в handle_cmd_git.
9. Справка /help упоминает команду /git.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from assistant_shared.hitl import ConfirmationStatus, ConfirmationStore
from src.brain.git_evaluator import (
    CardProposal,
    GitProgressEvaluator,
    NotionSyncError,
)
from src.core.domain.entities import Persona, Workspace, WorkspaceClearance
from src.notifier.bot_handler import EmailBotHandler
from src.storage.db import Database

USER_ID = 100000001


@pytest.fixture
async def bot_fixture(tmp_path: Path):
    db_file = tmp_path / "test_git_bot.db"
    db = Database(f"sqlite+aiosqlite:///{db_file}")
    await db.init_db()

    ws_public = Workspace(
        id="ws_git_bot",
        name="Bot Git Project",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(tmp_path / "repo"),
        remote="git@github.com:example/repo.git",
        notion_project="11111111111111111111111111111111",
    )
    persona = Persona(id="p_owner", name="Owner", workspaces=(ws_public,))

    store = ConfirmationStore(str(db_file))
    mock_git = AsyncMock()
    mock_notion = AsyncMock()
    mock_notion.is_configured = True
    mock_notion.find_project_activity = AsyncMock(return_value=None)
    mock_notion.log_project_activity = AsyncMock(return_value={"id": "page-notion-ok-123"})

    evaluator = GitProgressEvaluator(
        git_provider=mock_git,
        notion_client=mock_notion,
        confirmation_store=store,
        persona=persona,
        default_activity_db_id="22222222222222222222222222222222",
    )

    mock_notifier = AsyncMock()

    handler = EmailBotHandler(
        bot=AsyncMock(),
        db=db,
        allowed_user_id=USER_ID,
        git_evaluator=evaluator,
        notifier=mock_notifier,
    )

    return SimpleNamespace(
        db=db,
        store=store,
        evaluator=evaluator,
        mock_notion=mock_notion,
        handler=handler,
        ws_public=ws_public,
        notifier=mock_notifier,
    )


@pytest.mark.asyncio
async def test_ntn_confirm_failure_reopens_card_and_retry_succeeds(bot_fixture):
    """Сбой Notion при подтверждении откатывает статус в pending, повторное нажатие успешно (D-09)."""
    f = bot_fixture

    # Создаем подтверждение в состоянии PENDING
    conf = await f.store.create_confirmation(
        persona_id="p_owner",
        action_type="notion_project_sync",
        payload={
            "workspace_id": f.ws_public.id,
            "notion_project_id": "11111111111111111111111111111111",
            "database_id": "22222222222222222222222222222222",
            "date_iso": "2026-10-12",
        },
    )

    # 1. Первая попытка: Notion падает с NotionSyncError
    f.mock_notion.log_project_activity.side_effect = NotionSyncError("HTTP 500 error")

    cb1 = AsyncMock()
    cb1.from_user.id = USER_ID
    cb1.data = f"ntn:conf:{conf.id}"
    cb1.message = MagicMock()
    cb1.message.edit_text = AsyncMock()
    cb1.answer = AsyncMock()

    await f.handler.cb_ntn_confirm(cb1)

    # Карточка не заблокирована в confirmed: статус возвращен в pending
    reopened = await f.store.get_confirmation(conf.id)
    assert reopened.status == ConfirmationStatus.PENDING
    cb1.answer.assert_called_once_with("Не записано в Notion, повторите", show_alert=True)
    cb1.message.edit_text.assert_not_called()  # Кнопки остаются

    # 2. Вторая попытка: Notion починился, вызов успешен
    f.mock_notion.log_project_activity.side_effect = None
    f.mock_notion.log_project_activity.return_value = {"id": "page-notion-retry-success"}

    cb2 = AsyncMock()
    cb2.from_user.id = USER_ID
    cb2.data = f"ntn:conf:{conf.id}"
    cb2.message = MagicMock()
    cb2.message.edit_text = AsyncMock()
    cb2.answer = AsyncMock()

    await f.handler.cb_ntn_confirm(cb2)

    confirmed = await f.store.get_confirmation(conf.id)
    assert confirmed.status == ConfirmationStatus.CONFIRMED
    cb2.answer.assert_called_once_with("Записано в Notion")
    assert cb2.message.edit_text.called
    assert "Записано в Notion" in cb2.message.edit_text.call_args[0][0]
    assert f.mock_notion.log_project_activity.call_count == 2


@pytest.mark.asyncio
async def test_ntn_confirm_lookup_error_reopens_card(bot_fixture):
    """LookupError при подтверждении откатывает статус карточки в pending."""
    f = bot_fixture

    conf = await f.store.create_confirmation(
        persona_id="p_owner",
        action_type="unknown_unregistered_action",
        payload={"workspace_id": f.ws_public.id},
    )

    cb = AsyncMock()
    cb.from_user.id = USER_ID
    cb.data = f"ntn:conf:{conf.id}"
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()

    await f.handler.cb_ntn_confirm(cb)

    reopened = await f.store.get_confirmation(conf.id)
    assert reopened.status == ConfirmationStatus.PENDING
    cb.answer.assert_called_once_with("Не записано в Notion, повторите", show_alert=True)


@pytest.mark.asyncio
async def test_ntn_confirm_double_press_is_already_processed(bot_fixture):
    """Повторное нажатие подтверждения на уже завершенную карточку выводит предупреждение."""
    f = bot_fixture

    conf = await f.store.create_confirmation(
        persona_id="p_owner",
        action_type="notion_project_sync",
        payload={
            "workspace_id": f.ws_public.id,
            "notion_project_id": "11111111111111111111111111111111",
            "database_id": "22222222222222222222222222222222",
        },
    )
    await f.store.confirm_action(conf.id, confirmed_by="user")

    cb = AsyncMock()
    cb.from_user.id = USER_ID
    cb.data = f"ntn:conf:{conf.id}"
    cb.answer = AsyncMock()

    await f.handler.cb_ntn_confirm(cb)
    cb.answer.assert_called_once()
    assert "уже обработан" in cb.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_ntn_request_existing_pending_shows_card(bot_fixture):
    """При наличии существующей pending карточки она показывается заново с кнопками (D-08)."""
    f = bot_fixture

    conf = await f.store.create_confirmation(
        persona_id="p_owner",
        action_type="notion_project_sync",
        payload={"workspace_id": f.ws_public.id},
    )
    # Имитируем, что propose_card возвращает предложение с created=False
    mock_prop = CardProposal(created=False, confirmation=conf)
    f.evaluator.propose_card = AsyncMock(return_value=mock_prop)
    f.evaluator.format_card_text = MagicMock(return_value="Карточка проекта")

    # Регистрируем запуск в памяти хэндлера
    token = "test_run_token"
    run_entry = SimpleNamespace(notion_ready=True)
    f.handler._git_runs[token] = SimpleNamespace(date_iso="2026-10-12", entries=[run_entry])

    cb = AsyncMock()
    cb.from_user.id = USER_ID
    cb.data = f"ntn:req:{token}:0"
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()

    await f.handler.cb_ntn_request(cb)

    cb.message.answer.assert_called_once()
    assert cb.message.answer.call_args[0][0] == "Карточка проекта"
    assert cb.message.answer.call_args[1]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_ntn_request_already_confirmed_alerts(bot_fixture):
    """При наличии уже подтвержденной карточки повторный запрос выдает алерт 'Уже внесено в Notion' (D-08)."""
    f = bot_fixture

    conf = await f.store.create_confirmation(
        persona_id="p_owner",
        action_type="notion_project_sync",
        payload={"workspace_id": f.ws_public.id},
    )
    await f.store.confirm_action(conf.id, confirmed_by="user")
    confirmed_conf = await f.store.get_confirmation(conf.id)

    mock_prop = CardProposal(created=False, confirmation=confirmed_conf)
    f.evaluator.propose_card = AsyncMock(return_value=mock_prop)

    token = "test_run_token"
    run_entry = SimpleNamespace(notion_ready=True)
    f.handler._git_runs[token] = SimpleNamespace(date_iso="2026-10-12", entries=[run_entry])

    cb = AsyncMock()
    cb.from_user.id = USER_ID
    cb.data = f"ntn:req:{token}:0"
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()

    await f.handler.cb_ntn_request(cb)

    cb.answer.assert_called_once_with("Уже внесено в Notion", show_alert=True)
    cb.message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_ntn_request_already_rejected_alerts(bot_fixture):
    """При наличии отклоненной карточки повторный запрос выдает алерт 'Карточка за этот период отклонена' (D-08)."""
    f = bot_fixture

    conf = await f.store.create_confirmation(
        persona_id="p_owner",
        action_type="notion_project_sync",
        payload={"workspace_id": f.ws_public.id},
    )
    await f.store.reject_action(conf.id, rejected_by="user")
    rejected_conf = await f.store.get_confirmation(conf.id)

    mock_prop = CardProposal(created=False, confirmation=rejected_conf)
    f.evaluator.propose_card = AsyncMock(return_value=mock_prop)

    token = "test_run_token"
    run_entry = SimpleNamespace(notion_ready=True)
    f.handler._git_runs[token] = SimpleNamespace(date_iso="2026-10-12", entries=[run_entry])

    cb = AsyncMock()
    cb.from_user.id = USER_ID
    cb.data = f"ntn:req:{token}:0"
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()

    await f.handler.cb_ntn_request(cb)

    cb.answer.assert_called_once_with("Карточка за этот период отклонена", show_alert=True)
    cb.message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_text_alias_dispatches_to_git_command(bot_fixture):
    """Пользовательский текст «гит» маршрутизируется в handle_cmd_git."""
    f = bot_fixture
    f.handler.handle_cmd_git = AsyncMock()

    msg = MagicMock()
    msg.from_user.id = USER_ID
    msg.chat.id = USER_ID
    msg.chat.type = "private"
    msg.text = "гит"

    await f.handler.handle_user_text(msg)
    f.handler.handle_cmd_git.assert_called_once_with(msg)


def test_git_command_registered_before_generic_text_handler():
    """Command('git') зарегистрирован строго до F.text в роутере сообщений."""
    bot_path = Path(__file__).resolve().parents[1] / "src" / "notifier" / "bot_handler.py"
    tree = ast.parse(bot_path.read_text(encoding="utf-8"))

    git_line = None
    text_line = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            unparsed = ast.unparse(node)
            if "Command(" in unparsed and "git" in unparsed and git_line is None:
                git_line = node.lineno
            elif "F.text" in unparsed and text_line is None:
                text_line = node.lineno

    assert git_line is not None, "Регистрация Command('git') не найдена"
    assert text_line is not None, "Регистрация F.text не найдена"
    assert git_line < text_line, f"Command('git') (L{git_line}) должен предшествовать F.text (L{text_line})"


@pytest.mark.asyncio
async def test_voice_dispatch_has_git_branch(bot_fixture):
    """Голосовое сообщение с действием git маршрутизируется в handle_cmd_git."""
    f = bot_fixture
    f.handler.handle_cmd_git = AsyncMock()

    # Мокаем транскрипцию и роутер
    f.handler.voice_processor.transcribe = AsyncMock(
        return_value=SimpleNamespace(success=True, transcription="как там коммиты")
    )
    f.handler.intent_router.route = AsyncMock(
        return_value=SimpleNamespace(action="git", confidence=0.95, model="test", latency_ms=10.0)
    )

    msg = MagicMock()
    msg.from_user.id = USER_ID
    msg.chat.id = USER_ID
    msg.voice.file_id = "voice_file_123"
    msg.voice.duration = 5
    msg.answer = AsyncMock()

    f.handler.bot.get_file = AsyncMock(return_value=SimpleNamespace(file_path="voice.ogg"))
    f.handler.bot.download_file = AsyncMock()

    await f.handler.handle_user_voice(msg)
    f.handler.handle_cmd_git.assert_called_once_with(msg)


@pytest.mark.asyncio
async def test_help_mentions_git_command(bot_fixture):
    """Справка /help упоминает команду /git."""
    f = bot_fixture
    msg = MagicMock()
    msg.from_user.id = USER_ID
    msg.chat.id = USER_ID

    f.handler.notifier.send_message = AsyncMock()
    await f.handler.handle_cmd_help(msg)

    assert f.handler.notifier.send_message.called
    help_text = f.handler.notifier.send_message.call_args[0][0]
    assert "/git" in help_text
