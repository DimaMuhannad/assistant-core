"""Tests for HITL Telegram confirmation cards, inline keyboards, and callback_query handlers (Phase 8, Plan 08-02)."""

from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message

from assistant_shared.db.migrator import run_migrations
from assistant_shared.hitl import (
    ConfirmationChannel,
    ConfirmationStatus,
)
from src.brain.tools_schema import ActionProposal
from src.notifier.bot_handler import EmailBotHandler
from src.notifier.telegram import (
    build_hitl_action_keyboard,
    format_hitl_proposal_card,
)
from src.storage.db import Database


@pytest.fixture
async def test_db(tmp_path: Path) -> AsyncGenerator[Database, None]:
    """Isolated SQLite database with migrations applied."""
    db_file = tmp_path / "test_hitl_cards.db"
    run_migrations(db_file)
    db = Database(str(db_file))
    await db.init_db()
    yield db
    await db.close()


def test_hitl_action_keyboard_generation():
    """Verify inline keyboards for calendar, reminder, and email draft actions."""
    conf_id = "test-conf-uuid-1234"

    # 1. create_calendar_event
    kb_cal = build_hitl_action_keyboard(conf_id, "create_calendar_event")
    assert len(kb_cal.inline_keyboard) == 1
    assert len(kb_cal.inline_keyboard[0]) == 2
    btn_conf, btn_rej = kb_cal.inline_keyboard[0]
    assert "Записать в Google Calendar" in btn_conf.text
    assert btn_conf.callback_data == f"act:cal:conf:{conf_id}"
    assert "Отмена" in btn_rej.text
    assert btn_rej.callback_data == f"act:cal:rej:{conf_id}"

    # 2. create_reminder
    kb_rem = build_hitl_action_keyboard(conf_id, "create_reminder")
    assert len(kb_rem.inline_keyboard) == 1
    assert len(kb_rem.inline_keyboard[0]) == 2
    btn_conf, btn_rej = kb_rem.inline_keyboard[0]
    assert "Создать напоминание" in btn_conf.text
    assert btn_conf.callback_data == f"act:rem:conf:{conf_id}"
    assert "Отмена" in btn_rej.text
    assert btn_rej.callback_data == f"act:rem:rej:{conf_id}"

    # 3. draft_email_reply
    kb_drf = build_hitl_action_keyboard(conf_id, "draft_email_reply")
    assert len(kb_drf.inline_keyboard) == 1
    assert len(kb_drf.inline_keyboard[0]) == 2
    btn_conf, btn_rej = kb_drf.inline_keyboard[0]
    assert "Сохранить черновик" in btn_conf.text
    assert btn_conf.callback_data == f"act:drf:conf:{conf_id}"
    assert "Отмена" in btn_rej.text
    assert btn_rej.callback_data == f"act:drf:rej:{conf_id}"

    # 4. generic fallback
    kb_gen = build_hitl_action_keyboard(conf_id, "unknown_action")
    assert len(kb_gen.inline_keyboard) == 1
    assert len(kb_gen.inline_keyboard[0]) == 2
    btn_conf, btn_rej = kb_gen.inline_keyboard[0]
    assert btn_conf.callback_data == f"act:gen:conf:{conf_id}"
    assert btn_rej.callback_data == f"act:gen:rej:{conf_id}"


def test_format_hitl_proposal_card():
    """Verify proposal card text formatting and Russian confirmation question (D-01)."""
    # 1. Calendar
    cal_card = format_hitl_proposal_card(
        "create_calendar_event",
        {
            "title": "Консультация по физике",
            "date": "2026-10-10",
            "start_time": "18:30",
            "end_time": "20:00",
            "location": "Ауд. 13-05",
            "description": "Разбор типового расчета",
        },
    )
    assert "Подтверждение записи в Google Calendar" in cal_card
    assert "Консультация по физике" in cal_card
    assert "`2026-10-10`" in cal_card
    assert "`18:30` — `20:00`" in cal_card
    assert "Ауд. 13-05" in cal_card
    assert "Разбор типового расчета" in cal_card
    assert "Подтверждаете данное действие?" in cal_card

    # 2. Reminder
    rem_card = format_hitl_proposal_card(
        "create_reminder",
        {
            "text": "Проверить отчеты Новиковой",
            "due_date": "2026-10-14 12:00",
            "category": "academic",
            "target": "Ю.А. Новикова",
        },
    )
    assert "Подтверждение создания напоминания" in rem_card
    assert "Проверить отчеты Новиковой" in rem_card
    assert "`2026-10-14 12:00`" in rem_card
    assert "`academic`" in rem_card
    assert "Ю.А. Новикова" in rem_card
    assert "Подтверждаете данное действие?" in rem_card

    # 3. Email draft
    drf_card = format_hitl_proposal_card(
        "draft_email_reply",
        {
            "email_id": 42,
            "reply_text": "Уважаемая коллега, отчет готов.",
        },
    )
    assert "Подтверждение сохранения черновика ответа" in drf_card
    assert "#42" in drf_card
    assert "> Уважаемая коллега, отчет готов." in drf_card
    assert "Подтверждаете данное действие?" in drf_card


