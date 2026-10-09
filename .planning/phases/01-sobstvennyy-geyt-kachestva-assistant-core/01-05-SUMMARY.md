---
phase: 01-sobstvennyy-geyt-kachestva-assistant-core
plan: 05
subsystem: testing
tags: [gate, pytest, hook, assistant-shared, sqlite, red-cases, stdlib]

requires:
  - phase: 01-sobstvennyy-geyt-kachestva-assistant-core
    provides: "01-01 страж боевой БД; 01-02 тесты shared; 01-03 hook shared; 01-04 каркас scripts/gate.py"
provides:
  - "scripts/gate.py: полная таблица из 10 строк (core x7, shared x3), проверка установленного hook, один повтор замера хеша БД при записи живого сервиса"
  - "tests/test_gate.py: тесты hook, состава и порядка _run_all, отказоустойчивости, повтора при записи сервиса (154 теста вместе с красными кейсами)"
  - "tests/test_gate_red_cases.py: красные кейсы и зелёный контроль на мини-проектах в tmp_path"
affects: [01-08, 01-09, 01-10, gate]

actuals:
  tokens: 10366
  tasks: 3
  commits: 3
plan_head_before: bdc3946daf50c39cedc91fcf57ce6e7c57febb05
plan_head_after: 5ac98b41718e818af6007bf7e8598e207fb56d34

tech-stack:
  added: []
  patterns:
    - "Каждая красная ситуация доказана настоящим подпроцессом pytest на мини-проекте плюс зелёный контроль"
    - "Смягчение вердикта только при трёх совпавших условиях (хеши различаются, сервис active, mtime внутри окна), один повтор без цикла, пометка в info"

key-files:
  created:
    - tests/test_gate_red_cases.py
  modified:
    - scripts/gate.py
    - tests/test_gate.py

key-decisions:
  - "Решение владельца 2026-10-09 «Повтор при записи сервиса»: при расхождении хешей боевой БД, активном assistant-worker и mtime БД внутри окна измерения выполняется ОДИН повторный замер в тихом окне (два хеша через REMEASURE_WAIT_S = 5 с); совпали - строка зелёная с явной пометкой в info, иначе КРАСНЫЙ как раньше"
  - "mtime для свидетельства записи сервиса - максимум времени изменения assistant.db и assistant.db-wal (запись в WAL не меняет основной файл); -shm не берётся, его трогают читатели"
  - "Строки shared: pytest интерпретатором core .venv (D-03), shield отдельной строкой (D-05), hook отдельной строкой (D-04)"

patterns-established:
  - "Любая неизвестность в свидетельстве записи сервиса (systemctl недоступен, нет файла БД, окно не передано) означает отказ от повтора и КРАСНЫЙ"

requirements-completed: [GATE-01, GATE-02, GATE-03, GATE-04]

