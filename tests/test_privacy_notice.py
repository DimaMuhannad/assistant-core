"""Предупреждение о приватности почты в /help из данных персоны (PRIV-01, D-14, D-15 п.1, D-16)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.notifier.bot_handler import EmailBotHandler
from src.persona.current import use_persona
from src.persona.loader import load_persona
from src.persona.models import EMAIL_AI_NOTICE_MAX_LEN, PersonaConfig, PersonaConfigError, PrivacyConfig
from src.persona.notices import EMAIL_AI_NOTICE_FLAG_KEY, email_ai_notice

TELEGRAM_MESSAGE_LIMIT = 4096
ALLOWED_USER_ID = 424242

MINIMAL_TEMPLATE = """\
persona:
  id: {persona_id}
  display_name: Тестовая Персона
  short_name: Тестова П.
  title: тестировщик
  organizations:
    university:
      name: Университет-А
      aliases: []
  default_area: Область-А
  task_areas:
    - {{value: Область-А, label: Область А}}
  methodist:
    raw_dir: /tmp/raw
    kb_dir: /tmp/kb
    scope_rules: {{out_of_scope_reason: вне темы}}
{extra}"""


def _persona(tmp_path: Path, extra: str = "") -> PersonaConfig:
    path = tmp_path / "persona.yaml"
    path.write_text(MINIMAL_TEMPLATE.format(persona_id="tmp-privacy", extra=extra), encoding="utf-8")
    return load_persona(path)


def _handler() -> EmailBotHandler:
    handler = EmailBotHandler(db=MagicMock(), notifier=AsyncMock(), allowed_user_id=ALLOWED_USER_ID)
    handler.notifier = AsyncMock()
    return handler


def _message(user_id: int) -> MagicMock:
    message = MagicMock()
    message.from_user.id = user_id
    message.chat.id = 777
    return message


def test_persona_without_privacy_block_has_empty_privacy(tmp_path):
    persona = _persona(tmp_path)
    assert persona.privacy == PrivacyConfig()
    assert persona.privacy.email_ai_notice is None
    assert persona.privacy.external_ai_services == []


def test_privacy_block_with_unknown_key_rejected(tmp_path):
    with pytest.raises(PersonaConfigError):
        _persona(tmp_path, extra="  privacy:\n    consent_required: true\n")


@pytest.mark.parametrize("value", ["''", "'   '"])
def test_empty_notice_rejected(tmp_path, value):
    with pytest.raises(PersonaConfigError):
        _persona(tmp_path, extra=f"  privacy:\n    email_ai_notice: {value}\n")


def test_too_long_notice_rejected(tmp_path):
    too_long = "а" * (EMAIL_AI_NOTICE_MAX_LEN + 1)
    with pytest.raises(PersonaConfigError):
        _persona(tmp_path, extra=f"  privacy:\n    email_ai_notice: {too_long}\n")


def test_notice_of_max_length_accepted(tmp_path):
    ok = "а" * EMAIL_AI_NOTICE_MAX_LEN
    persona = _persona(tmp_path, extra=f"  privacy:\n    email_ai_notice: {ok}\n")
    assert email_ai_notice(persona) == ok


def test_empty_service_name_rejected(tmp_path):
    with pytest.raises(PersonaConfigError):
        _persona(tmp_path, extra="  privacy:\n    external_ai_services: ['  ']\n")


def test_notice_returns_persona_text_as_is(tmp_path):
    persona = _persona(tmp_path, extra="  privacy:\n    email_ai_notice: Текст предупреждения из данных.\n")
    assert email_ai_notice(persona) == "Текст предупреждения из данных."


def test_fallback_notice_is_neutral_and_informative(tmp_path):
    text = email_ai_notice(_persona(tmp_path))
    assert "внешними ИИ-сервисами" in text
    assert "не несёт ответственности" in text
    assert "и др." not in text
    assert "(" not in text
    # Markdown Telegram: подчёркивания и звёздочки в запасном тексте сломали бы разметку
    assert "_" not in text and "*" not in text


def test_fallback_notice_lists_configured_services(tmp_path):
    persona = _persona(tmp_path, extra="  privacy:\n    external_ai_services: [Сервис-А, Сервис-Б]\n")
    text = email_ai_notice(persona)
    assert "Сервис-А, Сервис-Б и др." in text
    assert "не несёт ответственности" in text


def test_flag_key_is_reserved_constant():
    assert EMAIL_AI_NOTICE_FLAG_KEY == "notice:email_ai"


@pytest.mark.asyncio
async def test_help_ends_with_persona_notice_and_fits_telegram_limit(tmp_path):
    persona = _persona(tmp_path, extra="  privacy:\n    email_ai_notice: Предупреждение из данных персоны.\n")
    handler = _handler()
    with use_persona(persona):
        await handler.handle_cmd_help(_message(ALLOWED_USER_ID))
    handler.notifier.send_message.assert_awaited_once()
    sent = handler.notifier.send_message.await_args.args[0]
    assert "Приватность почты" in sent
    assert sent.endswith("Предупреждение из данных персоны.")
    assert len(sent) < TELEGRAM_MESSAGE_LIMIT


@pytest.mark.asyncio
async def test_help_with_longest_notice_fits_telegram_limit(tmp_path):
    longest = "а" * EMAIL_AI_NOTICE_MAX_LEN
    persona = _persona(tmp_path, extra=f"  privacy:\n    email_ai_notice: {longest}\n")
    handler = _handler()
    with use_persona(persona):
        await handler.handle_cmd_help(_message(ALLOWED_USER_ID))
    sent = handler.notifier.send_message.await_args.args[0]
    assert sent.endswith(longest)
    assert len(sent) < TELEGRAM_MESSAGE_LIMIT


@pytest.mark.asyncio
async def test_help_does_not_reply_to_unauthorized_user(tmp_path):
    handler = _handler()
    with use_persona(_persona(tmp_path)):
        await handler.handle_cmd_help(_message(ALLOWED_USER_ID + 1))
    handler.notifier.send_message.assert_not_awaited()
