---
phase: 05-retro-verifikatsiya-v2-0
v2_phase: "09"
v2_source: /opt/chat-app/.planning/milestones/v2.0-phases/09-dinamicheskoe-menyu-i-interfeys
verified: 2026-10-18T21:32:20Z
status: gaps_found
score: "1 из 3 требований passed"
requirements: [UXQ-01, UXQ-02, UXQ-04]
gaps: [UXQ-01, UXQ-04]
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
| UXQ-01 | gap | `src/notifier/bot_handler.py:911–939` (`setup_bot_commands`) ← `src/notifier/commands.py:206–248` (реестр из коннекторов персоны); старт `src/main.py:700`, `src/main.py:932`; смена видимости и алиасов из чата `bot_handler.py:1363`, `:1376`, `:1397`, `:1408`. Разрыв: нет кода подключения и отключения коннекторов с вызовом обновления меню (`src/` вызывает `upsert_persona` только при старте, `src/persona/seed.py:43`) | `tests/test_bot_menu.py:11` (test_setup_bot_commands), `tests/test_command_registry.py:31` (test_command_registry_disable_connector); прогон 20 passed; журнал текущей инвокации (две строки «Successfully registered», 10 команд); смоук `scripts/deploy.py` без флагов (код 0) | трасса+e2e |
| UXQ-02 | passed | `src/notifier/bot_handler.py:432` (`F.text` → `handle_user_text`, 1311); скрыть 1354–1365, показать 1367–1378, алиас 1380–1402, удалить алиас 1404–1413; запись в БД `src/storage/db.py:2900` / `:2930` / `:2945`; таблицы `0003_bot_commands_and_feedback.sql:2–13`; меню `bot_handler.py:911` (`setup_bot_commands`) | `tests/test_phase3_reachability.py:192` (test_bot_hide_show_and_alias_flows_use_migrated_tables), `:237` (test_menu_command_reads_both_tables); `tests/test_command_aliases.py:45`; `tests/test_no_inline_ddl.py:75`. Прогон: 30 passed (3 файла), 12 passed (`test_phase3_reachability.py`) | трасса+e2e |
| UXQ-04 | gap | Части 1–2 (passed): `src/notifier/bot_handler.py:423` → `cb_dialog_feedback` (2698–2738) → `src/storage/db.py:2955` (INSERT в `dialog_feedback_log`); клавиатура `bot_handler.py:2631`, `src/notifier/telegram.py:153–163`; кэш `bot_handler.py:189`, `:549–553`, `:593`, `:1729–1730`, `:1783`, `:687–694`. Часть 3 (gap): `send_connector_health_alert` определён в `bot_handler.py:2660–2690`, вызовов в `src/` нет | `tests/test_command_aliases.py:171` (test_edge_caching_latency_sub_250ms), `:243`, `:272`, `:294`, `:345`, `:388`; `tests/test_phase3_reachability.py:261`, `:298`; прогон `-k "edge_caching or feedback or connector_health"`: 5 passed; `grep -rn send_connector_health_alert src/` — 1 строка (определение) | трасса+e2e |

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

- Исходный текст: `BACKLOG.md:158–161` («Пользователь может переименовывать команды (например, заменить `/timesheet` на удобное `/часы`)» и «Административное управление … «Переименуй команду /timesheet в /часы»»); `09-CONTEXT.md:14` и `:37`. Элемент `BLD-07` (`BACKLOG.md:262–270`) отдельно описывает переименование латинского слага в меню Telegram и не входит в UXQ-02.
- По коду глагол «переименуй» не распознаётся: `grep -rn "переимен" src/` — 0 совпадений. Распознаётся «называй|алиас|псевдоним <новое имя> как|= <команда>» (`bot_handler.py:1380–1383`). Тест `tests/test_phase3_reachability.py:216–222` проверяет «называй карточки как timesheet» → алиас «карточки» → `timesheet`.
- Кириллический `/часы` не может стать слагом нативного меню: `commands.py:17` (`_COMMAND_NAME_PATTERN = ^[a-z0-9_]{1,32}$`) и валидатор `CommandSpec.__post_init__` (`commands.py:32–37`) повторяют ограничение Telegram Bot API. В меню остаётся `/timesheet`. `/часы` работает как текстовый алиас: `commands.py:137` (`часы` в `default_aliases` команды `timesheet`) и пользовательские алиасы в `resolve_command_or_alias` (`commands.py:285–292`).
- Вывод: переименование реализовано алиасом, а не переименованием слага в меню. Переименование слага — `BLD-07` в бэклоге chat-app. Литеральная фраза «переименуй … в …» из диалога не выполняется, это записано в разделе «Наблюдения (не gaps)» для решения владельца.

