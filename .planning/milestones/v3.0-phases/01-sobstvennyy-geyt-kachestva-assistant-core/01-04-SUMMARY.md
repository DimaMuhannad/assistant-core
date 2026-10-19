---
phase: 01-sobstvennyy-geyt-kachestva-assistant-core
plan: 04
subsystem: testing
tags: [gate, pytest, junit, sqlite, import-linter, security-shield, stdlib]

requires:
  - phase: 01-sobstvennyy-geyt-kachestva-assistant-core
    provides: "01-01: страж боевой БД и переменная ASSISTANT_DB_PATH_OVERRIDE"
provides:
  - "scripts/gate.py: собственный гейт качества assistant-core (только stdlib), строки core: pytest, хеш боевой БД до/после, import-linter, shield, дрейф персоны"
  - "tests/test_gate.py: 111 юнит-тестов чистых функций гейта"
affects: [01-05, gate]

actuals:
  tokens: 15864
  tasks: 3
  commits: 3
plan_head_before: 08fe5f947a0576ed37c1cdc017a310d16077e3c3
plan_head_after: 1ea58fcb3eecb6e9182a5fee329e161175cf0ab6

tech-stack:
  added: []
  patterns:
    - "Fail-closed гейт: сбой шага превращается в красную строку, пустой список и 0 тестов дают КРАСНЫЙ"
    - "Вывод shield нормализуется до (путь, вид, число), текст находок в таблицу не попадает"
    - "Хеш логического содержимого БД через дамп в одной транзакции (mode=ro), «после» сразу за pytest core"

key-files:
  created:
    - scripts/gate.py
    - tests/test_gate.py
  modified: []

key-decisions:
  - "Режим shield один (--all), интерпретатор для обоих репозиториев из .venv core с запасным sys.executable"
  - "core_pytest_env дополнительно отвергает sidecar-файлы корневого assistant.db (assistant.db-wal и т.п.) и путь через .."
  - "db_unchanged_check принимает diagnostics_fn, диагностика только читает (systemctl is-active, mtime) и не смягчает вердикт"

patterns-established:
  - "Тесты гейта грузят scripts/gate.py как модуль через importlib и подменяют run_cmd; полный гейт и реальный shield из тестов не запускаются"
  - "Тексты NDA-слов, e-mail и remote в тестах собираются из частей"

requirements-completed: [GATE-01, GATE-02, GATE-04]

