"""Адаптер Google Calendar к порту BaseCalendarSink.

Обёртка делегирует вызовы GoogleCalendarClient позиционно: event_id порта
уходит на место google_event_id конкретного класса. Пока адаптер ни к чему
не подключён.
"""

from typing import Any

from src.core.domain.entities import ConnectorRole


class GoogleCalendarSink:
    """Google Calendar как реализация порта BaseCalendarSink."""

    connector_id = "google_calendar"
    required_scopes = ("calendar.read", "calendar.write")
    role = ConnectorRole.CALENDAR_SYNC

    def __init__(self, client: Any) -> None:
        self._client = client

    async def health_check(self) -> bool:
        """Готовность без сети и файлов: сервис календаря уже инициализирован."""
        return self._client.service is not None

    async def find_existing_event(self, calendar_id: str, lesson: Any) -> dict[str, Any] | None:
        return await self._client.find_existing_event(calendar_id, lesson)

    async def create_event(self, calendar_id: str, lesson: Any) -> str:
        return await self._client.create_event(calendar_id, lesson)

    async def patch_event(self, calendar_id: str, event_id: str, lesson: Any) -> bool:
        return await self._client.patch_event(calendar_id, event_id, lesson)

    async def delete_event(self, calendar_id: str, event_id: str) -> bool:
        return await self._client.delete_event(calendar_id, event_id)

    async def sync_schedule(self, calendar_id: str, diff: Any, db: Any) -> dict[str, int]:
        return await self._client.sync_schedule(calendar_id, diff, db)
