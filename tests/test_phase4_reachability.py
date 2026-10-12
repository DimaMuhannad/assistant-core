"""Тесты достижимости цепочки Git -> Оценка -> HITL -> Notion (GIT-01, GIT-03, NTN-01).

Проверяет:
1. Корень композиции собирает default_notion_client и default_git_evaluator с валидацией scopes (Task 1).
2. main.py регистрирует git_evaluator до EmailBotHandler, а также задачу планировщика git_progress_job (Task 2).
3. Цикл run_git_progress_cycle безопасен, не дублирует карточки и не падает (Task 2).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from assistant_shared.hitl.engine import get_action_handler
from src.core.exceptions import MissingScopeError
from src.persona.current import use_persona
from src.persona.loader import load_persona
from src.persona.models import PersonaConfig
from tests.synthetic_persona import SYNTHETIC_PERSONA, synthetic_to_config


@pytest.fixture
def fake_db(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(db_path=str(tmp_path / "test_reachability.db"))


def test_composition_default_git_evaluator_default_persona(fake_db: SimpleNamespace) -> None:
    """Test 1: персона по умолчанию: default_git_evaluator возвращает GitProgressEvaluator

    с провайдером SshGitProvider и клиентом NotionAsyncClient; обработчик notion_project_sync
    зарегистрирован именно на этот экземпляр.
    """
    from src.composition import default_git_evaluator, default_notion_client
    from src.connectors.git.provider import SshGitProvider
    from src.connectors.notion.client import NotionAsyncClient
    from src.brain.git_evaluator import GitProgressEvaluator

    client = default_notion_client()
    assert isinstance(client, NotionAsyncClient)

    evaluator = default_git_evaluator(fake_db)
    assert isinstance(evaluator, GitProgressEvaluator)
    assert isinstance(evaluator.git_provider, SshGitProvider)
    assert isinstance(evaluator.notion_client, NotionAsyncClient)

    handler = get_action_handler("notion_project_sync")
    assert handler == evaluator._handle_notion_sync


def test_composition_default_git_evaluator_without_git_source(
    tmp_path: Path, fake_db: SimpleNamespace
) -> None:
    """Test 2: персона без привязки git_source: default_git_evaluator возвращает None."""
    from src.composition import default_git_evaluator

    cfg_dict = synthetic_to_config(SYNTHETIC_PERSONA)
    cfg_dict["persona"]["connectors"]["git_source"] = []
    path = tmp_path / "persona_no_git.json"
    path.write_text(json.dumps(cfg_dict, ensure_ascii=False), encoding="utf-8")
    persona_no_git = load_persona(path)

    with use_persona(persona_no_git):
        evaluator = default_git_evaluator(fake_db)
        assert evaluator is None


def test_composition_default_git_evaluator_synthetic_without_notion(
    tmp_path: Path, fake_db: SimpleNamespace
) -> None:
    """Test 3: персона с git_source и без notion (синтетическая): оценщик создан, notion_client равен None."""
    from src.composition import default_git_evaluator, default_notion_client
    from src.brain.git_evaluator import GitProgressEvaluator

    path = tmp_path / "synthetic_persona.json"
    path.write_text(json.dumps(synthetic_to_config(SYNTHETIC_PERSONA), ensure_ascii=False), encoding="utf-8")
    synthetic_persona = load_persona(path)

    with use_persona(synthetic_persona):
        client = default_notion_client()
        assert client is None

        evaluator = default_git_evaluator(fake_db)
        assert isinstance(evaluator, GitProgressEvaluator)
        assert evaluator.notion_client is None


def test_composition_default_git_evaluator_missing_scope_raises(
    tmp_path: Path, fake_db: SimpleNamespace
) -> None:
    """Test 4: привязка git_source или notion без нужных scopes вызывает MissingScopeError."""
    from src.composition import default_git_evaluator, default_notion_client

    # 1. Недостаточно scopes для notion
    cfg_notion = synthetic_to_config(SYNTHETIC_PERSONA)
    cfg_notion["persona"]["connectors"]["notion"] = [
        {"id": "main", "provider": "notion_async", "scopes": ["notion.read"]}
    ]
    p_notion = tmp_path / "persona_bad_notion.json"
    p_notion.write_text(json.dumps(cfg_notion, ensure_ascii=False), encoding="utf-8")
    persona_bad_notion = load_persona(p_notion)

    with use_persona(persona_bad_notion):
        with pytest.raises(MissingScopeError, match="notion"):
            default_notion_client()

    # 2. Недостаточно scopes для git_source
    cfg_git = synthetic_to_config(SYNTHETIC_PERSONA)
    cfg_git["persona"]["connectors"]["git_source"] = [
        {"id": "main", "provider": "ssh_git", "scopes": []}
    ]
    p_git = tmp_path / "persona_bad_git.json"
    p_git.write_text(json.dumps(cfg_git, ensure_ascii=False), encoding="utf-8")
    persona_bad_git = load_persona(p_git)

    with use_persona(persona_bad_git):
        with pytest.raises(MissingScopeError, match="git_source"):
            default_git_evaluator(fake_db)


def test_composition_default_git_evaluator_db_path(fake_db: SimpleNamespace) -> None:
    """Test 5: ConfirmationStore оценщика указывает на тот же путь БД, что и переданный db."""
    from src.composition import default_git_evaluator

    evaluator = default_git_evaluator(fake_db)
    assert evaluator is not None
    assert evaluator.confirmation_store.db_path == fake_db.db_path


# --- Task 2: main.py AST и поведение цикла --------------------------------------------------

import ast
import importlib.util
import logging
import sys
from unittest.mock import AsyncMock, MagicMock

MAIN_PY_PATH = Path(__file__).resolve().parents[1] / "src" / "main.py"
DEPLOY_PY_PATH = Path(__file__).resolve().parents[1] / "scripts" / "deploy.py"


def _parse_main() -> ast.Module:
    return ast.parse(MAIN_PY_PATH.read_text(encoding="utf-8"))


def _func(tree: ast.Module, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name
    ]
    assert len(found) == 1, f"Функция {name} должна быть ровно одна, найдено {len(found)}"
    return found[0]


def check_execution_order(func_node: ast.AST, call_patterns: list[str]) -> list[int]:
    """Находит строки вызовов в теле функции и проверяет их строгий порядок возрастания."""
    line_numbers: list[int] = []
    for pattern in call_patterns:
        matched_lines = []
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                func_str = ast.unparse(node.func)
                if pattern in func_str:
                    matched_lines.append(node.lineno)
        if not matched_lines:
            raise AssertionError(f"Вызов с паттерном '{pattern}' не найден в функции")
        line_numbers.append(min(matched_lines))

    for i in range(len(line_numbers) - 1):
        if line_numbers[i] >= line_numbers[i + 1]:
            raise AssertionError(
                f"Нарушен порядок вызовов: {call_patterns[i]} (строка {line_numbers[i]}) "
                f"должен предшествовать {call_patterns[i + 1]} (строка {line_numbers[i + 1]})"
            )
    return line_numbers


def test_main_creates_git_evaluator_before_bot_handler() -> None:
    """Test 1 (ast): в main() вызов default_git_evaluator стоит раньше EmailBotHandler,

    а EmailBotHandler раньше первого scheduler.add_job.
    """
    tree = _parse_main()
    main_func = _func(tree, "main")

    patterns = ["default_git_evaluator", "EmailBotHandler", "scheduler.add_job"]
    lines = check_execution_order(main_func, patterns)
    assert len(lines) == 3


def test_main_registers_git_progress_job_unconditionally() -> None:
    """Test 2 (ast + deploy.load_expected_jobs): среди ожидаемых задач есть

    func=run_git_progress_cycle, job_id=git_progress_job, conditional False;
    триггер "cron"; day_of_week, hour, minute передаются не константами, а атрибутами настроек.
    """
    spec = importlib.util.spec_from_file_location("deploy_module", DEPLOY_PY_PATH)
    assert spec and spec.loader
    deploy_mod = importlib.util.module_from_spec(spec)
    sys.modules["deploy_module"] = deploy_mod
    spec.loader.exec_module(deploy_mod)

    jobs = deploy_mod.load_expected_jobs(MAIN_PY_PATH)
    target = next((j for j in jobs if j.job_id == "git_progress_job"), None)
    assert target is not None, "Задача git_progress_job не найдена среди expected_jobs в scripts/deploy.py"
    assert target.func == "run_git_progress_cycle"
    assert target.conditional is False, "Задача git_progress_job не должна быть зарегистрирована под if"

    # AST проверка аргументов вызова scheduler.add_job
    tree = _parse_main()
    main_func = _func(tree, "main")
    found_call = None
    for node in ast.walk(main_func):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_job":
            if any(isinstance(kw.value, ast.Constant) and kw.value.value == "git_progress_job" for kw in node.keywords if kw.arg == "id"):
                found_call = node
                break
    assert found_call is not None, "Вызов add_job с id='git_progress_job' не найден"

    # Второй позиционный аргумент - "cron"
    assert len(found_call.args) >= 2
    assert isinstance(found_call.args[1], ast.Constant) and found_call.args[1].value == "cron"

    # day_of_week, hour, minute передаются не константами, а атрибутами объекта настроек
    kw_dict = {kw.arg: kw.value for kw in found_call.keywords}
    for field in ("day_of_week", "hour", "minute"):
        assert field in kw_dict, f"Аргумент {field} отсутствует в вызове add_job"
        val_node = kw_dict[field]
        assert not isinstance(val_node, ast.Constant), f"{field} не должен быть константой, ожидается динамическое значение из настроек"
        assert isinstance(val_node, ast.Attribute), f"{field} должен читаться как атрибут настроек (например, gs.{field})"


def test_main_does_not_run_git_cycle_at_startup() -> None:
    """Test 3 (ast): run_git_progress_cycle не вызывается в main() напрямую (нет вызовов при старте)."""
    tree = _parse_main()
    main_func = _func(tree, "main")

    direct_calls: list[int] = []
    for node in ast.walk(main_func):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "run_git_progress_cycle":
                direct_calls.append(node.lineno)

    assert not direct_calls, f"run_git_progress_cycle вызывается напрямую в main() на строках: {direct_calls}"


@pytest.mark.asyncio
async def test_git_cycle_skips_when_evaluator_missing(caplog: pytest.LogCaptureFixture) -> None:
    """Test 4a (поведение): evaluator None даёт выход без исключений и без отправок."""
    from src.main import run_git_progress_cycle

    notifier = AsyncMock()
    with caplog.at_level(logging.INFO):
        await run_git_progress_cycle(None, notifier)

    notifier.send_message.assert_not_called()
    assert not any(r.levelname == "ERROR" for r in caplog.records)
    assert any("пропущен" in r.message.lower() or "evaluator" in r.message.lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_git_cycle_never_raises(caplog: pytest.LogCaptureFixture) -> None:
    """Test 4b (поведение): evaluate бросает исключение: цикл не падает, предупреждение в caplog, ни одного ERROR."""
    from src.main import run_git_progress_cycle

    evaluator = AsyncMock()
    evaluator.evaluate.side_effect = RuntimeError("Fatal git provider crash")
    notifier = AsyncMock()

    with caplog.at_level(logging.WARNING):
        # Цикл не должен бросить исключение
        await run_git_progress_cycle(evaluator, notifier)

    assert not any(r.levelname == "ERROR" for r in caplog.records)
    assert any(r.levelname == "WARNING" for r in caplog.records)
    notifier.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_git_cycle_sends_cards_only_for_new_and_one_summary() -> None:
    """Test 5 (поведение): карточка отправляется только для created=True и содержит кнопки;

    повторный запуск того же дня карточек не шлёт; сводка уходит один раз, пока сигнатура не изменилась;
    сбой отправки одной карточки не мешает остальным.
    """
    from src.main import run_git_progress_cycle

    evaluator = AsyncMock()
    notifier = AsyncMock()

    proposal_new = SimpleNamespace(
        created=True,
        confirmation=SimpleNamespace(id="conf_new_123"),
    )
    proposal_existing = SimpleNamespace(
        created=False,
        confirmation=SimpleNamespace(id="conf_old_456"),
    )

    evaluator.evaluate.return_value = "mock_run"
    evaluator.propose_cards.return_value = [proposal_new, proposal_existing]
    evaluator.format_card_text = MagicMock(return_value="Текст карточки для Telegram")
    evaluator.register_run_signature = MagicMock(return_value=True)
    evaluator.format_background_summary = MagicMock(return_value="Сводка прогресса Git")

    # Запуск 1: отправляется только новая карточка и сводка
    await run_git_progress_cycle(evaluator, notifier)

    # 1 вызов карточки + 1 вызов сводки = 2 вызова send_message
    assert notifier.send_message.call_count == 2
    # Проверяем карточку
    first_call = notifier.send_message.call_args_list[0]
    assert first_call.args[0] == "Текст карточки для Telegram"
    markup = first_call.kwargs.get("reply_markup")
    assert markup is not None
    # Кнопки ntn:conf и ntn:rej
    buttons = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert any(b.startswith("ntn:conf:conf_new_123") for b in buttons)
    assert any(b.startswith("ntn:rej:conf_new_123") for b in buttons)

    # Проверяем сводку
    second_call = notifier.send_message.call_args_list[1]
    assert second_call.args[0] == "Сводка прогресса Git"

    # Запуск 2 (того же дня): карточки уже есть (created=False), сигнатура не изменилась
    notifier.reset_mock()
    evaluator.propose_cards.return_value = [
        SimpleNamespace(created=False, confirmation=SimpleNamespace(id="conf_new_123")),
        SimpleNamespace(created=False, confirmation=SimpleNamespace(id="conf_old_456")),
    ]
    evaluator.register_run_signature.return_value = False

    await run_git_progress_cycle(evaluator, notifier)
    notifier.send_message.assert_not_called()

    # Сбой отправки одной карточки: не прерывает отправку второй карточки
    notifier.reset_mock()
    prop_fail = SimpleNamespace(created=True, confirmation=SimpleNamespace(id="conf_fail"))
    prop_ok = SimpleNamespace(created=True, confirmation=SimpleNamespace(id="conf_ok"))
    evaluator.propose_cards.return_value = [prop_fail, prop_ok]
    evaluator.register_run_signature.return_value = False

    # Первое сообщение упало, второе успешно
    notifier.send_message.side_effect = [Exception("Telegram network error"), MagicMock()]
    await run_git_progress_cycle(evaluator, notifier)
    assert notifier.send_message.call_count == 2
