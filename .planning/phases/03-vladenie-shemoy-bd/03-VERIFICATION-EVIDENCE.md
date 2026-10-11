# Phase 3: доказательства для VERIFICATION.md

Собрано в ходе выполнения планов 03-04..03-06. Проверка на герметичной копии боевой БД выполнена (план 03-05), регламентная выкатка по процедуре OPS-01 с созданием резервной копии, автоматический смоук и живые проверки выполнены по согласованию с владельцем (план 03-06).

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
| R1 | Старт демона `src/main.py`, `Database.init_db` применяет `0003` на временной БД (`test_main_creates_database_and_awaits_init_db_before_persona_and_bot`, `test_startup_on_empty_temp_db_applies_0003`, `test_startup_on_legacy_shaped_db_keeps_rows_and_adds_0003`) | смоук без ошибок в окне старта (`03-SMOKE-REPORT.md`), версия `0003` подтверждена в боевой БД после рестарта | passed |
| R2 | Скрытие и показ команд, алиасы, меню и 👍/👎 работают на мигрированной схеме через реальные обработчики бота (`test_bot_hide_show_and_alias_flows_use_migrated_tables`, `test_menu_command_reads_both_tables`, `test_feedback_buttons_from_keyboard_reach_the_log`, `test_feedback_keyboard_is_attached_in_runtime_code`) | ответ на `/help`, ответ на `/menu` со статусом команд и псевдонимами, запись отзыва 👍/👎 в `dialog_feedback_log` боевой БД | passed |
| R3 | Один неблокирующий путь миграций и отсутствие инлайн-DDL (`tests/test_init_db_migrations.py` 12 passed, `tests/test_no_inline_ddl.py` 13 passed, `tests/test_schema_parity.py` 5 passed) | тестами подтверждено, живой запуск не нужен | passed |
| R4 | chat-app получает таблицы через общий мигратор и сам их не создаёт, его pytest зелёный, правка сделана через /gsd-quick (`chat-app` коммит `011f9c2`, 279 passed) | тестами подтверждено, живой запуск не нужен (коммит `011f9c2`) | passed |
| R5 | Копия боевой БД без изменения данных при неизменном хеше оригинала и выкатка по OPS-01 с резервной копией, рестарт только по разрешению владельца, смоук, версия 0003 в боевой БД (`scripts/check_migration_on_copy.py`, `tests/test_check_migration_on_copy.py` 10 passed, `docs/OPS_DEPLOY.md` раздел 13, `tests/test_deploy_script.py` 198 passed) | копия: passed; резервная копия создана; рестарт по разрешению владельца; смоук ЗЕЛЁНЫЙ; повторная проверка после рестарта: passed | passed |

## Копия боевой БД

- **Дата (UTC):** 2026-10-11T00:50:34Z
- **Выбор владельца:** check-and-restart (Проверка на копии сейчас и рестарт с резервной копией в плане 03-06)
- **Ключ ASSISTANT_DB_PATH_OVERRIDE в .env:** подтверждено владельцем: отсутствует
- **Кто запускал проверку:** Claude
- **Код возврата:** 0
- **Число использованных попыток:** 1
- **Вывод проверки:** боевая БД не изменена: хеш источника до и после совпал; применено на копии: [] (версия `0003_bot_commands_and_feedback` уже присутствует в `schema_migrations`, таблицы бота содержат данные)

Дословный вывод скрипта `scripts/check_migration_on_copy.py --source data/assistant.db`:

```
==================================================================
  ОТЧЁТ ПРОВЕРКИ МИГРАЦИИ НА КОПИИ БД (DAT-01, D-05)
==================================================================
Хеш источника до: 47559fb19642
Хеш источника после: 47559fb19642
Версии до проверки:  ['0001_initial_schema', '0002_pending_confirmations', '0003_bot_commands_and_feedback']
Применено на копии:  []
------------------------------------------------------------------
Счётчики строк таблиц бота:
  • bot_command_settings: 1 строк
  • bot_custom_aliases: 1 строк
  • dialog_feedback_log: 0 строк
------------------------------------------------------------------
Результаты проверок:
  [✓] Неизменность источника (mode=ro) (до: 47559fb19642, после: 47559fb19642)
  [✓] Применение миграций на копии (применено: [])
  [✓] Целостность существующих данных (данные таблиц до и после совпадают)
  [✓] Отсутствие посторонних объектов (новые таблицы: [])
==================================================================
  ИТОГ: ЗЕЛЁНЫЙ
==================================================================
```

## Рестарт и смоук

