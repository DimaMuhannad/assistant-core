"""CLI and SDK helper for Dev Agent to manage Notion Engineering Tasks."""

import argparse
import asyncio
import logging
from datetime import datetime
from typing import Any
import httpx

from src import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("notion_dev")

NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"
ISSUES_DB_ID = "3eaa2e48-40a0-81e9-ad37-e793caf99ece"


def get_headers() -> dict[str, str]:
    token = config.NOTION_API_KEY
    if not token:
        raise ValueError("NOTION_API_KEY not configured in .env")
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


async def find_task(client: httpx.AsyncClient, query_or_id: str) -> dict[str, Any] | None:
    """Find task page by ID or partial title match."""
    # Check if direct page_id
    clean_id = query_or_id.replace("-", "").strip()
    if len(clean_id) == 32:
        try:
            resp = await client.get(f"/pages/{query_or_id}")
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass

    # Search in issues DB
    resp = await client.post(
        f"/databases/{ISSUES_DB_ID}/query",
        json={"filter": {"property": "Issue", "title": {"contains": query_or_id}}},
    )
    if resp.status_code == 200:
        results = resp.json().get("results", [])
        if results:
            return results[0]
    return None


async def get_next_issue_number(client: httpx.AsyncClient) -> int:
    """Fetch highest issue number and return next incremental number."""
    resp = await client.post(
        f"/databases/{ISSUES_DB_ID}/query",
        json={"sorts": [{"property": "№", "direction": "descending"}], "page_size": 1},
    )
    if resp.status_code == 200:
        results = resp.json().get("results", [])
        if results and results[0]["properties"].get("№", {}).get("number"):
            return results[0]["properties"]["№"]["number"] + 1
    return 1


async def create_issue(
    title: str,
    module: str = "LMS pro.guap.ru (Academic)",
    priority: str = "P1 - High",
    issue_type: str = "🚀 feat (Feature)",
    status: str = "In Progress",
) -> dict[str, Any]:
    """Create a new issue in Notion Issues DB."""
    async with httpx.AsyncClient(base_url=BASE_URL, headers=get_headers(), timeout=20.0) as client:
        next_num = await get_next_issue_number(client)
        payload = {
            "parent": {"database_id": ISSUES_DB_ID},
            "properties": {
                "Issue": {"title": [{"text": {"content": title}}]},
                "Module": {"select": {"name": module}},
                "Priority": {"select": {"name": priority}},
                "Type": {"select": {"name": issue_type}},
                "Status": {"status": {"name": status}},
                "№": {"number": next_num},
            },
        }
        resp = await client.post("/pages", json=payload)
        resp.raise_for_status()
        data = resp.json()
        logger.info("Created issue #%02d '%s' (ID: %s, Status: %s)", next_num, title, data["id"], status)
        return data


async def start_task(task_query: str) -> dict[str, Any]:
    """Transition task from 'Ready for Dev' / 'Backlog' to 'In Progress'."""
    async with httpx.AsyncClient(base_url=BASE_URL, headers=get_headers(), timeout=20.0) as client:
        task = await find_task(client, task_query)
        if not task:
            raise ValueError(f"Task '{task_query}' not found in Notion Issues DB.")

        page_id = task["id"]
        title = task["properties"]["Issue"]["title"][0]["plain_text"]
        logger.info("Starting task '%s' (ID: %s)...", title, page_id)

        resp = await client.patch(
            f"/pages/{page_id}",
            json={"properties": {"Status": {"status": {"name": "In Progress"}}}},
        )
        resp.raise_for_status()
        logger.info("Task '%s' is now In Progress.", title)
        return resp.json()


async def finish_task(
    task_query: str,
    commit_hash: str,
    changeset: str,
    design_decisions: str,
    quality_gates: str,
    tech_debt: str,
) -> dict[str, Any]:
    """Transition task to 'Done', record Git commit, and write Session Provenance into page body."""
    async with httpx.AsyncClient(base_url=BASE_URL, headers=get_headers(), timeout=25.0) as client:
        task = await find_task(client, task_query)
        if not task:
            raise ValueError(f"Task '{task_query}' not found in Notion Issues DB.")

        page_id = task["id"]
        title = task["properties"]["Issue"]["title"][0]["plain_text"]
        logger.info("Finishing task '%s' (ID: %s)...", title, page_id)

        # 1. Update properties
        resp = await client.patch(
            f"/pages/{page_id}",
            json={
                "properties": {
                    "Status": {"status": {"name": "Done"}},
                    "Git Commit": {"rich_text": [{"text": {"content": commit_hash}}]},
                }
            },
        )
        resp.raise_for_status()

        # 2. Append Session Provenance blocks to page content
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        blocks = [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": f"📝 Session Provenance ({now_str})"}}]
                },
            },
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "icon": {"type": "emoji", "emoji": "📦"},
                    "rich_text": [
                        {"type": "text", "text": {"content": "[Changeset]: "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": changeset}},
                    ],
                },
            },
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "icon": {"type": "emoji", "emoji": "💡"},
                    "rich_text": [
                        {"type": "text", "text": {"content": "[Design Decisions]: "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": design_decisions}},
                    ],
                },
            },
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "icon": {"type": "emoji", "emoji": "🧪"},
                    "rich_text": [
                        {"type": "text", "text": {"content": "[Quality Gates Status]: "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": quality_gates}},
                    ],
                },
            },
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "icon": {"type": "emoji", "emoji": "⚠️"},
                    "rich_text": [
                        {"type": "text", "text": {"content": "[Technical Debt Introduced]: "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": tech_debt}},
                    ],
                },
            },
        ]

        b_resp = await client.patch(f"/blocks/{page_id}/children", json={"children": blocks})
        if b_resp.status_code != 200:
            logger.error("Notion block append error: %s - %s", b_resp.status_code, b_resp.text)
        b_resp.raise_for_status()
        logger.info("Session Provenance documented in Notion for '%s'.", title)
        return resp.json()


