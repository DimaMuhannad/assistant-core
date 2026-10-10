"""Страж боевой БД для тестов assistant-core (GATE-02).

Регистрируется через ``sys.addaudithook`` при импорте ``tests/conftest.py``. Хук нельзя снять
до конца процесса, поэтому код теста не может обойти защиту. Модуль использует только stdlib
и не импортирует ``src``: он должен ставиться раньше любого импорта приложения.

Страж ловит события ``open`` и ``sqlite3.connect`` (включая вызовы из потока aiosqlite)
и поднимает ``LiveDatabaseAccessError`` ДО обращения к файлу.
"""

from __future__ import annotations

import os
import sys
import threading
import urllib.parse
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent.parent

# Боевая БД и корневой assistant.db (происхождение неизвестно, закрыт предохранительно).
# Пути от CORE_DIR защищают текущий checkout; абсолютные пути защищают боевые файлы и тогда,
# когда тесты запущены из другого checkout, worktree или jail (WR-07, D-17).
_LIVE_RELATIVE_PATHS: tuple[Path, ...] = (
    CORE_DIR / "data" / "assistant.db",
    CORE_DIR / "assistant.db",
)
_LIVE_ABSOLUTE_PATHS: tuple[Path, ...] = (
    Path("/opt/assistant-core/data/assistant.db"),
    Path("/opt/assistant-core/assistant.db"),
)
LIVE_DB_PATHS: tuple[Path, ...] = tuple(
    dict.fromkeys(_LIVE_RELATIVE_PATHS + _LIVE_ABSOLUTE_PATHS)
)

_SIDECAR_SUFFIXES = ("", "-wal", "-shm", "-journal")

BLOCKED_REALPATHS: frozenset[str] = frozenset(
    os.path.realpath(str(path) + suffix) for path in LIVE_DB_PATHS for suffix in _SIDECAR_SUFFIXES
)

# Дешёвый префильтр: хук вызывается на каждый open(), realpath нужен только для подходящих имён.
_BASENAMES = tuple(f"assistant.db{suffix}" for suffix in _SIDECAR_SUFFIXES)

_installed = False
# Флаг повторного входа хранится по потокам: хук вызывается и из потоков aiosqlite,
# общий флаг мог бы пропустить параллельный доступ из другого потока.
_state = threading.local()


class LiveDatabaseAccessError(RuntimeError):
    """Тест попытался открыть боевую БД владельца."""


def _normalize(raw: object) -> str | None:
    """Привести аргумент open/sqlite3.connect к строке-пути; не путь даёт None."""
    if isinstance(raw, bytes):
        raw = os.fsdecode(raw)
    if isinstance(raw, os.PathLike):
        raw = os.fspath(raw)
        if isinstance(raw, bytes):
            raw = os.fsdecode(raw)
    if not isinstance(raw, str):
        return None
    if raw.startswith("file:"):
        # sqlite URI: file:/abs/path?mode=ro -> путь без схемы и параметров
        return urllib.parse.unquote(urllib.parse.urlsplit(raw).path)
    return raw


def is_live_db_path(raw: object) -> bool:
    """Истинно, если путь (в любой форме) указывает на боевую БД или её sidecar-файл.

    Символическая ссылка с произвольным именем (``x.db``) проверяется по realpath: иначе
    префильтр по имени пропустил бы её, и open() открыл бы боевой файл через ссылку (WR-07).
    """
    text = _normalize(raw)
    if not text:
        return False
    if not (text.endswith(_BASENAMES) or os.path.islink(text)):
        return False
    return os.path.realpath(text) in BLOCKED_REALPATHS


def _audit_hook(event: str, args: tuple) -> None:
    if event not in ("open", "sqlite3.connect") or not args:
        return
    if getattr(_state, "busy", False):
        return
    _state.busy = True
    try:
        if is_live_db_path(args[0]):
            raise LiveDatabaseAccessError(
                f"Тест пытался открыть боевую БД: {_normalize(args[0])}. "
                "Используйте временную базу в tmp_path."
            )
    finally:
        _state.busy = False


def install() -> None:
    """Зарегистрировать хук один раз за процесс."""
    global _installed
    if _installed:
        return
    sys.addaudithook(_audit_hook)
    _installed = True
