"""Корень композиции: единственное место (кроме src/main.py), знающее конкретные классы.

Фабрики импортируют адаптеры лениво, внутри функций: так патчи модулей-источников
в тестах (например, src.connectors.aadhk.parser.AadhkIngestionService)
продолжают работать, а use-cases не импортируют адаптеры на верхнем уровне.
"""

from __future__ import annotations

from typing import Any

from src.core.ports.connectors import BaseTimesheetProvider


def default_timesheet_service(db: Any) -> BaseTimesheetProvider:
    """Собрать провайдера табеля по умолчанию (AADHk поверх переданной БД)."""
    from src.connectors.aadhk.parser import AadhkIngestionService
    from src.connectors.aadhk.provider import AadhkTimesheetProvider

    return AadhkTimesheetProvider(AadhkIngestionService(db))
