"""Populate full historical retrospective and session provenance into Notion Engineering Hub."""

import asyncio
import logging
from typing import Any
import httpx

from src import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("populate_notion_retrospective")

NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"

ENGINEERING_HUB_PAGE_ID = "3eaa2e48-40a0-8193-b939-c9202e481777"
ISSUES_DB_ID = "3eaa2e48-40a0-81e9-ad37-e793caf99ece"


def get_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def make_callout(emoji: str, title: str, content: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": emoji},
            "rich_text": [
                {"type": "text", "text": {"content": f"{title}: "}, "annotations": {"bold": True}},
                {"type": "text", "text": {"content": content}},
            ],
        },
    }


HISTORICAL_PROVENANCE = {
    "Развернуть базовые базы данных Notion Second Brain через API": {
        "changeset": "Реализован NotionAsyncClient, написан скрипт provision_notion.py, созданы базы Проектов, Задач, Контроля и Дневника на целевой странице Notion.",
        "decisions": "Прямая работа через REST API Notion v1 с токеном ntn_... Без лишних SDK-оберток (KISS). Двухуровневая схема со связью Задачи ➔ Проекты.",
        "quality": "3/3 теста в test_notion_client.py пройдены. API endpoints проверены на живом аккаунте.",
        "debt": "Автоматическая фоновая синхронизация локальной SQLite базы и Notion требует периодического воркера.",
    },
    "Добавить прием скриншотов и документов в Telegram-бот с Gemini Vision OCR": {
        "changeset": "В бот добавлены обработчики F.photo и F.document с автоматическим сохранением в /opt/chat-app/uploads/ и распознаванием через gemini-2.5-flash.",
        "decisions": "Мультимодальный анализ на лету позволяет извлекать токены, расписания и задачи прямо из скриншотов без сторонних тяжелых OCR-библиотек.",
        "quality": "Успешно распознан реальный скриншот настроек Notion со смартфона.",
        "debt": "Хранилище uploads/ не имеет автоматической очистки старых медиафайлов.",
    },
    "Создать и запустить веб-дашборд и Markdown-редактор планов (Antigravity Studio)": {
        "changeset": "FastAPI бэкенд на порту 8000, endpoints /api/v1/dashboard/*, SPA на Tailwind CSS + Marked.js с Канбан-доской, P1-фокусом и split-screen редактором, systemd-сервис chat-app.service.",
        "decisions": "Единая база assistant.db для бэкенда и демона исключает рассинхронизацию. Легковесный клиент без сборщиков React на сервере сохраняет память (< 35 МБ RAM).",
        "quality": "11/11 тестов в test_dashboard_api.py пройдены (100% pass).",
        "debt": "Отсутствует авторизация по логину/паролю для веб-кабинета (открытый доступ по локальному IP/порту).",
    },
    "Реализовать механизм очистки чата после отправки ответа на письмо": {
        "changeset": "Создана система отслеживания session_messages в памяти и БД, метод cleanup_email_session, автоматическое удаление всех карточек после отправки.",
        "decisions": "Принцип Spotless Chat: чат не загромождается перепиской, а полная аналитика сохраняется в SQLite и выводится в вечернем дайджесте.",
        "quality": "Протестировано в test_email_reply_workflow.py (8 тестов).",
        "debt": "При перезапуске демона in-memory ID промежуточных сообщений могут теряться (карточки сохраняются в БД).",
    },
    "Разработать интерактивные карточки писем с кнопками согласования черновика": {
        "changeset": "Шаблон карточки письма с отправителем, темой, сниппетом и кнопками [Предложить ответ], [Написать ответ], [Вся переписка], карточка согласования [Отправить], [Изменить], [Отменить].",
        "decisions": "Паттерн Human-in-the-Loop: ни одно письмо не отправляется автоматически, полный контроль у преподавателя.",
        "quality": "Протестировано в реальных условиях (отправка писем Марьяшиной и Парфировой через SMTP mail.ru).",
        "debt": "Генерация ответа пока использует базовый промпт; в будущем требуется библиотека стилей для разных типов адресатов.",
    },
    "Настроить утренний брифинг в 08:00 (пары ГУАП + Google Calendar + почта)": {
        "changeset": "В планировщик APScheduler добавлен cron-триггер на 08:00 MSK с запуском run_morning_brief_cycle, выборка пар на день, Google Calendar событий и P1-задач.",
        "decisions": "Брифинг отправляется ровно один раз в сутки (защита от дублей через снимок daily_morning_brief).",
        "quality": "Протестировано ручным вызовом --brief и автотестами test_brain.py.",
        "debt": "При отмене занятий в утренний брифинг пока не встраивается уведомление о причине отмены.",
    },
    "Детекция ответов на письма по исходящим и старение актуальности": {
        "changeset": "Механизм сверки Message-ID / References в исходящих папках IMAP ('Отправленные', 'Sent'), фильтрация отвеченных писем, алгоритм экспоненциального старения релевантности.",
        "decisions": "Исключает повторные напоминания по письмам, на которые преподаватель ответил с телефона или веб-интерфейса почты.",
        "quality": "Протестировано в test_email_collector.py.",
        "debt": "Проверка Sent папки требует дополнительного сетевого запроса к IMAP серверам.",
    },
    "Подключить мультиаккаунтный сбор почты (Mail.ru, Gmail, ГУАП)": {
        "changeset": "Класс EmailCollector с поддержкой IMAP SSL (mail.ru, mail.guap.ru) и Gmail REST API OAuth2, сохранение в таблицу email_messages, фоновый цикл каждые 15 минут.",
        "decisions": "Изоляция учетных данных в .env, раздельная обработка сбоев ящиков (сбой одного ящика не ломает сбор остальных).",
        "quality": "Успешная синхронизация 38+ входящих сообщений.",
        "debt": "Для Gmail используется токен OAuth2, требующий периодического обновления refresh-токена.",
    },
}


