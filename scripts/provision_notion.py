"""Provision and configure Notion Second Brain databases under a parent page."""

import argparse
import asyncio
import logging
import re
import sys
from typing import Any
import httpx

from src import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("provision_notion")

NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"


def clean_page_id(raw_id_or_url: str) -> str:
    """Extract standard 32-char UUID or 8-4-4-4-12 UUID from Notion URL or ID string."""
    clean = raw_id_or_url.split("?")[0].split("#")[0].strip()
    match = re.search(r"([0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", clean)
    if match:
        s = match.group(1).replace("-", "")
        return f"{s[:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:]}"
    return raw_id_or_url


async def provision_second_brain(page_id_or_url: str, api_key: str | None = None) -> dict[str, str]:
    token = api_key or config.NOTION_API_KEY
    if not token:
        raise ValueError("Notion API token not provided and not found in config.")

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    parent_page_id = clean_page_id(page_id_or_url)
    logger.info("Using Parent Page ID: %s", parent_page_id)

    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers, timeout=20.0) as client:
        # 1. Verify Parent Page Access
        page_resp = await client.get(f"/pages/{parent_page_id}")
        if page_resp.status_code != 200:
            logger.error("Cannot access parent page %s: %s %s", parent_page_id, page_resp.status_code, page_resp.text)
            raise RuntimeError(f"Cannot access parent page: {page_resp.status_code} - {page_resp.text}")
        logger.info("Parent page access verified successfully!")

        db_ids: dict[str, str] = {}

        # 2. Create Projects Database
        logger.info("Creating Projects Database...")
        projects_payload = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": "🗂️ Проекты (Projects)"}}],
            "properties": {
                "Name": {"title": {}},
                "Area": {
                    "select": {
                        "options": [
                            {"name": "🏛️ ГУАП", "color": "blue"},
                            {"name": "🔬 Тидекс", "color": "purple"},
                            {"name": "🤖 AI & Dev", "color": "green"},
                            {"name": "📚 Наука", "color": "orange"},
                            {"name": "🏠 Личное", "color": "pink"},
                        ]
                    }
                },
                "Status": {
                    "status": {
                        "options": [
                            {"name": "В работе", "color": "green"},
                            {"name": "На паузе", "color": "yellow"},
                            {"name": "Завершен", "color": "gray"},
                        ]
                    }
                },
                "Target Date": {"date": {}},
                "Key Result": {"rich_text": {}},
            },
        }
        resp = await client.post("/databases", json=projects_payload)
        resp.raise_for_status()
        projects_db = resp.json()
        db_ids["NOTION_PROJECTS_DB_ID"] = projects_db["id"]
        logger.info("Projects DB created: %s", projects_db["id"])

        # 3. Create Tasks Database
        logger.info("Creating Tasks Database...")
        tasks_payload = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": "📋 Задачи (Tasks)"}}],
            "properties": {
                "Task": {"title": {}},
                "Status": {
                    "status": {
                        "options": [
                            {"name": "To Do", "color": "default"},
                            {"name": "In Progress", "color": "blue"},
                            {"name": "Done", "color": "green"},
                        ]
                    }
                },
                "Priority": {
                    "select": {
                        "options": [
                            {"name": "P1", "color": "red"},
                            {"name": "P2", "color": "yellow"},
                            {"name": "P3", "color": "gray"},
                        ]
                    }
                },
                "Area": {
                    "select": {
                        "options": [
                            {"name": "🏛️ ГУАП", "color": "blue"},
                            {"name": "🔬 Тидекс", "color": "purple"},
                            {"name": "🤖 AI & Dev", "color": "green"},
                            {"name": "📚 Наука", "color": "orange"},
                            {"name": "🏠 Личное", "color": "pink"},
                        ]
                    }
                },
                "Due Date": {"date": {}},
                "Estimated Minutes": {"number": {"format": "number"}},
                "Project": {
                    "relation": {
                        "database_id": projects_db["id"],
                        "single_property": {},
                    }
                },
            },
        }
        resp = await client.post("/databases", json=tasks_payload)
        resp.raise_for_status()
        tasks_db = resp.json()
        db_ids["NOTION_TASKS_DB_ID"] = tasks_db["id"]
        logger.info("Tasks DB created: %s", tasks_db["id"])

        # 4. Create Waiting For / Reminders Database
        logger.info("Creating Waiting For Database...")
        waiting_payload = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": "⏰ На контроле (Waiting For)"}}],
            "properties": {
                "What": {"title": {}},
                "Person": {"rich_text": {}},
                "Check Date": {"date": {}},
                "Status": {
                    "status": {
                        "options": [
                            {"name": "Активно", "color": "blue"},
                            {"name": "Выполнено", "color": "green"},
                        ]
                    }
                },
                "Context": {"rich_text": {}},
            },
        }
        resp = await client.post("/databases", json=waiting_payload)
        resp.raise_for_status()
        waiting_db = resp.json()
        db_ids["NOTION_WAITING_DB_ID"] = waiting_db["id"]
        logger.info("Waiting For DB created: %s", waiting_db["id"])

        # 5. Create Daily Journal Database
        logger.info("Creating Daily Journal Database...")
        journal_payload = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": "📓 Ежедневный журнал (Daily Journal)"}}],
            "properties": {
                "Date": {"title": {}},
                "Done Summary": {"rich_text": {}},
                "Key Insights": {"rich_text": {}},
                "Raw Transcript": {"rich_text": {}},
            },
        }
        resp = await client.post("/databases", json=journal_payload)
        resp.raise_for_status()
        journal_db = resp.json()
        db_ids["NOTION_JOURNAL_DB_ID"] = journal_db["id"]
        logger.info("Journal DB created: %s", journal_db["id"])

        # 6. Seed starter projects
        logger.info("Seeding starter projects into Notion...")
        starter_projects = [
            {"name": "🏛️ Кафедра физики ГУАП (Осенний семестр 2026)", "area": "🏛️ ГУАП"},
            {"name": "🔬 Оптические приборы и измерения (ООО Тидекс)", "area": "🔬 Тидекс"},
            {"name": "🤖 AI Assistant & Antigravity Studio", "area": "🤖 AI & Dev"},
            {"name": "📚 Исследования и научные публикации", "area": "📚 Наука"},
        ]
        created_project_ids = {}
        for p in starter_projects:
            p_resp = await client.post(
                "/pages",
                json={
                    "parent": {"database_id": projects_db["id"]},
                    "properties": {
                        "Name": {"title": [{"text": {"content": p["name"]}}]},
                        "Area": {"select": {"name": p["area"]}},
                        "Status": {"status": {"name": "В работе"}},
                    },
                },
            )
            if p_resp.status_code == 200:
                created_project_ids[p["area"]] = p_resp.json()["id"]

        # 7. Seed starter tasks
        logger.info("Seeding starter tasks into Notion...")
        starter_tasks = [
            {
                "title": "Подготовка к занятиям в среду: Гастелло 15, ауд. 31-04а и 32-03 (ФОНТ и Физика)",
                "priority": "P1",
                "area": "🏛️ ГУАП",
                "due": "2026-09-30",
            },
            {
                "title": "Проверка домашних заданий (Паспорт проекта) групп м631к и м531 к 03.10",
                "priority": "P2",
                "area": "🏛️ ГУАП",
                "due": "2026-10-03",
            },
            {
                "title": "Провести онлайн-защиту лабораторных работ в Телемосте со Светланой Парфировой",
                "priority": "P1",
                "area": "🏛️ ГУАП",
                "due": "2026-10-02",
            },
        ]
        for t in starter_tasks:
            t_props: dict[str, Any] = {
                "Task": {"title": [{"text": {"content": t["title"]}}]},
                "Priority": {"select": {"name": t["priority"]}},
                "Area": {"select": {"name": t["area"]}},
                "Status": {"status": {"name": "To Do"}},
                "Due Date": {"date": {"start": t["due"]}},
            }
            if t["area"] in created_project_ids:
                t_props["Project"] = {"relation": [{"id": created_project_ids[t["area"]]}]}
            await client.post(
                "/pages",
                json={"parent": {"database_id": tasks_db["id"]}, "properties": t_props},
            )

        # 8. Seed reminder
        logger.info("Seeding reminder into Notion...")
        await client.post(
            "/pages",
            json={
                "parent": {"database_id": waiting_db["id"]},
                "properties": {
                    "What": {"title": [{"text": {"content": "Назначить дату онлайн-защиты лабораторных в Телемосте и отправить ссылку"}}]},
                    "Person": {"rich_text": [{"text": {"content": "Светлана Парфирова (гр. м651ксв)"}}]},
                    "Check Date": {"date": {"start": "2026-10-02"}},
                    "Status": {"status": {"name": "Активно"}},
                    "Context": {"rich_text": [{"text": {"content": "Студентка очно-заочной формы, проживает в другом городе"}}]},
                },
            },
        )

        logger.info("Provisioning completed successfully!")
        return db_ids


def update_env_file(db_ids: dict[str, str], env_path: str = "/opt/assistant-core/.env") -> None:
    with open(env_path, "r", encoding="utf-8") as f:
        content = f.read()

    for key, val in db_ids.items():
        if key in content:
            content = re.sub(rf"^{key}=.*$", f"{key}={val}", content, flags=re.MULTILINE)
        else:
            content += f"\n{key}={val}"

    with open(env_path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("Updated %s with database IDs.", env_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Provision Notion Second Brain databases")
    parser.add_argument("page_id", help="Notion Parent Page ID or full Page URL")
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    res = loop.run_until_complete(provision_second_brain(args.page_id))
    update_env_file(res)
    print("\nSUCCESS! Configured databases:")
    for k, v in res.items():
        print(f"  {k}: {v}")
