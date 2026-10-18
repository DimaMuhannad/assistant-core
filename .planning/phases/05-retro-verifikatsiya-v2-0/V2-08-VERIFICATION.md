---
phase: 05-retro-verifikatsiya-v2-0
v2_phase: "08"
v2_source: /opt/chat-app/.planning/milestones/v2.0-phases/08-ispolnitelnyy-kontur-tool-calling
verified: 2026-10-18T21:04:56Z
status: in_progress
score: "0 из 4 требований вынесены"
requirements: [ACT-01, ACT-02, ACT-03, ACT-04]
gaps: []
---

# V2-08: Исполнительный инструментальный контур (Tool Calling)

## Источник (только чтение)

- Путь: `/opt/chat-app/.planning/milestones/v2.0-phases/08-ispolnitelnyy-kontur-tool-calling`
- Файлы папки (11): `08-01-PLAN.md`, `08-01-SUMMARY.md`, `08-02-PLAN.md`, `08-02-SUMMARY.md`, `08-03-PLAN.md`, `08-03-SUMMARY.md`, `08-04-PLAN.md`, `08-04-SUMMARY.md`, `08-CONTEXT.md`, `08-DISCUSSION-LOG.md`, `08-RESEARCH.md`.
- `VERIFICATION.md` в исходной папке отсутствует (в v2.0 не создавался).

## Вердикты

| Требование | Статус | Точка входа в рантайме (file:line) | Тест или команда проверки | Метка |
|------------|--------|------------------------------------|---------------------------|-------|
| ACT-04 | passed | `src/notifier/bot_handler.py:1471` (`handle_user_text` `src/notifier/bot_handler.py:1311`, регистрация `src/notifier/bot_handler.py:432`) → `src/brain/intent_router.py:121` (`FastIntentRouter.route`; `VALID_ACTIONS` `src/brain/intent_router.py:35`) | `tests/test_fast_intent_router.py` (10 passed, процесс не завершается, см. Наблюдения 5); `tests/test_tool_calling_flow.py` (6 passed, код 0) | трасса+e2e |
| ACT-03 | gap | `src/notifier/bot_handler.py:403-409` (регистрация `act:cal|rem|drf:conf|rej`) → `src/notifier/bot_handler.py:2358` (`_handle_hitl_action_callback`) → `src/notifier/bot_handler.py:2401` (`resume_action`); обход: `src/notifier/bot_handler.py:2499-2551` (`act:cal:retry` вызывает `create_event_from_dict`, `src/calendar/client.py:185`, без `resume_action`) | `tests/test_hitl_telegram_cards.py`, `tests/test_tool_calling_e2e.py`, `tests/test_tool_calling_flow.py`, `tests/test_secretary_tools.py`, `tests/test_prompt_snapshot.py` (44 passed, код 0) | трасса+e2e |
| ACT-01 | passed | `src/notifier/bot_handler.py:1311` (`handle_user_text`) → `src/notifier/bot_handler.py:1472` → `src/brain/secretary_dialog.py:595` (`answer_user_message`), `src/brain/secretary_dialog.py:816-821` (`_build_action_proposal`, `src/brain/secretary_dialog.py:704`) → `src/notifier/bot_handler.py:2599-2616` (карточка) → `src/notifier/bot_handler.py:2401` (`resume_action`) → `src/notifier/bot_handler.py:228-295` (обработчики) → бэкенд: `src/calendar/client.py:149`, `src/storage/db.py:1566`, `src/storage/db.py:1175` | `tests/test_tool_calling_e2e.py` (3 passed), `tests/test_secretary_tools.py` (7), `tests/test_hitl_telegram_cards.py` (9): в составе прогона 44 passed, код 0 | трасса+e2e |
| ACT-02 | passed | `src/brain/secretary_dialog.py:702` (`render_prompt("secretary")`) → `src/brain/secretary_dialog.py:733` (`system_instruction`) → `config/prompts/secretary_default.jinja2:27-31` | `tests/test_prompt_snapshot.py` (19 passed), `tests/test_secretary_tools.py` (7 passed): в составе прогона 44 passed, код 0 | трасса |

