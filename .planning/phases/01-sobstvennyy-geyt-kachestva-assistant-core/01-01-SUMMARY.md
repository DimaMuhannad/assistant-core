---
phase: 01-sobstvennyy-geyt-kachestva-assistant-core
plan: 01
subsystem: testing
tags: [pytest, audit-hook, sqlite, config, gate]

requires: []
provides:
  - "tests/live_db_guard.py: страж боевой БД на sys.addaudithook (open, sqlite3.connect), ставится в conftest"
  - "ASSISTANT_DB_PATH_OVERRIDE в src/config.py: захват до load_dotenv(override=True), применение после"
  - "create_server_backup_archive(core_dir=...): тест на поддельном каталоге без чтения боевых файлов"
  - "Тайминговые проверки test_command_aliases.py по минимуму из LATENCY_SAMPLES замеров"
affects: [01-04, 01-05, gate]

actuals:
  tokens: 5800
  tasks: 3
  commits: 3
plan_head_before: 7f4d5c0dd63b8077830ee33e42910a6b8ab97ebe
plan_head_after: 8367e0561c6ae24ae69e1a510ff15e0f23eb695d

tech-stack:
  added: []
  patterns:
    - "Страж через sys.addaudithook: не снимается до конца процесса, флаг повторного входа в threading.local"
    - "Явное переопределение конфигурации захватывается до load_dotenv(override=True)"
    - "Пороги латентности проверяются по min из N замеров, а не по одиночному"

key-files:
  created:
    - tests/live_db_guard.py
    - tests/test_live_db_guard.py
  modified:
    - src/config.py
    - tests/conftest.py
    - src/connectors/gdrive/client.py
    - tests/test_gdrive_client.py
    - tests/test_command_aliases.py

key-decisions:
  - "Страж в тестовой оснастке плюс приоритет пути в src/config.py; рантайм с боевым .env не меняется"
  - "Корневой assistant.db закрыт предохранительно вместе с data/assistant.db и sidecar-файлами"
  - "Тайминги: минимум из 5 замеров, пороги 50 и 250 мс не менялись, skip/xfail не использовались"

patterns-established:
  - "conftest.py ставит страж и ASSISTANT_DB_PATH_OVERRIDE (setdefault) до первого импорта src"

requirements-completed: [GATE-02, GATE-01]

coverage:
  - id: D1
    description: "Любая форма доступа теста к боевой БД (open, sqlite3, file:-URI, относительный путь, aiosqlite, sidecar) даёт LiveDatabaseAccessError"
    requirement: GATE-02
    verification:
      - kind: unit
        ref: "tests/test_live_db_guard.py (32 теста)"
        status: pass
    human_judgment: false
  - id: D2
    description: "load_dotenv(override=True) не перебивает изолированный путь БД; без переменной поведение прежнее"
    requirement: GATE-02
    verification:
      - kind: unit
        ref: "tests/test_live_db_guard.py#test_db_path_override_survives_load_dotenv_override"
        status: pass
      - kind: unit
        ref: "tests/test_live_db_guard.py#test_db_path_without_override_is_taken_from_dotenv"
        status: pass
    human_judgment: false
  - id: D3
    description: "test_create_server_backup_archive работает на поддельном каталоге через core_dir"
    requirement: GATE-02
    verification:
      - kind: unit
        ref: "tests/test_gdrive_client.py#test_create_server_backup_archive"
        status: pass
    human_judgment: false
  - id: D4
    description: "Тайминговые пороги устойчивы к одиночным пикам нагрузки (три подряд зелёных прогона)"
    requirement: GATE-01
    verification:
      - kind: unit
        ref: "tests/test_command_aliases.py (3 прогона подряд)"
        status: pass
    human_judgment: false

duration: ~25min
completed: 2026-10-09
status: complete
---

# Phase 1 Plan 01: Страж боевой БД и устойчивые тайминги Summary

**Страж боевой БД на sys.addaudithook (open, sqlite3.connect, file:-URI, aiosqlite, sidecar), изолированный путь через ASSISTANT_DB_PATH_OVERRIDE, который не перебивает load_dotenv(override=True), и тайминговые тесты по минимуму из 5 замеров.**

## Performance

- **Duration:** ~25 мин (время старта не фиксировалось, оценка по журналу)
- **Completed:** 2026-10-09T17:28Z
- **Tasks:** 3
- **Files modified:** 7 (2 новых, 5 изменённых)

## Accomplishments

- Любой тест, пытающийся открыть `data/assistant.db`, корневой `assistant.db` или их `-wal/-shm/-journal`, получает `LiveDatabaseAccessError` с русским сообщением до обращения к файлу. Хук ставится при импорте `tests/conftest.py` и не снимается до конца процесса.
- `src/config.py` читает `ASSISTANT_DB_PATH_OVERRIDE` до `load_dotenv(override=True)` и применяет после. Тест подменой `dotenv.load_dotenv` доказывает приоритет, парный тест доказывает, что без переменной путь берётся как раньше.
- `GoogleDriveClient.create_server_backup_archive` получил параметр `core_dir` (по умолчанию `/opt/assistant-core`). Единственный тест, читавший боевую БД, `.env` и сессию, теперь работает на синтетических файлах в `tmp_path`.
- `test_command_aliases.py`: пороги 50 и 250 мс (не менялись) проверяются по минимуму из `LATENCY_SAMPLES = 5` замеров. Три прогона файла подряд зелёные.
- Полный прогон: **455 passed**, 0 failed/skipped/deselected/xfail/xpass, сообщений `LiveDatabaseAccessError` в выводе нет (с `-o xfail_strict=true`).

