"""Tests for Tool Calling flow: Two-step email search, time clarification, pending_sync buffer, and retry callback (Phase 8, Plan 08-03)."""

from datetime import datetime, timezone, date
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message
from google.genai import types

from assistant_shared.db.migrator import run_migrations
from assistant_shared.hitl import (
    ConfirmationChannel,
    ConfirmationStatus,
)
from src.brain.intent_router import FastIntentRouter, VALID_ACTIONS
from src.brain.secretary_dialog import SecretaryDialogEngine
from src.brain.tools_schema import ActionProposal, SECRETARY_TOOLS
from src.calendar.client import GoogleCalendarClient
from src.notifier.bot_handler import EmailBotHandler
from src.storage.db import Database


@pytest.fixture
async def test_db(tmp_path: Path) -> AsyncGenerator[Database, None]:
    """Isolated SQLite database with migrations applied."""
    db_file = tmp_path / "test_tool_calling_flow.db"
    run_migrations(db_file)
    db = Database(str(db_file))
    await db.init_db()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_intent_router_actions_and_fast_rules(test_db: Database):
    """Verify that FastIntentRouter supports planning actions and classifies deterministic phrases (ACT-04)."""
    assert {"calendar_schedule", "create_reminder", "draft_reply"}.issubset(VALID_ACTIONS)

    router = FastIntentRouter(db=test_db, api_key="dummy")

    # 1. Calendar schedule phrases
    res1 = await router.route(user_id=1, message_text="запиши в календарь пару по физике на пятницу в 15:00")
    assert res1.action == "calendar_schedule"
    assert res1.confidence == 1.0
    assert res1.model == "fast-rule"

    res2 = await router.route(user_id=1, message_text="добавь в календарь встречу с аспирантом")
    assert res2.action == "calendar_schedule"

    res3 = await router.route(user_id=1, message_text="запланируй встречу с деканом завтра в 11")
    assert res3.action == "calendar_schedule"

    # 2. Reminder phrases
    res4 = await router.route(user_id=1, message_text="напомни мне проверить отчеты студентов")
    assert res4.action == "create_reminder"
    assert res4.confidence == 1.0
    assert res4.model == "fast-rule"

    res5 = await router.route(user_id=1, message_text="поставь дедлайн по эффективному контракту")
    assert res5.action == "create_reminder"

    res6 = await router.route(user_id=1, message_text="создай напоминание позвонить в отдел кадров")
    assert res6.action == "create_reminder"

    # 3. Email draft reply phrases
    res7 = await router.route(user_id=1, message_text="ответь на письмо Новиковой что отчет готов")
    assert res7.action == "draft_reply"
    assert res7.confidence == 1.0
    assert res7.model == "fast-rule"

    res8 = await router.route(user_id=1, message_text="черновик ответа старосте группы")
    assert res8.action == "draft_reply"

    res9 = await router.route(user_id=1, message_text="подготовь ответ на запрос деканата")
    assert res9.action == "draft_reply"


@pytest.mark.asyncio
async def test_bot_handler_routes_planning_intents_to_secretary_dialog(test_db: Database):
    """Verify that bot_handler dispatches planning intents to _handle_secretary_dialog with intent context."""
    user_id = 9988
    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    handler = EmailBotHandler(
        db=test_db,
        bot=mock_bot,
        allowed_user_id=user_id,
    )
    handler.dialog_engine.answer_user_message = AsyncMock(return_value=("Ответ секретаря", [], None))

    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock()
    msg.from_user.id = user_id
    msg.chat = MagicMock()
    msg.chat.id = user_id
    msg.chat.type = "private"
    msg.delete = AsyncMock()
    msg.answer = AsyncMock()

    # Calendar schedule intent
    msg.text = "запиши в календарь консультацию 15 октября в 16:00"
    await handler.handle_user_text(msg)
    handler.dialog_engine.answer_user_message.assert_called_with(
        user_id=user_id,
        message_text=msg.text,
        return_files=True,
        return_proposal=True,
        intent="calendar_schedule",
    )

    # Reminder intent
    msg.text = "напомни отправить отчет в пятницу"
    await handler.handle_user_text(msg)
    handler.dialog_engine.answer_user_message.assert_called_with(
        user_id=user_id,
        message_text=msg.text,
        return_files=True,
        return_proposal=True,
        intent="create_reminder",
    )

    # Draft reply intent
    msg.text = "ответь на письмо замдекана"
    await handler.handle_user_text(msg)
    handler.dialog_engine.answer_user_message.assert_called_with(
        user_id=user_id,
        message_text=msg.text,
        return_files=True,
        return_proposal=True,
        intent="draft_reply",
    )