## Доказательства

### ACT-04

**Требование (REQUIREMENTS.md:61):** интенты `calendar_schedule`, `create_reminder`, `draft_reply` в `FastIntentRouter` с извлечением сущностей.

**Трасса по звеньям:**
- (а) Регистрация и вход. `src/main.py:687` создаёт `EmailBotHandler`; `src/main.py:699` подключает `bot_handler.router` к диспетчеру; `src/main.py:934` запускает `dp.start_polling`. В `EmailBotHandler.__init__` `src/notifier/bot_handler.py:182` создаётся `self.router`, `src/notifier/bot_handler.py:193` вызывает `_register_handlers`. В `_register_handlers` фильтр приватного чата `src/notifier/bot_handler.py:339`; `src/notifier/bot_handler.py:432` регистрирует `self.router.message(F.text)(self.handle_user_text)`.
- (б) Маршрутизатор. `src/notifier/bot_handler.py:179` создаёт `FastIntentRouter`. `handle_user_text` `src/notifier/bot_handler.py:1311`, авторизация `src/notifier/bot_handler.py:1317`, вызов `route` `src/notifier/bot_handler.py:1416` заполняет `route_res`. `src/brain/intent_router.py:121` (`route`), `src/brain/intent_router.py:85-91` (`IntentResult`), аудит `src/brain/intent_router.py:428`.
- (в) Множество `VALID_ACTIONS` `src/brain/intent_router.py:35-47` содержит `calendar_schedule` (строка 45), `create_reminder` (строка 46), `draft_reply` (строка 47). Детерминированные ветки: `create_reminder` на `src/brain/intent_router.py:224` (префикс) и `:263` (фразы); `calendar_schedule` на `src/brain/intent_router.py:235` (префикс) и `:247` (фразы); `draft_reply` на `src/brain/intent_router.py:275`. LLM-ветка: `extract_json_object` `src/brain/intent_router.py:385`, `IntentResult` `src/brain/intent_router.py:395-401`. Промпт `config/prompts/intent_router_default.jinja2:31-46` (пункты 10–12 и формат JSON).
- (г) Диспетчеризация. `src/notifier/bot_handler.py:1471-1473`: `elif route_res.action in ("calendar_schedule", "create_reminder", "draft_reply")` вызывает `self._handle_secretary_dialog(message, user_msg, intent=route_res.action)`.
- (г, сущности) `FastIntentRouter` сущности не извлекает: `IntentResult` несёт только `action`, `confidence`, `reason`, `model`, `latency_ms`. Извлечение выполняет `SecretaryDialogEngine` через объявления инструментов: `src/brain/tools_schema.py:21-36` (`create_calendar_event`: title, date, start_time, end_time, description, location), `src/brain/tools_schema.py:38-51` (`create_reminder`: text, due_date, target, category), `src/brain/tools_schema.py:53-64` (`draft_email_reply`: email_id, reply_text).
- (д) Действие вне `VALID_ACTIONS`: `src/brain/intent_router.py:389-391` переводит его в `"secretary"`; покрыто `tests/test_fast_intent_router.py:79` (`test_router_invalid_action_defaults_to_secretary`).

**Команды и результаты (исполнитель, Claude; agy не запускался):**
- `cd /opt/assistant-core && PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider tests/test_fast_intent_router.py -q`: строка итога «10 passed in 9.80s» (повторные прогоны: 9.14 s и 8.77 s). Процесс pytest после итога не завершается: прогон прерван по таймауту, код возврата 124 (четыре прогона из четырёх). Дамп потоков показал три незакрытых не-демонических потока `aiosqlite` (`_connection_worker_thread`). Бисекция по `-k`: группы `test_router_*` (7 тестов) завершаются с кодом 0, группа `test_bot_handler_dispatch_*` (3 теста) не завершается.
- `cd /opt/assistant-core && PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider tests/test_tool_calling_flow.py -q`: код возврата 0, «6 passed in 29.56s».