coverage:
  - id: D1
    description: "gate.py печатает русскую таблицу с ✓/✗ и ИТОГ ЗЕЛЁНЫЙ (rc 0) / КРАСНЫЙ (rc 1); сбой шага даёт красную строку, остальные печатаются"
    requirement: GATE-01
    verification:
      - kind: unit
        ref: "tests/test_gate.py#test_render_report_one_red_shows_detail_and_red_verdict"
        status: pass
      - kind: unit
        ref: "tests/test_gate.py#test_main_turns_internal_exception_into_red_row"
        status: pass
      - kind: integration
        ref: "python3 scripts/gate.py (полный прогон, 2-й запуск: ИТОГ ЗЕЛЁНЫЙ, rc 0)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Строгий критерий pytest: skipped == 1, xfailed, xpassed, deselected, error, 0 тестов и пустой список дают КРАСНЫЙ"
    requirement: GATE-01
    verification:
      - kind: unit
        ref: "tests/test_gate.py#test_pytest_ok_adjacency_exactly_one_skipped_is_red"
        status: pass
      - kind: unit
        ref: "tests/test_gate.py#test_pytest_ok_empty_zero_tests_is_red_for_rc_0_and_rc_5"
        status: pass
      - kind: unit
        ref: "tests/test_gate.py#test_overall_green_empty_list_is_red"
        status: pass
    human_judgment: false
  - id: D3
    description: "pytest core запускается с -v, no:cacheprovider, xfail_strict=true, junit, своим basetemp, очищенным PYTEST_ADDOPTS и ASSISTANT_DB_PATH_OVERRIDE во временный файл; путь на боевую БД отвергается"
    requirement: GATE-02
    verification:
      - kind: unit
        ref: "tests/test_gate.py#test_run_pytest_step_command_is_strict_and_unfiltered"
        status: pass
      - kind: unit
        ref: "tests/test_gate.py#test_core_pytest_env_refuses_live_db"
        status: pass
      - kind: unit
        ref: "tests/test_gate.py#test_run_all_isolates_pytest_db_and_removes_temp_dir"
        status: pass
    human_judgment: false
  - id: D4
    description: "Хеш логического содержимого боевой БД до и сразу после pytest core; совпадение даёт info с префиксом хеша, расхождение КРАСНЫЙ с диагностикой и без смягчения"
    requirement: GATE-02
    verification:
      - kind: unit
        ref: "tests/test_gate.py#test_db_unchanged_check_mismatch_is_red_with_diagnostics_and_retry_hint"
        status: pass
      - kind: unit
        ref: "tests/test_gate.py#test_run_all_measures_hash_after_pytest_core_and_before_other_rows"
        status: pass
      - kind: integration
        ref: "python3 scripts/gate.py (2-й запуск: SHA-256 до/после совпали: 080dc486b400)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Дрейф synthetic_persona.py и persona_tokens.py с копиями chat-app проверяется только на чтение; отсутствие копии краснит гейт"
    requirement: GATE-04
    verification:
      - kind: unit
        ref: "tests/test_gate.py#test_persona_drift_check_missing_chat_copy_is_red_with_reason"
        status: pass
      - kind: unit
        ref: "tests/test_gate.py#test_persona_drift_check_never_modifies_chat_copy"
        status: pass
    human_judgment: false
  - id: D6
    description: "Замороженный список ложных срабатываний shield (core: persona.yaml nda-keyword 3, shared: пусто); новая находка и устаревшая запись краснят; текст находок не утекает"
    requirement: GATE-04
    verification:
      - kind: unit
        ref: "tests/test_gate.py#test_known_shield_false_positives_frozen_list_is_exact"
        status: pass
      - kind: unit
        ref: "tests/test_gate.py#test_run_shield_step_does_not_leak_nda_word_email_or_remote"
        status: pass
      - kind: unit
        ref: "tests/test_gate.py#test_run_shield_step_core_stale_frozen_entry_is_red"
        status: pass
    human_judgment: false
  - id: D7
    description: "Гейт достижим из рантайма разработчика: python3 scripts/gate.py на текущем дереве зелёный; формулировка «гейт стабильно зелёный при активном assistant-worker» не доказана (см. Issues Encountered)"
    requirement: GATE-01
    verification: []
    human_judgment: true
    rationale: "Первый полный прогон дал КРАСНЫЙ из-за записи живого сервиса в боевую БД в окне pytest; решение о стратегии (повтор, остановка записи, иное окно измерения) принадлежит владельцу и плану 01-05"

duration: 19min
completed: 2026-10-09
status: complete
---

# Phase 1 Plan 04: Локальный гейт качества assistant-core Summary

**scripts/gate.py на одной stdlib: строгий pytest core в изолированной БД, независимый хеш боевой БД до и сразу после, import-linter, shield с замороженным списком ложных срабатываний без утечки текста находок и проверка дрейфа персоны; 111 юнит-тестов.**

## Performance

- **Duration:** 19 мин
- **Started:** 2026-10-09T18:08:45Z
- **Completed:** 2026-10-09T18:28Z
- **Tasks:** 3
- **Files modified:** 2 (оба новые: `scripts/gate.py`, `tests/test_gate.py`)

## Accomplishments

