---
phase: 01-sobstvennyy-geyt-kachestva-assistant-core
plan: 07
subsystem: ops
tags: [deploy, backup, sqlite-backup-api, systemd, restart, rollback-report, runbook]

requires:
  - phase: 01-sobstvennyy-geyt-kachestva-assistant-core
    provides: "Ядро scripts/deploy.py (план 01-06): раннер, белый список ensure_read_only, смоук, фазы без TTY, отчёт"
provides:
  - "scripts/deploy.py --backup: консистентная копия боевой БД (backup API, источник mode=ro) вне дерева git, права 0600 в каталоге 0700, integrity_check на копии (D-11)"
  - "scripts/deploy.py --restart: проверка чистого дерева, [копия], рестарт с таймаутом 300 с, ожидание новой инвокации и polling, окно старта, тот же смоук (D-10)"
  - "Отчёт о сбое выкатки: пронумерованные команды отката только печатаются, раннер их не получает (D-12)"
  - "docs/OPS_DEPLOY.md: процедура выкатки по-русски, обязанность Phase 3 вызвать --backup перед миграцией 0003"
affects: [01-10, phase-02, phase-03, phases 4-5, phases 7-9]

actuals:
  tokens: 20900
  tasks: 3
  commits: 3
plan_head_before: 255235c72dc5cf259dae9a24403af224629c014e
plan_head_after: 2705c32db9b49ee3c524a00454513e2abef33e38

tech-stack:
  added: []
  patterns:
    - "Команда рестарта формируется в одном месте (restart_service) и достижима только из ветки --restart; ensure_read_only её не пропускает"
    - "Откат только печатается: отчёт --report и файл состояния пишутся ДО печати отчёта об откате, после него раннер молчит"
    - "Дрейф документа и CLI ловит тест: каждый длинный флаг build_parser() должен встречаться в docs/OPS_DEPLOY.md, числа документа сверяются с константами скрипта"

key-files:
  created:
    - docs/OPS_DEPLOY.md
  modified:
    - scripts/deploy.py
    - tests/test_deploy_script.py

key-decisions:
  - "Команда рестарта вне белого списка ensure_read_only: белый список расширен только двумя read-only формами git (status --porcelain=v1 -z --untracked-files=all и rev-parse HEAD^)"
  - "Копия переводится в journal_mode=DELETE: она самодостаточна (один файл, без WAL), восстановление одним cp; в команды отката добавлено удаление -wal/-shm прежней БД"
  - "После готовности сервиса пауза STARTUP_TAIL_SECONDS (60 с) перед смоуком, иначе окно ошибок старта ещё не заполнено"
  - "Не удалось определить HEAD или проверить дерево: рестарт отменяется (rc 2) без единого вызова systemctl"
  - "--backup-dir без --backup и --backup/--restart вместе с фазами --await-help/--confirm-help отвергаются кодом 2"

patterns-established:
  - "Фейковый раннер со сценарием (RestartRunner) и перехват print в модуле: проверка порядка «команды раннера -> отчёт -> тишина»"

requirements-completed: [OPS-01]

