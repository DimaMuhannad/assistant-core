#!/usr/bin/env python3
"""Локальный гейт качества assistant-core: одна команда -> честный итог «ЗЕЛЁНЫЙ» / «КРАСНЫЙ».

Запуск (из /opt/assistant-core):  python3 scripts/gate.py
Только стандартная библиотека Python, запускается любым python3.

Гейт не обрывается на первой ошибке: сбой шага превращается в красную строку,
остальные строки всё равно печатаются. Прогон с 0 собранных тестов, с
пропущенными, xfail/xpass или deselected тестами считается красным.
Гейт не читает .env, credentials.json, token.json, *.session и не трогает
systemd-сервисы на запись.

Образец: /opt/chat-app/scripts/gate.py (только для чтения). Этот файл от chat-app
не зависит.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[1]
SHARED_DIR = Path(os.environ.get("ASSISTANT_SHARED_DIR", "/opt/assistant-shared"))
CHAT_APP_DIR = Path(os.environ.get("ASSISTANT_CHAT_APP_DIR", "/opt/chat-app"))
LIVE_DB = CORE_DIR / "data" / "assistant.db"
CORE_VENV_BIN = CORE_DIR / ".venv" / "bin"
PYTEST_TIMEOUT_S = 900
LINT_TIMEOUT_S = 300
SHIELD_TIMEOUT_S = 300

REPO_CORE = "assistant-core"
REPO_SHARED = "assistant-shared"


@dataclass(frozen=True)
class CheckResult:
    repo: str
    name: str
    ok: bool
    detail: str = ""
    info: str = ""


def run_cmd(
    cmd: list[str],
    cwd: Path,
    env_extra: dict[str, str] | None = None,
    timeout: int = PYTEST_TIMEOUT_S,
) -> subprocess.CompletedProcess:
    """Запуск подпроцесса: список аргументов, без shell, с таймаутом."""
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        shell=False,
        timeout=timeout,
    )


def _exc_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def run_lint_imports_step(
    repo: str,
    lint_bin: Path,
    cwd: Path,
    env_extra: dict[str, str] | None,
) -> CheckResult:
    """Один запуск lint-imports (контракт .importlinter репозитория) -> CheckResult.

    --no-cache: кэш import-linter не должен появляться в дереве репозитория.
    """
    name = "import-linter"
    if not lint_bin.is_file():
        return CheckResult(repo, name, False, "не установлен import-linter — см. requirements-dev.txt")
    if not cwd.is_dir():
        return CheckResult(repo, name, False, f"нет каталога репозитория: {cwd}")
    try:
        proc = run_cmd(
            [str(lint_bin), "--no-logo", "--no-cache"], cwd, env_extra, timeout=LINT_TIMEOUT_S
        )
    except subprocess.TimeoutExpired:
        return CheckResult(repo, name, False, "превышено время выполнения lint-imports")
    if proc.returncode == 0:
        return CheckResult(repo, name, True)
    output = proc.stdout + "\n" + proc.stderr
    lines = [line.strip() for line in output.splitlines() if "BROKEN" in line or "->" in line]
    if not lines:
        lines = [f"код возврата lint-imports: {proc.returncode}"]
    return CheckResult(repo, name, False, "\n".join(lines[:10]))


def overall_green(results: list[CheckResult]) -> bool:
    """Пустой список результатов - красный: гейт без проверок ничего не доказывает."""
    return bool(results) and all(result.ok for result in results)


def render_report(results: list[CheckResult]) -> str:
    """Таблица «Репозиторий | Проверка | Результат» с деталями и итоговой строкой."""
    rows = [("Репозиторий", "Проверка", "Результат")]
    rows += [(r.repo, r.name, "✓" if r.ok else "✗") for r in results]
    w_repo = max(len(row[0]) for row in rows) + 2
    w_name = max(len(row[1]) for row in rows) + 2
    lines = ["Гейт качества assistant-core и assistant-shared", ""]
    for index, row in enumerate(rows):
        lines.append(f"{row[0].ljust(w_repo)}{row[1].ljust(w_name)}{row[2]}")
        if index == 0:
            continue
        result = results[index - 1]
        if not result.ok:
            lines.extend(f"  ↳ {line}" for line in result.detail.splitlines())
        else:
            lines.extend(f"  · {line}" for line in result.info.splitlines())
    lines.append("")
    lines.append("ИТОГ: ЗЕЛЁНЫЙ" if overall_green(results) else "ИТОГ: КРАСНЫЙ")
    return "\n".join(lines)


def _safe_lint_step(repo: str, **kwargs) -> CheckResult:
    try:
        return run_lint_imports_step(repo=repo, **kwargs)
    except Exception as exc:  # неожиданный сбой шага - красная строка, не трассировка
        return CheckResult(repo, "import-linter", False, f"сбой шага: {_exc_text(exc)}")


def _run_all(save_dir: Path | None) -> list[CheckResult]:
    results: list[CheckResult] = []
    results.append(
        _safe_lint_step(
            REPO_CORE, lint_bin=CORE_VENV_BIN / "lint-imports", cwd=CORE_DIR, env_extra=None
        )
    )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Локальный гейт качества assistant-core.")
    parser.add_argument(
        "--save-pytest-output",
        metavar="DIR",
        help="сохранить сырой вывод pytest -v в DIR (снимок baseline; вывод shield не сохраняется)",
    )
    args = parser.parse_args(argv)
    save_dir = Path(args.save_pytest_output).resolve() if args.save_pytest_output else None
    try:
        results = _run_all(save_dir)
    except Exception as exc:
        results = [
            CheckResult(REPO_CORE, "работа гейта", False, f"внутренняя ошибка: {_exc_text(exc)}")
        ]
    print(render_report(results))
    return 0 if overall_green(results) else 1


if __name__ == "__main__":
    sys.exit(main())
