"""Предупреждение о приватности почты в /help из данных персоны (PRIV-01, D-14, D-15 п.1, D-16)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

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


# ---------------------------------------------------------------- данные владельца (персона по умолчанию)


def test_default_persona_carries_owner_notice(monkeypatch):
    monkeypatch.delenv("PERSONA_CONFIG_PATH", raising=False)
    notice = load_persona().privacy.email_ai_notice
    assert notice is not None
    assert "внешними ИИ-сервисами" in notice
    assert "Gemini" in notice
    assert "не несёт ответственности" in notice
    assert len(notice) <= EMAIL_AI_NOTICE_MAX_LEN
    # Markdown Telegram: подчёркивания и звёздочки вне разметки сломали бы форматирование
    assert "_" not in notice and "*" not in notice


@pytest.mark.asyncio
async def test_help_with_default_persona_sends_owner_notice(monkeypatch):
    monkeypatch.delenv("PERSONA_CONFIG_PATH", raising=False)
    persona = load_persona()
    handler = _handler()
    with use_persona(persona):
        await handler.handle_cmd_help(_message(ALLOWED_USER_ID))
    sent = handler.notifier.send_message.await_args.args[0]
    assert sent.endswith(persona.privacy.email_ai_notice)
    assert len(sent) < TELEGRAM_MESSAGE_LIMIT


@pytest.mark.asyncio
async def test_help_with_synthetic_persona_without_privacy_block_sends_fallback(tmp_path):
    from .synthetic_persona import SYNTHETIC_PERSONA, synthetic_to_config

    config = synthetic_to_config(SYNTHETIC_PERSONA)
    assert "privacy" not in config["persona"]
    path = tmp_path / "synthetic.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    persona = load_persona(path)
    handler = _handler()
    with use_persona(persona):
        await handler.handle_cmd_help(_message(ALLOWED_USER_ID))
    sent = handler.notifier.send_message.await_args.args[0]
    assert sent.endswith(email_ai_notice(persona))
    assert "внешними ИИ-сервисами" in sent


# ---------------------------------------------------------------- показ при старте сборщика (PRIV-01, план 02-12)

import logging  # noqa: E402

from src.persona.notices import EMAIL_AI_NOTICE_FLAG_KEY as _FLAG  # noqa: E402,F401
from src.storage.db import Database  # noqa: E402

CONNECTED = {
    "mailru": {"account": "mailru", "checked": 3, "inserted": 1},
    "reconciliation": {},
    "aging": {},
    "db_totals": {},
    "active_actionable_count": 0,
}
ALL_SKIPPED = {
    "mailru": {"account": "mailru", "status": "skipped_no_creds"},
    "gmail": {"account": "gmail", "status": "skipped_no_token"},
    "reconciliation": {},
    "aging": {},
    "db_totals": {},
    "active_actionable_count": 0,
}
ERRORED = {
    "mailru": {"account": "mailru", "checked": 0, "inserted": 0, "error": "login failed"},
    "reconciliation": {},
    "aging": {},
    "db_totals": {},
}
NOTICE_TEXT = "Тестовое предупреждение из данных персоны."


@pytest.fixture
async def notice_db(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'notice.db'}")
    await db.init_db()
    yield db
    await db.close()


def _notice_persona(tmp_path) -> PersonaConfig:
    return _persona(tmp_path, extra=f"  privacy:\n    email_ai_notice: {NOTICE_TEXT}\n")


async def _run_cycle(db, results, notifier, persona):
    from src.main import run_email_collector_cycle

    collector = AsyncMock()
    collector.sync_all_accounts.return_value = results
    with use_persona(persona):
        await run_email_collector_cycle(db, collector, notifier)


def _notifier(side_effect=None) -> AsyncMock:
    notifier = AsyncMock()
    notifier.send_message.return_value = [101]
    if side_effect is not None:
        notifier.send_message.side_effect = side_effect
    return notifier


@pytest.mark.asyncio
async def test_first_cycle_with_connected_mailbox_announces_once(notice_db, tmp_path, caplog):
    persona = _notice_persona(tmp_path)
    notifier = _notifier()
    with caplog.at_level(logging.INFO, logger="assistant-worker"):
        await _run_cycle(notice_db, CONNECTED, notifier, persona)
    notifier.send_message.assert_awaited_once()
    sent = notifier.send_message.await_args.args[0]
    assert NOTICE_TEXT in sent
    assert notifier.send_message.await_args.kwargs.get("chat_id") is None
    assert any("PRIV-01" in r.getMessage() and NOTICE_TEXT in r.getMessage() for r in caplog.records)
    assert await notice_db.has_notice_shown(EMAIL_AI_NOTICE_FLAG_KEY) is True


@pytest.mark.asyncio
async def test_second_cycle_is_silent(notice_db, tmp_path):
    persona = _notice_persona(tmp_path)
    notifier = _notifier()
    await _run_cycle(notice_db, CONNECTED, notifier, persona)
    await _run_cycle(notice_db, CONNECTED, notifier, persona)
    assert notifier.send_message.await_count == 1


@pytest.mark.asyncio
async def test_all_mailboxes_skipped_no_notice_no_flag(notice_db, tmp_path):
    notifier = _notifier()
    await _run_cycle(notice_db, ALL_SKIPPED, notifier, _notice_persona(tmp_path))
    notifier.send_message.assert_not_awaited()
    assert await notice_db.has_notice_shown(EMAIL_AI_NOTICE_FLAG_KEY) is False


@pytest.mark.asyncio
async def test_mailbox_with_error_no_notice_no_flag(notice_db, tmp_path):
    notifier = _notifier()
    await _run_cycle(notice_db, ERRORED, notifier, _notice_persona(tmp_path))
    notifier.send_message.assert_not_awaited()
    assert await notice_db.has_notice_shown(EMAIL_AI_NOTICE_FLAG_KEY) is False


@pytest.mark.asyncio
async def test_service_keys_alone_do_not_count_as_mailbox(notice_db, tmp_path):
    notifier = _notifier()
    results = {"reconciliation": {"inserted": 5}, "aging": {"x": 1}, "db_totals": {"y": 2}, "active_actionable_count": 3}
    await _run_cycle(notice_db, results, notifier, _notice_persona(tmp_path))
    notifier.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_skipped_plus_connected_counts_as_connected(notice_db, tmp_path):
    notifier = _notifier()
    results = dict(ALL_SKIPPED)
    results["gmail"] = {"account": "gmail", "checked": 2, "inserted": 0}
    await _run_cycle(notice_db, results, notifier, _notice_persona(tmp_path))
    notifier.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_send_keeps_flag_unset_and_does_not_break_cycle(notice_db, tmp_path, caplog):
    persona = _notice_persona(tmp_path)
    notifier = _notifier(side_effect=RuntimeError("telegram down"))
    with caplog.at_level(logging.WARNING, logger="assistant-worker"):
        await _run_cycle(notice_db, CONNECTED, notifier, persona)  # исключение наружу не выходит
    assert await notice_db.has_notice_shown(EMAIL_AI_NOTICE_FLAG_KEY) is False
    assert any("PRIV-01" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)
    # после восстановления Telegram предупреждение уходит
    notifier.send_message.side_effect = None
    notifier.send_message.return_value = [7]
    await _run_cycle(notice_db, CONNECTED, notifier, persona)
    assert await notice_db.has_notice_shown(EMAIL_AI_NOTICE_FLAG_KEY) is True


@pytest.mark.asyncio
async def test_empty_send_result_keeps_flag_unset(notice_db, tmp_path):
    notifier = _notifier()
    notifier.send_message.return_value = []
    await _run_cycle(notice_db, CONNECTED, notifier, _notice_persona(tmp_path))
    assert await notice_db.has_notice_shown(EMAIL_AI_NOTICE_FLAG_KEY) is False


@pytest.mark.asyncio
async def test_notice_failure_does_not_stop_email_cards(notice_db, tmp_path):
    from datetime import datetime, timezone

    await notice_db.upsert_email_message(
        message_id="msg-priv-1@example.org",
        account_id="mailru",
        folder="INBOX",
        sender_name="Отправитель",
        sender_email="sender@example.org",
        recipients_json="[]",
        subject="Тема",
        date_sent=datetime.now(timezone.utc),
        body_plain="Текст",
        body_html=None,
        snippet="Текст",
        has_attachments=False,
        attachments_json=None,
        in_reply_to=None,
        references_text=None,
        thread_id="th-priv-1",
        category="guap_dept",
        requires_action=True,
    )
    notifier = _notifier(side_effect=RuntimeError("telegram down"))
    notifier.send_actionable_email_card.return_value = [9001]
    await _run_cycle(notice_db, {"mailru": {"inserted": 1}}, notifier, _notice_persona(tmp_path))
    notifier.send_actionable_email_card.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_notice_shown_rejects_key_without_prefix(notice_db):
    with pytest.raises(ValueError):
        await notice_db.mark_notice_shown("2026-10-10")
    with pytest.raises(ValueError):
        await notice_db.has_notice_shown("email_ai")
    with pytest.raises(ValueError):
        await notice_db.mark_notice_shown("notice:")


@pytest.mark.asyncio
async def test_notice_flag_independent_from_primed_context(notice_db):
    await notice_db.mark_notice_shown("notice:email_ai")
    assert await notice_db.get_primed_context("2026-10-10") is None
    await notice_db.save_primed_context("2026-10-10", "контекст")
    assert await notice_db.has_notice_shown("notice:email_ai") is True
    assert (await notice_db.get_primed_context("2026-10-10"))["summary_text"] == "контекст"
    assert await notice_db.has_notice_shown("notice:other") is False
    # повторная отметка идемпотентна
    await notice_db.mark_notice_shown("notice:email_ai")
    assert await notice_db.has_notice_shown("notice:email_ai") is True


# ---------------------------------------------------------------- auth_google.py и .env.example (PRIV-01, D-15 п.3)

import ast  # noqa: E402
import importlib.util  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTH_SCRIPT = REPO_ROOT / "scripts" / "auth_google.py"


def _load_auth_script():
    spec = importlib.util.spec_from_file_location("auth_google_under_test", AUTH_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_notice_without_persona_returns_neutral_fallback():
    text = email_ai_notice(None)
    assert "внешними ИИ-сервисами" in text
    assert "не несёт ответственности" in text
    assert "и др." not in text


def test_auth_script_prints_default_persona_notice_to_stderr(monkeypatch, capsys):
    monkeypatch.delenv("PERSONA_CONFIG_PATH", raising=False)
    module = _load_auth_script()
    module._print_privacy_notice()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Приватность" in captured.err
    assert load_persona().privacy.email_ai_notice in captured.err


def test_auth_script_falls_back_when_persona_unavailable(monkeypatch, capsys):
    module = _load_auth_script()
    import src.persona.loader as loader

    def _boom(*args, **kwargs):
        raise RuntimeError("persona недоступна")

    monkeypatch.setattr(loader, "load_persona", _boom)
    module._print_privacy_notice()  # исключение наружу не выходит
    captured = capsys.readouterr()
    assert email_ai_notice(None) in captured.err


def test_env_example_has_commented_mail_block_with_russian_notice():
    from assistant_shared.security import SECRET_PATTERNS

    lines = (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if "Почта (сбор писем)" in line)
    block = lines[start:]
    joined = "\n".join(block)
    assert "внешними ИИ-сервисами" in joined
    assert "не отвечает" in joined
    for name in ("MAILRU_EMAIL", "MAILRU_PASSWORD", "GMAIL_EMAIL", "GMAIL_PASSWORD"):
        assert f"# {name}=" in block
    assert all(line.startswith("#") or not line.strip() for line in block)
    for line in block:
        for name, pattern in SECRET_PATTERNS:
            assert not pattern.search(line), (name, line)


def test_auth_script_prints_notice_before_credentials_check():
    tree = ast.parse(AUTH_SCRIPT.read_text(encoding="utf-8"))
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")

    def _first_line(predicate):
        lines = [n.lineno for n in ast.walk(main) if predicate(n)]
        return min(lines) if lines else None

    notice_line = _first_line(
        lambda n: isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_print_privacy_notice"
    )
    creds_line = _first_line(
        lambda n: isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "exists"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "creds_path"
    )
    assert notice_line is not None and creds_line is not None
    assert notice_line < creds_line
