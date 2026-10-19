# Phase 2: доказательства для VERIFICATION.md (черновик плана 02-14)

Собрано планом 02-14 до рестарта `assistant-worker`. Рестарт и живые проверки выполнены планом 02-15 по разрешению владельца; результаты в разделах «Рестарт и смоук» и «Живые проверки». Файл `02-VERIFICATION.md` пишет верификатор GSD по этому файлу и перечню R1-R5. В файле нет адресов e-mail, токенов, слов NDA и сырых строк журнала: только счётчики, имена тестов и хеши коммитов.

## Гейт и потребители

HEAD трёх репозиториев на момент прогонов:

| Репозиторий | HEAD | Дерево |
|---|---|---|
| assistant-core | `d1c58c9` | чисто вне `.planning/` |
| assistant-shared | `022bb3e` | чисто |
| chat-app | `f92d95f` | один посторонний неотслеживаемый флаг-файл `.watchdog_disabled` (пустой, создан 2026-10-10 11:58 UTC до начала фазы; в плане 02-07 уже отмечен как существовавший до работ); репозиторий в фазе не менялся этим планом |

Собственный гейт assistant-core (`python3 scripts/gate.py`, вывод в `/var/tmp/gsd-phase02-verify/gate-run.txt`): **ИТОГ: ЗЕЛЁНЫЙ**, 11 строк, все со значком ✓:

- assistant-core: pytest, тестов 977, ✓
- assistant-core: боевая `assistant.db` не изменена, ✓; строка «SHA-256 до/после совпали»
- assistant-core: import-linter, security_shield (`--all`), дрейф синтетической персоны, дрейф токенов персоны, pre-commit hook установлен: все ✓
- assistant-shared: pytest, тестов 197, ✓; security_shield (`--all`) ✓; pre-commit hook установлен ✓

Отдельный прогон `pytest` в `/opt/assistant-shared`: 197 passed. Отдельный прогон набора фазы 2 `tests/test_phase2_reachability.py`: 8 passed.

Общий гейт потребителя (`cd /opt/chat-app && python3 scripts/gate.py`, вывод в `/var/tmp/gsd-phase02-verify/chatapp-gate-run2.txt`): **ИТОГ: ЗЕЛЁНЫЙ** (chat-app pytest 277, assistant-core pytest 977, import-linter, shield, дрейф, боевая `assistant.db` не изменена). Первый прогон этого гейта был КРАСНЫМ только по одной строке: assistant-core pytest, 1 failed, 976 passed, упал плавающий тест `test_concurrent_confirmations_isolation` (`database is locked` в `ConfirmationStore`); повторный прогон без правок зелёный. Причина не относится к изменениям фазы, см. «Остаточные риски и допущения» и `deferred-items.md`. Вывод первого прогона: `/var/tmp/gsd-phase02-verify/chatapp-gate-run.txt`.

`scripts/security_shield.py . --all` в assistant-core: ровно 3 находки, все в `config/persona.yaml` (строка 44), код возврата 1; других файлов нет.

## Достижимость из рантайма

Новые функции доказаны без рестарта тестом `tests/test_phase2_reachability.py` (временные БД, `MagicMock` вместо бота, боевая БД не открывалась).

