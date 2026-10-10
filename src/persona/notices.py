"""Предупреждение о приватности почты (PRIV-01, D-14, D-16).

Текст принадлежит данным персоны (`persona.privacy.email_ai_notice`); в коде только нейтральный
запасной текст без названий сервисов, организаций и имён. Модуль лист зависимостей (контракт
persona-is-leaf): только stdlib и src.persona.*. Только информирование: никакого согласия и
блокировки сбора (D-16).
"""

from __future__ import annotations

from src.persona.models import PersonaConfig

# Зарезервированный ключ флага «предупреждение показано» (используется показом при старте сборщика).
EMAIL_AI_NOTICE_FLAG_KEY = "notice:email_ai"

_FALLBACK_BASE = (
    "Содержимое писем обрабатывается внешними ИИ-сервисами{services}. "
    "Разработчик не несёт ответственности за утечку секретов и иной личной информации из писем. "
    "Не подключайте ящики, содержимое которых нельзя передавать третьим лицам."
)


def email_ai_notice(persona: PersonaConfig) -> str:
    """Текст предупреждения: из данных персоны, а при его отсутствии нейтральный запасной."""
    configured = persona.privacy.email_ai_notice
    if configured is not None:
        return configured
    services = persona.privacy.external_ai_services
    suffix = f" ({', '.join(services)} и др.)" if services else ""
    return _FALLBACK_BASE.format(services=suffix)
