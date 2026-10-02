"""Порты коннекторов: структурные Protocol без привязки к конкретным системам.

Многоточие в качестве значения параметра по умолчанию означает «значение
задаёт реализация»: ядро не хранит данных профиля владельца.
Типы хранилища и моделей данных в ядре заменены на Any.
"""

from __future__ import annotations

from datetime import date
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


@runtime_checkable
class BaseScheduleProvider(BaseConnector, Protocol):
    """Порт источника расписания: сайт, откуда приходят занятия.

    Это отдельная роль от приёмника календаря (BaseCalendarSink): источник
    читает занятия, приёмник записывает их в календарь. Типы результата живут
    вне ядра, поэтому здесь Any.
    """

    role: ClassVar[ConnectorRole] = ConnectorRole.SCHEDULE_SOURCE

    async def fetch_schedule_raw(
        self,
        target_id: str,
        endpoint: str = "",
        param_name: str = "pr",
    ) -> Any:
        """Получить сырые данные расписания группы или преподавателя."""
        ...

    async def parse_json_payload(self, raw_json: str, group_or_teacher_id: str) -> Any:
        """Разобрать JSON расписания в нормализованную структуру."""
        ...

    async def parse_html_payload(
        self,
        html_content: str,
        group_or_teacher_id: str,
        target_date: date | None = None,
    ) -> Any:
        """Разобрать HTML-страницу расписания в нормализованную структуру."""
        ...


@runtime_checkable
class BaseCalendarSink(BaseConnector, Protocol):
    """Порт приёмника календаря: куда записываются занятия.

    Отдельная роль от источника расписания (BaseScheduleProvider). Порт
    нейтрален к поставщику: идентификатор события называется event_id.
    """

    role: ClassVar[ConnectorRole] = ConnectorRole.CALENDAR_SYNC

    async def find_existing_event(self, calendar_id: str, lesson: Any) -> dict[str, Any] | None:
        """Найти уже созданное событие для занятия."""
        ...

    async def create_event(self, calendar_id: str, lesson: Any) -> str:
        """Создать событие и вернуть его идентификатор."""
        ...

    async def patch_event(self, calendar_id: str, event_id: str, lesson: Any) -> bool:
        """Обновить существующее событие."""
        ...

    async def delete_event(self, calendar_id: str, event_id: str) -> bool:
        """Удалить событие."""
        ...

    async def sync_schedule(self, calendar_id: str, diff: Any, db: Any) -> dict[str, int]:
        """Применить разницу расписания к календарю и вернуть счётчики."""
        ...
