"""Общие фикстуры каркаса: вторая синтетическая персона (FND-03).

Файл ничего не трогает в приложении и базе данных.
"""

import copy

import pytest

from .synthetic_persona import SYNTHETIC_PERSONA


@pytest.fixture
def synthetic_persona() -> dict:
    """Независимая глубокая копия словаря синтетической персоны."""
    return copy.deepcopy(SYNTHETIC_PERSONA)
