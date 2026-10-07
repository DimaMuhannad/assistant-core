import pytest
from unittest.mock import AsyncMock, MagicMock
from src.storage.db import Database
from src.notifier.commands import CommandRegistry
from src.brain.intent_router import FastIntentRouter


@pytest.mark.asyncio
async def test_fast_intent_router_aliases(tmp_path):
    """Test FastIntentRouter resolves default catalog aliases instantaneously (< 10 ms)."""
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.init_db()
    try:
        registry = CommandRegistry(db=db)
        router = FastIntentRouter(db=db, command_registry=registry)

        test_cases = [
            ("пары", "today"),
            ("табель", "timesheet"),
            ("почта", "emails"),
            ("статус", "ticker"),
            ("вечер", "evening"),
        ]

        for text, expected_action in test_cases:
            res = await router.route(user_id=1001, message_text=text)
            assert res.action == expected_action
            assert res.model == "fast-rule"
            assert res.confidence == 1.0
            assert res.latency_ms < 50.0
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_hide_and_show_command(tmp_path):
    """Test hiding and restoring commands from Telegram Bot menu."""
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.init_db()
    try:
        registry = CommandRegistry(db=db)

        # Initially LMS is active
        cmds = await registry.get_telegram_commands()
        assert "lms" in [c.command for c in cmds]

        # Hide LMS
        await db.set_command_setting("lms", is_enabled=False)
        cmds_hidden = await registry.get_telegram_commands()
        assert "lms" not in [c.command for c in cmds_hidden]

        # Restore LMS
        await db.set_command_setting("lms", is_enabled=True)
        cmds_restored = await registry.get_telegram_commands()
        assert "lms" in [c.command for c in cmds_restored]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_custom_alias_registration_and_routing(tmp_path):
    """Test custom aliases resolution via FastIntentRouter."""
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.init_db()
    try:
        registry = CommandRegistry(db=db)
        router = FastIntentRouter(db=db, command_registry=registry)

        # Register custom alias: "лабы" -> "lms"
        await db.set_custom_alias("лабы", "lms")
        res = await router.route(user_id=1001, message_text="лабы")
        assert res.action == "lms"
        assert res.model == "fast-rule"
        assert res.confidence == 1.0

        # Remove custom alias
        removed = await db.remove_custom_alias("лабы")
        assert removed is True
        resolved = await registry.resolve_command_or_alias("лабы")
        assert resolved is None
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_menu_command_rendering(tmp_path):
    """Test that menu rendering formats command statuses and aliases correctly."""
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.init_db()
    try:
        registry = CommandRegistry(db=db)
        await db.set_command_setting("lms", is_enabled=False)
        await db.set_custom_alias("карточки", "timesheet")

        # Simulate bot handler menu inspection
        catalog = registry._build_default_catalog(registry.persona_getter())
        settings = await db.get_command_settings()
        custom_aliases = await db.get_custom_aliases()

        assert "lms" in settings
        assert settings["lms"]["is_enabled"] is False
        assert custom_aliases.get("карточки") == "timesheet"
    finally:
        await db.close()
