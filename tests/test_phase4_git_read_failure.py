"""Фаза 4, ревизия: сбой чтения git не равен «Застою»; последний коммит определяется по максимуму даты."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from assistant_shared.hitl import ConfirmationStore
from src.brain.git_evaluator import GitProgressEvaluator, GitStatus
from src.connectors.git.provider import SshGitProvider
from src.core.domain.entities import GitCommit, Workspace, WorkspaceClearance
from src.core.exceptions import GitReadError
from src.storage.db import Database
from tests.test_git_chain import StubGitProvider, _make_workspace


@pytest.fixture
async def store(tmp_path: Path) -> ConfirmationStore:
    db_path = str(tmp_path / "hitl.db")
    await Database(f"sqlite+aiosqlite:///{db_path}").init_db()
    return ConfirmationStore(db_path)


def _evaluator(provider, store, ws) -> GitProgressEvaluator:
    persona = SimpleNamespace(id="p_test", workspaces=[ws])
    return GitProgressEvaluator(
        git_provider=provider, notion_client=None, confirmation_store=store, persona=persona
    )


def _ws(tmp_path: Path) -> Workspace:
    ws_dir = tmp_path / "repo"
    (ws_dir / ".git").mkdir(parents=True)
    return Workspace(id="ws_r", name="R", clearance=WorkspaceClearance.INTERNAL, path=str(ws_dir))


async def test_provider_raises_on_git_log_nonzero_exit(tmp_path: Path):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(b"", b"fatal: bad object"))
    proc.returncode = 128
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with pytest.raises(GitReadError):
            await SshGitProvider().get_commits_since(_ws(tmp_path))


async def test_provider_raises_on_git_log_timeout(tmp_path: Path):
    proc = AsyncMock()
    proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
    proc.returncode = None
    provider = SshGitProvider()
    provider._terminate = AsyncMock()
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with pytest.raises(GitReadError):
            await provider.get_commits_since(_ws(tmp_path))


async def test_evaluator_reports_read_failure_not_stagnation(tmp_path: Path, store):
    ws = _make_workspace(tmp_path, "ws_read_fail")
    provider = StubGitProvider(commits=GitReadError("git log упал"))
    run = await _evaluator(provider, store, ws).evaluate()

    entry = run.entries[0]
    assert entry.status == GitStatus.READ_FAILED
    assert entry.report is None
    assert not entry.notion_ready
    assert "сбой" in entry.status_text
    assert "Застой" not in entry.status_text


async def test_latest_commit_date_is_max_not_first(tmp_path: Path, store):
    ws = _make_workspace(tmp_path, "ws_order")
    now = datetime.now(timezone.utc)
    old = GitCommit(hash="a" * 40, author="x", date=now - timedelta(days=30), message="old")
    new = GitCommit(hash="b" * 40, author="x", date=now - timedelta(days=1), message="new")
    provider = StubGitProvider(commits=[old, new])  # порядок не по убыванию даты
    run = await _evaluator(provider, store, ws).evaluate()

    report = run.entries[0].report
    assert report.latest_commit_date == new.date
    assert report.is_stagnant is False