| Критерий успеха | Чем доказано без рестарта | Живая проверка (план 02-15) |
|---|---|---|
| 1. Режим NDA по данным `workspaces`, в библиотеке нет прежних имён (SECF-01) | `tests/test_nda_script_parity.py` (D-10: нет констант слов и токенов организаций в `assistant_shared/security`), тесты сопоставления пространств и паритета в assistant-shared (планы 02-06, 02-10), обёртка передаёт в `audit_repository` только `workspaces` (`test_shield_wrapper_passes_only_workspaces_to_audit_repository`) | рестарт не нужен для проверки кода; живого шага нет |
| 2. Общая функция сканирования, web проверяет `forbidden_keywords` (SECF-02) | `tests/test_scan_file_content.py` и `tests/test_shield_parity.py` в assistant-shared (паритет на синтетических фикстурах), ASGI-тест web-аудита `test_security_audit_all` в chat-app (план 02-07, quick 261010-ivt) | живая проверка web-аудита требует рестарта `chat-app.service` (заморожен): в «Открытых пунктах» |
| 3. «Очисти диалог» не стирает историю без защиты (SAFE-01) | `tests/test_clear_dialog_text_guard.py` (план 02-02); сквозной `test_text_clear_phrase_through_router_text_handler_warns_and_keeps_history`: обработчик берётся из роутера, история не меняется, ответ равен предупреждению с `/clear`, карточки нет; `test_router_registers_help_clear_text_and_voice_handlers`: в роутере есть `handle_cmd_help`, `handle_cmd_clear_dialog`, `handle_user_text`, `handle_user_voice` | passed: текстовое сообщение боту после рестарта, ответ владельца «Предупреждение с /clear, карточки нет» |
| 4. Предупреждение при подключении почты и в `/help` (PRIV-01) | `tests/test_privacy_notice.py`, `tests/test_phase2_reachability.py::test_help_command_sends_privacy_block_from_default_persona` (обработчик `/help` из роутера, текст персоны по умолчанию), AST `main.py`: `email_collector_job` на `run_email_collector_cycle`, цикл вызывает `_announce_email_ai_notice` | passed: живая команда `/help` и одно сообщение о почте после рестарта (см. «Живые проверки») |
| 5. Достижимость, fail-closed, гейт, рестарт только по разрешению, смоук OPS-01 | `tests/test_phase2_reachability.py` (8 тестов), гейт ЗЕЛЁНЫЙ, read-only смоук текущего сервиса (раздел «Перечень достижимости»), `InvocationID` сервиса не менялся | passed: рестарт по разрешению владельца, смоук OPS-01 ЗЕЛЁНЫЙ (см. «Рестарт и смоук») |

Ссылки: `tests/test_phase2_reachability.py` (assistant-core); ASGI-тесты web-аудита chat-app `backend/tests/test_security_api.py` (`test_security_audit_all`, `test_security_audit_all_live_tree_has_only_frozen_findings`), прогнаны в составе 277 тестов chat-app в общем гейте.

## Закрытие находок ревью

Находка помечена `fixed` в `01-REVIEW-DISPOSITION.md` только после зелёного прогона её регрессионных тестов. Перечень идентификаторов: `/var/tmp/gsd-phase02-closure/tests.txt` (119 тестов, три столбца: находка, идентификатор pytest, каталог запуска), вывод: `/var/tmp/gsd-phase02-closure/closure-run.txt` (assistant-core: 103 passed; chat-app из `/opt/chat-app`: 16 passed; пропусков, xfail и deselected нет).

