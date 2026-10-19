---
phase: 01-sobstvennyy-geyt-kachestva-assistant-core
plan: 02
subsystem: testing
tags: [pytest, pytest-asyncio, sqlite, migrations, hitl, security-shield, assistant-shared]

requires: []
provides:
  - "pytest-конфигурация /opt/assistant-shared (asyncio_mode=auto, testpaths, pythonpath) и 83 собственных теста shared"
  - "tests/test_migrations.py: список миграций из каталога, префикс 0001-0002, миграция поверх существующих данных"
  - "tests/test_hitl_shared.py: HITL-примитив без меток anyio, 4 новых случая"
  - "tests/test_security_shared.py, test_shield_regressions.py, test_shield_parity.py: библиотека безопасности"
affects: [01-05, phase-02-SECF-01, phase-03-migration-0003]

actuals:
  tokens: 12245
  tasks: 3
  commits: 3
plan_head_before: 66eed3ac3c6456831993418239c4b34238f3d0c8
plan_head_after: 725639982139996a2a174aeaa001366ac1c98825

tech-stack:
  added: []
  patterns:
    - "Список миграций вычисляется из MIGRATIONS_DIR; 0001-0002 проверяются как неизменный префикс, таблицы как подмножество"
    - "Глобальный реестр HITL-обработчиков: уникальные action_type в тестах, чтобы не протекало между тестами"
    - "Секретные и NDA-литералы в тестах собираются из частей или импортируются из библиотеки"

key-files:
  created:
    - /opt/assistant-shared/tests/test_migrations.py
    - /opt/assistant-shared/tests/test_hitl_shared.py
    - /opt/assistant-shared/tests/test_security_shared.py
    - /opt/assistant-shared/tests/test_shield_regressions.py
    - /opt/assistant-shared/tests/test_shield_parity.py
  modified:
    - /opt/assistant-shared/pyproject.toml

key-decisions:
  - "Копии тестов в chat-app не тронуты (D-02); WR-13 и всё, что импортирует app.*, не перенесено (D-01)"
  - "Тесты shared запускаются только в /opt/assistant-core/.venv (D-03); новые зависимости не добавлялись"
  - "CLI-тесты CR-02 указывают на обёртку /opt/assistant-core/scripts/security_shield.py: в shared скрипта нет"

patterns-established:
  - "shared-тесты запускаются из каталога shared: cd /opt/assistant-shared && /opt/assistant-core/.venv/bin/pytest tests"

requirements-completed: [GATE-03]

coverage:
  - id: D1
    description: "У shared есть pytest-конфигурация, и 83 теста запускаются из каталога shared командой core .venv без skip/xfail/deselect"
    requirement: GATE-03
    verification:
      - kind: unit
        ref: "cd /opt/assistant-shared && /opt/assistant-core/.venv/bin/pytest tests -p no:cacheprovider (83 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Тесты мигратора устойчивы к появлению 0003: список из каталога, префикс 0001-0002, синтетическая 9999 поверх данных"
    requirement: GATE-03
    verification:
      - kind: unit
        ref: "tests/test_migrations.py#test_new_migration_applies_on_top_without_touching_existing_data"
        status: pass
      - kind: unit
        ref: "tests/test_migrations.py#test_migration_files_have_contiguous_unique_prefixes"
        status: pass
    human_judgment: false
  - id: D3
    description: "HITL-примитив покрыт тестами shared, включая unknown id, отсутствие обработчика, фильтр list_pending и 409"
    requirement: GATE-03
    verification:
      - kind: unit
        ref: "tests/test_hitl_shared.py (9 passed)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Библиотека безопасности покрыта тестами shared; тесты, закрепляющие поведение Phase 2, помечены SECF-01; скан shared зелёный"
    requirement: GATE-03
    verification:
      - kind: unit
        ref: "tests/test_security_shared.py, test_shield_regressions.py, test_shield_parity.py (60 passed)"
        status: pass
      - kind: other
        ref: ".venv/bin/python scripts/security_shield.py /opt/assistant-shared --all (rc 0)"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-10-09
status: complete
---

# Phase 1 Plan 02: Собственные тесты assistant-shared Summary