- `python3 scripts/gate.py` печатает по-русски таблицу «Репозиторий | Проверка | Результат» и строку «ИТОГ: ЗЕЛЁНЫЙ» (rc 0) или «ИТОГ: КРАСНЫЙ» (rc 1). Сбой любого шага превращается в красную строку, остальные строки всё равно печатаются. Пустой список результатов и 0 собранных тестов дают КРАСНЫЙ.
- pytest core запускается строго: `-v -p no:cacheprovider -o xfail_strict=true`, junit XML, свой `--basetemp`, пустой `PYTEST_ADDOPTS`, без `-k/-m/--deselect`. `ASSISTANT_DB_PATH_OVERRIDE` указывает на временный файл; `core_pytest_env` отвергает боевую БД, корневой `assistant.db` (и его sidecar-файлы), любой путь внутри `data/` и путь через `..`.
- Хеш логического содержимого боевой БД (дамп в одной транзакции, соединение `mode=ro`) считается до pytest core и сразу после него. Совпадение печатается как `SHA-256 до/после совпали: <12 символов>`; расхождение даёт КРАСНЫЙ с диагностикой (состояние сервиса, время изменения БД) и подсказкой повторить прогон.
- Shield: вывод нормализуется до `(путь, вид, число)`, замороженный список `KNOWN_SHIELD_FALSE_POSITIVES` = `{assistant-core: {(config/persona.yaml, nda-keyword): 3}, assistant-shared: {}}`. Новая находка, превышение числа и устаревшая запись краснят. Тест «нет утечки» подтверждает, что NDA-слово, e-mail и remote не попадают в detail и в таблицу.
- Дрейф `synthetic_persona.py` и `persona_tokens.py` с копиями chat-app (по умолчанию `/opt/chat-app`, переменная `ASSISTANT_CHAT_APP_DIR`) сверяется побайтно, только на чтение; отсутствие любой копии даёт КРАСНЫЙ с текстом «нет файла».

**Число тестов:** в `tests/test_gate.py` 111 (102 функции, часть параметризована). Весь набор core под гейтом: 688 passed, 0 skipped/deselected/xfail/xpass (с `-o xfail_strict=true`, допущение A2 исследования подтверждено на текущем дереве).
**Рестарт `assistant-worker` не требуется:** файлы только `scripts/gate.py` и `tests/test_gate.py`, `src/` не менялся.

## Task Commits

1. **Task 1: Скелет гейта и строка import-linter** - `1d5fd09` (feat)
2. **Task 2: Строгий pytest core, изоляция БД, хеш до/после, дрейф персоны** - `41c576b` (feat)
3. **Task 3: Нормализация shield и замороженный список ложных срабатываний** - `1ea58fc` (feat)

**Plan metadata:** следующий коммит docs(01-04).

## Files Created/Modified

- `scripts/gate.py` - гейт: `CheckResult`, `run_cmd`, строгий разбор pytest/junit, `core_pytest_env`, `db_content_hash`, `db_unchanged_check`, `persona_drift_check`, разбор и сверка shield, `render_report`, `main`, флаг `--save-pytest-output DIR`
- `tests/test_gate.py` - 111 юнит-тестов: границы adjacency (skipped == 1) и empty (0 тестов, пустой список), отказные пути `core_pytest_env`, WAL-стабильность хеша, диагностика, обе пары дрейфа, порядок шагов `_run_all`, шаги shield по подменённому `run_cmd`

## Decisions Made

- Режим shield один, `--all`; интерпретатор берётся из `.venv` core для обоих репозиториев (D-03), запасной `sys.executable`. Переменной режима из образца нет (YAGNI).
- `core_pytest_env` строже, чем в плане: помимо боевой БД, корневого `assistant.db` и каталога `data/` отвергает sidecar-файлы `assistant.db*` в корне репозитория и пути с `..` (через `resolve()`).
- Диагностика расхождения хеша передаётся функцией (`diagnostics_fn`), её сбой не отменяет КРАСНЫЙ вердикт («диагностика недоступна»).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Слово `--deselect` в докстринге нарушало критерий приёмки Task 2**
- **Found during:** Task 2 (тест `test_gate_source_has_no_test_filters_and_pins_xfail_strict`)
- **Issue:** докстринг `run_pytest_step`, перенесённый из образца, содержал текст «без -k/-m/--deselect», а критерий требует `grep -c '"-k"\|"-m"\|--deselect' scripts/gate.py` = 0.
- **Fix:** формулировка заменена на «без фильтров набора тестов».
- **Files modified:** scripts/gate.py
- **Verification:** grep печатает 0, тест зелёный
- **Committed in:** 41c576b

