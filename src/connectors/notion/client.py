"""Async Notion API client for Voice-First Second Brain synchronization."""

import logging
from typing import Any
import httpx

from src import config
from src.connectors.notion import schema
from src.models.second_brain import (
    DebriefResult,
    NewTaskItem,
    WaitingForItem,
)

logger = logging.getLogger(__name__)


class NotionAsyncClient:
    """Async client interacting with Notion API v1."""

    BASE_URL = "https://api.notion.com/v1"
    NOTION_VERSION = "2022-06-28"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.api_key = api_key if api_key is not None else config.NOTION_API_KEY
        self.timeout = timeout
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": self.NOTION_VERSION,
            "Content-Type": "application/json",
        }

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("secret_mock"))

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers=self._headers,
            timeout=self.timeout,
        )

    async def get_current_user(self) -> dict[str, Any] | None:
        """Verify authentication by getting bot user info."""
        if not self.is_configured:
            return None
        async with self._client() as client:
            try:
                resp = await client.get("/users/me")
                if resp.status_code == 200:
                    return resp.json()
                logger.error("Notion auth error: %s - %s", resp.status_code, resp.text)
                return None
            except Exception as e:
                logger.error("Failed to connect to Notion: %s", e)
                return None

    async def create_task(
        self,
        database_id: str,
        title: str,
        priority: str = "P2",
        area: str = "Разное",
        due_date: str | None = None,
        project_page_id: str | None = None,
        estimated_minutes: int | None = None,
    ) -> dict[str, Any]:
        """Create a new task in Tasks DB."""
        properties: dict[str, Any] = {
            schema.TaskProperties.TITLE: schema.title_property(title),
            schema.TaskProperties.STATUS: schema.status_property("To Do"),
            schema.TaskProperties.PRIORITY: schema.select_property(priority),
            schema.TaskProperties.AREA: schema.select_property(area),
        }
        if due_date:
            properties[schema.TaskProperties.DUE_DATE] = schema.date_property(due_date)
        if estimated_minutes:
            properties[schema.TaskProperties.ESTIMATED_MINUTES] = schema.number_property(estimated_minutes)
        if project_page_id:
            properties[schema.TaskProperties.PROJECT] = schema.relation_property([project_page_id])

        payload = {
            "parent": {"database_id": database_id},
            "properties": properties,
        }

        async with self._client() as client:
            resp = await client.post("/pages", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def update_page_properties(
        self,
        page_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        """Update properties of an existing page."""
        async with self._client() as client:
            resp = await client.patch(f"/pages/{page_id}", json={"properties": properties})
            resp.raise_for_status()
            return resp.json()

    async def mark_task_done(self, page_id: str) -> dict[str, Any]:
        """Set task status to 'Done'."""
        properties = {
            schema.TaskProperties.STATUS: schema.status_property("Done"),
        }
        return await self.update_page_properties(page_id, properties)

    async def query_tasks(
        self,
        database_id: str,
        title_contains: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query tasks database with optional title or status filter."""
        filters: list[dict[str, Any]] = []

        if title_contains:
            filters.append({
                "property": schema.TaskProperties.TITLE,
                "title": {"contains": title_contains},
            })
        if status:
            filters.append({
                "property": schema.TaskProperties.STATUS,
                "status": {"equals": status},
            })

        payload: dict[str, Any] = {}
        if len(filters) == 1:
            payload["filter"] = filters[0]
        elif len(filters) > 1:
            payload["filter"] = {"and": filters}

        async with self._client() as client:
            resp = await client.post(f"/databases/{database_id}/query", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [])

    async def add_waiting_item(
        self,
        database_id: str,
        what: str,
        person: str,
        check_date: str | None = None,
        context: str | None = None,
    ) -> dict[str, Any]:
        """Add an item into People & Waiting For DB."""
        properties: dict[str, Any] = {
            schema.WaitingForProperties.WHAT: schema.title_property(what),
            schema.WaitingForProperties.PERSON: schema.rich_text_property(person),
            schema.WaitingForProperties.STATUS: schema.status_property("Waiting"),
        }
        if check_date:
            properties[schema.WaitingForProperties.CHECK_DATE] = schema.date_property(check_date)
        if context:
            properties[schema.WaitingForProperties.CONTEXT] = schema.rich_text_property(context)

        payload = {
            "parent": {"database_id": database_id},
            "properties": properties,
        }
        async with self._client() as client:
            resp = await client.post("/pages", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def add_daily_journal(
        self,
        database_id: str,
        date_str: str,
        summary: str,
        insights: str | None = None,
        raw_transcript: str = "",
    ) -> dict[str, Any]:
        """Add entry into Daily Journal DB."""
        properties: dict[str, Any] = {
            schema.JournalProperties.DATE: schema.title_property(date_str),
            schema.JournalProperties.DONE_SUMMARY: schema.rich_text_property(summary),
        }
        if insights:
            properties[schema.JournalProperties.KEY_INSIGHTS] = schema.rich_text_property(insights)
        if raw_transcript:
            # Notion rich text limit is 2000 chars per text block
            properties[schema.JournalProperties.RAW_TRANSCRIPT] = schema.rich_text_property(raw_transcript[:2000])

        payload = {
            "parent": {"database_id": database_id},
            "properties": properties,
        }
        async with self._client() as client:
            resp = await client.post("/pages", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def sync_debrief(
        self,
        result: DebriefResult,
        tasks_db_id: str = config.NOTION_TASKS_DB_ID,
        waiting_db_id: str = config.NOTION_WAITING_DB_ID,
        journal_db_id: str = config.NOTION_JOURNAL_DB_ID,
    ) -> dict[str, Any]:
        """Orchestrate applying the full debrief result to Notion databases."""
        sync_report: dict[str, Any] = {
            "marked_done": [],
            "created_tasks": [],
            "created_waiting": [],
            "journal_created": False,
        }

        if not self.is_configured:
            logger.info("Notion client not configured, skipping live remote sync.")
            return sync_report

        # 1. Close completed tasks
        if tasks_db_id:
            for comp in result.completed_tasks:
                try:
                    # Search for matching existing open task
                    query_word = comp.normalized_title.split()[0] if comp.normalized_title.split() else comp.normalized_title
                    matches = await self.query_tasks(tasks_db_id, title_contains=query_word)
                    for page in matches:
                        pid = page.get("id")
                        if pid:
                            await self.mark_task_done(pid)
                            sync_report["marked_done"].append(pid)
                            break
                except Exception as e:
                    logger.warning("Error completing task in Notion: %s", e)

        # 2. Create new tasks
        if tasks_db_id:
            for task in result.new_tasks:
                try:
                    p = await self.create_task(
                        database_id=tasks_db_id,
                        title=task.title,
                        priority=task.priority.value,
                        area=task.area.value,
                        due_date=task.due_date,
                        estimated_minutes=task.estimated_minutes,
                    )
                    if p.get("id"):
                        sync_report["created_tasks"].append(p["id"])
                except Exception as e:
                    logger.warning("Error creating task in Notion: %s", e)

        # 3. Add waiting items
        if waiting_db_id:
            for w in result.waiting_for_items:
                try:
                    p = await self.add_waiting_item(
                        database_id=waiting_db_id,
                        what=w.what,
                        person=w.person,
                        check_date=w.check_date,
                        context=w.context,
                    )
                    if p.get("id"):
                        sync_report["created_waiting"].append(p["id"])
                except Exception as e:
                    logger.warning("Error creating waiting item in Notion: %s", e)

        # 4. Add daily journal
        if journal_db_id:
            try:
                j = await self.add_daily_journal(
                    database_id=journal_db_id,
                    date_str=result.journal_entry.date_str,
                    summary=result.journal_entry.done_summary,
                    insights=result.journal_entry.key_insights,
                    raw_transcript=result.journal_entry.raw_transcript,
                )
                if j.get("id"):
                    sync_report["journal_created"] = True
            except Exception as e:
                logger.warning("Error creating journal entry in Notion: %s", e)

        return sync_report

    async def log_project_activity(
        self,
        database_id: str,
        project_page_id: str,
        date_iso: str,
        commit_count: int,
        status: str,
        summary: str,
    ) -> dict[str, Any]:
        """Создает запись в базе данных логов активности проектов Notion (NTN-01)."""
        payload = {
            "parent": {"database_id": database_id},
            "properties": {
                "Name": {"title": [{"text": {"content": f"Сводка {date_iso}"}}]},
                "Project": {"relation": [{"id": project_page_id}]},
                "Date": {"date": {"start": date_iso}},
                "Commits": {"number": commit_count},
                "Status": {"select": {"name": status}},
            },
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": summary[:2000]}}]
                    },
                }
            ],
        }
        async with self._client() as client:
            resp = await client.post("/pages", json=payload)
            resp.raise_for_status()
            return resp.json()