**У /opt/assistant-shared появился собственный набор из 83 pytest-тестов (мигратор, HITL, библиотека безопасности), запускаемый из каталога shared через core .venv; тесты мигратора не ломаются при появлении миграции 0003.**

## Performance

- **Duration:** 12 мин
- **Started:** 2026-10-09T17:30:34Z
- **Completed:** 2026-10-09T17:42:42Z
- **Tasks:** 3
- **Files modified:** 6 в репозитории shared (5 новых тестовых файла, `pyproject.toml`)

## Accomplishments

- В `pyproject.toml` shared добавлена секция `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`, `testpaths`, `pythonpath`). Зависимости не менялись. `pytest-asyncio` (режим auto) и плагин anyio в core `.venv` совместно работают без предупреждений.
- Тесты мигратора перенесены: `ALL_MIGRATIONS` и `LATEST_SCHEMA_VERSION` считаются из `MIGRATIONS_DIR`, `BASELINE_MIGRATIONS` проверяется как неизменный префикс. Добавлены три теста: неизменный префикс, непрерывная уникальная нумерация, синтетическая миграция `9999_synthetic_extra` поверх БД с маркерной строкой (результат ровно `["9999_synthetic_extra"]`, данные целы, повторный вызов даёт `[]`).
- HITL: пять перенесённых тестов без меток anyio и четыре новых (`ValueError` для неизвестного id, `LookupError` без обработчика, фильтр `list_pending` по persona с пропуском просроченных, HTTP 409 с метаданными подтверждения).
- Безопасность: перенесены `test_security_shared`, `test_shield_regressions` (CR-01..CR-07, без WR-13) и `test_shield_parity`; добавлено пять новых тестов (параметризованная проверка каждого корпоративного слова NDA из библиотеки, custom_keywords заменяет список, отсутствующий файл, чистый репозиторий проходит `audit_path`, отсутствующий каталог даёт `virtual_airgap`).
- Скан `security_shield.py /opt/assistant-shared --all` (обёртка assistant-core): rc 0, 25 файлов.

**Число тестов по файлам (собранных pytest):** `test_migrations.py` 14 (11 перенесённых + 3 новых), `test_hitl_shared.py` 9 (5 + 4), `test_security_shared.py` 13 (6 перенесённых + 7 новых, из них 3 параметризованных случая), `test_shield_regressions.py` 46, `test_shield_parity.py` 1. Всего 83 passed, 0 skipped/deselected/xfail/xpass.

**Тесты с пометкой Phase 2 / SECF-01:**
- `test_security_shared.py::test_normalize_remote_formats` (литерал личного аккаунта в ожидаемом значении).
- `test_shield_regressions.py::test_cr05_cli_checks_all_remotes_and_aliases` (режим NDA по имени каталога `tydex-work` и литерал личного аккаунта в CLI-аудите).

**Наблюдение про fastapi (скрытый дефект, не исправлялся):** `assistant_shared.hitl.decorators` делает `from fastapi import HTTPException`, а `fastapi` нет среди зависимостей `pyproject.toml` shared (там только aiosqlite и pydantic). `import assistant_shared.hitl` без fastapi падает. Поэтому тесты shared работают только в core `.venv`, где fastapi стоит. Решение (вынести зависимость в optional-dependencies или убрать импорт из пакетного `__init__`) оставлено владельцу/следующему плану.

**Делегирование agy:** `test_migrations.py` (206 с, вход 108,5 тыс. / выход 19,3 тыс. токенов) и `test_shield_regressions.py` (315 с, вход 109,3 тыс. / выход 33,6 тыс.) выполнены через `agy_task.sh --repo /opt/assistant-shared --mode edit`. Оба патча прочитаны целиком и сверены с исходником построчной разницей: отличия только перечисленные в задании. Правила 1-3 не потребовались. Задания очищены (`clean`). HITL, безопасность и три новых теста мигратора написаны Claude.

## Task Commits

Коммиты сделаны в репозитории `/opt/assistant-shared` (ветка `master`), не в assistant-core:

1. **Task 1: pytest-конфиг и тесты мигратора** - `4fd0239` (test)
2. **Task 2: тесты HITL-примитива** - `3438904` (test)
3. **Task 3: тесты библиотеки безопасности** - `7256399` (test)