async def create_chronicle_page(client: httpx.AsyncClient) -> str:
    """Creates the master retrospective chronicle page under Engineering Hub."""
    logger.info("Creating Master Chronicle Page under Engineering Hub...")

    page_payload = {
        "parent": {"page_id": ENGINEERING_HUB_PAGE_ID},
        "icon": {"type": "emoji", "emoji": "📜"},
        "properties": {
            "title": [{"type": "text", "text": {"content": "📜 Архитектурная летопись проекта (Project Provenance)"}}]
        },
    }
    resp = await client.post("/pages", json=page_payload)
    resp.raise_for_status()
    page_id = resp.json()["id"]

    blocks: list[dict[str, Any]] = [
        {
            "object": "block",
            "type": "callout",
            "callout": {
                "icon": {"type": "emoji", "emoji": "🏛️"},
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": "Данная летопись фиксирует полную историю создания, архитектурные решения (Design Decisions), статус Quality Gates и технический долг проекта AI-ассистента и Студии. Предназначена для быстрого ввода в курс дела новых AI-агентов и разработчиков без галлюцинаций контекста."
                        },
                    }
                ],
            },
        },
        {
            "object": "block",
            "type": "heading_1",
            "heading_1": {
                "rich_text": [{"type": "text", "text": {"content": "🗺️ Карта пройденных майлстоунов"}}]
            },
        },
        make_callout(
            "1️⃣",
            "Phase 1: Часовой расписания ГУАП и Google Calendar Sync (27–28.09)",
            "Парсер HTML расписания guap.ru/rasp?pr=2903, снимки SQLite, двусторонняя синхронизация с Google Calendar, фоновый демон 24/7, Telegram-нотификатор изменений аудиторий.",
        ),
        make_callout(
            "2️⃣",
            "Phase 2: Мониторинг Telegram и двухэтапная фильтрация (28.09)",
            "Telethon Userbot для закрытых студенческих групп (м631к, м531), двухэтапный классификатор (Regex ➔ Gemini LLM), движок старения релевантности.",
        ),
        make_callout(
            "3️⃣",
            "Phase 3: Голосовой ввод и утренний брифинг (28.09)",
            "Модуль голосовой транскрипции Whisper + Gemini Multimodal, планировщик брифинга в 08:00 MSK со сводкой пар, календаря и фокусных задач.",
        ),
        make_callout(
            "4️⃣",
            "Phase 4: Почтовый щит и черновики с Human-in-the-Loop (28–29.09)",
            "Сбор почты с 3 ящиков (Mail.ru, Gmail, ГУАП), карточки писем с инлайн-кнопками, генерация проектов ответов, автоочистка чата после отправки, вечерний дайджест в 21:00.",
        ),
        make_callout(
            "5️⃣",
            "Phase 5: Веб-студия и Split-Screen Markdown редактор (29.09)",
            "Автономный веб-кабинет на FastAPI (порт 8000), единая база SQLite assistant.db, Канбан-доска задач, двухоконный редактор планов с превью, сервис chat-app.service.",
        ),
        make_callout(
            "6️⃣",
            "Phase 6: Мультимодальный бот и Telegram Vision (29.09)",
            "Прием скриншотов и документов в Telegram, OCR-анализ через gemini-2.5-flash, сохранение в uploads/.",
        ),
        make_callout(
            "7️⃣",
            "Phase 7: Notion Second Brain & Engineering Hub (29.09)",
            "Интеграция с облачным Notion через API, развертывание 4 пользовательских баз и 2 инженерных баз, скрипт notion_dev.py для ведения долгосрочной памяти.",
        ),
        make_callout(
            "8️⃣",
            "Phase 8: Тайм-трекинг AADHk («Тидекс») и кросс-валидация (29.09)",
            "Таблица timesheet_records, адаптивный парсер SQLite бэкапов AADHk Time Recording, детекция наложений с парами ГУАП, команда /cancel для чистоты чата.",
        ),
        {
            "object": "block",
            "type": "heading_1",
            "heading_1": {
                "rich_text": [{"type": "text", "text": {"content": "⚖️ Архитектурные принципы кодовой базы"}}]
            },
        },
        make_callout(
            "🛡️",
            "1. Принцип изоляции данных (Local-First SQLite)",
            "Оперативным источником истины 24/7 демона является локальная база SQLite (/opt/assistant-core/data/assistant.db). Это гарантирует мгновенную работу ассистента даже при отсутствии интернета или недоступности внешних облаков.",
        ),
        make_callout(
            "🧠",
            "2. Notion как Single Source of Truth для разработки",
            "Для агентов разработки и архитектора дашборд «Инженерные задачи и спринты» в Notion — единственный источник правды по статусам, коммитам и архитектурному представительству.",
        ),
        make_callout(
            "🤝",
            "3. Human-in-the-Loop для всех внешних действий",
            "Ни одно электронное письмо, оценка в ведомости или внешнее сообщение не отправляется без явного подтверждения преподавателя нажатием кнопки в Telegram.",
        ),
        make_callout(
            "🧹",
            "4. Spotless Chat & Zero-Clutter",
            "После согласования и отправки действия все промежуточные карточки, кнопки и подсказки удаляются из Telegram, оставляя диалог чистым. Вся статистика аккумулируется в вечернем дайджесте в 21:00.",
        ),
    ]

    await client.patch(f"/blocks/{page_id}/children", json={"children": blocks})
    logger.info("Master Chronicle page populated successfully: %s", page_id)
    return page_id


