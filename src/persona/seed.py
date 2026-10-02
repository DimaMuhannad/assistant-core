"""Загрузка персоны в таблицы БД и CLI: python -m src.persona.seed --db PATH [--persona-config FILE].

CLI отказывает на боевой БД (D-04): тесты и гейт работают только на копии.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from src.persona.loader import load_persona
from src.persona.models import ConnectorsConfig, PersonaConfig, PersonaConfigError
from src.storage.db import Database

LIVE_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "assistant.db"


def persona_rows(persona: PersonaConfig) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Строки workspaces (position = индекс) и connector_bindings (position внутри роли)."""
    workspaces = [
        {**ws.model_dump(), "position": index} for index, ws in enumerate(persona.workspaces)
    ]
    bindings = [
        {
            "binding_id": binding.id,
            "role": role,
            "provider": binding.provider,
            "scopes": list(binding.scopes),
            "config": dict(binding.config),
            "position": index,
        }
        for role in ConnectorsConfig.model_fields
        for index, binding in enumerate(getattr(persona.connectors, role))
    ]
    return workspaces, bindings


async def seed_persona(db: Database, persona: PersonaConfig) -> dict[str, int]:
    workspaces, bindings = persona_rows(persona)
    await db.upsert_persona(
        persona_id=persona.id,
        display_name=persona.display_name,
        config_json=persona.model_dump_json(),
        workspaces=workspaces,
        bindings=bindings,
    )
    return {"workspaces": len(workspaces), "bindings": len(bindings)}


async def _run(db_path: str, persona_config: str | None) -> str:
    persona = load_persona(persona_config)  # до открытия БД: ошибка файла не оставляет следов
    db = Database(db_path)
    try:
        await db.init_db()
        counts = await seed_persona(db, persona)
    finally:
        await db.close()
    return (
        f"персона {persona.id} записана: пространств {counts['workspaces']}, "
        f"привязок {counts['bindings']}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.persona.seed")
    parser.add_argument("--db", required=True, help="путь к БД (не боевой)")
    parser.add_argument("--persona-config", default=None, help="файл персоны вместо умолчания")
    args = parser.parse_args(argv)

    if Path(args.db).resolve() == LIVE_DB_PATH.resolve():
        print(f"отказ: seed не пишет в боевую БД {LIVE_DB_PATH}", file=sys.stderr)
        return 2
    try:
        message = asyncio.run(_run(args.db, args.persona_config))
    except PersonaConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
