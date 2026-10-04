"""Интеграционные тесты параллельного исполнения задач нескольких персон (ISO-04, D-01, D-10, D-11).

Проверяет:
1. Отсутствие cross-talk в пулах ключей Gemini и ContextVar между параллельными задачами.
2. Изоляцию рабочих пространств (default: 4, synthetic: 3).
3. Изоляцию разрешений коннекторов (default: доступен timesheet, synthetic: MissingScopeError).
4. Конкурентную изоляцию хранилища подтверждений (ConfirmationStore).
5. Высокую стабильность при множественных одновременных переключениях контекста персон.
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path

import pytest

from assistant_shared.db.migrator import run_migrations
from assistant_shared.hitl import ConfirmationChannel, ConfirmationStore
from src.brain.key_rotator import _rotator_cache, get_key_rotator
from src.composition import default_timesheet_service
from src.core.exceptions import MissingScopeError
from src.persona.current import current_persona, reset_persona_cache, use_persona
from src.persona.models import PersonaConfig
from .synthetic_persona import SYNTHETIC_PERSONA, synthetic_to_config


MOCK_DEFAULT_KEYS = ["mock-default-pool-key-alpha", "mock-default-pool-key-beta"]
MOCK_SYNTH_KEYS = ["mock-synth-pool-key-gamma", "mock-synth-pool-key-delta"]


@pytest.fixture(autouse=True)
def clean_rotator_and_persona_cache():
    """Сбрасывает кэш ротаторов и персон перед каждым тестом."""
    _rotator_cache.clear()
    reset_persona_cache()
    yield
    _rotator_cache.clear()
    reset_persona_cache()


@pytest.mark.asyncio
async def test_multi_persona_concurrency_isolation():
    """Сквозной тест параллельного исполнения воркеров default и synthetic персон (ISO-04)."""
    default_p = current_persona().model_copy(update={"gemini_keys": MOCK_DEFAULT_KEYS})
    synth_cfg = synthetic_to_config(SYNTHETIC_PERSONA)["persona"]
    synth_p = PersonaConfig.model_validate(synth_cfg).model_copy(update={"gemini_keys": MOCK_SYNTH_KEYS})

    results_default: list[tuple[str, int, str]] = []
    results_synth: list[tuple[str, int, str]] = []

    async def worker_default():
        with use_persona(default_p):
            for _ in range(25):
                await asyncio.sleep(0.005)
                p = current_persona()
                rotator = get_key_rotator()
                # У персоны по умолчанию есть привязка timesheet со всеми необходимыми scopes
                service = default_timesheet_service(None)
                assert service is not None
                results_default.append((p.id, len(p.workspaces), rotator.get_active_key()))

    async def worker_synth():
        with use_persona(synth_p):
            for _ in range(25):
                await asyncio.sleep(0.005)
                p = current_persona()
                rotator = get_key_rotator()
                # У синтетической персоны пустой список scopes для timesheet -> MissingScopeError
                with pytest.raises(MissingScopeError):
                    default_timesheet_service(None)
                results_synth.append((p.id, len(p.workspaces), rotator.get_active_key()))

    # Запускаем обе корутины конкурентно в одном event loop
    await asyncio.gather(worker_default(), worker_synth())

    assert len(results_default) == 25
    assert len(results_synth) == 25

    # Проверка результатов персоны по умолчанию
    for persona_id, ws_count, active_key in results_default:
        assert persona_id == "popov-da-default"
        assert ws_count == 4
        assert active_key in MOCK_DEFAULT_KEYS
        assert active_key not in MOCK_SYNTH_KEYS

    # Проверка результатов синтетической персоны
    for persona_id, ws_count, active_key in results_synth:
        assert persona_id == "synthetic-test-persona"
        assert ws_count == 3
        assert active_key in MOCK_SYNTH_KEYS
        assert active_key not in MOCK_DEFAULT_KEYS


@pytest.mark.asyncio
async def test_concurrent_confirmations_isolation(tmp_path: Path):
    """Тест конкурентной изоляции записей подтверждений (ConfirmationStore) между персонами (ISO-04)."""
    db_file = tmp_path / "test_concurrency_hitl.db"
    run_migrations(db_file)
    store = ConfirmationStore(db_file)

    async def create_default_confirmations():
        for i in range(10):
            await asyncio.sleep(0.002)
            await store.create_confirmation(
                persona_id="popov-da-default",
                action_type="delete_task",
                target_id=f"def-task-{i}",
                payload={"task_id": i, "persona": "default"},
                channel=ConfirmationChannel.WEB,
                ttl_minutes=15,
            )

    async def create_synth_confirmations():
        for i in range(10):
            await asyncio.sleep(0.002)
            await store.create_confirmation(
                persona_id="synthetic-test-persona",
                action_type="delete_task",
                target_id=f"synth-task-{i}",
                payload={"task_id": i, "persona": "synthetic"},
                channel=ConfirmationChannel.TELEGRAM,
                ttl_minutes=15,
            )

    # Параллельное создание подтверждений
    await asyncio.gather(create_default_confirmations(), create_synth_confirmations())

    pending_default = await store.list_pending(persona_id="popov-da-default")
    pending_synth = await store.list_pending(persona_id="synthetic-test-persona")

    assert len(pending_default) == 10
    assert len(pending_synth) == 10

    for item in pending_default:
        assert item.persona_id == "popov-da-default"
        assert item.target_id.startswith("def-task-")
        assert item.channel == ConfirmationChannel.WEB

    for item in pending_synth:
        assert item.persona_id == "synthetic-test-persona"
        assert item.target_id.startswith("synth-task-")
        assert item.channel == ConfirmationChannel.TELEGRAM

    # Подтверждение одного элемента default не должно аффектить синтетическую персону
    confirmed_def = await store.confirm_action(pending_default[0].id, confirmed_by="user_default")
    assert confirmed_def is not None

    after_def = await store.list_pending(persona_id="popov-da-default")
    after_synth = await store.list_pending(persona_id="synthetic-test-persona")
    assert len(after_def) == 9
    assert len(after_synth) == 10

    # Отклонение одного элемента synth не должно аффектить персону default
    rejected_synth = await store.reject_action(pending_synth[0].id, rejected_by="user_synth")
    assert rejected_synth is not None

    final_def = await store.list_pending(persona_id="popov-da-default")
    final_synth = await store.list_pending(persona_id="synthetic-test-persona")
    assert len(final_def) == 9
    assert len(final_synth) == 9


@pytest.mark.asyncio
async def test_high_concurrency_persona_switching():
    """Стресс-тестирование изоляции при одновременном запуске множества корутин (ISO-04)."""
    default_p = current_persona().model_copy(update={"gemini_keys": MOCK_DEFAULT_KEYS})
    synth_cfg = synthetic_to_config(SYNTHETIC_PERSONA)["persona"]
    synth_p = PersonaConfig.model_validate(synth_cfg).model_copy(update={"gemini_keys": MOCK_SYNTH_KEYS})

    async def single_run(persona: PersonaConfig, expected_id: str, expected_ws_count: int, expected_keys: list[str]):
        with use_persona(persona):
            for _ in range(5):
                await asyncio.sleep(random.uniform(0.001, 0.008))
                p = current_persona()
                assert p.id == expected_id
                assert len(p.workspaces) == expected_ws_count
                rotator = get_key_rotator()
                assert rotator.get_active_key() in expected_keys

    # Запускаем 60 параллельных задач (30 default, 30 synth)
    tasks = []
    for idx in range(60):
        if idx % 2 == 0:
            tasks.append(single_run(default_p, "popov-da-default", 4, MOCK_DEFAULT_KEYS))
        else:
            tasks.append(single_run(synth_p, "synthetic-test-persona", 3, MOCK_SYNTH_KEYS))

    await asyncio.gather(*tasks)