coverage:
  - id: D1
    description: "--backup: проверенная копия боевой БД через read-only источник вне git, исходная БД не меняется, раннер не вызывается"
    requirement: OPS-01
    verification:
      - kind: unit
        ref: "tests/test_deploy_script.py#test_backup_creates_checked_copy_with_private_modes"
        status: pass
      - kind: unit
        ref: "tests/test_deploy_script.py#test_backup_does_not_change_source_database"
        status: pass
      - kind: unit
        ref: "tests/test_deploy_script.py#test_backup_rejects_directory_inside_repo_before_creating_it"
        status: pass
      - kind: unit
        ref: "tests/test_deploy_script.py#test_main_backup_creates_copy_prints_path_and_size_and_never_calls_runner"
        status: pass
    human_judgment: false
  - id: D2
    description: "Рестарт только по --restart: без флага недостижим, при грязном дереве отказ без systemctl, порядок копия-рестарт-ожидание-смоук"
    requirement: OPS-01
    verification:
      - kind: unit
        ref: "tests/test_deploy_script.py#test_without_restart_flag_runner_never_sees_restart"
        status: pass
      - kind: unit
        ref: "tests/test_deploy_script.py#test_restart_refused_on_dirty_tree"
        status: pass
      - kind: unit
        ref: "tests/test_deploy_script.py#test_restart_sequence_and_ready_wait"
        status: pass
      - kind: unit
        ref: "tests/test_deploy_script.py#test_restart_service_is_called_only_from_the_restart_branch"
        status: pass
    human_judgment: false
  - id: D3
    description: "Красный смоук после рестарта: отчёт и команды отката печатаются, автоотката нет"
    requirement: OPS-01
    verification:
      - kind: unit
        ref: "tests/test_deploy_script.py#test_red_smoke_after_restart_prints_rollback_and_runs_nothing"
        status: pass
      - kind: unit
        ref: "tests/test_deploy_script.py#test_rollback_commands_are_never_executed_by_the_script"
        status: pass
    human_judgment: false
  - id: D4
    description: "docs/OPS_DEPLOY.md описывает процедуру и совпадает с CLI (флаги, числа, обязанность Phase 3)"
    requirement: OPS-01
    verification:
      - kind: unit
        ref: "tests/test_deploy_script.py#test_docs_cover_all_cli_flags"
        status: pass
      - kind: unit
        ref: "tests/test_deploy_script.py#test_docs_phase3_backup_duty_before_migration_0003_in_one_paragraph"
        status: pass
    human_judgment: false
  - id: D5
    description: "Работа --backup и --restart на живом сервисе и боевой БД"
    verification: []
    human_judgment: true
    rationale: "Живой рестарт и живая копия в Phase 1 не выполнялись (сервисы заморожены, нет разрешения владельца); первый живой --backup запланирован в Phase 3, живой --restart в первой фазе с изменением рантайма"

duration: 21min
completed: 2026-10-09
status: complete
---

# Phase 1 Plan 07: Резервная копия, рестарт по флагу и документ выкатки Summary

**scripts/deploy.py получил `--backup` (копия боевой БД через sqlite3 backup API с источником `mode=ro` вне git, права 0600/0700, integrity_check) и `--restart` (чистое дерево, рестарт с ожиданием новой инвокации и polling, тот же смоук, при красном исходе отчёт с командами отката без автоотката); процедура описана в docs/OPS_DEPLOY.md, а тест следит, чтобы каждый флаг CLI был в документе.**

## Performance

- **Duration:** 21 мин (1253 с)
- **Started:** 2026-10-09T18:31:49Z
- **Completed:** 2026-10-09T18:52:42Z
- **Tasks:** 3
- **Files modified:** 3 (`scripts/deploy.py`, `tests/test_deploy_script.py` изменены, `docs/OPS_DEPLOY.md` создан)

## Accomplishments

- `--backup` (D-11): `make_db_copy` отвергает каталог внутри `CORE_DIR` до создания (включая путь через симлинк), создаёт каталог 0700 и файл 0600 через `O_EXCL` (существующая копия не перезаписывается), копирует backup API с источника `file:...?mode=ro`, переводит копию в `journal_mode=DELETE` (самодостаточный файл) и проверяет `PRAGMA integrity_check`; при любом сбое неполная копия удаляется. Печатаются путь и размер, содержимое нет, при ошибке только имя класса исключения. Единственное место открытия SQLite в скрипте (проверяет статический тест по ast). Тест на WAL-базе с незакоммиченным в основной файл хвостом доказывает, что хвост попадает в копию, а хеш логического дампа и состав каталога источника не меняются.
- `--restart` (D-10): `git_dirty_paths` разбирает `git status --porcelain=v1 -z --untracked-files=all` (с переименованиями и копиями) и игнорирует `.planning/`; при грязном дереве, сбое git или неизвестном HEAD выкатка отменяется с кодом 2 и ни один вызов systemctl не делается. Порядок: дерево, HEAD и родитель, [копия: сбой останавливает выкатку до рестарта], `restart_service` (прежняя инвокация, `systemctl restart assistant-worker` с таймаутом 300 с, опрос до смены InvocationID, `active` и строки «Run polling for bot», общий дедлайн 300 с), пауза окна старта 60 с, тот же `run_smoke`. Файл состояния и `--report` обновляются в обоих исходах.
- Откат (D-12): `build_rollback_report` печатает «ОТЧЁТ О СБОЕ ВЫКАТКИ», красные строки с очищенными деталями и нумерованные команды (revert; с копией ещё stop, cp, удаление `-wal`/`-shm`, start; без копии restart) и фразу «Автоотката нет: откат требует нового разрешения владельца». Тест перехватывает `print` и вызовы раннера и доказывает, что после отчёта раннер не получает ни одной команды, а за весь прогон нет revert, checkout, cp, stop, start и второго restart.
- Документ `docs/OPS_DEPLOY.md` (12 разделов, 193 строки): правила рестарта только после «да» владельца, таблица флагов, проверки смоука, окно ошибок и строгий D-08, фазы без TTY, резервная копия с обязанностью Phase 3 вызвать `--backup` перед миграцией `0003`, рестарт, откат, отчёт, ограничения. Тесты сверяют флаги `build_parser()`, числа и константы скрипта, нумерацию разделов, отсутствие `@`, токенов и секретов.

