"""Протоколы существующих клиентов для внедрения зависимостей в use-cases.

Протоколы описывают клиенты ровно в той форме, в какой их вызывает бот, и
нужны только для аннотаций. Проверять isinstance по зависимостям в
конструкторах use-cases нельзя: объект MagicMock из тестов такую проверку
не проходит. Это не порты коннекторов: у клиентов нет connector_id и роли.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LmsClientLike(Protocol):
    """Клиент личного кабинета: все методы синхронные."""

    @property
    def is_configured(self) -> bool: ...

    def list_tasks(self, semester: int | str = ...) -> list[dict[str, Any]]: ...

    def get_task_details(self, task_id: int | str) -> dict[str, Any]: ...

    def create_task(
        self,
        name: str,
        subject_id: str | int,
        group_ids: list[str | int],
        **kwargs: Any,
    ) -> dict[str, Any]: ...

    def delete_task(self, task_id: int | str, semester_id: int | str = ...) -> bool: ...

    def set_task_visibility(
        self,
        task_id: int | str,
        is_public: bool,
        semester_id: int | str = ...,
    ) -> bool: ...

    def get_disciplines(self) -> list[dict[str, Any]]: ...


@runtime_checkable
class EmailSenderLike(Protocol):
    """Отправщик почты."""

    async def send_reply(
        self,
        to_email: str,
        subject: str,
        body: str,
        account_id: str = ...,
        in_reply_to: str | None = None,
        references: str | None = None,
        cc: list[str] | None = None,
    ) -> dict[str, Any]: ...


@runtime_checkable
class DriveClientLike(Protocol):
    """Клиент облачного диска с резервными копиями табеля."""

    @property
    def is_configured(self) -> bool: ...

    async def sync_aadhk_from_drive(self, db: Any) -> dict[str, Any]: ...