@pytest.mark.asyncio
async def test_secretary_dialog_creates_confirmation_and_sends_card(test_db: Database):
    """Verify that ActionProposal received from dialog_engine persists pending confirmation and sends interactive card."""
    user_id = 12345
    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    handler = EmailBotHandler(
        db=test_db,
        bot=mock_bot,
        allowed_user_id=user_id,
    )

    proposal = ActionProposal(
        action_type="create_calendar_event",
        params={
            "title": "Встреча с аспирантом",
            "date": "2026-10-12",
            "start_time": "15:00",
            "end_time": "16:00",
            "location": "Кафедра физики",
        },
    )

    handler.dialog_engine.answer_user_message = AsyncMock(
        return_value=("Я подготовил карточку для внесения в календарь.", [], proposal)
    )

    mock_msg = MagicMock()
    mock_msg.chat.id = user_id
    mock_msg.from_user.id = user_id

    await handler._handle_secretary_dialog(mock_msg, "Запиши встречу с аспирантом 12 октября в 15:00")

    # 1. Verify confirmation stored in DB
    store = handler._get_confirmation_store()
    pending = await store.list_pending()
    assert len(pending) == 1
    conf = pending[0]
    assert conf.action_type == "create_calendar_event"
    assert conf.payload["title"] == "Встреча с аспирантом"
    assert conf.channel == ConfirmationChannel.TELEGRAM
    assert conf.status == ConfirmationStatus.PENDING

    # 2. Verify message sent with buttons
    mock_bot.send_message.assert_called_once()
    call_kwargs = mock_bot.send_message.call_args.kwargs
    assert call_kwargs["chat_id"] == user_id
    assert "Подтверждение записи в Google Calendar" in call_kwargs["text"]
    assert "Встреча с аспирантом" in call_kwargs["text"]
    reply_markup = call_kwargs["reply_markup"]
    assert reply_markup is not None
    assert reply_markup.inline_keyboard[0][0].callback_data == f"act:cal:conf:{conf.id}"
    assert reply_markup.inline_keyboard[0][1].callback_data == f"act:cal:rej:{conf.id}"


@pytest.mark.asyncio
async def test_cb_act_calendar_confirm_and_reject(test_db: Database):
    """Verify confirming and rejecting create_calendar_event action via callback."""
    user_id = 12345
    mock_cal_client = MagicMock()
    mock_cal_client.create_event = AsyncMock(return_value="google_cal_ev_777")
    mock_cal_client.calendar_id = "primary"

    handler = EmailBotHandler(
        db=test_db,
        allowed_user_id=user_id,
        calendar_client=mock_cal_client,
    )
    store = handler._get_confirmation_store()

    # --- 1. Successful confirmation ---
    conf_confirm = await store.create_confirmation(
        persona_id="popov",
        action_type="create_calendar_event",
        payload={
            "title": "Научный семинар",
            "date": "2026-10-20",
            "start_time": "14:00",
            "end_time": "15:30",
            "location": "Ауд. 22-01",
        },
        channel=ConfirmationChannel.TELEGRAM,
    )

    cb_confirm = MagicMock(spec=CallbackQuery)
    cb_confirm.data = f"act:cal:conf:{conf_confirm.id}"
    cb_confirm.from_user = MagicMock()
    cb_confirm.from_user.id = user_id
    cb_confirm.answer = AsyncMock()
    cb_confirm.message = MagicMock(spec=Message)
    cb_confirm.message.edit_text = AsyncMock()

    await handler.cb_act_calendar_confirm(cb_confirm)

    # Calendar client invoked with Lesson
    mock_cal_client.create_event.assert_called_once()
    called_lesson = mock_cal_client.create_event.call_args[0][1]
    assert called_lesson.subject == "Научный семинар"
    assert str(called_lesson.date) == "2026-10-20"
    assert called_lesson.room == "Ауд. 22-01"

    # Status updated in store
    updated_conf = await store.get_confirmation(conf_confirm.id)
    assert updated_conf.status == ConfirmationStatus.CONFIRMED

    # Message edited with confirmation banner
    cb_confirm.message.edit_text.assert_called_once()
    edit_text = cb_confirm.message.edit_text.call_args[0][0]
    assert "✅ **Событие добавлено в Google Calendar**" in edit_text
    assert "Научный семинар" in edit_text
    cb_confirm.answer.assert_called_once_with("Подтверждено")

    # --- 2. Rejection ---
    conf_reject = await store.create_confirmation(
        persona_id="popov",
        action_type="create_calendar_event",
        payload={"title": "Отмененное совещание", "date": "2026-10-21", "start_time": "10:00", "end_time": "11:00"},
        channel=ConfirmationChannel.TELEGRAM,
    )

    cb_reject = MagicMock(spec=CallbackQuery)
    cb_reject.data = f"act:cal:rej:{conf_reject.id}"
    cb_reject.from_user = MagicMock()
    cb_reject.from_user.id = user_id
    cb_reject.answer = AsyncMock()
    cb_reject.message = MagicMock(spec=Message)
    cb_reject.message.edit_text = AsyncMock()

    mock_cal_client.create_event.reset_mock()
    await handler.cb_act_calendar_reject(cb_reject)

    # Calendar client MUST NOT be invoked upon reject
    mock_cal_client.create_event.assert_not_called()

    # Status updated to rejected
    rej_conf = await store.get_confirmation(conf_reject.id)
    assert rej_conf.status == ConfirmationStatus.REJECTED

    cb_reject.message.edit_text.assert_called_once()
    assert "❌ **Создание события отменено**" in cb_reject.message.edit_text.call_args[0][0]
    cb_reject.answer.assert_called_once_with("Отменено")


