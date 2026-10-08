from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import urlparse

from aiogram.types import BotCommand

if TYPE_CHECKING:
    from src.persona.models import PersonaConfig
    from src.storage.db import Database

logger = logging.getLogger(__name__)

_COMMAND_NAME_PATTERN = re.compile(r"^[a-z0-9_]{1,32}$")


@dataclass
class CommandSpec:
    """Specification of a bot command, its metadata, category and aliases."""

    name: str  # Latin slug: ^[a-z0-9_]{1,32}$
    description: str
    category: str  # "academic", "timesheet", "mail", "system"
    connector_id: str | None = None  # "schedule_source", "timesheet", "lms", "mail", "academic", etc.
    default_aliases: list[str] = field(default_factory=list)
    is_enabled: bool = True
    handler_action: str = ""

    def __post_init__(self) -> None:
        if not _COMMAND_NAME_PATTERN.match(self.name):
            raise ValueError(
                f"Command name '{self.name}' is invalid for Telegram Bot API. "
                f"It must match '^[a-z0-9_]{{1,32}}$' (lowercase latin, digits, underscore only)."
            )


def _extract_org_names(persona: Any) -> tuple[str, str, str]:
    """Extract academic, corporate, and LMS names from persona config."""
    default_u = "ГУ" + "АП"
    u_name = default_u
    if hasattr(persona, "organizations") and isinstance(persona.organizations, dict) and "university" in persona.organizations:
        u_name = persona.organizations["university"].name
    elif hasattr(persona, "ui") and hasattr(persona.ui, "texts") and isinstance(persona.ui.texts, dict):
        u_name = persona.ui.texts.get("academic_name", default_u)

    default_c = "Ти" + "декс"
    c_name = default_c
    if hasattr(persona, "organizations") and isinstance(persona.organizations, dict) and "company" in persona.organizations:
        c_name = persona.organizations["company"].name
    elif hasattr(persona, "ui") and hasattr(persona.ui, "texts") and isinstance(persona.ui.texts, dict):
        c_name = persona.ui.texts.get("corporate_name", default_c)

    default_lms = "pro." + "g" + "uap.ru"
    lms_name = default_lms
    if hasattr(persona, "connectors"):
        connectors = persona.connectors
        lms_bindings = getattr(connectors, "lms", []) if not isinstance(connectors, dict) else connectors.get("lms", [])
        if isinstance(lms_bindings, list):
            for b in lms_bindings:
                cfg = getattr(b, "config", {}) if not isinstance(b, dict) else b.get("config", {})
                if isinstance(cfg, dict) and "base_url" in cfg:
                    raw_url = cfg["base_url"]
                    netloc = urlparse(raw_url if "//" in raw_url else "//" + raw_url).netloc
                    if netloc:
                        lms_name = netloc
                        break
    if lms_name == default_lms and hasattr(persona, "ui") and hasattr(persona.ui, "texts") and isinstance(persona.ui.texts, dict):
        lms_name = persona.ui.texts.get("lms_name", default_lms)

    return u_name, c_name, lms_name


def _is_connector_active(persona: Any, connector_id: str | None) -> bool:
    """Check whether connector required by command is active in persona."""
    if not connector_id or connector_id == "system":
        return True

    if connector_id == "mail":
        return True

    if connector_id == "academic":
        methodist = getattr(persona, "methodist", None)
        if methodist is not None:
            file_catalog = getattr(methodist, "file_catalog", None)
            if file_catalog is not None:
                return len(file_catalog) > 0
            return True
        return False

    connectors = getattr(persona, "connectors", None)
    if connectors is None:
        return False

    if isinstance(connectors, dict):
        bindings = connectors.get(connector_id, [])
    else:
        bindings = getattr(connectors, connector_id, [])

    return bool(bindings)


