---
phase: 03-vladenie-shemoy-bd
plan: 03
subsystem: database
tags: [assistant-core, migrations, copy-check, deploy, backup, ops, dat-01]

requires:
  - phase: 03-vladenie-shemoy-bd
    plan: 01
    provides: "миграция 0003 в assistant-shared"
provides:
  - "scripts/check_migration_on_copy.py: скрипт герметичной проверки миграций на копии БД через backup API с mode=ro"
  - "tests/test_check_migration_on_copy.py: тесты проверки на синтетическом источнике формы боевой (10 тестов)"
  - "docs/OPS_DEPLOY.md: раздел 13 «Миграции схемы при выкатке» и обновлённое положение раздела 7"
  - "tests/test_deploy_script.py: тесты 13 разделов регламента и описания выкатки"
affects: [03-04, 03-05, 03-06, assistant-core]

actuals:
  tokens: 38000
  tasks: 2
  commits: 1
plan_head_before: 5413266
plan_head_after: 5413266

tech-stack:
  added: []
  patterns:
    - "Проверка миграции выполняется исключительно на герметичной копии, созданной через backup API"
    - "Источник всегда открывается в режиме mode=ro (read-only), логический хеш источника до и после проверяется на равенство"
    - "Временный каталог копии создаётся с правами 0700 вне дерева git и всегда удаляется в finally"
    - "Содержимое строк данных никогда не выводится в журнал или консоль (только счётчики и префиксы хешей)"

key-files:
  created:
    - scripts/check_migration_on_copy.py
    - tests/test_check_migration_on_copy.py
    - .planning/phases/03-vladenie-shemoy-bd/03-03-SUMMARY.md
  modified:
    - docs/OPS_DEPLOY.md
    - tests/test_deploy_script.py

key-decisions:
  - "D-05 / DAT-01: проверка миграции на копии оформлена отдельным скриптом с обязательным аргументом --source без умолчаний на боевую БД"
  - "D-06: регламент выкатки 0003 зафиксирован в разделе 13 docs/OPS_DEPLOY.md в четыре шага; выкатка с --backup непосредственно перед рестартом"
  - "D-05: при фоновой записи сервиса (дрейф хеша) скрипт делает до --attempts повторов (по умолчанию 3), после чего выдаёт честный КРАСНЫЙ без смягчения"

patterns-established:
  - "Подготовка к боевым миграциям: предварительная верификация на герметичной копии с контролем неизменности оригинала"

requirements-completed: [DAT-01]

coverage:
  - id: D1
    description: "Проверка миграции 0003 на копии БД без изменения данных и источника"
    requirement: DAT-01
    verification:
      - kind: unit
        ref: "assistant-core tests/test_check_migration_on_copy.py (10 passed)"
        status: pass
      - kind: manual
        ref: "scripts/check_migration_on_copy.py --help (exit 0)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Регламент выкатки миграции в docs/OPS_DEPLOY.md"
    requirement: DAT-01
    verification:
      - kind: unit
        ref: "assistant-core tests/test_deploy_script.py (198 passed)"
        status: pass
    human_judgment: false
---

# Итоги плана 03-03: Проверка миграции на копии БД и регламент выкатки

## 1. Task 1: scripts/check_migration_on_copy.py и герметичные тесты (DAT-01, D-05)

- **Красное состояние до создания скрипта (RED):**
  Создан `tests/test_check_migration_on_copy.py` с 10 тестами и публичной функцией `make_legacy_source` для создания синтетического источника формы боевой БД (0001, 0002, 3 таблицы бота прежним инлайн-DDL, WAL-режим).
  Прогон зафиксировал ожидаемое красное состояние:
  `10 failed in 0.72s` (все тесты упали с `FileNotFoundError` на `scripts/check_migration_on_copy.py`).
