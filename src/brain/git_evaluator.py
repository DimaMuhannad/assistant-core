"""GitProgressEvaluator: оркестратор оценки Git-активности и синхронизации с Notion (NTN-01, NTN-02).

Реализует:
1. Опрос репозиториев персоны через BaseGitSourceProvider (только чтение).
2. Расчет статуса активности и признака застоя (> 7 дней без коммитов).
3. Строгий Air-Gap для пространств restricted_nda (GIT-04).
4. Создание отложенных подтверждений PendingConfirmation (action_type='notion_project_sync').
5. Формирование индивидуальных карточек Telegram для каждого проекта (D-07).
6. Исполнение записи в Notion только при явном HITL-подтверждении владельца.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from assistant_shared.hitl import (
    ConfirmationChannel,
    ConfirmationStore,
    PendingConfirmation,
    register_action_handler,
)
from src import config
from src.core.ports.clients import NotionClientLike
from src.core.domain.entities import (
    GitCommit,
    GitProgressReport,
    Workspace,
    WorkspaceClearance,
)
from src.core.ports.connectors import BaseGitSourceProvider
from src.security.airgap import (
    is_nda_workspace,
    sanitize_git_commits_for_llm,
    sanitize_notion_payload_for_airgap,
)

logger = logging.getLogger(__name__)


class GitProgressEvaluator:
    """Сервисный оркестратор оценки прогресса разработки по Git-источникам."""

    def __init__(
        self,
        git_provider: BaseGitSourceProvider,
        notion_client: NotionClientLike,
        confirmation_store: ConfirmationStore,
        persona: Any | None = None,
        default_activity_db_id: str | None = None,
    ) -> None:
        self.git_provider = git_provider
        self.notion_client = notion_client
        self.confirmation_store = confirmation_store
        self._persona = persona
        self.default_activity_db_id = default_activity_db_id or getattr(config, "NOTION_ACTIVITY_DB_ID", "project_activity_logs")

        # Регистрируем обработчик действия HITL для notion_project_sync
        register_action_handler("notion_project_sync", self._handle_notion_sync)

    def _get_persona(self) -> Any:
        if self._persona is not None:
            return self._persona
        try:
            from src.persona.current import current_persona
            return current_persona()
        except Exception:
            return None

    async def evaluate_workspaces(
        self,
        since: datetime | None = None,
        fetch_remote: bool = True,
    ) -> list[GitProgressReport]:
        """Опрос репозиториев, санитизация и формирование GitProgressReport."""
        repos = await self.git_provider.list_repositories()
        reports: list[GitProgressReport] = []
        now = datetime.now(timezone.utc)
        period_start = since or (now - timedelta(days=7))

        persona = self._get_persona()

        for ws in repos:
            if fetch_remote:
                try:
                    await self.git_provider.fetch_remote(ws)
                except Exception as e:
                    logger.warning("Не удалось выполнить fetch для %s: %s", ws.id, e)

            raw_commits = await self.git_provider.get_commits_since(ws, since=period_start)
            safe_commits = sanitize_git_commits_for_llm(ws, raw_commits, persona)

            commit_count = len(safe_commits)
            latest_commit_date = safe_commits[0].date if safe_commits else None

            # Определение застоя: нет коммитов за период или последний коммит старше 7 дней
            is_stagnant = False
            if commit_count == 0:
                is_stagnant = True
            elif latest_commit_date:
                diff = now - (
                    latest_commit_date
                    if latest_commit_date.tzinfo
                    else latest_commit_date.replace(tzinfo=timezone.utc)
                )
                if diff > timedelta(days=7):
                    is_stagnant = True

            # Формирование summary_text
            is_nda = is_nda_workspace(ws, persona)
            if is_nda:
                summary_text = (
                    f"Проект находится под защитой Air-Gap (NDA). "
                    f"Зафиксировано {commit_count} коммитов за период."
                )
            else:
                if commit_count == 0:
                    summary_text = "За анализируемый период коммиты отсутствуют."
                else:
                    top_msgs = [c.message for c in safe_commits[:3] if c.message]
                    summary_text = (
                        f"Зафиксировано {commit_count} коммитов. "
                        f"Последние изменения: {'; '.join(top_msgs)}."
                    )

            notion_proj_id = getattr(ws, "notion_project", None)

            report = GitProgressReport(
                workspace_id=ws.id,
                notion_project_id=notion_proj_id,
                period_start=period_start,
                period_end=now,
                commit_count=commit_count,
                latest_commit_date=latest_commit_date,
                summary_text=summary_text,
                is_stagnant=is_stagnant,
                clearance=ws.clearance,
            )
            reports.append(report)

        return reports

    async def propose_notion_updates(
        self,
        reports: list[GitProgressReport] | None = None,
        since: datetime | None = None,
        ttl_minutes: int = 1440,  # 24 часа по умолчанию
    ) -> list[PendingConfirmation]:
        """Формирует запросы на подтверждение для каждого проекта (D-07)."""
        if reports is None:
            reports = await self.evaluate_workspaces(since=since)

        persona = self._get_persona()
        persona_id = getattr(persona, "id", "default_persona")
        created_confirmations: list[PendingConfirmation] = []

        for report in reports:
            raw_payload = {
                "workspace_id": report.workspace_id,
                "notion_project_id": report.notion_project_id,
                "database_id": self.default_activity_db_id,
                "date_iso": report.period_end.date().isoformat(),
                "commit_count": report.commit_count,
                "status": "Застой" if report.is_stagnant else "Активно",
                "summary": report.summary_text,
                "clearance": report.clearance.value if hasattr(report.clearance, "value") else str(report.clearance),
            }

            # Строгий Air-Gap фильтр для Notion
            safe_payload = sanitize_notion_payload_for_airgap(report.workspace_id, raw_payload, persona)

            conf = await self.confirmation_store.create_confirmation(
                persona_id=persona_id,
                action_type="notion_project_sync",
                target_id=report.workspace_id,
                payload=safe_payload,
                channel=ConfirmationChannel.TELEGRAM,
                ttl_minutes=ttl_minutes,
            )
            created_confirmations.append(conf)

        return created_confirmations

    @staticmethod
    def format_telegram_card(
        report: GitProgressReport,
        confirmation_id: str,
    ) -> tuple[str, list[list[dict[str, str]]]]:
        """Формирует текст карточки и инлайн-кнопки для Telegram (D-07)."""
        status_label = "⚠️ Застой (>7 дн)" if report.is_stagnant else "⚡ Активно"
        last_date = (
            report.latest_commit_date.strftime("%d.%m.%Y %H:%M")
            if report.latest_commit_date
            else "Нет данных"
        )
        clearance_label = (
            "🔒 NDA"
            if getattr(report.clearance, "value", str(report.clearance)) == "restricted_nda"
            else "🌐 Public/Internal"
        )

        text = (
            f"🚀 **Ход разработки: {report.workspace_id}**\n\n"
            f"• Допуск: {clearance_label}\n"
            f"• Статус: {status_label}\n"
            f"• Коммитов: {report.commit_count}\n"
            f"• Последний коммит: {last_date}\n\n"
            f"📝 **Сводка для Notion:**\n{report.summary_text}"
        )

        keyboard = [
            [
                {"text": "✅ Опубликовать в Notion", "callback_data": f"hitl:confirm:{confirmation_id}"},
                {"text": "❌ Отклонить", "callback_data": f"hitl:reject:{confirmation_id}"},
            ]
        ]
        return text, keyboard

    async def _handle_notion_sync(self, conf: PendingConfirmation) -> dict[str, Any]:
        """Обработчик действия HITL, вызываемый при подтверждении пользователем."""
        payload = conf.payload
        project_id = payload.get("notion_project_id") or conf.target_id
        db_id = payload.get("database_id") or self.default_activity_db_id
        date_iso = payload.get("date_iso") or datetime.now(timezone.utc).date().isoformat()
        commit_count = int(payload.get("commit_count", 0))
        status = str(payload.get("status", "Активно"))
        summary = str(payload.get("summary", ""))

        logger.info(
            "Отправка активности в Notion: проект=%s, коммитов=%s, статус=%s",
            project_id,
            commit_count,
            status,
        )

        res = await self.notion_client.log_project_activity(
            database_id=db_id,
            project_page_id=project_id,
            date_iso=date_iso,
            commit_count=commit_count,
            status=status,
            summary=summary,
        )
        return {"success": True, "page_id": res.get("id"), "notion_response": res}