**Число тестов:** 180 в `tests/test_deploy_script.py` (было 122; по задачам: 139, 172, 180). Полный прогон набора assistant-core: **746 passed**, 0 skipped/deselected/xfail (`-o xfail_strict=true`). `python3 scripts/gate.py`: ИТОГ ЗЕЛЁНЫЙ (хеш боевой БД до и после совпал).
**Живой рестарт и живая копия не выполнялись.** `systemctl show assistant-worker -p InvocationID -p NRestarts` до плана и после: `InvocationID=40e9fe7aaf694e44974e2f7b55206f32`, `NRestarts=0` в обоих замерах. Боевая БД не открывалась (страж плана 01-01 не срабатывал).

## Task Commits

1. **Task 1: Резервная копия по --backup (tracer)** - `2b0df32` (feat)
2. **Task 2: Рестарт по --restart, ожидание готовности, отчёт об откате** - `2f6762c` (feat)
3. **Task 3: docs/OPS_DEPLOY.md и тест полноты флагов** - `2705c32` (docs)

**Plan metadata:** следующие коммиты docs(01-07).

## Files Created/Modified

- `scripts/deploy.py` - `make_db_copy`, `_integrity_ok`, `BackupError`/`BackupPathError`, `RestartResult`, `restart_service`, `git_dirty_paths`, `get_parent_head`, `build_rollback_report`, `_run_restart`/`_run_backup`, флаги `--backup`, `--backup-dir`, `--restart`, константы `BACKUP_DIR_DEFAULT`, `LIVE_DB`, `RESTART_TIMEOUT_S`, `READY_TIMEOUT_S`, `POLL_INTERVAL_S`
- `tests/test_deploy_script.py` - 58 новых тестов: копия, рестарт на сценарном раннере, отчёт об откате, статические свойства (T-01-21, T-01-22), документ
- `docs/OPS_DEPLOY.md` - процедура выкатки (OPS-01); черновик агента agy, проверен построчно

## Decisions Made

- Белый список `ensure_read_only` расширен только двумя read-only формами git; команда рестарта в него не входит и живёт в `restart_service` (в коде строка `"restart"` встречается ровно один раз).
- Копия в `journal_mode=DELETE`: одним `cp` восстанавливается без WAL; в команды отката добавлено удаление `-wal` и `-shm` прежней БД.
- Окно старта 60 с выдерживается после готовности сервиса перед смоуком (см. отклонение 1).
- Родитель HEAD берётся отдельной read-only командой `git rev-parse HEAD^` (допустим None).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Пауза окна ошибок старта перед смоуком после рестарта**
- **Found during:** Task 2
- **Issue:** смоук читает окно «polling плюс 60 с». Сразу после появления строки «Run polling for bot» это окно ещё не заполнено, и ошибки первых секунд работы прошли бы незамеченными, то есть строгий D-08 был бы ослаблен.
- **Fix:** после успешного `restart_service` выдерживается `STARTUP_TAIL_SECONDS` через внедряемый `sleep`, затем запускается смоук.
- **Files modified:** scripts/deploy.py, tests/test_deploy_script.py (`test_restart_sequence_and_ready_wait` проверяет паузу)
- **Committed in:** 2f6762c

**2. [Rule 2 - Missing Critical] Защита от несовместимых флагов и самодостаточность копии**
- **Found during:** Tasks 1-2
- **Issue:** `--backup`/`--restart` вместе с `--await-help`/`--confirm-help` молча игнорировались бы (ветка фаз выполнялась первой); `--backup-dir` без `--backup` создавал ложное ощущение, что копия делается; копия WAL-базы наследовала бы режим WAL и требовала sidecar-файлов при восстановлении.
- **Fix:** такие сочетания отвергаются кодом 2 до любых действий; копия переводится в `journal_mode=DELETE`; в отчёт об откате добавлено удаление `-wal`/`-shm`.
- **Files modified:** scripts/deploy.py, tests/test_deploy_script.py
- **Committed in:** 2b0df32, 2f6762c