#### 5. Выполненные команды

- `cd /opt/assistant-core && PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider tests/test_command_aliases.py tests/test_command_registry.py tests/test_no_inline_ddl.py -q` — код возврата 0, `30 passed in 45.53s`.
- `... tests/test_phase3_reachability.py -q` — код возврата 0, `12 passed in 11.43s`.

### UXQ-01: Меню команд строится из коннекторов персоны и обновляется при подключении и отключении

#### 1. Построение меню из коннекторов персоны (трасса по коду)

- Каталог `CommandRegistry._build_default_catalog` (`src/notifier/commands.py:121–204`): 10 команд в 5 категориях. Системные (`connector_id=None`): `ticker`, `evening`, `undo_clear`, `help`. Привязанные: `timesheet` → `timesheet`; `today` → `schedule_source`; `lms` → `lms`; `emails` → `mail`; `methodist` → `academic`; `git` → `git_source`.
- Фильтр `_is_connector_active` (`commands.py:76–102`): `mail` активна всегда (`:81–82`, привязка почты не проверяется); `academic` активна при непустом `methodist.file_catalog` (`:84–91`); остальные — при непустом списке `persona.connectors.<id>` (`:93–102`). Поле `is_active` привязки не читается.
- `get_active_commands` (`commands.py:206–240`) учитывает `db.get_command_settings()` (скрытые команды, `custom_description`); `get_telegram_commands` (`:242–248`) формирует `BotCommand`.
- Регистрация: `EmailBotHandler.setup_bot_commands` (`src/notifier/bot_handler.py:911–939`): `set_my_commands(..., scope=BotCommandScopeDefault())` (строка 920); `set_my_commands(..., scope=BotCommandScopeChat(chat_id=cid))` для chat_id и `allowed_user_id` (строки 921–928); лог «Successfully registered …» (932–937); при исключении «Failed to register bot commands» (938–939).

#### 2. Полный перечень вызовов `setup_bot_commands(` в `src/` (поиск 2026-10-18)

1. `src/main.py:700` — старт, `await bot_handler.setup_bot_commands()` до запуска циклов сбора.
2. `src/main.py:932` — старт, непосредственно перед `dp.start_polling` (строка 934).
3. `src/notifier/bot_handler.py:1363` — скрыть команду из чата.
4. `src/notifier/bot_handler.py:1376` — показать команду из чата.
5. `src/notifier/bot_handler.py:1397` — создать алиас из чата.
6. `src/notifier/bot_handler.py:1408` — удалить алиас из чата.
7. Определение: `src/notifier/bot_handler.py:911`.

#### 3. Код подключения и отключения коннекторов (поиск)

- Запись в `connector_bindings` в `src/` делает только `Database.upsert_persona` (`src/storage/db.py:79`, INSERT на строке 134). Его вызывает `src/persona/seed.py:43`, а тот однократно при старте из `src/main.py:652` (`seed_persona`).
- Поиск «подключи|отключи|connect» в `src/notifier/`, `src/brain/` и `src/main.py` не находит диалогового пути подключения или отключения коннектора. Совпадения `disconnect` относятся к клиенту Telethon (`src/main.py:758…958`, `src/collector/tg_collector.py:51`).
- Вывод: при подключении или отключении коннектора вызов `setup_bot_commands` отсутствует. Меню обновляется только при старте процесса. Диалоговое подключение и отключение относится к ONB-02 (Phase 8; `.planning/REQUIREMENTS.md:74`; `.planning/ROADMAP.md:279–287`, где прямо записано «после подключения и отключения меню команд бота обновляется (UXQ-01)»).

#### 4. Тесты

