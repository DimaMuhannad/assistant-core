"""Текущая персона процесса (D-11): читается при вызове, подменяется в контексте.

Персона не читается при импорте (Pitfall 8): PERSONA_CONFIG_PATH и файл могут измениться
между импортом и первым обращением (тесты, смена конфигурации). Кэш ключуется путём файла.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from src.persona.loader import load_persona, resolve_persona_path
from src.persona.models import PersonaConfig

_override: ContextVar[PersonaConfig | None] = ContextVar("persona_override", default=None)
_cache: dict[Path, PersonaConfig] = {}


def current_persona() -> PersonaConfig:
    overridden = _override.get()
    if overridden is not None:
        return overridden
    path = resolve_persona_path()  # путь вычисляется при каждом вызове
    cached = _cache.get(path)
    if cached is None:
        cached = load_persona(path)
        _cache[path] = cached
    return cached


@contextmanager
def use_persona(persona: PersonaConfig) -> Iterator[PersonaConfig]:
    """Подменить текущую персону внутри блока (тесты, вторая персона)."""
    token = _override.set(persona)
    try:
        yield persona
    finally:
        _override.reset(token)


def reset_persona_cache() -> None:
    """Сбросить кэш файлов: следующий current_persona() перечитает persona.yaml."""
    _cache.clear()
