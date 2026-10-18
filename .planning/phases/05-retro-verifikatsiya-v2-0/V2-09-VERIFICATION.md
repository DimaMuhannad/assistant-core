---
phase: 05-retro-verifikatsiya-v2-0
v2_phase: "09"
v2_source: /opt/chat-app/.planning/milestones/v2.0-phases/09-dinamicheskoe-menyu-i-interfeys
verified: 2026-10-18T21:30:00Z
status: in_progress
score: "0 из 3 требований passed"
requirements: [UXQ-01, UXQ-02, UXQ-04]
gaps: []
---

# V2-09: Динамическое меню и интерфейс Telegram-бота, декларативные алиасы и аудит эргономики

## Источник (только чтение)

- Путь: `/opt/chat-app/.planning/milestones/v2.0-phases/09-dinamicheskoe-menyu-i-interfeys`
- Файлы папки (ls, только чтение): `09-01-PLAN.md`, `09-01-SUMMARY.md`, `09-02-PLAN.md`, `09-02-SUMMARY.md`, `09-03-PLAN.md`, `09-04-PLAN.md`, `09-04-SUMMARY.md`, `09-CONTEXT.md`, `09-DISCUSSION-LOG.md`, `09-RESEARCH.md`. `VERIFICATION.md` в исходной папке отсутствует.
- Исходный текст требований `UXQ-01`, `UXQ-02`, `UXQ-04`: `/opt/chat-app/.planning/BACKLOG.md`, раздел «Инициатива 5» (UXQ-01 — строки 150–155, UXQ-02 — 156–161, UXQ-04 — 170–182); элемент `BLD-07` — строки 262–270. Формулировки с глаголом «переименуй» — `09-CONTEXT.md` строки 14 и 37.
- Поправка к указателю плана 05-04: файл `/opt/chat-app/.planning/milestones/v2.0-REQUIREMENTS.md` не содержит ни одного вхождения `UXQ` (проверено `grep -c`), поэтому исходный текст взят из `BACKLOG.md`.
- Файлы chat-app только читались; в chat-app ничего не записано. `chat-app.service` неактивен (`systemctl is-active`: inactive), для UXQ не нужен.

## Вердикты

| Требование | Статус | Точка входа в рантайме (file:line) | Тест или команда проверки | Метка |
|---|---|---|---|---|
| UXQ-02 | passed | `src/notifier/bot_handler.py:432` (`F.text` → `handle_user_text`, 1311); скрыть 1354–1365, показать 1367–1378, алиас 1380–1402, удалить алиас 1404–1413; запись в БД `src/storage/db.py:2900` / `:2930` / `:2945`; таблицы `0003_bot_commands_and_feedback.sql:2–13`; меню `bot_handler.py:911` (`setup_bot_commands`) | `tests/test_phase3_reachability.py:192` (test_bot_hide_show_and_alias_flows_use_migrated_tables), `:237` (test_menu_command_reads_both_tables); `tests/test_command_aliases.py:45`; `tests/test_no_inline_ddl.py:75`. Прогон: 30 passed (3 файла), 12 passed (`test_phase3_reachability.py`) | трасса+e2e |

## Доказательства

### UXQ-02

#### 1. Хранение: миграция 0003 (перенесено из Phase 3, DAT-01)

- `/opt/assistant-shared/assistant_shared/db/migrations/0003_bot_commands_and_feedback.sql`: таблица `bot_command_settings` создаётся строками 2–7 (`command_name` PK, `is_enabled`, `custom_description`, `updated_at`); таблица `bot_custom_aliases` — строками 9–13 (`alias` PK, `canonical_command`, `created_at`); таблица `dialog_feedback_log` — строками 15–21 (используется UXQ-04).
- Инлайн-DDL в `src/`: `grep -rn "CREATE TABLE\|ALTER TABLE" src/` — 0 совпадений. `tests/test_no_inline_ddl.py::test_src_has_no_inline_ddl` — passed.
- Применение миграции при старте процесса: `src/main.py:646–647` (`Database(...)`, `await db.init_db()`) → `src/storage/db.py:73` (`init_db`) → `:56` (`_apply_migrations`) → `asyncio.to_thread(run_migrations, ...)` (`db.py:71`). Тесты `tests/test_phase3_reachability.py:139` (старт на пустой временной БД применяет 0003) и `:157` (старт на БД старой формы сохраняет строки и добавляет 0003) — passed.

#### 2. Четыре операции управления из чата (трасса до БД и до обновления меню)

Все четыре ветки выполняются в `EmailBotHandler.handle_user_text` до LLM-маршрутизатора (вызов `intent_router.route` на строке 1416).