@pytest.mark.asyncio
async def test_two_step_search_emails_flow_d02(test_db: Database):
    """Verify two-step tool calling: search_emails followed by ActionProposal generation (D-02)."""
    await test_db.upsert_email_message(
        message_id="msg_novikova_101",
        account_id="guap",
        folder="INBOX",
        sender_name="Новикова Ю.А.",
        sender_email="novikova@guap.ru",
        recipients_json='["scipopov@guap.ru"]',
        subject="Сроки сдачи отчетов по эффективному контракту",
        date_sent=datetime(2026, 10, 5, 9, 30, tzinfo=timezone.utc),
        body_plain="Уважаемые коллеги! Напоминаю, что срок сдачи отчетов по эффективному контракту — до 15.10.2026 18:00.",
        body_html="",
        snippet="срок сдачи отчетов до 15.10.2026 18:00",
        has_attachments=False,
        attachments_json="[]",
        in_reply_to=None,
        references_text=None,
        thread_id="th_novikova_101",
        category="guap_dept",
        requires_action=True,
    )

    engine = SecretaryDialogEngine(db=test_db, api_key="test-api-key")
    mock_client = MagicMock()
    engine._client = mock_client

    # Step 1: Model requests search_emails
    fc1 = types.FunctionCall(
        name="search_emails",
        args={"query": "эффективному контракту", "sender": "Новикова"},
    )
    cand1 = types.Candidate(content=types.Content(role="model", parts=[types.Part(function_call=fc1)]))
    resp1 = types.GenerateContentResponse(candidates=[cand1])

    # Step 2: Model consumes search results and produces create_reminder ActionProposal
    fc2 = types.FunctionCall(
        name="create_reminder",
        args={
            "text": "Сдача отчетов по эффективному контракту",
            "due_date": "2026-10-15 18:00",
            "category": "academic",
            "target": "Новикова Ю.А.",
        },
    )
    cand2 = types.Candidate(content=types.Content(role="model", parts=[types.Part(function_call=fc2)]))
    resp2 = types.GenerateContentResponse(candidates=[cand2])

    mock_client.aio.models.generate_content = AsyncMock(side_effect=[resp1, resp2])

    answer, proposal = await engine.answer_user_message(
        user_id=123,
        message_text="Поставь напоминание о дедлайне из письма Новиковой",
        return_proposal=True,
    )

    # Verify that search_emails was executed and subsequent reminder proposal generated
    assert mock_client.aio.models.generate_content.call_count == 2
    assert proposal is not None
    assert proposal.action_type == "create_reminder"
    assert proposal.params["due_date"] == "2026-10-15 18:00"
    assert "эффективному контракту" in proposal.params["text"].lower()
    assert "карточку" in answer.lower()


@pytest.mark.asyncio
async def test_missing_time_clarification_no_action_proposal_d03(test_db: Database):
    """Verify that requests without concrete event time trigger clarification dialogue without guessing default hours (D-03)."""
    engine = SecretaryDialogEngine(db=test_db, api_key="test-api-key")
    mock_client = MagicMock()
    engine._client = mock_client

    # Model replies with clarification question instead of invoking tool with fake 00:00 / 09:00
    clarification_text = "В какое время в пятницу запланировать встречу с деканом?"
    cand = types.Candidate(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=clarification_text)],
        )
    )
    mock_resp = types.GenerateContentResponse(candidates=[cand])
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)

    answer, proposal = await engine.answer_user_message(
        user_id=456,
        message_text="Запланируй встречу с деканом в пятницу",
        return_proposal=True,
    )

    assert proposal is None
    assert "время" in answer.lower()
    assert "какое время" in answer.lower() or "в какое время" in answer.lower()


