import pytest
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.storage.db import Database
from src.sender.email_sender import EmailSender
from src.brain.reply_generator import ReplyGenerator
from src.notifier.telegram import (
    TelegramNotifier,
    build_email_action_keyboard,
    build_draft_action_keyboard,
)
from src.notifier.bot_handler import EmailBotHandler


@pytest.fixture
async def in_memory_db():
    db = Database(":memory:")
    await db.init_db()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_email_drafts_db_crud(in_memory_db: Database):
    # 1. Insert test email message
    await in_memory_db.upsert_email_message(
        message_id="msg-101@guap.ru",
        account_id="mailru",
        folder="INBOX",
        sender_name="Мария Марьяшина",
        sender_email="shineshane8@gmail.com",
        recipients_json='["scipopov@mail.ru"]',
        subject="Вопрос по лабораторной",
        date_sent=datetime.now(timezone.utc),
        body_plain="Подскажите, делать по графику или по формуле?",
        body_html=None,
        snippet="Подскажите, делать...",
        has_attachments=False,
        attachments_json=None,
        in_reply_to=None,
        references_text=None,
        thread_id="th-lab5",
        category="guap_student",
        requires_action=True,
    )

    # Find the inserted email
    email_row = await in_memory_db.get_email_by_id(1)
    assert email_row is not None
    assert email_row["sender_name"] == "Мария Марьяшина"
    assert email_row["is_answered"] == 0

    # 2. Create draft
    draft_id = await in_memory_db.create_email_draft(1, "Здравствуйте, Мария! Делайте по формулам.")
    assert draft_id == 1

    # 3. Retrieve draft
    draft = await in_memory_db.get_email_draft(draft_id)
    assert draft is not None
    assert draft["draft_text"] == "Здравствуйте, Мария! Делайте по формулам."
    assert draft["draft_status"] == "pending"
    assert draft["sender_email"] == "shineshane8@gmail.com"

    # 4. Update draft text and status
    updated = await in_memory_db.update_email_draft(draft_id, draft_text="Новый текст", status="sent")
    assert updated is True

    draft_after = await in_memory_db.get_email_draft(draft_id)
    assert draft_after["draft_text"] == "Новый текст"
    assert draft_after["draft_status"] == "sent"

    # 5. Mark email as answered
    marked = await in_memory_db.mark_email_as_answered(1, reply_message_id="reply-101", user_email="scipopov@mail.ru")
    assert marked is True

    email_after = await in_memory_db.get_email_by_id(1)
    assert email_after["is_answered"] == 1
    assert email_after["requires_action"] == 0
    assert email_after["reply_message_id"] == "reply-101"

    # 6. Verify thread messages
    thread_msgs = await in_memory_db.get_thread_messages("th-lab5")
    assert len(thread_msgs) == 1
    assert thread_msgs[0]["subject"] == "Вопрос по лабораторной"


def test_keyboards_structure():
    email_kb = build_email_action_keyboard(97)
    buttons = email_kb.inline_keyboard
    assert len(buttons) == 3
    assert buttons[0][0].text == "💡 Предложить ответ"
    assert buttons[0][0].callback_data == "em:sug:97"
    assert buttons[1][0].text == "✏️ Написать ответ"
    assert buttons[1][0].callback_data == "em:wr:97"
    assert buttons[2][0].text == "📜 Посмотреть всю переписку"
    assert buttons[2][0].callback_data == "em:th:97"

    draft_kb = build_draft_action_keyboard(42)
    draft_buttons = draft_kb.inline_keyboard
    assert len(draft_buttons) == 2
    assert draft_buttons[0][0].text == "✅ Отправить"
    assert draft_buttons[0][0].callback_data == "dr:snd:42"
    assert draft_buttons[0][1].text == "✏️ Исправить"
    assert draft_buttons[0][1].callback_data == "dr:edt:42"
    assert draft_buttons[1][0].text == "❌ Отменить"
    assert draft_buttons[1][0].callback_data == "dr:cnc:42"


def test_email_sender_resolve_config():
    sender = EmailSender()
    
    # Mail.ru test
    h, p, u, pwd, from_hdr = sender._resolve_smtp_config("mailru", "student@mail.ru")
    assert "smtp.mail.ru" in h
    assert p == 587
    assert "Дмитрий Александрович Попов" in from_hdr

    # GUAP test
    h_g, p_g, u_g, pwd_g, from_hdr_g = sender._resolve_smtp_config("guap", "rectorat@guap.ru")
    assert "guap.ru" in h_g
    assert p_g == 587