**2. [Процесс] RED-стадия Task 1 не показана отдельно**
- **Found during:** Task 1 (tdd="true")
- **Issue:** скелет `gate.py` написан до тестов, поэтому падение тестов до реализации не фиксировалось. Для Task 2 и Task 3 тесты писались первыми и падали на `AttributeError` отсутствующих функций (57 и 35 красных соответственно), затем зеленели после реализации.
- **Impact:** `workflow.tdd_mode` в конфиге не включён, план имеет `type: execute`, отдельные `test(...)` коммиты не требовались.

**3. [Расширение] Полный прогон гейта выполнен, хотя план его не требовал**
- План оставлял полный прогон плану 01-05. Я запустил `python3 scripts/gate.py` дважды как smoke-проверку строк core (см. ниже). Строк shared и hook в гейте нет, они в 01-05.

---

**Total deviations:** 1 auto-fixed (Rule 1), 2 процессные заметки
**Impact on plan:** на результат и безопасность не влияют.

## Issues Encountered

- **Первый полный прогон гейта: КРАСНЫЙ из-за хеша боевой БД.** Строка pytest (688 тестов) зелёная, но «боевая assistant.db не изменена» красная: диагностика показала `сервис assistant-worker: active`, mtime БД 18:17:10 UTC внутри окна прогона. Тесты на боевую БД выйти не могут (страж `tests/live_db_guard.py` из 01-01, 688 тестов прошли без `LiveDatabaseAccessError`). Доказательства, что запись была от живого сервиса, а не от тестов: хеш простаивающей БД 4 замера подряд с интервалом 60 с одинаков (`080dc486b400`), а второй полный прогон дал `SHA-256 до/после совпали: 080dc486b400` и ИТОГ ЗЕЛЁНЫЙ (хеш «до» второго прогона равен хешу «после» первого). Вердикт я не смягчал: по плану расхождение всегда КРАСНЫЙ. Вывод для 01-05: проверка «до/после» по своей природе гоняется с активным `assistant-worker` (окно pytest около 3,5 мин, периодические задания пишут в БД), красный из-за записи сервиса возможен на любом прогоне; нужно решение владельца о стратегии (повтор по подсказке в detail, как сейчас, либо иное окно измерения). Само по себе это не ошибка кода гейта.
- Полный прогон pytest core занимает около 3,5 мин на загруженном VPS (688 тестов).

## Known Stubs

None.

## Threat Flags

None. Новых сетевых точек и путей аутентификации нет. Меры T-01-09 (нормализация shield, тест «нет утечки»), T-01-10 (fail-closed ветки), T-01-11 (`shell=False`, список аргументов, таймауты, проверка AST), T-01-12 (в `CHAT_APP_DIR` только чтение, тест `never_modifies_chat_copy`), T-01-SC (только stdlib, проверка AST импортов) реализованы.

## Next Phase Readiness

- Для 01-05: подключить строки assistant-shared (pytest, shield), проверку hook, красные кейсы на мини-проектах и итоговый прогон. Решить вопрос окна хеша при активном `assistant-worker` (см. Issues Encountered).
- `_run_all` содержит порядок: хеш «до», pytest core, хеш «после», сверка хеша, import-linter, shield core, дрейф x2. Тест порядка уже есть и потребует расширения при добавлении строк shared.

## Self-Check: PASSED

- FOUND: scripts/gate.py, tests/test_gate.py
- FOUND коммиты (предки HEAD): 1d5fd09, 41c576b, 1ea58fc
- tests/test_gate.py: 111 passed; tests/test_hardcode_scanner.py: 3 passed; полный набор core под гейтом: 688 passed
- `grep -c '"-k"\|"-m"\|--deselect' scripts/gate.py` = 0; `shell=True` отсутствует; запись в `CHAT_APP_DIR` отсутствует

---
*Phase: 01-sobstvennyy-geyt-kachestva-assistant-core*
*Completed: 2026-10-09*
