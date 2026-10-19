---
phase: 03-vladenie-shemoy-bd
plan: 02
subsystem: database
tags: [assistant-core, db, init_db, migrations, inline-ddl, schema-parity, sch-01, dat-01]

requires:
  - phase: 03-vladenie-shemoy-bd
    plan: 01
    provides: "миграция 0003 в assistant-shared и согласование chat-app"
provides:
  - "src/storage/db.py: Database._apply_migrations в отдельном потоке (asyncio.to_thread), общий хвост init_db, полное удаление инлайн-DDL"
  - "tests/test_init_db_migrations.py: тесты неблокирующей инициализации, потока миграции, fail-closed и идемпотентности"
  - "tests/test_no_inline_ddl.py: статический сканер DDL без белого списка по всему src/ (75 файлов) с самопроверкой"
  - "tests/test_schema_parity.py: паритет схемы трёх источников (85 элементов), эталон прежнего DDL, контроль чувствительности"
affects: [03-03, 03-04, 03-05, 03-06, assistant-core]

actuals:
  tokens: 36000
  tasks: 3
  commits: 1
plan_head_before: 833514f
plan_head_after: 833514f

tech-stack:
  added: []
  patterns:
    - "В Database ровно один вызов run_migrations, выполняемый через asyncio.to_thread(run_migrations, target)"
    - "В src/ полностью отсутствуют операторы DDL; схема принадлежит исключительно миграциям assistant-shared"
    - "Паритет схемы (sqlite_master) трёх источников проверяется автоматическим тестом (85 объектов: таблицы, индексы, триггеры, FTS)"

key-files:
  created:
    - tests/test_init_db_migrations.py
    - tests/test_no_inline_ddl.py
    - tests/test_schema_parity.py
    - .planning/phases/03-vladenie-shemoy-bd/03-02-SUMMARY.md
  modified:
    - src/storage/db.py

key-decisions:
  - "D-01 / SCH-01: Database._apply_migrations вынесен как единственный неблокирующий путь применения миграций для файловой БД и :memory:"
  - "D-02 / DAT-01: удалены все инлайн-операторы создания трёх таблиц бота из обоих веток init_db; сидирование вынесено в общий хвост"
  - "D-03: ветка :memory: сохранена без изменений для тестов; мигратор сам распаковывает соединение aiosqlite"
  - "D-11: сканер find_inline_ddl не имеет белого списка или исключений; docstrings и комментарии не исключаются"
  - "D-10 / D-04: схема трёх источников (85 элементов) проверена на точное совпадение с эталоном прежнего DDL"

patterns-established:
  - "Защита от расщепления владения схемой: сканер DDL в src/ и тест паритета sqlite_master входят в обязательный гейт"

requirements-completed: [SCH-01, DAT-01]

coverage:
  - id: D1
    description: "Единый неблокирующий путь миграций и отсутствие инлайн-DDL в db.py"
    requirement: SCH-01
    verification:
      - kind: unit
        ref: "assistant-core tests/test_init_db_migrations.py (12 passed)"
        status: pass
      - kind: unit
        ref: "assistant-core tests/test_no_inline_ddl.py (13 passed, 75 files scanned)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Паритет схемы трёх источников и совпадение с эталоном прежнего DDL"
    requirement: DAT-01
    verification:
      - kind: unit
        ref: "assistant-core tests/test_schema_parity.py (5 passed, 85 elements)"
        status: pass
    human_judgment: false
---

# Итоги плана 03-02: Единый неблокирующий путь миграций и удаление инлайн-DDL

## 1. Task 1: Единый путь миграций в Database (SCH-01, DAT-01, D-01, D-12)

- **Красное состояние до правки `db.py` (RED):**
  Создан `tests/test_init_db_migrations.py` (12 тестов). Прогон до модификации `src/storage/db.py` зафиксировал:
  `3 failed, 9 passed in 13.38s`
  - `FAILED test_migration_runs_off_the_event_loop_thread[memory]` (миграция выполнялась в потоке цикла событий)
  - `FAILED test_event_loop_keeps_ticking_during_migration[memory]` (цикл событий блокировался синхронным вызовом)
  - `FAILED test_single_run_migrations_call_site` (обнаружено 2 обращения к `run_migrations` вместо 1)
- **Реализация (GREEN):**
  - В класс `Database` добавлен приватный метод `_apply_migrations`: для `:memory:` целью служит соединение `aiosqlite`, для файла — `self.db_path`; единственный вызов `await asyncio.to_thread(run_migrations, target)`.
  - Метод `init_db` переписан в компактную форму: `await self._apply_migrations()` и общий хвост `async with self.connection() as conn: await self._seed_initial_data_if_empty(conn)`.
  - Удалены все дублированные блоки создания трёх таблиц (`bot_command_settings`, `bot_custom_aliases`, `dialog_feedback_log`).
- **Итог проверки:**
  Все 12 тестов `test_init_db_migrations.py` пройдены (`12 passed in 1.97s`).
  Регрессионный набор смежных потребителей (40 тестов) пройден (`40 passed in 42.04s`).

## 2. Task 2: Защитный тест «в src/ нет инлайн-DDL» (D-11)

- Создан `tests/test_no_inline_ddl.py`.
- Функция `find_inline_ddl(root)` не имеет параметров белого списка или исключений по путям (проверено через `inspect.signature`).
- Сканер просмотрел 75 файлов реального каталога `src/` (требование >= 50 выполнено) и дал 0 находок.
- Самопроверка чувствительности на 10 синтетических вариантах DDL (`CREATE TABLE`, строчные буквы, `UNIQUE INDEX`, `VIRTUAL TABLE`, `TRIGGER`, `TEMP TABLE`, `ALTER TABLE`, переносы строк и табуляции, строковые литералы Python) подтвердила 100% обнаружение.
- Проза («Create all tables») и файлы внутри `__pycache__` ложных срабатываний не дают.
- Итог: `13 passed in 0.16s`.

## 3. Task 3: Паритет схемы трёх источников (D-10, D-04)

- Создан `tests/test_schema_parity.py`.
- Проверен паритет множества `(type, name, normalized_sql)` из `sqlite_master` между:
  1. `:memory:` после `init_db`.
  2. Файловой БД после `init_db`.
  3. Чистой БД после `run_migrations` из `assistant-shared`.
- Все 3 источника имеют идентичную схему из 85 объектов (таблицы, индексы, триггеры, виртуальные таблицы FTS).
- Списки версий `schema_migrations` совпадают во всех источниках и каталоге `*.sql`.
- Структура и нормализованный SQL трёх таблиц 0003 посимвольно совпадают с независимым эталоном `LEGACY_BOT_UI_DDL`.
- Контроль чувствительности: усечённый каталог без `0003` выявил различие ровно в трёх таблицах бота.
- Идемпотентность: повторный `init_db` не меняет схему.
- Итог: `5 passed in 1.15s`.

## 4. Результаты полного регрессионного прогона двух репозиториев

- **`assistant-core`:** `1007 passed, 35 warnings in 134.27s (0:02:14)` (100% зелёный, страж боевой БД активен).
- **`assistant-shared`:** `202 passed in 50.01s` (100% зелёный, репозиторий не модифицировался).
- Боевая база данных `data/assistant.db` не затрагивалась.
- Сервис `assistant-worker.service` не перезапускался.