@pytest.mark.asyncio
async def test_reply_generator_fallback():
    gen = ReplyGenerator(api_key="")
    assert not gen.is_configured
    reply = await gen.generate_reply({
        "sender_name": "Мария",
        "sender_email": "m@stud.guap.ru",
        "subject": "Лабораторная",
        "body_plain": "Вопрос",
        "category": "guap_student",
    })
    assert "Здравствуйте, Мария!" in reply
    assert "Попов" in reply
    assert "Доцент кафедры физики ГУАП" in reply


@pytest.mark.asyncio
async def test_bot_handler_authorization(in_memory_db: Database):
    notifier = TelegramNotifier(bot_token="fake:token", user_id="12345")
    handler = EmailBotHandler(
        db=in_memory_db,
        reply_generator=ReplyGenerator(api_key=""),
        email_sender=EmailSender(),
        notifier=notifier,
        allowed_user_id=12345,
    )

    assert handler._is_authorized(12345) is True
    assert handler._is_authorized(99999) is False


@pytest.mark.asyncio
async def test_daily_email_stats(in_memory_db: Database):
    from datetime import date
    now = datetime.now(timezone.utc)
    # 1. Answered email
    e1_id = await in_memory_db.upsert_email_message(
        message_id="msg-ans-1@guap.ru",
        account_id="mailru",
        folder="INBOX",
        sender_name="Студент 1",
        sender_email="stud1@guap.ru",
        recipients_json='["scipopov@mail.ru"]',
        subject="Отчет готов",
        date_sent=now,
        body_plain="Отчет прикреплен",
        body_html=None,
        snippet="Отчет",
        has_attachments=False,
        attachments_json=None,
        in_reply_to=None,
        references_text=None,
        thread_id="th-ans-1",
        category="guap_student",
        requires_action=True,
    )
    d1_id = await in_memory_db.create_email_draft(e1_id, "Спасибо, принято.")
    await in_memory_db.update_email_draft(d1_id, status="sent")
    await in_memory_db.mark_email_as_answered(e1_id)

    # 2. Pending email
    await in_memory_db.upsert_email_message(
        message_id="msg-pend-1@guap.ru",
        account_id="mailru",
        folder="INBOX",
        sender_name="Студент 2",
        sender_email="stud2@guap.ru",
        recipients_json='["scipopov@mail.ru"]',
        subject="Вопрос по теории",
        date_sent=now,
        body_plain="Поясните формулу",
        body_html=None,
        snippet="Вопрос",
        has_attachments=False,
        attachments_json=None,
        in_reply_to=None,
        references_text=None,
        thread_id="th-pend-1",
        category="guap_student",
        requires_action=True,
    )

    stats = await in_memory_db.get_daily_email_stats(now.date())
    assert len(stats["bot_answered"]) == 1
    assert stats["bot_answered"][0]["subject"] == "Отчет готов"
    assert len(stats["pending_actionable"]) == 1


@pytest.mark.asyncio
async def test_cleanup_email_session(in_memory_db: Database):
    mock_bot = AsyncMock()
    notifier = TelegramNotifier(bot_token="123456:FAKE", user_id="12345")
    handler = EmailBotHandler(
        db=in_memory_db,
        reply_generator=ReplyGenerator(api_key=""),
        email_sender=EmailSender(),
        notifier=notifier,
        bot=mock_bot,
        allowed_user_id=12345,
    )
    handler.session_messages[99] = {1001, 1002}
    await handler.cleanup_email_session(chat_id=12345, email_id=99)
    assert mock_bot.delete_message.await_count == 2
    assert 99 not in handler.session_messages


@pytest.mark.asyncio
async def test_evening_digest_fallback():
    from datetime import date, time
    from src.brain.summarizer import GeminiSummarizer
    from src.models.schedule import Lesson, LessonType

    summarizer = GeminiSummarizer(api_key="")
    test_lessons = [
        Lesson(
            subject="Физика",
            lesson_type=LessonType.PRACTICE,
            date=date(2026, 9, 30),
            start_time=time(9, 30),
            end_time=time(11, 0),
            room="31-04а",
            building="Гастелло 15",
            teacher="Попов Д.А.",
            group="м431к",
        )
    ]
    email_stats = {
        "bot_answered": [
            {
                "sender_name": "Мария Марьяшина",
                "sender_email": "shineshane8@gmail.com",
                "subject": "Вопрос",
                "category": "guap_student",
                "updated_at": "2026-09-29T10:00:00",
            }
        ],
        "pending_actionable": [],
    }

    digest = await summarizer.generate_evening_digest(
        target_date=date(2026, 9, 29),
        email_stats=email_stats,
        tomorrow_date=date(2026, 9, 30),
        tomorrow_lessons=test_lessons,
    )

    assert "Вечерний дайджест" in digest
    assert "Почтовый щит: статистика за день" in digest
    assert "Мария Марьяшина" in digest
    assert "Расписание на завтра" in digest
    assert "Физика" in digest

