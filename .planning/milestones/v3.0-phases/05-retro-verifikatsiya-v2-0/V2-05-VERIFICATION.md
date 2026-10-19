---
phase: 05-retro-verifikatsiya-v2-0
v2_phase: "05"
v2_source: /opt/chat-app/.planning/milestones/v2.0-phases/05-edinyy-hitl-primitiv
verified: 2026-10-18T22:05:00Z
status: gaps_found
score: "1 из 1 требований passed"
requirements: [HIT-01]
gaps: [HIT-05]
---

# V2-05: Единый HITL-примитив (ретро-верификация фазы 05 v2.0)

## Источник (только чтение)

- Исходный каталог: `/opt/chat-app/.planning/milestones/v2.0-phases/05-edinyy-hitl-primitiv/` (только `ls`, файлы не открывались для правки).
- Состав каталога (11 файлов, проверено `ls`): `05-01-PLAN.md`, `05-01-SUMMARY.md`, `05-02-PLAN.md`, `05-02-SUMMARY.md`, `05-03-PLAN.md`, `05-03-SUMMARY.md`, `05-04-PLAN.md`, `05-04-SUMMARY.md`, `05-CONTEXT.md`, `05-RESEARCH.md`, `05-VALIDATION.md`. Собственного `05-VERIFICATION.md` в v2.0 нет.

## Вердикты

| Требование | Статус | Точка входа в рантайме (file:line) | Тест или команда проверки | Метка |
|---|---|---|---|---|
| HIT-01 | passed | `src/main.py:647` (`db.init_db()`) → миграция `0002`; `src/notifier/bot_handler.py:399-400` (`hitl:confirm:` / `hitl:reject:`) → `cb_hitl_confirm` `:2051`, `resume_action` `:2078`; `bot_handler.py:403-409` (`act:cal\|rem\|drf:conf/rej:`) → `_handle_hitl_action_callback` `:2358`, `resume_action` `:2401`; `/opt/assistant-shared/assistant_shared/hitl/engine.py:28-62` (`resume_action`) → `store.py:116-139` (`confirm_action`) | `tests/test_hitl_safety_guardrails.py tests/test_bot_hitl_parity.py tests/test_hitl_telegram_cards.py`: 18 passed, код 0 (3 прогона из 3 зелёные); `/opt/assistant-shared/tests`: 211 passed, код 0; e2e: `tests/test_hitl_telegram_cards.py:448` (`test_cb_act_deduplication_and_protection`, двойное нажатие даёт одно напоминание), `tests/test_bot_hitl_parity.py:72` (`test_cb_hitl_confirm_authorized`, кнопка → реальный обработчик удаления на временной БД) | трасса+e2e |

Решение владельца 2026-10-18 №3 (как указано в `05-03-PLAN.md`): примитив `ConfirmationStore` + `resume_action` + миграция `0002_pending_confirmations` засчитаны как выполнение HIT-01. Отсутствие декоратора `@requires_confirmation` записано в «Наблюдениях», не в «Gaps». Обход единой точки в очистке диалога записан отдельно (HIT-05, см. «Gaps»).

## Доказательства

### HIT-01

**Четыре части требования (проверено чтением и grep):**