| Операция | Распознавание | Запись в БД | Обновление меню |
|---|---|---|---|
| Скрыть команду | `bot_handler.py:1354–1357` (regex `^скрой\s+(?:команды\s+|команду\s+)?(...)`) | строка 1362: `db.set_command_setting(canonical, is_enabled=False)` → `db.py:2900` (`INSERT ... ON CONFLICT`) | строка 1363: `setup_bot_commands(chat_id=message.chat.id)` |
| Показать команду | `bot_handler.py:1367–1370` (`покажи команду` / `верни`) | строка 1375: `set_command_setting(canonical, is_enabled=True)` → `db.py:2900` | строка 1376 |
| Добавить алиас | `bot_handler.py:1380–1383` (`называй\|алиас\|псевдоним <алиас> как\|= <команда>`); защищённые `cancel, cansel, reset, clear, undo_clear` — строки 1390–1393 | строка 1396: `db.set_custom_alias(alias, canonical)` → `db.py:2930` (`INSERT ... ON CONFLICT`) | строка 1397 |
| Удалить алиас | `bot_handler.py:1404` (`удали алиас <алиас>`) | строка 1407: `db.remove_custom_alias(alias)` → `db.py:2945` (`DELETE FROM bot_custom_aliases`) | строка 1408 |

- Цель `скрыть`/`показать` приводится к каноническому имени через встроенную карту `cmd_aliases_map` (`bot_handler.py:1338–1352`). Отдельной функции `_resolve_cmd_target` в коде нет.
- Чтение: `CommandRegistry.get_active_commands` (`src/notifier/commands.py:206–240`) читает `db.get_command_settings()` (`db.py:2884`), отбрасывает команды с `is_enabled=False` (`commands.py:219–222`) и подставляет `custom_description` (`commands.py:223–225`); `resolve_command_or_alias` (`commands.py:250–303`) читает `db.get_custom_aliases()` (`commands.py:285`, `db.py:2921`).
- Сквозной путь от текста до `set_my_commands`: сообщение → `handle_user_text` → `db.*` (0003) → `setup_bot_commands(chat_id)` (`bot_handler.py:911–939`) → `bot.set_my_commands(commands, scope=BotCommandScopeChat(...))` (строка 928).

#### 3. Обновление меню после команды из чата

- Вызовы `setup_bot_commands(` в `src/`: 1363, 1376, 1397, 1408 (`bot_handler.py`) и `main.py:700`, `main.py:932`. Полный перечень — в разделе `### UXQ-01`.
- Тест `tests/test_phase3_reachability.py::_make_handler` (строки 59–64) подменяет `handler.setup_bot_commands` на `AsyncMock()`. Поэтому тест команд из чата проверяет БД и ответ бота, но не факт вызова `set_my_commands` после команды. Звено «команда чата → обновление меню» подтверждено трассой по коду, метка здесь — трасса.
- Тест на уровне реестра (`tests/test_command_aliases.py:45` test_hide_and_show_command, `:95` test_menu_command_rendering) показывает, что после `set_command_setting` меняется `get_telegram_commands()`: lms исчезает из меню и возвращается.

#### 4. Пример «переименуй /timesheet в /часы» (разбор по исходному тексту и коду)

- Исходный текст: `BACKLOG.md:158–160` («Пользователь может переименовывать команды (например, заменить `/timesheet` на удобное `/часы`)» и «Административное управление … «Переименуй команду /timesheet в /часы»»); `09-CONTEXT.md:14` и `:37`. Элемент `BLD-07` (`BACKLOG.md:262–270`) отдельно описывает переименование латинского слага в меню Telegram и не входит в UXQ-02.
- По коду глагол «переименуй» не распознаётся: `grep -rn "переимен" src/` — 0 совпадений. Распознаётся «называй|алиас|псевдоним <новое имя> как|= <команда>» (`bot_handler.py:1380–1383`). Тест `tests/test_phase3_reachability.py:216–222` проверяет «называй карточки как timesheet» → алиас «карточки» → `timesheet`.
- Кириллический `/часы` не может стать слагом нативного меню: `commands.py:17` (`_COMMAND_NAME_PATTERN = ^[a-z0-9_]{1,32}$`) и валидатор `CommandSpec.__post_init__` (`commands.py:32–37`) повторяют ограничение Telegram Bot API. В меню остаётся `/timesheet`. `/часы` работает как текстовый алиас: `commands.py:137` (`часы` в `default_aliases` команды `timesheet`) и пользовательские алиасы в `resolve_command_or_alias` (`commands.py:285–292`).
- Вывод: переименование реализовано алиасом, а не переименованием слага в меню. Переименование слага — `BLD-07` в бэклоге chat-app. Литеральная фраза «переименуй … в …» из диалога не выполняется, это записано в разделе «Наблюдения (не gaps)» для решения владельца.

#### 5. Выполненные команды

- `cd /opt/assistant-core && PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider tests/test_command_aliases.py tests/test_command_registry.py tests/test_no_inline_ddl.py -q` — код возврата 0, `30 passed in 45.53s`.
- `... tests/test_phase3_reachability.py -q` — код возврата 0, `12 passed in 11.43s`.

## Наблюдения (не gaps)

(заполняется в задаче 3)

## Gaps

(заполняется в задаче 2 и 3)

## Ограничения проверки

(заполняется в задаче 3)