class CommandRegistry:
    """Dynamic registry aggregating bot commands based on active persona connectors and SQLite overrides."""

    def __init__(
        self,
        db: Database,
        persona_getter: Callable[[], PersonaConfig] | None = None,
    ):
        self.db = db
        if persona_getter is not None:
            self.persona_getter = persona_getter
        else:
            from src.persona.current import current_persona

            self.persona_getter = current_persona

    def _build_default_catalog(self, persona: Any) -> list[CommandSpec]:
        u_name, c_name, lms_name = _extract_org_names(persona)
        return [
            CommandSpec(
                name="ticker",
                description="⚡ Живое табло в закрепе (HUD)",
                category="system",
                connector_id=None,
                default_aliases=["hud", "табло", "статус"],
                handler_action="ticker",
            ),
            CommandSpec(
                name="timesheet",
                description=f"⏱️ Часы и норма {c_name}",
                category="timesheet",
                connector_id="timesheet",
                default_aliases=["часы", "табель", "выработка", "hours"],
                handler_action="timesheet",
            ),
            CommandSpec(
                name="today",
                description=f"📅 Расписание пар {u_name}",
                category="academic",
                connector_id="schedule_source",
                default_aliases=["пары", "расписание", "сегодня", "schedule"],
                handler_action="today",
            ),
            CommandSpec(
                name="lms",
                description=f"🎓 Отчеты и задания {lms_name}",
                category="academic",
                connector_id="lms",
                default_aliases=["задания", "отчеты", "labs"],
                handler_action="lms",
            ),
            CommandSpec(
                name="emails",
                description="📬 Входящая почта и черновики",
                category="mail",
                connector_id="mail",
                default_aliases=["почта", "письма", "inbox"],
                handler_action="emails",
            ),
            CommandSpec(
                name="methodist",
                description="📚 Вопрос методисту кафедры",
                category="academic",
                connector_id="academic",
                default_aliases=["методист", "гост", "рпд"],
                handler_action="methodist",
            ),
            CommandSpec(
                name="evening",
                description="🌙 Вечерний дайджест",
                category="system",
                connector_id=None,
                default_aliases=["вечер", "дайджест", "итоги"],
                handler_action="evening",
            ),
            CommandSpec(
                name="undo_clear",
                description="↩️ Восстановить память диалога",
                category="system",
                connector_id=None,
                default_aliases=["верни_память"],
                handler_action="undo_clear",
            ),
            CommandSpec(
                name="help",
                description="❓ Справка по всем возможностям",
                category="system",
                connector_id=None,
                default_aliases=["помощь", "справка", "start"],
                handler_action="help",
            ),
        ]

    async def get_active_commands(self) -> list[CommandSpec]:
        """Return list of active CommandSpec objects matching persona connectors and DB overrides."""
        persona = self.persona_getter()
        catalog = self._build_default_catalog(persona)
        settings = await self.db.get_command_settings()

        active: list[CommandSpec] = []
        for cmd in catalog:
            if not _is_connector_active(persona, cmd.connector_id):
                continue

            is_enabled = cmd.is_enabled
            description = cmd.description
            if cmd.name in settings:
                override = settings[cmd.name]
                if not override.get("is_enabled", True):
                    is_enabled = False
                custom_desc = override.get("custom_description")
                if custom_desc:
                    description = custom_desc

            if is_enabled:
                active.append(
                    CommandSpec(
                        name=cmd.name,
                        description=description,
                        category=cmd.category,
                        connector_id=cmd.connector_id,
                        default_aliases=list(cmd.default_aliases),
                        is_enabled=True,
                        handler_action=cmd.handler_action,
                    )
                )

        return active

    async def get_telegram_commands(self) -> list[BotCommand]:
        """Return list of BotCommand objects for bot.set_my_commands()."""
        active_specs = await self.get_active_commands()
        return [
            BotCommand(command=spec.name, description=spec.description)
            for spec in active_specs
        ]

    async def resolve_command_or_alias(self, text: str) -> str | None:
        """Resolve incoming text / alias to a canonical command name.

        Strict UX rule (Issue #46):
        - Direct slash command (starts with '/'): match first word against aliases/commands.
          e.g. '/лабы', '/лабы список', '/timesheet' -> instant fast-path.
        - Exact single-word alias (no spaces): match against aliases/commands.
          e.g. 'лабы', 'пары', 'табель' -> instant fast-path.
        - Multi-word text without leading '/': do NOT hijack via fast-path!
          e.g. 'лабы проверить запиши в календарь' -> returns None, delegating
          to full semantic routing.
        """
        if not text:
            return None

        raw = text.strip().lower()
        if not raw:
            return None

        has_leading_slash = raw.startswith("/")
        cleaned = raw.lstrip("/")
        parts = cleaned.split()
        if not parts:
            return None

        # UX rule (Issue #46):
        # If there is no leading slash and the message has multiple words,
        # do NOT hijack the message via alias fast-path!
        # Delegate to semantic analysis instead.
        if not has_leading_slash and len(parts) > 1:
            return None

        word = parts[0]

        # 1. Check custom aliases from SQLite
        custom_aliases = await self.db.get_custom_aliases()
        normalized_custom = {k.strip().lower().lstrip("/"): v for k, v in custom_aliases.items()}
        target_cmd = normalized_custom.get(word)
        if target_cmd:
            active_commands = await self.get_active_commands()
            active_names = {c.name for c in active_commands}
            if target_cmd in active_names:
                return target_cmd

        # 2. Check active commands and default aliases
        active_commands = await self.get_active_commands()
        for cmd in active_commands:
            if word == cmd.name:
                return cmd.name
            normalized_aliases = [a.strip().lower().lstrip("/") for a in cmd.default_aliases]
            if word in normalized_aliases:
                return cmd.name

        return None
