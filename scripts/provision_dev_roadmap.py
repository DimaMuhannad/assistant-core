"""Provision Engineering Hub & Dev Roadmap in Notion following developer best practices."""

import argparse
import asyncio
import logging
from typing import Any
import httpx

from src import config
from scripts.provision_notion import clean_page_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("provision_dev_roadmap")

NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"


async def setup_engineering_hub(parent_page_id_raw: str) -> dict[str, str]:
    token = config.NOTION_API_KEY
    if not token:
        raise ValueError("NOTION_API_KEY is not configured in .env")

    parent_id = clean_page_id(parent_page_id_raw)
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers, timeout=25.0) as client:
        # 1. Create Sub-Page: Engineering Hub
        logger.info("Creating 'Engineering Hub' sub-page under %s...", parent_id)
        page_payload = {
            "parent": {"page_id": parent_id},
            "icon": {"type": "emoji", "emoji": "🛠️"},
            "properties": {
                "title": [{"type": "text", "text": {"content": "🛠️ Engineering Hub · План разработки AI-Студии"}}]
            },
        }
        resp = await client.post("/pages", json=page_payload)
        resp.raise_for_status()
        hub_page = resp.json()
        hub_page_id = hub_page["id"]
        logger.info("Engineering Hub page created: %s", hub_page_id)

        # 2. Create Milestones & Epics Database
        logger.info("Creating Milestones & Epics Database...")
        milestones_payload = {
            "parent": {"type": "page_id", "page_id": hub_page_id},
            "title": [{"type": "text", "text": {"content": "🎯 Эпики и Майлстоуны (Milestones & Epics)"}}],
            "properties": {
                "Milestone": {"title": {}},
                "Phase": {
                    "select": {
                        "options": [
                            {"name": "Phase 1: Core Voice & Sentinel", "color": "blue"},
                            {"name": "Phase 2: Email Shield & Briefing", "color": "purple"},
                            {"name": "Phase 3: Notion Second Brain", "color": "green"},
                            {"name": "Phase 4: Studio Web UI & Editor", "color": "orange"},
                            {"name": "Phase 5: Telegram Vision & Media", "color": "pink"},
                            {"name": "Phase 6: AADHk Timesheets (Corporate)", "color": "yellow"},
                            {"name": "Phase 7: Omnichannel Secretary", "color": "default"},
                            {"name": "Phase 8: LMS Academic Auto-Grading", "color": "red"},
                        ]
                    }
                },
                "Status": {
                    "status": {
                        "options": [
                            {"name": "Completed", "color": "green"},
                            {"name": "In Progress", "color": "blue"},
                            {"name": "Planned", "color": "default"},
                        ]
                    }
                },
                "Stream": {
                    "select": {
                        "options": [
                            {"name": "Data Layer (Notion/DB)", "color": "blue"},
                            {"name": "Brain Engine (AI)", "color": "purple"},
                            {"name": "Delivery & Telegram UX", "color": "green"},
                            {"name": "Studio Web UI (React/FastAPI)", "color": "orange"},
                            {"name": "Domain Context (Academic/Corporate)", "color": "red"},
                        ]
                    }
                },
                "Target Version": {
                    "select": {
                        "options": [
                            {"name": "v1.0 MVP", "color": "green"},
                            {"name": "v1.1 Second Brain", "color": "blue"},
                            {"name": "v1.2 Studio IDE", "color": "orange"},
                            {"name": "v1.3 Omnichannel", "color": "purple"},
                            {"name": "v2.0 Academic LMS", "color": "red"},
                        ]
                    }
                },
                "Description": {"rich_text": {}},
            },
        }
        resp = await client.post("/databases", json=milestones_payload)
        resp.raise_for_status()
        milestones_db = resp.json()
        milestones_db_id = milestones_db["id"]
        logger.info("Milestones DB created: %s", milestones_db_id)

        # 3. Create Dev Issues & Sprint Tasks Database
        logger.info("Creating Dev Issues & Tasks Database...")
        issues_payload = {
            "parent": {"type": "page_id", "page_id": hub_page_id},
            "title": [{"type": "text", "text": {"content": "📋 Инженерные задачи и спринты (Dev Issues & Tasks)"}}],
            "properties": {
                "Issue": {"title": {}},
                "Type": {
                    "select": {
                        "options": [
                            {"name": "🚀 feat (Feature)", "color": "green"},
                            {"name": "🐛 fix (Bugfix)", "color": "red"},
                            {"name": "⚙️ infra (DevOps/Systemd)", "color": "yellow"},
                            {"name": "🧠 ai (LLM/Prompt)", "color": "purple"},
                            {"name": "📝 docs (Architecture)", "color": "blue"},
                            {"name": "🧪 test (Pytest/QA)", "color": "pink"},
                        ]
                    }
                },
                "Status": {
                    "status": {
                        "options": [
                            {"name": "Backlog", "color": "default"},
                            {"name": "Ready for Dev", "color": "yellow"},
                            {"name": "In Progress", "color": "blue"},
                            {"name": "Done", "color": "green"},
                        ]
                    }
                },
                "Priority": {
                    "select": {
                        "options": [
                            {"name": "P0 - Blocker", "color": "red"},
                            {"name": "P1 - High", "color": "orange"},
                            {"name": "P2 - Medium", "color": "yellow"},
                            {"name": "P3 - Low", "color": "gray"},
                        ]
                    }
                },
                "Module": {
                    "select": {
                        "options": [
                            {"name": "assistant-worker (Daemon)", "color": "blue"},
                            {"name": "Telegram Bot (Assistant)", "color": "green"},
                            {"name": "FastAPI & Studio Web (chat-app)", "color": "orange"},
                            {"name": "Notion API Sync", "color": "purple"},
                            {"name": "Email (IMAP/SMTP Mail.ru & Gmail)", "color": "yellow"},
                            {"name": "Schedule Sentinel & Calendar", "color": "red"},
                            {"name": "LMS Portal (Academic)", "color": "pink"},
                        ]
                    }
                },
                "Milestone": {
                    "relation": {
                        "database_id": milestones_db_id,
                        "single_property": {},
                    }
                },
                "Git Commit": {"rich_text": {}},
            },
        }
        resp = await client.post("/databases", json=issues_payload)
        resp.raise_for_status()
        issues_db = resp.json()
        issues_db_id = issues_db["id"]
        logger.info("Issues DB created: %s", issues_db_id)

        # 4. Seed Milestones (Roadmap Phases)
        logger.info("Seeding Milestones into Notion...")
        milestone_data = [
            {
                "name": "Phase 1: Сквозной цикл «Голос ➔ База задач»",
                "phase": "Phase 1: Core Voice & Sentinel",
                "status": "Completed",
                "stream": "Brain Engine (AI)",
                "version": "v1.0 MVP",
                "desc": "Распознавание голосовых сообщений Whisper + Gemini, выделение поручений и задач.",
            },
            {
                "name": "Phase 2: Почтовый щит и интерактивные черновики писем",
                "phase": "Phase 2: Email Shield & Briefing",
                "status": "Completed",
                "stream": "Delivery & Telegram UX",
                "version": "v1.0 MVP",
                "desc": "Сбор писем Mail.ru/Gmail/Университет, карточки ответов с кнопками, автоочистка чата, дайджест.",
            },
            {
                "name": "Phase 3: Облачный Notion Second Brain",
                "phase": "Phase 3: Notion Second Brain",
                "status": "Completed",
                "stream": "Data Layer (Notion/DB)",
                "version": "v1.1 Second Brain",
                "desc": "Интеграция с официальным Notion API, связанные базы Проектов, Задач, Контроля и Дневника.",
            },
            {
                "name": "Phase 4: Web Studio UI & Split-Screen Markdown Editor",
                "phase": "Phase 4: Studio Web UI & Editor",
                "status": "Completed",
                "stream": "Studio Web UI (React/FastAPI)",
                "version": "v1.2 Studio IDE",
                "desc": "Веб-дашборд на порту 8000 с Канбан-доской, P1-фокусом и двухоконным Markdown-редактором планов.",
            },
            {
                "name": "Phase 5: Мультимодальный бот (Скриншоты, файлы, Vision OCR)",
                "phase": "Phase 5: Telegram Vision & Media",
                "status": "Completed",
                "stream": "Brain Engine (AI)",
                "version": "v1.2 Studio IDE",
                "desc": "Прием скриншотов, сохранение на сервере, мультимодальный OCR через Gemini 2.5 Flash.",
            },
            {
                "name": "Phase 6: Корпоративный тайм-трекинг и разбор БД AADHk Time Recording",
                "phase": "Phase 6: AADHk Timesheets (Corporate)",
                "status": "In Progress",
                "stream": "Domain Context (Academic/Corporate)",
                "version": "v1.3 Omnichannel",
                "desc": "Импорт бэкапов SQLite AADHk, аналитика смен и рабочих часов, сопоставление с расписанием.",
            },
            {
                "name": "Phase 7: Омниканальный секретарь (WhatsApp, Max, расширенный пул Telegram)",
                "phase": "Phase 7: Omnichannel Secretary",
                "status": "Planned",
                "stream": "Delivery & Telegram UX",
                "version": "v1.3 Omnichannel",
                "desc": "Подключение Green-API (WhatsApp), корпоративного мессенджера Max и динамических учебных групп.",
            },
            {
                "name": "Phase 8: Личный кабинет преподавателя LMS и автопроверка лаб",
                "phase": "Phase 8: LMS Academic Auto-Grading",
                "status": "Planned",
                "stream": "Domain Context (Academic/Corporate)",
                "version": "v2.0 Academic LMS",
                "desc": "Парсинг сданных PDF-отчетов, проверка структуры и титульных листов через OCR, автовыставление баллов в БРС.",
            },
        ]
        created_milestone_ids: dict[str, str] = {}
        for m in milestone_data:
            m_res = await client.post(
                "/pages",
                json={
                    "parent": {"database_id": milestones_db_id},
                    "properties": {
                        "Milestone": {"title": [{"text": {"content": m["name"]}}]},
                        "Phase": {"select": {"name": m["phase"]}},
                        "Status": {"status": {"name": m["status"]}},
                        "Stream": {"select": {"name": m["stream"]}},
                        "Target Version": {"select": {"name": m["version"]}},
                        "Description": {"rich_text": [{"text": {"content": m["desc"]}}]},
                    },
                },
            )
            if m_res.status_code == 200:
                created_milestone_ids[m["phase"]] = m_res.json()["id"]

        # 5. Seed Engineering Issues (Tasks)
        logger.info("Seeding Engineering Issues into Notion...")
        issue_items = [
            # Completed Tasks
            {
                "title": "Развернуть базовые базы данных Notion Second Brain через API",
                "type": "🚀 feat (Feature)",
                "status": "Done",
                "priority": "P1 - High",
                "module": "Notion API Sync",
                "phase": "Phase 3: Notion Second Brain",
                "commit": "5ea0cda",
            },
            {
                "title": "Добавить прием скриншотов и документов в Telegram-бот с Gemini Vision OCR",
                "type": "🚀 feat (Feature)",
                "status": "Done",
                "priority": "P1 - High",
                "module": "Telegram Bot (Assistant)",
                "phase": "Phase 5: Telegram Vision & Media",
                "commit": "640562a",
            },
            {
                "title": "Создать и запустить веб-дашборд и Markdown-редактор планов (Antigravity Studio)",
                "type": "🚀 feat (Feature)",
                "status": "Done",
                "priority": "P1 - High",
                "module": "FastAPI & Studio Web (chat-app)",
                "phase": "Phase 4: Studio Web UI & Editor",
                "commit": "6dd720b",
            },
            {
                "title": "Реализовать механизм очистки чата после отправки ответа на письмо",
                "type": "🚀 feat (Feature)",
                "status": "Done",
                "priority": "P2 - Medium",
                "module": "Telegram Bot (Assistant)",
                "phase": "Phase 2: Email Shield & Briefing",
                "commit": "976e487",
            },
            {
                "title": "Разработать интерактивные карточки писем с кнопками согласования черновика",
                "type": "🚀 feat (Feature)",
                "status": "Done",
                "priority": "P1 - High",
                "module": "Telegram Bot (Assistant)",
                "phase": "Phase 2: Email Shield & Briefing",
                "commit": "d41bfe2",
            },
            {
                "title": "Настроить утренний брифинг в 08:00 (расписание + Google Calendar + почта)",
                "type": "🚀 feat (Feature)",
                "status": "Done",
                "priority": "P1 - High",
                "module": "assistant-worker (Daemon)",
                "phase": "Phase 2: Email Shield & Briefing",
                "commit": "90ba631",
            },
            {
                "title": "Детекция ответов на письма по исходящим и старение актуальности",
                "type": "🚀 feat (Feature)",
                "status": "Done",
                "priority": "P2 - Medium",
                "module": "Email (IMAP/SMTP Mail.ru & Gmail)",
                "phase": "Phase 2: Email Shield & Briefing",
                "commit": "0cb2a5b",
            },
            {
                "title": "Подключить мультиаккаунтный сбор почты (Mail.ru, Gmail, Университет)",
                "type": "🚀 feat (Feature)",
                "status": "Done",
                "priority": "P1 - High",
                "module": "Email (IMAP/SMTP Mail.ru & Gmail)",
                "phase": "Phase 2: Email Shield & Briefing",
                "commit": "23abed1",
            },
            # In Progress & Next Tasks
            {
                "title": "Разработать парсер бэкапов SQLite приложения AADHk Time Recording",
                "type": "🚀 feat (Feature)",
                "status": "In Progress",
                "priority": "P1 - High",
                "module": "assistant-worker (Daemon)",
                "phase": "Phase 6: AADHk Timesheets (Corporate)",
                "commit": "in_progress",
            },
            {
                "title": "Сопоставление отработанных часов в компании с расписанием пар без наложений",
                "type": "🚀 feat (Feature)",
                "status": "Ready for Dev",
                "priority": "P2 - Medium",
                "module": "assistant-worker (Daemon)",
                "phase": "Phase 6: AADHk Timesheets (Corporate)",
                "commit": "pending",
            },
            {
                "title": "Подключить шлюз WhatsApp через Green-API для входящих сообщений",
                "type": "🚀 feat (Feature)",
                "status": "Backlog",
                "priority": "P2 - Medium",
                "module": "Telegram Bot (Assistant)",
                "phase": "Phase 7: Omnichannel Secretary",
                "commit": "backlog",
            },
            {
                "title": "Сессионный клиент авторизации и парсинга заданий личного кабинета LMS",
                "type": "🚀 feat (Feature)",
                "status": "Backlog",
                "priority": "P1 - High",
                "module": "LMS Portal (Academic)",
                "phase": "Phase 8: LMS Academic Auto-Grading",
                "commit": "backlog",
            },
            {
                "title": "AI-пайплайн проверки структуры и титульного листа PDF-отчетов лабораторных работ",
                "type": "🧠 ai (LLM/Prompt)",
                "status": "Backlog",
                "priority": "P1 - High",
                "module": "LMS Portal (Academic)",
                "phase": "Phase 8: LMS Academic Auto-Grading",
                "commit": "backlog",
            },
        ]

        for item in issue_items:
            props: dict[str, Any] = {
                "Issue": {"title": [{"text": {"content": item["title"]}}]},
                "Type": {"select": {"name": item["type"]}},
                "Status": {"status": {"name": item["status"]}},
                "Priority": {"select": {"name": item["priority"]}},
                "Module": {"select": {"name": item["module"]}},
                "Git Commit": {"rich_text": [{"text": {"content": item["commit"]}}]},
            }
            if item["phase"] in created_milestone_ids:
                props["Milestone"] = {"relation": [{"id": created_milestone_ids[item["phase"]]}]}

            await client.post(
                "/pages",
                json={"parent": {"database_id": issues_db_id}, "properties": props},
            )

        logger.info("Engineering Hub setup completed successfully!")
        return {
            "HUB_PAGE_ID": hub_page_id,
            "MILESTONES_DB_ID": milestones_db_id,
            "ISSUES_DB_ID": issues_db_id,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Provision Engineering Hub & Dev Roadmap in Notion")
    parser.add_argument("parent_page_id", nargs="?", default="3eaa2e4840a080e98617f466a68be204", help="Parent Notion Page ID")
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    res = loop.run_until_complete(
        setup_engineering_hub(args.parent_page_id)
    )
    print("\nSUCCESS! Engineering Hub provisioned:")
    for k, v in res.items():
        print(f"  {k}: {v}")