**Число тестов:** до плана 421, после 455 (+32 в `test_live_db_guard.py`, +2 в `test_gdrive_client.py`: 1 тест заменён тремя).
**Тесты, исправленные из-за стража:** один, `test_create_server_backup_archive` (читал боевые файлы). Других обращений к боевой БД полный прогон под стражем не выявил.
**Рестарт `assistant-worker` не требуется:** вызов `create_server_backup_archive()` в рантайме остаётся без аргументов, `src/config.py` без переменной окружения вычисляет путь БД как раньше, остальные правки только в `tests/`.

## Task Commits

1. **Task 1: Страж боевой БД и приоритет пути в config** - `2011961` (feat)
2. **Task 2: core_dir у create_server_backup_archive и тест на поддельном каталоге** - `695c5be` (feat)
3. **Task 3: Стабилизация тайминговых порогов** - `8367e05` (test)

**Plan metadata:** следующий коммит docs(01-01).

## Files Created/Modified

- `tests/live_db_guard.py` - audit-hook страж, `LiveDatabaseAccessError`, `is_live_db_path`, `install`, `LIVE_DB_PATHS`
- `tests/test_live_db_guard.py` - 32 теста: формы путей, реальные вызовы, идемпотентность, приоритет config
- `tests/conftest.py` - установка стража и `ASSISTANT_DB_PATH_OVERRIDE` (setdefault) до импорта `src`
- `src/config.py` - `_DB_PATH_OVERRIDE` до `load_dotenv`, ветки `SQLITE_DB_PATH` и `DATABASE_URL`
- `src/connectors/gdrive/client.py` - параметр `core_dir`
- `tests/test_gdrive_client.py` - тест на поддельном каталоге, тест пустого архива, тест значения по умолчанию
- `tests/test_command_aliases.py` - `LATENCY_SAMPLES`, проверка по минимуму

## Decisions Made

- Страж в тестовой оснастке плюс захват переопределения в `src/config.py`, как задано планом.
- Копия боевой БД под другим именем или symlink с иным именем стражем не ловится (префильтр по basename). Это зафиксированное допущение плана, не регрессия.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Проверка отсутствия ключа в боевом `.env` выполнена по `.env.example`**
- **Found during:** Task 1 (третья команда `<verify>`: `grep -c '^ASSISTANT_DB_PATH_OVERRIDE=' .env`)
- **Issue:** хук `PreToolUse` («Secret read guard») запретил любую Bash-команду, читающую `.env`, включая `grep -c`. Обходить запрет не стал.
- **Fix:** проверил имя ключа в `.env.example` (счётчик 0). Боевой `.env` не открывался и не читался.
- **Остаточный риск:** отсутствие ключа именно в боевом `.env` формально не подтверждено. Предлагается подтвердить владельцу. Если ключ окажется в `.env`, `load_dotenv` его не затрёт (захват идёт до загрузки), но рантайм пошёл бы на другую БД, поэтому проверка нужна до рестарта.
- **Files modified:** нет

**2. [Процесс] RED-стадия Task 1 подтверждена ошибкой импорта, а не падением assertion**
- **Found during:** Task 1 (tdd="true")
- **Issue:** модуля стража ещё не существовало, `pytest tests/test_live_db_guard.py` упал на `ImportError` при сборе (строго это INVALID_RED по tdd.md). `workflow.tdd_mode` в конфиге не включён, план имеет `type: execute`, поэтому гейт RED-коммита не применялся.
- **Fix:** RED для Task 2 получен честно (`TypeError: unexpected keyword argument 'core_dir'`, 2 целевых теста упали, 2 прочих прошли). Отдельные `test(...)` коммиты не делались: по одному коммиту на задачу, как требует план.

---

**Total deviations:** 1 auto-fixed (Rule 3), 1 процессная заметка
**Impact on plan:** на безопасность и результат не влияет; единственный открытый пункт: подтверждение владельцем отсутствия ключа в боевом `.env`.

## Issues Encountered

- Сбор тестов и прогон `tests/test_command_aliases.py` занимают 30-50 с из-за импортов (VPS под нагрузкой), поэтому проверка «три прогона подряд» длится около 2 минут.
- Критерий приёмки Task 2 «минимум три использования `core_dir`»: в методе имя `core_dir` встречается в сигнатуре, докстринге и один раз при вычислении `core_root = Path(core_dir)`, а три пути строятся от `core_root`. Смысл (пути строятся от параметра, жёстких путей нет) выполнен, буквальный подсчёт `grep -c core_dir` равен 3 строкам.

## Known Stubs

None.

## Threat Flags

None. Новых сетевых точек, путей аутентификации или схемных изменений нет. Меры T-01-01 ... T-01-04 реализованы (страж на audit-hook, `core_dir` с синтетическими байтами, захват до `load_dotenv`, префильтр по basename и thread-local флаг).

## Next Phase Readiness

- План 01-04/01-05 (гейт) может передавать свой путь через `ASSISTANT_DB_PATH_OVERRIDE`: conftest использует `setdefault` и не затирает его. Гейту стоит отказываться от назначения этого пути на боевую БД (T-01-03).
- Базовая линия набора: 455 тестов, стабильный по времени.

## Self-Check: PASSED

- FOUND: tests/live_db_guard.py, tests/test_live_db_guard.py
- FOUND коммиты: 2011961, 695c5be, 8367e05 (предки HEAD)
- Полный прогон: 455 passed, 0 skipped/deselected/xfail/xpass

---
*Phase: 01-sobstvennyy-geyt-kachestva-assistant-core*
*Completed: 2026-10-09*
