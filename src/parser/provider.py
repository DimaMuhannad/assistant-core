"""Адаптер источника расписания к порту BaseScheduleProvider.

Обёртка делегирует вызовы ScheduleParser. Порт полностью async, а разбор
payload у конкретного класса синхронный: адаптер закрывает это несовпадение
(конкретный класс не меняется). Пока адаптер ни к чему не подключён.
"""

from datetime import date
from typing import Any

from src.core.domain.entities import ConnectorRole


class ScheduleParserSource:
    """Сайт расписания как реализация порта BaseScheduleProvider."""

    connector_id = "schedule_site"
    required_scopes = ("schedule.read",)
    role = ConnectorRole.SCHEDULE_SOURCE

    def __init__(self, parser: Any) -> None:
        self._parser = parser

    async def health_check(self) -> bool:
        """Готовность без сети: у парсера задан базовый адрес."""
        return bool(self._parser.base_url)

    async def fetch_schedule_raw(
        self,
        target_id: str,
        endpoint: str = "",
        param_name: str = "pr",
    ) -> Any:
        return await self._parser.fetch_schedule_raw(target_id, endpoint, param_name)

    async def parse_json_payload(self, raw_json: str, group_or_teacher_id: str) -> Any:
        return self._parser.parse_json_payload(raw_json, group_or_teacher_id)

    async def parse_html_payload(
        self,
        html_content: str,
        group_or_teacher_id: str,
        target_date: date | None = None,
    ) -> Any:
        return self._parser.parse_html_payload(html_content, group_or_teacher_id, target_date)
