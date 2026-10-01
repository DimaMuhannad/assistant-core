import pytest
from datetime import datetime, timedelta, timezone
from src.collector.email_collector import (
    extract_deadline,
    calculate_relevance,
    EmailCollector,
)
from src.storage.db import Database


def test_extract_deadline():
    # Relative / specific date formats
    d1 = extract_deadline("Прошу Вас в ближайшее время (до 24.09.26 ) предоставить мне на почту")
    assert d1 is not None
    assert d1.year == 2026 and d1.month == 9 and d1.day == 24

    d2 = extract_deadline("Эффективные контракты все должны быть отправлены до 25.08")
    assert d2 is not None
    assert d2.year == 2026 and d2.month == 8 and d2.day == 25

    d3 = extract_deadline("Сдать отчет к 15 октября 2026 года")
    assert d3 is not None
    assert d3.year == 2026 and d3.month == 10 and d3.day == 15

    d4 = extract_deadline("Письмо без каких-либо сроков и дат")
    assert d4 is None


def test_calculate_relevance():
    now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Past deadline -> expired
    past_dl = datetime(2026, 9, 24, 23, 59, 59, tzinfo=timezone.utc)
    score, is_expired = calculate_relevance(now - timedelta(days=7), past_dl, now=now)
    assert is_expired is True
    assert score == 0.05

    # 2. Future urgent deadline (in 2 days)
    future_dl = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
    score, is_expired = calculate_relevance(now - timedelta(days=1), future_dl, now=now)
    assert is_expired is False
    assert score >= 1.3

    # 3. No deadline: fresh (< 1 day)
    score, is_expired = calculate_relevance(now - timedelta(hours=5), None, now=now)
    assert is_expired is False
    assert score == 1.0

    # 4. No deadline: 5 days old
    score, is_expired = calculate_relevance(now - timedelta(days=5), None, now=now)
    assert is_expired is False
    assert score == 0.75

    # 5. No deadline: 40 days old -> expired
    score, is_expired = calculate_relevance(now - timedelta(days=40), None, now=now)
    assert is_expired is True
    assert score == 0.05


