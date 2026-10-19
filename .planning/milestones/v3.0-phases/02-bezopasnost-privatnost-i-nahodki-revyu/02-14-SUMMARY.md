---
phase: 02-bezopasnost-privatnost-i-nahodki-revyu
plan: 14
subsystem: verification
tags: [reachability, review-findings, disposition, debt-03, d-17, d-21, evidence]
status: complete

requires:
  - phase: 02-bezopasnost-privatnost-i-nahodki-revyu
    provides: "планы 02-01..02-13: код, тесты и закрытие находок ревью"
provides:
  - "tests/test_phase2_reachability.py: 8 тестов достижимости из рантайма без рестарта"
  - "01-REVIEW-DISPOSITION.md: CR-01 и WR-01..WR-13 в fixed (14), IN-01..IN-06 deferred (6)"
  - "REQUIREMENTS.md: запись DEBT-03"
  - "02-VERIFICATION-EVIDENCE.md: доказательства и перечень R1-R5 для верификатора и плана 02-15"
  - "deferred-items.md: плавающий тест test_concurrent_confirmations_isolation"
affects: [02-15]

actuals:
  tokens: 12160
  tasks: 3
  commits: 3
plan_head_before: dbffdae8bf3a45dfedf5a589545d8af1c4b3d975
plan_head_after: 5f36fb81009307769446449b8191daa64c4769ab

key-files:
  created:
    - tests/test_phase2_reachability.py
    - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-VERIFICATION-EVIDENCE.md
    - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/deferred-items.md
  modified:
    - .planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-REVIEW-DISPOSITION.md
    - .planning/REQUIREMENTS.md

key-decisions:
  - "Каждая находка помечена fixed только после зелёного прогона её тестов: 119 тестов (103 в assistant-core, 16 в chat-app из /opt/chat-app), 0 skipped, xfail, deselected"
  - "Пометка fixed для WR-03 сохраняет принятый остаточный риск T-02-45 (запись в Source и evidence), для WR-07 остаётся ограничение жёсткой ссылки"
  - "Плавающий тест HITL записан в deferred-items.md и не чинился (вне области плана, assistant-shared read-only)"

requirements-completed: []
---

# Phase 2 Plan 14: достижимость, закрытие находок ревью, доказательства Summary

Новые функции фазы 2 доказаны достижимыми из рантайма без рестарта (роутер бота, планировщик почты, hook и обёртка shield), 14 находок ревью закрыты по прогнанным тестам, собран черновик evidence с перечнем R1-R5 для плана 02-15.

## Что сделано

- **Task 1 (tracer), коммит `ee410ba`:** `tests/test_phase2_reachability.py`, 8 passed. Проверено: в роутере `EmailBotHandler` зарегистрированы `handle_cmd_help` (команды start, help), `handle_cmd_clear_dialog` (clear, reset), `handle_user_text`, `handle_user_voice`; обработчик `/help`, взятый из роутера, отправляет текст с блоком приватности персоны по умолчанию; обработчик текста, взятый из роутера, на фразу «очисти диалог» оставляет историю нетронутой и отвечает предупреждением с `/clear` без карточки; AST `main.py`: один `add_job` на `run_email_collector_cycle` с `id="email_collector_job"`, цикл вызывает `_announce_email_ai_notice`, `main()` создаёт `EmailBotHandler` и подключает его роутер; hook одной строкой `exec` без флагов допуска; `audit_repository` вызывается только с `check_staged_only` и `workspaces`, в обёртке нет констант слов; подпроцесс shield на временном репозитории даёт код 1 на синтетическом секрете (значение не печатается) и код 0 на чистом. Слов NDA и организаций в файле нет (проверено по данным персоны).
- **Task 2, коммит `d1c58c9`:** перечень `/var/tmp/gsd-phase02-closure/tests.txt`, прогон тестов, disposition и DEBT-03.
- **Task 3, коммит `5f36fb8`:** три репозитория, базовая линия сервиса, read-only смоук, `02-VERIFICATION-EVIDENCE.md`, `deferred-items.md`.

