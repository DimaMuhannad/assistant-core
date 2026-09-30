"""Unit tests for Long-Term Memory (memory_facts), Weekly Sunday Review, and Daily Priming."""

import pytest
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

from src.storage.db import Database
from src.brain.secretary_dialog import SecretaryDialogEngine


@pytest.mark.asyncio
async def test_memory_facts_crud_and_touch():
    db = Database(db_path=":memory:")
    await db.init_db()

    fact_id = await db.add_memory_fact(
        fact_text="25 сентября 2026 г. взят один день в счет отпуска в ООО Тидекс",
        category="tydex",
        retention_policy="forever",
    )
    assert fact_id > 0

    # Search and touch
    matches = await db.search_and_touch_memory_facts("когда был день отпуска в тидексе?")
    assert len(matches) == 1
    assert matches[0]["id"] == fact_id

    # Verify access counter was incremented in DB
    facts = await db.get_active_memory_facts()
    assert len(facts) == 1
    assert facts[0]["access_count"] == 1
    assert facts[0]["retention_policy"] == "forever"

    await db.close()


@pytest.mark.asyncio
async def test_memory_facts_for_review_filtering():
    db = Database(db_path=":memory:")
    await db.init_db()

    now = datetime.now(timezone.utc)

    # 1. Forever fact: must NOT be a candidate
    await db.add_memory_fact(
        fact_text="Фундаментальное правило Тидекс",
        category="tydex",
        retention_policy="forever",
    )

    # 2. Fact protected until future: must NOT be a candidate
    await db.add_memory_fact(
        fact_text="Временный проект до конца года",
        category="academic",
        retention_policy="temporary",
        protect_until=now + timedelta(days=60),
    )

    # 3. Expired deadline (> 7 days ago): MUST be a candidate
    expired_id = await db.add_memory_fact(
        fact_text="Сдача ведомостей по физике до 15 сентября",
        category="admin",
        deadline=now - timedelta(days=10),
        retention_policy="standard",
    )

    # 4. Old fact with 0 accesses: MUST be a candidate
    async with db.connection() as conn:
        cursor = await conn.execute(
            """
            INSERT INTO memory_facts (fact_text, category, created_at, last_accessed_at, access_count, retention_policy, is_active)
            VALUES ('Старая заметка', 'general', ?, ?, 0, 'standard', TRUE);
            """,
            (now - timedelta(days=20), now - timedelta(days=20)),
        )
        old_id = cursor.lastrowid
        await conn.commit()

    candidates = await db.get_memory_facts_for_review(now=now)
    cand_ids = [c["id"] for c in candidates]

    assert expired_id in cand_ids
    assert old_id in cand_ids
    assert len(candidates) == 2

    await db.close()


@pytest.mark.asyncio
async def test_memory_review_command_parsing():
    db = Database(db_path=":memory:")
    await db.init_db()
    engine = SecretaryDialogEngine(db=db, api_key="")

    # Create 5 test facts
    f1 = await db.add_memory_fact("Факт 1", category="academic")
    f2 = await db.add_memory_fact("Факт 2", category="tydex")
    f3 = await db.add_memory_fact("Факт 3", category="general")
    f4 = await db.add_memory_fact("Факт 4", category="student")
    f5 = await db.add_memory_fact("Факт 5", category="admin")

    # Set up pending review items mapping
    pending_items = [
        {"index": 1, "fact_id": f1, "text": "Факт 1", "category": "academic"},
        {"index": 2, "fact_id": f2, "text": "Факт 2", "category": "tydex"},
        {"index": 3, "fact_id": f3, "text": "Факт 3", "category": "general"},
        {"index": 4, "fact_id": f4, "text": "Факт 4", "category": "student"},
        {"index": 5, "fact_id": f5, "text": "Факт 5", "category": "admin"},
    ]
    await db.save_pending_memory_review("2026-10-04", pending_items)

    user_cmd = """
    удалить: 2, 5
    заменить на год: 1
    запомнить навсегда: 3-4
    """

    res = await engine._handle_memory_review_command(user_cmd)
    assert res is not None
    assert "Ревизия долгосрочной памяти успешно проведена" in res
    assert "Удалено из активной памяти: **2**" in res
    assert "Сохранено навсегда: **2**" in res
    assert "Установлена временная защита: **1**" in res

    # Verify states in DB
    all_facts = await db.get_active_memory_facts(limit=10)
    active_ids = [f["id"] for f in all_facts]

    # f2 and f5 should be deleted (inactive)
    assert f2 not in active_ids
    assert f5 not in active_ids

    # f3 and f4 should be forever
    f3_row = next(f for f in all_facts if f["id"] == f3)
    f4_row = next(f for f in all_facts if f["id"] == f4)
    assert f3_row["retention_policy"] == "forever"
    assert f4_row["retention_policy"] == "forever"

    # f1 should be protected with future protect_until
    f1_row = next(f for f in all_facts if f["id"] == f1)
    assert f1_row["protect_until"] is not None

    # Review should be marked resolved
    pending = await db.get_pending_memory_review("2026-10-04")
    assert pending is None  # only pending status returned

    await db.close()


@pytest.mark.asyncio
async def test_manual_fact_addition_handler():
    db = Database(db_path=":memory:")
    await db.init_db()
    engine = SecretaryDialogEngine(db=db, api_key="")

    res = await engine._handle_manual_fact_addition("Запомни на год: в пятницу после второй пары консультация по нанотехнологиям")
    assert res is not None
    assert "Зафиксировал в долгосрочной памяти" in res
    assert "на 1 год" in res or "защищено до" in res

    facts = await db.get_active_memory_facts()
    assert len(facts) == 1
    assert "консультация по нанотехнологиям" in facts[0]["fact_text"]
    assert facts[0]["protect_until"] is not None

    await db.close()


@pytest.mark.asyncio
async def test_daily_archive_and_reset():
    db = Database(db_path=":memory:")
    await db.init_db()

    # Save turns in dialog
    await db.save_dialog_message(user_id=123, role="user", content="Вчерашнее сообщение")
    await db.save_dialog_message(user_id=123, role="model", content="Вчерашний ответ")

    history = await db.get_recent_dialog_history(user_id=123, limit=10, active_only=True)
    assert len(history) == 2

    # Run daily archive reset
    archived = await db.archive_dialog_history(user_id=123)
    assert archived == 2

    # Active history is now empty
    active_history = await db.get_recent_dialog_history(user_id=123, limit=10, active_only=True)
    assert len(active_history) == 0

    # Historical messages are preserved in DB
    full_history = await db.get_recent_dialog_history(user_id=123, limit=10, active_only=False)
    assert len(full_history) == 2
    assert full_history[0]["is_archived"] in (True, 1)

    await db.close()
