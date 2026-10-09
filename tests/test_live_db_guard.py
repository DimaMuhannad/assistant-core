"""Доказательство изоляции боевой БД в тестах (GATE-02).

Боевой файл тесты не открывают: его путь только сравнивается строкой, а страж
обязан сработать ДО реального обращения к файлу.
"""

import importlib
import os
import sqlite3
from pathlib import Path

import aiosqlite
import dotenv
import pytest

from . import live_db_guard
from .live_db_guard import LIVE_DB_PATHS, LiveDatabaseAccessError, is_live_db_path

LIVE_DATA_DB = str(live_db_guard.CORE_DIR / "data" / "assistant.db")
LIVE_ROOT_DB = str(live_db_guard.CORE_DIR / "assistant.db")
SIDECARS = ("", "-wal", "-shm", "-journal")


# --- is_live_db_path: какие формы пути считаются боевыми ---


@pytest.mark.parametrize("sidecar", SIDECARS)
@pytest.mark.parametrize("base", [LIVE_DATA_DB, LIVE_ROOT_DB])
def test_is_live_db_path_true_for_live_files_and_sidecars(base: str, sidecar: str):
    assert is_live_db_path(base + sidecar) is True


def test_live_db_paths_constant_lists_both_live_files():
    assert {str(p) for p in LIVE_DB_PATHS} == {LIVE_DATA_DB, LIVE_ROOT_DB}


def test_is_live_db_path_true_for_file_uri_with_query():
    assert is_live_db_path(f"file:{LIVE_DATA_DB}?mode=ro") is True
    assert is_live_db_path(f"file://{LIVE_ROOT_DB}?mode=ro&cache=shared") is True


def test_is_live_db_path_true_for_relative_paths_resolved_from_cwd(monkeypatch):
    monkeypatch.chdir(live_db_guard.CORE_DIR)
    assert is_live_db_path("data/assistant.db") is True
    assert is_live_db_path("./assistant.db") is True
    monkeypatch.chdir(live_db_guard.CORE_DIR / "data")
    assert is_live_db_path("assistant.db") is True
    assert is_live_db_path("assistant.db-wal") is True


def test_is_live_db_path_accepts_bytes_and_pathlike():
    assert is_live_db_path(os.fsencode(LIVE_DATA_DB)) is True
    assert is_live_db_path(Path(LIVE_ROOT_DB)) is True


def test_is_live_db_path_false_for_safe_inputs(tmp_path: Path):
    assert is_live_db_path(str(tmp_path / "assistant.db")) is False
    assert is_live_db_path(str(tmp_path / "other.db")) is False
    assert is_live_db_path(":memory:") is False
    assert is_live_db_path(None) is False
    assert is_live_db_path(3) is False


# --- страж на реальных вызовах (audit hook) ---


@pytest.mark.parametrize("sidecar", SIDECARS)
@pytest.mark.parametrize("base", [LIVE_DATA_DB, LIVE_ROOT_DB])
def test_builtin_open_of_live_path_is_blocked(base: str, sidecar: str):
    with pytest.raises(LiveDatabaseAccessError):
        open(base + sidecar, "rb")


def test_sqlite3_connect_to_live_path_is_blocked():
    with pytest.raises(LiveDatabaseAccessError):
        sqlite3.connect(LIVE_DATA_DB)
    with pytest.raises(LiveDatabaseAccessError):
        sqlite3.connect(LIVE_ROOT_DB)


def test_sqlite3_connect_file_uri_to_live_path_is_blocked():
    with pytest.raises(LiveDatabaseAccessError):
        sqlite3.connect(f"file:{LIVE_DATA_DB}?mode=ro", uri=True)


def test_relative_path_to_live_db_is_blocked(monkeypatch):
    monkeypatch.chdir(live_db_guard.CORE_DIR)
    with pytest.raises(LiveDatabaseAccessError):
        sqlite3.connect("data/assistant.db")
    with pytest.raises(LiveDatabaseAccessError):
        open("assistant.db", "rb")


