"""SshGitProvider: асинхронный провайдер Git-источников (GIT-01, GIT-02).

Только чтение: чтение локальных коммитов и неблокирующий fetch по SSH с таймаутом.
Любые операции записи (push, commit, branch) исключены на уровне контракта.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from src.core.domain.entities import ConnectorRole, GitCommit, Workspace
from src.core.exceptions import AirGapViolationError, GitReadError
from src.core.ports.connectors import BaseGitSourceProvider
from src.security.airgap import is_git_chain_eligible, git_chain_workspaces

logger = logging.getLogger(__name__)

_URL_CREDENTIALS_RE = re.compile(r"(://)[^/@\s]+@")


def _redact_credentials(text: str) -> str:
    """Скрыть user:token@ в URL из вывода git перед записью в лог."""
    return _URL_CREDENTIALS_RE.sub(r"\1***@", text)


_STAT_RE = re.compile(
    r"(\d+)\s+file[s]?\s+changed(?:,\s+(\d+)\s+insertion[s]?\(\+\))?(?:,\s+(\d+)\s+deletion[s]?\(-\))?"
)


class SshGitProvider(BaseGitSourceProvider):
    """Реализация порта BaseGitSourceProvider поверх системного git."""

    connector_id: str = "ssh_git"
    role: ClassVar[ConnectorRole] = ConnectorRole.GIT_SOURCE
    required_scopes: ClassVar[tuple[str, ...]] = ("git.read",)

    def __init__(self, git_bin: str | None = None) -> None:
        self.git_bin = git_bin or shutil.which("git") or "git"

    def _git_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes -o ConnectTimeout=10"
        return env

    async def _terminate(self, proc: asyncio.subprocess.Process) -> None:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        except Exception:
            pass
        try:
            await proc.wait()
        except Exception:
            pass

    async def health_check(self) -> bool:
        """Проверка наличия исполняемого файла git."""
        return bool(shutil.which(self.git_bin))

    async def list_repositories(self) -> list[Workspace]:
        """Возвращает список рабочих пространств с настроенным git-репозиторием."""
        try:
            from src.persona.current import current_persona

            persona = current_persona()
            split = git_chain_workspaces(persona)
            if split.unresolved:
                return []
            workspaces = split.eligible
        except Exception:
            return []

        repos: list[Workspace] = []
        for ws in workspaces:
            p = Path(ws.path)
            # Репозиторий считается таковым, если есть локальная папка .git либо указан remote/ssh_alias
            if (p / ".git").exists() or ws.remote or ws.ssh_alias:
                repos.append(ws)
        return repos

    async def fetch_remote(self, workspace: Workspace, timeout_sec: float = 30.0) -> bool:
        """Неблокирующий git fetch по SSH с таймаутом (D-01, D-02)."""
        if not is_git_chain_eligible(workspace):
            raise AirGapViolationError(f"Рабочее пространство {workspace.id} не допущено к цепочке git (Air-Gap)")

        p = Path(workspace.path)
        if not (p / ".git").exists():
            logger.warning("Каталог %s не является git-репозиторием, fetch пропущен", workspace.path)
            return False

        if not workspace.remote and not workspace.ssh_alias:
            logger.debug("Для %s не настроен remote/ssh_alias, fetch не требуется", workspace.id)
            return True

        cmd = [self.git_bin, "-C", str(p), "fetch", "--all", "--prune"]
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
                env=self._git_env(),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
            if proc.returncode == 0:
                logger.info("Успешный git fetch для %s", workspace.id)
                return True
            logger.warning(
                "git fetch для %s завершился с кодом %s: %s",
                workspace.id,
                proc.returncode,
                _redact_credentials(stderr.decode(errors="replace").strip()),
            )
            return False
        except asyncio.TimeoutError:
            logger.warning("Таймаут git fetch для %s (> %s с)", workspace.id, timeout_sec)
            if proc is not None:
                await self._terminate(proc)
            return False
        except Exception as e:
            logger.warning("Ошибка при вызове git fetch для %s: %s", workspace.id, e)
            return False

    async def get_commits_since(
        self,
        workspace: Workspace,
        since: datetime | None = None,
        max_commits: int = 100,
    ) -> list[GitCommit]:
        """Чтение истории коммитов репозитория начиная с указанной даты (D-01, D-03).

        Сбой чтения поднимает GitReadError: пустой список означает только отсутствие коммитов.
        """
        if not is_git_chain_eligible(workspace):
            raise AirGapViolationError(f"Рабочее пространство {workspace.id} не допущено к цепочке git (Air-Gap)")

        p = Path(workspace.path)
        if not (p / ".git").exists():
            logger.warning("Каталог %s не существует, коммиты не найдены", workspace.path)
            return []

        # Формат: %H (hash), %an (author name), %aI (author date ISO), %s (subject) с разделителем Unit Separator \x1f
        # Фильтр --since работает по дате коммитера, разбор берёт дату автора (%aI), расхождение допустимо;
        # при достижении max_commits счётчик ограничен сверху.
        # Флаги --branches и --remotes гарантируют включение коммитов из всех веток (в т.ч. remote-tracking).
        cmd = [
            self.git_bin,
            "-C",
            str(p),
            "log",
            "--branches",
            "--remotes",
            f"-n{max_commits}",
            "--format=format:COMMIT_RECORD%x1f%H%x1f%an%x1f%aI%x1f%s",
            "--shortstat",
        ]
        if since is not None:
            cmd.append(f"--since={since.isoformat()}")

        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
                env=self._git_env(),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
            if proc.returncode != 0:
                logger.warning(
                    "git log для %s завершился с кодом %s: %s",
                    workspace.id,
                    proc.returncode,
                    _redact_credentials(stderr.decode(errors="replace").strip()),
                )
                raise GitReadError(f"git log для {workspace.id} завершился с кодом {proc.returncode}")

            output = stdout.decode("utf-8", errors="replace")
            return self._parse_git_log(output)
        except GitReadError:
            raise
        except asyncio.TimeoutError:
            logger.warning("Таймаут git log для %s (> 15.0 с)", workspace.id)
            if proc is not None:
                await self._terminate(proc)
            raise GitReadError(f"Таймаут git log для {workspace.id}")
        except Exception as e:
            logger.warning("Ошибка чтения git log для %s: %s", workspace.id, e)
            raise GitReadError(f"Ошибка чтения git log для {workspace.id}") from e

    def _parse_git_log(self, text: str) -> list[GitCommit]:
        """Разбор вывода git log --shortstat."""
        commits: list[GitCommit] = []
        if not text.strip():
            return commits

        blocks = text.split("COMMIT_RECORD\x1f")
        for block in blocks:
            if not block.strip():
                continue
            lines = [l.strip() for l in block.splitlines() if l.strip()]
            if not lines:
                continue

            header_parts = lines[0].split("\x1f")
            if len(header_parts) < 4:
                continue

            commit_hash = header_parts[0]
            author = header_parts[1]
            date_str = header_parts[2]
            message = header_parts[3]

            try:
                commit_date = datetime.fromisoformat(date_str)
            except ValueError:
                # Подмена даты «сейчас» скрыла бы застой проекта; коммит без даты пропускаем.
                logger.warning("Коммит %s пропущен: нечитаемая дата", commit_hash[:12])
                continue

            files_changed = 0
            insertions = 0
            deletions = 0

            # Ищем shortstat в последующих строках блока
            for line in lines[1:]:
                m = _STAT_RE.search(line)
                if m:
                    files_changed = int(m.group(1)) if m.group(1) else 0
                    insertions = int(m.group(2)) if m.group(2) else 0
                    deletions = int(m.group(3)) if m.group(3) else 0
                    break

            commits.append(
                GitCommit(
                    hash=commit_hash,
                    author=author,
                    date=commit_date,
                    message=message,
                    files_changed=files_changed,
                    insertions=insertions,
                    deletions=deletions,
                )
            )

        return commits
