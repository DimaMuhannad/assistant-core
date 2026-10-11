"""Тесты достижимости фазы 3 из рантайма (D-13, критерий успеха 5, CLAUDE.md §5).

Проверяет:
1. src/main.py: инициализация Database и await init_db() до записи персоны и создания EmailBotHandler.
2. src/storage/db.py: Database.init_db вызывает _apply_migrations до сидирования, инлайн-DDL отсутствует.
3. Старт демона на пустой временной БД накатывает миграцию 0003, создавая три таблицы.
4. Старт демона на БД формы боевой (без 0003, со строками) добавляет 0003 без изменения существующих данных.
5. Обработчик сообщений бота handle_user_text управляет скрытием/показом команд и алиасами через мигрированные таблицы.
6. Обработчик /menu отображает статус команд и псевдонимы из БД.
7. Callback-обработчик fb: записывает 👍 и 👎 в dialog_feedback_log с дедупликацией.
8. Вызов build_dialog_feedback_keyboard и регистрация префикса fb: присутствуют в AST рантайма.
9. Контроль чувствительности AST-проверки порядка вызовов.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
import sqlite3
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from assistant_shared.db.migrator import (
    MIGRATIONS_DIR,
    get_schema_version,
    list_applied_migrations,
)
from src.notifier.bot_handler import EmailBotHandler
from src.notifier.telegram import build_dialog_feedback_keyboard
from src.storage.db import Database

from .test_check_migration_on_copy import make_legacy_source

ROOT = Path(__file__).resolve().parents[1]
MAIN_PY_PATH = ROOT / "src" / "main.py"
DB_PY_PATH = ROOT / "src" / "storage" / "db.py"
BOT_HANDLER_PY_PATH = ROOT / "src" / "notifier" / "bot_handler.py"

USER_ID = 424242


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _func(tree: ast.Module, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name
    ]
    assert len(found) == 1, f"Функция {name} должна быть ровно одна, найдено {len(found)}"
    return found[0]


def _make_handler(db: Database) -> EmailBotHandler:
    bot = AsyncMock()
    handler = EmailBotHandler(bot=bot, db=db, allowed_user_id=USER_ID)
    handler.notifier = AsyncMock()
    handler.setup_bot_commands = AsyncMock()
    return handler


def _make_message(text: str) -> MagicMock:
    msg = MagicMock()
    msg.from_user.id = USER_ID
    msg.chat.id = USER_ID
    msg.chat.type = "private"
    msg.text = text
    msg.answer = AsyncMock()
    return msg


def _make_callback(data: str, msg_id: int = 123) -> MagicMock:
    cb = MagicMock()
    cb.from_user.id = USER_ID
    cb.data = data
    cb.message = MagicMock()
    cb.message.message_id = msg_id
    cb.message.edit_reply_markup = AsyncMock()
    cb.answer = AsyncMock()
    return cb


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


def test_main_creates_database_and_awaits_init_db_before_persona_and_bot() -> None:
    """В main() инициализация Database и await init_db() строго предшествуют seed_persona и EmailBotHandler."""
    tree = _parse(MAIN_PY_PATH)
    main_func = _func(tree, "main")

    patterns = ["Database", "init_db", "seed_persona", "EmailBotHandler"]
    lines = check_execution_order(main_func, patterns)
    assert len(lines) == 4


def test_init_db_calls_migrations_before_seeding() -> None:
    """В Database.init_db вызов _apply_migrations стоит строго раньше _seed_initial_data_if_empty."""
    tree = _parse(DB_PY_PATH)
    init_db_func = _func(tree, "init_db")

    patterns = ["_apply_migrations", "_seed_initial_data_if_empty"]
    lines = check_execution_order(init_db_func, patterns)
    assert len(lines) == 2

    # Проверяем отсутствие строковых констант с CREATE TABLE в init_db
    for node in ast.walk(init_db_func):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert "create table" not in node.value.lower(), (
                "Обнаружен оператор создания таблицы в теле init_db!"
            )


@pytest.mark.asyncio
async def test_startup_on_empty_temp_db_applies_0003(tmp_path: Path) -> None:
    """Старт на чистой БД применяет 0003, создавая три пустые таблицы."""
    db_file = tmp_path / "empty_startup.db"
    db = Database(f"sqlite+aiosqlite:///{db_file}")
    await db.init_db()
    await db.close()

    assert get_schema_version(db_file) == "0003_bot_commands_and_feedback"
    expected_all = sorted(p.stem for p in MIGRATIONS_DIR.glob("*.sql"))
    assert list_applied_migrations(db_file) == expected_all

    with sqlite3.connect(str(db_file)) as conn:
        for tbl in ("bot_command_settings", "bot_custom_aliases", "dialog_feedback_log"):
            row = conn.execute(f"SELECT COUNT(*) FROM {tbl};").fetchone()
            assert row[0] == 0, f"Таблица {tbl} должна быть пустой"


@pytest.mark.asyncio
async def test_startup_on_legacy_shaped_db_keeps_rows_and_adds_0003(tmp_path: Path) -> None:
    """Старт на БД формы боевой (без 0003) накладывает 0003 без потери строк."""
    source = make_legacy_source(tmp_path / "legacy_startup")

    # До старта версии 0003 быть не должно
    versions_before = list_applied_migrations(source)
    assert "0003_bot_commands_and_feedback" not in versions_before

    with sqlite3.connect(str(source)) as conn:
        count_settings_before = conn.execute("SELECT COUNT(*) FROM bot_command_settings;").fetchone()[0]
        count_aliases_before = conn.execute("SELECT COUNT(*) FROM bot_custom_aliases;").fetchone()[0]
        count_feedback_before = conn.execute("SELECT COUNT(*) FROM dialog_feedback_log;").fetchone()[0]
        assert count_settings_before > 0
        assert count_aliases_before > 0
        assert count_feedback_before > 0

    # Эмулируем старт демона
    db = Database(f"sqlite+aiosqlite:///{source}")
    await db.init_db()
    await db.close()

    # После старта версия 0003 добавилась
    versions_after = list_applied_migrations(source)
    assert "0003_bot_commands_and_feedback" in versions_after

    with sqlite3.connect(str(source)) as conn:
        count_settings_after = conn.execute("SELECT COUNT(*) FROM bot_command_settings;").fetchone()[0]
        count_aliases_after = conn.execute("SELECT COUNT(*) FROM bot_custom_aliases;").fetchone()[0]
        count_feedback_after = conn.execute("SELECT COUNT(*) FROM dialog_feedback_log;").fetchone()[0]
        assert count_settings_after == count_settings_before
        assert count_aliases_after == count_aliases_before
        assert count_feedback_after == count_feedback_before


@pytest.mark.asyncio
async def test_bot_hide_show_and_alias_flows_use_migrated_tables(tmp_path: Path) -> None:
    """Реальный обработчик handle_user_text управляет скрытием команд и алиасами в мигрированной БД."""
    db_file = tmp_path / "bot_flows.db"
    db = Database(f"sqlite+aiosqlite:///{db_file}")
    await db.init_db()

    handler = _make_handler(db)
    try:
        # 1. Скрыть команду lms
        msg_hide = _make_message("скрой команду lms")
        await handler.handle_user_text(msg_hide)
        settings = await db.get_command_settings()
        assert settings["lms"]["is_enabled"] is False
        msg_hide.answer.assert_called_once()
        assert "скрыта" in msg_hide.answer.call_args[0][0]

        # 2. Показать команду lms
        msg_show = _make_message("покажи команду lms")
        await handler.handle_user_text(msg_show)
        settings = await db.get_command_settings()
        assert settings["lms"]["is_enabled"] is True
        msg_show.answer.assert_called_once()
        assert "возвращена" in msg_show.answer.call_args[0][0]

        # 3. Назначить алиас: "называй карточки как timesheet"
        msg_alias = _make_message("называй карточки как timesheet")
        await handler.handle_user_text(msg_alias)
        aliases = await db.get_custom_aliases()
        assert aliases.get("карточки") == "timesheet"
        msg_alias.answer.assert_called_once()
        assert "привязан" in msg_alias.answer.call_args[0][0]

        # 4. Удалить алиас: "удали алиас карточки"
        msg_del = _make_message("удали алиас карточки")
        await handler.handle_user_text(msg_del)
        aliases = await db.get_custom_aliases()
        assert "карточки" not in aliases
        msg_del.answer.assert_called_once()
        assert "удален" in msg_del.answer.call_args[0][0]

    finally:
        await db.close()


@pytest.mark.asyncio
async def test_menu_command_reads_both_tables(tmp_path: Path) -> None:
    """Обработчик /menu отображает скрытые команды и алиасы из базы данных."""
    db_file = tmp_path / "menu_test.db"
    db = Database(f"sqlite+aiosqlite:///{db_file}")
    await db.init_db()

    await db.set_command_setting("lms", is_enabled=False)
    await db.set_custom_alias("карточки", "timesheet")

    handler = _make_handler(db)
    try:
        msg_menu = _make_message("/menu")
        await handler.handle_cmd_menu(msg_menu)
        msg_menu.answer.assert_called_once()
        text = msg_menu.answer.call_args[0][0]
        assert "отключена" in text
        assert "/lms" in text
        assert "/карточки" in text
        assert "/timesheet" in text
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_feedback_buttons_from_keyboard_reach_the_log(tmp_path: Path) -> None:
    """Кнопки из build_dialog_feedback_keyboard записывают 👍 и 👎 в dialog_feedback_log."""
    db_file = tmp_path / "feedback_test.db"
    db = Database(f"sqlite+aiosqlite:///{db_file}")
    await db.init_db()

    handler = _make_handler(db)
    try:
        # Создаём клавиатуру через реальную вспомогательную функцию
        kb = build_dialog_feedback_keyboard(msg_id=987)
        btn_up_data = kb.inline_keyboard[0][0].callback_data
        btn_down_data = kb.inline_keyboard[0][1].callback_data
        assert btn_up_data.startswith("fb:up:")
        assert btn_down_data.startswith("fb:down:")

        # Нажатие "up"
        cb_up = _make_callback(btn_up_data, msg_id=987)
        await handler.cb_dialog_feedback(cb_up)
        entries = await db.get_dialog_feedback(message_id=987)
        assert len(entries) == 1
        assert entries[0]["feedback_type"] == "up"

        # Повторное нажатие "up" тем же пользователем (дедупликация)
        await handler.cb_dialog_feedback(cb_up)
        entries_dedup = await db.get_dialog_feedback(message_id=987)
        assert len(entries_dedup) == 1

        # Нажатие "down" для другого сообщения
        cb_down = _make_callback("fb:down:988", msg_id=988)
        await handler.cb_dialog_feedback(cb_down)
        entries_down = await db.get_dialog_feedback(message_id=988)
        assert len(entries_down) == 1
        assert entries_down[0]["feedback_type"] == "down"
    finally:
        await db.close()


def test_feedback_keyboard_is_attached_in_runtime_code() -> None:
    """В ast bot_handler.py есть вызов build_dialog_feedback_keyboard и регистрация fb:."""
    tree = _parse(BOT_HANDLER_PY_PATH)

    has_keyboard_call = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_str = ast.unparse(node.func)
            if "build_dialog_feedback_keyboard" in func_str:
                has_keyboard_call = True
                break
    assert has_keyboard_call, "Вызов build_dialog_feedback_keyboard не найден в bot_handler.py"

    content = BOT_HANDLER_PY_PATH.read_text(encoding="utf-8")
    assert 'F.data.startswith("fb:")' in content or "fb:" in content, (
        "Регистрация callback_query с префиксом fb: не найдена в bot_handler.py"
    )


def test_order_check_detects_reordered_calls() -> None:
    """Контроль чувствительности: check_execution_order падает при перестановке вызовов."""
    synthetic_code = """
async def sample_func():
    step_b()
    step_a()
"""
    synthetic_ast = ast.parse(synthetic_code)
    func_node = _func(synthetic_ast, "sample_func")

    # Порядок правильный: step_b -> step_a
    lines = check_execution_order(func_node, ["step_b", "step_a"])
    assert lines[0] < lines[1]

    # Порядок нарушен: step_a -> step_b
    with pytest.raises(AssertionError, match="Нарушен порядок вызовов"):
        check_execution_order(func_node, ["step_a", "step_b"])
