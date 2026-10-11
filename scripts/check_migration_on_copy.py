#!/usr/bin/env python3
"""Проверка миграции SQLite на герметичной копии БД (DAT-01, D-05).

Гарантии безопасности:
1. Источник открывается строго в режиме 'mode=ro' (read-only) через sqlite3 backup API и logical_hash.
2. Копия базы данных создаётся во временном каталоге с правами 0700 вне дерева git.
3. Миграции применяются ИСКЛЮЧИТЕЛЬНО к копии базы данных.
4. Логический хеш источника до и после проверки сравнивается для гарантии неизменности.
5. Временный каталог копии всегда удаляется после завершения (в блоке finally).
6. Содержимое строк никогда не печатается в вывод (только имена объектов, счётчики и префиксы хешей).

Запуск:
    .venv/bin/python scripts/check_migration_on_copy.py --source data/assistant.db
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile
from typing import Any

from assistant_shared.db.migrator import MIGRATIONS_DIR, run_migrations

BOT_UI_TABLES: tuple[str, ...] = (
    "bot_command_settings",
    "bot_custom_aliases",
    "dialog_feedback_log",
)
ATTEMPTS_DEFAULT: int = 3
SHORT_HASH_LEN: int = 12

# Загрузка scripts/deploy.py через importlib для использования make_db_copy
DEPLOY_SCRIPT_PATH = Path(__file__).resolve().parent / "deploy.py"


def _load_deploy_module():
    spec = importlib.util.spec_from_file_location("deploy_module", DEPLOY_SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Не удалось загрузить deploy.py из {DEPLOY_SCRIPT_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["deploy_module"] = mod
    spec.loader.exec_module(mod)
    return mod


_deploy = _load_deploy_module()
make_db_copy = _deploy.make_db_copy


@dataclass
class MigrationCheckReport:
    """Датакласс итогового отчёта проверки миграции на копии БД."""

    ok: bool
    check_rows: list[tuple[str, bool, str]]
    applied_versions: list[str]
    source_versions_before: list[str]
    source_versions_after: list[str]
    hash_before: str
    hash_after: str
    bot_table_counts: dict[str, int]
    issues: list[str]


def logical_hash(db: Path | str) -> str:
    """Вычисляет SHA-256 логического дампа БД (соединение строго mode=ro)."""
    db_path = Path(db).resolve()
    conn = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True, timeout=30.0)
    try:
        conn.execute("BEGIN")
        digest = hashlib.sha256()
        for line in conn.iterdump():
            digest.update(line.encode("utf-8", "surrogatepass"))
            digest.update(b"\n")
        return digest.hexdigest()
    finally:
        conn.close()


def _normalize_sql(sql: str | None) -> str:
    if not sql:
        return ""
    s = re.sub(r"\s+", " ", sql.strip().lower())
    s = re.sub(r"\s*([(),;])\s*", r"\1", s)
    return s.rstrip(";")


def snapshot(db: Path | str) -> dict[str, dict[str, Any]]:
    """Снимок структуры и контрольных сумм таблиц (кроме schema_migrations и sqlite_*)."""
    db_path = Path(db).resolve()
    # Копия может открываться без mode=ro, но для единообразия открываем стандартно
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    try:
        cursor = conn.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' AND name != 'schema_migrations' AND sql IS NOT NULL "
            "ORDER BY name ASC;"
        )
        objects: dict[str, dict[str, Any]] = {}
        for obj_type, name, sql in cursor.fetchall():
            info: dict[str, Any] = {
                "type": obj_type,
                "sql": _normalize_sql(sql),
                "count": 0,
                "data_hash": "",
            }
            if obj_type == "table":
                # Считаем количество строк
                c_cur = conn.execute(f"SELECT COUNT(*) FROM {name};")
                info["count"] = c_cur.fetchone()[0]

                # Хешируем отсортированные строки для проверки неизменности данных
                rows_cur = conn.execute(f"SELECT * FROM {name};")
                rows = sorted(repr(r) for r in rows_cur.fetchall())
                h = hashlib.sha256()
                for r_repr in rows:
                    h.update(r_repr.encode("utf-8", "surrogatepass"))
                    h.update(b"\n")
                info["data_hash"] = h.hexdigest()

            objects[name] = info
        return objects
    finally:
        conn.close()


def list_versions(db: Path | str) -> list[str]:
    """Список применённых версий из schema_migrations (строго mode=ro)."""
    db_path = Path(db).resolve()
    conn = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True, timeout=30.0)
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations';")
        if not cur.fetchone():
            return []
        v_cur = conn.execute("SELECT version FROM schema_migrations ORDER BY version ASC;")
        return [row[0] for row in v_cur.fetchall()]
    finally:
        conn.close()


def compare_snapshots(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
    expected_new: tuple[str, ...],
) -> list[str]:
    """Сравнивает снимки до и после миграции на копии.

    Возвращает список описаний обнаруженных проблем по-русски.
    Никакое содержимое строк в сообщения не попадает.
    """
    issues: list[str] = []

    # 1. Проверяем объекты, существовавшие до миграции
    for name, b_info in before.items():
        if name not in after:
            issues.append(f"Объект '{name}' ({b_info['type']}) исчез после миграции")
            continue

        a_info = after[name]
        if b_info["sql"] != a_info["sql"]:
            issues.append(f"DDL объекта '{name}' ({b_info['type']}) изменился после миграции")

        if b_info["type"] == "table":
            if b_info["count"] != a_info["count"]:
                issues.append(
                    f"Число строк таблицы '{name}' изменилось: было {b_info['count']}, стало {a_info['count']}"
                )
            elif b_info["data_hash"] != a_info["data_hash"]:
                issues.append(f"Содержимое строк таблицы '{name}' изменилось после миграции")

    # 2. Проверяем новые объекты
    for name, a_info in after.items():
        if name not in before:
            if name not in expected_new:
                issues.append(
                    f"Обнаружен неожиданный новый объект '{name}' ({a_info['type']}) после миграции"
                )

    return issues


def check_migration_on_copy(
    source: Path | str,
    *,
    migrations_dir: Path | None = None,
    attempts: int = ATTEMPTS_DEFAULT,
    expected_new: tuple[str, ...] = BOT_UI_TABLES,
) -> MigrationCheckReport:
    """Выполняет герметичную проверку миграции на копии базы данных.

    Источник открывается строго mode=ro. Копия создаётся во временном каталоге
    и удаляется в finally. Повторяется до attempts раз при дрейфе хеша источника.
    """
    source_path = Path(source).resolve()
    last_report: MigrationCheckReport | None = None

    for attempt in range(1, attempts + 1):
        check_rows: list[tuple[str, bool, str]] = []
        issues: list[str] = []
        bot_counts: dict[str, int] = {}
        applied_versions: list[str] = []
        source_versions_before: list[str] = []
        source_versions_after: list[str] = []

        # 1. Замер хеша источника ДО
        try:
            hash_before = logical_hash(source_path)
            source_versions_before = list_versions(source_path)
        except Exception as e:
            return MigrationCheckReport(
                ok=False,
                check_rows=[("Чтение источника до проверки", False, f"{type(e).__name__}: {e}")],
                applied_versions=[],
                source_versions_before=[],
                source_versions_after=[],
                hash_before="",
                hash_after="",
                bot_table_counts={},
                issues=[f"Не удалось прочитать источник: {e}"],
            )

        # 2. Создание временного каталога (0700)
        temp_dir = Path(tempfile.mkdtemp(prefix="check_mig_copy_"))
        try:
            # 3. Создание копии через deploy.make_db_copy (mode=ro)
            now = datetime.now(timezone.utc)
            copy_path = make_db_copy(source_path, temp_dir, now)

            # 4. Снимок копии ДО
            snap_before = snapshot(copy_path)

            # 5. Применение миграций к копии
            try:
                applied_versions = run_migrations(copy_path, migrations_dir=migrations_dir)
            except (sqlite3.Error, OSError, FileNotFoundError) as err:
                err_msg = f"{type(err).__name__}: {str(err)[:160]}"
                issues.append(f"Ошибка применения миграции: {err_msg}")
                applied_versions = []

            # 6. Снимок копии ПОСЛЕ
            snap_after = snapshot(copy_path)
            copy_versions_after = list_versions(copy_path)

            # Счётчики строк трёх таблиц
            for tbl in BOT_UI_TABLES:
                if tbl in snap_after:
                    bot_counts[tbl] = snap_after[tbl]["count"]
                else:
                    bot_counts[tbl] = 0

            # 7. Замер хеша источника ПОСЛЕ
            hash_after = logical_hash(source_path)
            source_versions_after = list_versions(source_path)

            # Проверка дрейфа хеша источника
            if hash_before != hash_after:
                if attempt < attempts:
                    continue  # Повторная попытка в тихом окне
                issues.append(
                    "Дрейф хеша источника: логическое содержимое изменилось во время проверки "
                    "(возможна фоновая запись работающего сервиса)"
                )

            # Сравнение снимков
            snapshot_issues = compare_snapshots(snap_before, snap_after, expected_new)
            issues.extend(snapshot_issues)

            # Формирование строк проверок
            check_rows.append(
                (
                    "Неизменность источника (mode=ro)",
                    hash_before == hash_after,
                    f"до: {hash_before[:SHORT_HASH_LEN]}, после: {hash_after[:SHORT_HASH_LEN]}",
                )
            )
            check_rows.append(
                (
                    "Применение миграций на копии",
                    not any("Ошибка применения" in iss for iss in issues),
                    f"применено: {applied_versions or '[]'}",
                )
            )
            check_rows.append(
                (
                    "Целостность существующих данных",
                    not any("Содержимое" in iss or "Число строк" in iss for iss in issues),
                    "данные таблиц до и после совпадают",
                )
            )
            check_rows.append(
                (
                    "Отсутствие посторонних объектов",
                    not any("неожиданный" in iss for iss in issues),
                    f"новые таблицы: {[t for t in BOT_UI_TABLES if t in snap_after and t not in snap_before]}",
                )
            )

            ok = len(issues) == 0
            last_report = MigrationCheckReport(
                ok=ok,
                check_rows=check_rows,
                applied_versions=applied_versions,
                source_versions_before=source_versions_before,
                source_versions_after=source_versions_after,
                hash_before=hash_before,
                hash_after=hash_after,
                bot_table_counts=bot_counts,
                issues=issues,
            )
            if ok:
                return last_report

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    return last_report or MigrationCheckReport(
        ok=False,
        check_rows=[],
        applied_versions=[],
        source_versions_before=[],
        source_versions_after=[],
        hash_before="",
        hash_after="",
        bot_table_counts={},
        issues=["Исчерпаны все попытки проверки"],
    )


def render_report(report: MigrationCheckReport) -> str:
    """Рендерит отчёт о проверке миграции в текстовую таблицу на русском языке."""
    lines: list[str] = [
        "==================================================================",
        "  ОТЧЁТ ПРОВЕРКИ МИГРАЦИИ НА КОПИИ БД (DAT-01, D-05)",
        "==================================================================",
        f"Хеш источника до: {report.hash_before[:SHORT_HASH_LEN]}",
        f"Хеш источника после: {report.hash_after[:SHORT_HASH_LEN]}",
        f"Версии до проверки:  {report.source_versions_before}",
        f"Применено на копии:  {report.applied_versions or '[]'}",
        "------------------------------------------------------------------",
        "Счётчики строк таблиц бота:",
    ]
    for tbl, count in sorted(report.bot_table_counts.items()):
        lines.append(f"  • {tbl}: {count} строк")

    lines.append("------------------------------------------------------------------")
    lines.append("Результаты проверок:")
    for name, ok, detail in report.check_rows:
        mark = "✓" if ok else "✗"
        lines.append(f"  [{mark}] {name} ({detail})")

    if report.issues:
        lines.append("------------------------------------------------------------------")
        lines.append("Обнаруженные замечания:")
        for iss in report.issues:
            lines.append(f"  ! {iss}")

    lines.append("==================================================================")
    verdict = "ИТОГ: ЗЕЛЁНЫЙ" if report.ok else "ИТОГ: КРАСНЫЙ"
    lines.append(f"  {verdict}")
    lines.append("==================================================================")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Проверка миграции SQLite на герметичной копии БД (DAT-01, D-05)."
    )
    parser.add_argument(
        "--source",
        required=True,
        type=Path,
        help="Путь к файлу проверяемой SQLite БД (обязательный аргумент)",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=ATTEMPTS_DEFAULT,
        help=f"Число попыток при дрейфе хеша источника (по умолчанию {ATTEMPTS_DEFAULT})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    source_path = args.source
    # Проверка пути: существование, файл, не символическая ссылка
    if not source_path.exists():
        sys.stderr.write(f"Ошибка: источник {source_path} не существует.\n")
        return 2

    if source_path.is_symlink():
        sys.stderr.write(f"Ошибка: источник {source_path} является символической ссылкой.\n")
        return 2

    if not source_path.is_file():
        sys.stderr.write(f"Ошибка: источник {source_path} не является обычным файлом.\n")
        return 2

    report = check_migration_on_copy(source_path, attempts=args.attempts)
    sys.stdout.write(render_report(report) + "\n")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