- `tests/test_bot_menu.py:11` (test_setup_bot_commands): `EmailBotHandler` на временной БД с миграциями; проверяет, что `set_my_commands` получил 10 команд, включая ticker, timesheet, today, git, lms, emails, methodist, evening, undo_clear, help. Метка e2e для построения меню.
- `tests/test_command_registry.py:8` (test_command_registry_default_catalog) и `:31` (test_command_registry_disable_connector): persona с пустыми привязками `timesheet` и `git_source` → команды `timesheet` и `git` не попадают в активные; `today` остаётся. Проверка фильтра по коннекторам на уровне реестра.
- Тесты не проверяют повторный вызов `set_my_commands` после изменения привязок: в тестах нет изменения `connector_bindings` с последующим обновлением меню.
- Выполнено: `cd /opt/assistant-core && PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider tests/test_bot_menu.py tests/test_command_registry.py tests/test_command_aliases.py -q` — код возврата 0, `20 passed in 33.70s`.

#### 5. Граничные случаи (разобраны вручную)

- Смена видимости из чата (скрыть, показать): меню обновляется (трасса `bot_handler.py:1363`, `:1376`); на уровне реестра — `tests/test_command_aliases.py:45` (test_hide_and_show_command).
- Алиасы из чата: вызывается `setup_bot_commands` (`:1397`, `:1408`), но алиасы в нативное меню не попадают (там только латинские слаги). Алиасы показывает `/menu` (`tests/test_phase3_reachability.py:237`).
- Подключение коннектора из диалога: пути нет, меню до перезапуска не меняется — gap (ONB-02).
- Отключение коннектора: привязка в рантайме не удаляется (запись только при старте); при следующем старте меню строится заново — gap (ONB-02).
- Пустой состав коннекторов: в меню остаются системные команды и `emails` (`mail` всегда активна, `commands.py:81–82`).

### Смоук deploy.py

- Команда: `cd /opt/assistant-core && python3 scripts/deploy.py` (без флагов). Флаги `--restart`, `--backup`, `--await-help`, `--confirm-help`, `--report` не использовались. Код возврата: 0.
- Таблица проверок (вывод скрипта; токен не выводится):

| Проверка | Результат |
|---|---|
| сервис active | ✓ |
| журнал текущего запуска доступен | ✓ |
| в окне старта нет ERROR/CRITICAL/Traceback | ✓ |
| polling бота запущен (запись в журнале) | ✓ |
| планировщик: задачи зарегистрированы (11 из 11) | ✓ |
| getMe: токен бота жив | ✓ |

- Итог автоматической части: ЗЕЛЁНАЯ. Строка итога: «ИТОГ СМОУКА: ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ». Это не красный исход: фаза подтверждения `/help` (`--await-help`, `--confirm-help`) по D-03 в этом плане не запускается. Строка «ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ», ожидавшаяся в черновике Argon, этим режимом не выводится.
- Список задач планировщика: скрипт печатает только счётчик «11 из 11». Имена взяты из `src/main.py` (`id=` у `add_job`): `schedule_sentinel_job`, `telegram_collector_job`, `email_collector_job`, `lms_monitor_job`, `morning_brief_job`, `evening_digest_job`, `aadhk_gdrive_sync_job`, `nightly_reset_and_priming_job`, `weekly_memory_review_job`, `live_ticker_refresh_job`, `git_progress_job`. Задачи проверки здоровья коннекторов в списке нет.
- Единственный живой внешний вызов: `getMe` (D-02). Сервис не перезапускался. Скрипт читает `.env` только ключ `TELEGRAM_BOT_TOKEN` (значение не выводится); сам агент `.env` не читал. Файл состояния `/var/lib/assistant-core/smoke-state.json` записан штатно (OPS-01, вне репозитория и вне БД), его содержимое в документ не переписано.
- Поправка к RESEARCH (D-03): `deploy.py` меню не проверяет (`05-RESEARCH.md:185`, `:357`), подтверждение меню дано журналом ниже.

#### 6. Журнал старта: строка «Successfully registered» (текущая инвокация)

- Команда: `INV=$(systemctl show assistant-worker.service -p InvocationID --value)`; `journalctl -u assistant-worker.service _SYSTEMD_INVOCATION_ID="$INV" --no-pager | grep 'Successfully registered' | sed -E 's/\(chats:[^)]*\)/(chats: скрыто)/'`.
- Инвокация: `52e2ba619cbf424bafe106b59140ca19`, `ActiveState=active`, `ActiveEnterTimestamp` 2026-10-18 17:14:12 UTC.
- Найдено 2 строки (старт, вызовы `main.py:700` и `main.py:932`), обе очищены и идентичны по содержанию: «Successfully registered 10 Telegram bot menu commands across categories: academic, mail, projects, system, timesheet (chats: скрыто)». Строк «Failed to register bot commands» в инвокации: 0. Идентификаторы чатов в документ не переписаны.
- Число команд 10 соответствует каталогу при всех привязках персоны, включённых в текущем составе.

