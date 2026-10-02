"""Тесты PRT-05: внутрипроцессная шина доменных событий (D-16, D-17)."""

import asyncio
import dataclasses
import logging
from datetime import timedelta
from pathlib import Path

import pytest

from src.core.domain.events import (
    DelegatedToSpecialist,
    DialogMemoryCleared,
    DomainEvent,
    ScheduleChanged,
    SecurityViolationDetected,
    TaskCreated,
    TimesheetSynced,
)
from src.core.events.bus import EventBus

REPO = Path(__file__).resolve().parents[1]


async def test_publish_delivers_to_subscriber():
    got: list = []
    bus = EventBus()
    bus.subscribe(TaskCreated, got.append)
    event = TaskCreated()

    await bus.publish(event)

    assert len(got) == 1
    assert got[0] is event


async def test_handlers_called_in_subscription_order():
    marks: list[str] = []
    bus = EventBus()
    bus.subscribe(TaskCreated, lambda e: marks.append("a"))
    bus.subscribe(TaskCreated, lambda e: marks.append("b"))
    bus.subscribe(TaskCreated, lambda e: marks.append("c"))

    await bus.publish(TaskCreated())

    assert marks == ["a", "b", "c"]


async def test_failing_subscriber_is_isolated(caplog):
    called: list = []

    def broken(event):
        raise RuntimeError("boom")

    bus = EventBus()
    bus.subscribe(TaskCreated, broken)
    bus.subscribe(TaskCreated, called.append)

    with caplog.at_level(logging.ERROR):
        await bus.publish(TaskCreated())

    assert len(called) == 1
    assert "TaskCreated" in caplog.text


async def test_failure_log_has_no_payload(caplog):
    def broken(event):
        raise RuntimeError("boom")

    bus = EventBus()
    bus.subscribe(DelegatedToSpecialist, broken)
    event = DelegatedToSpecialist(from_agent="a", to_agent="b", reason="SYNTH-PAYLOAD-MARKER")

    with caplog.at_level(logging.ERROR):
        await bus.publish(event)

    assert "SYNTH-PAYLOAD-MARKER" not in caplog.text
    assert "DelegatedToSpecialist" in caplog.text


async def test_unsubscribed_type_not_delivered():
    got: list = []
    bus = EventBus()
    bus.subscribe(ScheduleChanged, got.append)

    await bus.publish(TaskCreated())

    assert got == []


async def test_dispatch_is_exact_type_only():
    got: list = []
    bus = EventBus()
    bus.subscribe(DomainEvent, got.append)

    await bus.publish(TaskCreated())

    assert got == []


async def test_sync_and_async_handlers():
    sync_got: list = []
    async_got: list = []

    async def async_handler(event):
        async_got.append(event)

    bus = EventBus()
    bus.subscribe(TaskCreated, sync_got.append)
    bus.subscribe(TaskCreated, async_handler)
    event = TaskCreated()

    await bus.publish(event)

    assert sync_got == [event]
    assert async_got == [event]


async def test_cancelled_error_propagates():
    async def cancelled(event):
        raise asyncio.CancelledError()

    bus = EventBus()
    bus.subscribe(TaskCreated, cancelled)

    with pytest.raises(asyncio.CancelledError):
        await bus.publish(TaskCreated())


def test_event_defaults_utc_and_unique_id():
    first, second = TaskCreated(), TaskCreated()

    assert first.occurred_at.utcoffset() == timedelta(0)
    assert first.event_id != second.event_id


def test_events_are_frozen():
    event = DelegatedToSpecialist(from_agent="a")

    with pytest.raises(dataclasses.FrozenInstanceError):
        event.from_agent = "b"


def test_six_domain_event_types():
    classes = {
        c.__name__: c
        for c in (
            ScheduleChanged,
            TimesheetSynced,
            TaskCreated,
            SecurityViolationDetected,
            DialogMemoryCleared,
            DelegatedToSpecialist,
        )
    }

    assert set(classes) == {
        "ScheduleChanged",
        "TimesheetSynced",
        "TaskCreated",
        "SecurityViolationDetected",
        "DialogMemoryCleared",
        "DelegatedToSpecialist",
    }
    for cls in classes.values():
        assert issubclass(cls, DomainEvent)
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen is True


def test_bus_not_wired_into_production_flows():
    """D-17: шина и события не подключены к боевым потокам этой фазы."""
    paths = list((REPO / "src" / "brain").rglob("*.py"))
    paths += list((REPO / "src" / "notifier").rglob("*.py"))
    paths += [REPO / "src" / "main.py", REPO / "src" / "composition.py"]
    assert len(paths) > 2

    offenders = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        offenders += [
            f"{path.name}: {s}"
            for s in ("EventBus", "src.core.events", "src.core.domain.events")
            if s in text
        ]
    assert not offenders, offenders
