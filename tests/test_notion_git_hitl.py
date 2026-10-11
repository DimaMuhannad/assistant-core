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
def mock_workspaces(tmp_path: Path) -> tuple[Workspace, Workspace]:
    pub_path = tmp_path / "lab_public"
    pub_path.mkdir()
    (pub_path / ".git").mkdir()

    nda_path = tmp_path / "tydex_nda"
    nda_path.mkdir()
    (nda_path / ".git").mkdir()

    ws_public = Workspace(
        id="ws_lab_public",
        name="GUAP Physics Lab",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(pub_path),
        remote="git@github.com:guap/lab.git",
        notion_project="11111111111111111111111111111111",
    )
    ws_nda = Workspace(
        id="ws_tydex_nda",
        name="Tydex THz Device",
        clearance=WorkspaceClearance.RESTRICTED_NDA,
        path=str(nda_path),
        remote="git@secret:tydex/device.git",
        ssh_alias="tydex-vps",
        notion_project="22222222222222222222222222222222",
    )
    return ws_public, ws_nda


@pytest.fixture
def mock_git_provider(mock_workspaces: tuple[Workspace, Workspace]):
    ws_public, ws_nda = mock_workspaces
    now = datetime.now(timezone.utc)

    provider = AsyncMock()
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
    client.is_configured = True
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
    """Допущенный публичный репозиторий порождает PendingConfirmation, а NDA исключается (D-07, D-12)."""
    ws_public, ws_nda = mock_workspaces
    dummy_persona = Persona(id="p_owner", name="Owner", workspaces=(ws_public, ws_nda))

    with use_persona(dummy_persona):
        evaluator = GitProgressEvaluator(
            git_provider=mock_git_provider,
            notion_client=mock_notion_client,
            confirmation_store=hitl_store,
            persona=dummy_persona,
            default_activity_db_id="33333333333333333333333333333333",
        )

        run = await evaluator.evaluate()
        # В допущенных только публичный проект
        assert len(run.entries) == 1
        assert run.nda_excluded is True

        entry_pub = run.entries[0]
        assert entry_pub.workspace.id == ws_public.id
        assert entry_pub.notion_ready is True

        proposal = await evaluator.propose_card(entry_pub, run.date_iso)
        conf_pub = proposal.confirmation

        assert conf_pub.action_type == "notion_project_sync"
        assert conf_pub.status == ConfirmationStatus.PENDING
        assert conf_pub.channel == ConfirmationChannel.TELEGRAM
        assert conf_pub.payload["commit_count"] == 1
        assert conf_pub.payload["status"] == "Активно"
        assert "lab experiment simulator" in conf_pub.payload["summary"]


def test_telegram_card_formatting(mock_notion_client, hitl_store: ConfirmationStore):
    """Интерактивная карточка Telegram содержит статус и сводку без лишней разметки."""
    evaluator = GitProgressEvaluator(
        git_provider=AsyncMock(),
        notion_client=mock_notion_client,
        confirmation_store=hitl_store,
        default_activity_db_id="33333333333333333333333333333333",
    )
    conf = AsyncMock(
        payload={
            "workspace_id": "ws_lab",
            "workspace_name": "GUAP Lab",
            "status": "Активно",
            "commit_count": 3,
            "date_iso": "2026-10-11",
            "summary": "Успешно завершен этап калибровки.",
        }
    )
    text = evaluator.format_card_text(conf)

    assert "Публикация в Notion: GUAP Lab" in text
    assert "⚡ Активно" in text
    assert "Коммитов: 3 коммита" in text
    assert "Успешно завершен этап калибровки." in text


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
            default_activity_db_id="33333333333333333333333333333333",
        )

        run = await evaluator.evaluate()
        proposal = await evaluator.propose_card(run.entries[0], run.date_iso)
        conf_pub = proposal.confirmation

        # До подтверждения вызовов Notion не было (NTN-02)
        assert mock_notion_client.log_project_activity.call_count == 0

        # Выполняем подтверждение действия
        res = await confirm_pending_action(conf_pub.id, hitl_store, user_id="telegram_user_1")
        assert res["success"] is True
        assert res["page_id"] == "page-notion-created-123"

        # Notion был вызван ровно 1 раз
        assert mock_notion_client.log_project_activity.call_count == 1
        call_kwargs = mock_notion_client.log_project_activity.call_args.kwargs
        assert call_kwargs["project_page_id"] == "11111111111111111111111111111111"
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
            default_activity_db_id="33333333333333333333333333333333",
        )

        run = await evaluator.evaluate()
        proposal = await evaluator.propose_card(run.entries[0], run.date_iso)
        conf_pub = proposal.confirmation

        # Отклоняем действие
        rejected_conf = await reject_pending_action(conf_pub.id, hitl_store, user_id="telegram_user_1")
        assert rejected_conf is not None
        assert rejected_conf.status == ConfirmationStatus.REJECTED

        # Notion НЕ вызывался
        assert mock_notion_client.log_project_activity.call_count == 0