### UXQ-04: Edge caching, телеметрия 👍/👎 и проактивные алерты коннекторов

Требование состоит из трёх частей. Части 1 и 2 достижимы из рантайма (passed). Часть 3 не доставляется владельцу (gap). Итоговый статус строки — gap.

#### Часть 1: телеметрия 👍/👎 — passed (трасса+e2e)

- Прикрепление клавиатуры: `handle_user_text` вызывает `_handle_secretary_dialog` (`src/notifier/bot_handler.py:1472`, `:1476`; определение `:2569`). После отправки ответа получен `sent_msg_id` и вызвано `build_dialog_feedback_keyboard(sent_msg_id)` (`bot_handler.py:2631`; определение `src/notifier/telegram.py:153–163`, кнопки `fb:up:<id>` и `fb:down:<id>`), затем `edit_message_reply_markup` (`bot_handler.py:2635–2639`).
- Нажатие: `self.router.callback_query(F.data.startswith("fb:"))` (`bot_handler.py:423`) → `cb_dialog_feedback` (`bot_handler.py:2698–2738`) → защита от повтора `_feedback_voted` (определение `:191`, проверка `:2719–2723`) → `self.db.log_dialog_feedback(msg_id, user_id, feedback_type)` (`bot_handler.py:2724` → `src/storage/db.py:2955`, SQL `INSERT INTO dialog_feedback_log` в строке 2962) → кнопка заменяется на «Спасибо за отзыв!» (`:2727–2734`) и toast (`:2738`).
- Таблица `dialog_feedback_log` создана в `0003_bot_commands_and_feedback.sql:15–21`.
- Тесты: `tests/test_command_aliases.py:272` (test_dialog_feedback_db_logging), `:294` (test_build_dialog_feedback_keyboard_and_callbacks: структура клавиатуры, callback, дедупликация, одна строка в БД), `:388` (test_secretary_dialog_feedback_attachment); `tests/test_phase3_reachability.py:261` (test_feedback_buttons_from_keyboard_reach_the_log), `:298` (test_feedback_keyboard_is_attached_in_runtime_code, проверка AST). Прогон: passed.
- Ограничение: нажатие не проходит через Dispatcher aiogram в тестах, вызываются методы хэндлера на временной БД. Вердикт: passed, метка трасса+e2e.

#### Часть 2: edge cache — passed (трасса+e2e), с ограничениями теста

- Кэш: `self._edge_cache: dict[str, tuple[float, str]] = {}` в памяти процесса (`src/notifier/bot_handler.py:189`).
- `/today`: `handle_cmd_today` (`bot_handler.py:543`): ключ `today:<дата>` (`:549`); при `now_ts < exp_at` (`:551–553`) возвращается сохранённый текст без обращения к БД; при промахе расчёт из SQLite и запись с TTL 15 минут (`:593`). Вызовы: команда `/today` (`:347`), fast path (`:1426–1427`).
- `/timesheet`: `handle_cmd_timesheet` (`bot_handler.py:1716`): ключ `timesheet:<дата>` (`:1728`), попадание (`:1729–1730`), запись с TTL 30 минут (`:1783`). Вызовы: `/timesheet` (`:346`), fast path (`:1441–1442`).
- Инвалидация: `clear_edge_cache(prefix)` (`bot_handler.py:687–694`). Вызывается из `cb_ticker_refresh` (`:897`, полный сброс по `tk:refresh`, `:413`) и из `cb_timesheet_sync` (`:1795`, префикс `timesheet`, по `ts:sync_gdrive`, `:373`). Тест инвалидации: `tests/test_command_aliases.py:243` (test_clear_edge_cache_invalidation).
- Проверка допущения RESEARCH A3 («латентность 250 мс не измерена нигде», `05-RESEARCH.md:557`): тест `tests/test_command_aliases.py:171` (test_edge_caching_latency_sub_250ms) читан полностью. Он замеряет `time.perf_counter()` повторных вызовов `handle_cmd_today` и `handle_cmd_timesheet` (`LATENCY_SAMPLES = 5`, строка 8; минимум из 5 замеров; порог `< 250.0` мс, строки 202 и 237). Допущение A3 опровергнуто: замер есть.
- Что тест не доказывает: попадание в кэш. В тесте нет ассерта на `_edge_cache`, на число обращений к БД или на отсутствие расчёта. Порог проходит и при расчёте, если он быстрый на временной БД с замоканными notifier и сервисом табеля. Попадание в кэш подтверждено только трассой (`:551–553`, `:1729–1730`).
- Вердикт части 2: passed (латентность проверяется тестом через `EmailBotHandler`, метка трасса+e2e). Слабость метрики (минимум из 5, без p95) записана в наблюдениях.