- (а) `ConfirmationStore` (`/opt/assistant-shared/assistant_shared/hitl/store.py`): класс `:20`, `create_confirmation` `:24-75`, `get_confirmation` `:77-98` (авто-перевод в `expired` по TTL), `confirm_action` `:116-139`, `reject_action` `:141-164`. `confirm_action` выполняет условный `UPDATE ... WHERE id = ? AND status = 'pending'` (`:124-131`) и при `rowcount == 0` возвращает `None` (`:133-134`).
- (б) `resume_action` (`/opt/assistant-shared/assistant_shared/hitl/engine.py`): реестр `_ACTION_HANDLERS` `:15`, `register_action_handler` `:18-21`, `get_action_handler` `:24-25`, `resume_action` `:28-62`. Атомарное подтверждение через `store.confirm_action` `:39`; при отсутствии записи `ValueError` `:40-46`; при отсутствии обработчика `LookupError` `:48-51`; исполнение обработчика ровно один раз `:60-62` (`handler(conf)` для корутины или синхронной функции).
- (в) Миграция `/opt/assistant-shared/assistant_shared/db/migrations/0002_pending_confirmations.sql`: таблица `pending_confirmations` `:2-14`, индексы `:16-18`. Применяет `run_migrations` (`/opt/assistant-shared/assistant_shared/db/migrator.py:151`, glob `*.sql` `:164`, `_apply_migration` `:121`, `BEGIN IMMEDIATE` `:129`). Тесты: `/opt/assistant-shared/tests/test_hitl_shared.py:33-55` (`test_migration_0002`: таблица, колонки, индексы), `/opt/assistant-shared/tests/test_migrations.py:54` (ожидаемые таблицы, включая `pending_confirmations`) и `:65-83` (`test_initial_schema_creates_all_tables`).
- (г) Декоратор `@requires_confirmation`: `/opt/assistant-shared/assistant_shared/hitl/decorators.py` (26 строк) содержит только `create_hitl_conflict_exception` `:13-26`. Команда `grep -rn "requires_confirmation" /opt/assistant-shared /opt/assistant-core/src /opt/assistant-core/tests --include=*.py` вернула 0 совпадений (код возврата grep 1). По решению №3 это наблюдение, не gap.

**Трасса из рантайма (`файл:строка`):**

1. Старт демона: `src/main.py:646` (`db = Database(config.SQLITE_DB_PATH)`), `:647` (`await db.init_db()`) → `src/storage/db.py:73-75` (`init_db` → `_apply_migrations`) → `db.py:71` (`asyncio.to_thread(run_migrations, target)`) → миграция `0002` (см. пункт (в)).
2. Регистрация обработчиков: `src/notifier/bot_handler.py:193-194` (в `__init__`: `_register_handlers()`, `_register_hitl_action_handlers()`); `:205` (`_register_hitl_action_handlers`); `register_action_handler` вызывается для `delete_project` `:223`, `delete_document` `:224`, `delete_task` `:225`, `delete_reminder` `:226`, `create_calendar_event` `:297`, `create_reminder` `:298`, `draft_email_reply` `:299`.
3. Подключение роутера: `src/main.py:687-699` (создание `EmailBotHandler`, `dp.include_router(bot_handler.router)` `:699`).
4. Путь 1, веб-карточка: роутер `bot_handler.py:399-400` → `cb_hitl_confirm` `:2051`. Авторизация `:2053-2055` (`_is_authorized` `:307-311`, закрыт по умолчанию при `allowed_user_id is None`). Загрузка `get_confirmation` `:2060`. Истечение TTL `:2067-2071`. Идемпотентность `status != PENDING` `:2073-2075`. Вызов `resume_action(conf_id, store, confirmed_by=...)` `:2078` → `engine.py:28` → `store.py:116`.
5. Путь 2, карточки секретаря: создание записи `_handle_secretary_dialog` `bot_handler.py:2569`, `store.create_confirmation` `:2601`. Роутер `:403-409` → `cb_act_calendar_confirm` `:2491-2493`, `cb_act_reminder_confirm` `:2553-2555`, `cb_act_draft_confirm` `:2561-2563` → `_handle_hitl_action_callback` `:2358`. Авторизация `:2360-2362`. Загрузка `:2370-2371`. Проверки существования, истечения и статуса `:2372-2397`. Вызов `resume_action` `:2401` → `engine.py:28` → `store.py:116`.
6. Путь 3, Notion (подключён в v3, фаза 4): роутер `bot_handler.py:418` (`ntn:conf:`) → `cb_ntn_confirm` `:2242`, `resume_action` `:2274`, откат через `store.reopen_action` `:2277`, `:2282`, `:2290`. Регистрация обработчика `notion_project_sync` (`src/brain/git_evaluator.py:209`) условна: `src/composition.py:151-153` возвращает `None`, если `default_git_source_provider()` пуст; `src/main.py:674-678` оборачивает вызов в `try`.

