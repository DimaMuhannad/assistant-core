"""Protocol-проверка PRT-03: адаптеры соответствуют портам, роли разделены.

Соответствие проверяется двумя способами: isinstance (имена членов порта) и
inspect.iscoroutinefunction по каждому методу порта (isinstance сам по себе
сигнатуры и корутинность не проверяет). Тесты не ходят в сеть и не читают
учётные данные: календарь создаётся в dry_run, клиент ЛК — с пустыми
реквизитами, сервис табеля — на MagicMock.
"""

import inspect
import socket
import threading
from datetime import datetime
from pathlib import Path
from typing import Generic, Protocol
from unittest.mock import MagicMock

import pytest

from src.calendar.client import GoogleCalendarClient
from src.calendar.provider import GoogleCalendarSink
from src.connectors.aadhk.parser import AadhkIngestionService
from src.connectors.aadhk.provider import AadhkTimesheetProvider
from src.connectors.gdrive.client import GoogleDriveClient
from src.connectors.guap_lms.client import GuapLmsClient
from src.connectors.guap_lms.provider import GuapLmsProvider, _parse_deadline
from src.core.domain.entities import AcademicSubmission, ConnectorRole
from src.core.ports.clients import DriveClientLike, EmailSenderLike, LmsClientLike
from src.core.ports.connectors import (
    BaseCalendarSink,
    BaseLMSProvider,
    BaseScheduleProvider,
    BaseTimesheetProvider,
)
from src.parser.provider import ScheduleParserSource
from src.parser.schedule_parser import ScheduleParser
from src.core.exceptions import MissingScopeError
from src.composition import default_timesheet_service, default_lms_client
from src.persona.current import current_persona, use_persona
from src.sender.email_sender import EmailSender

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
        pytest.param(
            BaseLMSProvider,
            lambda: GuapLmsProvider(GuapLmsClient(email="", password="")),
            id="lms",
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
        GuapLmsProvider: ("lms_portal", ConnectorRole.LMS, ("lms.read", "lms.write")),
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
        pytest.param(
            lambda: GuapLmsProvider(GuapLmsClient(email="", password="")), False, id="lms"
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
        "connectors/guap_lms/provider.py",
    ],
)
def test_adapters_do_not_duplicate_profile_defaults(relative):
    text = (SRC / relative).read_text(encoding="utf-8")

    for forbidden in ("Тидекс", "8.5", "= 28", "Отчет по лабораторной"):
        assert forbidden not in text, f"{relative}: дефолт профиля {forbidden!r}"


LMS_CLIENT_METHODS = (
    "list_tasks",
    "get_task_details",
    "create_task",
    "delete_task",
    "set_task_visibility",
    "get_disciplines",
)


def test_lms_confirmation_markers():
    expected = frozenset({"submit_grade", "delete_task"})
    methods = _port_methods(BaseLMSProvider)

    assert BaseLMSProvider.REQUIRES_CONFIRMATION == expected
    assert GuapLmsProvider.REQUIRES_CONFIRMATION == expected
    assert GuapLmsProvider(MagicMock()).REQUIRES_CONFIRMATION == expected
    assert expected <= set(methods)


async def test_lms_submit_grade_not_implemented():
    client = MagicMock()
    provider = GuapLmsProvider(client)

    with pytest.raises(NotImplementedError):
        await provider.submit_grade("1", 5)

    assert client.mock_calls == []


async def test_lms_list_tasks_maps_to_academic_submission():
    client = MagicMock()
    client.list_tasks.return_value = [
        {"id": 101, "title": "Синтетика 1", "deadline": "15.10.2026", "is_public": True},
        {"id": "102", "title": "Синтетика 2", "deadline": "", "is_public": False},
    ]
    provider = GuapLmsProvider(client)

    result = await provider.list_tasks(28)

    assert result == [
        AcademicSubmission("101", "Синтетика 1", datetime(2026, 10, 15), True),
        AcademicSubmission("102", "Синтетика 2", None, False),
    ]
    client.list_tasks.assert_called_once_with(28)


