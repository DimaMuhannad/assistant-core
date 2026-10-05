"""End-to-end integration tests for Tool Calling & HITL workflow (Phase 8, Plan 08-04).

Scenarios:
1. 'Письмо Новиковой' (D-02):
   - Two-step tool calling: search_emails -> reminder proposal -> HITL card -> Telegram confirm -> SQLite persistence.
2. Google Calendar 'pending_sync' resilience & retry flow (D-04):
   - Calendar proposal -> Telegram confirm -> Network outage -> pending_sync fallback -> Retry callback -> sync active.
3. Missing time clarification (D-03):
   - User request without concrete time -> Clarification question without guessing fake hours.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message
from google.genai import types

from assistant_shared.db.migrator import run_migrations
from assistant_shared.hitl import ConfirmationStatus
from src.brain.secretary_dialog import SecretaryDialogEngine
from src.calendar.client import GoogleCalendarClient
from src.notifier.bot_handler import EmailBotHandler
from src.storage.db import Database


@pytest.fixture
async def e2e_db(tmp_path: Path) -> AsyncGenerator[Database, None]:
    """Isolated SQLite database with migrations applied."""
    db_file = tmp_path / "test_tool_calling_e2e.db"
    run_migrations(db_file)
    db = Database(str(db_file))
    await db.init_db()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_e2e_novikova_email_reminder_flow(e2e_db: Database):
    """Scenario 1: Full cycle for 'письмо Новиковой' (D-02, ACT-01, ACT-02, ACT-03).

    1. Seed incoming email from Novikova with deadline.
    2. User sends: 'Поставь напоминание о дедлайне из письма Новиковой'.
    3. Model performs two-step tool calling: search_emails -> create_reminder proposal.
    4. Secretary dialog outputs HITL confirmation card with inline buttons.
    5. Check DB: reminder NOT yet created in reminders table (air-gap HITL safety).
    6. User clicks 'Создать напоминание' callback.
    7. Handler executes action, edits Telegram card, and creates reminder in SQLite.
    """
    user_id = 12345

    # 1. Seed email message
    await e2e_db.upsert_email_message(
        message_id="msg_novikova_e2e_01",
        account_id="guap",
        folder="INBOX",
        sender_name="Новикова Юлиана Александровна",
        sender_email="novikova@guap.ru",
        recipients_json='["popov@guap.ru"]',
        subject="Сроки сдачи отчетов по эффективному контракту",
        date_sent=datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc),
        body_plain="Уважаемые коллеги! Напоминаю о необходимости сдать отчеты по эффективному контракту до 15.10.2026 18:00.",
        body_html="",
        snippet="сдать отчеты по эффективному контракту до 15.10.2026 18:00",
        has_attachments=False,
        attachments_json="[]",
        in_reply_to=None,
        references_text=None,
        thread_id="th_novikova_e2e_01",
        category="guap_dept",
        requires_action=True,
    )

    # 2. Setup mock bot and handler
    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    handler = EmailBotHandler(
        db=e2e_db,
        bot=mock_bot,
        allowed_user_id=user_id,
    )

    # Setup mocked GenAI client for SecretaryDialogEngine
    mock_genai_client = MagicMock()
    handler.dialog_engine._client = mock_genai_client

    # Step 1 response from LLM: call search_emails
    fc1 = types.FunctionCall(
        name="search_emails",
        args={"query": "эффективному контракту", "sender": "Новикова"},
    )
    cand1 = types.Candidate(content=types.Content(role="model", parts=[types.Part(function_call=fc1)]))
    resp1 = types.GenerateContentResponse(candidates=[cand1])

    # Step 2 response from LLM: call create_reminder
    fc2 = types.FunctionCall(
        name="create_reminder",
        args={
            "text": "Сдать отчет по эффективному контракту",
            "due_date": "2026-10-15 18:00",
            "category": "academic",
            "target": "Новикова Ю.А.",
        },
    )
    cand2 = types.Candidate(content=types.Content(role="model", parts=[types.Part(function_call=fc2)]))
    resp2 = types.GenerateContentResponse(candidates=[cand2])

    mock_genai_client.aio.models.generate_content = AsyncMock(side_effect=[resp1, resp2])

    # 3. User message arrives in bot
    incoming_msg = MagicMock(spec=Message)
    incoming_msg.from_user = MagicMock()
    incoming_msg.from_user.id = user_id
    incoming_msg.chat = MagicMock()
    incoming_msg.chat.id = user_id
    incoming_msg.chat.type = "private"
    incoming_msg.text = "Поставь напоминание о дедлайне из письма Новиковой"
    incoming_msg.delete = AsyncMock()
    incoming_msg.answer = AsyncMock()

    await handler.handle_user_text(incoming_msg)

    # 4. Verify Telegram reply sent with HITL confirmation card
    mock_bot.send_message.assert_called_once()
    call_args, call_kwargs = mock_bot.send_message.call_args
    reply_text = call_kwargs.get("text", "")
    reply_markup = call_kwargs.get("reply_markup")

    assert "Подтверждаете данное действие?" in reply_text
    assert "Сдать отчет по эффективному контракту" in reply_text
    assert "2026-10-15 18:00" in reply_text
    assert reply_markup is not None
    assert len(reply_markup.inline_keyboard) == 1
    conf_btn, rej_btn = reply_markup.inline_keyboard[0]
    assert conf_btn.callback_data.startswith("act:rem:conf:")
    conf_id = conf_btn.callback_data.replace("act:rem:conf:", "")

    # 5. Check database: No Novikova reminder exists yet (air-gap HITL safety)!
    async with e2e_db.connection() as conn:
        cursor = await conn.execute("SELECT count(*) FROM reminders WHERE what LIKE '%эффективному контракту%';")
        row = await cursor.fetchone()
        assert row[0] == 0

    # 6. Check confirmation store has pending item
    store = handler._get_confirmation_store()
    pending_items = await store.list_pending(persona_id="popov")
    assert len(pending_items) == 1
    assert pending_items[0].id == conf_id
    assert pending_items[0].action_type == "create_reminder"
    assert pending_items[0].status == ConfirmationStatus.PENDING

    # 7. User clicks confirm button
    cb_query = MagicMock(spec=CallbackQuery)
    cb_query.data = f"act:rem:conf:{conf_id}"
    cb_query.from_user = MagicMock()
    cb_query.from_user.id = user_id
    cb_query.answer = AsyncMock()
    cb_query.message = MagicMock(spec=Message)
    cb_query.message.edit_text = AsyncMock()

    await handler.cb_act_reminder_confirm(cb_query)

    # 8. Verify confirmation results
    cb_query.message.edit_text.assert_called_once()
    edited_text = cb_query.message.edit_text.call_args[0][0]
    assert "Напоминание успешно создано" in edited_text
    assert cb_query.message.edit_text.call_args[1].get("reply_markup") is None

    # 9. Verify reminder is physically persisted in SQLite
    async with e2e_db.connection() as conn:
        cursor = await conn.execute(
            "SELECT what, check_date, status FROM reminders WHERE what LIKE '%эффективному контракту%';"
        )
        row = await cursor.fetchone()
        assert row is not None
        assert "Сдать отчет по эффективному контракту" in row[0]
        assert "2026-10-15 18:00" in row[1]
        assert row[2] == "active"


@pytest.mark.asyncio
async def test_e2e_calendar_pending_sync_and_retry_flow(e2e_db: Database):
    """Scenario 2: Google Calendar outage with pending_sync fallback and retry (D-04).

    1. User confirms calendar event creation.
    2. Google API fails with ConnectionError.
    3. System captures event into SQLite pending_sync and sends retry button.
    4. Network recovers; user clicks [🔄 Повторить синхронизацию].
    5. Event is sent to Google Calendar and status transitions to 'active'.
    """
    user_id = 9876
    mock_cal = MagicMock(spec=GoogleCalendarClient)
    mock_cal.calendar_id = "primary"
    # Step A: API failure
    mock_cal.create_event = AsyncMock(side_effect=ConnectionError("Failed to reach googleapis.com"))
    mock_cal.create_event_from_dict = AsyncMock(return_value="google_event_recovered_e2e_1")

    handler = EmailBotHandler(
        db=e2e_db,
        allowed_user_id=user_id,
        calendar_client=mock_cal,
    )
    store = handler._get_confirmation_store()

    # Pre-create pending confirmation for calendar event
    conf = await store.create_confirmation(
        persona_id="popov",
        action_type="create_calendar_event",
        payload={
            "title": "Научный семинар кафедры физики",
            "date": "2026-10-28",
            "start_time": "14:00",
            "end_time": "15:30",
            "location": "Ауд. 53-01",
        },
    )

    cb_confirm = MagicMock(spec=CallbackQuery)
    cb_confirm.data = f"act:cal:conf:{conf.id}"
    cb_confirm.from_user = MagicMock()
    cb_confirm.from_user.id = user_id
    cb_confirm.answer = AsyncMock()
    cb_confirm.message = MagicMock(spec=Message)
    cb_confirm.message.edit_text = AsyncMock()

    # User clicks confirm -> fails -> pending_sync
    await handler.cb_act_calendar_confirm(cb_confirm)

    cb_confirm.message.edit_text.assert_called_once()
    fail_card_text = cb_confirm.message.edit_text.call_args[0][0]
    reply_markup = cb_confirm.message.edit_text.call_args[1]["reply_markup"]

    assert "временно недоступен" in fail_card_text.lower()
    assert "pending_sync" in fail_card_text
    retry_btn = reply_markup.inline_keyboard[0][0]
    assert "Повторить синхронизацию" in retry_btn.text
    sync_id = int(retry_btn.callback_data.split(":")[3])

    # Check SQLite pending record
    pending_record = await e2e_db.get_pending_calendar_sync(sync_id)
    assert pending_record is not None
    assert pending_record["status"] == "pending_sync"
    assert pending_record["summary"] == "Научный семинар кафедры физики"

    # Step B: User clicks retry button
    cb_retry = MagicMock(spec=CallbackQuery)
    cb_retry.data = f"act:cal:retry:{sync_id}"
    cb_retry.from_user = MagicMock()
    cb_retry.from_user.id = user_id
    cb_retry.answer = AsyncMock()
    cb_retry.message = MagicMock(spec=Message)
    cb_retry.message.edit_text = AsyncMock()

    await handler.cb_act_calendar_retry(cb_retry)

    cb_retry.message.edit_text.assert_called_once()
    success_text = cb_retry.message.edit_text.call_args[0][0]
    assert "Синхронизировано с Google Calendar" in success_text

    # Record updated to active
    active_record = await e2e_db.get_pending_calendar_sync(sync_id)
    assert active_record is not None
    assert active_record["status"] == "active"
    assert active_record["google_event_id"] == "google_event_recovered_e2e_1"


@pytest.mark.asyncio
async def test_e2e_missing_time_clarification_no_card(e2e_db: Database):
    """Scenario 3: Request without concrete time triggers clarification dialogue without guessing fake hours (D-03)."""
    user_id = 5544
    engine = SecretaryDialogEngine(db=e2e_db, api_key="dummy-key")
    mock_client = MagicMock()
    engine._client = mock_client

    # Model returns question: 'В какое время в пятницу запланировать встречу?'
    clarification_msg = "В какое время в пятницу запланировать встречу с деканом?"
    cand = types.Candidate(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=clarification_msg)],
        )
    )
    mock_resp = types.GenerateContentResponse(candidates=[cand])
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)

    answer, proposal = await engine.answer_user_message(
        user_id=user_id,
        message_text="Запланируй встречу с деканом в пятницу",
        return_proposal=True,
    )

    # Verify no proposal card was generated and model asked for time
    assert proposal is None
    assert "время" in answer.lower()
    assert "в какое время" in answer.lower() or "какое время" in answer.lower()
