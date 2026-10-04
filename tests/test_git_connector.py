"""Тесты SshGitProvider и BaseGitSourceProvider (GIT-01, GIT-02).

Проверяет:
1. Соответствие протоколу BaseGitSourceProvider и корутинность методов.
2. Безопасность контракта: отсутствие методов записи (push, commit, branch).
3. Чтение коммитов из локального git-репозитория и корректный парсинг.
4. Устойчивость к сбоям: невалидные пути, таймауты fetch, сетевые сбои (D-02).
"""

from __future__ import annotations

import asyncio
import inspect
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.connectors.git.provider import SshGitProvider
from src.core.domain.entities import (
    ConnectorRole,
    GitCommit,
    GitProgressReport,
    Persona,
    Workspace,
    WorkspaceClearance,
)
from src.core.ports.connectors import BaseGitSourceProvider
from src.persona.current import use_persona


def test_ssh_git_provider_conforms_to_protocol():
    """SshGitProvider реализует BaseGitSourceProvider."""
    provider = SshGitProvider()
    assert isinstance(provider, BaseGitSourceProvider)
    assert provider.connector_id == "ssh_git"
    assert provider.role == ConnectorRole.GIT_SOURCE
    assert provider.required_scopes == ("git.read",)


def test_ssh_git_provider_methods_are_coroutines():
    """Все публичные методы порта являются асинхронными."""
    provider = SshGitProvider()
    for method_name in ("health_check", "list_repositories", "fetch_remote", "get_commits_since"):
        method = getattr(provider, method_name, None)
        assert method is not None, f"Отсутствует метод {method_name}"
        assert inspect.iscoroutinefunction(method), f"{method_name} не является корутиной"


def test_ssh_git_provider_prohibits_write_operations():
    """Провайдер не должен содержать методов записи в git (GIT-01)."""
    forbidden_methods = (
        "push",
        "commit",
        "create_branch",
        "delete_branch",
        "tag",
        "merge",
        "rebase",
        "reset",
        "cherry_pick",
    )
    for method in forbidden_methods:
        assert not hasattr(SshGitProvider, method), f"Обнаружен запрещенный метод записи: {method}"


async def test_health_check():
    """health_check возвращает True при доступном git и False при отсутствующем."""
    provider = SshGitProvider()
    assert await provider.health_check() is True

    bad_provider = SshGitProvider(git_bin="/nonexistent/git/binary")
    assert await bad_provider.health_check() is False


def test_domain_entities_immutability():
    """GitCommit и GitProgressReport неизменяемы (frozen slots)."""
    now = datetime.now(timezone.utc)
    commit = GitCommit(
        hash="abc1234",
        author="Test Author",
        date=now,
        message="test commit",
        files_changed=2,
        insertions=10,
        deletions=3,
    )
    with pytest.raises(Exception):
        commit.hash = "def5678"  # type: ignore

    report = GitProgressReport(
        workspace_id="test_ws",
        notion_project_id="proj_1",
        period_start=now,
        period_end=now,
        commit_count=1,
        latest_commit_date=now,
        summary_text="OK",
        is_stagnant=False,
        clearance=WorkspaceClearance.INTERNAL,
    )
    with pytest.raises(Exception):
        report.commit_count = 5  # type: ignore