@pytest.mark.asyncio
async def test_stagnant_project_detection(
    hitl_store: ConfirmationStore,
    mock_notion_client,
    tmp_path: Path,
):
    """Проект без коммитов или с коммитами старше 7 дней помечается как 'Застой'."""
    stagnant_dir = tmp_path / "stagnant"
    stagnant_dir.mkdir()
    (stagnant_dir / ".git").mkdir()

    ws_stagnant = Workspace(
        id="ws_stagnant",
        name="Stagnant Project",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(stagnant_dir),
        remote="git@github.com:test/stagnant.git",
        notion_project="44444444444444444444444444444444",
    )
    old_date = datetime.now(timezone.utc) - timedelta(days=14)

    mock_git = AsyncMock()
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
            default_activity_db_id="33333333333333333333333333333333",
        )

        run = await evaluator.evaluate()
        assert len(run.entries) == 1
        entry = run.entries[0]
        assert entry.report is not None
        assert entry.report.is_stagnant is True

        proposal = await evaluator.propose_card(entry, run.date_iso)
        assert proposal.confirmation.payload["status"] == "Застой"


# ---------------------------------------------------------------------------
# План 04-07 Task 1: Идемпотентность карточек, propose_cards, сигнатура запуска
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_propose_card_idempotent_for_same_workspace_and_date(
    hitl_store: ConfirmationStore,
    mock_git_provider,
    mock_notion_client,
    mock_workspaces: tuple[Workspace, Workspace],
) -> None:
    """Повторный вызов propose_card для того же пространства и даты возвращает created=False и ту же карточку."""
    ws_public, _ = mock_workspaces
    persona = Persona(id="p_owner", name="Owner", workspaces=(ws_public,))
    evaluator = GitProgressEvaluator(
        git_provider=mock_git_provider,
        notion_client=mock_notion_client,
        confirmation_store=hitl_store,
        persona=persona,
        default_activity_db_id="33333333333333333333333333333333",
    )
    run = await evaluator.evaluate()
    entry = run.entries[0]

    prop1 = await evaluator.propose_card(entry, run.date_iso)
    assert prop1.created is True

    prop2 = await evaluator.propose_card(entry, run.date_iso)
    assert prop2.created is False
    assert prop2.confirmation.id == prop1.confirmation.id

    # В хранилище создана ровно 1 запись
    found = await hitl_store.find_confirmations(
        action_type="notion_project_sync",
        target_id=f"{ws_public.id}|{run.date_iso}",
    )
    assert len(found) == 1


@pytest.mark.asyncio
async def test_propose_card_rejected_same_day_not_recreated(
    hitl_store: ConfirmationStore,
    mock_git_provider,
    mock_notion_client,
    mock_workspaces: tuple[Workspace, Workspace],
) -> None:
    """После отклонения (REJECTED) в тот же день новая карточка не создается."""
    ws_public, _ = mock_workspaces
    persona = Persona(id="p_owner", name="Owner", workspaces=(ws_public,))
    evaluator = GitProgressEvaluator(
        git_provider=mock_git_provider,
        notion_client=mock_notion_client,
        confirmation_store=hitl_store,
        persona=persona,
        default_activity_db_id="33333333333333333333333333333333",
    )
    run = await evaluator.evaluate()
    entry = run.entries[0]

    prop1 = await evaluator.propose_card(entry, run.date_iso)
    await reject_pending_action(prop1.confirmation.id, hitl_store)

    prop2 = await evaluator.propose_card(entry, run.date_iso)
    assert prop2.created is False
    assert prop2.confirmation.id == prop1.confirmation.id
    assert prop2.confirmation.status == ConfirmationStatus.REJECTED


@pytest.mark.asyncio
async def test_propose_card_expired_allows_new(
    hitl_store: ConfirmationStore,
    mock_git_provider,
    mock_notion_client,
    mock_workspaces: tuple[Workspace, Workspace],
) -> None:
    """Истекшая карточка (EXPIRED) не блокирует создание новой карточки."""
    ws_public, _ = mock_workspaces
    persona = Persona(id="p_owner", name="Owner", workspaces=(ws_public,))
    evaluator = GitProgressEvaluator(
        git_provider=mock_git_provider,
        notion_client=mock_notion_client,
        confirmation_store=hitl_store,
        persona=persona,
        default_activity_db_id="33333333333333333333333333333333",
    )
    run = await evaluator.evaluate()
    entry = run.entries[0]

    # Создаем с отрицательным ttl (уже истекла)
    prop1 = await evaluator.propose_card(entry, run.date_iso, ttl_minutes=-10)
    await hitl_store.cleanup_expired()

    prop2 = await evaluator.propose_card(entry, run.date_iso)
    assert prop2.created is True
    assert prop2.confirmation.id != prop1.confirmation.id