async def test_aiosqlite_connect_to_live_path_is_blocked():
    with pytest.raises(LiveDatabaseAccessError):
        async with aiosqlite.connect(LIVE_DATA_DB):
            pass


def test_error_message_is_russian_and_names_only_the_path():
    with pytest.raises(LiveDatabaseAccessError) as excinfo:
        sqlite3.connect(LIVE_DATA_DB)
    message = str(excinfo.value)
    assert LIVE_DATA_DB in message
    assert "tmp_path" in message


def test_non_live_database_still_works(tmp_path: Path):
    db_path = tmp_path / "assistant.db"  # то же имя, но не боевой каталог
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    assert conn.execute("SELECT x FROM t").fetchone() == (1,)
    conn.close()
    with open(db_path, "rb") as fh:
        assert fh.read(6) == b"SQLite"


async def test_non_live_database_works_through_aiosqlite(tmp_path: Path):
    async with aiosqlite.connect(tmp_path / "other.db") as conn:
        await conn.execute("CREATE TABLE t (x INTEGER)")
        await conn.commit()


def test_install_is_idempotent(monkeypatch):
    calls: list = []
    monkeypatch.setattr(live_db_guard.sys, "addaudithook", lambda hook: calls.append(hook))
    live_db_guard.install()  # conftest уже поставил хук: повтор ничего не регистрирует
    assert calls == []
    monkeypatch.setattr(live_db_guard, "_installed", False)
    live_db_guard.install()
    live_db_guard.install()
    assert len(calls) == 1


# --- src.config: приоритет явного пути БД над load_dotenv(override=True) ---


def _reload_config():
    import src.config

    return importlib.reload(src.config)


def test_test_process_uses_isolated_db_path():
    import src.config

    assert os.environ.get("ASSISTANT_DB_PATH_OVERRIDE")
    assert src.config.SQLITE_DB_PATH == os.environ["ASSISTANT_DB_PATH_OVERRIDE"]
    assert is_live_db_path(src.config.SQLITE_DB_PATH) is False


def test_db_path_override_survives_load_dotenv_override(monkeypatch, tmp_path: Path):
    import src.config

    before = src.config.SQLITE_DB_PATH
    isolated = str(tmp_path / "isolated.db")
    monkeypatch.setenv("ASSISTANT_DB_PATH_OVERRIDE", isolated)

    def fake_load_dotenv(*args, **kwargs):
        # эмуляция load_dotenv(..., override=True): боевой URL и враждебное значение самой переменной
        monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{LIVE_DATA_DB}")
        monkeypatch.setenv("ASSISTANT_DB_PATH_OVERRIDE", LIVE_DATA_DB)
        return True

    monkeypatch.setattr(dotenv, "load_dotenv", fake_load_dotenv)
    try:
        config = _reload_config()
        assert config.SQLITE_DB_PATH == isolated
        assert config.DATABASE_URL == f"sqlite+aiosqlite:///{isolated}"
    finally:
        monkeypatch.undo()
        restored = _reload_config()
    assert restored.SQLITE_DB_PATH == before


def test_db_path_without_override_is_taken_from_dotenv(monkeypatch, tmp_path: Path):
    import src.config

    before = src.config.SQLITE_DB_PATH
    from_dotenv = str(tmp_path / "from_dotenv.db")
    monkeypatch.delenv("ASSISTANT_DB_PATH_OVERRIDE", raising=False)

    def fake_load_dotenv(*args, **kwargs):
        monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{from_dotenv}")
        return True

    monkeypatch.setattr(dotenv, "load_dotenv", fake_load_dotenv)
    try:
        config = _reload_config()
        assert config.SQLITE_DB_PATH == from_dotenv  # поведение рантайма не изменено
    finally:
        monkeypatch.undo()
        restored = _reload_config()
    assert restored.SQLITE_DB_PATH == before