#### Часть 3: проактивные алерты коннекторов — gap (функция не доставляется)

- Определение: `EmailBotHandler.send_connector_health_alert(chat_id, service_name, issue_text, fix_action="retry")` (`src/notifier/bot_handler.py:2660–2690`), карточка с кнопкой `chk:<service_name>` (`:2682`).
- Поиск `grep -rn "send_connector_health_alert" src/ scripts/`: одна строка, определение `bot_handler.py:2660`. Вызовов 0.
- Планировщик: 11 `add_job` в `src/main.py:808–911` (список в разделе смоука); задачи проверки коннекторов нет.
- `health_check()` коннекторов: определения в `src/core/ports/connectors.py:24`, `src/calendar/provider.py:23`, `src/parser/provider.py:24`, `src/connectors/aadhk/provider.py:23`, `src/connectors/guap_lms/provider.py:38`, `src/connectors/git/provider.py:66`. Вызовов в `src/` нет.
- Callback `chk:` зарегистрирован в `bot_handler.py:422`, обрабатывается `cb_connector_health_check` (`:2692–2696`). Метод отвечает строкой «Проверка связи со службой … » и не вызывает `health_check()`.
- Тест `tests/test_command_aliases.py:345` (test_connector_health_alert_and_check) вызывает `send_connector_health_alert` (`:363`) и `cb_connector_health_check` (`:381`) напрямую. Он проверяет изолированную функцию, а не достижимость из рантайма, и по D-01 не доказывает доставку.
- Вывод: алерт о падении коннектора из рантайма не может прийти владельцу. Нет вызывающего кода ни в коннекторах, ни в планировщике. Вердикт части 3: gap.
- Класс по D-09: улучшение / функция не доставляется. Это уведомление, не действие, поэтому не безопасность, не HITL и не NDA. Мёртвый путь в этой фазе не исправляется (D-10).

#### Итог строки UXQ-04: gap

Части 1–2 passed, часть 3 gap. Строка получает gap, пока алерты не доставляются.

## Наблюдения (не gaps)

1. UXQ-02, фиксированный набор слов. Команды «скрой» и «покажи» (`src/notifier/bot_handler.py:1355`, `:1368`) принимают только `lms`, `git`, `гит`, `коммиты`, `лабы`, `табель`, `часы`, `почта`, `расписание`, `пары`, `методист`. Английские имена `timesheet`, `today`, `emails`, `methodist`, а также `ticker`, `evening`, `help`, `undo_clear` из чата не скрываются: сообщение не распознаётся как команда управления меню. Решение владельца: расширить список (улучшение, 999.x) или принять ограничение.
2. UXQ-02, переименование. Литеральная фраза «переименуй команду /timesheet в /часы» не распознаётся (`grep -rn "переимен" src/` — 0 совпадений). Переименование реализовано алиасом «называй <новое> как <команда>». Слаг в нативном меню не меняется (ограничение Telegram, элемент `BLD-07`). Решение владельца: принять алиас как закрытие UXQ-02 или перевести литеральный глагол в gap-улучшение.
3. UXQ-02, обновление меню после команды из чата. Тест `tests/test_phase3_reachability.py` подменяет `setup_bot_commands` (`_make_handler`, строки 59–64). Вызов `set_my_commands` после команды чата тестами не проверен; звено подтверждено трассой.
4. UXQ-01, mail всегда активна. `commands.py:81–82` возвращает `True` для `mail` без проверки привязки почты. Расходится с формулировкой «меню строится из коннекторов персоны».
5. UXQ-04, кэш в памяти процесса. `_edge_cache` (`bot_handler.py:189`) пуст после каждого перезапуска. В исходном тексте (`BACKLOG.md:175`) сказано «из SQLite», а решение D-04 (`09-CONTEXT.md:50`) фиксирует in-memory кэш. Текущая реализация соответствует D-04; расхождение с формулировкой BACKLOG отмечено.
6. UXQ-04, кнопка проверки. Если алерт будет подключён, `callback_data` вида `chk:<название службы>` с кириллицей может превысить лимит Telegram в 64 байта. Предположение, не проверено: вызова алерта нет.
7. RESEARCH A3 опровергнуто (см. часть 2 UXQ-04): замер latency существует, но он не доказывает попадание в кэш.
8. Тестовый набор: `tests/test_fast_intent_router.py` при отдельном запуске (`timeout 300`) выдал `10 passed` и не завершил процесс за 300 с (код 124). Тот же файл в наборе из 6 файлов завершился с кодом 0 (`55 passed`). Это наблюдение, не красный гейт; по указанию оркестратора известна утечка потоков aiosqlite. Полный гейт `scripts/gate.py` агентом не запускался.

