"""Параметры коннекторов из привязок персоны (PER-06, D-18).

Адаптеры и места вызова берут значения здесь, в момент вызова: персона по умолчанию -
current_persona() (подменяется use_persona), явная персона - аргумент. Значения нигде, кроме
данных персоны, не известны. Модуль лист зависимостей (контракт persona-is-leaf): только
stdlib и src.persona.*. Ошибки называют роль и ключ, значения конфигурации не печатаются.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.persona.current import current_persona
from src.persona.models import ConnectorBindingConfig, MethodistConfig, PersonaConfig, PersonaConfigError


@dataclass(frozen=True)
class TimesheetSettings:
    """Проект учёта и суточная норма часов (привязка timesheet)."""

    default_project: str
    daily_norm_hours: float


@dataclass(frozen=True)
class LessonSlot:
    """Слот пары: номер и время начала (HH:MM), конец необязателен."""

    number: int
    start: str
    end: str | None = None


@dataclass(frozen=True)
class ScheduleSourceSettings:
    """Адрес сайта расписания, слоты пар и короткие названия предметов (привязка schedule_source)."""

    base_url: str
    lesson_slots: tuple[LessonSlot, ...]
    subjects: dict[str, str]


@dataclass(frozen=True)
class LmsSettings:
    """Адрес личного кабинета (привязка lms)."""

    base_url: str


def binding(role: str, persona: PersonaConfig | None = None) -> ConnectorBindingConfig:
    """Первая привязка роли; нет привязки - PersonaConfigError с названием роли."""
    persona = persona or current_persona()
    bindings = getattr(persona.connectors, role, None)
    if not bindings:
        raise PersonaConfigError(f"в персоне нет привязки коннектора для роли {role}")
    return bindings[0]


def _config_value(bound: ConnectorBindingConfig, role: str, key: str) -> Any:
    try:
        return bound.config[key]
    except KeyError:
        raise PersonaConfigError(f"в привязке {role} нет ключа конфигурации {key}") from None


def timesheet_settings(persona: PersonaConfig | None = None) -> TimesheetSettings:
    bound = binding("timesheet", persona)
    return TimesheetSettings(
        default_project=str(_config_value(bound, "timesheet", "default_project")),
        daily_norm_hours=float(_config_value(bound, "timesheet", "daily_norm_hours")),
    )


def schedule_source_settings(persona: PersonaConfig | None = None) -> ScheduleSourceSettings:
    bound = binding("schedule_source", persona)
    slots = tuple(
        LessonSlot(
            number=int(slot["number"]),
            start=str(slot["start"]),
            end=str(slot["end"]) if slot.get("end") else None,
        )
        for slot in _config_value(bound, "schedule_source", "lesson_slots")
    )
    subjects = {
        str(full): str(short) for full, short in _config_value(bound, "schedule_source", "subjects").items()
    }
    return ScheduleSourceSettings(
        base_url=str(_config_value(bound, "schedule_source", "base_url")),
        lesson_slots=slots,
        subjects=subjects,
    )


def lms_settings(persona: PersonaConfig | None = None) -> LmsSettings:
    bound = binding("lms", persona)
    return LmsSettings(base_url=str(_config_value(bound, "lms", "base_url")))


def methodist_settings(persona: PersonaConfig | None = None) -> MethodistConfig:
    """Каталоги, каталог файлов и правила области методиста - блок persona.methodist."""
    return (persona or current_persona()).methodist


def format_hours(value: float) -> str:
    """Норма часов для текстов: 8.5 -> «8.5», 6.0 -> «6»."""
    return f"{value:g}"