coverage:
  - id: D1
    description: "Гейт печатает ровно 10 строк в фиксированном порядке (core: pytest, БД, import-linter, shield, 2 дрейфа, hook; shared: pytest, shield, hook)"
    requirement: GATE-03
    verification:
      - kind: unit
        ref: "tests/test_gate.py#test_run_all_row_order"
        status: pass
      - kind: unit
        ref: "tests/test_gate.py#test_shared_rows_are_separate"
        status: pass
      - kind: integration
        ref: "python3 scripts/gate.py (полный прогон: 10 строк ✓, ИТОГ: ЗЕЛЁНЫЙ, rc 0)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Проверка hook: core.hooksPath = .githooks и исполняемый .githooks/pre-commit; любой сбой даёт красную строку с подсказкой scripts/install_hooks.sh"
    requirement: GATE-03
    verification:
      - kind: unit
        ref: "tests/test_gate.py#test_hook_installed_check_green_with_hookspath_and_executable_hook"
        status: pass
      - kind: unit
        ref: "tests/test_gate.py#test_hook_installed_check_red_without_hookspath_mentions_installer"
        status: pass
      - kind: unit
        ref: "tests/test_gate.py#test_hook_installed_check_without_git_is_red_not_exception"
        status: pass
    human_judgment: false
  - id: D3
    description: "Красные кейсы на мини-проектах: падающий тест, skip, xfail, xpass, deselected через addopts, ноль тестов, нет бинарника, таймаут; зелёный контроль; PYTEST_ADDOPTS окружения не сужает набор"
    requirement: GATE-01
    verification:
      - kind: unit
        ref: "tests/test_gate_red_cases.py (10 тестов, настоящий подпроцесс pytest в tmp_path)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Сбой любого шага не обрывает гейт: исключение превращается в красную строку, печатаются все 10 строк"
    requirement: GATE-01
    verification:
      - kind: unit
        ref: "tests/test_gate.py#test_run_all_never_aborts_on_step_exception"
        status: pass
    human_judgment: false
  - id: D5
    description: "Повтор замера хеша БД при записи живого сервиса (решение владельца): ровно один повтор, зелёный только при совпадении двух замеров тихого окна; не active, mtime вне окна, нет окна, хеш None, сбой - КРАСНЫЙ"
    requirement: GATE-02
    verification:
      - kind: unit
        ref: "tests/test_gate.py#test_db_retry_service_write_then_quiet_remeasure_match_is_green_with_explicit_note"
        status: pass
      - kind: unit
        ref: "tests/test_gate.py#test_db_retry_not_attempted_when_service_not_active_or_mtime_outside_window"
        status: pass
      - kind: unit
        ref: "tests/test_gate.py#test_run_all_write_with_idle_service_stays_red"
        status: pass
      - kind: unit
        ref: "tests/test_gate.py#test_db_unchanged_check_has_no_loop_so_retry_is_single"
        status: pass
    human_judgment: false
  - id: D6
    description: "Ветка повтора реально срабатывает на боевом сервисе: в полном прогоне расхождения не было, повтор не вызывался"
    requirement: GATE-02
    verification: []
    human_judgment: true
    rationale: "Единственный полный прогон дал совпадение хешей до/после без повтора. Ветка доказана юнит-тестами с подменой замеров, но не боевым событием записи сервиса; понаблюдать на следующих прогонах."

duration: 10min
completed: 2026-10-09
status: complete
---

# Phase 1 Plan 05: Полный гейт качества Summary

**scripts/gate.py печатает 10 строк по двум репозиториям (core: 789 тестов, shared: 91), проверяет установленные pre-commit hook, доказан красными кейсами на мини-проектах и по решению владельца делает один повтор замера хеша боевой БД при записи живого assistant-worker.**

## Performance

- **Duration:** 10 мин
- **Started:** 2026-10-09T20:00:43Z
- **Completed:** 2026-10-09T20:10Z
- **Tasks:** 3 (Task 3 без изменения файлов, только прогон)
- **Files modified:** 3 (`scripts/gate.py`, `tests/test_gate.py`, новый `tests/test_gate_red_cases.py`)

## Accomplishments

- **Состав таблицы (Task 1).** `_run_all` даёт ровно 10 строк: assistant-core (pytest, БД не изменена, import-linter, security_shield, дрейф синтетической персоны, дрейф токенов персоны, hook) и assistant-shared (pytest, security_shield, hook). Тесты shared запускаются интерпретатором `/opt/assistant-core/.venv` с `cwd = SHARED_DIR` и пустым `PYTEST_ADDOPTS` (`shared_pytest_env`). Секрет в shared краснит итог (D-05).
- **Проверка hook (D-04).** `hook_installed_check`: `core.hooksPath` равен `.githooks` и файл `.githooks/pre-commit` исполняемый. Нет каталога, git, значения, файла, бита исполнения, таймаут: красная строка с подсказкой «выполните scripts/install_hooks.sh в репозитории», не исключение.
- **Красные кейсы (Task 2).** `tests/test_gate_red_cases.py`: падающий тест, skip, xfail, xpass (strict), deselected через `addopts` в `pytest.ini` мини-проекта, ноль тестов, нет бинарника pytest, таймаут дают `ok is False`; зелёный контроль даёт `ok is True` («pytest — тестов: 2»). Тест `test_pytest_addopts_env_does_not_narrow_the_suite` доказывает защиту `env_extra`, а контрольный запуск без `env_extra` с тем же фильтром действительно красный.
- **Решение владельца «Повтор при записи сервиса».** `db_unchanged_check` при `before != after` спрашивает `service_write_evidence(window)`: сервис `assistant-worker` active (только `systemctl is-active`) И время изменения БД (максимум по `assistant.db` и `assistant.db-wal`) внутри окна [начало замера «до»; конец замера «после»]. Только тогда `quiet_remeasure()` берёт хеш, ждёт `REMEASURE_WAIT_S = 5` с и берёт хеш снова; совпали - строка зелёная, а в info явно: «обнаружена запись сервиса assistant-worker в окне прогона ... SHA-256 до/после не совпали; повторное измерение в тихом окне (5 с) дало совпадение двух замеров: <префикс>». Иначе (повтор не совпал, сервис не active, mtime вне окна, окна нет, любой хеш None, сбой свидетельства или замера) - КРАСНЫЙ как раньше, во фразе остаётся «страж tests/live_db_guard.py». Повтор один: в функции нет циклов (проверяет AST-тест). Настоящая запись теста при простаивающем сервисе по-прежнему красная.
- **Первый полный прогон на чистом дереве (Task 3).** `python3 scripts/gate.py --save-pytest-output ...`: 10 строк ✓, 0 ✗, `ИТОГ: ЗЕЛЁНЫЙ`, rc 0.

