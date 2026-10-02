"""EventBus: доставка доменного события подписчикам точного типа внутри процесса.

Только stdlib и src.core. Подписчики хранятся в словаре объекта, вызываются
последовательно в порядке подписки. Сбой подписчика журналируется (только имя
обработчика и тип события, без содержимого события) и не прерывает остальных;
отмена задачи (CancelledError) не перехватывается.
"""

import inspect
import logging
from collections.abc import Callable
from typing import Any

from src.core.domain.events import DomainEvent

logger = logging.getLogger(__name__)


class EventBus:
    """Шина событий: subscribe(тип, обработчик) и async publish(событие)."""

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[Callable[[DomainEvent], Any]]] = {}

    def subscribe(
        self, event_type: type[DomainEvent], handler: Callable[[DomainEvent], Any]
    ) -> None:
        """Подписать обработчик (обычная функция или корутинная) на точный тип события."""
        self._handlers.setdefault(event_type, []).append(handler)

    async def publish(self, event: DomainEvent) -> None:
        """Доставить событие подписчикам его точного типа; подклассы не учитываются."""
        for handler in tuple(self._handlers.get(type(event), ())):
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception(
                    "EventBus: подписчик %s упал на событии %s",
                    getattr(handler, "__qualname__", type(handler).__name__),
                    type(event).__name__,
                )
