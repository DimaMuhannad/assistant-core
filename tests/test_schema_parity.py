"""Тест паритета схемы трёх источников и эталон формы таблиц 0003 (D-10, D-04, SCH-01).

Проверяет:
1. Идентичность схемы (таблицы, индексы, триггеры, виртуальные таблицы) из sqlite_master:
   - Ветка :memory: после init_db.
   - Ветка файловой БД после init_db.
   - Чистая БД после вызова run_migrations из assistant-shared.
2. Идентичность списка версий в schema_migrations.
3. Полное соответствие трёх таблиц 0003 (bot_command_settings, bot_custom_aliases,
   dialog_feedback_log) дословному эталону прежнего DDL (по колонкам и нормализованному SQL).
4. Чувствительность пробы: каталог миграций без 0003 гарантированно детектирует различие
   ровно в трёх таблицах.
5. Идемпотентность: повторный вызов init_db не меняет схему.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from assistant_shared.db.migrator import (
    MIGRATIONS_DIR,
    list_applied_migrations,
    run_migrations,
)
from src.storage.db import Database

BOT_UI_TABLES = (
    "bot_command_settings",
    "bot_custom_aliases",
    "dialog_feedback_log",
)

# Дословный эталон прежнего инлайн-DDL трёх таблиц бота (D-04)
LEGACY_BOT_UI_DDL: dict[str, str] = {
    "bot_command_settings": """