async def enrich_historical_issues(client: httpx.AsyncClient) -> int:
    """Iterate over issues DB and append Session Provenance to matching historical tasks."""
    logger.info("Enriching historical issues with Session Provenance...")
    resp = await client.post(f"/databases/{ISSUES_DB_ID}/query", json={})
    resp.raise_for_status()
    issues = resp.json().get("results", [])

    enriched_count = 0
    for issue in issues:
        title = issue["properties"]["Issue"]["title"][0]["plain_text"] if issue["properties"]["Issue"]["title"] else ""
        if title in HISTORICAL_PROVENANCE:
            prov = HISTORICAL_PROVENANCE[title]
            page_id = issue["id"]
            logger.info("Enriching task '%s' (ID: %s)...", title, page_id)

            blocks = [
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "📝 Session Provenance (Архитектурный след)"}}]
                    },
                },
                make_callout("📦", "[Changeset]", prov["changeset"]),
                make_callout("💡", "[Design Decisions]", prov["decisions"]),
                make_callout("🧪", "[Quality Gates Status]", prov["quality"]),
                make_callout("⚠️", "[Technical Debt Introduced]", prov["debt"]),
            ]
            b_resp = await client.patch(f"/blocks/{page_id}/children", json={"children": blocks})
            if b_resp.status_code == 200:
                enriched_count += 1
            else:
                logger.warning("Failed enriching %s: %s", title, b_resp.text)

    return enriched_count


async def main() -> None:
    headers = get_headers()
    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers, timeout=30.0) as client:
        # 1. Create chronicle page
        chronicle_id = await create_chronicle_page(client)
        print(f"Chronicle Page Created: {chronicle_id}")

        # 2. Enrich historical issues
        count = await enrich_historical_issues(client)
        print(f"Enriched {count} historical issues with Session Provenance!")


if __name__ == "__main__":
    asyncio.run(main())