**Plan metadata:** следующий коммит docs(01-02) в assistant-core.

## Files Created/Modified

- `/opt/assistant-shared/pyproject.toml` - секция `[tool.pytest.ini_options]`
- `/opt/assistant-shared/tests/test_migrations.py` - 14 тестов мигратора
- `/opt/assistant-shared/tests/test_hitl_shared.py` - 9 тестов HITL
- `/opt/assistant-shared/tests/test_security_shared.py` - 13 тестов правил, паттернов, ключевых слов NDA
- `/opt/assistant-shared/tests/test_shield_regressions.py` - 46 регрессий CR-01..CR-07
- `/opt/assistant-shared/tests/test_shield_parity.py` - паритет web-аудита и CLI-аудита

## Decisions Made

- Следовал плану: перенос только тестов самой библиотеки, копии в chat-app остаются.
- Тесты CR-02 (флаги CLI) запускают обёртку из assistant-core, потому что в shared скрипта `security_shield.py` нет. Путь задан константой `SHIELD` с комментарием; если обёртку переименуют, тесты упадут (а не пропустятся).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Путь к CLI-обёртке в тестах CR-02**
- **Found during:** Task 3
- **Issue:** в исходнике `SHIELD = Path(__file__).resolve().parents[2] / "scripts" / "security_shield.py"`; в shared такого скрипта нет, при переносе как есть два теста CR-02 упали бы.
- **Fix:** константа указывает на `/opt/assistant-core/scripts/security_shield.py` (обёртка принадлежит потребителю), в задании agy это было прописано явно.
- **Files modified:** `/opt/assistant-shared/tests/test_shield_regressions.py`
- **Verification:** `test_cr02_flag_first_is_not_treated_as_path` и `test_cr02_unknown_flag_and_missing_path_fail` проходят.
- **Committed in:** `7256399`

**2. [Процесс] Новые тесты проходят сразу (TDD RED не наблюдался)**
- **Found during:** Tasks 1-3 (`tdd="true"`)
- **Issue:** все новые тесты фиксируют уже существующее поведение библиотеки (характеризационные), поэтому unexpected green в RED-фазе неизбежен; код библиотеки в плане не менялся. Тесты `tdd_mode` в конфиге не включён, план имеет `type: execute`, отдельные `test(...)`-коммиты не требовались.
- **Fix:** по одному коммиту на задачу, как требует план.

---

**Total deviations:** 1 auto-fixed (Rule 3), 1 процессная заметка
**Impact on plan:** на безопасность и результат не влияет. Код библиотеки и chat-app не изменены.

## Issues Encountered

- `agy` занял по 3-5 минут на задачу, поэтому HITL- и безопасностные тесты писались параллельно с ожиданием.
- Хук «Secret read guard» не срабатывал: `.env` не читался.

## Known Stubs

None.

## Threat Flags

None. Новых сетевых точек, путей аутентификации и схемных изменений нет. T-01-05: тестовые секреты собираются из частей или импортируются из библиотеки, скан `security_shield --all` по shared зелёный. T-01-SC: пакеты не устанавливались.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- План 01-05 (гейт) может запускать тесты shared строкой `cd /opt/assistant-shared && /opt/assistant-core/.venv/bin/pytest tests`: 83 passed, около 30-45 с.
- Phase 3 (миграция `0003`) не сломает тесты мигратора: список берётся из каталога; единственное жёсткое место `BASELINE_MIGRATIONS`.
- Phase 2 (SECF-01) должна переписать два теста с пометкой SECF-01.
- Открытый дефект: fastapi не в зависимостях shared (см. выше).

## Self-Check: PASSED

- FOUND: 5 тестовых файлов и `pyproject.toml` в `/opt/assistant-shared`
- FOUND коммиты: `4fd0239`, `3438904`, `7256399` (предки HEAD в репозитории shared)
- `git -C /opt/assistant-shared status --short` пуст, `git -C /opt/chat-app status --short` пуст
- Полный прогон: 83 passed, 0 skipped/deselected/xfail/xpass; скан безопасности rc 0

---
*Phase: 01-sobstvennyy-geyt-kachestva-assistant-core*
*Completed: 2026-10-09*