- **Выбор владельца (дословно):** `check-and-restart (Проверка на копии сейчас и рестарт с резервной копией в плане 03-06)`
- **Хеш HEAD на момент рестарта:** `de2dbae983f05517cc110b9fee8849cda00bdeb6`
- **InvocationID сервиса:**
  - До рестарта: `25ff0740810d4783ae1ba7721b6f836c`
  - После рестарта: `0dc5531ee9824fb7a6145d333f5eef65`
- **Резервная копия:**
  - Путь: `/var/backups/assistant-core/assistant-20261011-005251.db` (размер: 8704000 байт, права 0600 в каталоге 0700). Содержимое копии не читалось.
- **Статус автоматического смоука:**
  - Команда: `python3 scripts/deploy.py --backup --restart --report .planning/phases/03-vladenie-shemoy-bd/03-SMOKE-REPORT.md`
  - Итог: **ИТОГ СМОУКА: ЗЕЛЁНЫЙ** (файл `.planning/phases/03-vladenie-shemoy-bd/03-SMOKE-REPORT.md`).
  - Ошибки в окне старта: 0.
  - Предупреждения (WARNING): 0.
  - Команды отката из отчёта зафиксированы справочно: **не исполнялись**.
  - Сервис потребителя: **chat-app.service не перезапускался**.
- **Повторная проверка на герметичной копии после рестарта:**
  - Команда: `.venv/bin/python scripts/check_migration_on_copy.py --source data/assistant.db` (вывод сохранён в `/var/tmp/gsd-phase03-verify/live-copy-check-after.txt`).
  - Код возврата: 0.
  - Хеш источника до: `83fece373834`.
  - Хеш источника после: `83fece373834` (совпали, неизменность источника обеспечена).
  - Версии источника: `['0001_initial_schema', '0002_pending_confirmations', '0003_bot_commands_and_feedback']`.
  - Применено на копии: `[]` (no-op, схема полностью актуальна).
  - Счётчики строк таблиц бота: `bot_command_settings`: 1, `bot_custom_aliases`: 1, `dialog_feedback_log`: 1.
  - Вердикт: **ИТОГ: ЗЕЛЁНЫЙ**.

## Живые проверки

Живые проверки выполнены владельцем в Telegram через диалоговые опросы (диалог GSD):

1. **Команда `/help`:**
   - Обработка в журнале зафиксирована скриптом (`scripts/deploy.py --await-help`, статус: `handled`).
   - Ответ бота получен владельцем в Telegram: подтверждено (`deploy.py --confirm-help yes`).
   - Статус: **passed** (источник: опрос владельца, `03-SMOKE-REPORT.md`).
2. **Команда `/menu`:**
   - Бот ответил интерактивным меню со списком команд, их статусом активности и блоком «Персональные псевдонимы». Обработчик успешно прочитал `bot_command_settings` и `bot_custom_aliases`.
   - Статус: **passed** (источник: опрос владельца).
3. **Кнопки обратной связи 👍/👎:**
   - Владелец нажал кнопку 👍/👎 под сообщением секретаря; бот отобразил уведомление «Спасибо за отзыв!».
   - В боевой БД зафиксирована строка в таблице `dialog_feedback_log` (подтверждено счётчиком `dialog_feedback_log: 1 строк` при контрольной проверке на копии).
   - Статус: **passed** (источник: опрос владельца, счётчик `check_migration_on_copy.py`).

## Результаты проверок после рестарта

### Гейт качества assistant-core (`scripts/gate.py`)

Вывод сохранён вне репозитория в `/var/tmp/gsd-phase03-verify/gate-after-restart.txt`.
Вердикт гейта: **ИТОГ: ЗЕЛЁНЫЙ** (10 строк, все ✓):

- `assistant-core`: pytest — тестов 1027, ✓
- `assistant-core`: боевая `assistant.db` не изменена, ✓; строка «SHA-256 до/после совпали: 83fece373834»
- `assistant-core`: import-linter, ✓
- `assistant-core`: security_shield (`--all`), ✓
- `assistant-core`: синтетическая персона (дрейф SHA-256), ✓
- `assistant-core`: токены персоны (дрейф SHA-256), ✓
- `assistant-core`: pre-commit hook установлен, ✓
- `assistant-shared`: pytest — тестов 202, ✓
- `assistant-shared`: security_shield (`--all`), ✓
- `assistant-shared`: pre-commit hook установлен, ✓

## Открытые пункты

1. Усиления схемы (дополнительные индексы, ограничения CHECK, NOT NULL) отложены на отдельную миграцию решением владельца D-04.
2. 03-VERIFICATION.md пишется верификатором GSD по этому перечню, каждый пункт R1-R5 попадает в него со статусом passed или gap и источником, фаза без этого файла не закрывается; данный документ предоставляет полный доказательный базис.