| Находка | Регрессионные тесты (представители) | План | Результат |
|---|---|---|---|
| CR-01 | `test_sync_rejects_hostile_remote_names`, `test_sync_rejects_symlink_pointing_outside_uploads` | 02-03 | fixed, 11 passed |
| WR-01 | `test_sync_runs_blocking_drive_calls_off_event_loop` | 02-03 | fixed, 1 passed |
| WR-02 | `test_server_backup_archive_methods_are_removed` | 02-03 | fixed, 1 passed |
| WR-03 | `test_db_unchanged_check_mitigation_*`, `test_integrity_snapshot_*`, `test_compare_integrity_*` | 02-13 | fixed, 18 passed, остаточный риск принят |
| WR-04 | `test_compare_shield_findings_same_count_on_another_line_is_new_and_stale`, `test_run_shield_step_core_same_count_on_a_replaced_line_is_red` | 02-13 | fixed, 24 passed |
| WR-05 | `test_gate_environment_path_refused` x8 (chat-app) | 02-09 (chat-app `27886b3`) | fixed, 8 passed |
| WR-06 | `test_fallback_gate_warns_in_stderr_and_summary` (chat-app) | 02-09 (chat-app `27886b3`) | fixed, 3 passed |
| WR-07 | `test_absolute_live_path_is_blocked_regardless_of_core_dir`, `test_symlink_with_other_name_to_live_path_is_blocked` | 02-05 | fixed, 12 passed, остаточный риск (жёсткая ссылка) |
| WR-08 | `test_write_private_replaces_symlink_and_never_touches_its_target`, `test_load_state_refuses_symlink_to_state_file` | 02-04 | fixed, 17 passed |
| WR-09 | `test_backup_refuses_existing_directory_with_wide_mode_and_keeps_its_mode`, `test_backup_rejects_directory_under_foreign_git_repository_before_creating_it` | 02-04 | fixed, 5 passed |
| WR-10 | `test_autouse_fixture_replaces_*`, `test_db_checks_run_without_any_real_subprocess` | 02-13 | fixed, 4 passed |
| WR-11 | `test_menu_command_rendering` | 02-05 | fixed, 1 passed |
| WR-12 | `test_find_backup_*` (5), `test_download_file_writes_collected_bytes` | 02-03 | fixed, 7 passed |
| WR-13 | `test_rules_files_do_not_name_legacy_gate_command`, `test_legacy_gate_patterns_self_check` | 02-05 | fixed, 2 passed |
| T-uo4-02 | `test_scripts_directory_replaced_by_symlink_refused`, `test_symlinked_gate_path_refused_before_agent`, `test_gate_path_turned_into_symlink_before_gate_reverts_patch` (chat-app) | 02-09 (chat-app `27886b3`) | закрыт; строка AR-01-04 в `01-SECURITY.md` помечена закрытой; 5 passed |

Итог disposition: 14 строк `fixed` (CR-01, WR-01..WR-13), 6 строк `info` в `deferred` (IN-01..IN-06, бэклог по решению владельца 2026-10-10, запись DEBT-03 в `REQUIREMENTS.md`). Находок со статусом `open` нет. План 02-08 в перечне SUMMARY плана 02-14 упомянут по ошибке: находки WR-08 и WR-09 закрыл план 02-04, а 02-08 закрыл обёртку shield (SECF-01).

## Остаточные риски и допущения

- **WR-03 (принят, T-02-45):** смягчение проверки боевой БД не закрывает добавление и изменение строк тестом через дочерний процесс, не охваченный стражем, при совпадающей схеме и неубывающих счётчиках. Основной барьер: страж `tests/live_db_guard.py`; применение смягчения видно в строке прогона. Возможен ложный красный (fail-closed, «повторите прогон»).
- **WR-07:** страж охраняет боевые пути и символические ссылки, но не сравнивает файлы по inode: жёсткая ссылка с другим именем остаётся вне охвата (принято в плане 02-05).
- **Пересекающиеся пространства (T-02-21):** репозиторий, подходящий двум пространствам, получает строжайший допуск; слова самого NDA-пространства в таком репозитории не ищутся (закреплено тестом).
- **Публичный репозиторий и данные персоны:** `config/persona.yaml` содержит слова NDA как данные. Hook и shield не ослаблены (D-21), допусков нет. Три известные находки видны в режиме `--all` (строка 44, код возврата 1) и будут видны в web-аудите после рестарта `chat-app.service`; для режима фиксации (staged) они возникают только при изменении этого файла.
- **Единственный обход hook в фазе (D-21), `--no-verify`:** коммит `95812d1dd748aed1a8700ec68b2fba3d6e357436` («текст предупреждения в `config/persona.yaml`», план 02-11), форма `git commit --no-verify --only -- config/persona.yaml`, по ответу владельца «Разрешаю один раз (Рекомендуется)». Файлы коммита: только `config/persona.yaml` (2 вставленные строки). Находок shield `--all` непосредственно перед ним: 3; после него: 3, новых нет. Источники: SUMMARY плана 02-11 и `/var/tmp/gsd-phase02-persona/result.txt`. Остальные коммиты фазы прошли штатный hook. В этом плане (02-14) обходов hook нет: оба коммита прошли shield штатно.
- **Критерий «ящик подключён» (A7):** `_has_connected_mailbox` в `src/main.py` считает ящиком результат, ключ которого не служебный, у которого `status` не начинается с `skipped` и нет ключа `error`. Служебные ключи (`reconciliation`, `aging`, `db_totals`, `active_actionable_count`) не считаются. Флаг `notice:email_ai` ставится только после успешной отправки.
- **Живой web-аудит:** невозможен без рестарта `chat-app.service` (заморожен); достижимость подтверждена ASGI-тестами chat-app (план 02-07).
- **Плавающий тест (новая находка, не из фазы 2):** `tests/test_concurrency_isolation.py::test_concurrent_confirmations_isolation` падает примерно в одном прогоне из десяти (`database is locked`, `assistant_shared/hitl/store.py`, одиночный INSERT на свежей временной БД). Из-за него один из двух прогонов общего гейта chat-app был красным. Не исправлено (`assistant-shared` в плане read-only); запись в `deferred-items.md` фазы.
- **Посторонний файл в chat-app:** `.watchdog_disabled` (пустой, неотслеживаемый) делает дерево chat-app «нечистым» для буквального критерия плана; процедура рестарта `deploy.py --restart` проверяет только дерево assistant-core, поэтому рестарт `assistant-worker` он не блокирует.
- **Живая БД:** не открывалась ни тестами (страж), ни этим планом; гейт сверил SHA-256 до и после (совпали).

