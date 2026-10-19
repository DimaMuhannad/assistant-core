---
phase: 03-vladenie-shemoy-bd
plan: 01
subsystem: database
tags: [assistant-shared, chat-app, migrations, 0003, bot-tables, dat-01, sch-02]

requires:
  - phase: 02-bezopasnost-privatnost-i-nahodki-revyu
    provides: "стабилизированный рантайм, изоляция тестов"
provides:
  - "/opt/assistant-shared/assistant_shared/db/migrations/0003_bot_commands_and_feedback.sql: миграция 0003 для трёх таблиц бота"
  - "/opt/assistant-shared/tests/test_migrations.py: тесты соответствия прежнему DDL, no-op на существующих данных, фиксация имени и структуры"
  - "/opt/chat-app/backend/tests/test_migrations.py: динамический вывод миграций из каталога, расширение EXPECTED_CORE_TABLES, статический запрет собственного DDL"
  - ".planning/phases/03-vladenie-shemoy-bd/03-CHATAPP-QUICK-BRIEF.md: задание на согласование потребителя"
affects: [03-02, 03-03, 03-04, 03-05, 03-06, assistant-shared, chat-app]

actuals:
  tokens: 28500
  tasks: 3
  commits: 2
plan_head_before: 5bce99c
plan_head_after: 5bce99c

tech-stack:
  added: []
  patterns:
    - "Схема трёх таблиц бота полностью принадлежит миграциям assistant-shared (CREATE TABLE IF NOT EXISTS, точная копия прежнего инлайн-DDL)"
    - "Потребитель chat-app выводит список миграций динамически из каталога *.sql библиотеки (MIGRATIONS_DIR) и проверяет отсутствие собственного DDL в коде"

key-files:
  created:
    - /opt/assistant-shared/assistant_shared/db/migrations/0003_bot_commands_and_feedback.sql
    - .planning/phases/03-vladenie-shemoy-bd/03-CHATAPP-QUICK-BRIEF.md
    - .planning/phases/03-vladenie-shemoy-bd/03-01-SUMMARY.md
  modified:
    - /opt/assistant-shared/tests/test_migrations.py
    - /opt/chat-app/backend/tests/test_migrations.py

key-decisions:
  - "D-04 / DAT-01: миграция 0003 создана как точная копия прежнего инлайн-DDL без индексов, CHECK, триггеров и смены DEFAULT"
  - "D-07 / D-08 / SCH-02: согласование chat-app выполнено в том же проходе с гарантией коммита chat-app строго ДО коммита 0003 в assistant-shared"
  - "chat-app.service не перезапускался"

patterns-established:
  - "Потребители общей библиотеки не зашивают литералы версий миграций, а выводят их из MIGRATIONS_DIR"

requirements-completed: [DAT-01, SCH-02]

coverage:
  - id: D1
    description: "0003_bot_commands_and_feedback.sql точная копия прежнего DDL и no-op на БД с данными"
    requirement: DAT-01
    verification:
      - kind: unit
        ref: "assistant-shared tests/test_migrations.py (test_0003_tables_match_legacy_inline_ddl, test_0003_is_create_if_not_exists_only, test_0003_noop_on_legacy_db_with_existing_data)"
        status: pass
    human_judgment: false
  - id: D2
    description: "chat-app получает таблицы через общий мигратор, сам их не создаёт, тесты 100% зелёные"
    requirement: SCH-02
    verification:
      - kind: unit
        ref: "chat-app backend/tests/test_migrations.py (test_bot_tables_schema_columns, test_chat_app_does_not_create_shared_schema_tables, test_initial_schema_creates_all_tables)"
        status: pass
    human_judgment: false
---

# Итоги плана 03-01: Миграция 0003 и согласование потребителя chat-app

## 1. Task 1: Миграция 0003 и TDD-тесты в assistant-shared (DAT-01, D-04)

