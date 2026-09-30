"""Unit tests for FastIntentRouter and its integration with EmailBotHandler."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.storage.db import Database
from src.brain.intent_router import FastIntentRouter, IntentResult, ROUTER_SYSTEM_PROMPT


@pytest.fixture
async def test_db():
    db = Database(":memory:")
    await db.init_db()
    return db


@pytest.mark.asyncio
async def test_router_deterministic_clear_dialog(test_db):
    """Verify that deterministic commands bypass LLM and route instantly."""
    router = FastIntentRouter(db=test_db)
    res = await router.route(user_id=123, message_text="очисти диалог")

    assert res.action == "clear_dialog"
    assert res.confidence == 1.0
    assert res.model == "fast-rule"
    assert res.latency_ms == 0.0

    # Verify audit log in SQLite
    audit = await test_db.get_recent_router_audit(limit=5)
    assert len(audit) == 1
    assert audit[0]["action_chosen"] == "clear_dialog"
    assert audit[0]["user_id"] == 123


@pytest.mark.asyncio
async def test_router_offline_mode(test_db):
    """Verify that router defaults to secretary when unconfigured (offline)."""
    router = FastIntentRouter(db=test_db, api_key="")
    res = await router.route(user_id=456, message_text="Сколько часов отработано?")

    assert res.action == "secretary"
    assert res.model == "offline"

    audit = await test_db.get_recent_router_audit(limit=5)
    assert len(audit) == 1
    assert audit[0]["action_chosen"] == "secretary"


@pytest.mark.asyncio
async def test_router_llm_classification_success(test_db):
    """Verify successful JSON parsing from LLM response."""
    router = FastIntentRouter(db=test_db, api_key="test-api-key", model="gemini-3.8-flash")

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps({
        "action": "timesheet",
        "confidence": 0.98,
        "reason": "Запрос табеля и часов"
    })
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)
    router._client = mock_client

    res = await router.route(user_id=789, message_text="табель за сентябрь")

    assert res.action == "timesheet"
    assert res.confidence == 0.98
    assert res.model == "gemini-3.8-flash"
    assert "Запрос табеля" in res.reason

    audit = await test_db.get_recent_router_audit(limit=5)
    assert len(audit) == 1
    assert audit[0]["action_chosen"] == "timesheet"
    assert audit[0]["model"] == "gemini-3.8-flash"


@pytest.mark.asyncio
async def test_router_invalid_action_defaults_to_secretary(test_db):
    """Verify that an unrecognized action string safely defaults to secretary."""
    router = FastIntentRouter(db=test_db, api_key="test-api-key")

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps({
        "action": "unknown_random_action",
        "confidence": 0.5,
        "reason": "Непонятный интент"
    })
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)
    router._client = mock_client

    res = await router.route(user_id=789, message_text="какой-то странный запрос")
    assert res.action == "secretary"


@pytest.mark.asyncio
async def test_router_fallback_on_model_quota_error(test_db):
    """Verify fallback to secondary model when primary model encounters 429/quota error."""
    router = FastIntentRouter(db=test_db, api_key="test-api-key", model="gemini-3.8-flash")
    router._model_cooldowns.clear()

    mock_client = MagicMock()
    mock_success_resp = MagicMock()
    mock_success_resp.text = json.dumps({
        "action": "evening",
        "confidence": 0.95,
        "reason": "Запрос дайджеста"
    })

    # First attempt fails with 429 RESOURCE_EXHAUSTED, second succeeds
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=[
            Exception("429 RESOURCE_EXHAUSTED Quota exceeded for gemini-3.8-flash"),
            mock_success_resp,
        ]
    )
    router._client = mock_client

    res = await router.route(user_id=101, message_text="Подведи вечерние итоги дня, пожалуйста")

    assert res.action == "evening"
    assert res.model == "gemini-3.5-flash-lite"
    assert "gemini-3.8-flash" in router._model_cooldowns


@pytest.mark.asyncio
async def test_bot_handler_dispatch_to_timesheet(test_db):
    """Verify that EmailBotHandler correctly dispatches timesheet intent."""
    from src.notifier.bot_handler import EmailBotHandler

    handler = EmailBotHandler(db=test_db, allowed_user_id=123)
    handler.handle_cmd_timesheet = AsyncMock()
    handler._handle_secretary_dialog = AsyncMock()

    # Mock router to return timesheet
    handler.intent_router.route = AsyncMock(
        return_value=IntentResult(
            action="timesheet",
            confidence=0.99,
            reason="Запрос табеля",
            model="test-model",
            latency_ms=10.0,
        )
    )

    mock_msg = MagicMock()
    mock_msg.from_user.id = 123
    mock_msg.text = "покажи табель тидекс"

    await handler.handle_user_text(mock_msg)

    handler.handle_cmd_timesheet.assert_awaited_once_with(mock_msg)
    handler._handle_secretary_dialog.assert_not_awaited()


@pytest.mark.asyncio
async def test_bot_handler_dispatch_to_secretary(test_db):
    """Verify that EmailBotHandler dispatches nuanced conversational inquiries to secretary."""
    from src.notifier.bot_handler import EmailBotHandler

    handler = EmailBotHandler(db=test_db, allowed_user_id=123)
    handler.handle_cmd_timesheet = AsyncMock()
    handler._handle_secretary_dialog = AsyncMock()

    # Mock router to return secretary
    handler.intent_router.route = AsyncMock(
        return_value=IntentResult(
            action="secretary",
            confidence=0.95,
            reason="Сложный вопрос для секретаря",
            model="test-model",
            latency_ms=15.0,
        )
    )

    mock_msg = MagicMock()
    mock_msg.from_user.id = 123
    mock_msg.text = "Сколько часов мне надо доработать до конца месяца с учетом отпуска в пятницу?"

    await handler.handle_user_text(mock_msg)

    handler._handle_secretary_dialog.assert_awaited_once_with(mock_msg, mock_msg.text)
    handler.handle_cmd_timesheet.assert_not_awaited()


@pytest.mark.asyncio
async def test_bot_handler_dispatch_to_methodist(test_db):
    """Verify that EmailBotHandler dispatches methodist queries."""
    from src.notifier.bot_handler import EmailBotHandler

    handler = EmailBotHandler(db=test_db, allowed_user_id=123)
    handler._handle_methodist_query = AsyncMock()

    handler.intent_router.route = AsyncMock(
        return_value=IntentResult(
            action="methodist",
            confidence=0.98,
            reason="Вопрос по ГОСТу",
            model="test-model",
            latency_ms=12.0,
        )
    )

    mock_msg = MagicMock()
    mock_msg.from_user.id = 123
    mock_msg.text = "@методист как оформить титульный лист"

    await handler.handle_user_text(mock_msg)

    handler._handle_methodist_query.assert_awaited_once_with(mock_msg, "как оформить титульный лист")


@pytest.mark.asyncio
async def test_router_markdown_fenced_json_parsing(test_db):
    """Verify that extract_json_object cleanly handles Markdown code fences."""
    router = FastIntentRouter(db=test_db, api_key="test-api-key")

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = '```json\n{\n  "action": "lms_reports",\n  "confidence": 0.96,\n  "reason": "Запрос непроверенных отчетов"\n}\n```'
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)
    router._client = mock_client

    res = await router.route(user_id=123, message_text="кто из студентов сдал отчеты?")
    assert res.action == "lms_reports"
    assert res.confidence == 0.96
    assert "непроверенных отчетов" in res.reason


@pytest.mark.asyncio
async def test_router_new_deterministic_shortcuts(test_db):
    """Verify instant zero-latency routing for standard Russian commands and shortcuts."""
    router = FastIntentRouter(db=test_db, api_key="test-api-key")

    res_ts = await router.route(user_id=123, message_text="табель")
    assert res_ts.action == "timesheet"
    assert res_ts.model == "fast-rule"

    res_ev = await router.route(user_id=123, message_text="вечерний дайджест")
    assert res_ev.action == "evening"
    assert res_ev.model == "fast-rule"

    res_em = await router.route(user_id=123, message_text="почта")
    assert res_em.action == "emails"
    assert res_em.model == "fast-rule"

    res_rep = await router.route(user_id=123, message_text="отчеты")
    assert res_rep.action == "lms_reports"
    assert res_rep.model == "fast-rule"
