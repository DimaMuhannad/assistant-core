---
phase: 01
review: 01-REVIEW.md
titles: json
findings:
  - id: CR-01
    severity: critical
    disposition: fixed
    title: "Path traversal при записи скачанного файла Google Drive (запись от root за пределы uploads)"
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "Блокирующий сетевой и файловый ввод-вывод внутри async-методов (замораживает event loop демона)"
  - id: WR-02
    severity: warning
    disposition: fixed
    title: "Архив «серверного бэкапа» несогласован, небезопасен по правам и не используется"
  - id: WR-03
    severity: warning
    disposition: fixed
    title: "Смягчение проверки «боевая БД не изменена» почти полностью отключает её"
  - id: WR-04
    severity: warning
    disposition: fixed
    title: "Замороженный список ложных срабатываний shield позволяет подменить находку"
  - id: WR-05
    severity: warning
    disposition: fixed
    title: "Защита адаптера агента неполна: гейт цели исполняет код, который патч менять может"
  - id: WR-06
    severity: warning
    disposition: fixed
    title: "Для репозитория без своего гейта адаптер молча запускает гейт chat-app и сообщает «гейт цели зелёный»"
  - id: WR-07
    severity: warning
    disposition: fixed
    title: "Страж боевой БД не закрывает часть путей"
  - id: WR-08
    severity: warning
    disposition: fixed
    title: "`deploy.py` пишет от root в предсказуемый путь в `/var/tmp` с переходом по symlink"
  - id: WR-09
    severity: warning
    disposition: fixed
    title: "`make_db_copy` меняет права произвольного существующего каталога и проверяет только «внутри core»"
  - id: WR-10
    severity: warning
    disposition: fixed
    title: "Тесты `db_unchanged_check` недетерминированы: запускают реальный `systemctl` и делают `stat` боевой БД"
  - id: WR-11
    severity: warning
    disposition: fixed
    title: "Тест `test_menu_command_rendering` ничего не проверяет про «отрисовку меню»"
  - id: WR-12
    severity: warning
    disposition: fixed
    title: "Тест Drive проходит через ветку «папка», а не через общий поиск; пути `download`/`sync` не покрыты"
  - id: WR-13
    severity: warning
    disposition: fixed
    title: "Защитный тест на «возврат к чужому гейту» ловит только точную строку"
  - id: IN-01
    severity: info
    disposition: deferred
    title: "`ASSISTANT_DB_PATH_OVERRIDE` в боевом рантайме не логируется и не нормализуется"
  - id: IN-02
    severity: info
    disposition: deferred
    title: "`os.environ.setdefault` не заменяет пустую строку"
  - id: IN-03
    severity: info
    disposition: deferred
    title: "Мелочи в `deploy.py`"
  - id: IN-04
    severity: info
    disposition: deferred
    title: "Неточности в `gate.py`"
  - id: IN-05
    severity: info
    disposition: deferred
    title: "Хук и установщик assistant-shared зависят от пути assistant-core и проверяют не то, что исполняется"
  - id: IN-06
    severity: info
    disposition: deferred
    title: "Мёртвые/слабые места `gdrive/client.py`"
open: 0
total: 20
recorded: 2026-10-10T16:37:20.000Z
---

# Phase 01: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| CR-01 | critical | fixed | fixed in Phase 2, plan 02-03, test: test_sync_rejects_hostile_remote_names, test_sync_rejects_symlink_pointing_outside_uploads |
| WR-01 | warning | fixed | fixed in Phase 2, plan 02-03, test: test_sync_runs_blocking_drive_calls_off_event_loop |
| WR-02 | warning | fixed | fixed in Phase 2, plan 02-03, test: test_server_backup_archive_methods_are_removed |
| WR-03 | warning | fixed | fixed in Phase 2, plan 02-13, test: test_db_unchanged_check_mitigation_*, test_integrity_snapshot_*, test_compare_integrity_* (residual risk accepted, T-02-45, see 02-13-SUMMARY) |
| WR-04 | warning | fixed | fixed in Phase 2, plan 02-13, test: test_compare_shield_findings_same_count_on_another_line_is_new_and_stale, test_run_shield_step_core_same_count_on_a_replaced_line_is_red |
| WR-05 | warning | fixed | fixed in Phase 2, plan 02-09 (chat-app commit 27886b3), test: test_gate_environment_path_refused (chat-app backend/tests/test_agy_cross_ai.py) |
| WR-06 | warning | fixed | fixed in Phase 2, plan 02-09 (chat-app commit 27886b3), test: test_fallback_gate_warns_in_stderr_and_summary (chat-app backend/tests/test_agy_cross_ai.py) |
| WR-07 | warning | fixed | fixed in Phase 2, plan 02-05, test: test_absolute_live_path_is_blocked_regardless_of_core_dir, test_symlink_with_other_name_to_live_path_is_blocked |
| WR-08 | warning | fixed | fixed in Phase 2, plan 02-04, test: test_write_private_replaces_symlink_and_never_touches_its_target, test_load_state_refuses_symlink_to_state_file |
| WR-09 | warning | fixed | fixed in Phase 2, plan 02-04, test: test_backup_refuses_existing_directory_with_wide_mode_and_keeps_its_mode, test_backup_rejects_directory_under_foreign_git_repository_before_creating_it |
| WR-10 | warning | fixed | fixed in Phase 2, plan 02-13, test: test_autouse_fixture_replaces_*, test_db_checks_run_without_any_real_subprocess |
| WR-11 | warning | fixed | fixed in Phase 2, plan 02-05, test: test_menu_command_rendering |
| WR-12 | warning | fixed | fixed in Phase 2, plan 02-03, test: test_find_backup_* (5), test_download_file_writes_collected_bytes |
| WR-13 | warning | fixed | fixed in Phase 2, plan 02-05, test: test_rules_files_do_not_name_legacy_gate_command, test_legacy_gate_patterns_self_check |
| IN-01 | info | deferred | owner decision 2026-10-10 (D-17): backlog, см. DEBT-03 в REQUIREMENTS.md |
| IN-02 | info | deferred | owner decision 2026-10-10 (D-17): backlog, см. DEBT-03 в REQUIREMENTS.md |
| IN-03 | info | deferred | owner decision 2026-10-10 (D-17): backlog, см. DEBT-03 в REQUIREMENTS.md |
| IN-04 | info | deferred | owner decision 2026-10-10 (D-17): backlog, см. DEBT-03 в REQUIREMENTS.md |
| IN-05 | info | deferred | owner decision 2026-10-10 (D-17): backlog, см. DEBT-03 в REQUIREMENTS.md |
| IN-06 | info | deferred | owner decision 2026-10-10 (D-17): backlog, см. DEBT-03 в REQUIREMENTS.md |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
