"""GitProgressEvaluator: сервисный оркестратор оценки Git-активности и синхронизации с Notion (NTN-01, NTN-02).

Реализует:
1. Строгий fail-closed шлюз допуска git_chain_workspaces (D-12, D-13, GIT-04).
2. Классификацию доступности репозиториев (D-05, GIT-02).
3. Опрос репозиториев через BaseGitSourceProvider (только чтение).
4. Оценку активности, расчет признака застоя (> 7 дней без коммитов) и сводку по-русски.
5. Формирование отложенных подтверждений PendingConfirmation (action_type='notion_project_sync').
6. Исполнение публикации в Notion через HITL-подтверждение владельца (D-10, NTN-02).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import logging
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

from assistant_shared.hitl import (
    ConfirmationChannel,
    ConfirmationStore,
    PendingConfirmation,
    register_action_handler,
)
from src import config
from src.core.domain.entities import (
    GitCommit,
    GitProgressReport,
    Workspace,
    WorkspaceClearance,
)
from src.core.ports.clients import NotionClientLike
from src.core.ports.connectors import BaseGitSourceProvider
from src.security.airgap import (
    git_chain_workspaces,
    sanitize_git_commits_for_llm,
)

logger = logging.getLogger(__name__)

NDA_EXCLUDED_LINE = "NDA: исключено из оценки"
NOTION_ACTION_TYPE = "notion_project_sync"
CARD_TTL_MINUTES = 1440
DEFAULT_STAGNATION_DAYS = 7

_NOTION_ID_HEX_RE = re.compile(r"^[0-9a-fA-F]{32}$")
_NOTION_ID_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class NotionSyncError(RuntimeError):
    """Ошибка при синхронизации записи активности с Notion."""


def is_valid_notion_id(value: Any) -> bool:
    """Проверка идентификатора Notion: 32 hex символа или UUID 8-4-4-4-12 (D-06)."""
    if not isinstance(value, str):
        return False
    val = value.strip()
    if not val:
        return False
    return bool(_NOTION_ID_HEX_RE.match(val) or _NOTION_ID_UUID_RE.match(val))


class GitStatus(StrEnum):
    """Статусы готовности рабочего пространства к оценке git."""

    OK = "ok"
    NO_REMOTE = "no_remote"
    NO_DIR = "no_dir"
    NOT_GIT = "not_git"
    FETCH_FAILED = "fetch_failed"


@dataclass(frozen=True, slots=True)
class WorkspaceEvaluation:
    """Результат оценки одного рабочего пространства."""

    workspace: Any
    status: GitStatus
    status_text: str
    report: GitProgressReport | None
    notion_ready: bool
    notion_note: str


@dataclass(frozen=True, slots=True)
class EvaluationRun:
    """Сводный результат цикла оценки рабочих пространств."""

    entries: tuple[WorkspaceEvaluation, ...]
    nda_excluded: bool
    date_iso: str


@dataclass(frozen=True, slots=True)
class CardProposal:
    """Результат создания запроса на подтверждение публикации в Notion."""

    confirmation: PendingConfirmation
    created: bool


def _format_commit_declension(count: int) -> str:
    """Правильное склонение слова 'коммит' по-русски."""
    n = count % 100
    if 11 <= n <= 19:
        return f"{count} коммитов"
    last = n % 10
    if last == 1:
        return f"{count} коммит"
    if 2 <= last <= 4:
        return f"{count} коммита"
    return f"{count} коммитов"


class GitProgressEvaluator:
    """Сервисный оркестратор оценки прогресса разработки по Git-источникам."""

    def __init__(
        self,
        git_provider: BaseGitSourceProvider,
        notion_client: NotionClientLike | None,
        confirmation_store: ConfirmationStore,
        persona: Any | None = None,
        default_activity_db_id: str | None = None,
    ) -> None:
        self.git_provider = git_provider
        self.notion_client = notion_client
        self.confirmation_store = confirmation_store
        self._persona = persona
        self.default_activity_db_id = (
            default_activity_db_id
            if default_activity_db_id is not None
            else getattr(config, "NOTION_ACTIVITY_DB_ID", "")
        )

        register_action_handler(NOTION_ACTION_TYPE, self._handle_notion_sync)

    def _get_persona(self) -> Any:
        if self._persona is not None:
            return self._persona
        try:
            from src.persona.current import current_persona

            return current_persona()
        except Exception:
            return None

    async def evaluate(
        self,
        since: datetime | None = None,
        fetch_remote: bool = True,
    ) -> EvaluationRun:
        """Опрос репозиториев, санитизация и формирование сводки активности.
        
        Инвариант безопасности: git_chain_workspaces вызывается ПЕРВОЙ операцией,
        до любых обращений к self.git_provider (T-04-01, D-12, D-13).
        """
        split = git_chain_workspaces(self._get_persona())

        now = datetime.now(timezone.utc)
        try:
            tz = ZoneInfo(getattr(config, "TZ", "Europe/Moscow"))
        except Exception:
            tz = timezone.utc
        date_iso = now.astimezone(tz).date().isoformat()
        period_start = since or (now - timedelta(days=DEFAULT_STAGNATION_DAYS))

        entries: list[WorkspaceEvaluation] = []

        for ws in split.eligible:
            ws_id = getattr(ws, "id", str(ws))
            ws_remote = getattr(ws, "remote", None)
            ws_alias = getattr(ws, "ssh_alias", None)
            ws_path_str = getattr(ws, "path", "")

            # 1. Классификация по данным без вызова провайдера
            if not ws_remote and not ws_alias:
                entries.append(
                    WorkspaceEvaluation(
                        workspace=ws,
                        status=GitStatus.NO_REMOTE,
                        status_text="пропущено: нет remote",
                        report=None,
                        notion_ready=False,
                        notion_note="Notion не настроен",
                    )
                )
                continue

            ws_path = Path(ws_path_str) if ws_path_str else None
            if not ws_path or not ws_path.is_dir():
                entries.append(
                    WorkspaceEvaluation(
                        workspace=ws,
                        status=GitStatus.NO_DIR,
                        status_text="пропущено: нет каталога",
                        report=None,
                        notion_ready=False,
                        notion_note="Notion не настроен",
                    )
                )
                continue

            git_dir = ws_path / ".git"
            if not git_dir.exists():
                entries.append(
                    WorkspaceEvaluation(
                        workspace=ws,
                        status=GitStatus.NOT_GIT,
                        status_text="пропущено: не git-репозиторий",
                        report=None,
                        notion_ready=False,
                        notion_note="Notion не настроен",
                    )
                )
                continue

            # 2. Fetch remote (если включено)
            if fetch_remote:
                try:
                    fetch_ok = await self.git_provider.fetch_remote(ws)
                    if not fetch_ok:
                        logger.warning("fetch_remote вернул False для %s", ws_id)
                        entries.append(
                            WorkspaceEvaluation(
                                workspace=ws,
                                status=GitStatus.FETCH_FAILED,
                                status_text="сбой SSH",
                                report=None,
                                notion_ready=False,
                                notion_note="Notion не настроен",
                            )
                        )
                        continue
                except Exception as e:
                    logger.warning("fetch_remote ошибка для %s: %s", ws_id, type(e).__name__)
                    entries.append(
                        WorkspaceEvaluation(
                            workspace=ws,
                            status=GitStatus.FETCH_FAILED,
                            status_text="сбой SSH",
                            report=None,
                            notion_ready=False,
                            notion_note="Notion не настроен",
                        )
                    )
                    continue

            # 3. Чтение и санитизация коммитов
            try:
                raw_commits = await self.git_provider.get_commits_since(ws, since=period_start)
            except Exception as e:
                logger.warning("get_commits_since ошибка для %s: %s", ws_id, type(e).__name__)
                raw_commits = []

            safe_commits = sanitize_git_commits_for_llm(ws, raw_commits, self._get_persona())
            commit_count = len(safe_commits)
            latest_commit_date = safe_commits[0].date if safe_commits else None

            # Определение застоя: нет коммитов за период или последний старше DEFAULT_STAGNATION_DAYS
            is_stagnant = False
            if commit_count == 0:
                is_stagnant = True
            elif latest_commit_date:
                diff = now - (
                    latest_commit_date
                    if latest_commit_date.tzinfo
                    else latest_commit_date.replace(tzinfo=timezone.utc)
                )
                if diff > timedelta(days=DEFAULT_STAGNATION_DAYS):
                    is_stagnant = True

            # Формирование запасного шаблона сводки
            if commit_count == 0:
                summary_text = "За анализируемый период коммиты отсутствуют."
            else:
                top_msgs = [c.message for c in safe_commits[:3] if c.message]
                commit_decl = _format_commit_declension(commit_count)
                summary_text = (
                    f"Зафиксировано {commit_decl}. "
                    f"Последние изменения: {'; '.join(top_msgs)}."
                )

            notion_proj_id = getattr(ws, "notion_project", None)
            client_ok = bool(
                self.notion_client is not None
                and getattr(self.notion_client, "is_configured", True)
            )
            notion_ready = bool(
                is_valid_notion_id(notion_proj_id)
                and is_valid_notion_id(self.default_activity_db_id)
                and client_ok
            )
            notion_note = "" if notion_ready else "Notion не настроен"

            report = GitProgressReport(
                workspace_id=ws_id,
                notion_project_id=notion_proj_id,
                period_start=period_start,
                period_end=now,
                commit_count=commit_count,
                latest_commit_date=latest_commit_date,
                summary_text=summary_text,
                is_stagnant=is_stagnant,
                clearance=getattr(ws, "clearance", WorkspaceClearance.PUBLIC),
            )

            entries.append(
                WorkspaceEvaluation(
                    workspace=ws,
                    status=GitStatus.OK,
                    status_text=summary_text,
                    report=report,
                    notion_ready=notion_ready,
                    notion_note=notion_note,
                )
            )

        nda_excluded = bool(split.excluded_count > 0 or split.unresolved)
        return EvaluationRun(
            entries=tuple(entries),
            nda_excluded=nda_excluded,
            date_iso=date_iso,
        )

    async def propose_card(
        self,
        entry: WorkspaceEvaluation,
        date_iso: str,
        ttl_minutes: int = CARD_TTL_MINUTES,
    ) -> CardProposal:
        """Создать отложенное подтверждение PendingConfirmation для одного проекта (D-04, D-11)."""
        if not entry.notion_ready or entry.report is None:
            ws_id = getattr(entry.workspace, "id", str(entry.workspace))
            raise ValueError(f"Рабочее пространство {ws_id} не готово к созданию карточки Notion")

        persona = self._get_persona()
        persona_id = getattr(persona, "id", "default_persona")
        ws = entry.workspace
        ws_id = getattr(ws, "id", str(ws))
        ws_name = getattr(ws, "name", ws_id)
        report = entry.report

        payload = {
            "workspace_id": ws_id,
            "workspace_name": ws_name,
            "notion_project_id": getattr(ws, "notion_project", ""),
            "database_id": self.default_activity_db_id,
            "date_iso": date_iso,
            "commit_count": report.commit_count,
            "status": "Застой" if report.is_stagnant else "Активно",
            "summary": report.summary_text,
        }

        target_id = f"{ws_id}|{date_iso}"
        conf = await self.confirmation_store.create_confirmation(
            persona_id=persona_id,
            action_type=NOTION_ACTION_TYPE,
            target_id=target_id,
            payload=payload,
            channel=ConfirmationChannel.TELEGRAM,
            ttl_minutes=ttl_minutes,
        )
        return CardProposal(confirmation=conf, created=True)

    def format_run_text(self, run: EvaluationRun) -> str:
        """Сформировать текст ответа для команды /git (D-04, D-05, D-12)."""
        lines: list[str] = ["🚀 Ход разработки по git-проектам:\n"]

        for entry in run.entries:
            ws_name = getattr(entry.workspace, "name", getattr(entry.workspace, "id", "Проект"))
            if entry.status == GitStatus.OK:
                emoji = "⚠️" if (entry.report and entry.report.is_stagnant) else "⚡"
                note_suffix = f" [{entry.notion_note}]" if entry.notion_note else ""
                lines.append(f"• {ws_name}: {emoji} {entry.status_text}{note_suffix}")
            else:
                lines.append(f"• {ws_name}: {entry.status_text}")

        if run.nda_excluded:
            lines.append(f"\n🔒 {NDA_EXCLUDED_LINE}")

        full_text = "\n".join(lines).strip()
        if len(full_text) > 3900:
            return full_text[:3897] + "..."
        return full_text

    def format_card_text(self, conf: PendingConfirmation) -> str:
        """Сформировать текст интерактивной карточки подтверждения (D-04)."""
        payload = conf.payload or {}
        ws_name = payload.get("workspace_name") or payload.get("workspace_id") or "Проект"
        status = payload.get("status", "Активно")
        commit_count = payload.get("commit_count", 0)
        date_iso = payload.get("date_iso", "")
        summary = payload.get("summary", "")

        status_emoji = "⚠️" if status == "Застой" else "⚡"
        decl = _format_commit_declension(int(commit_count))

        lines = [
            f"📝 Публикация в Notion: {ws_name}",
            f"",
            f"• Статус: {status_emoji} {status}",
            f"• Коммитов: {decl}",
            f"• Период: {date_iso}",
            f"",
            f"Сводка для Notion:",
            f"{summary}",
        ]
        return "\n".join(lines).strip()

    async def _handle_notion_sync(self, conf: PendingConfirmation) -> dict[str, Any]:
        """Обработчик действия HITL: публикация активности в Notion (D-06, D-09, D-10)."""
        if self.notion_client is None:
            raise NotionSyncError("Клиент Notion не настроен")

        payload = conf.payload or {}
        project_id = payload.get("notion_project_id")
        db_id = payload.get("database_id")

        if not is_valid_notion_id(project_id) or not is_valid_notion_id(db_id):
            raise NotionSyncError(
                f"Некорректный ID Notion: project={project_id}, database={db_id}"
            )

        date_iso = payload.get("date_iso") or datetime.now(timezone.utc).date().isoformat()
        commit_count = int(payload.get("commit_count", 0))
        status = str(payload.get("status", "Активно"))
        summary = str(payload.get("summary", ""))

        try:
            res = await self.notion_client.log_project_activity(
                database_id=db_id,
                project_page_id=project_id,
                date_iso=date_iso,
                commit_count=commit_count,
                status=status,
                summary=summary,
            )
            return {"success": True, "page_id": res.get("id"), "notion_response": res}
        except Exception as e:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            logger.warning(
                "Ошибка публикации в Notion для %s: %s (status=%s)",
                payload.get("workspace_id"),
                type(e).__name__,
                status_code,
            )
            raise NotionSyncError(
                f"Ошибка вызова Notion API: {type(e).__name__} (status={status_code})"
            ) from e