**3. [Rule 1 - Bug] Устаревшая проверка «скрипт не содержит sqlite3»**
- **Found during:** Task 1
- **Issue:** тест плана 01-06 `test_script_does_not_import_src_and_does_not_open_database` запрещал слово `sqlite3`, что несовместимо с `--backup` по плану.
- **Fix:** заменён на `test_script_does_not_import_src_and_opens_sqlite_only_in_make_db_copy` (ast: `sqlite3.connect` только внутри `make_db_copy`, не более двух вызовов).
- **Files modified:** tests/test_deploy_script.py
- **Committed in:** 2b0df32

**4. [Процесс] Один коммит на задачу вместо RED/GREEN-коммитов**
- RED подтверждён прогоном до реализации в Task 1 (15 падений на отсутствующих функциях и параметре `live_db`) и в Task 2 (25 падений), как в плане 01-06; `workflow.tdd_mode` не включён, план имеет `type: execute`, отдельных `test(...)` коммитов нет.

**5. [Процесс] Правки черновика agy**
- Заголовок «Решение владельца про повтор при внешнем сбое» заменён на «Как решать про повтор при внешнем сбое» (это рекомендация документа, а не решение владельца); команды отката расписаны отдельно для случаев с `--backup` и без него (как печатает скрипт); добавлено пояснение, что ответ бота на `/help` подтверждается фазами без TTY. Остальное совпало с CONTEXT D-06..D-14 и реализацией.

---

**Total deviations:** 3 auto-fixed (2 Rule 2, 1 Rule 1), 2 процессные заметки
**Impact on plan:** безопасность усилена, объём и интерфейс (имена флагов и функций из плана) не изменены.

## Делегирование agy

Черновик `docs/OPS_DEPLOY.md` сделан агентом agy через `agy_task.sh run --mode edit --agent docs` (SUCCESS, 478 с, вход 262830, выход 50575 токенов Antigravity). Патч прочитан целиком, сверен с CONTEXT и кодом, правки внесены вручную, тест `test_docs_cover_all_cli_flags` и остальные тесты документа написаны Claude, задание очищено командой `clean`.

## Issues Encountered

- `security_shield --all` по всему репозиторию возвращает код 1 только из-за трёх известных ложных срабатываний `config/persona.yaml:44` (nda-keyword), как и ожидает verify плана; новых находок нет. Точное сравнение выполняет гейт (ЗЕЛЁНЫЙ).
- Допущение A6 (каталог копий `/var/backups/assistant-core`) остаётся флагом планировщика: живая проверка прав каталога произойдёт при первом живом `--backup` в Phase 3.

## Known Stubs

None.

## Threat Flags

None. Новых сетевых точек нет. Меры T-01-21 (рестарт в одном месте, только из ветки `--restart`, тесты и ast-проверка), T-01-22 (откат только печатается, раннер молчит после отчёта), T-01-23 (каталог вне git, права 0700/0600, путь и размер без содержимого), T-01-24 (путь `--report` вне `.git`, `--backup-dir` внутри репозитория отвергается), T-01-SC (только stdlib, пакеты не устанавливались) реализованы.

## Next Phase Readiness

- План 01-10 использует `--report`, `--await-help`, `--confirm-help` для read-only смоука на живом сервисе; план 01-08/09 не зависят от этого плана.
- Phase 3 обязана вызвать выкатку с `--backup` перед миграцией `0003` (зафиксировано в `docs/OPS_DEPLOY.md`, раздел 7).
- Первый живой `--restart` выполняется только по «да» владельца в первой фазе с изменением рантайма; допущение, что `/var/backups/assistant-core` можно создать с правами 0700, проверится тогда же.

## Self-Check: PASSED

- FOUND: scripts/deploy.py, tests/test_deploy_script.py, docs/OPS_DEPLOY.md
- FOUND коммиты: 2b0df32, 2f6762c, 2705c32 (предки HEAD)
- `grep -v '^\s*#' scripts/deploy.py`: `sqlite3.connect` 2 раза, `"restart"` 1 раз, `runner(["git", "revert"` 0 раз
- Полный прогон: 746 passed, 0 skipped/deselected/xfail; gate: ИТОГ ЗЕЛЁНЫЙ
- Пре-коммит Security Shield зелёный на всех трёх коммитах; tests/test_hardcode_scanner.py зелёный

---
*Phase: 01-sobstvennyy-geyt-kachestva-assistant-core*
*Completed: 2026-10-09*
