"""Tests for Secretary Tools schema, function calling interception, and anti-hallucination guardrails (Phase 8, Plan 08-01)."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from google.genai import types

from src.storage.db import Database
from src.brain.secretary_dialog import SecretaryDialogEngine
from src.brain.tools_schema import (
    ActionProposal,
    SECRETARY_TOOLS,
    tool_create_calendar_event,
    tool_create_reminder,
    tool_draft_email_reply,
    tool_search_emails,
)
from src.persona.prompts import render_prompt


def test_secretary_tools_schema_declarations():
    """Verify that all 4 tool schemas are properly declared with required properties and types."""
    assert len(SECRETARY_TOOLS) == 1
    tool_decl = SECRETARY_TOOLS[0]
    funcs = {f.name: f for f in tool_decl.function_declarations}

    assert len(funcs) == 4
    assert set(funcs.keys()) == {
        "create_calendar_event",
        "create_reminder",
        "draft_email_reply",
        "search_emails",
    }

    # 1. create_calendar_event
    cal_tool = funcs["create_calendar_event"]
    assert set(cal_tool.parameters.required) == {"title", "date", "start_time", "end_time"}
    cal_props = cal_tool.parameters.properties
    assert "title" in cal_props
    assert "date" in cal_props
    assert "start_time" in cal_props
    assert "end_time" in cal_props
    assert "description" in cal_props
    assert "location" in cal_props

    # 2. create_reminder
    rem_tool = funcs["create_reminder"]
    assert set(rem_tool.parameters.required) == {"text", "due_date"}
    rem_props = rem_tool.parameters.properties
    assert "text" in rem_props
    assert "due_date" in rem_props
    assert "target" in rem_props
    assert "category" in rem_props

    # 3. draft_email_reply
    draft_tool = funcs["draft_email_reply"]
    assert set(draft_tool.parameters.required) == {"email_id", "reply_text"}
    draft_props = draft_tool.parameters.properties
    assert "email_id" in draft_props
    assert "reply_text" in draft_props

    # 4. search_emails
    search_tool = funcs["search_emails"]
    assert set(search_tool.parameters.required) == {"query"}
    search_props = search_tool.parameters.properties
    assert "query" in search_props
    assert "sender" in search_props
    assert "limit" in search_props


def test_action_proposal_dataclass():
    """Verify ActionProposal dataclass attributes and defaults."""
    prop = ActionProposal(
        action_type="create_calendar_event",
        params={"title": "Консультация", "date": "2026-10-10"},
    )
    assert prop.action_type == "create_calendar_event"
    assert prop.params["title"] == "Консультация"
    assert prop.proposal_text == ""

    prop2 = ActionProposal(
        action_type="create_reminder",
        params={"text": "Купить билеты"},
        proposal_text="Подготовлено напоминание",
    )
    assert prop2.proposal_text == "Подготовлено напоминание"


@pytest.mark.asyncio
async def test_calendar_event_action_proposal_interception():
    """Verify that create_calendar_event tool call produces ActionProposal without mutating Google Calendar (ACT-01)."""
    db = Database(db_path=":memory:")
    await db.init_db()

    engine = SecretaryDialogEngine(db=db, api_key="test-api-key")

    mock_client = MagicMock()
    engine._client = mock_client

    fc = types.FunctionCall(
        name="create_calendar_event",
        args={
            "title": "Консультация гр. 1632",
            "date": "2026-10-10",
            "start_time": "18:30",
            "end_time": "20:00",
            "location": "Ауд. 13-05",
            "description": "Разбор типового расчета",
        },
    )
    candidate = types.Candidate(content=types.Content(role="model", parts=[types.Part(function_call=fc)]))
    mock_resp = types.GenerateContentResponse(candidates=[candidate])

    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)

    # Call with return_proposal=True
    answer, proposal = await engine.answer_user_message(
        user_id=123,
        message_text="Запланируй консультацию для группы 1632 10 октября с 18:30 до 20:00 в ауд 13-05",
        return_proposal=True,
    )

    # 1. Verify ActionProposal structure
    assert proposal is not None
    assert proposal.action_type == "create_calendar_event"
    assert proposal.params["title"] == "Консультация гр. 1632"
    assert proposal.params["date"] == "2026-10-10"
    assert proposal.params["start_time"] == "18:30"
    assert proposal.params["end_time"] == "20:00"
    assert proposal.params["location"] == "Ауд. 13-05"

    # 2. Verify answer text informs user about confirmation card
    assert "карточку" in answer.lower()
    assert "подтверд" in answer.lower()

    # 3. Verify tool configuration passed to generate_content
    call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
    assert "config" in call_kwargs
    config_passed = call_kwargs["config"]
    assert config_passed.tools == SECRETARY_TOOLS

    # 4. Verify history persisted
    history = await db.get_recent_dialog_history(123)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "model"
    assert "карточку" in history[1]["content"].lower()

    await db.close()


@pytest.mark.asyncio
async def test_two_step_search_emails_flow():
    """Verify 2-step tool calling: search_emails first, then create_reminder based on found email (D-02, ACT-01)."""
    db = Database(db_path=":memory:")
    await db.init_db()

    # Seed an email in SQLite
    now = datetime.now(timezone.utc)
    await db.upsert_email_message(
        message_id="novikova-deadline-01@guap.ru",
        account_id="guap",
        folder="INBOX",
        sender_name="Новикова Юлия Александровна",
        sender_email="novikova@guap.ru",
        recipients_json='["scipopov@guap.ru"]',
        subject="Сроки сдачи отчетов по эффективному контракту",
        date_sent=now,
        body_plain="Уважаемые коллеги, напоминаю: крайний срок сдачи отчетов 15 октября до 18:00!",
        body_html=None,
        snippet="крайний срок сдачи отчетов 15 октября до 18:00",
        has_attachments=False,
        attachments_json="[]",
        in_reply_to=None,
        references_text=None,
        thread_id="th-nov-01",
        category="guap_dept",
        requires_action=False,
    )

    engine = SecretaryDialogEngine(db=db, api_key="test-api-key")
    mock_client = MagicMock()
    engine._client = mock_client

    # Step 1 response: model invokes search_emails
    fc_search = types.FunctionCall(
        name="search_emails",
        args={"query": "отчет", "sender": "Новикова"},
    )
    resp_step1 = types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(function_call=fc_search)]))]
    )

    # Step 2 response: model processes email text and invokes create_reminder
    fc_reminder = types.FunctionCall(
        name="create_reminder",
        args={
            "text": "Сдача отчетов по эффективному контракту (письмо Новиковой)",
            "due_date": "2026-10-15 18:00",
            "category": "academic",
        },
    )
    resp_step2 = types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(function_call=fc_reminder)]))]
    )

    mock_client.aio.models.generate_content = AsyncMock(side_effect=[resp_step1, resp_step2])

    answer, proposal = await engine.answer_user_message(
        user_id=456,
        message_text="Поставь напоминание о дедлайне из письма Новиковой",
        return_proposal=True,
    )

    # Verify 2 calls to model
    assert mock_client.aio.models.generate_content.call_count == 2

    # Verify second call contents contain tool function_response
    step2_call_args = mock_client.aio.models.generate_content.call_args_list[1]
    step2_contents = step2_call_args.kwargs["contents"]
    assert len(step2_contents) == 3

    tool_content = step2_contents[2]
    assert tool_content.role == "tool"
    assert len(tool_content.parts) == 1
    fn_resp = tool_content.parts[0].function_response
    assert fn_resp.name == "search_emails"
    assert fn_resp.response["count"] >= 1
    assert "Новикова" in fn_resp.response["emails"][0]["sender"]

    # Verify final ActionProposal
    assert proposal is not None
    assert proposal.action_type == "create_reminder"
    assert proposal.params["due_date"] == "2026-10-15 18:00"
    assert "Новиковой" in proposal.params["text"]
    assert "карточку" in answer.lower()

    await db.close()


def test_antihallucination_prompt_content():
    """Verify that secretary system prompt enforces D-05 anti-hallucination directive and clarification rules."""
    rendered = render_prompt("secretary")

    assert "СТРОЖАЙШИЙ ЗАПРЕТ ГАЛЛЮЦИНАЦИЙ И ПРАВИЛО ИСПОЛНИТЕЛЬНОГО КОНТУРА" in rendered
    assert "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО утверждать" in rendered
    assert "не был вызван соответствующий инструмент" in rendered
    assert "Я подготовил карточку" in rendered
    assert "В какое время запланировать встречу?" in rendered
    assert "search_emails" in rendered


@pytest.mark.asyncio
async def test_missing_time_clarification_no_action_proposal():
    """Verify that when user specifies vague date without time, model returns clarification text without ActionProposal."""
    db = Database(db_path=":memory:")
    await db.init_db()

    engine = SecretaryDialogEngine(db=db, api_key="test-api-key")
    mock_client = MagicMock()
    engine._client = mock_client

    # Model asks clarification question (no function_calls)
    clarification_text = "В какое время в пятницу запланировать встречу с деканом?"
    candidate = types.Candidate(content=types.Content(role="model", parts=[types.Part.from_text(text=clarification_text)]))
    mock_resp = types.GenerateContentResponse(candidates=[candidate])

    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)

    answer, proposal = await engine.answer_user_message(
        user_id=789,
        message_text="Запланируй встречу с деканом в пятницу",
        return_proposal=True,
    )

    assert proposal is None
    assert answer == clarification_text

    await db.close()


@pytest.mark.asyncio
async def test_return_flags_backward_compatibility():
    """Verify return_files and return_proposal combinations maintain backward compatibility."""
    db = Database(db_path=":memory:")
    await db.init_db()

    engine = SecretaryDialogEngine(db=db, api_key="test-api-key")
    mock_client = MagicMock()
    engine._client = mock_client

    fc = types.FunctionCall(
        name="draft_email_reply",
        args={"email_id": 42, "reply_text": "Уважаемая Юлиана Александровна, отчет прикреплен."},
    )
    candidate = types.Candidate(content=types.Content(role="model", parts=[types.Part(function_call=fc)]))
    mock_resp = types.GenerateContentResponse(candidates=[candidate])
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)

    # 1. Default (return_files=False, return_proposal=False) -> str
    res1 = await engine.answer_user_message(1, "Ответь на письмо 42")
    assert isinstance(res1, str)
    assert "карточку" in res1.lower() or "проект ответа" in res1.lower()

    # 2. return_files=True, return_proposal=False -> (str, list)
    res2, files2 = await engine.answer_user_message(1, "Ответь на письмо 42", return_files=True)
    assert isinstance(res2, str)
    assert isinstance(files2, list)

    # 3. return_files=False, return_proposal=True -> (str, ActionProposal)
    res3, prop3 = await engine.answer_user_message(1, "Ответь на письмо 42", return_proposal=True)
    assert isinstance(res3, str)
    assert isinstance(prop3, ActionProposal)
    assert prop3.action_type == "draft_email_reply"
    assert prop3.params["email_id"] == 42

    # 4. return_files=True, return_proposal=True -> (str, list, ActionProposal)
    res4, files4, prop4 = await engine.answer_user_message(1, "Ответь на письмо 42", return_files=True, return_proposal=True)
    assert isinstance(res4, str)
    assert isinstance(files4, list)
    assert isinstance(prop4, ActionProposal)
    assert prop4.action_type == "draft_email_reply"

    await db.close()
