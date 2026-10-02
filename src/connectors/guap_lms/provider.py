"""Адаптер личного кабинета к порту BaseLMSProvider.

Клиент личного кабинета синхронный, поэтому каждый вызов уходит в поток через
asyncio.to_thread. Аргументы пробрасываются как есть: значения по умолчанию
(семестр, описание задания) остаются только в конкретном клиенте.
Адаптер пока не подключён к боевым потокам: бот работает с клиентом напрямую
и сохраняет прежний HITL-диалог удаления.
"""

import asyncio
from datetime import datetime
from typing import Any

from src.core.domain.entities import AcademicSubmission, ConnectorRole
from src.core.ports.clients import LmsClientLike
from src.core.ports.connectors import BaseLMSProvider


def _parse_deadline(value: Any) -> datetime | None:
    """Разобрать срок вида «15.10.2026»; неразборчивое значение даёт None."""
    try:
        return datetime.strptime(str(value).strip(), "%d.%m.%Y") if value else None
    except (ValueError, TypeError):
        return None


class GuapLmsProvider:
    """Личный кабинет как реализация порта BaseLMSProvider."""

    connector_id = "lms_portal"
    required_scopes = ("lms.read", "lms.write")
    role = ConnectorRole.LMS
    REQUIRES_CONFIRMATION = BaseLMSProvider.REQUIRES_CONFIRMATION

    def __init__(self, client: LmsClientLike) -> None:
        self._client = client

    async def health_check(self) -> bool:
        """Готовность без сети: учётные данные заданы (is_authenticated не вызываем)."""
        return bool(self._client.is_configured)

    async def list_tasks(self, *args: Any, **kwargs: Any) -> list[AcademicSubmission]:
        rows = await asyncio.to_thread(self._client.list_tasks, *args, **kwargs)
        return [
            AcademicSubmission(
                submission_id=str(row["id"]),
                title=str(row.get("title", "")),
                deadline=_parse_deadline(row.get("deadline")),
                is_public=bool(row.get("is_public")),
            )
            for row in rows
        ]

    async def get_task_details(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._client.get_task_details, *args, **kwargs)

    async def create_task(
        self,
        name: str,
        subject_id: str | int,
        group_ids: list[str | int],
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._client.create_task, name, subject_id, group_ids, **kwargs
        )

    async def delete_task(self, *args: Any, **kwargs: Any) -> bool:
        return await asyncio.to_thread(self._client.delete_task, *args, **kwargs)

    async def set_task_visibility(self, *args: Any, **kwargs: Any) -> bool:
        return await asyncio.to_thread(self._client.set_task_visibility, *args, **kwargs)

    async def get_disciplines(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._client.get_disciplines, *args, **kwargs)

    async def submit_grade(self, submission_id: str, grade: Any) -> None:
        raise NotImplementedError(
            "Выставление оценок через личный кабинет не поддерживается: "
            "у клиента нет такой операции"
        )
