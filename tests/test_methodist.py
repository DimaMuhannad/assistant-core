"""Unit tests for Methodist Service (Frozen Context, Scope Check, and Effective Contract)."""

import pytest
from src.brain.methodist import MethodistService
from src.storage.db import Database


@pytest.mark.asyncio
async def test_methodist_scope_keywords():
    db = Database(db_path=":memory:")
    await db.init_db()
    methodist = MethodistService(db, api_key="")

    # 1. Effective contract queries must be in scope
    res1 = await methodist.check_scope("Сколько баллов дает статья ВАК в эффективном контракте ГУАП?")
    assert res1["is_in_scope"] is True

    # 2. Kovalenko & lab manual queries must be in scope
    res2 = await methodist.check_scope("Как оформлять погрешности по Коваленко в лабораторной работе?")
    assert res2["is_in_scope"] is True

    # 3. Department regulations and title templates
    res3 = await methodist.check_scope("Где взять титульный лист для отчета по физике?")
    assert res3["is_in_scope"] is True

    # 4. Out-of-scope queries must be rejected
    res4 = await methodist.check_scope("Сколько деталей из кремния отгрузил сектор приборов Тидекс?")
    assert res4["is_in_scope"] is False

    res5 = await methodist.check_scope("Какая погода завтра в Амстердаме?")
    assert res5["is_in_scope"] is False

    await db.close()


@pytest.mark.asyncio
async def test_methodist_ask_out_of_scope_guardrail():
    db = Database(db_path=":memory:")
    await db.init_db()
    methodist = MethodistService(db, api_key="")

    # Out of scope question should return template refusal immediately without calling Gemini
    res = await methodist.ask("Напиши код на C++ для рендеринга треугольника")
    assert res["is_out_of_scope"] is True
    assert "специализированный агент-методист кафедры физики ГУАП" in res["answer"]

    await db.close()
