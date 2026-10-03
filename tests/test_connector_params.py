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
