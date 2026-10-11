"""Тесты неблокирующей инициализации БД и миграций (SCH-01, DAT-01, D-01, D-12).

Проверяет:
1. Обе ветки init_db (:memory: и файловая) применяют миграции без блокировки цикла событий.
2. migrator.run_migrations выполняется в рабочем потоке (asyncio.to_thread).
3. Чувствительность пробы: синхронный блокирующий вызов гарантированно детектируется.
4. Сбои миграции не проглатываются (fail-closed, пропуск сидирования).
5. Идемпотентность повторного вызова init_db.
6. В файле src/storage/db.py ровно один вызов run_migrations, являющийся аргументом asyncio.to_thread.
7. Сквозная запись и чтение feedback на обеих ветках.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
import threading
from typing import Any

import pytest

import src.storage.db
from src.storage.db import Database, run_migrations as real_run_migrations


def _make_db(db_kind: str, tmp_path: Path) -> Database:
    """Создать экземпляр Database для ветки :memory: или файловой БД."""
    if db_kind == "memory":
        return Database(":memory:")
    db_file = tmp_path / f"{db_kind}_test.db"
    return Database(f"sqlite+aiosqlite:///{db_file}")


async def _run_with_pulse_probe(
    action_coro: Any,
    monkeypatch: pytest.MonkeyPatch,
    timeout: float = 3.0,
) -> dict[str, Any]:
    """Вспомогательная корутина-проба неблокирования цикла событий (D-12).

    Подменяет run_migrations в src.storage.db:
    - Запоминает thread id миграции.
    - Ожидает threading.Event (до timeout секунд).
    Параллельно в цикле событий тикает корутина-пульс (5 тиков по 5 мс),
    которая по достижении 5 тиков выставляет Event.
    Если цикл событий заблокирован синхронным вызовом, пульс не успевает
    сделать тики, и Event не устанавливается вовремя.
    """
    event = threading.Event()
    loop_thread_id = threading.get_ident()
    migration_thread_ids: list[int] = []
    real_fn = real_run_migrations

    def mock_run_migrations(target: Any) -> list[str]:
        migration_thread_ids.append(threading.get_ident())
        # Ждём пока пульс-корутина протикает в цикле событий
        event.wait(timeout)
        return real_fn(target)

    monkeypatch.setattr(src.storage.db, "run_migrations", mock_run_migrations)

    pulse_ticks = 0
    stop_pulse = False

    async def pulse() -> None:
        nonlocal pulse_ticks
        while not stop_pulse and pulse_ticks < 5:
            await asyncio.sleep(0.005)
            pulse_ticks += 1
        if pulse_ticks >= 5:
            event.set()

    pulse_task = asyncio.create_task(pulse())
    try:
        await action_coro
    finally:
        stop_pulse = True
        await pulse_task

    return {
        "event_signaled": event.is_set(),
        "pulse_ticks": pulse_ticks,
        "loop_thread_id": loop_thread_id,
        "migration_thread_ids": migration_thread_ids,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("db_kind", ["memory", "file"])
async def test_init_db_round_trip_feedback(db_kind: str, tmp_path: Path) -> None:
    """Сквозной раунд-трип: после init_db запись и чтение обратной связи работают."""
    db = _make_db(db_kind, tmp_path)
    try:
        await db.init_db()
        await db.log_dialog_feedback(message_id=101, user_id=202, feedback_type="thumbs_up")
        rows = await db.get_dialog_feedback(message_id=101)
        assert len(rows) == 1
        assert rows[0]["message_id"] == 101
        assert rows[0]["user_id"] == 202
        assert rows[0]["feedback_type"] == "thumbs_up"
        assert "created_at" in rows[0]
    finally:
        await db.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("db_kind", ["memory", "file"])
async def test_migration_runs_off_the_event_loop_thread(
    db_kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Мигратор выполняется в потоке, отличном от потока цикла событий."""
    loop_thread_id = threading.get_ident()
    called_threads: list[int] = []
    real_fn = real_run_migrations

    def mock_run_migrations(target: Any) -> list[str]:
        called_threads.append(threading.get_ident())
        return real_fn(target)

    monkeypatch.setattr(src.storage.db, "run_migrations", mock_run_migrations)

    db = _make_db(db_kind, tmp_path)
    try:
        await db.init_db()
        assert len(called_threads) == 1
        assert called_threads[0] != loop_thread_id, (
            f"Миграция выполнялась в потоке цикла событий ({loop_thread_id})!"
        )
    finally:
        await db.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("db_kind", ["memory", "file"])