@pytest.mark.asyncio
async def test_concurrent_propose_creates_single_card(
    hitl_store: ConfirmationStore,
    mock_git_provider,
    mock_notion_client,
    mock_workspaces: tuple[Workspace, Workspace],
) -> None:
    """Параллельные вызовы propose_card защищены замком и создают ровно одну запись."""
    import asyncio

    ws_public, _ = mock_workspaces
    persona = Persona(id="p_owner", name="Owner", workspaces=(ws_public,))
    evaluator = GitProgressEvaluator(
        git_provider=mock_git_provider,
        notion_client=mock_notion_client,
        confirmation_store=hitl_store,
        persona=persona,
        default_activity_db_id="33333333333333333333333333333333",
    )
    run = await evaluator.evaluate()
    entry = run.entries[0]

    proposals = await asyncio.gather(*[evaluator.propose_card(entry, run.date_iso) for _ in range(5)])

    created_flags = [p.created for p in proposals]
    assert created_flags.count(True) == 1
    assert created_flags.count(False) == 4

    conf_ids = {p.confirmation.id for p in proposals}
    assert len(conf_ids) == 1


@pytest.mark.asyncio
async def test_propose_cards_only_for_ready_entries(
    hitl_store: ConfirmationStore,
    mock_notion_client,
    tmp_path: Path,
) -> None:
    """propose_cards создает карточки только для готовых записей (notion_ready=True, report!=None)."""
    from src.brain.git_evaluator import EvaluationRun, GitStatus, WorkspaceEvaluation
    from src.core.domain.entities import GitProgressReport

    ws_ready = Workspace(
        id="ws_ready",
        name="Ready WS",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(tmp_path),
        remote="git@github.com:test/ready.git",
        notion_project="11111111111111111111111111111111",
    )
    ws_no_remote = Workspace(
        id="ws_no_rem",
        name="No Remote",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(tmp_path),
    )
    ws_not_notion = Workspace(
        id="ws_not_notion",
        name="No Notion WS",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(tmp_path),
        remote="git@github.com:test/no_notion.git",
    )

    report_ready = GitProgressReport(
        workspace_id=ws_ready.id,
        notion_project_id=ws_ready.notion_project,
        period_start=datetime.now(timezone.utc),
        period_end=datetime.now(timezone.utc),
        commit_count=1,
        latest_commit_date=datetime.now(timezone.utc),
        summary_text="Сводка",
        is_stagnant=False,
        clearance=WorkspaceClearance.PUBLIC,
    )
    report_not_notion = GitProgressReport(
        workspace_id=ws_not_notion.id,
        notion_project_id=None,
        period_start=datetime.now(timezone.utc),
        period_end=datetime.now(timezone.utc),
        commit_count=1,
        latest_commit_date=datetime.now(timezone.utc),
        summary_text="Сводка",
        is_stagnant=False,
        clearance=WorkspaceClearance.PUBLIC,
    )

    entry1 = WorkspaceEvaluation(
        workspace=ws_ready,
        status=GitStatus.OK,
        status_text="OK",
        report=report_ready,
        notion_ready=True,
        notion_note="",
    )
    entry2 = WorkspaceEvaluation(
        workspace=ws_no_remote,
        status=GitStatus.NO_REMOTE,
        status_text="пропущено: нет remote",
        report=None,
        notion_ready=False,
        notion_note="Notion не настроен",
    )
    entry3 = WorkspaceEvaluation(
        workspace=ws_not_notion,
        status=GitStatus.OK,
        status_text="OK",
        report=report_not_notion,
        notion_ready=False,
        notion_note="Notion не настроен",
    )

    run = EvaluationRun(entries=(entry1, entry2, entry3), nda_excluded=False, date_iso="2026-10-11")

    evaluator = GitProgressEvaluator(
        git_provider=AsyncMock(),
        notion_client=mock_notion_client,
        confirmation_store=hitl_store,
        default_activity_db_id="33333333333333333333333333333333",
    )

    proposals = await evaluator.propose_cards(run)
    assert len(proposals) == 1
    assert proposals[0].confirmation.payload["workspace_id"] == "ws_ready"


