# ROADMAP.md: Архитектура базы данных и этапы эволюции системы

## 1. Схема локальной базы данных (SQLite / SQLAlchemy Async)

Локальная база (`assistant.db`) служит оперативным кешем, хранилищем снапшотов и реестром состояний для оффлайн-устойчивости:

```sql
CREATE TABLE monitored_sources (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    display_name TEXT NOT NULL,
    config_json TEXT NOT NULL,
    last_checked_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE content_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL REFERENCES monitored_sources(id),
    content_hash TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE calendar_sync_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_event_id TEXT NOT NULL UNIQUE,
    google_event_id TEXT NOT NULL UNIQUE,
    calendar_id TEXT NOT NULL,
    event_start TIMESTAMP NOT NULL,
    event_end TIMESTAMP NOT NULL,
    summary TEXT NOT NULL,
    last_synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'active'
);

CREATE TABLE action_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    priority_score INTEGER NOT NULL,
    summary_text TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE notion_sync_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,              -- 'task', 'project', 'waiting_for', 'journal'
    local_id TEXT,
    notion_page_id TEXT NOT NULL UNIQUE,
    last_synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 2. Фазы развития системы

### Фаза 1: Часовой расписания и времени (Schedule Sentinel) — [✅ Реализовано]
- Парсинг `guap.ru/rasp` (преподаватель ID `2903`).
- Сравнение слепков расписания, детекция изменений (аудитории, отмены, переносы).
- Идемпотентная синхронизация с Google Calendar без дубликатов.
- Telegram-нотификации об изменениях расписания.

### Фаза 2: Информационный щит и STT (Telegram Triage & Speech Engine) — [✅ Реализовано]
- Автономный двухконтурный STT-пайплайн: Groq Whisper (`whisper-large-v3-turbo`) + локальный `faster-whisper` (int8 CPU).
- Прием голосовых сообщений и файлов (документы, аудиозаписи) в Telegram-боте.
- Интеллектуальный фильтр спама в студенческих и кафедральных чатах.

### Фаза 3: Второй мозг и Голосовой секретарь в Notion (Voice-First Second Brain) — [⏳ В разработке]
- **3.1 Notion API Connector:** Интеграция с базами `Projects`, `Tasks`, `People & Waiting`, `Daily Journal`.
- **3.2 Вечерняя рефлексия (Voice Debrief):** 3-минутный вечерний войс -> закрытие задач в Notion, постановка новых, запись в дневник.
- **3.3 Утренний фокус-дайджест:** Расписание ГУАП + Google Calendar + Топ-3 приоритетные задачи из Notion (P1) + мелкие поручения.
- **3.4 Разбор созвонов и встреч:** Транскрибация аудиозаписей, формирование протоколов и матриц поручений по участникам.
- **3.5 Контекстные запросы:** Мгновенные подсказки перед встречами (*«Что обсудить с X?»*).

### Фаза 4: Мультиагентность и автономный секретарь (Autonomous Chief of Staff)
- Право черновика: подготовка проектов ответов на письма и сообщения.
- Согласование внешних действий через интерактивные inline-кнопки в Telegram.
- Веб-кабинет (`chat-app`): канбан проектов, интерактивный диалог, управление правилами агента.
