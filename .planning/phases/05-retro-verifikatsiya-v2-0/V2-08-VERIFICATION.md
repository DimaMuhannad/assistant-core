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

## Наблюдения (не gaps)

_(заполняется в Task 2)_

## Gaps

_(заполняется в Task 2)_

## Ограничения проверки

_(заполняется в Task 2 и Task 3)_