## Открытые пункты

1. ~~Рестарт `assistant-worker.service` по разрешению владельца и смоук OPS-01~~ выполнено планом 02-15 (см. «Рестарт и смоук»).
2. DEBT-03: информационные находки IN-01..IN-06 ушли в бэклог (запись в `REQUIREMENTS.md`).
3. Рестарт `chat-app.service` (заморожен, в плане 02-15 не выполнялся) и решение владельца по находкам web-аудита: после его рестарта web-аудит chat-app покажет находки по запретным словам пространства в `config/persona.yaml` (три известные) и замороженные находки; решение про сохранение этих слов в публичном `config/persona.yaml` относится к Phase 8.
4. ~~Подтвердить отсутствие ключа переопределения пути БД в живом `.env`~~ выполнено владельцем: `grep -c` дал 0 (см. «Рестарт и смоук»).
5. Плавающий тест `test_concurrent_confirmations_isolation`: решение владельца, куда отнести исправление (`deferred-items.md`).
6. Неотслеживаемый `.watchdog_disabled` в chat-app: убрать или занести в `.gitignore` chat-app малой задачей `/gsd-quick` (в этой фазе не трогался).
7. ~~Фаза подтверждения `/help` смоука OPS-01~~ выполнена: обработанное обновление и ответ владельца «да», итог смоука ЗЕЛЁНЫЙ.
8. Первая живая резервная копия сделана сейчас (`--backup`, файл `/var/backups/assistant-core/assistant-20261010-172727.db`, 8695808 байт, права 0600); процедура копирования после исправлений WR-08 и WR-09 подтверждена вживую. Перед миграцией `0003` в Phase 3 нужна новая копия с отдельным разрешением владельца.

## Перечень достижимости для VERIFICATION.md

Базовая линия живого сервиса (для сравнения в плане 02-15), `/var/tmp/gsd-phase02-verify/baseline.txt`: `InvocationID=40e9fe7aaf694e44974e2f7b55206f32`, `NRestarts=0`, `MainPID=295112`. После всех прогонов этого плана значения те же (сервис не перезапускался).

