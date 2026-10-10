#!/usr/bin/env python3
"""Security Shield CLI Wrapper (SEC-02, SECF-01).

Режим NDA определяется данными рабочих пространств персоны (config/persona.yaml или
PERSONA_CONFIG_PATH), а не константами в коде (D-06). Обёртка загружает персону и передаёт
правила в audit_repository ровно тремя аргументами: repo, check_staged_only и workspaces.
Допусков слов и иных смягчений нет ни в режиме фиксации, ни в режиме --all (D-21).
Любая проблема с данными пространств даёт rc=1 без отката к публичной проверке (D-08).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    from assistant_shared.security import audit_repository
except ImportError:
    shared_path = Path("/opt/assistant-shared")
    if shared_path.is_dir() and str(shared_path) not in sys.path:
        sys.path.insert(0, str(shared_path))
    from assistant_shared.security import audit_repository

__all__ = ["audit_repository", "main"]

CORE_ROOT = Path(__file__).resolve().parents[1]


def _load_workspaces() -> tuple[list[dict[str, Any]], Any]:
    """Правила пространств из персоны: [ws.model_dump() ...] и сама персона.

    Импорт отложен до вызова: сам модуль при импорте персону не читает. Любое исключение
    поднимается наружу и обрабатывается в main как недоступность данных (fail-closed).
    """
    if str(CORE_ROOT) not in sys.path:
        sys.path.insert(0, str(CORE_ROOT))
    from src.persona.loader import load_persona

    persona = load_persona()
    return [ws.model_dump() for ws in persona.workspaces], persona


def _report_unavailable(exc: Exception) -> None:
    """Сообщение без значений из файла: имя класса и безопасный текст PersonaConfigError."""
    print(
        "\n❌ SECURITY SHIELD ERROR: данные рабочих пространств недоступны "
        f"({type(exc).__name__}). Проверьте config/persona.yaml или PERSONA_CONFIG_PATH.\n"
    )
    try:
        from src.persona.models import PersonaConfigError
    except Exception:
        return
    if isinstance(exc, PersonaConfigError):
        # Текст построен загрузчиком без входных значений (только пути и имена полей)
        print(str(exc))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Security Shield: scan staged (default) or all tracked files."
    )
    parser.add_argument("path", nargs="?", default=".", help="repository path (default: current directory)")
    parser.add_argument("--all", action="store_true", help="scan all tracked files instead of staged ones")
    args = parser.parse_args(argv)  # unknown flags exit with code 2 (fail-closed), never treated as a path
    repo = Path(args.path).resolve()

    try:
        workspaces, _persona = _load_workspaces()
    except Exception as exc:  # noqa: BLE001 - любая ошибка загрузки = проверка не пройдена
        _report_unavailable(exc)
        return 1

    return audit_repository(repo, check_staged_only=not args.all, workspaces=workspaces)


if __name__ == "__main__":
    sys.exit(main())