@pytest.mark.asyncio
async def test_cb_act_reminder_confirm_and_reject(test_db: Database):
    """Verify physical creation of reminder in SQLite only upon confirmation (ACT-03)."""
    user_id = 12345
    handler = EmailBotHandler(
        db=test_db,
        allowed_user_id=user_id,
    )
    store = handler._get_confirmation_store()

    # Record baseline reminders count (seeded by init_db)
    base_reminders = await test_db.list_reminders()
    base_count = len(base_reminders)

    # --- 1. Confirmation: Reminder MUST be written to DB ---
    conf_confirm = await store.create_confirmation(
        persona_id="popov",
        action_type="create_reminder",
        payload={
            "text": "Подготовить билеты к экзамену",
            "due_date": "2026-11-01 18:00",
            "category": "academic",
            "target": "Студенты ФВБ",
        },
        channel=ConfirmationChannel.TELEGRAM,
    )

    cb_confirm = MagicMock(spec=CallbackQuery)
    cb_confirm.data = f"act:rem:conf:{conf_confirm.id}"
    cb_confirm.from_user = MagicMock()
    cb_confirm.from_user.id = user_id
    cb_confirm.answer = AsyncMock()
    cb_confirm.message = MagicMock(spec=Message)
    cb_confirm.message.edit_text = AsyncMock()

    await handler.cb_act_reminder_confirm(cb_confirm)

    # Verify reminder created in DB
    reminders_after = await test_db.list_reminders()
    assert len(reminders_after) == base_count + 1
    new_r = [r for r in reminders_after if r["what"] == "Подготовить билеты к экзамену"][0]
    assert new_r["check_date"] == "2026-11-01 18:00"
    assert new_r["person"] == "Студенты ФВБ"
    assert "academic" in (new_r.get("context") or "")

    cb_confirm.message.edit_text.assert_called_once()
    assert "✅ **Напоминание успешно создано**" in cb_confirm.message.edit_text.call_args[0][0]

    # --- 2. Rejection: Reminder MUST NOT be written to DB ---
    conf_reject = await store.create_confirmation(
        persona_id="popov",
        action_type="create_reminder",
        payload={"text": "Несохраненное напоминание", "due_date": "2026-11-05"},
        channel=ConfirmationChannel.TELEGRAM,
    )

    cb_reject = MagicMock(spec=CallbackQuery)
    cb_reject.data = f"act:rem:rej:{conf_reject.id}"
    cb_reject.from_user = MagicMock()
    cb_reject.from_user.id = user_id
    cb_reject.answer = AsyncMock()
    cb_reject.message = MagicMock(spec=Message)
    cb_reject.message.edit_text = AsyncMock()

    await handler.cb_act_reminder_reject(cb_reject)

    # Reminders count remains base_count + 1
    reminders_final = await test_db.list_reminders()
    assert len(reminders_final) == base_count + 1

    cb_reject.message.edit_text.assert_called_once()
    assert "❌ **Создание напоминания отменено**" in cb_reject.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cb_act_draft_confirm_and_reject(test_db: Database):
    """Verify physical creation of email draft in SQLite only upon confirmation (ACT-03)."""
    user_id = 12345
    handler = EmailBotHandler(
        db=test_db,
        allowed_user_id=user_id,
    )
    store = handler._get_confirmation_store()

    # Seed an email
    await test_db.upsert_email_message(
        message_id="test-draft-email@guap.ru",
        account_id="guap",
        folder="INBOX",
        sender_name="Тестовый Отправитель",
        sender_email="test@guap.ru",
        recipients_json="[]",
        subject="Вопрос по лабораторной",
        date_sent=datetime.now(timezone.utc),
        body_plain="Подскажите срок сдачи.",
        body_html=None,
        snippet="Подскажите срок",
        has_attachments=False,
        attachments_json="[]",
        in_reply_to=None,
        references_text=None,
        thread_id="th-test-42",
        category="student",
        requires_action=True,
    )
    emails = await test_db.list_recent_emails(limit=1)
    email_id = emails[0]["id"]

    # --- 1. Confirmation: draft saved to DB ---
    conf_confirm = await store.create_confirmation(
        persona_id="popov",
        action_type="draft_email_reply",
        payload={
            "email_id": email_id,
            "reply_text": "Срок сдачи лабораторной — до конца текущей недели.",
        },
        channel=ConfirmationChannel.TELEGRAM,
    )

    cb_confirm = MagicMock(spec=CallbackQuery)
    cb_confirm.data = f"act:drf:conf:{conf_confirm.id}"
    cb_confirm.from_user = MagicMock()
    cb_confirm.from_user.id = user_id
    cb_confirm.answer = AsyncMock()
    cb_confirm.message = MagicMock(spec=Message)
    cb_confirm.message.edit_text = AsyncMock()

    await handler.cb_act_draft_confirm(cb_confirm)

    # Verify draft in DB
    async with test_db.connection() as conn:
        cursor = await conn.execute("SELECT * FROM email_drafts WHERE email_id = ?", (email_id,))
        row = await cursor.fetchone()
        assert row is not None
        assert row["draft_text"] == "Срок сдачи лабораторной — до конца текущей недели."
        assert row["status"] == "pending"

    cb_confirm.message.edit_text.assert_called_once()
    assert "✅ **Черновик ответа сохранен**" in cb_confirm.message.edit_text.call_args[0][0]

    # --- 2. Rejection: no draft created ---
    conf_reject = await store.create_confirmation(
        persona_id="popov",
        action_type="draft_email_reply",
        payload={
            "email_id": email_id,
            "reply_text": "Отклоненный проект черновика",
        },
        channel=ConfirmationChannel.TELEGRAM,
    )

    cb_reject = MagicMock(spec=CallbackQuery)
    cb_reject.data = f"act:drf:rej:{conf_reject.id}"
    cb_reject.from_user = MagicMock()
    cb_reject.from_user.id = user_id
    cb_reject.answer = AsyncMock()
    cb_reject.message = MagicMock(spec=Message)
    cb_reject.message.edit_text = AsyncMock()

    await handler.cb_act_draft_reject(cb_reject)

    # Still only 1 draft for email_id
    async with test_db.connection() as conn:
        cursor = await conn.execute("SELECT count(*) as cnt FROM email_drafts WHERE email_id = ?", (email_id,))
        row = await cursor.fetchone()
        assert row["cnt"] == 1

    cb_reject.message.edit_text.assert_called_once()
    assert "❌ **Создание черновика отменено**" in cb_reject.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cb_act_deduplication_and_protection(test_db: Database):
    """Verify double-click protection: second click answers alert and does not duplicate action (ACT-03, T-08-03)."""
    user_id = 12345
    handler = EmailBotHandler(
        db=test_db,
        allowed_user_id=user_id,
    )
    store = handler._get_confirmation_store()

    base_count = len(await test_db.list_reminders())

    conf = await store.create_confirmation(
        persona_id="popov",
        action_type="create_reminder",
        payload={"text": "Уникальное напоминание", "due_date": "2026-10-30"},
        channel=ConfirmationChannel.TELEGRAM,
    )

    cb1 = MagicMock(spec=CallbackQuery)
    cb1.data = f"act:rem:conf:{conf.id}"
    cb1.from_user = MagicMock()
    cb1.from_user.id = user_id
    cb1.answer = AsyncMock()
    cb1.message = MagicMock(spec=Message)
    cb1.message.edit_text = AsyncMock()

    # First click: success
    await handler.cb_act_reminder_confirm(cb1)
    cb1.answer.assert_called_once_with("Подтверждено")

    reminders = await test_db.list_reminders()
    assert len(reminders) == base_count + 1

    # Second click (double submit race): blocked by ConfirmationStore status check
    cb2 = MagicMock(spec=CallbackQuery)
    cb2.data = f"act:rem:conf:{conf.id}"
    cb2.from_user = MagicMock()
    cb2.from_user.id = user_id
    cb2.answer = AsyncMock()
    cb2.message = MagicMock(spec=Message)
    cb2.message.edit_text = AsyncMock()
    cb2.message.edit_reply_markup = AsyncMock()

    await handler.cb_act_reminder_confirm(cb2)

    cb2.answer.assert_called_once_with("Запрос уже обработан или истек", show_alert=True)
    cb2.message.edit_text.assert_not_called()

    # Database still has exactly base_count + 1 reminders (no duplication)
    reminders_after_double_click = await test_db.list_reminders()
    assert len(reminders_after_double_click) == base_count + 1

    # Attempting to reject already confirmed action also blocked
    cb_rej = MagicMock(spec=CallbackQuery)
    cb_rej.data = f"act:rem:rej:{conf.id}"
    cb_rej.from_user = MagicMock()
    cb_rej.from_user.id = user_id
    cb_rej.answer = AsyncMock()
    cb_rej.message = MagicMock(spec=Message)
    cb_rej.message.edit_text = AsyncMock()

    await handler.cb_act_reminder_reject(cb_rej)
    cb_rej.answer.assert_called_once_with("Запрос уже обработан или истек", show_alert=True)
    cb_rej.message.edit_text.assert_not_called()