def test_register_run_signature_changes_only_on_status_change(hitl_store: ConfirmationStore) -> None:
    """register_run_signature сообщает об изменениях только при изменении статусов или NDA."""
    from src.brain.git_evaluator import EvaluationRun, GitStatus, WorkspaceEvaluation
    from src.core.domain.entities import GitProgressReport

    ws1 = Workspace(id="ws1", name="WS1", clearance=WorkspaceClearance.PUBLIC, path="/tmp")
    ws2 = Workspace(id="ws2", name="WS2", clearance=WorkspaceClearance.PUBLIC, path="/tmp")

    rep1 = GitProgressReport(
        workspace_id=ws1.id,
        notion_project_id="11111111111111111111111111111111",
        period_start=datetime.now(timezone.utc),
        period_end=datetime.now(timezone.utc),
        commit_count=1,
        latest_commit_date=datetime.now(timezone.utc),
        summary_text="S1",
        is_stagnant=False,
        clearance=WorkspaceClearance.PUBLIC,
    )
    e1 = WorkspaceEvaluation(workspace=ws1, status=GitStatus.OK, status_text="OK", report=rep1, notion_ready=True, notion_note="")
    e2 = WorkspaceEvaluation(workspace=ws2, status=GitStatus.FETCH_FAILED, status_text="сбой SSH", report=None, notion_ready=False, notion_note="")

    run1 = EvaluationRun(entries=(e1, e2), nda_excluded=False, date_iso="2026-10-11")
    evaluator = GitProgressEvaluator(git_provider=AsyncMock(), notion_client=None, confirmation_store=hitl_store)

    assert evaluator.register_run_signature(run1) is True
    assert evaluator.register_run_signature(run1) is False

    # Изменяем статус второго пространства
    e2_changed = WorkspaceEvaluation(workspace=ws2, status=GitStatus.OK, status_text="OK", report=rep1, notion_ready=False, notion_note="")
    run2 = EvaluationRun(entries=(e1, e2_changed), nda_excluded=False, date_iso="2026-10-11")
    assert evaluator.register_run_signature(run2) is True
    assert evaluator.register_run_signature(run2) is False


def test_background_summary_lists_only_entries_without_cards(hitl_store: ConfirmationStore) -> None:
    """format_background_summary формирует текст только для записей без карточек и NDA."""
    from src.brain.git_evaluator import EvaluationRun, GitStatus, WorkspaceEvaluation
    from src.core.domain.entities import GitProgressReport

    ws1 = Workspace(id="ws1", name="ReadyWS", clearance=WorkspaceClearance.PUBLIC, path="/tmp")
    ws2 = Workspace(id="ws2", name="FailWS", clearance=WorkspaceClearance.PUBLIC, path="/tmp")
    ws3 = Workspace(id="ws3", name="NoNotionWS", clearance=WorkspaceClearance.PUBLIC, path="/tmp")

    rep1 = GitProgressReport(
        workspace_id=ws1.id,
        notion_project_id="11111111111111111111111111111111",
        period_start=datetime.now(timezone.utc),
        period_end=datetime.now(timezone.utc),
        commit_count=1,
        latest_commit_date=datetime.now(timezone.utc),
        summary_text="S1",
        is_stagnant=False,
        clearance=WorkspaceClearance.PUBLIC,
    )
    rep3 = GitProgressReport(
        workspace_id=ws3.id,
        notion_project_id=None,
        period_start=datetime.now(timezone.utc),
        period_end=datetime.now(timezone.utc),
        commit_count=1,
        latest_commit_date=datetime.now(timezone.utc),
        summary_text="Зафиксирован 1 коммит.",
        is_stagnant=False,
        clearance=WorkspaceClearance.PUBLIC,
    )

    evaluator = GitProgressEvaluator(git_provider=AsyncMock(), notion_client=None, confirmation_store=hitl_store)

    # 1. Только готовые записи и без NDA -> None
    e1 = WorkspaceEvaluation(workspace=ws1, status=GitStatus.OK, status_text="OK", report=rep1, notion_ready=True, notion_note="")
    run_all_ready = EvaluationRun(entries=(e1,), nda_excluded=False, date_iso="2026-10-11")
    assert evaluator.format_background_summary(run_all_ready) is None

    # 2. Есть сбой SSH, нет Notion и есть NDA -> формирует сводку
    e2 = WorkspaceEvaluation(workspace=ws2, status=GitStatus.FETCH_FAILED, status_text="сбой SSH", report=None, notion_ready=False, notion_note="")
    e3 = WorkspaceEvaluation(workspace=ws3, status=GitStatus.OK, status_text="Зафиксирован 1 коммит.", report=rep3, notion_ready=False, notion_note="Notion не настроен")
    run_mixed = EvaluationRun(entries=(e1, e2, e3), nda_excluded=True, date_iso="2026-10-11")

    text = evaluator.format_background_summary(run_mixed)
    assert text is not None
    assert "FailWS: сбой SSH" in text
    assert "NoNotionWS: ⚡ Зафиксирован 1 коммит. [Notion не настроен]" in text
    assert "ReadyWS" not in text  # готовое к карточке не попадает в фон
    assert "🔒 NDA: исключено из оценки" in text