**Метка:** трасса+e2e. E2e-часть: `tests/test_tool_calling_flow.py:81` (`test_bot_handler_routes_planning_intents_to_secretary_dialog`) вызывает реальный `route()` без мока и подаёт три фразы в `handle_user_text` на временной БД; диалог секретаря заглушен. Фразы дают `calendar_schedule`, `create_reminder`, `draft_reply`.

**Вывод по ACT-04:** звенья (а)–(д) подтверждены чтением кода с номерами строк; поведение интентов подтверждено 10 зелёными тестами и сквозным прогоном через обработчик. Вердикт: passed. Дефект выхода процесса pytest (код 124 при 10 passed) не относится к поведению интентов; он записан в «Наблюдения (не gaps)», п. 5, потому что блокирует гейт.

### ACT-03

**Требование (REQUIREMENTS.md:60):** перед созданием внешних событий и изменением критичных данных — HITL-карточка с инлайн-кнопками; действие только после нажатия.

**Трасса по звеньям:**
- (1) До нажатия бэкенд не вызывается. В `answer_user_message` ветки `create_calendar_event`, `create_reminder`, `draft_email_reply` только формируют `ActionProposal` через `_build_action_proposal` (`src/brain/secretary_dialog.py:704-728`, вызовы `:816-821`). Затем `src/notifier/bot_handler.py:2601-2607` создаёт `PendingConfirmation` (`store.create_confirmation`), `src/notifier/bot_handler.py:2608` формирует карточку (`format_hitl_proposal_card`), `src/notifier/bot_handler.py:2609` строит клавиатуру (`build_hitl_action_keyboard`, `src/notifier/telegram.py:111-150`).
- (2) Регистрация callbacks. `src/notifier/bot_handler.py:403-409` регистрирует все семь префиксов: `act:cal:conf`, `act:cal:rej`, `act:cal:retry`, `act:rem:conf`, `act:rem:rej`, `act:drf:conf`, `act:drf:rej`.
- (3) Подтверждение. `cb_act_*_confirm` вызывает `_handle_hitl_action_callback` (`src/notifier/bot_handler.py:2358`). Авторизация `src/notifier/bot_handler.py:2360-2362`. Проверка статуса (истёк, не PENDING) `src/notifier/bot_handler.py:2381-2397`. Исполнение `src/notifier/bot_handler.py:2401` (`resume_action`) → `/opt/assistant-shared/assistant_shared/hitl/engine.py:28-62` → `ConfirmationStore.confirm_action`, атомарный `UPDATE ... WHERE id = ? AND status = 'pending'` (`/opt/assistant-shared/assistant_shared/hitl/store.py:124-134`) → зарегистрированный обработчик (`src/notifier/bot_handler.py:297-299`).
- (4) Отклонение. `src/notifier/bot_handler.py:2476-2489` вызывает `store.reject_action` (`/opt/assistant-shared/assistant_shared/hitl/store.py:141-164`); `resume_action` и бэкенд не вызываются.
- (5) Обход, нарушающий проверку. `cb_act_calendar_retry` (`src/notifier/bot_handler.py:2499-2551`): авторизация `:2501-2503`; запись берётся по `sync_id` через `db.get_pending_calendar_sync` (`src/storage/db.py:381`, SQL `WHERE id = ?`, без фильтра по статусу; вызов `src/notifier/bot_handler.py:2516`); запись в Google Calendar через `create_event_from_dict` (`src/calendar/client.py:185`); статус `active` через `update_calendar_sync_status` (`src/storage/db.py:393`). В этом пути нет `resume_action`, нет проверки `status == pending_sync` и нет обновления `ConfirmationStore`. Утверждение, что `src/notifier/bot_handler.py:2401` — «единственная точка запуска», неверно.