@pytest.mark.asyncio
async def test_cb_act_unauthorized_user_blocked(test_db: Database):
    """Verify that unauthorized user cannot confirm or reject actions."""
    owner_id = 12345
    intruder_id = 99999
    handler = EmailBotHandler(
        db=test_db,
        allowed_user_id=owner_id,
    )
    store = handler._get_confirmation_store()

    base_count = len(await test_db.list_reminders())

    conf = await store.create_confirmation(
        persona_id="popov",
        action_type="create_reminder",
        payload={"text": "Секретное напоминание", "due_date": "2026-10-30"},
        channel=ConfirmationChannel.TELEGRAM,
    )

    cb = MagicMock(spec=CallbackQuery)
    cb.data = f"act:rem:conf:{conf.id}"
    cb.from_user = MagicMock()
    cb.from_user.id = intruder_id
    cb.answer = AsyncMock()
    cb.message = MagicMock(spec=Message)
    cb.message.edit_text = AsyncMock()

    await handler.cb_act_reminder_confirm(cb)

    cb.answer.assert_called_once_with("⛔ Доступ запрещен", show_alert=True)
    cb.message.edit_text.assert_not_called()

    # Action remains pending
    conf_check = await store.get_confirmation(conf.id)
    assert conf_check.status == ConfirmationStatus.PENDING

    # Database untouched
    reminders = await test_db.list_reminders()
    assert len(reminders) == base_count


@pytest.mark.asyncio
async def test_cb_act_expired_action_blocked(test_db: Database):
    """Verify that expired action cannot be executed (T-08-04)."""
    user_id = 12345
    handler = EmailBotHandler(
        db=test_db,
        allowed_user_id=user_id,
    )
    store = handler._get_confirmation_store()

    base_count = len(await test_db.list_reminders())

    # Create already expired confirmation (ttl_minutes = -5)
    conf = await store.create_confirmation(
        persona_id="popov",
        action_type="create_reminder",
        payload={"text": "Просроченное напоминание", "due_date": "2026-10-30"},
        channel=ConfirmationChannel.TELEGRAM,
        ttl_minutes=-5,
    )

    cb = MagicMock(spec=CallbackQuery)
    cb.data = f"act:rem:conf:{conf.id}"
    cb.from_user = MagicMock()
    cb.from_user.id = user_id
    cb.answer = AsyncMock()
    cb.message = MagicMock(spec=Message)
    cb.message.edit_text = AsyncMock()

    await handler.cb_act_reminder_confirm(cb)

    cb.answer.assert_called_once_with("Запрос уже обработан или истек", show_alert=True)

    # Reminders not created
    reminders = await test_db.list_reminders()
    assert len(reminders) == base_count
