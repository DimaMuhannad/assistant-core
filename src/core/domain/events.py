"""Доменные события ядра: неизменяемые dataclass без полезной нагрузки (кроме делегирования).

Только stdlib. Время события хранится с часовым поясом UTC. Поля-ключевые слова
(kw_only) позволят будущим событиям добавлять обязательные поля без перестановки аргументов.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent:
    """Базовое событие: уникальный идентификатор и время возникновения (UTC)."""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True, slots=True, kw_only=True)
class ScheduleChanged(DomainEvent):
    """Расписание изменилось."""


@dataclass(frozen=True, slots=True, kw_only=True)
class TimesheetSynced(DomainEvent):
    """Табель синхронизирован."""


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskCreated(DomainEvent):
    """Создана задача."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SecurityViolationDetected(DomainEvent):
    """Обнаружено нарушение политики безопасности."""


@dataclass(frozen=True, slots=True, kw_only=True)
class DialogMemoryCleared(DomainEvent):
    """Память диалога очищена."""


@dataclass(frozen=True, slots=True, kw_only=True)
class DelegatedToSpecialist(DomainEvent):
    """Задача передана специалисту-агенту."""

    from_agent: str = ""
    to_agent: str = ""
    reason: str = ""