## Gaps

| Требование | Класс по D-09 | Предложение оформления | Привязка |
|---|---|---|---|
| UXQ-01 | улучшение / функция не доставляется (не безопасность, не HITL, не NDA) | Вызывать `setup_bot_commands(chat_id=...)` сразу после изменения состава коннекторов в диалоге подключения и отключения (через ONB-02) и после ручного изменения привязок. Новое требование не создаётся | существующее требование ONB-02 (Phase 8, `.planning/REQUIREMENTS.md:74`); запись бэклога 999.x (план 05-08) |

| UXQ-04 | улучшение / функция не доставляется (не безопасность, не HITL, не NDA) | Подключить `send_connector_health_alert` к периодической проверке `health_check()` коннекторов (задача планировщика с дедупликацией и cooldown); сделать `cb_connector_health_check` реальной проверкой связи. Отдельно, по решению владельца: измерить задержку кэша на реальных данных расписания (сейчас замер best-of-5 на моках) | запись бэклога 999.x (план 05-08); новое требование не создаётся |

## Ограничения проверки

1. Черновик agy/Argon (acc2, gemini-4-argon-high) использован как недоверенный ввод по решению владельца 2026-10-18. Каждый file:line и каждый вердикт проверены по коду. Вердикты черновика совпали с итоговыми (UXQ-01 gap, UXQ-02 passed, UXQ-04 gap), но доказательная часть содержала ошибки. Исправлено 21 пункт (список ниже).
2. Пробы «ПРОБА: выполнить проверяющему» выполнены агентом: все pytest-наборы (код возврата 0), узкий запрос журнала с верным юнитом, `scripts/deploy.py` без флагов. Черновик эти команды не запускал.
3. Зависание `tests/test_fast_intent_router.py` при отдельном запуске зафиксировано как наблюдение 8, не как красный гейт. Полный гейт `python3 scripts/gate.py` агентом не запускался (запускает оркестратор).
4. Живые вызовы: единственный внешний вызов — `getMe` внутри `scripts/deploy.py` (D-02). Не использовались `--restart`, `--backup`, `--await-help`, `--confirm-help`, `--report`. `systemctl show` вызывался только с `-p InvocationID`, `-p ActiveEnterTimestamp -p ActiveState`; параметр `Environment` не выводился.
5. Боевая БД `/opt/assistant-core/data/assistant.db` не открывалась; `/opt/assistant-core/assistant.db` не читался. Файл `.env` агентом не читался. Скрипт `deploy.py` читает из него только ключ `TELEGRAM_BOT_TOKEN` для `getMe`, значение не выводится. Файл состояния смоука `/var/lib/assistant-core/smoke-state.json` записан штатно (OPS-01), содержимое не переписано.
6. Сервисы: `assistant-worker.service` не перезапускался (инвокация `52e2ba619cbf424bafe106b59140ca19`, активна с 17:14:12 UTC). `chat-app.service` неактивен; для UXQ не нужен, не запускался и не менялся.
7. Код, тесты и миграции не менялись (D-10). Новых тестов и проб-скриптов в репозитории нет. Изменения вне `.planning/` отсутствуют.
8. В документ не попали сырые строки журнала, идентификаторы чатов (заменены на «скрыто»), токены и адреса e-mail. Идентификатор инвокации systemd приведён: он не относится ни к чату, ни к токену.
9. Итог смоука «ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ», а не «ЗЕЛЁНЫЙ». Фаза `/help` требует сообщения владельца боту и по D-03 этого плана не запускалась. Это решение владельца (см. итоговый отчёт), а не провал проверки.
10. Диалоговое подключение и отключение коннектора не проверялось в рантайме: пути в коде нет. Отправка проактивного алерта не проверялась: вызова нет.
11. Латентность кэша измерена тестом на моках (минимум из 5 замеров), а не на реальных данных расписания. Попадание в кэш подтверждено трассой, не замером.
12. Команды скрыть, показать, алиас и удалить алиас проверены тестами на временной БД, без сообщений живому боту.
13. Таблицы 0003 проверены миграцией, тестами на временной БД и трассой. Живую БД агент не открывал.

