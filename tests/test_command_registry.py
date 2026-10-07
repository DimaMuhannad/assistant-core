import pytest
from unittest.mock import MagicMock
from src.storage.db import Database
from src.notifier.commands import CommandRegistry, CommandSpec


@pytest.mark.asyncio
async def test_command_registry_default_catalog(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.init_db()

    registry = CommandRegistry(db=db)
    active = await registry.get_active_commands()
    assert len(active) == 9

    names = [c.name for c in active]
    assert "ticker" in names
    assert "timesheet" in names
    assert "today" in names
    assert "help" in names

    tg_cmds = await registry.get_telegram_commands()
    assert len(tg_cmds) == 9
    for c in tg_cmds:
        assert c.command.islower()
        assert c.command.isascii()


@pytest.mark.asyncio
async def test_command_registry_disable_connector(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.init_db()

    mock_persona = MagicMock()
    mock_persona.organizations = {}
    mock_persona.ui.texts = {}
    mock_persona.connectors.timesheet = []  # No timesheet
    mock_persona.connectors.schedule_source = [MagicMock()]
    mock_persona.connectors.lms = [MagicMock()]
    mock_persona.methodist.file_catalog = [MagicMock()]

    registry = CommandRegistry(db=db, persona_getter=lambda: mock_persona)
    active = await registry.get_active_commands()
    names = [c.name for c in active]
    assert "timesheet" not in names
    assert "today" in names


@pytest.mark.asyncio
async def test_command_registry_db_settings_override(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.init_db()

    await db.set_command_setting("lms", is_enabled=False)
    await db.set_command_setting("today", is_enabled=True, custom_description="Новое расписание пар")

    registry = CommandRegistry(db=db)
    active = await registry.get_active_commands()
    names = [c.name for c in active]
    assert "lms" not in names
    assert "today" in names

    today_spec = next(c for c in active if c.name == "today")
    assert today_spec.description == "Новое расписание пар"


@pytest.mark.asyncio
async def test_command_registry_resolve_aliases(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.init_db()

    registry = CommandRegistry(db=db)

    # 1. Default aliases
    assert await registry.resolve_command_or_alias("/часы") == "timesheet"
    assert await registry.resolve_command_or_alias("часы") == "timesheet"
    assert await registry.resolve_command_or_alias("пары") == "today"
    assert await registry.resolve_command_or_alias("/today") == "today"

    # 2. Custom alias in SQLite
    await db.set_custom_alias("выработка_тидекс", "timesheet")
    assert await registry.resolve_command_or_alias("выработка_тидекс") == "timesheet"
    assert await registry.resolve_command_or_alias("/выработка_тидекс") == "timesheet"

    # 3. Non-existent alias
    assert await registry.resolve_command_or_alias("неизвестная_команда") is None


def test_command_spec_name_validation():
    # Valid names
    CommandSpec(name="test_cmd_1", description="desc", category="system")
    CommandSpec(name="today", description="desc", category="system")

    # Invalid names (Cyrillic, uppercase, special symbols)
    with pytest.raises(ValueError):
        CommandSpec(name="пары", description="desc", category="system")

    with pytest.raises(ValueError):
        CommandSpec(name="Today", description="desc", category="system")

    with pytest.raises(ValueError):
        CommandSpec(name="cmd-with-dash", description="desc", category="system")