**Идемпотентность и однократность:**

- Двойное нажатие в пути 2 закрыто тестом: `tests/test_hitl_telegram_cards.py:448-512` (второе нажатие отвечает «Запрос уже обработан или истек», напоминаний после него ровно `base + 1`).
- Однократное исполнение на уровне примитива: `/opt/assistant-shared/tests/test_hitl_shared.py:113-147` (`executed_count == 1` после повторного `resume_action`, `ValueError` `match="cannot be resumed"`).
- Для пути 1 (веб-карточка) повторного нажатия отдельным тестом не покрыто. Защита обеспечивается проверкой статуса `:2073-2075` и условным `UPDATE` в `store.py:124-134`. Записано в «Наблюдениях».

**Тесты пути 1 и 2 на временной БД (метка e2e):**

- `tests/test_bot_hitl_parity.py:72` (`test_cb_hitl_confirm_authorized`): callback `hitl:confirm:<id>` → `cb_hitl_confirm` → реальный обработчик `delete_task` → строка задачи удалена, статус `CONFIRMED`, `confirmed_by` заполнен.
- `tests/test_bot_hitl_parity.py:132` (неавторизованный), `:187` (отклонение), `:240` (истёкший срок).
- `tests/test_hitl_telegram_cards.py:189` (`test_cb_act_calendar_confirm_and_reject`, `create_event.assert_called_once()` на `:228`), `:515` (неавторизованный), `:557` (истёкший срок).

**Выполненные команды (каталог `/opt/assistant-core`, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, `timeout 300`):**

| Команда | Код возврата | Результат |
|---|---|---|
| `.venv/bin/pytest tests/test_hitl_safety_guardrails.py tests/test_bot_hitl_parity.py tests/test_hitl_telegram_cards.py -q` (прогон 1) | 0 | 18 passed in 14.50s |
| то же (прогон 2) | 0 | 18 passed in 12.81s |
| то же (прогон 3) | 0 | 18 passed in 13.18s |
| `.venv/bin/pytest /opt/assistant-shared/tests -q` | 0 | 211 passed in 28.06s |

Проверка неизменности assistant-shared: `git -C /opt/assistant-shared status --porcelain --ignored | sort` до и после прогона совпал (6 строк, одинаковые). Изменений в `/opt/assistant-shared` нет.

Строка вердикта проверена командой `grep -E '^\| HIT-01 \| (passed|gap) \|'`: код возврата 0.

## Наблюдения (не gaps)

1. **Декоратор `@requires_confirmation` отсутствует.** `grep` по трём деревьям вернул 0 совпадений (см. пункт (г)). По решению владельца №3 это не gap. Текст требования HIT-01 упоминает декоратор буквально, поэтому вердикт опирается на решение владельца, а не на букву требования. `decorators.py:7` импортирует `fastapi`, которого нет в зависимостях `assistant-shared` (известно как A-4 в `STATE.md`).
2. **Идемпотентность пути 1 не покрыта повторным нажатием в тестах.** Защита есть в коде (`bot_handler.py:2073-2075`, `store.py:124-134`), отдельного теста двойного нажатия для `hitl:confirm:` нет.
3. **Тесты очистки диалога зелёные, но обход не ловят.** `tests/test_hitl_safety_guardrails.py` (`:42-79`, `:83-134`) проверяет карточку и итоговую очистку, но не проверяет `pending_confirmations` и не вызывает `resume_action`. Подробности в «Gaps» (HIT-05).
4. **Голосовой и текстовый пути `/clear` не очищают память.** `bot_handler.py:1453-1459` (текст без слэша) и `:2794-2796` (голос) только вызывают `_warn_clear_requires_slash` (`:1888`). Это не обход.
5. **Регистрация `notion_project_sync` условна** (см. трассу, пункт 6). Для HIT-01 не влияет, относится к V2-07.
6. **Тесты очистки диалога зелёные, но обход не ловят.** Тесты `tests/test_hitl_safety_guardrails.py` (прогон зелёный, см. таблицу команд) и `tests/test_bot_hitl_parity.py:277-314` проходят при наличии обхода; `test_dlg_clear_registers_in_confirmation_store` закрепляет постфактум-запись как ожидаемую. Gap HIT-05 записан по коду, а не по падению тестов.
7. **Стабильность.** Набор `test_hitl_safety_guardrails.py tests/test_bot_hitl_parity.py tests/test_hitl_telegram_cards.py` прошёл 3 из 3 прогонов (18 passed). Падений, зависаний и `database is locked` в этих прогонах не наблюдалось. `test_concurrent_confirmations_isolation` (`tests/test_concurrency_isolation.py:97`, ISO-04) в эту проверку не входит.

