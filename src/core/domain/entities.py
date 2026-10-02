"""Доменные сущности ядра.

Только stdlib. Сущности объявляются здесь, схема персоны и загрузчики
появятся в следующих фазах.
"""

from enum import StrEnum


class ConnectorRole(StrEnum):
    """Роль коннектора в платформе (для портов, существующих в этой фазе)."""

    SCHEDULE_SOURCE = "schedule_source"
    CALENDAR_SYNC = "calendar_sync"
    TIMESHEET = "timesheet"
    LMS = "lms"
