"""Тесты scripts/check_migration_on_copy.py: проверка миграции на копии БД (DAT-01, D-05).

Все тесты герметичны и используют синтетический источник формы боевой БД.
Боевая БД в тестах никогда не открывается (страж GATE-02 активен).
"""

from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from typing import Any
from unittest.mock import patch

import pytest

from assistant_shared.db.migrator import MIGRATIONS_DIR, run_migrations

CHECK_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_migration_on_copy.py"

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

SECRET_MARKER = "SUPER_SECRET_MARKER_FORBIDDEN_IN_OUTPUT_42791"


def _load_check_script():
    """Загружает модуль скрипта по пути через importlib с уникальным именем."""
    spec = importlib.util.spec_from_file_location("check_migration_under_test", CHECK_SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Не удалось загрузить модуль из {CHECK_SCRIPT_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_migration_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def make_legacy_source(directory: Path) -> Path:
    """Создаёт синтетический источник формы боевой БД (публичная функция, D-05).

    Включает:
    - Миграции 0001 и 0002 из assistant-shared (каталог без 0003).
    - Три таблицы бота, созданные дословным прежним инлайн-DDL.
    - Строки с кириллицей, маркерным текстом и автоинкрементом.
    - Режим WAL.
    """
    custom_mig_dir = directory / "migrations_without_0003"
    custom_mig_dir.mkdir(parents=True, exist_ok=True)
    for sql_file in MIGRATIONS_DIR.glob("*.sql"):
        if not sql_file.name.startswith("0003"):
            shutil.copy(sql_file, custom_mig_dir / sql_file.name)

    source_path = directory / "synthetic_legacy_source.db"
    run_migrations(source_path, migrations_dir=custom_mig_dir)

    with sqlite3.connect(str(source_path)) as conn:
        for ddl in LEGACY_BOT_UI_DDL.values():
            conn.execute(ddl)

        conn.execute(
            "INSERT INTO bot_command_settings (command_name, is_enabled, custom_description) "
            "VALUES (?, ?, ?);",
            ("cmd_help", 1, f"Справка с маркером {SECRET_MARKER}"),
        )
        conn.execute(
            "INSERT INTO bot_custom_aliases (alias, canonical_command) VALUES (?, ?);",
            ("хелп", "cmd_help"),
        )
        conn.execute(
            "INSERT INTO dialog_feedback_log (message_id, user_id, feedback_type) "
            "VALUES (?, ?, ?);",
            (1001, 2002, f"positive_feedback_{SECRET_MARKER}"),
        )
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.commit()

    return source_path


def test_green_on_legacy_shaped_source(tmp_path: Path) -> None:
    """Синтетический источник формы боевой даёт ok=True, 0003 no-op на данных."""
    script = _load_check_script()
    source = make_legacy_source(tmp_path / "src_test")

    report = script.check_migration_on_copy(source)
    assert report.ok is True
    assert report.applied_versions == ["0003_bot_commands_and_feedback"]
    assert report.hash_before == report.hash_after
    assert report.bot_table_counts["bot_command_settings"] == 1
    assert report.bot_table_counts["bot_custom_aliases"] == 1
    assert report.bot_table_counts["dialog_feedback_log"] == 1


def test_source_is_never_modified(tmp_path: Path) -> None:
    """Источник и его логический хеш неизменны; все подключения к нему идут с mode=ro."""
    script = _load_check_script()
    source = make_legacy_source(tmp_path / "src_ro")

    hash_initial = script.logical_hash(source)

    real_connect = sqlite3.connect
    connect_calls: list[str] = []

    def tracking_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        if args:
            connect_calls.append(str(args[0]))
        elif "database" in kwargs:
            connect_calls.append(str(kwargs["database"]))
        return real_connect(*args, **kwargs)

    with patch("sqlite3.connect", side_effect=tracking_connect):
        report = script.check_migration_on_copy(source)

    assert report.ok is True
    assert script.logical_hash(source) == hash_initial

    # Все вызовы connect к файлу источника обязаны содержать mode=ro
    source_str = str(source.resolve())
    for call_target in connect_calls:
        if source_str in call_target or source.name in call_target:
            assert "mode=ro" in call_target, (
                f"Обращение к источнику без mode=ro: {call_target}"
            )


def test_already_migrated_source_is_green(tmp_path: Path) -> None:
    """Уже мигрированный источник (после рестарта) даёт ok=True и applied=[]."""
    script = _load_check_script()
    source = tmp_path / "already_migrated.db"
    run_migrations(source)

    report = script.check_migration_on_copy(source)
    assert report.ok is True
    assert report.applied_versions == []
    assert "0003_bot_commands_and_feedback" in report.source_versions_before
    assert report.source_versions_before == report.source_versions_after


def test_red_when_migration_changes_existing_data(tmp_path: Path) -> None:
    """Миграция, меняющая существующие данные, даёт ok=False с именем таблицы."""
    script = _load_check_script()
    source = make_legacy_source(tmp_path / "data_change")
    hash_orig = script.logical_hash(source)

    # Создаём зловредную миграцию, меняющую данные
    bad_mig_dir = tmp_path / "bad_data_migrations"
    bad_mig_dir.mkdir()
    for sql_file in MIGRATIONS_DIR.glob("*.sql"):
        if not sql_file.name.startswith("0003"):
            shutil.copy(sql_file, bad_mig_dir / sql_file.name)
    (bad_mig_dir / "0003_mutate_data.sql").write_text(
        "UPDATE bot_command_settings SET custom_description = 'MUTATED';\n",
        encoding="utf-8",
    )

    report = script.check_migration_on_copy(source, migrations_dir=bad_mig_dir)
    assert report.ok is False
    assert any("bot_command_settings" in issue for issue in report.issues)
    assert script.logical_hash(source) == hash_orig


def test_red_when_migration_fails(tmp_path: Path) -> None:
    """Миграция с синтаксической ошибкой даёт ok=False без исключения наружу."""
    script = _load_check_script()
    source = make_legacy_source(tmp_path / "syntax_err")

    broken_mig_dir = tmp_path / "broken_migrations"
    broken_mig_dir.mkdir()
    for sql_file in MIGRATIONS_DIR.glob("*.sql"):
        if not sql_file.name.startswith("0003"):
            shutil.copy(sql_file, broken_mig_dir / sql_file.name)
    (broken_mig_dir / "0003_syntax_error.sql").write_text(
        "SYNTAX ERROR NOT VALID SQL;\n",
        encoding="utf-8",
    )

    report = script.check_migration_on_copy(source, migrations_dir=broken_mig_dir)
    assert report.ok is False
    assert any("ошибка" in issue.lower() or "error" in issue.lower() for issue in report.issues)


def test_red_on_unexpected_new_object(tmp_path: Path) -> None:
    """Появление посторонней таблицы или индекса даёт ok=False с именами объектов."""
    script = _load_check_script()
    source = make_legacy_source(tmp_path / "unexpected_obj")

    extra_mig_dir = tmp_path / "extra_migrations"
    extra_mig_dir.mkdir()
    for sql_file in MIGRATIONS_DIR.glob("*.sql"):
        shutil.copy(sql_file, extra_mig_dir / sql_file.name)
    (extra_mig_dir / "0004_unexpected.sql").write_text(
        "CREATE TABLE unexpected_tbl (id INT);\nCREATE INDEX idx_unexp ON unexpected_tbl(id);\n",
        encoding="utf-8",
    )

    report = script.check_migration_on_copy(source, migrations_dir=extra_mig_dir)
    assert report.ok is False
    assert any("unexpected_tbl" in issue for issue in report.issues)


def test_source_hash_drift_retries_then_red(tmp_path: Path) -> None:
    """Дрейф хеша источника вызывает повторные попытки (до attempts); различие даёт Red."""
    script = _load_check_script()
    source = make_legacy_source(tmp_path / "drift_src")

    call_count = 0
    real_logical_hash = script.logical_hash

    def drifting_hash(db: Path) -> str:
        nonlocal call_count
        call_count += 1
        # Меняем хеш между замерами "до" и "после"
        return f"hash_{call_count}"

    with patch.object(script, "logical_hash", side_effect=drifting_hash):
        report = script.check_migration_on_copy(source, attempts=3)

    assert report.ok is False
    assert any("хеш" in issue.lower() or "дрейф" in issue.lower() for issue in report.issues)
    assert call_count >= 6  # 3 попытки * 2 замера (до и после)

    # Если дрейф был только в первой попытке, вторая должна быть зеленой
    call_count_2 = 0

    def drift_once_hash(db: Path) -> str:
        nonlocal call_count_2
        call_count_2 += 1
        if call_count_2 == 1:
            return "hash_attempt1_before"
        if call_count_2 == 2:
            return "hash_attempt1_after"
        # Со второй попытки хеш стабилен
        return "stable_hash_from_attempt2"

    with patch.object(script, "logical_hash", side_effect=drift_once_hash):
        report_2 = script.check_migration_on_copy(source, attempts=3)

    assert report_2.ok is True


def test_temp_directory_removed(tmp_path: Path) -> None:
    """Временный каталог копии всегда удаляется, в том числе при красном исходе."""
    script = _load_check_script()
    source = make_legacy_source(tmp_path / "tmp_cleanup")

    created_temp_dirs: list[Path] = []
    real_mkdtemp = tempfile.mkdtemp

    def tracking_mkdtemp(*args: Any, **kwargs: Any) -> str:
        d = real_mkdtemp(*args, **kwargs)
        created_temp_dirs.append(Path(d))
        return d

    with patch("tempfile.mkdtemp", side_effect=tracking_mkdtemp):
        report = script.check_migration_on_copy(source)

    assert report.ok is True
    assert len(created_temp_dirs) > 0
    for d in created_temp_dirs:
        assert not d.exists(), f"Временный каталог {d} не был удалён!"


def test_report_never_prints_row_content(tmp_path: Path) -> None:
    """Маркерный текст строк никогда не попадает в report и вывод main()."""
    script = _load_check_script()
    source = make_legacy_source(tmp_path / "leak_check")

    report = script.check_migration_on_copy(source)
    rendered = script.render_report(report)
    assert SECRET_MARKER not in rendered

    stdout_capture = StringIO()
    with patch("sys.stdout", stdout_capture):
        rc = script.main(["--source", str(source)])

    assert rc == 0
    assert SECRET_MARKER not in stdout_capture.getvalue()


def test_cli_exit_codes_and_russian_verdict(tmp_path: Path) -> None:
    """Коды выхода CLI: 0 (зелёный), 1 (красный), 2 (неверный путь или нет аргументов)."""
    script = _load_check_script()
    source = make_legacy_source(tmp_path / "cli_test")

    # 1. Успех: rc=0, "ИТОГ: ЗЕЛЁНЫЙ"
    out_ok = StringIO()
    with patch("sys.stdout", out_ok):
        rc = script.main(["--source", str(source)])
    assert rc == 0
    assert "ИТОГ: ЗЕЛЁНЫЙ" in out_ok.getvalue()
    assert "Хеш источника до:" in out_ok.getvalue()
    assert "Хеш источника после:" in out_ok.getvalue()

    # 2. Ошибки аргументов: rc=2
    with pytest.raises(SystemExit) as exc:
        script.main([])
    assert exc.value.code == 2

    # Несуществующий файл
    rc_missing = script.main(["--source", str(tmp_path / "nonexistent.db")])
    assert rc_missing == 2

    # Каталог вместо файла
    rc_dir = script.main(["--source", str(tmp_path)])
    assert rc_dir == 2

    # Символическая ссылка
    symlink_path = tmp_path / "source_symlink.db"
    symlink_path.symlink_to(source)
    rc_symlink = script.main(["--source", str(symlink_path)])
    assert rc_symlink == 2

    # 3. Красный случай: rc=1, "ИТОГ: КРАСНЫЙ"
    with patch.object(
        script,
        "check_migration_on_copy",
        return_value=script.MigrationCheckReport(
            ok=False,
            check_rows=[],
            applied_versions=[],
            source_versions_before=[],
            source_versions_after=[],
            hash_before="123456789012",
            hash_after="123456789012",
            bot_table_counts={},
            issues=["Обнаружена ошибка схемы"],
        ),
    ):
        out_fail = StringIO()
        with patch("sys.stdout", out_fail):
            rc_fail = script.main(["--source", str(source)])
        assert rc_fail == 1
        assert "ИТОГ: КРАСНЫЙ" in out_fail.getvalue()
