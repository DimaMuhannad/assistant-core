---
phase: 02-bezopasnost-privatnost-i-nahodki-revyu
plan: 04
subsystem: infra
tags: [deploy, security, sqlite-backup, root-hardening, WR-08, WR-09, D-17]

# Dependency graph
requires:
  - phase: 01-sobstvennyy-geyt-kachestva-assistant-core
    provides: скрипт выкатки scripts/deploy.py и находки код-ревью WR-08 (запись состояния и отчёта от root) и WR-09 (резервная копия и проверка дерева git)
provides:
  - make_db_copy: chmod 0700 только у каталога, созданного этим вызовом; существующий каталог принимается только собственный и без битов группы и остальных, иначе отказ без изменений
  - проверка «внутри дерева git» по самому пути и всем существующим предкам (запись .git каталогом или файлом), до создания каталога
  - _write_private: атомарная запись через временный файл рядом с целью (O_CREAT|O_EXCL|O_NOFOLLOW, 0600) и os.replace
  - STATE_FILE_DEFAULT = /var/lib/assistant-core/smoke-state.json; каталог создаётся с правами 0700 при первом запуске
  - load_state: отказ для символической ссылки, чужого владельца и битов группы или остальных
  - validate_report_path: отказ для символической ссылки и для существующего не-обычного файла
affects: [02-14 (disposition WR-08 и WR-09), 02-15 (первая живая выкатка с --backup и --restart)]

# Actuals (#2632) — chars/4 по реальному диффу, не счётчик харнесса
actuals:
  tokens: 8266
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Атомарная запись: временный файл рядом с целью, затем os.replace; ссылка на месте файла заменяется, а не открывается"
    - "Чтение состояния через O_NOFOLLOW с fstat по дескриптору (без окна между проверкой и чтением)"
    - "chmod только у каталога, созданного этим вызовом; существующий каталог проверяется и не меняется"

key-files:
  created: []
  modified:
    - scripts/deploy.py
    - tests/test_deploy_script.py
    - docs/OPS_DEPLOY.md

key-decisions:
  - "WR-09: существующий каталог копий принимается только если он принадлежит текущему пользователю и mode & 0o077 == 0; иначе BackupPathError, права не меняются, копия не создаётся"
  - "WR-09: отказ «внутри git», если путь, CORE_DIR или любой существующий предок содержит .git (каталог или файл worktree); проверка lexists, поэтому битая ссылка на .git тоже отказ"
  - "WR-08: состояние читается через os.open(O_NOFOLLOW) и fstat по дескриптору вместо отдельного os.lstat: та же проверка, но без окна подмены между проверкой и чтением (уточнение формулировки плана)"
  - "WR-08: путь состояния по умолчанию в /var/lib/assistant-core (0700); для пользовательского --state-file родитель обязан существовать, как и раньше"
  - "WR-08: validate_report_path проверяет символическую ссылку по неразрешённому пути (до resolve()), иначе resolve() скрыл бы ссылку"
  - "Временный файл записи имеет вид .<имя>.<hex16>.tmp рядом с целью; перед os.replace выполняется fsync"
  - "Режим чтения по умолчанию, белый список команд и правило «рестарт только по разрешению владельца» не изменены"

patterns-established:
  - "Проверка каталога под root: создать 0700 и менять права только у созданного каталога, существующий валидировать (владелец, mode & 0o077) и отвергать без изменений"
  - "Тесты не трогают /var/lib и боевые пути: STATE_FILE_DEFAULT подменяется монкипатчем, владелец через подмену os.geteuid"

requirements-completed: []