**Исправления черновика Argon (21 пункт, сверено с кодом):**

1. Источник UXQ: указан `v2.0-REQUIREMENTS.md:38–42` и `:163–166`. В файле нет ни одного `UXQ` (`grep -c`). Текст требований в `BACKLOG.md:145–182`.
2. Ссылки на ONB-02: `.planning/REQUIREMENTS.md:91` → `:74`; `.planning/ROADMAP.md:208` → `:279–287`.
3. Ссылка на допущение A3: `05-RESEARCH.md:547` → `:557`.
4. Журнал: юнит `assistant-core` → `assistant-worker`; фильтр `--since "7 days ago"` → по `_SYSTEMD_INVOCATION_ID`; маркер `Failed to setup bot commands` → фактический `Failed to register bot commands` (`bot_handler.py:938–939`).
5. Смоук: юниты `assistant-core.service` и `chat-app.service` → только `assistant-worker` (`scripts/deploy.py:50`).
6. Смоук: состав проверок (9 пунктов, включая HTTP 8000, SQLite integrity, RAM/OOM, «Start polling») → фактически 6 строк таблицы.
7. Смоук: ожидаемая строка «ИТОГ СМОУКА: ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ» → фактически «ИТОГ СМОУКА: ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ».
8. Каталог команд: перечислены `status`, `menu`, `week`, `mail`, `labs` и класс `CommandDef` → фактически 10 команд и класс `CommandSpec` (`commands.py:20–37`).
9. `_is_connector_active`: якобы проверяет `binding.is_active` → фактически `bool(bindings)`; `mail` всегда активна (`commands.py:81–82`).
10. `_resolve_cmd_target` (`bot_handler.py:1337–1352`) не существует → встроенная карта `cmd_aliases_map` (`:1338–1352`).
11. Регулярные выражения скрыть, показать и алиас процитированы неверно (добавлены `\s*$` и `[a-z0-9_]+`); переменная `_protected_cmds` → фактически локальная `protected` (`:1390`).
12. `handle_cmd_menu`: `bot_handler.py:469–511` → `:941`.
13. Сигнатура `send_connector_health_alert(connector_name, error_details)` → `(chat_id, service_name, issue_text, fix_action)`.
14. `_build_today_Quick_actions_kb` (`:513–541`) в коде отсутствует.
15. Тесты `test_handle_cmd_menu_groups_by_category` и `test_edge_cache_clear` не существуют; есть `test_clear_edge_cache_invalidation`.
16. Проба `-k "edge_caching or feedback or connector_health"`: указано 6 тестов → фактически `5 passed, 7 deselected`.
17. Диапазоны строк тестов (`test_command_aliases.py:21–167`, `:272–341`, `:345–384` и др.) → начала функций `:12`, `:45`, `:70`, `:95`, `:171`, `:243`, `:272`, `:294`, `:345`, `:388`.
18. `upsert_persona`: `db.py:105–141` → `db.py:79`, INSERT в `connector_bindings` на `:134`.
19. Покрытие меню после команд чата: черновик относил его к e2e. Тест подменяет `setup_bot_commands` (`test_phase3_reachability.py:59–64`), поэтому звено подтверждено трассой.
20. Вывод «тест кэша подтверждает попадание в кэш»: тест проверяет только латентность и инвалидацию (см. UXQ-04, часть 2).
21. Формат таблицы: обратные кавычки вокруг ID и статусов ломали обязательный формат строки (`| UXQ-01 | gap |`).
