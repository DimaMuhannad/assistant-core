"""Protocol-проверка PRT-03: адаптеры соответствуют портам, роли разделены.

Соответствие проверяется двумя способами: isinstance (имена членов порта) и
inspect.iscoroutinefunction по каждому методу порта (isinstance сам по себе
сигнатуры и корутинность не проверяет). Тесты не ходят в сеть и не читают
учётные данные: календарь создаётся в dry_run, клиент ЛК — с пустыми
реквизитами, сервис табеля — на MagicMock.
"""

import inspect
import socket
from pathlib import Path
from typing import Generic, Protocol
from unittest.mock import MagicMock

import pytest

from src.calendar.client import GoogleCalendarClient
from src.calendar.provider import GoogleCalendarSink
from src.connectors.aadhk.parser import AadhkIngestionService
from src.connectors.aadhk.provider import AadhkTimesheetProvider
from src.core.domain.entities import ConnectorRole
from src.core.ports.connectors import (
    BaseCalendarSink,
    BaseScheduleProvider,
    BaseTimesheetProvider,
)
from src.parser.provider import ScheduleParserSource
from src.parser.schedule_parser import ScheduleParser

SRC = Path(__file__).resolve().parent.parent / "src"


def _port_methods(port) -> tuple[str, ...]:
    """Публичные функции-члены порта и его Protocol-предков."""
    names: set[str] = set()
    for cls in port.__mro__:
        if cls in (Protocol, Generic, object):
            continue
        if not cls.__dict__.get("_is_protocol", False):
            continue
        for name, value in vars(cls).items():
            if inspect.isfunction(value) and not name.startswith("_"):
                names.add(name)
    return tuple(sorted(names))


def _pairs() -> list:
    """Пары порт - адаптер; конструирование без сети и файлов учётных данных."""
    return [
        pytest.param(
            BaseScheduleProvider,
            lambda: ScheduleParserSource(ScheduleParser()),
            id="schedule",
        ),
        pytest.param(
            BaseCalendarSink,
            lambda: GoogleCalendarSink(GoogleCalendarClient(dry_run=True)),
            id="calendar",
        ),
        pytest.param(
            BaseTimesheetProvider,
            lambda: AadhkTimesheetProvider(AadhkIngestionService(MagicMock())),
            id="timesheet",
        ),
    ]


@pytest.mark.parametrize("port, make", _pairs())
def test_adapter_conforms_to_port(port, make):
    assert isinstance(make(), port)


@pytest.mark.parametrize("port, make", _pairs())
def test_port_methods_are_coroutines_on_adapter(port, make):
    adapter = make()
    methods = _port_methods(port)

    assert methods
    assert "health_check" in methods
    for name in methods:
        member = getattr(adapter, name, None)
        assert member is not None, f"у адаптера нет метода {name}"
        assert inspect.iscoroutinefunction(member), f"{name} не корутина"
        assert inspect.iscoroutinefunction(getattr(port, name)), f"{name} порта не async"


def test_schedule_roles_are_separated():
    source = ScheduleParserSource(ScheduleParser())
    sink = GoogleCalendarSink(GoogleCalendarClient(dry_run=True))

    assert isinstance(source, BaseScheduleProvider)
    assert not isinstance(source, BaseCalendarSink)
    assert isinstance(sink, BaseCalendarSink)
    assert not isinstance(sink, BaseScheduleProvider)
    assert source.role != sink.role
    assert source.role == ConnectorRole.SCHEDULE_SOURCE
    assert sink.role == ConnectorRole.CALENDAR_SYNC


def test_adapter_roles_and_ids():
    expected = {
        ScheduleParserSource: ("schedule_site", ConnectorRole.SCHEDULE_SOURCE, ("schedule.read",)),
        GoogleCalendarSink: (
            "google_calendar",
            ConnectorRole.CALENDAR_SYNC,
            ("calendar.read", "calendar.write"),
        ),
        AadhkTimesheetProvider: (
            "aadhk_timesheet",
            ConnectorRole.TIMESHEET,
            ("timesheet.read", "timesheet.write"),
        ),
    }
    for cls, (connector_id, role, scopes) in expected.items():
        assert cls.connector_id == connector_id
        assert cls.role == role
        assert cls.required_scopes == scopes
        assert isinstance(cls.required_scopes, tuple)
        assert all(isinstance(s, str) for s in cls.required_scopes)


@pytest.mark.parametrize(
    "make, expected",
    [
        pytest.param(lambda: ScheduleParserSource(ScheduleParser()), True, id="schedule"),
        pytest.param(lambda: GoogleCalendarSink(GoogleCalendarClient(dry_run=True)), False, id="calendar"),
        pytest.param(
            lambda: AadhkTimesheetProvider(AadhkIngestionService(MagicMock())), True, id="timesheet"
        ),
    ],
)
async def test_health_check_is_offline(monkeypatch, make, expected):
    def _forbidden(self, *args, **kwargs):
        raise AssertionError("сеть запрещена")

    adapter = make()
    monkeypatch.setattr(socket.socket, "connect", _forbidden)

    assert await adapter.health_check() is expected


@pytest.mark.parametrize(
    "relative",
    [
        "parser/provider.py",
        "calendar/provider.py",
        "connectors/aadhk/provider.py",
    ],
)
def test_adapters_do_not_duplicate_profile_defaults(relative):
    text = (SRC / relative).read_text(encoding="utf-8")

    for forbidden in ("Тидекс", "8.5", "= 28", "Отчет по лабораторной"):
        assert forbidden not in text, f"{relative}: дефолт профиля {forbidden!r}"
