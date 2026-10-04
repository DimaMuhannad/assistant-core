"""Корень композиции: единственное место (кроме src/main.py), знающее конкретные классы.

Фабрики импортируют адаптеры лениво, внутри функций: так патчи модулей-источников
в тестах (например, src.connectors.aadhk.parser.AadhkIngestionService)
продолжают работать, а use-cases не импортируют адаптеры на верхнем уровне.
Реализует Zero-Trust Scope Validation (D-09, D-10, D-11).
"""

from __future__ import annotations

from typing import Any

from src.core.ports.clients import DriveClientLike, EmailSenderLike, LmsClientLike
from src.core.ports.connectors import BaseScheduleProvider, BaseTimesheetProvider


def schedule_site_url() -> str:
    """Адрес сайта расписания: переменная окружения SCHEDULE_URL сильнее персоны (A1), иначе base_url привязки."""
    from src import config
    from src.core.exceptions import MissingScopeError
    from src.persona.bindings import binding, has_binding, schedule_source_settings

    if config.SCHEDULE_URL:
        return config.SCHEDULE_URL

    if not has_binding("schedule_source"):
        return ""

    bound = binding("schedule_source")
    req = set(BaseScheduleProvider.required_scopes)
    actual = set(bound.scopes)
    if not req.issubset(actual):
        raise MissingScopeError(f"Коннектор schedule_source требует scopes {req}, у персоны только {actual}")

    return schedule_source_settings().base_url


def default_timesheet_service(db: Any) -> BaseTimesheetProvider | None:
    """Собрать провайдера табеля по умолчанию (AADHk поверх переданной БД)."""
    from src.core.exceptions import MissingScopeError
    from src.persona.bindings import binding, has_binding

    if not has_binding("timesheet"):
        return None

    from src.connectors.aadhk.parser import AadhkIngestionService
    from src.connectors.aadhk.provider import AadhkTimesheetProvider

    bound = binding("timesheet")
    req = set(AadhkTimesheetProvider.required_scopes)
    actual = set(bound.scopes)
    if not req.issubset(actual):
        raise MissingScopeError(f"Коннектор timesheet требует scopes {req}, у персоны только {actual}")

    return AadhkTimesheetProvider(AadhkIngestionService(db))


def default_lms_client() -> LmsClientLike | None:
    """Собрать клиент личного кабинета по умолчанию."""
    from src.core.exceptions import MissingScopeError
    from src.persona.bindings import binding, has_binding

    if not has_binding("lms"):
        return None

    from src.connectors.guap_lms.client import GuapLmsClient

    bound = binding("lms")
    req = set(GuapLmsClient.required_scopes)
    actual = set(bound.scopes)
    if not req.issubset(actual):
        raise MissingScopeError(f"Коннектор lms требует scopes {req}, у персоны только {actual}")

    return GuapLmsClient()


def default_email_sender() -> EmailSenderLike:
    """Собрать отправщик почты по умолчанию."""
    from src.sender.email_sender import EmailSender

    return EmailSender()


def default_drive_client() -> DriveClientLike:
    """Собрать клиент Google Drive по умолчанию (новый экземпляр на каждый вызов)."""
    from src.connectors.gdrive.client import GoogleDriveClient

    return GoogleDriveClient()