## Базовая линия полного прогона

| Показатель | Значение |
|---|---|
| Тесты assistant-core | 789 passed, 0 skipped/xfail/xpass/deselected (pytest-часть 1 мин 54 с, 35 предупреждений) |
| Тесты assistant-shared | 91 passed |
| Длительность всего гейта | 2 мин 16 с (real), оценка плана 5-6 мин оказалась завышенной |
| Строка хеша | `SHA-256 до/после совпали: 88aaf13e6cbd` (расхождения не было, повтор не вызывался) |
| Строки ✓ / ✗ | 10 / 0 |
| `git status --short` после прогона | новых неотслеживаемых файлов нет (остались только `.planning/config.json`, `milestone.lock`, `state.json` оркестратора) |
| `git -C /opt/assistant-shared status --short` | пусто |
| Повторы прогона | не потребовались, прогон один |

### Сравнение списка имён в `data/` (допущение A7 / T-01-15)

До прогона: `assistant.db`, `assistant_worker.session`, `benchmarks`, `methodist`, `telethon_userbot.session`.
После прогона: те же плюс **`assistant.db-shm` (32 КБ) и `assistant.db-wal` (0 байт)**.

**Допущение A7 подтверждено.** Чтение боевой БД в режиме `mode=ro` оставляет в `data/` пустые sidecar-файлы WAL. Процессов, держащих файлы открытыми, нет (проверено по `/proc/*/fd`). Файлы в `.gitignore` (`data/`), в git не попадают, SQLite при следующем открытии обрабатывает пустой WAL штатно, поэтому вреда нет. Проверено на синтетической БД в tmp: первое ro-чтение создаёт `-wal` и `-shm`, повторные чтения mtime `-wal` не меняют. Файлы я не удалял (каталог `data/` боевой, не трогаем). Вопрос вынесен в `deferred-items.md` (удалять после прогона или нет, решить владельцу/Phase 3).

## Task Commits

1. **Task 1: строки assistant-shared и проверка hook** - `faab34e` (feat)
2. **Task 2: красные кейсы на мини-проектах** - `84e4eb5` (test)
3. **Решение владельца: один повтор замера хеша при записи сервиса** - `5ac98b4` (feat)
4. **Task 3:** полный прогон без изменения файлов, коммита нет

**Plan metadata:** следующий коммит docs(01-05).

## Files Created/Modified

- `scripts/gate.py` - `shared_pytest_env`, `hook_installed_check`, `_safe_hook_step`, `_service_state`, `_db_latest_mtime`, `service_write_evidence`, `quiet_remeasure`, `REMEASURE_WAIT_S`, расширенные `db_unchanged_check` и `_run_all` (окно измерения, 10 строк)
- `tests/test_gate.py` - тесты hook, порядка и состава строк, отказоустойчивости, повтора при записи сервиса; два старых теста порядка обновлены под 10 строк
- `tests/test_gate_red_cases.py` - 10 тестов красных кейсов и зелёного контроля на мини-проектах

## Decisions Made

