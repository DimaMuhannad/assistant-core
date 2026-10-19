# Phase 3: Владение схемой БД - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-10
**Phase:** 3-Владение схемой БД
**Areas discussed:** Ветка :memory: без блокировки, Форма миграции 0003, Порядок с chat-app, Тест паритета и защита от инлайн-DDL

---

## Ветка :memory: без блокировки

| Option | Description | Selected |
|--------|-------------|----------|
| Один хелпер, to_thread на соединении | Общий метод; путь для файла, разделяемое соединение для :memory: | ✓ |
| Общий URI в памяти | `file:...?mode=memory&cache=shared`, правка мигратора | |
| Убрать :memory: из Database | Тесты на временных файлах | |

**User's choice:** Один хелпер, to_thread на соединении
**Notes:** Остальной код init_db (сидирование) остаётся, выносится в общий хвост.

## Форма миграции 0003

| Option | Description | Selected |
|--------|-------------|----------|
| Точная копия + IF NOT EXISTS | No-op на боевой БД | ✓ |
| С индексом по message_id | Усиление схемы сверх DAT-01 | |

**User's choice:** Точная копия + IF NOT EXISTS

## Порядок с chat-app

| Option | Description | Selected |
|--------|-------------|----------|
| Один /gsd-quick в том же проходе | Нет красного pytest chat-app | ✓ |
| Сначала chat-app, потом 0003 | Две волны | |
| Сначала 0003, chat-app после | chat-app временно красный | |

**User's choice:** Один /gsd-quick в chat-app в том же проходе; тест выводит список миграций из каталога.

## Тест паритета и защита от инлайн-DDL

| Option | Description | Selected |
|--------|-------------|----------|
| sqlite_master: нормализованный sql | Таблицы, индексы, триггеры | ✓ |
| PRAGMA table_info | Только колонки | |
| Тест на исходнике + все src/ | Без белого списка | ✓ |
| Только db.py | Уже покрывает критерий | |

## Claude's Discretion

- Имя файла 0003, имя общего метода, нормализация SQL, разбиение на планы.

## Deferred Ideas

- Индекс по dialog_feedback_log(message_id) и прочие усиления схемы.