@pytest.mark.asyncio
async def test_reply_reconciliation_and_actionable_queue():
    db = Database(":memory:")
    await db.init_db()

    now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
    user_emails = ["scipopov@mail.ru", "scipopov@guap.ru"]

    # 1. Student email A: unanswered, recent (2 days ago)
    await db.upsert_email_message(
        message_id="msg-student-1",
        account_id="mailru",
        folder="INBOX",
        sender_name="Студент 1",
        sender_email="student1@stud.guap.ru",
        recipients_json='["scipopov@mail.ru"]',
        subject="Вопрос по лабораторной работе 5",
        date_sent=now - timedelta(days=2),
        body_plain="Подскажите, как оформлять графики?",
        body_html=None,
        snippet="Подскажите, как оформлять графики?",
        has_attachments=False,
        attachments_json=None,
        in_reply_to=None,
        references_text=None,
        thread_id="th-lab5-stud1",
        category="guap_student",
        is_noise=False,
        requires_action=True,
        is_answered=False,
        relevance_score=0.9,
    )

    # 2. Student email B: answered via IMAP flag \Answered
    await db.upsert_email_message(
        message_id="msg-student-2",
        account_id="mailru",
        folder="INBOX",
        sender_name="Студент 2",
        sender_email="student2@stud.guap.ru",
        recipients_json='["scipopov@mail.ru"]',
        subject="Уточнение по защите",
        date_sent=now - timedelta(days=10),
        body_plain="Когда можно прийти на защиту?",
        body_html=None,
        snippet="Когда можно прийти на защиту?",
        has_attachments=False,
        attachments_json=None,
        in_reply_to=None,
        references_text=None,
        thread_id="th-defense-stud2",
        category="guap_student",
        is_noise=False,
        requires_action=True,
        is_answered=True,
        flags_json='["\\\\Seen", "\\\\Answered"]',
        relevance_score=0.5,
    )

    # 3. Department email C: expired deadline (passed 5 days ago)
    past_dl = now - timedelta(days=5)
    await db.upsert_email_message(
        message_id="msg-dept-3",
        account_id="mailru",
        folder="INBOX",
        sender_name="Кафедра",
        sender_email="nov-jliana@yandex.ru",
        recipients_json='["scipopov@mail.ru"]',
        subject="План работы (до 24.09.26)",
        date_sent=now - timedelta(days=10),
        body_plain="Прислать до 24 сентября",
        body_html=None,
        snippet="Прислать до 24 сентября",
        has_attachments=False,
        attachments_json=None,
        in_reply_to=None,
        references_text=None,
        thread_id="th-plan-2026",
        category="guap_dept",
        is_noise=False,
        requires_action=True,
        is_answered=False,
        is_expired=True,
        deadline_at=past_dl,
        relevance_score=0.05,
    )

    # 4. Student email D: answered via Dmitry's outgoing reply
    await db.upsert_email_message(
        message_id="msg-student-4",
        account_id="guap",
        folder="INBOX",
        sender_name="Студент 4",
        sender_email="student4@stud.guap.ru",
        recipients_json='["scipopov@guap.ru"]',
        subject="Вопрос по коллоквиуму",
        date_sent=now - timedelta(days=3),
        body_plain="Будут ли вопросы по термодинамике?",
        body_html=None,
        snippet="Будут ли вопросы по термодинамике?",
        has_attachments=False,
        attachments_json=None,
        in_reply_to=None,
        references_text=None,
        thread_id="th-colloquium",
        category="guap_student",
        is_noise=False,
        requires_action=True,
        is_answered=False,
        relevance_score=0.9,
    )

    # Outgoing reply from Dmitry to Student 4
    await db.upsert_email_message(
        message_id="msg-reply-by-dmitry",
        account_id="guap",
        folder="Sent",
        sender_name="Дмитрий Попов",
        sender_email="scipopov@guap.ru",
        recipients_json='["student4@stud.guap.ru"]',
        subject="Re: Вопрос по коллоквиуму",
        date_sent=now - timedelta(days=2, hours=20),
        body_plain="Да, термодинамика включена.",
        body_html=None,
        snippet="Да, термодинамика включена.",
        has_attachments=False,
        attachments_json=None,
        in_reply_to="msg-student-4",
        references_text="msg-student-4",
        thread_id="th-colloquium",
        category="outgoing",
        is_noise=False,
        requires_action=False,
        is_answered=True,
    )

    # Run reconciliation
    rec_stats = await db.reconcile_replies_and_threads(user_emails)
    assert rec_stats["answered_by_reply"] >= 1

    # Check actionable queue: should ONLY contain Student email A!
    actionable = await db.list_actionable_emails()
    assert len(actionable) == 1
    assert actionable[0]["message_id"] == "msg-student-1"
    assert actionable[0]["sender_name"] == "Студент 1"

    # Verify that Student 4 is marked answered
    async with db.connection() as conn:
        cursor = await conn.execute("SELECT is_answered, reply_message_id FROM email_messages WHERE message_id = 'msg-student-4'")
        row = await cursor.fetchone()
        assert row["is_answered"] == 1
        assert row["reply_message_id"] == "msg-reply-by-dmitry"

        # Verify thread status
        c2 = await conn.execute("SELECT status FROM email_threads WHERE thread_id = 'th-colloquium'")
        t_row = await c2.fetchone()
        assert t_row["status"] == "answered"

    await db.close()