coverage:
  - id: D1
    description: "Резервная копия не меняет права существующего каталога: широкие права и чужой владелец дают BackupPathError без изменений"
    verification:
      - kind: unit
        ref: "tests/test_deploy_script.py#test_backup_refuses_existing_directory_with_wide_mode_and_keeps_its_mode"
        status: pass
      - kind: unit
        ref: "tests/test_deploy_script.py#test_backup_refuses_existing_directory_of_other_owner_without_changes"
        status: pass
      - kind: unit
        ref: "tests/test_deploy_script.py#test_backup_chmods_only_the_directory_it_created"
        status: pass
    human_judgment: false
  - id: D2
    description: "Каталог копий внутри чужого репозитория (предок с .git) отвергается до создания каталога, включая путь через символическую ссылку"
    verification:
      - kind: unit
        ref: "tests/test_deploy_script.py#test_backup_rejects_directory_under_foreign_git_repository_before_creating_it"
        status: pass
    human_judgment: false
  - id: D3
    description: "Запись состояния поверх символической ссылки заменяет ссылку и не меняет её цель"
    verification:
      - kind: unit
        ref: "tests/test_deploy_script.py#test_write_private_replaces_symlink_and_never_touches_its_target"
        status: pass
    human_judgment: false
  - id: D4
    description: "load_state отказывает для символической ссылки, битов группы или остальных и чужого владельца; путь состояния по умолчанию в /var/lib с каталогом 0700"
    verification:
      - kind: unit
        ref: "tests/test_deploy_script.py#test_load_state_refuses_symlink_to_state_file"
        status: pass
      - kind: unit
        ref: "tests/test_deploy_script.py#test_load_state_refuses_group_or_other_readable_file"
        status: pass
      - kind: unit
        ref: "tests/test_deploy_script.py#test_load_state_refuses_file_of_other_owner"
        status: pass
      - kind: unit
        ref: "tests/test_deploy_script.py#test_save_state_creates_default_directory_with_0700"
        status: pass
    human_judgment: false
  - id: D5
    description: "validate_report_path отказывает для символической ссылки (в том числе на новый путь) и для FIFO"
    verification:
      - kind: unit
        ref: "tests/test_deploy_script.py#test_validate_report_path_rejects_symlink_even_to_new_target"
        status: pass
      - kind: unit
        ref: "tests/test_deploy_script.py#test_validate_report_path_rejects_non_regular_file"
        status: pass
    human_judgment: false
  - id: D6
    description: "docs/OPS_DEPLOY.md описывает новый путь состояния и новые отказы; сверка с константой STATE_FILE_DEFAULT"
    verification:
      - kind: unit
        ref: "tests/test_deploy_script.py#test_docs_drop_old_state_path_and_describe_new_refusals"
        status: pass
    human_judgment: false

# Metrics
plan_head_before: 15c66c0806bec63741c8478df68810101af7aea4
plan_head_after: 8f70aca780c414bcda60198857e638f061073813
duration: не измерялась (время старта не зафиксировано в начале выполнения)
completed: 2026-10-10
status: complete
---

# Phase 02 Plan 04: Закрытие WR-08 и WR-09 в scripts/deploy.py (укрепление записи от root)

**Резервная копия не меняет права чужих каталогов и не ложится в дерево любого git-репозитория; состояние смоука и отчёт пишутся атомарно без следования по символическим ссылкам, а путь состояния перенесён в /var/lib/assistant-core (0700).**

## Performance

- **Duration:** не измерялась (время старта не зафиксировано)
- **Started:** не зафиксировано
- **Completed:** 2026-10-10T12:22:05Z (коммит задачи 2)
- **Tasks:** 2 из 2
- **Files modified:** 3 (`scripts/deploy.py`, `tests/test_deploy_script.py`, `docs/OPS_DEPLOY.md`)

## Accomplishments

- WR-09: `make_db_copy` меняет права только у каталога, созданного этим вызовом; существующий каталог с чужим владельцем или с битами группы и остальных отвергается (`BackupPathError`) до любых изменений
- WR-09: проверка «внутри дерева git» распространена на все существующие предки пути и на запись `.git` (каталог или файл worktree); отказ происходит до создания каталога
- WR-08: `_write_private` пишет через временный файл рядом с целью (O_EXCL|O_NOFOLLOW, 0600) и `os.replace`; подложенная ссылка заменяется, цель ссылки не меняется
- WR-08: `load_state` отказывает для символической ссылки, чужого владельца и битов группы или остальных; вердикт смоука нельзя подменить подложенным файлом
- WR-08: путь состояния по умолчанию `/var/lib/assistant-core/smoke-state.json`, каталог создаётся с правами 0700; существующий каталог проверяется тем же правилом, что и каталог копий
- WR-08: `validate_report_path` отказывает для символической ссылки и для существующего не-обычного файла (FIFO, каталог)
- Документ `docs/OPS_DEPLOY.md` обновлён: таблица флагов, разделы 6, 7, 8, 10

## Task Commits

Each task was committed atomically:

1. **Task 1: WR-09 — chmod только созданного каталога, отказ при небезопасном существующем, проверка .git у предков** - `d3d5cd7` (fix)
2. **Task 2: WR-08 — безопасная запись состояния и отчёта, путь состояния в /var/lib, проверка файла при чтении** - `8f70aca` (fix, TDD: тесты написаны первыми, 11 красных, затем реализация)

**Plan metadata:** будет создан отдельным коммитом docs после записи этого файла.

## Находка → изменение → тест

