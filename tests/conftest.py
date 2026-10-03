"""Общие фикстуры каркаса: вторая синтетическая персона (FND-03) и персона по умолчанию (PER-08).

Файл ничего не трогает в приложении и базе данных.
"""

import copy
import os

import pytest

from src.persona.loader import PERSONA_CONFIG_ENV, load_persona

from .synthetic_persona import SYNTHETIC_PERSONA


@pytest.fixture
def synthetic_persona() -> dict:
    """Независимая глубокая копия словаря синтетической персоны."""
    return copy.deepcopy(SYNTHETIC_PERSONA)


@pytest.fixture(scope="session")
def default_persona_config() -> dict:
    """Поля персоны по умолчанию: model_dump(mode="json") персоны из config/persona.yaml.

    Данные профиля владельца берутся отсюда, а не копируются в тесты (PER-08, D-16).
    Переменная PERSONA_CONFIG_PATH на время загрузки снимается: нужна именно персона по умолчанию.
    """
    saved = os.environ.pop(PERSONA_CONFIG_ENV, None)
    try:
        return load_persona().model_dump(mode="json")
    finally:
        if saved is not None:
            os.environ[PERSONA_CONFIG_ENV] = saved