## Gaps

### HIT-05 (кандидат): обход единой точки подтверждения в очистке диалога

**Вход и карточка (`/clear`, `/reset`):**

- Регистрация команды: `src/notifier/bot_handler.py:428` (`Command("clear", "reset")` → `handle_cmd_clear_dialog`). Текст без слэша и голос очистку не запускают: `:1453-1459` и `:2794-2796` только вызывают `_warn_clear_requires_slash` (`:1888`).
- `handle_cmd_clear_dialog` `:1897-1930`: проверка `_is_authorized` `:1899`, подсчёт `get_active_dialog_count` `:1902`, карточка с кнопками `callback_data="dlg:confirm_clear"` `:1922` и `"dlg:cancel_clear"` `:1923`. Запись `PendingConfirmation` при показе карточки **не создаётся**, `confirmation_id` в `callback_data` **не передаётся** (константная строка, без привязки к записи и без TTL).
- Регистрация колбэка: `bot_handler.py:394` (`F.data == "dlg:confirm_clear"` → `cb_dlg_confirm_clear`).

**Разбор `cb_dlg_confirm_clear` (`bot_handler.py:1932-1967`):**

- (а) Авторизация: `:1933-1935` (`_is_authorized`, при отказе `answer` и `return`).
- (б) Постфактум-создание записи в момент нажатия: `try:` `:1938`, `store = self._get_confirmation_store()` `:1939`, `store.create_confirmation(action_type="clear_dialog", target_id=<user_id>, channel=TELEGRAM, ttl_minutes=10)` `:1940-1947`.
- (в) Немедленное подтверждение той же записи без решения пользователя: `await store.confirm_action(conf.id, ...)` `:1948`.
- (г) Fail-open: `except Exception:` `:1949`, `logger.warning("Не удалось зафиксировать clear_dialog в ConfirmationStore", exc_info=True)` `:1950`. Ошибка хранилища не прерывает выполнение.
- (д) Прямое разрушающее действие без `resume_action`: `archived = await self.db.clear_dialog_history(callback.from_user.id)` `:1952` → `src/storage/db.py:2365-2373` (`UPDATE bot_dialog_history SET is_archived = TRUE WHERE user_id = ? AND ...`). Обработчик `clear_dialog` в реестре `register_action_handler` не зарегистрирован (`grep` по `src/` и `/opt/assistant-shared/assistant_shared`: совпадений с `clear_dialog` как ключом реестра нет).

**Смягчающие факты (для честной оценки, серьёзность не снижена):** очистка мягкая (архивирование; восстановление через `dlg:undo_clear`, `bot_handler.py:2326`, `db.py:2347`), выполняется только для владельца (`_is_authorized`), нажатие кнопки остаётся действием человека. Требование HITL, однако, не выполнено: запись создаётся после нажатия, а не до него, не привязана к карточке, не имеет TTL при показе, и при сбое ConfirmationStore очистка всё равно выполняется.

**Отмена (`cb_dlg_cancel_clear`, `:1969-1989`):** та же схема постфактум: `create_confirmation` `:1976-1983`, `reject_action` `:1984`, `except` `:1985-1986`. Действие не выполняется, запись пишется задним числом.

**Полный перечень вызовов `confirm_action(` и `resume_action(` в `src/` (проверено grep):**