- **Реализация (GREEN):**
  Создан `scripts/check_migration_on_copy.py`:
  - Обязательный аргумент `--source`, опциональный `--attempts` (по умолчанию 3), умолчания на боевую БД нет.
  - Импорт `deploy.make_db_copy` через `importlib` по относительному пути (без импорта `src`).
  - Все подключения к источнику строго в режиме `mode=ro` (`?mode=ro`, `uri=True`).
  - Логический хеш источника `logical_hash` вычисляется по `conn.iterdump()`.
  - Снимок структуры `snapshot` фиксирует типы, имена, нормализованный SQL и SHA-256 хеш отсортированных строк таблиц.
  - Копия создаётся во временном каталоге с правами 0700 вне git и гарантированно удаляется в блоке `finally`.
  - Вывод отчёта по-русски: таблицы проверок, счётчики строк таблиц бота, префиксы хешей (12 символов), вердикт `ИТОГ: ЗЕЛЁНЫЙ` / `ИТОГ: КРАСНЫЙ`. Содержимое строк никогда не попадает в вывод.
  - Коды возврата: 0 (успех), 1 (замечания), 2 (несуществующий файл, каталог, символическая ссылка, отсутствие аргументов).
- **Проверенные сценарии (100% зелёные):**
  1. `test_green_on_legacy_shaped_source`: синтетический источник даёт `ok=True`, применена ровно 0003, хеш источника до и после равен, счётчики строк совпадают.
  2. `test_source_is_never_modified`: перехват вызовов `sqlite3.connect` подтвердил, что все обращения к источнику содержат `mode=ro`.
  3. `test_already_migrated_source_is_green`: на уже мигрированном источнике применено `[]`, вердикт зелёный.
  4. `test_red_when_migration_changes_existing_data`: изменение данных миграцией даёт `ok=False` с именем таблицы.
  5. `test_red_when_migration_fails`: синтаксическая ошибка миграции перехватывается, даёт `ok=False`, временный каталог удаляется.
  6. `test_red_on_unexpected_new_object`: появление посторонней таблицы/индекса даёт `ok=False` с их именами.
  7. `test_source_hash_drift_retries_then_red`: дрейф хеша вызывает повторы до `--attempts`; если дрейф только на первой попытке, вторая проходит.
  8. `test_temp_directory_removed`: временный каталог удаляется во всех случаях (включая красный).
  9. `test_report_never_prints_row_content`: маркерный текст данных отсутствует в отчёте и в выводе CLI.
  10. `test_cli_exit_codes_and_russian_verdict`: корректные коды 0, 1, 2 и русские вердикты.
- **Итог проверки:** `10 passed in 3.66s`.

## 2. Task 2: Раздел 13 в docs/OPS_DEPLOY.md и обновление тестов документа (D-06)

- **Красное состояние до обновления документа (RED):**
  В `tests/test_deploy_script.py` тест нумерации разделов расширен до 13 разделов с обязательным словом «Миграц» в заголовке раздела 13, и добавлен тест `test_docs_describe_migration_rollout`.
  Прогон зафиксировал: `2 failed, 196 deselected in 1.34s`.
- **Реализация (GREEN):**
  - В `docs/OPS_DEPLOY.md`:
    - В разделе 7 обновлён абзац «ОБЯЗАННОСТЬ Phase 3» (актуализирована связь с первой копией Phase 2 и обязательной новой копией перед рестартом с миграцией 0003).
    - Добавлен раздел `## 13. Миграции схемы при выкатке`: поведение при рестарте (безопасный no-op), порядок выкатки в 4 шага (проверка на копии с разрешения владельца, бэкап и рестарт, смоук, контрольная повторная проверка), гарантии безопасности, критерии красного вердикта, процедура отката и ограничения.
  - Проверено отсутствие символов `@`, шестнадцатеричных строк длиной >=32 и секретов.
- **Итог проверки:**
  Все тесты документа (10 тестов) пройдены (`10 passed in 0.27s`).
  Полный модуль `tests/test_deploy_script.py` пройден (`198 passed in 22.69s`).

## 3. Результаты полного регрессионного прогона

- **`assistant-core` pytest:** `1018 passed, 35 warnings in 141.42s (0:02:21)` (100% зелёный).
- **Страж боевой БД (`GATE-02`):** активен на протяжении всех прогонов, боевая БД `data/assistant.db` **НЕ ОТКРЫВАЛАСЬ**.
- **Демон `assistant-worker.service`:** не перезапускался.