- **Шаг RED:** В `tests/test_migrations.py` добавлены константа `MIGRATION_0003 = "0003_bot_commands_and_feedback"`, кортеж `BOT_UI_TABLES`, эталон `LEGACY_BOT_UI_DDL`, включение в `EXPECTED_CORE_TABLES` и пять специализированных тестов. Прогон pytest зафиксировал ожидаемое красное состояние до создания файла миграции:
  `6 failed, 13 passed in 18.71s` (упали `test_initial_schema_creates_all_tables` и все пять новых тестов 0003).
- **Шаг GREEN:** Создан файл `/opt/assistant-shared/assistant_shared/db/migrations/0003_bot_commands_and_feedback.sql` с тремя операторами `CREATE TABLE IF NOT EXISTS` (`bot_command_settings`, `bot_custom_aliases`, `dialog_feedback_log`) в точном соответствии с прежним инлайн-DDL.
- Повторный запуск: все 19 тестов модуля и полный набор `assistant-shared` пройдены:
  `202 passed in 40.20s`.
- Файл `0003` оставлен в рабочем дереве незакоммиченным до согласования `chat-app` (D-07).

## 2. Task 2: Предпроверка chat-app и техническое задание (D-07, D-08)

- **Предпроверка:** Полный прогон `backend/.venv/bin/pytest backend/tests` в `/opt/chat-app` против модифицированной библиотеки зафиксировал:
  `6 failed, 271 passed, 3 warnings in 64.60s`.
  Все 6 падений относятся исключительно к одному файлу: `backend/tests/test_migrations.py`. Расхождений с допущением D-07 нет. Список и вывод сохранены в `/var/tmp/gsd-phase03-precheck/`.
- **Задание:** Создан файл `.planning/phases/03-vladenie-shemoy-bd/03-CHATAPP-QUICK-BRIEF.md` из 10 разделов с детальными требованиями согласования. Автоматические проверки структуры и отсутствие утечек NDA-строк персоны пройдены (CHECK 1, 2, 3: PASSED).

## 3. Task 3: Согласование потребителя chat-app и коммиты (SCH-02)

- В `/opt/chat-app/backend/tests/test_migrations.py`:
  - `ALL_MIGRATIONS` и `LATEST_SCHEMA_VERSION` переведены на динамический вывод из `MIGRATIONS_DIR.glob("*.sql")`.
  - `EXPECTED_CORE_TABLES` расширен тремя таблицами бота.
  - Добавлен тест структуры колонок `test_bot_tables_schema_columns`.
  - Добавлен статический тест `test_chat_app_does_not_create_shared_schema_tables` (проверка отсутствия `CREATE TABLE` в `backend/app/**/*.py`).
- **Коммит в chat-app (строго до assistant-shared):**
  - Хеш: `011f9c2`
  - Время: `2026-10-10 23:51:12 +0000`
  - Сообщение: `test(migrations): derive migration list from shared catalog, cover bot tables (SCH-02)`
  - Pre-commit hook пройден чисто (`Security Shield passed`).
- **Коммит в assistant-shared:**
  - Хеш: `5c85613`
  - Время: `2026-10-10 23:51:24 +0000`
  - Сообщение: `feat(schema): 0003 bot commands, aliases and dialog feedback tables (DAT-01, SCH-02)`
  - Pre-commit hook пройден чисто (`Security Shield passed`).
- **Порядок коммитов:**
  Коммит `chat-app` (`011f9c2`, 23:51:12) предшествует коммиту `assistant-shared` (`5c85613`, 23:51:24).

## 4. Проверочные прогоны после фиксации

- `assistant-shared` pytest: `202 passed in 26.28s`.
- `chat-app` pytest: `279 passed, 3 warnings in 91.90s`.
- Общий гейт `chat-app`: тесты `chat-app` (279) зелёные, linter зелёный, shield зелёный, боевая БД не затронута.
- Сервис `chat-app.service` не перезапускался.
