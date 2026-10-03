"""PER-06: параметры коннекторов читаются из персоны (привязки connector_bindings).

Для персоны по умолчанию значения прежние (BCK-01), синтетическая персона на тех же кодовых
путях получает свои значения (PER-09: дефолты и scope-решения). Значения берутся в момент
вызова: персону подменяет use_persona, файлы и переменные окружения не трогаются.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.persona.current import use_persona
from src.persona.loader import PERSONA_CONFIG_ENV, load_persona
from src.persona.models import PersonaConfig

from .synthetic_persona import SYNTHETIC_PERSONA, synthetic_to_config

SYNTHETIC_PROJECT = SYNTHETIC_PERSONA["timesheet"]["default_project"]
SYNTHETIC_NORM = SYNTHETIC_PERSONA["timesheet"]["daily_norm_hours"]


@pytest.fixture(autouse=True)
def _default_persona_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PERSONA_CONFIG_ENV, raising=False)


@pytest.fixture
def synthetic_loaded(tmp_path: Path) -> PersonaConfig:
    """Синтетическая персона, загруженная тем же load_persona, что и персона по умолчанию."""
    path = tmp_path / "persona.json"
    path.write_text(json.dumps(synthetic_to_config(SYNTHETIC_PERSONA), ensure_ascii=False), encoding="utf-8")
    return load_persona(path)


# --- Задача 1: аксессоры привязок и табель -------------------------------------------------


def test_timesheet_settings_default_persona() -> None:
    from src.persona.bindings import format_hours, timesheet_settings

    settings = timesheet_settings()

    assert settings.default_project == "Тидекс"
    assert settings.daily_norm_hours == 8.5
    assert format_hours(settings.daily_norm_hours) == "8.5"


def test_timesheet_settings_follow_active_persona(synthetic_loaded: PersonaConfig) -> None:
    from src.persona.bindings import format_hours, timesheet_settings

    with use_persona(synthetic_loaded):
        settings = timesheet_settings()

    assert settings.default_project == SYNTHETIC_PROJECT
    assert settings.daily_norm_hours == SYNTHETIC_NORM
    assert format_hours(settings.daily_norm_hours) == "6"
    assert timesheet_settings().default_project == "Тидекс"  # вне блока снова персона по умолчанию


def test_binding_without_role_entry_names_role(synthetic_loaded: PersonaConfig) -> None:
    from src.persona.bindings import binding
    from src.persona.models import PersonaConfigError

    with pytest.raises(PersonaConfigError, match="notion"):
        binding("notion", synthetic_loaded)


def test_missing_config_key_names_role_and_key(synthetic_loaded: PersonaConfig) -> None:
    from src.persona.bindings import timesheet_settings
    from src.persona.models import PersonaConfigError

    broken = synthetic_loaded.model_copy(deep=True)
    del broken.connectors.timesheet[0].config["daily_norm_hours"]

    with pytest.raises(PersonaConfigError, match="timesheet.*daily_norm_hours"):
        timesheet_settings(broken)


async def _recording_pacing(monkeypatch: pytest.MonkeyPatch, **call_kwargs) -> tuple[dict, list[dict]]:
    from src.connectors.aadhk.parser import AadhkIngestionService
    from src.storage.db import Database

    calls: list[dict] = []

    async def list_timesheet_records(**kwargs):
        calls.append(kwargs)
        return []

    db = Database(db_path=":memory:")
    monkeypatch.setattr(db, "list_timesheet_records", list_timesheet_records)
    pacing = await AadhkIngestionService(db).get_monthly_pacing(year=2026, month=10, **call_kwargs)
    return pacing, calls


async def test_aadhk_monthly_pacing_default_persona(monkeypatch: pytest.MonkeyPatch) -> None:
    pacing, calls = await _recording_pacing(monkeypatch)

    assert pacing["monthly_norm_hours"] == pacing["total_workdays"] * 8.5
    assert calls[0]["project_name"] == "Тидекс"


async def test_aadhk_monthly_pacing_uses_persona_norm_and_project(
    monkeypatch: pytest.MonkeyPatch, synthetic_loaded: PersonaConfig
) -> None:
    with use_persona(synthetic_loaded):
        pacing, calls = await _recording_pacing(monkeypatch)

    assert pacing["monthly_norm_hours"] == pacing["total_workdays"] * SYNTHETIC_NORM
    assert calls[0]["project_name"] == SYNTHETIC_PROJECT


async def test_aadhk_explicit_arguments_beat_persona(
    monkeypatch: pytest.MonkeyPatch, synthetic_loaded: PersonaConfig
) -> None:
    with use_persona(synthetic_loaded):
        pacing, calls = await _recording_pacing(monkeypatch, daily_norm=2.0, project_name="Явный")
        _, all_projects = await _recording_pacing(monkeypatch, project_name=None)

    assert pacing["monthly_norm_hours"] == pacing["total_workdays"] * 2.0
    assert calls[0]["project_name"] == "Явный"
    assert all_projects[0]["project_name"] is None  # явный None по-прежнему означает «все проекты»


def test_aadhk_service_takes_explicit_settings() -> None:
    from src.connectors.aadhk.parser import AadhkIngestionService
    from src.persona.bindings import TimesheetSettings

    explicit = TimesheetSettings(default_project="Явный проект", daily_norm_hours=4.0)
    service = AadhkIngestionService(MagicMock(), settings=explicit)

    assert service.settings is explicit
    assert AadhkIngestionService(MagicMock()).settings.default_project == "Тидекс"


def _pacing_payload() -> dict:
    return {
        "month": 3,
        "year": 2026,
        "delta_pacing": 1.25,
        "monthly_norm_hours": 120.0,
        "total_workdays": 20,
        "worked_hours": 42.5,
        "total_shifts": 6,
        "remaining_hours_to_norm": 77.5,
        "required_daily_pacing": 5.0,
        "remaining_workdays": 15,
        "morning_delta": 0.0,
        "worked": 0.0,
    }


async def test_secretary_and_ticker_pass_persona_project_and_norm(synthetic_loaded: PersonaConfig) -> None:
    from src.brain.secretary_dialog import SecretaryDialogEngine
    from src.notifier.live_ticker import LiveTickerService

    calls: list[dict] = []

    class FakeProvider:
        async def get_monthly_pacing(self, *args, **kwargs):
            calls.append(kwargs)
            return _pacing_payload()

    with use_persona(synthetic_loaded):
        text = await SecretaryDialogEngine(
            db=MagicMock(), api_key="", timesheet_service=FakeProvider()
        )._get_tydex_context()
        await LiveTickerService(db=MagicMock(), timesheet_service=FakeProvider()).get_timesheet_metrics()

    assert calls == [{"project_name": SYNTHETIC_PROJECT}, {"project_name": SYNTHETIC_PROJECT}]
    assert "по 6 ч" in text
    assert "по 8.5 ч" not in text


def test_bindings_match_adapter_ids_and_scopes() -> None:
    from src.calendar.provider import GoogleCalendarSink
    from src.connectors.aadhk.provider import AadhkTimesheetProvider
    from src.connectors.guap_lms.provider import GuapLmsProvider
    from src.parser.provider import ScheduleParserSource
    from src.persona.bindings import binding

    adapters = {
        "schedule_source": ScheduleParserSource,
        "calendar_sync": GoogleCalendarSink,
        "timesheet": AadhkTimesheetProvider,
        "lms": GuapLmsProvider,
    }
    for role, adapter in adapters.items():
        bound = binding(role)
        assert bound.provider == adapter.connector_id, role
        assert tuple(bound.scopes) == adapter.required_scopes, role


# --- Задача 2: расписание ------------------------------------------------------------------


def _lesson(subject: str, start: str, end: str, group: str | None = "1632"):
    from datetime import date, time

    from src.models.schedule import Lesson, LessonType

    return Lesson(
        subject=subject,
        lesson_type=LessonType.LAB,
        room="31-04б",
        group=group,
        date=date(2026, 10, 1),
        start_time=time.fromisoformat(start),
        end_time=time.fromisoformat(end),
    )


def test_lesson_slots_and_subjects_default_persona() -> None:
    from src.models.schedule import (
        format_academic_lesson_line,
        get_guap_pair_number,
        lesson_slot_numbers,
        subject_short_names,
    )

    assert lesson_slot_numbers() == {
        "09:30": 1, "11:10": 2, "13:00": 3, "15:10": 4, "17:00": 5, "18:40": 6, "20:20": 7,
    }
    assert get_guap_pair_number("11:10") == 2
    assert get_guap_pair_number("11:25") == 2  # допуск ±15 минут сохранён
    assert get_guap_pair_number("11:26") is None
    assert subject_short_names()["физические основы нанотехнологий"] == "ФОНТ"
    assert format_academic_lesson_line(_lesson("Физика", "11:10", "12:45")) == (
        "2) 11:10 • [Лаб] Физика (гр. 1632, ауд. 31-04б)"
    )


def test_lesson_slots_and_subjects_from_persona(synthetic_loaded: PersonaConfig) -> None:
    from src.models.schedule import (
        format_academic_lesson_line,
        get_guap_pair_number,
        lesson_slot_numbers,
        subject_short_names,
    )

    with use_persona(synthetic_loaded):
        assert lesson_slot_numbers() == {"08:15": 1}
        assert get_guap_pair_number("08:15") == 1
        assert get_guap_pair_number("11:10") is None
        assert subject_short_names() == {"синтетическая механика": "СинтМех"}
        line = format_academic_lesson_line(_lesson("Синтетическая механика", "08:15", "09:45"))
        assert line == "1) 08:15 • [Лаб] СинтМех (гр. 1632, ауд. 31-04б)"


def test_calendar_formatting_follows_persona(synthetic_loaded: PersonaConfig) -> None:
    from src.calendar.client import GoogleCalendarClient

    lesson = _lesson("Синтетическая механика", "08:15", "09:45")
    default_lesson = _lesson("Физика", "09:30", "11:00")

    assert "Пара: 1 (09:30—11:00)" in GoogleCalendarClient.format_description(default_lesson)
    with use_persona(synthetic_loaded):
        assert GoogleCalendarClient.format_summary(lesson) == "[1632] СинтМех (Лаб)"
        description = GoogleCalendarClient.format_description(lesson)

    assert "Пара: 1 (08:15—09:45)" in description
    assert "Предмет: Синтетическая механика (СинтМех)" in description


def test_calendar_and_ticker_have_no_own_subject_dicts() -> None:
    import src.calendar.client as calendar_client
    import src.notifier.live_ticker as live_ticker

    for module in (calendar_client, live_ticker):
        assert not hasattr(module, "SUBJECT_SHORT_NAMES"), module.__name__
        own = [
            name
            for name, value in vars(module).items()
            if isinstance(value, dict) and "ФОНТ" in value.values()
        ]
        assert not own, f"{module.__name__}: собственный словарь коротких названий {own}"


def test_ticker_uses_persona_subject_names(synthetic_loaded: PersonaConfig) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from src import config
    from src.notifier.live_ticker import LiveTickerService

    now = datetime(2026, 10, 1, 8, 30, tzinfo=ZoneInfo(config.TZ))
    lesson = _lesson("Синтетическая механика", "08:15", "09:45")
    service = LiveTickerService(db=MagicMock())

    with use_persona(synthetic_loaded):
        line = service.compute_ticker_line([lesson], {"pending_count": 0}, {"worked_hours": 1.0}, now)

    assert "СинтМех" in line


def test_schedule_site_url_env_wins_over_persona(
    monkeypatch: pytest.MonkeyPatch, synthetic_loaded: PersonaConfig
) -> None:
    from src import config
    from src.composition import schedule_site_url

    monkeypatch.setattr(config, "SCHEDULE_URL", "")
    assert schedule_site_url() == "https://guap.ru/rasp"
    with use_persona(synthetic_loaded):
        assert schedule_site_url() == "https://schedule.synthetic.example/"

    monkeypatch.setattr(config, "SCHEDULE_URL", "https://env.example/schedule")
    assert schedule_site_url() == "https://env.example/schedule"
    with use_persona(synthetic_loaded):
        assert schedule_site_url() == "https://env.example/schedule"  # окружение сильнее персоны


def test_schedule_parser_default_base_url_from_persona(synthetic_loaded: PersonaConfig) -> None:
    from src.parser.schedule_parser import ScheduleParser

    assert ScheduleParser().base_url == "https://guap.ru/rasp"
    with use_persona(synthetic_loaded):
        assert ScheduleParser().base_url == "https://schedule.synthetic.example"
    assert ScheduleParser(base_url="https://explicit.example/").base_url == "https://explicit.example"