- Решение владельца 2026-10-09 «Повтор при записи сервиса» реализовано как уточнение, сохраняющее строгость: смягчение только при трёх совпавших условиях, один повтор, пометка в info, страж `tests/live_db_guard.py` остаётся основной защитой (формулировка в красном detail сохранена). Запись зафиксирована в STATE.md.
- В свидетельство записи сервиса включён mtime `assistant.db-wal` (запись в WAL основной файл не меняет), `-shm` не включён (его меняют и читатели). Компромисс: при самом первом ro-чтении, создающем `-wal`, mtime попадает в окно; тогда повтор всё равно требует двух совпавших замеров.
- Общий принцип: любая неизвестность в свидетельстве (systemctl недоступен, БД не найдена) означает отказ от повтора.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Два существующих теста `_run_all` не учитывали строки shared и hook**
- **Found during:** Task 1
- **Issue:** `test_run_all_measures_hash_after_pytest_core_and_before_other_rows` и `test_run_all_isolates_pytest_db_and_removes_temp_dir` рассчитывали на 7 шагов, а `seen.update(kw)` перезаписывался вторым вызовом pytest (shared).
- **Fix:** заглушка `_safe_hook_step`, новая ожидаемая последовательность событий, `seen` обновляется только для `REPO_CORE`.
- **Files modified:** tests/test_gate.py
- **Committed in:** faab34e

### Изменения относительно текста плана

- **Решение владельца вне плана.** Оркестратор передал решение владельца, которого нет в тексте 01-05-PLAN.md; реализовано отдельным коммитом `5ac98b4` между Task 2 и Task 3, чтобы Task 3 (полный прогон) шёл уже с ним.
- **`test_run_all_never_aborts_on_step_exception` и `test_shared_rows_are_separate`** вошли в коммит Task 1, а не Task 2 (они тестируют `_run_all`, который меняется в Task 1).
- **Проверка Task 3** `grep "SHA-256 до/после совпали"` в ветке с повтором не найдёт эту фразу (информация там честно говорит «до/после не совпали»). В фактическом прогоне повтор не требовался, все условия `<verify>` выполнены буквально: rc 0, 10 ✓, 0 ✗, `ИТОГ: ЗЕЛЁНЫЙ`, строка хеша есть. Прогон выполнен с `--save-pytest-output` (как в action), а не буквальной командой из `<verify>`, повторно запускать не стал: условия проверены по сохранённому выводу.
- **Таймаут/время:** оценка плана 5-6 мин для полного гейта оказалась завышенной (2 мин 16 с).

**Total deviations:** 1 auto-fixed (Rule 1), 4 процессные заметки
**Impact on plan:** безопасность и строгость не ослаблены.

## Issues Encountered

- Допущение A7 подтверждено (см. выше): sidecar-файлы WAL в `data/` после ro-чтения. Вреда нет, оставлено в `deferred-items.md`.
- RED-стадия Task 1 и повтора: тесты писались первыми и падали на `AttributeError` / `TypeError` отсутствующих функций (1 красный в срезе `-x` для Task 1, 18 красных для повтора), затем зеленели. Task 2 зелёный с первого запуска, потому что тестирует уже существующий `run_pytest_step`; их осмысленность проверена зелёным контролем и контрольным запуском без `env_extra`. `workflow.tdd_mode` не включён, отдельных `test(...)` коммитов для TDD-пары не делалось.

## Known Stubs

None.

## Threat Flags

None. Новых сетевых точек и путей аутентификации нет. Меры плана: T-01-13 (красные строки на каждую ветку отказа, тесты), T-01-14 (пустой `PYTEST_ADDOPTS` для обоих pytest, тест на сужение), T-01-15 (сравнение списка файлов `data/`, результат выше), T-01-SC (новых зависимостей нет, добавлен только stdlib-модуль `time`).

## Self-Check: PASSED

- FOUND: scripts/gate.py, tests/test_gate.py, tests/test_gate_red_cases.py
- FOUND коммиты (предки HEAD): faab34e, 84e4eb5, 5ac98b4
- `tests/test_gate.py` + `tests/test_gate_red_cases.py`: 154 passed; полный гейт: 10 ✓, ИТОГ ЗЕЛЁНЫЙ, rc 0
- `grep -c REPO_SHARED scripts/gate.py` = 5 (4 и более)

## Next Phase Readiness

- `python3 scripts/gate.py` теперь единственная команда проверки обоих репозиториев и не зависит от `/opt/chat-app/scripts/gate.py` (кроме побайтной сверки двух общих тестовых файлов персоны, только чтение).
- Для 01-08..01-10 и последующих фаз: красный по строке БД при `active` сервисе и совпавшем окне больше не требует ручного повтора; настоящая запись при простаивающем сервисе красная.
- Открытый вопрос владельцу: sidecar-файлы WAL в `data/` после прогона (`deferred-items.md`).

---
*Phase: 01-sobstvennyy-geyt-kachestva-assistant-core*
*Completed: 2026-10-09*