## Находка -> тест -> результат прогона

Вывод: `/var/tmp/gsd-phase02-closure/closure-run.txt` (assistant-core `103 passed`, chat-app из `/opt/chat-app` `16 passed`).

| Находка | Тесты (представители) | План | Тестов в прогоне | Итог |
|---|---|---|---|---|
| CR-01 | `test_sync_rejects_hostile_remote_names` (7 имён), `test_sync_rejects_symlink_pointing_outside_uploads` | 02-03 | 11 | fixed |
| WR-01 | `test_sync_runs_blocking_drive_calls_off_event_loop` | 02-03 | 1 | fixed |
| WR-02 | `test_server_backup_archive_methods_are_removed` | 02-03 | 1 | fixed |
| WR-03 | `test_db_unchanged_check_mitigation_*`, `test_integrity_snapshot_*`, `test_compare_integrity_*` | 02-13 | 18 | fixed (остаточный риск принят) |
| WR-04 | `test_compare_shield_findings_same_count_on_another_line_is_new_and_stale`, `test_run_shield_step_core_same_count_on_a_replaced_line_is_red` | 02-13 | 24 | fixed |
| WR-05 | `test_gate_environment_path_refused` x8 (chat-app) | 02-09 | 8 | fixed |
| WR-06 | `test_fallback_gate_warns_in_stderr_and_summary` (chat-app) | 02-09 | 3 | fixed |
| WR-07 | `test_absolute_live_path_is_blocked_regardless_of_core_dir`, `test_symlink_with_other_name_to_live_path_is_blocked` | 02-05 | 12 | fixed |
| WR-08 | `test_write_private_replaces_symlink_and_never_touches_its_target`, `test_load_state_refuses_symlink_to_state_file` | 02-04 | 17 | fixed |
| WR-09 | `test_backup_refuses_existing_directory_with_wide_mode_and_keeps_its_mode` | 02-04 | 5 | fixed |
| WR-10 | `test_autouse_fixture_replaces_*`, `test_db_checks_run_without_any_real_subprocess` | 02-13 | 4 | fixed |
| WR-11 | `test_menu_command_rendering` | 02-05 | 1 | fixed |
| WR-12 | `test_find_backup_*` (5), `test_download_file_writes_collected_bytes` | 02-03 | 7 | fixed |
| WR-13 | `test_rules_files_do_not_name_legacy_gate_command`, `test_legacy_gate_patterns_self_check` | 02-05 | 2 | fixed |
| T-uo4-02 | `test_scripts_directory_replaced_by_symlink_refused`, `test_symlinked_gate_path_refused_before_agent` x2, `test_gate_path_turned_into_symlink_before_gate_reverts_patch` (chat-app) | 02-09 | 5 | закрыт, AR-01-04 помечена в `01-SECURITY.md` |

Disposition: **закрыто 14** (CR-01, WR-01..WR-13), **открыто 0**, **отложено 6** (IN-01..IN-06, бэклог, DEBT-03). Требование DEBT-03 записано в раздел v2 «Найдено при онбординге» как будущее требование, не как выполненное.

## Результаты гейтов и проверок

