"""Доменные сущности ядра.

Только stdlib. Все сущности неизменяемы (frozen) и без __dict__ (slots);
коллекции — tuple. Схема персоны и загрузчики появятся в следующих фазах.
"""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class ConnectorRole(StrEnum):
    """Роль коннектора в платформе.

    GIT_SOURCE и NOTION только объявлены (привязки в персоне допустимы, пустые); портов и
    реализаций у них нет до Фазы 7.
    """

    SCHEDULE_SOURCE = "schedule_source"
    CALENDAR_SYNC = "calendar_sync"
    TIMESHEET = "timesheet"
    LMS = "lms"
    GIT_SOURCE = "git_source"
    NOTION = "notion"


class WorkspaceClearance(StrEnum):
    """Уровень допуска рабочего пространства."""

    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED_NDA = "restricted_nda"


@dataclass(frozen=True, slots=True)
class ScheduleEvent:
    """Событие расписания (пара, встреча)."""

    external_id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    location: str | None = None


@dataclass(frozen=True, slots=True)
class WorkRecord:
    """Запись о рабочей смене; метка проекта обязательна и без значения по умолчанию."""

    shift_date: date
    hours: float
    project_tag: str


@dataclass(frozen=True, slots=True)
class AcademicSubmission:
    """Академическое задание в личном кабинете; срок может быть неизвестен."""

    submission_id: str
    title: str
    deadline: datetime | None
    is_public: bool


@dataclass(frozen=True, slots=True)
class Task:
    """Задача; область (area) — свободная строка."""

    title: str
    area: str
    status: str


@dataclass(frozen=True, slots=True)
class EmailMessage:
    """Письмо. Правило обработки NDA-почты появится в следующих фазах."""

    message_id: str
    subject: str
    sender: str
    received_at: datetime
    body: str = ""
    workspace_id: str | None = None


@dataclass(frozen=True, slots=True)
class Workspace:
    """Рабочее пространство с уровнем допуска."""

    id: str
    name: str
    clearance: WorkspaceClearance
    path: str
    remote: str | None = None
    ssh_alias: str | None = None
    notion_project: str | None = None


@dataclass(frozen=True, slots=True)
class GitCommit:
    """Неизменяемое представление коммита."""

    hash: str
    author: str
    date: datetime
    message: str
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0


@dataclass(frozen=True, slots=True)
class GitProgressReport:
    """Оценка хода работ по проекту."""

    workspace_id: str
    notion_project_id: str | None
    period_start: datetime
    period_end: datetime
    commit_count: int
    latest_commit_date: datetime | None
    summary_text: str
    is_stagnant: bool
    clearance: WorkspaceClearance


@dataclass(frozen=True, slots=True)
class Persona:
    """Минимальный профиль владельца: идентификатор, имя и пространства."""

    id: str
    name: str
    workspaces: tuple[Workspace, ...] = ()

