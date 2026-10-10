"""Достижимость новых функций фазы 2 из рантайма (критерий успеха 5, правило CLAUDE.md §5).

Юнит-тесты доказывают логику, а здесь проверяется подключение: обработчики зарегистрированы в роутере
EmailBotHandler, main.py подключает роутер и ставит задачу почты, цикл почты вызывает показ
предупреждения PRIV-01, hook и обёртка shield передают в аудит только правила пространств (D-21).
Боевая БД и сеть не используются: временные БД в tmp_path, MagicMock вместо бота, подпроцесс shield
работает на временном репозитории. Слов NDA и организаций здесь нет; секрет синтетический, из частей.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.brain.dialog_safety import CLEAR_DIALOG_TEXT_WARNING
from src.notifier.bot_handler import EmailBotHandler
from src.persona.current import use_persona
from src.persona.loader import load_persona
from src.storage.db import Database

from .test_persona_loader import MINIMAL_TEMPLATE

ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "src" / "main.py"
SHIELD_PATH = ROOT / "scripts" / "security_shield.py"
HOOK_PATH = ROOT / ".githooks" / "pre-commit"

USER_ID = 424242


# ---------------------------------------------------------------- вспомогательное


def _make_handler(db) -> EmailBotHandler:
    handler = EmailBotHandler(bot=MagicMock(), db=db, allowed_user_id=USER_ID)
    handler.notifier = AsyncMock()
    return handler


def _make_message(text: str | None = None) -> MagicMock:
    msg = MagicMock()
    msg.from_user.id = USER_ID
    msg.chat.id = USER_ID
    msg.chat.type = "private"
    msg.text = text
    msg.answer = AsyncMock()
    return msg


def _registered(handler: EmailBotHandler) -> dict[str, list]:
    """Имя функции обратного вызова -> список зарегистрированных HandlerObject роутера сообщений."""
    result: dict[str, list] = {}
    for registered in handler.router.message.handlers:
        name = getattr(registered.callback, "__name__", "")
        result.setdefault(name, []).append(registered)
    return result


def _command_names(registered) -> set[str]:
    """Имена слэш-команд из фильтров обработчика (Command.commands)."""
    names: set[str] = set()
    for flt in registered.filters:
        commands = getattr(flt.callback, "commands", None)
        if commands:
            names.update(str(c) for c in commands)
    return names


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _func(tree: ast.Module, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name
    ]
    assert len(found) == 1, f"функция {name} должна быть ровно одна, найдено {len(found)}"
    return found[0]


def _callee_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


# ---------------------------------------------------------------- 1. роутер бота


@pytest.mark.asyncio
async def test_router_registers_help_clear_text_and_voice_handlers(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'reach.db'}")
    await db.init_db()
    handler = _make_handler(db)
    registered = _registered(handler)

    for name in ("handle_cmd_help", "handle_cmd_clear_dialog", "handle_user_text", "handle_user_voice"):
        assert name in registered, f"в роутере бота нет обработчика {name}"

    help_cmds = {c for r in registered["handle_cmd_help"] for c in _command_names(r)}
    clear_cmds = {c for r in registered["handle_cmd_clear_dialog"] for c in _command_names(r)}
    assert {"start", "help"} <= help_cmds
    assert {"clear", "reset"} <= clear_cmds
    # Текстовый и голосовой маршруты сидят на фильтрах сообщений, а не на слэш-командах
    assert all(not _command_names(r) for r in registered["handle_user_text"])
    assert all(not _command_names(r) for r in registered["handle_user_voice"])


# ---------------------------------------------------------------- 2. /help с блоком приватности


@pytest.mark.asyncio
async def test_help_command_sends_privacy_block_from_default_persona(tmp_path, monkeypatch):
    monkeypatch.delenv("PERSONA_CONFIG_PATH", raising=False)
    persona = load_persona()
    notice = persona.privacy.email_ai_notice
    assert notice, "персона по умолчанию обязана нести текст предупреждения PRIV-01"

    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'help.db'}")
    await db.init_db()
    handler = _make_handler(db)
    registered = _registered(handler)
    # Вызов именно того обработчика, который роутер сопоставляет с /help
    callback = registered["handle_cmd_help"][0].callback

    msg = _make_message("/help")
    with use_persona(persona):
        await callback(msg)

    handler.notifier.send_message.assert_awaited_once()
    sent = handler.notifier.send_message.await_args.args[0]
    assert "Приватность почты" in sent
    assert "внешними ИИ-сервисами" in sent
    assert sent.endswith(notice)


# ---------------------------------------------------------------- 3. текстовое «очисти диалог»


@pytest.mark.asyncio
async def test_text_clear_phrase_through_router_text_handler_warns_and_keeps_history(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'clear.db'}")
    await db.init_db()
    for i in range(2):
        await db.save_dialog_message(user_id=USER_ID, role="user", content=f"Вопрос {i}")
        await db.save_dialog_message(user_id=USER_ID, role="model", content=f"Ответ {i}")
    handler = _make_handler(db)
    callback = _registered(handler)["handle_user_text"][0].callback
    assert await db.get_active_dialog_count(USER_ID) == 4

    msg = _make_message("очисти диалог")
    await callback(msg)

    assert await db.get_active_dialog_count(USER_ID) == 4
    handler.notifier.send_message.assert_awaited_once()
    sent = handler.notifier.send_message.await_args.args[0]
    assert sent == CLEAR_DIALOG_TEXT_WARNING
    assert "/clear" in sent
    kwargs = handler.notifier.send_message.await_args.kwargs
    assert kwargs.get("reply_markup") is None, "карточка подтверждения из текста показываться не должна"


# ---------------------------------------------------------------- 4. планировщик и цикл почты (AST main.py)


def test_main_wires_bot_router_and_email_collector_job():
    tree = _parse(MAIN_PATH)
    main_fn = _func(tree, "main")

    calls = [n for n in ast.walk(main_fn) if isinstance(n, ast.Call)]
    assert any(_callee_name(c) == "EmailBotHandler" for c in calls), "main() не создаёт EmailBotHandler"

    include = [c for c in calls if _callee_name(c) == "include_router"]
    assert include, "main() не подключает роутер к диспетчеру"
    assert any(
        isinstance(a, ast.Attribute) and a.attr == "router" and isinstance(a.value, ast.Name)
        for c in include
        for a in c.args
    ), "в диспетчер должен попадать router обработчика бота"

    jobs = [
        c
        for c in calls
        if _callee_name(c) == "add_job"
        and c.args
        and isinstance(c.args[0], ast.Name)
        and c.args[0].id == "run_email_collector_cycle"
    ]
    assert len(jobs) == 1, "ровно одна задача планировщика на run_email_collector_cycle"
    ids = [
        kw.value.value
        for kw in jobs[0].keywords
        if kw.arg == "id" and isinstance(kw.value, ast.Constant)
    ]
    assert ids == ["email_collector_job"]


def test_email_collector_cycle_calls_privacy_notice_announcement():
    cycle = _func(_parse(MAIN_PATH), "run_email_collector_cycle")
    called = {_callee_name(c) for c in ast.walk(cycle) if isinstance(c, ast.Call)}
    assert "_announce_email_ai_notice" in called
    # Показ предупреждения идёт после сбора: результат sync_all_accounts передаётся в него
    announce = [
        c for c in ast.walk(cycle) if isinstance(c, ast.Call) and _callee_name(c) == "_announce_email_ai_notice"
    ]
    assert len(announce) == 1 and len(announce[0].args) == 3


# ---------------------------------------------------------------- 5. hook, обёртка, audit_repository


def test_pre_commit_hook_runs_security_shield_without_relaxing_flags():
    text = HOOK_PATH.read_text(encoding="utf-8")
    assert "scripts/security_shield.py" in text
    exec_lines = [ln for ln in text.splitlines() if "security_shield.py" in ln and not ln.lstrip().startswith("#")]
    assert len(exec_lines) == 1
    assert exec_lines[0].strip().startswith("exec ")
    # Допусков и обходов в вызове нет: ни аргументов командной строки сверх пути репозитория, ни `|| true`
    assert "||" not in exec_lines[0]
    assert "--allow" not in text and "--ignore" not in text and "--skip" not in text


def test_shield_wrapper_passes_only_workspaces_to_audit_repository():
    tree = _parse(SHIELD_PATH)
    audit_calls = [
        n for n in ast.walk(tree) if isinstance(n, ast.Call) and _callee_name(n) == "audit_repository"
    ]
    assert len(audit_calls) == 1
    keywords = {kw.arg for kw in audit_calls[0].keywords}
    assert keywords == {"check_staged_only", "workspaces"}, "допусков слов нет: другие аргументы запрещены (D-21)"

    # Постоянных наборов слов NDA в обёртке нет: правила приходят из данных персоны
    pattern = re.compile("(?i)(" + "n" + "da|forbid" + "den|key" + "word)")
    for node in tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                assert not pattern.search(target.id), f"константа с набором слов в обёртке: {target.id}"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True, timeout=60)


def _synthetic_repo(path: Path, content: str) -> Path:
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "synthetic@synthetic.example")
    _git(path, "config", "user.name", "Synthetic")
    (path / "sample.txt").write_text(content, encoding="utf-8")
    _git(path, "add", "sample.txt")
    return path


def _run_shield(persona: Path, repo: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PERSONA_CONFIG_PATH"] = str(persona)
    return subprocess.run(
        [sys.executable, str(SHIELD_PATH), str(repo)],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )


def test_shield_entry_point_is_red_on_synthetic_secret_and_green_on_clean_repo(tmp_path):
    persona = tmp_path / "persona.yaml"
    persona.write_text(MINIMAL_TEMPLATE.format(persona_id="reach-shield", extra=""), encoding="utf-8")

    # Синтетический ключ формата Google API собран из частей: сам файл теста секрет не содержит
    secret = "AIza" + "Sy" + "A" * 33
    dirty = _synthetic_repo(tmp_path / "dirty", f"key = '{secret}'\n")
    clean = _synthetic_repo(tmp_path / "clean", "ordinary text\n")

    red = _run_shield(persona, dirty)
    assert red.returncode == 1, red.stdout + red.stderr
    assert secret not in red.stdout + red.stderr, "shield не должен печатать значение секрета"

    green = _run_shield(persona, clean)
    assert green.returncode == 0, green.stdout + green.stderr