| Находка | Изменение в scripts/deploy.py | Тесты (tests/test_deploy_script.py) |
|---|---|---|
| WR-09: chmod чужого существующего каталога | `_prepare_private_dir`: `os.makedirs(mode=0o700)`, `os.chmod` только при создании; для существующего `lstat` и отказ при не-каталоге, чужом uid или `mode & 0o077` | `test_backup_refuses_existing_directory_with_wide_mode_and_keeps_its_mode`, `test_backup_refuses_existing_directory_of_other_owner_without_changes`, `test_backup_accepts_own_private_directory_and_does_not_chmod_it`, `test_backup_chmods_only_the_directory_it_created` |
| WR-09: «внутри git» только для CORE_DIR | `_inside_git_tree`: путь, CORE_DIR и все существующие предки с `.git` (lexists) | `test_backup_rejects_directory_under_foreign_git_repository_before_creating_it` (каталог, worktree-файл `.git`, символическая ссылка на чужой репозиторий) |
| WR-08: запись по предсказуемому пути в /var/tmp | `_write_private`: временный файл O_EXCL|O_NOFOLLOW, fchmod 0600, fsync, `os.replace` | `test_write_private_replaces_symlink_and_never_touches_its_target`, `test_write_private_leaves_no_temp_file_and_replaces_content` |
| WR-08: подложенное состояние меняет вердикт | `_read_state_text`: `os.open(O_NOFOLLOW)` и `fstat` по дескриптору: ссылка, не-файл, чужой uid, mode & 0o077 | `test_load_state_refuses_symlink_to_state_file`, `test_load_state_refuses_group_or_other_readable_file`, `test_load_state_refuses_file_of_other_owner` |
| WR-08: путь состояния в /var/tmp | `STATE_FILE_DEFAULT` = `/var/lib/assistant-core/smoke-state.json`; `_prepare_state_dir` для пути по умолчанию | `test_state_file_default_lives_in_var_lib_and_is_not_in_var_tmp`, `test_save_state_creates_default_directory_with_0700`, `test_save_state_refuses_existing_default_directory_with_wide_mode`, `test_save_state_custom_path_requires_existing_parent`, `test_main_refuses_unsafe_default_state_directory_before_any_command` |
| WR-08: отчёт по символической ссылке | `validate_report_path`: проверка `is_symlink()` по неразрешённому пути; отказ для существующего не-обычного файла | `test_validate_report_path_rejects_symlink_even_to_new_target`, `test_validate_report_path_rejects_non_regular_file` |
| WR-08 и WR-09: регламент в документе | `docs/OPS_DEPLOY.md`: флаги, разделы 6, 7, 8, 10 | `test_docs_drop_old_state_path_and_describe_new_refusals`, прежние `test_docs_numbers_match_script_constants` и `test_docs_cover_all_cli_flags` |

## Files Created/Modified

- `scripts/deploy.py` - `_inside_git_tree`, `_prepare_private_dir`, `make_db_copy`, `_write_private`, `_prepare_state_dir`, `_state_dir_refusal`, `save_state`, `_read_state_text`, `load_state`, `validate_report_path`, `STATE_FILE_DEFAULT`, ветки `except StateError` и предварительная проверка в `main`
- `tests/test_deploy_script.py` - 13 новых тестов и переписанный тест прав каталога; все тесты используют `tmp_path` и монкипатч, `/var/lib` не затрагивается
- `docs/OPS_DEPLOY.md` - таблица флагов (`--backup-dir`, `--report`, `--state-file`), раздел 6 (путь состояния, отказы фазы), раздел 7 (правила каталога копий), раздел 8 (предварительная проверка до рестарта), раздел 10 (отчёт)

## Decisions Made

- Существующий каталог копий принимается только собственный и без битов группы и остальных; иначе отказ без изменений (WR-09, D-17)
- «Внутри git» проверяется по пути, CORE_DIR и всем существующим предкам; запись `.git` может быть каталогом или файлом worktree (WR-09)
- Состояние читается через `O_NOFOLLOW` и `fstat` по дескриптору вместо отдельного `os.lstat`: та же проверка без окна между проверкой и чтением (WR-08)
- Путь состояния по умолчанию в `/var/lib/assistant-core` с каталогом 0700; для пользовательского `--state-file` родитель обязан существовать, как раньше (WR-08)
- `validate_report_path` проверяет ссылку до `resolve()`, иначе разрешение скрыло бы ссылку (WR-08)
- Режим чтения по умолчанию, белый список команд и правило «рестарт только по разрешению владельца» не изменены

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Предварительная проверка каталога состояния до рестарта и до смоука**
- **Found during:** Task 2 (WR-08)
- **Issue:** план проверяет каталог состояния только при записи. Если `/var/lib/assistant-core` окажется небезопасным, `--restart` выполнит рестарт сервиса, а сохранение состояния упадёт уже после него: вердикта не будет
- **Fix:** `_state_dir_refusal` вызывается в `main` до ветки `--restart` и до `run_smoke`; при отказе код 2 и ни одной команды (systemctl не вызывается)
- **Files modified:** `scripts/deploy.py`
- **Verification:** `test_main_refuses_unsafe_default_state_directory_before_any_command` (проверяет `runner.calls == []` для смоука и для `--restart`)
- **Committed in:** `8f70aca` (задача 2)