| Файл:строка | Вызов | Функция | Роль |
|---|---|---|---|
| `src/notifier/bot_handler.py:1948` | `confirm_action` | `cb_dlg_confirm_clear` | **ОБХОД**: прямое подтверждение, за ним очистка без `resume_action` |
| `bot_handler.py:2078` | `resume_action` | `cb_hitl_confirm` | единая точка |
| `bot_handler.py:2274` | `resume_action` | `cb_ntn_confirm` | единая точка (откат `reopen_action` `:2277`, `:2282`, `:2290`) |
| `bot_handler.py:2401` | `resume_action` | `_handle_hitl_action_callback` | единая точка |
| `bot_handler.py:1984`, `:2132`, `:2321`, `:2477` | `reject_action` | отмена `dlg`, `hitl`, `ntn`, `act` | отказ, действие не выполняется |
| `bot_handler.py:2601`, `src/brain/git_evaluator.py:566` | `create_confirmation` | `_handle_secretary_dialog`, дайджест Git | создание записи до показа карточки |

Вызовов `resume_action` в `src/` три (`:2078`, `:2274`, `:2401`). Другого обхода, кроме `cb_dlg_confirm_clear`, не найдено.

**Тесты, которые не ловят обход:**

- `tests/test_hitl_safety_guardrails.py:42-79` (`test_bot_handler_clear_dialog_hitl_card`): проверяет `active_count == 2` (`:68-69`) и кнопки (`:75-79`). Записи в `pending_confirmations` после показа карточки не проверяет.
- `tests/test_hitl_safety_guardrails.py:83-134` (`test_bot_handler_confirm_cancel_undo_callbacks`): вызывает `cb_dlg_confirm_clear` (`:114`), проверяет `get_active_dialog_count == 0` (`:117`). `ConfirmationStore` и `resume_action` не проверяет.
- `tests/test_bot_hitl_parity.py:277-314` (`test_dlg_clear_registers_in_confirmation_store`): вызывает `cb_dlg_confirm_clear` без предварительной карточки (`:295`) и **закрепляет обход** как ожидаемое поведение: проверяет строку `clear_dialog` со статусом `confirmed` и каналом `telegram` (`:307-314`). Не проверяет состояние `pending`, TTL карточки, вызов `resume_action` и поведение при сбое ConfirmationStore.
- Тест на сбой ConfirmationStore при очистке диалога в `tests/` отсутствует.

**Gap:**

| Требование | Класс по D-09 | Предложение оформления | Привязка |
|---|---|---|---|
| HIT-01 (обход единой точки), кандидат HIT-05 | HITL (высокий приоритет): очистка памяти диалога выполняется напрямую после `confirm_action` без `resume_action`; запись создаётся постфактум при нажатии; карточка не привязана к записи и не имеет TTL; сбой ConfirmationStore проглатывается (fail-open) | Новое требование **HIT-05** в `.planning/REQUIREMENTS.md`, серьёзность `high`: «Очистка памяти диалога проходит через единую точку `resume_action`: запись создаётся до показа карточки, привязана к ней и имеет TTL, при сбое хранилища очистка не выполняется (fail-closed)». Оформляет план 05-08. В фазе 5 не исправляется (D-10) | Phase 999.3 (бэклог), решение владельца №3 и №6 (как указано в `05-03-PLAN.md`) |

## Ограничения проверки