def test_parse_git_log_shortstat():
    """Парсинг вывода git log с разделителями и статистикой."""
    raw_output = (
        "COMMIT_RECORD\x1f1111111111111111111111111111111111111111\x1f"
        "Alice <alice@example.com>\x1f2026-03-20T10:00:00+00:00\x1f"
        "feat(core): first commit\n"
        " 3 files changed, 25 insertions(+), 5 deletions(-)\n"
        "COMMIT_RECORD\x1f2222222222222222222222222222222222222222\x1f"
        "Bob <bob@example.com>\x1f2026-03-21T12:00:00+00:00\x1f"
        "fix(api): simple patch without shortstat\n"
    )
    provider = SshGitProvider()
    commits = provider._parse_git_log(raw_output)

    assert len(commits) == 2
    assert commits[0].hash == "1111111111111111111111111111111111111111"
    assert commits[0].author == "Alice <alice@example.com>"
    assert commits[0].message == "feat(core): first commit"
    assert commits[0].files_changed == 3
    assert commits[0].insertions == 25
    assert commits[0].deletions == 5

    assert commits[1].hash == "2222222222222222222222222222222222222222"
    assert commits[1].author == "Bob <bob@example.com>"
    assert commits[1].message == "fix(api): simple patch without shortstat"
    assert commits[1].files_changed == 0
    assert commits[1].insertions == 0
    assert commits[1].deletions == 0


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Создает временный git-репозиторий с несколькими коммитами."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=repo, check=True)

    # Коммит 1
    (repo / "file1.txt").write_text("Hello\nWorld\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "feat: initial commit"], cwd=repo, check=True)

    # Коммит 2
    (repo / "file2.txt").write_text("Second file\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "feat: second commit"], cwd=repo, check=True)

    return repo


async def test_get_commits_since_real_repo(temp_git_repo: Path):
    """Чтение реальных коммитов из временного git-репозитория."""
    ws = Workspace(
        id="ws_temp",
        name="Temporary Repo",
        clearance=WorkspaceClearance.INTERNAL,
        path=str(temp_git_repo),
    )
    provider = SshGitProvider()
    commits = await provider.get_commits_since(ws, max_commits=10)

    assert len(commits) == 2
    assert commits[0].message == "feat: second commit"
    assert commits[1].message == "feat: initial commit"
    assert commits[0].author == "Tester"
    assert commits[0].files_changed >= 1


async def test_get_commits_since_nonexistent_dir(tmp_path: Path):
    """Чтение из несуществующего пути возвращает пустой список без падения."""
    ws = Workspace(
        id="ws_missing",
        name="Missing Repo",
        clearance=WorkspaceClearance.INTERNAL,
        path=str(tmp_path / "does_not_exist"),
    )
    provider = SshGitProvider()
    commits = await provider.get_commits_since(ws)
    assert commits == []


async def test_fetch_remote_no_remote_configured(temp_git_repo: Path):
    """Если remote и ssh_alias не заданы, fetch возвращает True без вызова git."""
    ws = Workspace(
        id="ws_no_remote",
        name="No Remote Repo",
        clearance=WorkspaceClearance.INTERNAL,
        path=str(temp_git_repo),
        remote=None,
        ssh_alias=None,
    )
    provider = SshGitProvider()
    result = await provider.fetch_remote(ws)
    assert result is True


async def test_fetch_remote_nonexistent_dir(tmp_path: Path):
    """Если каталог не существует или нет .git, fetch возвращает False."""
    ws = Workspace(
        id="ws_missing",
        name="Missing",
        clearance=WorkspaceClearance.INTERNAL,
        path=str(tmp_path / "missing"),
        ssh_alias="my_server",
    )
    provider = SshGitProvider()
    result = await provider.fetch_remote(ws)
    assert result is False


async def test_fetch_remote_timeout_handling(temp_git_repo: Path):
    """Таймаут fetch перехватывается, процесс не падает, возвращается False (D-02)."""
    ws = Workspace(
        id="ws_slow",
        name="Slow Remote",
        clearance=WorkspaceClearance.INTERNAL,
        path=str(temp_git_repo),
        ssh_alias="slow_host",
    )
    provider = SshGitProvider()

    mock_proc = AsyncMock()
    async def _slow_communicate():
        await asyncio.sleep(1.0)
        return b"", b""
    mock_proc.communicate = _slow_communicate

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await provider.fetch_remote(ws, timeout_sec=0.01)
        assert result is False


async def test_fetch_remote_failure_handling(temp_git_repo: Path):
    """Ошибка команды fetch возвращает False без исключений (D-02)."""
    ws = Workspace(
        id="ws_error",
        name="Error Remote",
        clearance=WorkspaceClearance.INTERNAL,
        path=str(temp_git_repo),
        ssh_alias="failing_host",
    )
    provider = SshGitProvider()

    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", b"Host key verification failed"))
    mock_proc.returncode = 255

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await provider.fetch_remote(ws)
        assert result is False


async def test_list_repositories_filtering(tmp_path: Path):
    """list_repositories фильтрует пространства по наличию .git или remote/ssh_alias."""
    repo_dir = tmp_path / "valid_repo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()

    ws_local = Workspace(
        id="ws_1",
        name="Local Git",
        clearance=WorkspaceClearance.INTERNAL,
        path=str(repo_dir),
    )
    ws_remote = Workspace(
        id="ws_2",
        name="Remote Git",
        clearance=WorkspaceClearance.RESTRICTED_NDA,
        path=str(tmp_path / "remote_only"),
        ssh_alias="remote_alias",
    )
    ws_plain = Workspace(
        id="ws_3",
        name="Plain Dir",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(tmp_path / "just_dir"),
    )

    dummy_persona = Persona(
        id="p1",
        name="Test Persona",
        workspaces=(ws_local, ws_remote, ws_plain),
    )

    provider = SshGitProvider()
    with use_persona(dummy_persona):
        repos = await provider.list_repositories()
        repo_ids = {r.id for r in repos}
        assert "ws_1" in repo_ids
        assert "ws_2" in repo_ids
        assert "ws_3" not in repo_ids