- `python3 scripts/gate.py` (assistant-core, `/var/tmp/gsd-phase02-verify/gate-run.txt`): **ИТОГ: ЗЕЛЁНЫЙ**; 11 строк ✓; assistant-core 977 тестов; assistant-shared 197; «SHA-256 до/после совпали».
- `cd /opt/chat-app && python3 scripts/gate.py`: первый прогон **КРАСНЫЙ** по одной строке (assistant-core pytest, 1 failed, 976 passed: плавающий `test_concurrent_confirmations_isolation`, `database is locked`); повторный прогон без правок **ИТОГ: ЗЕЛЁНЫЙ** (chat-app 277, assistant-core 977, боевая БД не изменена). Выводы: `chatapp-gate-run.txt`, `chatapp-gate-run2.txt` в `/var/tmp/gsd-phase02-verify/`.
- pytest assistant-shared: 197 passed. pytest chat-app: 277 passed (в составе гейта chat-app; отдельно 16 тестов адаптера в прогоне закрытия).
- `scripts/security_shield.py . --all`: ровно 3 находки, все в `config/persona.yaml:44`, rc=1 (известные, D-21).
- HEAD: assistant-core `5f36fb8` (после коммита SUMMARY будет ещё один), assistant-shared `022bb3e`, chat-app `f92d95f`.
- Базовая линия сервиса (`baseline.txt`): `InvocationID=40e9fe7aaf694e44974e2f7b55206f32`, `NRestarts=0`, `MainPID=295112`; после всех прогонов значения те же.
- Read-only смоук (`python3 scripts/deploy.py --state-file /var/tmp/gsd-phase02-verify/smoke-state.json`, без `--restart` и `--backup`): автоматическая часть **ЗЕЛЁНАЯ** (сервис active, журнал доступен, нет ошибок старта, polling запущен, планировщик 10 из 10, `getMe` жив); итог «ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ» (фаза `/help` с участием владельца принадлежит плану 02-15).

## Deviations from Plan

### Не выполненные буквально критерии

**1. Дерево chat-app не пусто.** `git -C /opt/chat-app status --short` показывает `?? .watchdog_disabled` (пустой неотслеживаемый файл, создан 2026-10-10 11:58 UTC, до начала плана; тот же факт отмечен в SUMMARY 02-07). Файл не мой и не менялся; chat-app в плане read-only. Влияние на рестарт: `deploy.py --restart` проверяет чистоту только дерева assistant-core (`git_dirty_paths`), поэтому рестарт `assistant-worker` он не блокирует. Дерево assistant-core вне `.planning/` и дерево assistant-shared пусты. Записано в evidence («Открытые пункты», п. 6).

**2. Нашлось расхождение в плане.** Task 2 называет план 02-08 источником тестов WR-08/WR-09; на деле их закрыл план 02-04 (02-08 закрыл обёртку shield, SECF-01). Тесты взяты из 02-04.

### Auto-fixed Issues

Нет правок кода.

### Найдено вне области плана

**3. [Scope boundary] Плавающий тест HITL.** `tests/test_concurrency_isolation.py::test_concurrent_confirmations_isolation` падает примерно в 1 из 10 прогонов (`sqlite3.OperationalError: database is locked`, `ConfirmationStore.create_confirmation` в assistant-shared). Не вызван изменениями фазы (файлы не менялись), не исправлялся; записан в `deferred-items.md`. Из-за него первый общий гейт chat-app был красным. Решение владельцу: малая задача в assistant-shared (кандидат в Phase 3) или `/gsd-quick`.

## Auth gates

Не возникали.

## Known Stubs

Нет.

## Threat Flags

Нет новой поверхности: добавлены только тест и документы. Угрозы плана: T-02-47 (fixed только после зелёного прогона тестов, число строк проверено автоматически), T-02-48 (evidence проверено на e-mail, токены и слова персоны: совпадений нет), T-02-49 (флагов `--restart` и `--backup` не использовалось, `InvocationID` равен базовой линии).

## Остаточный долг

- Рестарт, фаза `/help` и живые проверки: план 02-15 (по разрешению владельца).
- Статусы требований SECF-01, SECF-02, SAFE-01, PRIV-01 этим планом не менялись (по плану их обновляет завершение фазы/02-15).
- `.watchdog_disabled` в chat-app и плавающий тест HITL: решения владельца в evidence.

## Self-Check: PASSED

- FOUND: `tests/test_phase2_reachability.py`, `02-VERIFICATION-EVIDENCE.md`, `deferred-items.md`, `/var/tmp/gsd-phase02-closure/tests.txt`, `/var/tmp/gsd-phase02-verify/baseline.txt`
- FOUND коммиты: `ee410ba`, `d1c58c9`, `5f36fb8` (проверка `merge-base --is-ancestor`)