def test_determine_message_classification_self_forwards_and_notes():
    collector = EmailCollector()
    now = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)

    # 1. Genuine outgoing in 'Отправленные' -> outgoing
    c1 = collector.determine_message_classification(
        sender_email="scipopov@mail.ru",
        subject="Ответ студенту",
        snippet="Занятие перенесено",
        folder_or_labels="Отправленные",
        date_sent=now,
    )
    assert c1["category"] == "outgoing"
    assert c1["requires_action"] is False

    # 2. Forwarded student email in INBOX/ToMyself from user's email -> guap_student
    c2 = collector.determine_message_classification(
        sender_email="scipopov@mail.ru",
        subject="Fwd: Вопрос от старосты гр. 2815 по лабораторным работам",
        snippet="Студенты просят продлить дедлайн до 05.10",
        folder_or_labels="INBOX/ToMyself",
        date_sent=now,
    )
    assert c2["category"] == "guap_student"
    assert c2["is_noise"] is False
    assert c2["requires_action"] is True

    # 3. Personal note in INBOX from user's email -> personal, not noise
    c3 = collector.determine_message_classification(
        sender_email="scipopov@mail.ru",
        subject="Заметка по прибору",
        snippet="Проверить юстировку лазера",
        folder_or_labels="INBOX",
        date_sent=now,
    )
    assert c3["category"] == "personal"
    assert c3["is_noise"] is False
    assert c3["requires_action"] is False


@pytest.mark.asyncio
async def test_mark_email_delivery_failed_and_actionable_suppression():
    db = Database(":memory:")
    await db.init_db()

    now = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)
    await db.upsert_email_message(
        message_id="msg-failed-recipient",
        account_id="mailru",
        folder="INBOX",
        sender_name="Неизвестный Студент",
        sender_email="nonexistent@stud.guap.ru",
        recipients_json='["scipopov@mail.ru"]',
        subject="Вопрос по допуску",
        date_sent=now,
        body_plain="Прошу допуск",
        body_html=None,
        snippet="Прошу допуск",
        has_attachments=False,
        attachments_json=None,
        in_reply_to=None,
        references_text=None,
        thread_id="th-failed-recip",
        category="guap_student",
        is_noise=False,
        requires_action=True,
        is_answered=False,
        relevance_score=1.0,
    )

    actionable_before = await db.list_actionable_emails()
    assert len(actionable_before) == 1
    email_id = actionable_before[0]["id"]

    # Mark delivery failed (e.g. SMTP 550)
    await db.mark_email_delivery_failed(email_id, reason="550 Recipient Refused")

    actionable_after = await db.list_actionable_emails()
    assert len(actionable_after) == 0

    async with db.connection() as conn:
        cursor = await conn.execute("SELECT delivery_failed, delivery_error, requires_action FROM email_messages WHERE id = ?", (email_id,))
        row = await cursor.fetchone()
        assert row["delivery_failed"] == 1
        assert "550 Recipient Refused" in row["delivery_error"]
        assert row["requires_action"] == 0

    await db.close()


@pytest.mark.asyncio
async def test_db_existing_message_ids_and_flags():
    db = Database(":memory:")
    await db.init_db()

    now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
    await db.upsert_email_message(
        message_id="mid-cached-1",
        account_id="guap",
        folder="INBOX",
        sender_name="Преподаватель",
        sender_email="teacher@guap.ru",
        recipients_json='["scipopov@guap.ru"]',
        subject="Расписание пересдач",
        date_sent=now,
        body_plain="Расписание во вложении",
        body_html=None,
        snippet="Расписание во вложении",
        has_attachments=False,
        attachments_json=None,
        in_reply_to=None,
        references_text=None,
        thread_id="th-resched",
        category="guap_dept",
        is_read=False,
        is_answered=False,
    )

    # Check get_existing_message_ids
    existing = await db.get_existing_message_ids(["mid-cached-1", "mid-nonexistent-2"])
    assert "mid-cached-1" in existing
    assert "mid-nonexistent-2" not in existing

    # Check update_email_flags
    await db.update_email_flags("mid-cached-1", '["\\\\Seen", "\\\\Answered"]', is_read=True, is_answered=True)

    async with db.connection() as conn:
        cursor = await conn.execute("SELECT is_read, is_answered, flags_json FROM email_messages WHERE message_id = 'mid-cached-1'")
        row = await cursor.fetchone()
        assert row["is_read"] == 1
        assert row["is_answered"] == 1
        assert "\\\\Answered" in row["flags_json"]

    await db.close()