async def block_task(task_query: str, error_log: str, hypotheses: str) -> dict[str, Any]:
    """Transition task to 'Backlog' and document block reason."""
    async with httpx.AsyncClient(base_url=BASE_URL, headers=get_headers(), timeout=25.0) as client:
        task = await find_task(client, task_query)
        if not task:
            raise ValueError(f"Task '{task_query}' not found in Notion Issues DB.")

        page_id = task["id"]
        title = task["properties"]["Issue"]["title"][0]["plain_text"]
        logger.warning("Blocking task '%s' (ID: %s)...", title, page_id)

        resp = await client.patch(
            f"/pages/{page_id}",
            json={"properties": {"Status": {"status": {"name": "Backlog"}}}},
        )
        resp.raise_for_status()

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        blocks = [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": f"🚨 Blocked Task Report ({now_str})"}}]
                },
            },
            {
                "object": "block",
                "type": "code",
                "code": {
                    "language": "plain text",
                    "rich_text": [{"type": "text", "text": {"content": error_log[:1900]}}],
                },
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "Гипотезы и шаги для Архитектора: ", "annotations": {"bold": True}}},
                        {"type": "text", "text": {"content": hypotheses}},
                    ]
                },
            },
        ]
        await client.patch(f"/blocks/{page_id}/children", json={"children": blocks})
        logger.info("Blocked task documented in Notion for '%s'.", title)
        return resp.json()


async def list_tasks(status: str | None = None, reverse: bool = False) -> list[dict[str, Any]]:
    """List issues from Notion Issues DB sorted chronologically by default."""
    payload: dict[str, Any] = {
        "sorts": [{"property": "№", "direction": "descending" if reverse else "ascending"}]
    }
    if status:
        payload["filter"] = {"property": "Status", "status": {"equals": status}}

    async with httpx.AsyncClient(base_url=BASE_URL, headers=get_headers(), timeout=20.0) as client:
        resp = await client.post(f"/databases/{ISSUES_DB_ID}/query", json=payload)
        resp.raise_for_status()
        tasks = resp.json().get("results", [])
        return [
            {
                "id": t["id"],
                "num": t["properties"].get("№", {}).get("number") if t["properties"].get("№") else None,
                "title": t["properties"]["Issue"]["title"][0]["plain_text"] if t["properties"]["Issue"]["title"] else "",
                "status": t["properties"]["Status"]["status"]["name"] if t["properties"].get("Status") else "",
                "type": t["properties"]["Type"]["select"]["name"] if t["properties"].get("Type", {}).get("select") else "",
                "priority": t["properties"]["Priority"]["select"]["name"] if t["properties"].get("Priority", {}).get("select") else "",
                "module": t["properties"]["Module"]["select"]["name"] if t["properties"].get("Module", {}).get("select") else "",
                "commit": t["properties"]["Git Commit"]["rich_text"][0]["plain_text"] if t["properties"].get("Git Commit", {}).get("rich_text") else "",
            }
            for t in tasks
        ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage Notion Engineering Tasks")
    subparsers = parser.add_subparsers(dest="cmd")

    # list
    p_list = subparsers.add_parser("list")
    p_list.add_argument("--status", help="Filter by status (Backlog, Ready for Dev, In Progress, Done)")
    p_list.add_argument("--reverse", action="store_true", help="Sort in reverse chronological order (newest first)")

    # create
    p_create = subparsers.add_parser("create")
    p_create.add_argument("title", help="Issue title")
    p_create.add_argument("--module", default="LMS pro.guap.ru (Academic)", help="Module name")
    p_create.add_argument("--priority", default="P1 - High", help="Priority")
    p_create.add_argument("--type", default="🚀 feat (Feature)", help="Type")
    p_create.add_argument("--status", default="In Progress", help="Initial status")

    # start
    p_start = subparsers.add_parser("start")
    p_start.add_argument("task", help="Task title or ID")

    # finish
    p_fin = subparsers.add_parser("finish")
    p_fin.add_argument("task", help="Task title or ID")
    p_fin.add_argument("--commit", required=True, help="Git commit hash")
    p_fin.add_argument("--changeset", required=True, help="What changed physically")
    p_fin.add_argument("--decisions", required=True, help="Design decisions (KISS/YAGNI)")
    p_fin.add_argument("--quality", required=True, help="Quality gates status (pytest, linter)")
    p_fin.add_argument("--debt", default="None", help="Technical debt introduced")

    # block
    p_block = subparsers.add_parser("block")
    p_block.add_argument("task", help="Task title or ID")
    p_block.add_argument("--error", required=True, help="Error logs")
    p_block.add_argument("--hypotheses", required=True, help="Hypotheses for architect")

    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    if args.cmd == "list":
        res = loop.run_until_complete(list_tasks(args.status, getattr(args, "reverse", False)))
        for t in res:
            num_str = f"#{t['num']:02d}" if t.get("num") is not None else "[-]"
            print(f"{num_str} [{t['status']:<11}] [{t['priority']:<11}] [{t['module']:<30}] {t['title']} ({t['commit']})")
    elif args.cmd == "create":
        loop.run_until_complete(create_issue(args.title, args.module, args.priority, args.type, args.status))
    elif args.cmd == "start":
        loop.run_until_complete(start_task(args.task))
    elif args.cmd == "finish":
        loop.run_until_complete(finish_task(args.task, args.commit, args.changeset, args.decisions, args.quality, args.debt))
    elif args.cmd == "block":
        loop.run_until_complete(block_task(args.task, args.error, args.hypotheses))
    else:
        parser.print_help()
