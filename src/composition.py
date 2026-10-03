"""Корень композиции: единственное место (кроме src/main.py), знающее конкретные классы.

Фабрики импортируют адаптеры лениво, внутри функций: так патчи модулей-источников
в тестах (например, src.connectors.aadhk.parser.AadhkIngestionService)
продолжают работать, а use-cases не импортируют адаптеры на верхнем уровне.
"""

from __future__ import annotations

from typing import Any

from src.core.ports.clients import DriveClientLike, EmailSenderLike, LmsClientLike
from src.core.ports.connectors import BaseTimesheetProvider


def schedule_site_url() -> str:
    """Адрес сайта расписания: переменная окружения SCHEDULE_URL сильнее персоны (A1), иначе base_url привязки."""
    from src import config
    from src.persona.bindings import schedule_source_settings

    return config.SCHEDULE_URL or schedule_source_settings().base_url


def default_timesheet_service(db: Any) -> BaseTimesheetProvider:
    """Собрать провайдера табеля по умолчанию (AADHk поверх переданной БД)."""
    from src.connectors.aadhk.parser import AadhkIngestionService
    from src.connectors.aadhk.provider import AadhkTimesheetProvider

    return AadhkTimesheetProvider(AadhkIngestionService(db))


def default_lms_client() -> LmsClientLike:
    """Собрать клиент личного кабинета по умолчанию."""
    from src.connectors.guap_lms.client import GuapLmsClient

    return GuapLmsClient()


def default_email_sender() -> EmailSenderLike:
    """Собрать отправщик почты по умолчанию."""
    from src.sender.email_sender import EmailSender

    return EmailSender()


def default_drive_client() -> DriveClientLike:
    """Собрать клиент Google Drive по умолчанию (новый экземпляр на каждый вызов)."""
    from src.connectors.gdrive.client import GoogleDriveClient

    return GoogleDriveClient()