1. **Что не делалось.** Боевая БД `/opt/assistant-core/data/assistant.db` и файл `/opt/assistant-core/assistant.db` не открывались. `.env` не читался. Живая очистка диалога, нажатие кнопок бота, вызовы `resume_action` на боевых данных и живой Telegram не выполнялись. Проверка идёт чтением кода и тестами на временных БД.
2. **chat-app не участвует в проверке HIT-01.** Из `/opt/chat-app` взят только список файлов исходной папки (`ls`).
3. **Веб-цепочка HIT-02..HIT-04 вне области.** Поллер web-подтверждений и отправка карточек из веб-процесса отложены в бэклог Phase 999.2 (решение владельца 2026-10-18, как указано в `05-03-PLAN.md`). Метод `send_web_hitl_card` (`bot_handler.py:1991`) существует, но фонового поллера в демоне нет.
4. **Решение №3 владельца.** Вердикт HIT-01 `passed` опирается на решение владельца 2026-10-18 №3, которое цитирует `05-03-PLAN.md`. В файлах фазы 5 (`05-CONTEXT.md`) нумерованных решений владельца нет. Номер стоит подтвердить записью в владельческом источнике.
5. **Декоратор.** Буква требования HIT-01 упоминает `@requires_confirmation`. Его нет в коде, вердикт по решению №3 принят без него. Это может потребовать пересмотра текста требования владельцем.
6. **Прогоны.** Набор HITL: 3 прогона, все зелёные. `assistant-shared`: 1 прогон (211 passed). Флейк `test_concurrent_confirmations_isolation` (ISO-04) в проверку не входил.
7. **Нет новых тестов и изменений кода.** D-10 соблюдён. Изменения только в `.planning/phases/05-retro-verifikatsiya-v2-0/`. Git-статус `/opt/assistant-shared` до и после прогона совпал.
8. **Черновик агента Argon использован как входной черновик (agy, Argon acc2, gemini-4-argon-high, только чтение, без pytest).** Каждое file:line, имя, цитата и вердикт сверены с реальным кодом. Исправлено 24 пункта (ниже сгруппированы), добавлено 1. Файлы V2-05 и V2-07 исправлены одновременно:
   - формат таблицы: ID в обратных кавычках, колонки не по D-06 (переделано);
   - строка HIT-05 в таблице вердиктов удалена, gap только в «Gaps»;
   - ссылки `file:///var/tmp/argon-p5...` (чужой клон) заменены путями `/opt/assistant-core` и `/opt/assistant-shared`;
   - вызов обработчика в `resume_action`: `handler(conf)`, а не `handler(conf.target_id, conf.payload)` (`engine.py:60-62`);
   - журнал очистки: `bot_dialog_history.is_archived`, а не `dialog_history.archived` (`db.py:2365-2373`);
   - тесты `test_bot_hitl_parity.py`: защита от неавторизованного на `:132`, не `:52-77`; тест «повторного нажатия :172-206» не существует;
   - тест «слэш-защита /clear» в `test_hitl_telegram_cards.py` не существует;
   - тест «asyncio.gather» в `test_hitl_shared.py` не существует; однократность проверяется в `:113-147`;
   - вызов `cb_dlg_confirm_clear` в parity-тесте на `:295` (не `:302`), диапазон теста `:277-314`;
   - ссылки «05-CONTEXT.md:35-40, 70» как номера решений владельца не подтверждаются файлом;
   - привязка gap: план 05-08 и бэклог 999.3, а не «план 05-04» и «Фаза 6»;
   - регистрация `notion_project_sync` условна (`composition.py:151-153`), а не безусловна (`main.py:675`);
   - `cb_hitl_reject` reject на `:2132` (не `:2133`), миграция `0002` 18 строк (не 19);
   - описания содержимого файлов chat-app и ссылки на аудит v2.0 не проверены и убраны;
   - ПРОБА-строки черновика не выполнялись. Выполнены здесь: HITL 18 passed ×3, shared 211 passed;
   - черновик утверждал, что `.venv` отсутствует. `.venv` есть.
   - V2-07: пути `src/integrations/git_source.py` и `src/integrations/notion_project_sync.py` не существуют (удалены);
   - V2-07: статус GIT-01 «passed» исправлен на «◐ PARTIAL (override)» (`04-VERIFICATION.md:115`);
   - V2-07: «35 passed» не найдено в `04-VERIFICATION.md`; фактически два файла дают 36 passed;
   - V2-07: «Прочитано 33 файла» не проверяемо, удалено;
   - V2-07: ссылки на строки `04-VERIFICATION.md` (85-95, 98-120) заменены на строки таблицы охвата (115-120).
   - Дополнение: в V2-07 добавлено расхождение `status: passed` (frontmatter, `:4`) и `human_needed` (тело, `:86`) в `04-VERIFICATION.md`, которое черновик не упомянул.