CREATE TABLE IF NOT EXISTS bot_command_settings (
    command_name TEXT PRIMARY KEY,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    custom_description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""",
    "bot_custom_aliases": """
CREATE TABLE IF NOT EXISTS bot_custom_aliases (
    alias TEXT PRIMARY KEY,
    canonical_command TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""",
    "dialog_feedback_log": """
CREATE TABLE IF NOT EXISTS dialog_feedback_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    feedback_type TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""",
}


def _normalize_sql(sql: str | None) -> str:
    """Нормализует SQL-оператор для канонического сравнения."""
    if not sql:
        return ""
    # Нижний регистр и схлопывание пробелов
    s = re.sub(r"\s+", " ", sql.strip().lower())
    # Удаление пробелов вокруг скобок, запятых и точек с запятой
    s = re.sub(r"\s*([(),;])\s*", r"\1", s)
    return s.rstrip(";")


async def _extract_schema_from_memory(db: Database) -> set[tuple[str, str, str]]:
    """Извлекает множество (type, name, normalized_sql) из активной in-memory БД."""
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL;"
        )
        rows = await cursor.fetchall()
        return {(r[0], r[1], _normalize_sql(r[2])) for r in rows}


def _extract_schema_from_file(db_path: Path) -> set[tuple[str, str, str]]:
    """Извлекает множество (type, name, normalized_sql) из файла SQLite."""
    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL;"
        )
        rows = cursor.fetchall()
        return {(r[0], r[1], _normalize_sql(r[2])) for r in rows}


def _extract_applied_versions_from_sqlite(db_path: Path) -> list[str]:
    """Извлекает список версий миграций из файла SQLite без applied_at."""
    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.execute("SELECT version FROM schema_migrations ORDER BY version ASC;")
        return [row[0] for row in cursor.fetchall()]


async def _extract_applied_versions_from_memory(db: Database) -> list[str]:
    """Извлекает список версий миграций из in-memory БД без applied_at."""
    async with db.connection() as conn:
        cursor = await conn.execute("SELECT version FROM schema_migrations ORDER BY version ASC;")
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


@pytest.mark.asyncio
async def test_three_sources_have_identical_schema(tmp_path: Path) -> None:
    """Множества (type, name, normalized_sql) для memory, file и shared миграций равны."""
    # 1. Источник 1: :memory: после init_db
    db_mem = Database(":memory:")
    await db_mem.init_db()
    schema_mem = await _extract_schema_from_memory(db_mem)
    await db_mem.close()

    # 2. Источник 2: файловая БД после init_db
    file_db_path = tmp_path / "file_init.db"
    db_file = Database(f"sqlite+aiosqlite:///{file_db_path}")
    await db_file.init_db()
    await db_file.close()
    schema_file = _extract_schema_from_file(file_db_path)

    # 3. Источник 3: чистая БД после run_migrations из assistant-shared
    shared_db_path = tmp_path / "shared_direct.db"
    run_migrations(shared_db_path)
    schema_shared = _extract_schema_from_file(shared_db_path)

    # Проверка, что множество не пустое и достаточно полное (не менее 80 элементов)
    assert len(schema_shared) >= 80, (
        f"Слишком мало элементов схемы: {len(schema_shared)} (ожидалось >= 80)"
    )

    # Паритет трёх источников
    assert schema_mem == schema_file, (
        f"Схема :memory: расходится с файловой БД! Diff: {schema_mem ^ schema_file}"
    )
    assert schema_file == schema_shared, (
        f"Схема файловой БД расходится с чистой БД мигратора! Diff: {schema_file ^ schema_shared}"
    )

    # Проверка наличия трёх таблиц 0003 в итоговом множестве
    created_tables = {name for (obj_type, name, _) in schema_shared if obj_type == "table"}
    for bot_tbl in BOT_UI_TABLES:
        assert bot_tbl in created_tables, f"Таблица {bot_tbl} отсутствует в схеме!"


@pytest.mark.asyncio
async def test_applied_versions_match_across_sources(tmp_path: Path) -> None:
    """Списки версий schema_migrations равны во всех источниках и каталоге."""
    expected_versions = sorted(p.stem for p in MIGRATIONS_DIR.glob("*.sql"))

    # 1. Memory
    db_mem = Database(":memory:")
    await db_mem.init_db()
    versions_mem = await _extract_applied_versions_from_memory(db_mem)
    await db_mem.close()

    # 2. File
    file_db_path = tmp_path / "file_versions.db"
    db_file = Database(f"sqlite+aiosqlite:///{file_db_path}")
    await db_file.init_db()
    await db_file.close()
    versions_file = _extract_applied_versions_from_sqlite(file_db_path)

    # 3. Shared
    shared_db_path = tmp_path / "shared_versions.db"
    run_migrations(shared_db_path)
    versions_shared = _extract_applied_versions_from_sqlite(shared_db_path)

    assert versions_mem == expected_versions
    assert versions_file == expected_versions
    assert versions_shared == expected_versions


@pytest.mark.asyncio
async def test_bot_ui_tables_match_legacy_ddl(tmp_path: Path) -> None:
    """PRAGMA table_info и нормализованный SQL трёх таблиц совпадают с эталоном прежнего DDL."""
    # Создаём базу с эталонным DDL
    legacy_db_path = tmp_path / "legacy_reference.db"
    with sqlite3.connect(str(legacy_db_path)) as conn_leg:
        for ddl in LEGACY_BOT_UI_DDL.values():
            conn_leg.execute(ddl)
        conn_leg.commit()

    # Создаём базу через init_db
    init_db_path = tmp_path / "init_check.db"
    db = Database(f"sqlite+aiosqlite:///{init_db_path}")
    await db.init_db()
    await db.close()

    with sqlite3.connect(str(init_db_path)) as conn_init, sqlite3.connect(
        str(legacy_db_path)
    ) as conn_leg:
        for tbl in BOT_UI_TABLES:
            info_init = conn_init.execute(f"PRAGMA table_info({tbl});").fetchall()
            info_leg = conn_leg.execute(f"PRAGMA table_info({tbl});").fetchall()
            assert info_init == info_leg, f"PRAGMA table_info не совпадает для {tbl}"

            sql_init = conn_init.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?;", (tbl,)
            ).fetchone()[0]
            sql_leg = conn_leg.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?;", (tbl,)
            ).fetchone()[0]
            assert _normalize_sql(sql_init) == _normalize_sql(sql_leg), (
                f"Нормализованный DDL не совпадает для {tbl}"
            )


@pytest.mark.asyncio
async def test_parity_probe_detects_missing_migration(tmp_path: Path) -> None:
    """Контроль чувствительности: каталог без 0003 выявляет расхождение ровно в трёх таблицах."""
    # 1. Каталог миграций без 0003
    custom_migrations_dir = tmp_path / "migrations_without_0003"
    custom_migrations_dir.mkdir()
    for sql_file in MIGRATIONS_DIR.glob("*.sql"):
        if not sql_file.name.startswith("0003"):
            shutil.copy(sql_file, custom_migrations_dir / sql_file.name)

    # 2. Накатываем усечённый каталог
    incomplete_db_path = tmp_path / "incomplete.db"
    run_migrations(incomplete_db_path, migrations_dir=custom_migrations_dir)
    incomplete_schema = _extract_schema_from_file(incomplete_db_path)

    # 3. Полная база через init_db
    full_db_path = tmp_path / "full.db"
    db = Database(f"sqlite+aiosqlite:///{full_db_path}")
    await db.init_db()
    await db.close()
    full_schema = _extract_schema_from_file(full_db_path)

    # Вычисляем разницу по (type, name)
    diff_objects = {
        (obj_type, name)
        for (obj_type, name, _) in (full_schema - incomplete_schema)
    }

    expected_diff = {("table", tbl) for tbl in BOT_UI_TABLES}
    assert diff_objects == expected_diff, (
        f"Различие схем должно состоять ровно из трёх таблиц 0003, получено: {diff_objects}"
    )


@pytest.mark.asyncio
async def test_repeated_init_keeps_schema(tmp_path: Path) -> None:
    """Повторный вызов init_db сохраняет неизменность схемы на обеих ветках."""
    # 1. Memory
    db_mem = Database(":memory:")
    await db_mem.init_db()
    schema_mem_1 = await _extract_schema_from_memory(db_mem)
    await db_mem.init_db()
    schema_mem_2 = await _extract_schema_from_memory(db_mem)
    await db_mem.close()
    assert schema_mem_1 == schema_mem_2, "Повторный init_db изменил схему :memory:!"

    # 2. File
    file_path = tmp_path / "file_repeat.db"
    db_file = Database(f"sqlite+aiosqlite:///{file_path}")
    await db_file.init_db()
    schema_file_1 = _extract_schema_from_file(file_path)
    await db_file.init_db()
    schema_file_2 = _extract_schema_from_file(file_path)
    await db_file.close()
    assert schema_file_1 == schema_file_2, "Повторный init_db изменил схему файловой БД!"
