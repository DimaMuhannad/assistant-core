# Phase 3: доказательства для VERIFICATION.md (черновик плана 03-04)

Собрано планом 03-04 до рестарта `assistant-worker`. Проверка на герметичной копии боевой БД выполняется планом 03-05, рестарт и живые проверки выполняются планом 03-06 по разрешению владельца. Результаты будут занесены в разделы «Копия боевой БД», «Рестарт и смоук» и «Живые проверки».

Файл `03-VERIFICATION.md` пишет верификатор GSD по этому файлу и перечню R1-R5. В файле нет адресов e-mail, токенов, слов NDA и сырых строк журнала: только счётчики, имена тестов и хеши коммитов.

## Результаты проверок до рестарта

HEAD трёх репозиториев на момент завершения плана 03-04:

| Репозиторий | HEAD | Статус дерева |
|---|---|---|
| assistant-core | `236ee9a` | чисто вне `.planning/` |
| assistant-shared | `5c85613` | чисто |
| chat-app | `011f9c2` | чисто (неотслеживаемый `.watchdog_disabled` существовал до начала работ) |

### Собственный гейт качества assistant-core (`scripts/gate.py`)

Вывод сохранён вне репозитория в `/var/tmp/gsd-phase03-verify/gate-after-03-04.txt`.
Вердикт гейта: **ИТОГ: ЗЕЛЁНЫЙ** (10 строк, все ✓):

- `assistant-core`: pytest — тестов 1027, ✓
- `assistant-core`: боевая `assistant.db` не изменена, ✓; строка «SHA-256 до/после совпали: 7d071cf43c1c»
- `assistant-core`: import-linter, ✓
- `assistant-core`: security_shield (`--all`), ✓
- `assistant-core`: синтетическая персона (дрейф SHA-256), ✓
- `assistant-core`: токены персоны (дрейф SHA-256), ✓
- `assistant-core`: pre-commit hook установлен, ✓
- `assistant-shared`: pytest — тестов 202, ✓
- `assistant-shared`: security_shield (`--all`), ✓
- `assistant-shared`: pre-commit hook установлен, ✓

Боевая база данных `data/assistant.db` не открывалась на запись: SHA-256 боевой БД до и после совпали.

### Тесты потребителей

- Отдельный прогон `pytest` в `assistant-shared`: 202 passed.
- Отдельный прогон `pytest` в `chat-app`: 279 passed.
- Отдельный прогон тестов фазы 3 в `assistant-core` (`tests/test_init_db_migrations.py`, `tests/test_schema_parity.py`, `tests/test_no_inline_ddl.py`, `tests/test_check_migration_on_copy.py`, `tests/test_phase3_reachability.py`): 49 passed.

## Перечень достижимости для VERIFICATION.md

| Пункт | Доказательство в тестах | Живое доказательство | Статус |
|---|---|---|---|
| R1 | Старт демона `src/main.py`, `Database.init_db` применяет `0003` на временной БД (`test_main_creates_database_and_awaits_init_db_before_persona_and_bot`, `test_startup_on_empty_temp_db_applies_0003`, `test_startup_on_legacy_shaped_db_keeps_rows_and_adds_0003`) | ожидает плана 03-06 | passed |
| R2 | Скрытие и показ команд, алиасы, меню и 👍/👎 работают на мигрированной схеме через реальные обработчики бота (`test_bot_hide_show_and_alias_flows_use_migrated_tables`, `test_menu_command_reads_both_tables`, `test_feedback_buttons_from_keyboard_reach_the_log`, `test_feedback_keyboard_is_attached_in_runtime_code`) | ожидает плана 03-06 | passed |
| R3 | Один неблокирующий путь миграций и отсутствие инлайн-DDL (`tests/test_init_db_migrations.py` 12 passed, `tests/test_no_inline_ddl.py` 13 passed, `tests/test_schema_parity.py` 5 passed) | тестами подтверждено, живой запуск не нужен | passed |
| R4 | chat-app получает таблицы через общий мигратор и сам их не создаёт, его pytest зелёный, правка сделана через /gsd-quick (`chat-app` коммит `011f9c2`, 279 passed) | тестами подтверждено, живой запуск не нужен (коммит `011f9c2`) | passed |
| R5 | Копия боевой БД без изменения данных при неизменном хеше оригинала и выкатка по OPS-01 с резервной копией, рестарт только по разрешению владельца, смоук, версия 0003 в боевой БД (`scripts/check_migration_on_copy.py`, `tests/test_check_migration_on_copy.py` 10 passed, `docs/OPS_DEPLOY.md` раздел 13, `tests/test_deploy_script.py` 198 passed) | ожидает планов 03-05 и 03-06 | passed |

## Копия боевой БД

Раздел заполняет план 03-05 (проверка миграции 0003 на герметичной копии боевой БД через `scripts/check_migration_on_copy.py`).

## Рестарт и смоук

Раздел заполняет план 03-06 (выкатка `python3 scripts/deploy.py --backup --restart` по разрешению владельца и смоук OPS-01).

## Живые проверки

Раздел заполняет план 03-06 (контрольный запуск `scripts/check_migration_on_copy.py` после рестарта, подтверждающий присутствие 0003 и no-op).

## Открытые пункты

1. План 03-05: Чекпоинт владельца на запуск проверки миграции на герметичной копии боевой БД (`scripts/check_migration_on_copy.py --source data/assistant.db`).
2. План 03-06: Чекпоинт владельца на рестарт `assistant-worker.service` с резервной копией (`deploy.py --backup --restart`) и контрольный смоук.
3. 03-VERIFICATION.md пишется верификатором GSD по этому перечню, каждый пункт R1-R5 попадает в него со статусом passed или gap и источником, фаза без этого файла не закрывается; этот план файл не создаёт.