@pytest.mark.asyncio
async def test_calendar_pending_sync_buffer_and_retry_flow_d04(test_db: Database):
    """Verify that Google Calendar API errors store records in pending_sync and retry button restores them (D-04)."""
    user_id = 777
    mock_cal_client = MagicMock()
    # 1. Simulate Google Calendar API failure (network error / 503)
    mock_cal_client.create_event = AsyncMock(side_effect=Exception("503 Service Unavailable: Google Calendar unreachable"))
    mock_cal_client.calendar_id = "primary"

    handler = EmailBotHandler(
        db=test_db,
        allowed_user_id=user_id,
        calendar_client=mock_cal_client,
    )
    store = handler._get_confirmation_store()

    conf = await store.create_confirmation(
        persona_id="popov",
        action_type="create_calendar_event",
        payload={
            "title": "Срочное заседание кафедры",
            "date": "2026-10-22",
            "start_time": "15:00",
            "end_time": "16:30",
            "location": "Ауд. 13-05",
        },
        channel=ConfirmationChannel.TELEGRAM,
    )

    cb_confirm = MagicMock(spec=CallbackQuery)
    cb_confirm.data = f"act:cal:conf:{conf.id}"
    cb_confirm.from_user = MagicMock()
    cb_confirm.from_user.id = user_id
    cb_confirm.answer = AsyncMock()
    cb_confirm.message = MagicMock(spec=Message)
    cb_confirm.message.edit_text = AsyncMock()

    # Step 1: User confirms creation, but API fails
    await handler.cb_act_calendar_confirm(cb_confirm)

    # Verification of Step 1:
    cb_confirm.message.edit_text.assert_called_once()
    status_text, kwargs = cb_confirm.message.edit_text.call_args[0][0], cb_confirm.message.edit_text.call_args[1]
    assert "pending_sync" in status_text
    assert "временно недоступен" in status_text.lower()
    assert "reply_markup" in kwargs
    retry_markup = kwargs["reply_markup"]
    assert len(retry_markup.inline_keyboard) == 1
    retry_btn = retry_markup.inline_keyboard[0][0]
    assert "Повторить синхронизацию" in retry_btn.text
    assert retry_btn.callback_data.startswith("act:cal:retry:")

    sync_id = int(retry_btn.callback_data.split(":")[3])

    # Check database state: record saved with pending_sync status
    pending_rec = await test_db.get_pending_calendar_sync(sync_id)
    assert pending_rec is not None
    assert pending_rec["status"] == "pending_sync"
    assert pending_rec["summary"] == "Срочное заседание кафедры"

    # Step 2: Network is restored. User clicks retry button
    mock_cal_client.create_event = AsyncMock(return_value="google_cal_ev_recovered_999")
    mock_cal_client.create_event_from_dict = AsyncMock(return_value="google_cal_ev_recovered_999")

    cb_retry = MagicMock(spec=CallbackQuery)
    cb_retry.data = f"act:cal:retry:{sync_id}"
    cb_retry.from_user = MagicMock()
    cb_retry.from_user.id = user_id
    cb_retry.answer = AsyncMock()
    cb_retry.message = MagicMock(spec=Message)
    cb_retry.message.edit_text = AsyncMock()

    await handler.cb_act_calendar_retry(cb_retry)

    # Verification of Step 2:
    cb_retry.message.edit_text.assert_called_once()
    final_text = cb_retry.message.edit_text.call_args[0][0]
    assert "Синхронизировано с Google Calendar" in final_text

    # Database updated to active and google_event_id saved
    updated_rec = await test_db.get_pending_calendar_sync(sync_id)
    assert updated_rec is not None
    assert updated_rec["status"] == "active"
    assert updated_rec["google_event_id"] == "google_cal_ev_recovered_999"


@pytest.mark.asyncio
async def test_google_calendar_client_create_event_from_dict():
    """Verify GoogleCalendarClient.create_event_from_dict parses parameters and creates events."""
    client = GoogleCalendarClient(dry_run=True)

    event_payload = {
        "title": "Консультация перед экзаменом",
        "date": "2026-10-25",
        "start_time": "11:00",
        "end_time": "12:30",
        "location": "Ауд. 13-05",
        "description": "Разбор задач",
    }

    event_id = await client.create_event_from_dict("primary", event_payload)
    assert event_id.startswith("mock_")

    # Also test with event_start and event_end directly
    event_payload2 = {
        "summary": "Встреча аспирантов",
        "event_start": "2026-10-26T14:00:00",
        "event_end": "2026-10-26T15:00:00",
    }
    event_id2 = await client.create_event_from_dict("primary", event_payload2)
    assert event_id2.startswith("mock_")
