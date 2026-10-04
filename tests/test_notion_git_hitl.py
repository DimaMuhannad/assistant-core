"""Интеграционные тесты шлюза HITL и отправки отчетов Git в Notion (NTN-01, NTN-02).

Проверяет:
1. Создание индивидуальных запросов PendingConfirmation для каждого репозитория (D-07).
2. Безопасность: отправка в Notion происходит ИСКЛЮЧИТЕЛЬНО после явного подтверждения владельца.
3. Отклонение (rejection): при отклонении запроса Notion не вызывается.
4. Идемпотентность: защита от повторного выполнения (T-07-04).
5. Корректное форматирование интерактивных карточек Telegram.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from assistant_shared.db.migrator import run_migrations
from assistant_shared.hitl import (
    ConfirmationChannel,
    ConfirmationStatus,
    ConfirmationStore,
    confirm_pending_action,
    reject_pending_action,
    resume_action,
)
from src.brain.git_evaluator import GitProgressEvaluator
from src.core.domain.entities import (
    GitCommit,
    Persona,
    Workspace,
    WorkspaceClearance,
)
from src.persona.current import use_persona


@pytest.fixture
def hitl_store(tmp_path: Path) -> ConfirmationStore:
    db_file = str(tmp_path / "test_hitl.db")
    run_migrations(db_file)
    return ConfirmationStore(db_file)


@pytest.fixture
def mock_workspaces() -> tuple[Workspace, Workspace]:
    ws_public = Workspace(
        id="ws_lab_public",
        name="GUAP Physics Lab",
        clearance=WorkspaceClearance.PUBLIC,
        path="/opt/guap/lab",
        notion_project="notion-proj-lab",
    )
    ws_nda = Workspace(
        id="ws_tydex_nda",
        name="Tydex THz Device",
        clearance=WorkspaceClearance.RESTRICTED_NDA,
        path="/opt/tydex/device",
        ssh_alias="tydex-vps",
        notion_project="notion-proj-tydex",
    )
    return ws_public, ws_nda


@pytest.fixture
def mock_git_provider(mock_workspaces: tuple[Workspace, Workspace]):
    ws_public, ws_nda = mock_workspaces
    now = datetime.now(timezone.utc)

    provider = AsyncMock()
    provider.list_repositories.return_value = [ws_public, ws_nda]
    provider.fetch_remote.return_value = True

    async def _get_commits(ws, since=None, max_commits=100):
        if ws.id == ws_public.id:
            return [
                GitCommit(
                    hash="1111111111111111111111111111111111111111",
                    author="Alice",
                    date=now - timedelta(hours=2),
                    message="feat: lab experiment simulator",
                    files_changed=2,
                    insertions=20,
                    deletions=2,
                )
            ]
        elif ws.id == ws_nda.id:
            return [
                GitCommit(
                    hash="2222222222222222222222222222222222222222",
                    author="Bob",
                    date=now - timedelta(hours=5),
                    message="feat: secret THz laser proprietary algorithm",
                    files_changed=5,
                    insertions=100,
                    deletions=10,
                )
            ]
        return []

    provider.get_commits_since = _get_commits
    return provider


@pytest.fixture
def mock_notion_client():
    client = AsyncMock()
    client.log_project_activity = AsyncMock(
        return_value={"id": "page-notion-created-123", "object": "page"}
    )
    return client


@pytest.mark.asyncio
async def test_git_evaluator_creates_individual_pending_confirmations(
    hitl_store: ConfirmationStore,
    mock_git_provider,
    mock_notion_client,
    mock_workspaces: tuple[Workspace, Workspace],
):
    """Каждый репозиторий порождает отдельный PendingConfirmation (D-07)."""
    ws_public, ws_nda = mock_workspaces
    dummy_persona = Persona(id="p_owner", name="Owner", workspaces=(ws_public, ws_nda))

    with use_persona(dummy_persona):
        evaluator = GitProgressEvaluator(
            git_provider=mock_git_provider,
            notion_client=mock_notion_client,
            confirmation_store=hitl_store,
            persona=dummy_persona,
        )

        confirmations = await evaluator.propose_notion_updates()
        assert len(confirmations) == 2

        # 1. Проверка публичного проекта
        conf_pub = next(c for c in confirmations if c.target_id == ws_public.id)
        assert conf_pub.action_type == "notion_project_sync"
        assert conf_pub.status == ConfirmationStatus.PENDING
        assert conf_pub.channel == ConfirmationChannel.TELEGRAM
        assert conf_pub.payload["commit_count"] == 1
        assert conf_pub.payload["status"] == "Активно"
        assert "lab experiment simulator" in conf_pub.payload["summary"]

        # 2. Проверка NDA проекта (Air-Gap)
        conf_nda = next(c for c in confirmations if c.target_id == ws_nda.id)
        assert conf_nda.action_type == "notion_project_sync"
        assert conf_nda.status == ConfirmationStatus.PENDING
        assert conf_nda.payload["commit_count"] == 1
        assert "secret THz laser proprietary algorithm" not in conf_nda.payload["summary"]
        assert "Air-Gap (NDA)" in conf_nda.payload["summary"]
        assert "commits" not in conf_nda.payload


def test_telegram_card_formatting():
    """Интерактивная карточка Telegram содержит эмодзи, статус и callback-кнопки."""
    now = datetime.now(timezone.utc)
    report = GitProgressEvaluator.format_telegram_card(
        report=AsyncMock(
            workspace_id="ws_lab",
            commit_count=3,
            is_stagnant=False,
            latest_commit_date=now,
            clearance=WorkspaceClearance.PUBLIC,
            summary_text="Успешно завершен этап калибровки.",
        ),
        confirmation_id="test-conf-uuid-456",
    )
    text, keyboard = report

    assert "🚀 **Ход разработки: ws_lab**" in text
    assert "⚡ Активно" in text
    assert "• Коммитов: 3" in text
    assert "Успешно завершен этап калибровки." in text

    # Проверка инлайн-кнопок
    assert len(keyboard) == 1
    assert keyboard[0][0]["text"] == "✅ Опубликовать в Notion"
    assert keyboard[0][0]["callback_data"] == "hitl:confirm:test-conf-uuid-456"
    assert keyboard[0][1]["text"] == "❌ Отклонить"
    assert keyboard[0][1]["callback_data"] == "hitl:reject:test-conf-uuid-456"


@pytest.mark.asyncio
async def test_hitl_confirmation_posts_to_notion(
    hitl_store: ConfirmationStore,
    mock_git_provider,
    mock_notion_client,
    mock_workspaces: tuple[Workspace, Workspace],
):
    """Подтверждение действия через resume_action выполняет публикацию в Notion (NTN-02)."""
    ws_public, ws_nda = mock_workspaces
    dummy_persona = Persona(id="p_owner", name="Owner", workspaces=(ws_public, ws_nda))

    with use_persona(dummy_persona):
        evaluator = GitProgressEvaluator(
            git_provider=mock_git_provider,
            notion_client=mock_notion_client,
            confirmation_store=hitl_store,
            persona=dummy_persona,
        )

        confirmations = await evaluator.propose_notion_updates()
        conf_pub = next(c for c in confirmations if c.target_id == ws_public.id)

        # До подтверждения вызовов Notion не было (NTN-02)
        assert mock_notion_client.log_project_activity.call_count == 0

        # Выполняем подтверждение действия
        res = await confirm_pending_action(conf_pub.id, hitl_store, user_id="telegram_user_1")
        assert res["success"] is True
        assert res["page_id"] == "page-notion-created-123"

        # Notion был вызван ровно 1 раз
        assert mock_notion_client.log_project_activity.call_count == 1
        call_kwargs = mock_notion_client.log_project_activity.call_args.kwargs
        assert call_kwargs["project_page_id"] == "notion-proj-lab"
        assert call_kwargs["commit_count"] == 1
        assert call_kwargs["status"] == "Активно"

        # Статус в хранилище обновился на confirmed
        updated_conf = await hitl_store.get_confirmation(conf_pub.id)
        assert updated_conf is not None
        assert updated_conf.status == ConfirmationStatus.CONFIRMED

        # Идемпотентность: повторный вызов отклоняется с ошибкой и не дублирует отправку в Notion
        with pytest.raises(ValueError):
            await resume_action(conf_pub.id, hitl_store, confirmed_by="telegram_user_1")
        assert mock_notion_client.log_project_activity.call_count == 1


@pytest.mark.asyncio
async def test_hitl_rejection_does_not_post_to_notion(
    hitl_store: ConfirmationStore,
    mock_git_provider,
    mock_notion_client,
    mock_workspaces: tuple[Workspace, Workspace],
):
    """Отклонение действия не вызывает публикацию в Notion и переводит статус в REJECTED."""
    ws_public, ws_nda = mock_workspaces
    dummy_persona = Persona(id="p_owner", name="Owner", workspaces=(ws_public, ws_nda))

    with use_persona(dummy_persona):
        evaluator = GitProgressEvaluator(
            git_provider=mock_git_provider,
            notion_client=mock_notion_client,
            confirmation_store=hitl_store,
            persona=dummy_persona,
        )

        confirmations = await evaluator.propose_notion_updates()
        conf_nda = next(c for c in confirmations if c.target_id == ws_nda.id)

        # Отклоняем действие
        rejected_conf = await reject_pending_action(conf_nda.id, hitl_store, user_id="telegram_user_1")
        assert rejected_conf is not None
        assert rejected_conf.status == ConfirmationStatus.REJECTED

        # Notion НЕ вызывался
        assert mock_notion_client.log_project_activity.call_count == 0


@pytest.mark.asyncio
async def test_stagnant_project_detection(
    hitl_store: ConfirmationStore,
    mock_notion_client,
):
    """Проект без коммитов или с коммитами старше 7 дней помечается как 'Застой'."""
    ws_stagnant = Workspace(
        id="ws_stagnant",
        name="Stagnant Project",
        clearance=WorkspaceClearance.PUBLIC,
        path="/opt/stagnant",
        notion_project="notion-proj-old",
    )
    old_date = datetime.now(timezone.utc) - timedelta(days=14)

    mock_git = AsyncMock()
    mock_git.list_repositories.return_value = [ws_stagnant]
    mock_git.fetch_remote.return_value = True
    mock_git.get_commits_since.return_value = [
        GitCommit(
            hash="old1111111111111111111111111111111111111",
            author="Dev",
            date=old_date,
            message="chore: old commit two weeks ago",
        )
    ]

    dummy_persona = Persona(id="p_owner", name="Owner", workspaces=(ws_stagnant,))

    with use_persona(dummy_persona):
        evaluator = GitProgressEvaluator(
            git_provider=mock_git,
            notion_client=mock_notion_client,
            confirmation_store=hitl_store,
            persona=dummy_persona,
        )

        reports = await evaluator.evaluate_workspaces()
        assert len(reports) == 1
        assert reports[0].is_stagnant is True

        confirmations = await evaluator.propose_notion_updates(reports)
        assert len(confirmations) == 1
        assert confirmations[0].payload["status"] == "Застой"