async def test_event_loop_keeps_ticking_during_migration(
    db_kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Параллельная корутина-пульс свободно тикает во время выполнения миграции."""
    db = _make_db(db_kind, tmp_path)
    try:
        result = await _run_with_pulse_probe(db.init_db(), monkeypatch, timeout=3.0)
        assert result["event_signaled"], "Цикл событий был заблокирован во время миграции!"
        assert result["pulse_ticks"] >= 5, f"Пульс сделал только {result['pulse_ticks']} тиков!"
        assert len(result["migration_thread_ids"]) == 1
        assert result["migration_thread_ids"][0] != result["loop_thread_id"]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_probe_detects_a_loop_blocking_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Контроль чувствительности: синхронный блокирующий вызов детерминированно красит пробу."""
    # Симулируем блокирующий вызов прямо в цикле событий (старое поведение ветки :memory:)
    async def blocking_action() -> None:
        # Вызываем функцию напрямую без asyncio.to_thread
        src.storage.db.run_migrations(":memory:")

    # Короткий таймаут 0.3с
    result = await _run_with_pulse_probe(blocking_action(), monkeypatch, timeout=0.3)
    assert not result["event_signaled"], "Блокирующий вызов должен был сорвать таймаут пробы!"
    assert result["pulse_ticks"] == 0, "В заблокированном цикле тики пульса не должны были пройти!"
    assert result["migration_thread_ids"][0] == result["loop_thread_id"], (
        "Блокирующий вызов должен был произойти в потоке цикла"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("db_kind", ["memory", "file"])
async def test_migration_failure_propagates_and_skips_seed(
    db_kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Сбой миграции пробрасывается наружу (fail-closed) и сидирование не выполняется."""
    def broken_run_migrations(target: Any) -> list[str]:
        raise RuntimeError("Migration failed intentionally")

    monkeypatch.setattr(src.storage.db, "run_migrations", broken_run_migrations)

    seed_called = False
    original_seed = Database._seed_initial_data_if_empty

    async def tracking_seed(self_db: Database, conn: Any) -> None:
        nonlocal seed_called
        seed_called = True
        await original_seed(self_db, conn)

    monkeypatch.setattr(Database, "_seed_initial_data_if_empty", tracking_seed)

    db = _make_db(db_kind, tmp_path)
    try:
        with pytest.raises(RuntimeError, match="Migration failed intentionally"):
            await db.init_db()
        assert not seed_called, "Метод сидирования был вызван несмотря на сбой миграции!"
    finally:
        await db.close()


def test_single_run_migrations_call_site() -> None:
    """В src/storage/db.py ровно одно обращение к run_migrations вне импорта, и оно аргумент asyncio.to_thread."""
    db_file = Path("/opt/assistant-core/src/storage/db.py")
    tree = ast.parse(db_file.read_text(encoding="utf-8"))

    # Находим все узлы Name с id == "run_migrations" вне Import/ImportFrom
    occurrences: list[ast.Name] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "run_migrations":
            occurrences.append(node)

    assert len(occurrences) == 1, (
        f"Ожидалось ровно 1 обращение к run_migrations в db.py, обнаружено {len(occurrences)}"
    )

    # Проверяем, что run_migrations передан первым аргументом в asyncio.to_thread
    to_thread_calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "to_thread"
                and isinstance(func.value, ast.Name)
                and func.value.id == "asyncio"
            ):
                to_thread_calls.append(node)

    matching = [
        call for call in to_thread_calls
        if call.args and isinstance(call.args[0], ast.Name) and call.args[0].id == "run_migrations"
    ]
    assert len(matching) == 1, (
        "run_migrations обязан передаваться аргументом в asyncio.to_thread"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("db_kind", ["memory", "file"])
async def test_init_db_is_idempotent(db_kind: str, tmp_path: Path) -> None:
    """Повторный вызов init_db идемпотентен, данные проектов не дублируются."""
    db = _make_db(db_kind, tmp_path)
    try:
        await db.init_db()
        projects_first = await db.list_projects()
        assert len(projects_first) > 0

        # Повторный вызов init_db
        await db.init_db()
        projects_second = await db.list_projects()

        assert len(projects_first) == len(projects_second), (
            "Повторный init_db изменил число проектов!"
        )
    finally:
        await db.close()
