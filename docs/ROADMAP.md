# ROADMAP.md: Архитектура базы данных и этапы эволюции системы

## 1. Схема базы данных (SQLite / SQLAlchemy Async)

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
```

## 2. Фазы разработки
- **Фаза 1:** Часовой расписания (Schedule Sentinel)
- **Фаза 2:** Информационный щит (Telethon Userbot)
- **Фаза 3:** Секретарь с правом черновика (Inbox Zero)
- **Фаза 4:** Мультиагентность и Second Brain