**Граничные случаи:**
- Чужой пользователь: `_is_authorized` (`src/notifier/bot_handler.py:307-311`, fail-closed при `allowed_user_id is None`) в подтверждении и в retry. Тест `test_cb_act_unauthorized_user_blocked` (`tests/test_hitl_telegram_cards.py:515`).
- Повторное нажатие подтверждения: `test_cb_act_deduplication_and_protection` (`tests/test_hitl_telegram_cards.py:448`); защита атомарным UPDATE и проверкой статуса. Для retry такой защиты нет (см. п. 5).
- Истёкшая запись: `test_cb_act_expired_action_blocked` (`tests/test_hitl_telegram_cards.py:557`).
- Отклонение ничего не исполняет: `test_cb_act_calendar_confirm_and_reject` (`:189`), `test_cb_act_reminder_confirm_and_reject` (`:277`), `test_cb_act_draft_confirm_and_reject` (`:351`).
- Retry покрыт тестами `tests/test_tool_calling_flow.py:233` и `tests/test_tool_calling_e2e.py:185`, но они проверяют успешный повтор после сбоя. Повтор после успеха и гонку двух нажатий они не проверяют.

**Команда проверки:** `cd /opt/assistant-core && PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider tests/test_hitl_telegram_cards.py tests/test_tool_calling_e2e.py tests/test_tool_calling_flow.py tests/test_secretary_tools.py tests/test_prompt_snapshot.py -q`: код возврата 0, «44 passed in 16.71s» (по файлам 9, 3, 6, 7, 19). Прогон завершился штатно.

**Метка:** трасса+e2e. E2e-часть: `tests/test_tool_calling_e2e.py:41` (сообщение в `handle_user_text` → карточка → `cb_act_reminder_confirm` → запись в `reminders`), `tests/test_hitl_telegram_cards.py:189` (callbacks на временной БД с заглушкой календаря).

**Вывод по ACT-03: gap.** Основной путь (карточка до нажатия, регистрация callbacks, подтверждение и отклонение через `resume_action`, авторизация, идемпотентность, истечение срока) подтверждён. Требование плана «исполнение только через `resume_action`» нарушено путём `act:cal:retry`: повторная запись во внешний календарь идёт вне HITL-движка, без проверки статуса записи и без следа в `ConfirmationStore`. По коду повтор после успешной синхронизации или двойное нажатие до смены статуса создаёт второе событие. Живым прогоном это не проверено (D-02: записи во внешние системы запрещены), вывод опирается на чтение `src/storage/db.py:381`, `src/notifier/bot_handler.py:2516-2519` и `src/notifier/bot_handler.py:2551`.

---

### ACT-01

**Требование (REQUIREMENTS.md:58, с учётом решения владельца 2026-10-18 №2 о HITL-first):** вызов `create_calendar_event`, `create_reminder`, `draft_email_reply` превращается в `ActionProposal` и карточку подтверждения, бэкенд вызывается обработчиком после подтверждения; `search_emails` возвращает `function_response` модели.

**Трасса по звеньям (сообщение → бэкенд):**
1. Вход: `src/main.py:687-699` (`EmailBotHandler`, `dp.include_router`) → `src/notifier/bot_handler.py:432` → `handle_user_text` `src/notifier/bot_handler.py:1311`.
2. Маршрутизация: `src/notifier/bot_handler.py:1416` (`intent_router.route`) → `src/brain/intent_router.py:121` → `src/notifier/bot_handler.py:1471-1472`.
3. LLM с инструментами: `src/notifier/bot_handler.py:2576-2582` (`answer_user_message(return_files=True, return_proposal=True, intent=...)`) → `src/brain/secretary_dialog.py:595`; `system_instruction` `src/brain/secretary_dialog.py:702`; `tools=SECRETARY_TOOLS` `src/brain/secretary_dialog.py:735`; объявления `src/brain/tools_schema.py:21-87`.
4. Ответ модели. `search_emails`: `src/brain/secretary_dialog.py:758-790` (поиск, маскировка NDA-писем, `types.Part.from_function_response` на `:787-790`, повторный вызов модели). `create_*`: `_build_action_proposal` на `:816-821`, бэкенд не вызывается.
5. Карточка: `src/notifier/bot_handler.py:2599-2616`; текст `src/notifier/telegram.py:191`; клавиатура `src/notifier/telegram.py:111`.
6. Подтверждение и бэкенд: `act:*:conf` → `src/notifier/bot_handler.py:2401` (`resume_action`) → обработчики `src/notifier/bot_handler.py:228` (календарь: `Lesson`, затем `calendar_client.create_event`, `src/calendar/client.py:149`), `:272` (напоминание: `db.create_reminder`, `src/storage/db.py:1566`, `INSERT` на `:1580`), `:287` (черновик: `db.create_email_draft`, `src/storage/db.py:1175`, `INSERT` на `:1181`).
7. Сбой календаря после подтверждения: `src/notifier/bot_handler.py:264, 269` сохраняют запись `pending_sync` (`src/storage/db.py:326`) и дают кнопку повтора. Повтор идёт вне `resume_action`, см. ACT-03 п. 5. Покрыто `tests/test_tool_calling_flow.py:233` и `tests/test_tool_calling_e2e.py:185`.
8. Граничные случаи: повтор нажатия подтверждения (`tests/test_hitl_telegram_cards.py:448`), истёкшая запись (`:557`), чужой пользователь (`:515`).

