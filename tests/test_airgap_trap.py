"""Тесты строгого Air-Gap и изоляции LLM-контекста для почты restricted_nda (ISO-02).

Проверяют:
1. Блокировку автогенерации ответов в ReplyGenerator с AirGapViolationError (D-07).
2. Маскирование тел и вложений NDA-писем в SecretaryDialogEngine и GeminiSummarizer (D-06).
3. Отсутствие конфиденциальных данных в промптах к Google Gemini через SpyGenAIClient (D-08).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.core.exceptions import AirGapViolationError
from src.brain.reply_generator import ReplyGenerator
from src.brain.secretary_dialog import SecretaryDialogEngine
from src.brain.summarizer import GeminiSummarizer
from src.security.airgap import is_nda_email, mask_nda_email_data, NDA_MASK_MARKER
from src.storage.db import Database


class SpyGenAIClient:
    """Шпион-ловушка вместо genai.Client для проверки отсутствия NDA-данных в LLM (D-08)."""

    def __init__(self, forbidden_patterns: list[str] | None = None):
        self.recorded_calls: list[dict[str, Any]] = []
        self.forbidden_patterns = forbidden_patterns or [
            "mock_nda_secret_token",
            "mock_proprietary_token",
            "CONFIDENTIAL: Параметры оптического датчика",
            "CONFIDENTIAL: Чертежи и калибровка",
        ]

        # Подготовка mock для client.aio.models.generate_content
        self.aio = MagicMock()
        self.aio.models = MagicMock()
        self.aio.models.generate_content = AsyncMock(side_effect=self._mock_generate_content)

    async def _mock_generate_content(self, model: str, contents: Any, config: Any = None) -> Any:
        contents_str = str(contents)
        sys_inst = str(getattr(config, "system_instruction", ""))

        for forbidden in self.forbidden_patterns:
            assert forbidden not in contents_str, f"УТЕЧКА В LLM: Секретный токен '{forbidden}' найден в contents!"
            assert forbidden not in sys_inst, f"УТЕЧКА В LLM: Секретный токен '{forbidden}' найден в system_instruction!"

        self.recorded_calls.append({
            "model": model,
            "contents": contents_str,
            "system_instruction": sys_inst,
            "config": config,
        })

        mock_resp = MagicMock()
        mock_resp.text = "Mock LLM Response: все проверено."
        return mock_resp


@pytest.fixture
def nda_email_by_workspace():
    return {
        "id": "email-nda-001",
        "workspace_id": "tydex-optics",
        "sender_name": "ООО Тидекс Партнер",
        "sender_email": "partner@tydex.example",
        "subject": "Согласование закрытого технического задания",
        "body_plain": "CONFIDENTIAL: Параметры оптического датчика mock_nda_secret_token строго конфиденциальны.",
        "snippet": "CONFIDENTIAL: Параметры оптического датчика...",
        "attachments": [{"filename": "nda_spec.pdf", "size": 10240}],
    }


@pytest.fixture
def nda_email_by_account():
    return {
        "id": "email-nda-002",
        "account_id": "tydex-optics",
        "sender_name": "Инженер Тидекс",
        "sender_email": "dev@tydex.example",
        "subject": "Спецификация спектрометра",
        "body_plain": "CONFIDENTIAL: Чертежи и калибровка mock_proprietary_token",
        "snippet": "CONFIDENTIAL: Чертежи...",
        "attachments": ["calibration.bin"],
    }


@pytest.fixture
def regular_academic_email():
    return {
        "id": "email-guap-001",
        "workspace_id": "guap-physics",
        "sender_name": "Иван Студент",
        "sender_email": "student@guap.ru",
        "subject": "Вопрос по лабораторной работе №2",
        "body_plain": "Здравствуйте, Дмитрий Александрович! Проверьте, пожалуйста, отчет по оптике.",
        "snippet": "Здравствуйте, Дмитрий Александрович! Проверьте, пожалуйста...",
        "attachments": [],
    }


def test_is_nda_email_detection(nda_email_by_workspace, nda_email_by_account, regular_academic_email):
    assert is_nda_email(nda_email_by_workspace) is True
    assert is_nda_email(nda_email_by_account) is True
    assert is_nda_email(regular_academic_email) is False


def test_mask_nda_email_data(nda_email_by_workspace):
    masked = mask_nda_email_data(nda_email_by_workspace)
    assert masked["body_plain"] == NDA_MASK_MARKER
    assert masked["snippet"] == NDA_MASK_MARKER
    assert masked["body_html"] == ""
    assert masked["attachments"] == []
    assert "mock_nda_secret_token" not in masked["body_plain"]
    # Исходный словарь не должен быть мутирован
    assert "mock_nda_secret_token" in nda_email_by_workspace["body_plain"]


@pytest.mark.asyncio
async def test_reply_generator_blocked_for_nda(nda_email_by_workspace, nda_email_by_account):
    gen = ReplyGenerator(api_key="mock_key")

    with pytest.raises(AirGapViolationError) as exc_info:
        await gen.generate_reply(nda_email_by_workspace)
    assert "Автогенерация ответа запрещена политикой Air-Gap" in str(exc_info.value)

    with pytest.raises(AirGapViolationError) as exc_info2:
        await gen.generate_reply(nda_email_by_account)
    assert "Автогенерация ответа запрещена политикой Air-Gap" in str(exc_info2.value)


@pytest.mark.asyncio
async def test_secretary_overview_masks_nda_emails():
    db = Database(db_path=":memory:")
    await db.init_db()

    now = datetime.now(timezone.utc)

    # 1. Вставляем NDA-письмо
    await db.upsert_email_message(
        message_id="msg-nda-100",
        account_id="tydex-optics",
        folder="INBOX",
        sender_name="Сектор приборов",
        sender_email="device@tydex.example",
        recipients_json='["popov@tydex.example"]',
        subject="Срочный отчет по спектрометру",
        date_sent=now,
        body_plain="CONFIDENTIAL: Параметры оптического датчика mock_nda_secret_token строго конфиденциальны.",
        body_html="",
        snippet="CONFIDENTIAL: Параметры оптического датчика...",
        has_attachments=False,
        attachments_json=None,
        in_reply_to=None,
        references_text=None,
        thread_id="thread-nda-1",
        category="tydex_work",
        requires_action=True,
    )

    # 2. Вставляем обычное академическое письмо
    await db.upsert_email_message(
        message_id="msg-guap-200",
        account_id="guap-physics",
        folder="INBOX",
        sender_name="Алексей Смирнов",
        sender_email="smirnov@guap.ru",
        recipients_json='["popov@guap.ru"]',
        subject="Лабораторная работа по лазерам",
        date_sent=now,
        body_plain="Дмитрий Александрович, направляю титульный лист работы №4.",
        body_html="",
        snippet="Дмитрий Александрович, направляю титульный лист...",
        has_attachments=False,
        attachments_json=None,
        in_reply_to=None,
        references_text=None,
        thread_id="thread-guap-2",
        category="guap_student",
        requires_action=True,
    )

    engine = SecretaryDialogEngine(db=db, api_key="mock_key")
    overview = await engine._get_email_overview()

    # Проверяем маскирование NDA
    assert NDA_MASK_MARKER in overview
    assert "mock_nda_secret_token" not in overview
    assert "CONFIDENTIAL" not in overview

    # Проверяем, что академическое письмо НЕ замаскировано
    assert "Дмитрий Александрович, направляю титульный лист..." in overview
    assert "Алексей Смирнов" in overview

    await db.close()


@pytest.mark.asyncio
async def test_secretary_search_masks_nda_emails():
    db = Database(db_path=":memory:")
    await db.init_db()

    now = datetime.now(timezone.utc)
    await db.upsert_email_message(
        message_id="msg-nda-300",
        account_id="tydex-optics",
        folder="INBOX",
        sender_name="Руководство Тидекс",
        sender_email="boss@tydex.example",
        recipients_json='["popov@tydex.example"]',
        subject="План НИОКР оптика",
        date_sent=now,
        body_plain="CONFIDENTIAL: Чертежи и калибровка mock_proprietary_token в закрытом доступе.",
        body_html="",
        snippet="CONFIDENTIAL: Чертежи...",
        has_attachments=False,
        attachments_json=None,
        in_reply_to=None,
        references_text=None,
        thread_id="thread-nda-3",
        category="tydex_work",
        requires_action=True,
    )

    engine = SecretaryDialogEngine(db=db, api_key="mock_key")
    search_res = await engine._search_email_context("оптика")

    assert NDA_MASK_MARKER in search_res
    assert "mock_proprietary_token" not in search_res
    assert "CONFIDENTIAL" not in search_res

    await db.close()


@pytest.mark.asyncio
async def test_secretary_dialog_full_flow_with_spy_trap():
    db = Database(db_path=":memory:")
    await db.init_db()

    now = datetime.now(timezone.utc)
    await db.upsert_email_message(
        message_id="msg-nda-400",
        account_id="tydex-optics",
        folder="INBOX",
        sender_name="Конструктор Тидекс",
        sender_email="tech@tydex.example",
        recipients_json='["popov@tydex.example"]',
        subject="Корпоративная тайна",
        date_sent=now,
        body_plain="CONFIDENTIAL: Параметры оптического датчика mock_nda_secret_token",
        body_html="",
        snippet="CONFIDENTIAL: Параметры...",
        has_attachments=False,
        attachments_json=None,
        in_reply_to=None,
        references_text=None,
        thread_id="thread-nda-4",
        category="tydex_work",
        requires_action=True,
    )

    spy_client = SpyGenAIClient()
    engine = SecretaryDialogEngine(db=db, api_key="mock_key")
    engine._client = spy_client

    ans = await engine.answer_user_message(user_id=123, message_text="Какие у меня неотвеченные письма?")
    assert len(spy_client.recorded_calls) >= 1

    for call in spy_client.recorded_calls:
        contents = call["contents"]
        assert "mock_nda_secret_token" not in contents
        assert "CONFIDENTIAL" not in contents
        assert NDA_MASK_MARKER in contents

    await db.close()


@pytest.mark.asyncio
async def test_summarizer_masks_nda_emails(nda_email_by_workspace, nda_email_by_account, regular_academic_email):
    spy_client = SpyGenAIClient()
    summarizer = GeminiSummarizer(api_key="mock_key")
    summarizer._client = spy_client

    # 1. Проверка Morning Brief
    await summarizer.generate_morning_brief(
        target_date=date.today(),
        lessons=[],
        action_items=[],
        actionable_emails=[nda_email_by_workspace, regular_academic_email],
    )
    assert len(spy_client.recorded_calls) >= 1

    # 2. Проверка Evening Digest
    await summarizer.generate_evening_digest(
        target_date=date.today(),
        email_stats={
            "bot_answered": [nda_email_by_workspace],
            "pending_actionable": [nda_email_by_account],
        },
        tomorrow_date=date.today(),
        tomorrow_lessons=[],
        action_items=[],
    )
    assert len(spy_client.recorded_calls) >= 2

    # Проверка всех перехваченных промптов
    for call in spy_client.recorded_calls:
        assert "mock_nda_secret_token" not in call["contents"]
        assert "mock_proprietary_token" not in call["contents"]
        assert "CONFIDENTIAL" not in call["contents"]


def test_regular_emails_unaffected(regular_academic_email):
    assert is_nda_email(regular_academic_email) is False
    assert regular_academic_email["snippet"] == "Здравствуйте, Дмитрий Александрович! Проверьте, пожалуйста..."
    assert regular_academic_email["body_plain"].startswith("Здравствуйте")
