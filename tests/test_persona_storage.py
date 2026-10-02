"""Хранилище персоны (PER-02, D-02): таблицы в init_db, идемпотентность, атомарность, seed-CLI."""

import asyncio
import json

import pytest

from src.persona import seed as seed_module
from src.storage.db import Database

PERSONA_TABLES = {"personas", "workspaces", "connector_bindings"}


def _workspaces() -> list[dict]:
    return [
        {
            "id": "ws-a",
            "position": 0,
            "label": "Пространство A",
            "path": "/tmp/ws-a",
            "clearance": "public",
            "forbidden_keywords": ["kw-a"],
        },
        {
            "id": "ws-b",
            "position": 1,
            "label": "Пространство B",
            "path": "/tmp/ws-b",
            "clearance": "internal",
        },
    ]


async def _count(db: Database, table: str) -> int:
    async with db.connection() as conn:
        cursor = await conn.execute(f"SELECT COUNT(*) FROM {table}")
        return (await cursor.fetchone())[0]


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.init_db()
    yield database
    await database.close()


async def test_init_db_creates_persona_tables(db):
    async with db.connection() as conn:
        cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        names = {row[0] for row in await cursor.fetchall()}
    assert PERSONA_TABLES <= names
    await db.init_db()  # повторный вызов не падает


async def test_upsert_persona_is_idempotent(db):
    args = dict(
        persona_id="p1",
        display_name="Персона Один",
        config_json='{"id": "p1"}',
        workspaces=_workspaces(),
        bindings=[],
    )
    await db.upsert_persona(**args)
    first = await db.get_persona_record("p1")
    first_ws = await db.list_persona_workspaces("p1")

    await db.upsert_persona(**args)
    second = await db.get_persona_record("p1")
    second_ws = await db.list_persona_workspaces("p1")

    assert second["created_at"] == first["created_at"]
    assert second["config_json"] == first["config_json"]
    assert second_ws == first_ws
    assert [w["id"] for w in second_ws] == ["ws-a", "ws-b"]
    assert second_ws[0]["forbidden_keywords"] == ["kw-a"]
    assert await _count(db, "personas") == 1
    assert await _count(db, "workspaces") == 2


async def test_upsert_does_not_touch_user_tables(db):
    before = (await _count(db, "tasks"), await _count(db, "projects"))
    await db.upsert_persona("p1", "Персона", "{}", _workspaces(), [])
    await db.upsert_persona("p1", "Персона", "{}", _workspaces(), [])
    after = (await _count(db, "tasks"), await _count(db, "projects"))
    assert after == before


async def test_upsert_is_atomic_on_failure(db):
    await db.upsert_persona("p1", "Персона", '{"v": 1}', _workspaces(), [])
    bad_binding = {
        "binding_id": "b1",
        "role": "bad-role",
        "provider": "x",
        "scopes": [],
        "config": {},
    }
    with pytest.raises(Exception):
        await db.upsert_persona("p1", "Персона", '{"v": 2}', _workspaces()[:1], [bad_binding])

    record = await db.get_persona_record("p1")
    assert record["config_json"] == '{"v": 1}'
    assert [w["id"] for w in await db.list_persona_workspaces("p1")] == ["ws-a", "ws-b"]
    assert await db.list_connector_bindings("p1") == []


def test_seed_cli_refuses_live_db(monkeypatch):
    class ForbiddenDatabase:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Database не должна создаваться для боевого пути")

    monkeypatch.setattr(seed_module, "Database", ForbiddenDatabase)
    assert seed_module.main(["--db", str(seed_module.LIVE_DB_PATH)]) == 2


def test_seed_cli_writes_persona_into_temp_db(tmp_path):
    path = tmp_path / "t.db"
    assert seed_module.main(["--db", str(path)]) == 0

    record = asyncio.run(Database(str(path)).get_persona_record("popov-da-default"))
    assert record is not None
    assert json.loads(record["config_json"])["id"] == "popov-da-default"


def test_seed_cli_uses_persona_config_argument(tmp_path):
    persona_file = tmp_path / "persona.yaml"
    persona_file.write_text(
        "persona:\n"
        "  id: tmp-persona\n"
        "  display_name: Тестовая Персона\n"
        "  short_name: Тестова П.\n"
        "  title: тестировщик\n"
        "  organizations:\n"
        "    university:\n"
        "      name: Университет-А\n"
        "  default_area: Область-А\n",
        encoding="utf-8",
    )
    path = tmp_path / "t.db"
    assert seed_module.main(["--db", str(path), "--persona-config", str(persona_file)]) == 0

    check = Database(str(path))
    assert asyncio.run(check.get_persona_record("tmp-persona")) is not None
    assert asyncio.run(check.get_persona_record("popov-da-default")) is None


async def test_seed_writes_workspaces_in_order(db):
    from src.persona.loader import load_persona
    from src.persona.seed import persona_rows, seed_persona

    persona = load_persona()
    expected_nda = next(ws for ws in persona.workspaces if ws.clearance == "restricted_nda")
    workspace_rows, binding_rows = persona_rows(persona)
    assert [row["position"] for row in workspace_rows] == [0, 1, 2, 3]
    assert binding_rows == []

    await seed_persona(db, persona)
    rows = await db.list_persona_workspaces(persona.id)
    assert [r["id"] for r in rows] == ["chat-app", "assistant-core", "tydex-optics", "guap-physics"]
    assert [r["clearance"] for r in rows] == ["public", "public", "restricted_nda", "internal"]
    nda_row = rows[2]
    # слова в assert напрямую не сравниваются: pytest напечатал бы их при провале
    assert len(nda_row["forbidden_keywords"]) == len(expected_nda.forbidden_keywords) > 0
    same = nda_row["forbidden_keywords"] == expected_nda.forbidden_keywords
    assert same, "слова NDA в БД и в данных расходятся"
    assert nda_row["forbidden_remote_substrings"] == expected_nda.forbidden_remote_substrings
    assert all(rows[i]["forbidden_keywords"] == [] for i in (0, 1, 3))