| Пункт | Автоматическое доказательство (этот план) | Живое доказательство (план 02-15) | Статус |
|---|---|---|---|
| R1. `/help` с блоком приватности | `test_help_command_sends_privacy_block_from_default_persona` (обработчик `handle_cmd_help` берётся из роутера, текст оканчивается предупреждением персоны), `test_router_registers_help_clear_text_and_voice_handlers` (команды `start` и `help`), `tests/test_privacy_notice.py` | бот владельца ответил на `/help`, в конце справки есть блок «Приватность почты» (ответ владельца опросом: «Да, ответ пришёл, блок есть»; смоук: обработанное обновление после метки: да, ответ владельца на /help: да; `02-SMOKE-REPORT.md`) | passed |
| R2. Точка подключения почты | AST `main.py`: `add_job(run_email_collector_cycle, ..., id="email_collector_job")` ровно один, цикл вызывает `_announce_email_ai_notice` с тремя аргументами, `main()` создаёт `EmailBotHandler` и подключает его роутер; `tests/test_privacy_notice.py` и план 02-12 (показ один раз, флаг после отправки) | после рестарта пришло ровно одно сообщение «Приватность почты» (ответ владельца: «Да, ровно одно»); записей `PRIV-01:` в журнале инвокации `25ff0740…`: 1 | passed |
| R3. Текстовое «очисти диалог» даёт предупреждение с `/clear` и не меняет историю | `test_text_clear_phrase_through_router_text_handler_warns_and_keeps_history`, `tests/test_clear_dialog_text_guard.py` | владелец отправил боту «очисти диалог»: «Предупреждение с /clear, карточки нет» (ответ владельца опросом; память не стёрта, карточки подтверждения не было) | passed |
| R4. `scripts/security_shield.py` как точка входа аудита | hook вызывает обёртку одной строкой `exec` без флагов допуска (`test_pre_commit_hook_runs_security_shield_without_relaxing_flags`); AST обёртки: `audit_repository` только с `check_staged_only` и `workspaces`, констант слов нет; подпроцесс на временном репозитории: синтетический секрет даёт код 1 и значение не печатается, чистый репозиторий даёт код 0; гейт ЗЕЛЁНЫЙ; `--all` даёт 3 известные находки в данных персоны | гейт ЗЕЛЁНЫЙ на момент рестарта (план 02-14, 11 строк ✓) и повторно после рестарта (см. «Живые проверки»); hook и обёртка shield в рантайм-службу не входят, живой шаг не нужен; `--all` даёт 3 известные находки в данных персоны | passed |
| R5. Рестарт и смоук OPS-01 | read-only смоук текущего сервиса без `--restart` и `--backup` (`python3 scripts/deploy.py --state-file /var/tmp/gsd-phase02-verify/smoke-state.json`, вывод `/var/tmp/gsd-phase02-verify/smoke-run.txt`): автоматическая часть ЗЕЛЁНАЯ (сервис active, журнал доступен, нет ошибок старта, polling бота запущен, планировщик 10 из 10, `getMe` жив), итог «ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ» (фаза `/help` не выполнялась) | рестарт выполнил владелец командой `python3 scripts/deploy.py --restart --backup --report …/02-SMOKE-REPORT.md`, код возврата 0; InvocationID `40e9fe7aaf694e44974e2f7b55206f32` -> `25ff0740810d4783ae1ba7721b6f836c`, MainPID 295112 -> 893511, NRestarts 0; строка «ИТОГ СМОУКА: ЗЕЛЁНЫЙ» в `02-SMOKE-REPORT.md` после `--confirm-help yes` | passed |

**Указание верификатору:** `02-VERIFICATION.md` пишется по этому перечню; каждый пункт R1-R5 попадает в него со статусом и источником (см. столбцы выше и раздел «Живые проверки»). Фаза без этого файла не закрывается; этот файл создаёт верификатор GSD, а не план 02-15.

## Рестарт и смоук

**Разрешение владельца** (опрос в чате, дословно): выбор «Рестарт с резервной копией --backup (Рекомендуется)» (restart-with-backup). Условие «ключа `ASSISTANT_DB_PATH_OVERRIDE` в живом `.env` нет»: первый ответ «Не знаю»; затем владелец сам выполнил в сессии `grep -c ASSISTANT_DB_PATH_OVERRIDE /opt/assistant-core/.env` и получил `0` (ключа нет). Содержимое `.env` исполнитель не читал. Запись: `/var/tmp/gsd-phase02-verify/restart-note.txt`.

**Кто и как выполнил:** запуск рестарта агентом был заблокирован правилами прав Claude Code (блокировку никто не обходил); команду выполнил сам владелец в этой сессии: `python3 scripts/deploy.py --restart --backup --report .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-SMOKE-REPORT.md`, код возврата 0. Один рестарт, без повторов.

