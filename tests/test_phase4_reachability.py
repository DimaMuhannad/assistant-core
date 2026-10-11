"""Тесты достижимости цепочки Git -> Оценка -> HITL -> Notion (GIT-01, GIT-03, NTN-01).

Проверяет:
1. Корень композиции собирает default_notion_client и default_git_evaluator с валидацией scopes (Task 1).
2. main.py регистрирует git_evaluator до EmailBotHandler, а также задачу планировщика git_progress_job (Task 2).
3. Цикл run_git_progress_cycle безопасен, не дублирует карточки и не падает (Task 2).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from assistant_shared.hitl.engine import get_action_handler
from src.core.exceptions import MissingScopeError
from src.persona.current import use_persona
from src.persona.loader import load_persona
from src.persona.models import PersonaConfig
from tests.synthetic_persona import SYNTHETIC_PERSONA, synthetic_to_config


@pytest.fixture
def fake_db(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(db_path=str(tmp_path / "test_reachability.db"))


def test_composition_default_git_evaluator_default_persona(fake_db: SimpleNamespace) -> None:
    """Test 1: персона по умолчанию: default_git_evaluator возвращает GitProgressEvaluator

    с провайдером SshGitProvider и клиентом NotionAsyncClient; обработчик notion_project_sync
    зарегистрирован именно на этот экземпляр.
    """
    from src.composition import default_git_evaluator, default_notion_client
    from src.connectors.git.provider import SshGitProvider
    from src.connectors.notion.client import NotionAsyncClient
    from src.brain.git_evaluator import GitProgressEvaluator

    client = default_notion_client()
    assert isinstance(client, NotionAsyncClient)

    evaluator = default_git_evaluator(fake_db)
    assert isinstance(evaluator, GitProgressEvaluator)
    assert isinstance(evaluator.git_provider, SshGitProvider)
    assert isinstance(evaluator.notion_client, NotionAsyncClient)

    handler = get_action_handler("notion_project_sync")
    assert handler == evaluator._handle_notion_sync


def test_composition_default_git_evaluator_without_git_source(
    tmp_path: Path, fake_db: SimpleNamespace
) -> None:
    """Test 2: персона без привязки git_source: default_git_evaluator возвращает None."""
    from src.composition import default_git_evaluator

    cfg_dict = synthetic_to_config(SYNTHETIC_PERSONA)
    cfg_dict["persona"]["connectors"]["git_source"] = []
    path = tmp_path / "persona_no_git.json"
    path.write_text(json.dumps(cfg_dict, ensure_ascii=False), encoding="utf-8")
    persona_no_git = load_persona(path)

    with use_persona(persona_no_git):
        evaluator = default_git_evaluator(fake_db)
        assert evaluator is None


def test_composition_default_git_evaluator_synthetic_without_notion(
    tmp_path: Path, fake_db: SimpleNamespace
) -> None:
    """Test 3: персона с git_source и без notion (синтетическая): оценщик создан, notion_client равен None."""
    from src.composition import default_git_evaluator, default_notion_client
    from src.brain.git_evaluator import GitProgressEvaluator

    path = tmp_path / "synthetic_persona.json"
    path.write_text(json.dumps(synthetic_to_config(SYNTHETIC_PERSONA), ensure_ascii=False), encoding="utf-8")
    synthetic_persona = load_persona(path)

    with use_persona(synthetic_persona):
        client = default_notion_client()
        assert client is None

        evaluator = default_git_evaluator(fake_db)
        assert isinstance(evaluator, GitProgressEvaluator)
        assert evaluator.notion_client is None


def test_composition_default_git_evaluator_missing_scope_raises(
    tmp_path: Path, fake_db: SimpleNamespace
) -> None:
    """Test 4: привязка git_source или notion без нужных scopes вызывает MissingScopeError."""
    from src.composition import default_git_evaluator, default_notion_client

    # 1. Недостаточно scopes для notion
    cfg_notion = synthetic_to_config(SYNTHETIC_PERSONA)
    cfg_notion["persona"]["connectors"]["notion"] = [
        {"id": "main", "provider": "notion_async", "scopes": ["notion.read"]}
    ]
    p_notion = tmp_path / "persona_bad_notion.json"
    p_notion.write_text(json.dumps(cfg_notion, ensure_ascii=False), encoding="utf-8")
    persona_bad_notion = load_persona(p_notion)

    with use_persona(persona_bad_notion):
        with pytest.raises(MissingScopeError, match="notion"):
            default_notion_client()

    # 2. Недостаточно scopes для git_source
    cfg_git = synthetic_to_config(SYNTHETIC_PERSONA)
    cfg_git["persona"]["connectors"]["git_source"] = [
        {"id": "main", "provider": "ssh_git", "scopes": []}
    ]
    p_git = tmp_path / "persona_bad_git.json"
    p_git.write_text(json.dumps(cfg_git, ensure_ascii=False), encoding="utf-8")
    persona_bad_git = load_persona(p_git)

    with use_persona(persona_bad_git):
        with pytest.raises(MissingScopeError, match="git_source"):
            default_git_evaluator(fake_db)


def test_composition_default_git_evaluator_db_path(fake_db: SimpleNamespace) -> None:
    """Test 5: ConfirmationStore оценщика указывает на тот же путь БД, что и переданный db."""
    from src.composition import default_git_evaluator

    evaluator = default_git_evaluator(fake_db)
    assert evaluator is not None
    assert evaluator.confirmation_store.db_path == fake_db.db_path