def test_lms_deadline_parsing_tolerant():
    assert _parse_deadline("15.10.2026") == datetime(2026, 10, 15)
    for bad in ("2026-10-15", "", None, "31.02.2026"):
        assert _parse_deadline(bad) is None


async def test_lms_delete_task_runs_in_thread_and_forwards_args():
    calls: list[tuple] = []
    threads: list[int] = []

    class FakeClient:
        is_configured = True

        def delete_task(self, *args):
            threads.append(threading.get_ident())
            calls.append(args)
            return True

    provider = GuapLmsProvider(FakeClient())

    assert await provider.delete_task(7, 28) is True
    assert await provider.delete_task(7) is True

    assert calls == [(7, 28), (7,)]
    assert all(t != threading.get_ident() for t in threads)


async def test_existing_clients_match_di_protocols(tmp_path):
    lms = GuapLmsClient(email="", password="")
    assert isinstance(lms, LmsClientLike)
    for name in LMS_CLIENT_METHODS:
        assert not inspect.iscoroutinefunction(getattr(lms, name)), name

    sender = EmailSender()
    assert isinstance(sender, EmailSenderLike)
    assert inspect.iscoroutinefunction(sender.send_reply)

    drive = GoogleDriveClient(
        token_path=tmp_path / "absent-token.json",
        credentials_path=tmp_path / "absent-creds.json",
    )
    assert isinstance(drive, DriveClientLike)
    assert inspect.iscoroutinefunction(drive.sync_aadhk_from_drive)


def test_lms_provider_not_wired_into_production():
    files = [
        *sorted((SRC / "notifier").glob("*.py")),
        *sorted((SRC / "brain").glob("*.py")),
        SRC / "main.py",
        SRC / "composition.py",
    ]

    assert files
    for path in files:
        assert "GuapLmsProvider" not in path.read_text(encoding="utf-8"), path.name


def test_connectors_declare_required_scopes():
    assert BaseTimesheetProvider.required_scopes == ("timesheet.read", "timesheet.write")
    assert BaseScheduleProvider.required_scopes == ("schedule.read",)
    assert BaseCalendarSink.required_scopes == ("calendar.read", "calendar.write")
    assert BaseLMSProvider.required_scopes == ("lms.read", "lms.write")

    assert AadhkTimesheetProvider.required_scopes == ("timesheet.read", "timesheet.write")
    assert ScheduleParserSource.required_scopes == ("schedule.read",)
    assert GoogleCalendarSink.required_scopes == ("calendar.read", "calendar.write")
    assert GuapLmsProvider.required_scopes == ("lms.read", "lms.write")
    assert GuapLmsClient.required_scopes == ("lms.read", "lms.write")


def test_composition_missing_scope_error():
    base = current_persona()

    # Persona with incomplete scopes for timesheet
    broken_binding = base.connectors.timesheet[0].model_copy(update={"scopes": ["timesheet.read"]})
    broken_connectors = base.connectors.model_copy(update={"timesheet": [broken_binding]})
    p_broken = base.model_copy(update={"connectors": broken_connectors})

    with use_persona(p_broken):
        with pytest.raises(MissingScopeError) as exc_info:
            default_timesheet_service(MagicMock())
        assert "timesheet" in str(exc_info.value)
        assert "scopes" in str(exc_info.value)


def test_composition_unbound_role_returns_none():
    base = current_persona()

    # Persona without timesheet or lms bindings
    unbound_connectors = base.connectors.model_copy(update={"timesheet": [], "lms": []})
    p_unbound = base.model_copy(update={"connectors": unbound_connectors})

    with use_persona(p_unbound):
        assert default_timesheet_service(MagicMock()) is None
        assert default_lms_client() is None