**Команда проверки:** та же, что для ACT-03 (44 passed, код 0).

**Расхождение с буквальным текстом (принято владельцем):** для `create_*` `function_response` модели не формируется; вместо `tool_result` пользователь получает карточку. `function_response` возвращается модели только для `search_emails` (`src/brain/secretary_dialog.py:787-788`). См. Наблюдения, п. 1.

**Метка:** трасса+e2e (`tests/test_tool_calling_e2e.py:41`, `:185`).

**Вывод по ACT-01: passed** по HITL-first прочтению. Обрыв на звеньях 1–6 не найден. Звено 7 (повтор) работает, но вне HITL-движка, это зафиксировано как gap ACT-03.

---

### ACT-02

**Требование (REQUIREMENTS.md:59, с учётом решения владельца 2026-10-18 №2):** промпт секретаря запрещает утверждать о выполнении без вызова инструмента и формирования карточки подтверждения; при нехватке данных задаётся уточняющий вопрос.

**Трасса:** `src/brain/secretary_dialog.py:702` (`render_prompt("secretary")`) → `src/brain/secretary_dialog.py:733` (`system_instruction` в `GenerateContentConfig`) → `src/brain/secretary_dialog.py:742-746` (`generate_content`).

**Цитата правила** (`config/prompts/secretary_default.jinja2`):
- строка 27: «СТРОЖАЙШИЙ ЗАПРЕТ ГАЛЛЮЦИНАЦИЙ И ПРАВИЛО ИСПОЛНИТЕЛЬНОГО КОНТУРА (D-05, ACT-02)»;
- строка 28: «КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО утверждать ... что событие внесено в календарь, создано напоминание или подготовлен черновик, если в текущем диалоге не был вызван соответствующий инструмент и не сформирована карточка подтверждения»;
- строка 29: шаблон ответа «Я подготовил карточку ... Пожалуйста, подтвердите действие кнопкой ниже»;
- строка 30: запрет придумывать время; уточняющий вопрос «В какое время запланировать встречу?»;
- строка 31: для данных из письма сначала `search_emails`.

**Закрепление снимком и тестами:** `tests/fixtures/prompts_snapshot/secretary.txt:27-31` совпадает со строками шаблона (проверено построчно). `tests/test_prompt_snapshot.py:134-146` (`test_secretary_prompt_matches_snapshot`) сравнивает побайтно перехваченный `system_instruction` со снимком; `tests/test_prompt_snapshot.py:287` (`test_default_template_renders_to_snapshot`). `tests/test_secretary_tools.py:242` (`test_antihallucination_prompt_content`), `:255` (`test_missing_time_clarification_no_action_proposal`); `tests/test_tool_calling_e2e.py:271` и `tests/test_tool_calling_flow.py:204` (при уточнении `ActionProposal` не создаётся).

**Команда проверки:** та же, что для ACT-03 (44 passed, код 0; в ней 19 тестов `test_prompt_snapshot.py` и 7 тестов `test_secretary_tools.py`).