| Показатель | До | После |
|---|---|---|
| HEAD assistant-core на момент рестарта | `a115f334c6c963dab9092875bcae1d1748bca264` | то же |
| InvocationID | `40e9fe7aaf694e44974e2f7b55206f32` | `25ff0740810d4783ae1ba7721b6f836c` |
| MainPID | 295112 | 893511 |
| NRestarts | 0 | 0 |
| ActiveState | active | active |

**Автоматическая часть смоука:** ЗЕЛЁНАЯ. Все семь строк ✓: рестарт (новая инвокация active, polling запущен), сервис active, журнал доступен, нет ERROR/CRITICAL/Traceback в окне старта (ошибок 0, WARNING 0), polling бота запущен, планировщик 10 из 10, `getMe` жив. Фаза `--await-help`: обработанное обновление после метки смоука получено. Ответ владельца опросом «Да, ответ пришёл, блок есть»; `deploy.py --confirm-help yes --report …` перезаписал отчёт. **ИТОГ СМОУКА: ЗЕЛЁНЫЙ.** Отчёт: `.planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-SMOKE-REPORT.md` (адресов e-mail и токенов нет).

**Резервная копия:** была (первая живая). Файл `/var/backups/assistant-core/assistant-20261010-172727.db`, 8695808 байт, права 0600, каталог 0700 (вне деревьев git); содержимое не читалось. Это первая живая проверка исправлений WR-08 и WR-09: прошла.

**Откат:** красного исхода не было, команды отката не печатались и не исполнялись (справка: порядок в `docs/OPS_DEPLOY.md`, раздел 9; новый откат потребует нового разрешения владельца).

**chat-app.service не перезапускался.**

**Побочные записи демона:** первый успешный цикл почты записал флаг показа `notice:email_ai` в боевую БД и отправил одно сообщение «Приватность почты» (штатная запись демона, не смоук).

## Живые проверки

Ответы владельца получены опросами в чате; запись оркестратора: `/var/tmp/gsd-phase02-verify/live-checks.txt`. Сырые строки журнала не читались и не вносятся.

| Пункт | Что проверено | Ответ или результат | Статус | Источник |
|---|---|---|---|---|
| R1 | `/help` в Telegram, блок «Приватность почты» в конце справки | «Да, ответ пришёл, блок есть» | passed | ответ владельца, `02-SMOKE-REPORT.md` (подтверждение бота: да) |
| R2 | сообщение «Приватность почты» после старта и записи PRIV-01 | «Да, ровно одно»; строк `PRIV-01:` в журнале текущей инвокации: 1 | passed | ответ владельца, счёт `grep -c` по журналу инвокации |
| R3 | текст «очисти диалог» боту | «Предупреждение с /clear, карточки нет» (память не стёрта) | passed | ответ владельца; тесты `tests/test_clear_dialog_text_guard.py`, `tests/test_phase2_reachability.py` |
| R4 | `scripts/security_shield.py` как точка входа аудита | hook и обёртка не входят в рантайм-службу; гейт ЗЕЛЁНЫЙ (план 02-14), повторный прогон после рестарта: см. строку ниже | passed | тесты `tests/test_phase2_reachability.py`, гейт |
| R5 | рестарт только по разрешению владельца, смоук OPS-01 | рестарт по ответу «restart-with-backup», новая инвокация, ИТОГ СМОУКА ЗЕЛЁНЫЙ; ERROR/CRITICAL/Traceback в журнале инвокации: 0 | passed | `02-SMOKE-REPORT.md`, `restart-note.txt` |

**Гейт после рестарта:** `python3 scripts/gate.py` после рестарта (вывод `/var/tmp/gsd-phase02-verify/gate-run-after-restart.txt`): **ИТОГ: ЗЕЛЁНЫЙ**, 11 строк ✓, assistant-core 977 тестов, assistant-shared 197; «SHA-256 до/после совпали» (гейт прошёл с первого раза, повтор не понадобился). Источник для R4.
