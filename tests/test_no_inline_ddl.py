"""Защитный тест: в src/ нет инлайн-DDL без белого списка (D-11, DAT-01).

Любое создание таблиц, индексов, триггеров и альтеров обязано производиться
исключительно через версионированные миграции assistant-shared.
Сканер не имеет белого списка и проверяет все файлы src/.
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path
import re

import pytest

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"

# Регулярное выражение для обнаружения DDL операторов SQLite
DDL_PATTERN = re.compile(
    r"\b(?:CREATE\s+(?:(?:UNIQUE|TEMPORARY|TEMP|VIRTUAL)\s+)*(?:TABLE|INDEX|TRIGGER)|ALTER\s+TABLE)\b",
    re.IGNORECASE,
)

IGNORED_FILE_EXTENSIONS = (".pyc", ".pyo", ".so")


def find_inline_ddl(root: Path | str) -> list[str]:
    """Сканирует каталог на наличие инлайн-DDL операторов.

    Принимает ровно один аргумент root.
    Белого списка, исключений по файлам или путям нет (D-11).
    Возвращает список находок вида 'относительный_путь:номер_строки'.
    """
    root_path = Path(root).resolve()
    findings: list[str] = []

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Игнорируем только каталоги кеша байткода
        if "__pycache__" in dirnames:
            dirnames.remove("__pycache__")

        for filename in filenames:
            if filename.endswith(IGNORED_FILE_EXTENSIONS):
                continue

            full_file_path = Path(dirpath) / filename
            try:
                content = full_file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            rel_path = full_file_path.relative_to(root_path).as_posix()

            for match in DDL_PATTERN.finditer(content):
                line_no = content[: match.start()].count("\n") + 1
                findings.append(f"{rel_path}:{line_no}")

    return sorted(findings)


def count_scanned_files(root: Path | str) -> int:
    """Возвращает число просмотренных файлов в каталоге."""
    root_path = Path(root).resolve()
    count = 0
    for dirpath, dirnames, filenames in os.walk(root_path):
        if "__pycache__" in dirnames:
            dirnames.remove("__pycache__")
        for filename in filenames:
            if not filename.endswith(IGNORED_FILE_EXTENSIONS):
                count += 1
    return count


def test_src_has_no_inline_ddl() -> None:
    """В реальном каталоге src/ нет инлайн-DDL операторов (проверено не менее 50 файлов)."""
    assert SRC_ROOT.exists(), f"Каталог {SRC_ROOT} не найден!"

    scanned_count = count_scanned_files(SRC_ROOT)
    assert scanned_count >= 50, (
        f"Просмотрено слишком мало файлов: {scanned_count} (ожидалось не менее 50)"
    )

    findings = find_inline_ddl(SRC_ROOT)
    assert findings == [], f"Обнаружен инлайн-DDL в коде src/: {findings}"


DDL_SYNTHETIC_VARIANTS = [
    ("CREATE TABLE", "CREATE TABLE dummy (id INTEGER PRIMARY KEY);"),
    ("create table lowercase", "create table test_table (name text);"),
    ("CREATE UNIQUE INDEX", "CREATE UNIQUE INDEX idx_uniq ON users(email);"),
    ("CREATE INDEX", "CREATE INDEX idx_simple ON items(created_at);"),
    ("CREATE VIRTUAL TABLE", "CREATE VIRTUAL TABLE docs_fts USING fts5(content);"),
    ("CREATE TRIGGER", "CREATE TRIGGER update_time AFTER UPDATE ON tbl BEGIN SELECT 1; END;"),
    ("CREATE TEMP TABLE", "CREATE TEMP TABLE temp_store (x INT);"),
    ("ALTER TABLE", "ALTER TABLE accounts ADD COLUMN status TEXT;"),
    ("multiline with tabs", "CREATE\n\t  TABLE\n\t  tab_custom (id INT);"),
    ("inside python string literal", 'QUERY = """\nCREATE TABLE nested_str (val TEXT);\n"""'),
]


@pytest.mark.parametrize("variant_name,snippet", DDL_SYNTHETIC_VARIANTS)
def test_scanner_detects_every_ddl_variant(
    variant_name: str, snippet: str, tmp_path: Path
) -> None:
    """Самопроверка: каждый из вариантов DDL гарантированно обнаруживается сканером."""
    test_file = tmp_path / "synthetic_code.py"
    test_file.write_text(snippet, encoding="utf-8")

    findings = find_inline_ddl(tmp_path)
    assert len(findings) == 1, (
        f"Вариант '{variant_name}' не был обнаружен сканером: {findings}"
    )
    assert findings[0].startswith("synthetic_code.py:")


def test_scanner_ignores_prose_and_caches(tmp_path: Path) -> None:
    """Проза («Create all tables») и файлы внутри __pycache__ не дают находок."""
    # 1. Обычный текст / документация / комментарий со словами, не являющимися оператором DDL
    prose_file = tmp_path / "notes.txt"
    prose_file.write_text(
        "Please create all tables carefully. We will create many indexes later.\n",
        encoding="utf-8",
    )

    # 2. Файл внутри __pycache__ с DDL-текстом (должен игнорироваться)
    cache_dir = tmp_path / "__pycache__"
    cache_dir.mkdir()
    cache_file = cache_dir / "bytecode_dump.py"
    cache_file.write_text("CREATE TABLE ignored_table (id INT);\n", encoding="utf-8")

    findings = find_inline_ddl(tmp_path)
    assert findings == [], f"Сканер дал ложные срабатывания: {findings}"


def test_scanner_has_no_allowlist_parameter() -> None:
    """Сигнатура find_inline_ddl принимает ровно один аргумент root; белого списка нет."""
    sig = inspect.signature(find_inline_ddl)
    params = list(sig.parameters.keys())
    assert len(params) == 1, f"Ожидался 1 параметр, найдено: {params}"
    assert params[0] == "root", f"Параметр должен называться 'root', получено: {params[0]}"