**Метка:** трасса. Пометка «доказано трассой, без e2e-теста» (D-04): поведение LLM недетерминировано (допущение A5 из `05-RESEARCH.md`), живой вызов Gemini не выполнялся (D-02). Проверено наличие правила в промпте и его передача в модель, но не то, что модель ему следует.

**Вывод по ACT-02: passed** по принятой HITL-first формулировке.

## Наблюдения (не gaps)

1. **ACT-01 и ACT-02: карточка подтверждения вместо `function_response` и `tool_result` (решение владельца 2026-10-18 №2).** Буквальный текст REQUIREMENTS.md:58–59 расходится с реализацией. Для `create_calendar_event`, `create_reminder`, `draft_email_reply` `function_response` не формируется, карточка подтверждения возвращается вместо `tool_result` (`src/notifier/bot_handler.py:2599-2616`). Владелец принял HITL-first как спецификацию. Формулировки в REQUIREMENTS.md обновит план 05-08, ACT-05 не создаётся.
2. **ACT-04: извлечение сущностей вне `FastIntentRouter`.** `IntentResult` не содержит полей сущностей (`src/brain/intent_router.py:85-91`). Сущности извлекает `SecretaryDialogEngine` через `SECRETARY_TOOLS` (`src/brain/tools_schema.py:21-64`). REQUIREMENTS.md:61 говорит «в `FastIntentRouter` с извлечением сущностей». По сквозной цепочке требование выполнено; формулировку стоит уточнить (кандидат для 05-08).
3. **ACT-03: литерал `persona_id="popov"`** в `src/notifier/bot_handler.py:2602` вместо `current_persona().id` (как в `src/notifier/bot_handler.py:1941`). Статус не меняет, но нарушает правило CLAUDE.md о персоне из конфигурации и при смене персоны запишет подтверждения с чужим `persona_id`.
4. **ACT-03: мёртвая ветка `act:gen:conf` / `act:gen:rej`** в `src/notifier/telegram.py:140-148` для неизвестного `action_type`. Обработчиков для этих префиксов в `src/notifier/bot_handler.py` нет. С текущими тремя инструментами ветка недостижима.
5. **Дефект инфраструктуры тестов (не требование ACT): процесс pytest не завершается после итога.** Три теста `tests/test_fast_intent_router.py::test_bot_handler_dispatch_to_timesheet`, `_to_secretary`, `_to_methodist` создают `EmailBotHandler` без `bot` и `notifier`. После них остаются три незакрытых не-демонических потока `aiosqlite`. Дамп потоков получен на `pytest_unconfigure` плагином вне репозитория. Бисекция: остальные 7 тестов файла завершаются с кодом 0. Точная строка утечки не локализована. Итог «10 passed» верен, код возврата 124. `scripts/gate.py` ограничивает pytest таймаутом (`scripts/gate.py:94-107`, `:268-269`), по коду такой прогон даёт КРАСНЫЙ. Гейт в этой фазе не запускался: он хеширует боевую БД. Решение владельца: закрыть соединения в этих тестах отдельной задачей `/gsd-quick` или записать в бэклог. Код и тесты не менялись (D-10).
6. **ACT-02: недетерминированность LLM** (допущение A5). Вердикт опирается на текст промпта и байтовый снимок.

## Gaps

| Требование | Класс по D-09 | Предложение оформления | Привязка |
|------------|---------------|------------------------|----------|
| ACT-03 | HITL и целостность данных | Новое требование HIT-06 (предложено; HIT-05 уже назначен под обход очистки диалога в плане 05-08): «повтор синхронизации календаря проходит через HITL-движок (`resume_action` и `ConfirmationStore`) и выполняет внешнюю запись не более одного раза, только для записи в статусе `pending_sync`». Исправление в фазе 5 не входит (D-10). | Номер фазы 999.N назначает план 05-08 по правилу его must_haves (после HIT-05 → 999.3 и ISO-05 → 999.4) |

Наблюдение 5 (дефект инфраструктуры) не является gap требования. Его класс по D-09 — целостность гейта, решение за владельцем: `/gsd-quick` до закрытия фазы 5 или запись в бэклог 999.N.

## Ограничения проверки

_(заполняется в Task 3)_