**2. [Rule 1 - Bug] StateError из save_state не перехватывался**
- **Found during:** Task 2 (WR-08)
- **Issue:** `save_state` теперь может поднять `StateError`, а три места сохранения (`_run_phase`, `_run_restart`, `main`) ловили только `OSError`: исключение ушло бы трейсбеком
- **Fix:** в каждом месте добавлена ветка `except StateError` с печатью текста отказа и кодом 2 (текст без значений)
- **Files modified:** `scripts/deploy.py`
- **Verification:** прогон `tests/test_deploy_script.py` (197 тестов зелёные), включая тесты фаз и рестарта
- **Committed in:** `8f70aca` (задача 2)

**Total deviations:** 2 auto-fixed (1 missing critical, 1 bug). Оба исправления следуют из изменения самого плана и не расширяют его объём.
**Impact on plan:** границы плана соблюдены; белый список, режим чтения и правило рестарта не менялись.

## Issues Encountered

- Устаревший ledger `.git/gsd-plan-head-before-02-04` (указывал на `c5820eb`) перезаписан реальной базой `15c66c0` по инструкции оркестратора; метрики считаются от `15c66c0`.
- В рабочем дереве до начала работы были неотносящиеся изменения: `.planning/config.json` (M) и неотслеживаемые `.planning/milestone.lock`, `.planning/state.json`. Они не индексировались и не коммитились.
- Фактический `actuals.tokens` = 8266 (chars/4 по реальному диффу, 33066 символов) против `estimate.tokens` = 70000 из плана. Значение записано как есть, не округлено.
- Длительность не измерялась: время старта не записано в начале выполнения.

## Verification

- `.venv/bin/pytest tests/test_deploy_script.py` - 197 passed (до правок: 11 красных тестов задачи 2, затем зелёные)
- `.venv/bin/pytest tests/test_claude_md_gate_pointer.py tests/test_architecture_contract.py` - 8 passed
- `python3 scripts/deploy.py --help` - завершается с кодом 0, ничего не меняет
- `python3 scripts/gate.py` - ИТОГ: ЗЕЛЁНЫЙ (assistant-core pytest 871, assistant-shared pytest 145, security_shield, import-linter, дрейф персоны, хук; боевая БД SHA-256 до и после совпали)
- Проверено, что после прогона тестов нет `/var/lib/assistant-core` и `/var/tmp/assistant-core-smoke-state.json`
- В этом плане НЕ запускались: `--restart`, `--backup`, `systemctl`, запись в `/var/lib`; боевая БД `data/assistant.db` не открывалась (гейт читает только её хеш)

## User Setup Required

None - внешняя настройка не требуется.

## Known Stubs

None.

## Threat Flags

None - новых сетевых поверхностей и путей доверия не добавлено; изменения сужают существующие.

## Next Phase Readiness

- WR-08 и WR-09 закрыты кодом, тестами и документом; можно указать disposition в плане 02-14
- Первая живая выкатка (план 02-15) создаст `/var/lib/assistant-core` с правами 0700 при первом смоуке. Старый файл `/var/tmp/assistant-core-smoke-state.json` не мигрируется и не нужен: смоук пишет состояние заново
- Отчёт `--report` в `/var/tmp` теперь отвергает символические ссылки и не-обычные файлы; обычный новый путь работает как раньше
- Рестарт assistant-worker по-прежнему только по явному разрешению владельца; в этом плане сервис не трогался

## Self-Check: PASSED

Проверено: `scripts/deploy.py`, `tests/test_deploy_script.py`, `docs/OPS_DEPLOY.md` и этот SUMMARY существуют; коммиты `d3d5cd7` и `8f70aca` являются предками HEAD.

---
*Phase: 02-bezopasnost-privatnost-i-nahodki-revyu*
*Completed: 2026-10-10*
