"""Адаптер AADHk к порту BaseTimesheetProvider.

Обёртка делегирует вызовы AadhkIngestionService и пробрасывает *args/**kwargs,
поэтому зашитые значения по умолчанию остаются только в конкретном классе.
Сам сервис этот модуль не импортирует: сборку выполняет src.composition.
"""

from typing import Any

from src.core.domain.entities import ConnectorRole


class AadhkTimesheetProvider:
    """Табель AADHk как реализация порта BaseTimesheetProvider."""

    connector_id = "aadhk_timesheet"
    required_scopes = ("timesheet.read", "timesheet.write")
    role = ConnectorRole.TIMESHEET

    def __init__(self, service: Any) -> None:
        self._service = service

    async def health_check(self) -> bool:
        """Готовность без сети и файлов: у сервиса есть хранилище."""
        return self._service.db is not None

    async def ingest_backup_file(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self._service.ingest_backup_file(*args, **kwargs)

    async def reconcile_all_conflicts(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self._service.reconcile_all_conflicts(*args, **kwargs)

    async def get_timesheet_report(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self._service.get_timesheet_report(*args, **kwargs)

    async def get_monthly_pacing(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self._service.get_monthly_pacing(*args, **kwargs)
