"""Порты коннекторов: структурные Protocol без привязки к конкретным системам.

Многоточие в качестве значения параметра по умолчанию означает «значение
задаёт реализация»: ядро не хранит данных профиля владельца.
Типы хранилища и моделей данных в ядре заменены на Any.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, Protocol, runtime_checkable

from src.core.domain.entities import ConnectorRole


@runtime_checkable
class BaseConnector(Protocol):
    """Общий порт любого коннектора: идентификатор, права и проверка живости."""

    connector_id: str
    required_scopes: tuple[str, ...]

    async def health_check(self) -> bool:
        """Дешёвая проверка готовности без сети и чтения файлов учётных данных."""
        ...


@runtime_checkable
class BaseTimesheetProvider(BaseConnector, Protocol):
    """Порт источника табеля рабочего времени."""

    role: ClassVar[ConnectorRole] = ConnectorRole.TIMESHEET

    async def ingest_backup_file(
        self,
        backup_file_path: str | Path,
        default_project: str = ...,
    ) -> dict[str, Any]:
        """Загрузить резервную копию табеля и сохранить смены."""
        ...

    async def reconcile_all_conflicts(self) -> dict[str, Any]:
        """Пересчитать конфликты табеля с расписанием по всем записям."""
        ...

    async def get_timesheet_report(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        project_name: str | None = ...,
    ) -> dict[str, Any]:
        """Сформировать отчёт по табелю за период."""
        ...

    async def get_monthly_pacing(
        self,
        year: int | None = None,
        month: int | None = None,
        daily_norm: float = ...,
        project_name: str | None = ...,
    ) -> dict[str, Any]:
        """Посчитать выработку за месяц и требуемый дневной темп."""
        ...
