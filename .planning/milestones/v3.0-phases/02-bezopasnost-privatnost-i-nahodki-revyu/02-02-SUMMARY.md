---
phase: 02-bezopasnost-privatnost-i-nahodki-revyu
plan: 02
subsystem: security
tags: [hitl, dialog-memory, telegram-bot, safe-01, intent-router, secretary-dialog]

requires:
  - phase: 01-sobstvennyy-geyt-kachestva-assistant-core
    provides: "собственный гейт качества (scripts/gate.py), тесты HITL-карточки очистки"
provides:
  - "src/brain/dialog_safety.py: CLEAR_DIALOG_TRIGGERS, CLEAR_DIALOG_TEXT_WARNING, is_clear_dialog_request"
  - "EmailBotHandler._warn_clear_requires_slash: предупреждение вместо очистки из текста и голоса"
  - "Единственный путь очистки памяти диалога: /clear или /reset, карточка dlg:confirm_clear / dlg:cancel_clear, кнопка восстановления"
  - "tests/test_clear_dialog_text_guard.py: 45 тестов D-04"
affects: [02-14, 02-15, phase-08]

actuals:
  tokens: 4600
  tasks: 2
  commits: 2
plan_head_before: f186a32a96fa8c22ffbf67ebcdb90ddc0cf0cd51
plan_head_after: 79e2a40c05e58dc591fbfbd38de9008d674358a2

tech-stack:
  added: []
  patterns:
    - "Чистый модуль без импортов в src/brain для общих констант безопасности: его берут и маршрутизатор, и движок, и бот без нарушения контрактов import-linter"
    - "AST-страж в тесте запрещает вызов опасного метода в заданном модуле"

key-files:
  created:
    - src/brain/dialog_safety.py
    - tests/test_clear_dialog_text_guard.py
  modified:
    - src/notifier/bot_handler.py
    - src/brain/secretary_dialog.py
    - src/brain/intent_router.py
    - tests/test_secretary_dialog.py

key-decisions:
  - "SAFE-01 закрыт по D-01..D-04: очистка памяти диалога идёт только через HITL-карточку слэш-команды /clear или /reset; текст, голос, маршрут clear_dialog (в том числе после LLM) и движок диалога лишь предупреждают по-русски и просят ввести /clear вручную"
  - "Слэш-форма, дошедшая до текстового обработчика (например /clear@имя_бота), остаётся на карточке (защитная ветка D-03); у голосового сообщения message.text равен None, поэтому проверка написана как (message.text or '')"
  - "Нормализация триггеров: strip, casefold и отбрасывание хвостовых пробелов и знаков . ! ? … ; пять прежних фраз сохранены, расходящиеся кортежи в движке и маршрутизаторе заменены одним списком"

patterns-established:
  - "Слэш-команда и обычная речь разведены: деструктивное действие вызывается только явной командой с карточкой подтверждения"

requirements-completed: [SAFE-01]

coverage:
  - id: D1
    description: "Текстовая фраза очистки (очисти диалог, забудь контекст, сброс, с регистром и пунктуацией) через handle_user_text не меняет bot_dialog_history и даёт предупреждение с /clear без карточки"
    requirement: SAFE-01
    verification:
      - kind: integration
        ref: "tests/test_clear_dialog_text_guard.py::test_text_clear_phrase_warns_and_keeps_history (4 фразы), ::test_llm_clear_dialog_route_warns_and_keeps_history"
        status: pass
    human_judgment: false
  - id: D2
    description: "Голосовое сообщение с фразой очистки и прямой вызов SecretaryDialogEngine.answer_user_message по всем пяти триггерам и четырём формам возврата не меняют историю"
    requirement: SAFE-01
    verification:
      - kind: integration
        ref: "tests/test_clear_dialog_text_guard.py::test_voice_clear_phrase_warns_and_keeps_history, ::test_engine_never_clears_history (5 фраз x 4 формы)"
        status: pass
      - kind: unit
        ref: "tests/test_secretary_dialog.py::test_secretary_dialog_clear_command (после /clear история сохранена, len == 1)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Слэш-путь цел: /clear показывает карточку с dlg:confirm_clear и dlg:cancel_clear, история без подтверждения на месте, при пустой истории ответ «контекст уже пуст»; /clear@имя_бота в текстовом обработчике остаётся на карточке"
    requirement: SAFE-01
    verification:
      - kind: integration
        ref: "tests/test_clear_dialog_text_guard.py::test_slash_form_in_text_handler_keeps_hitl_card, ::test_slash_form_with_empty_history_says_context_is_empty, ::test_slash_command_card_shows_without_confirmation_history_stays; tests/test_hitl_safety_guardrails.py без правок"
        status: pass
    human_judgment: false
  - id: D4
    description: "Страж и достижимость: в secretary_dialog.py нет обращения к clear_dialog_history (AST), обработчики clear, текста и голоса зарегистрированы в router; неавторизованный пользователь ответа не получает"
    requirement: SAFE-01
    verification:
      - kind: unit
        ref: "tests/test_clear_dialog_text_guard.py::test_secretary_dialog_has_no_clear_dialog_history_call, ::test_clear_and_text_voice_handlers_are_registered, ::test_unauthorized_user_gets_no_reply"
        status: pass
      - kind: other
        ref: "git grep -n clear_dialog_history -- src/brain/secretary_dialog.py: пусто"
        status: pass
    human_judgment: false
  - id: D5
    description: "Общий список триггеров и контракты архитектуры: маршрутизатор распознаёт «Очисти диалог!» как clear_dialog (fast-rule), import-linter не нарушен, полный гейт зелёный"
    requirement: SAFE-01
    verification:
      - kind: integration
        ref: "tests/test_clear_dialog_text_guard.py::test_router_recognises_clear_phrase_with_punctuation_and_case; tests/test_architecture_contract.py (5 passed); python3 scripts/gate.py: ИТОГ ЗЕЛЁНЫЙ (837 + 145 тестов)"
        status: pass
    human_judgment: false

duration: 40min
completed: 2026-10-10
status: complete
---

# Phase 2 Plan 02: Очистка памяти диалога только через /clear Summary

**Решение SAFE-01: фраза «очисти диалог» больше не стирает память без защиты; единственный путь очистки это слэш-команда /clear или /reset с HITL-карточкой, а текст, голос, LLM-маршрут и движок диалога только предупреждают по-русски и просят ввести /clear вручную.**

## Решение SAFE-01 (D-01..D-04)

Исследование показало, что обычный текст «очисти диалог» уже уходил на HITL-карточку, но в `SecretaryDialogEngine` оставался прямой вызов `clear_dialog_history`, а карточка из болтовни и голоса создавала впечатление, что сброс допустим из речи. Теперь `src/brain/dialog_safety.py` держит единый список триггеров и русский текст предупреждения; ветки `clear_dialog` в `handle_user_text` и `handle_user_voice` вызывают `_warn_clear_requires_slash` (с проверкой `_is_authorized` первой, без `reply_markup`, без обращения к БД). Движок диалога возвращает то же предупреждение во всех формах возврата. Слэш-путь (`Command("clear", "reset")`, колбэки `dlg:*`, восстановление) не менялся. Маршрут `clear_dialog` в `FastIntentRouter` и значение в `VALID_ACTIONS` сохранены.

## Performance

- **Duration:** около 40 мин (основное время ушло на холодный запуск pytest и полный гейт)
- **Completed:** 2026-10-10
- **Tasks:** 2 (tracer + auto/tdd)
- **Files:** 6 (2 новых, 4 изменённых)

## Accomplishments

- Новый чистый модуль `src/brain/dialog_safety.py`: `CLEAR_DIALOG_TRIGGERS` (пять значений), `CLEAR_DIALOG_TEXT_WARNING`, `is_clear_dialog_request` (strip, casefold, хвостовая пунктуация).
- `bot_handler.py`: метод `_warn_clear_requires_slash`; текст и голос используют его; в текстовой ветке слэш-форма (`(message.text or "").lstrip().startswith("/")`) идёт на карточку.
- `secretary_dialog.py` и `intent_router.py` используют `is_clear_dialog_request`; прежние кортежи удалены, вызова `clear_dialog_history` в движке нет.
- Ночной сброс `archive_dialog_history` (04:00) не менялся: `git diff f186a32 HEAD -- src/main.py src/storage/db.py` пуст (D-05, уведомление после сброса и предупреждение при онбординге отложены в Phase 8).

## Тесты

Новый файл `tests/test_clear_dialog_text_guard.py` (45 тестов, ~260 строк):

- текст: четыре фразы (включая «Очисти диалог!») и LLM-маршрут без карточки, история 4 реплики не меняется;
- голос: распознанная фраза «сброс» при подменённых `get_file`, `download_file`, `transcribe`;
- движок: 5 триггеров x 4 формы возврата (`return_files`, `return_proposal`), история не меняется;
- маршрутизатор: «Очисти диалог!» даёт `clear_dialog` у `fast-rule`;
- слэш: `/clear@secretary_bot` в текстовом обработчике показывает карточку с `dlg:confirm_clear` и `dlg:cancel_clear`, при пустой истории «контекст уже пуст», `/clear` без подтверждения оставляет историю;
- страж: AST-разбор `secretary_dialog.py` не находит обращения `clear_dialog_history`; регистрация обработчиков clear, текста, голоса; неавторизованный пользователь не получает ответа; `is_clear_dialog_request` на триггерах и «чужом» тексте.

Переписан `tests/test_secretary_dialog.py::test_secretary_dialog_clear_command`: после `/clear` история сохранена (`len(hist) == 1`), ответ содержит «/clear».

## Проверки

| Проверка | Результат |
|---|---|
| связанные наборы (guard, secretary_dialog, hitl_guardrails, bot_hitl_parity, fast_intent_router, bot_menu, architecture_contract, test_help_handler_does_not_touch_db) | 79 passed |
| `python3 scripts/gate.py` | ИТОГ ЗЕЛЁНЫЙ: assistant-core 837 тестов, assistant-shared 145, SHA-256 боевой БД до и после совпали, import-linter, shield |
| `git grep -n clear_dialog_history -- src/brain/secretary_dialog.py` | пусто |

## Task Commits

1. **Task 1 (tracer): текст «очисти диалог» даёт предупреждение вместо очистки** - `523736b` (feat)
2. **Task 2: голос, движок и маршрутизатор не очищают память диалога** - `79e2a40` (feat)

**Plan metadata:** коммит docs(02-02) (SUMMARY, STATE, ROADMAP, REQUIREMENTS).

## Decisions Made

См. frontmatter. Главное: очистка только по явной слэш-команде с карточкой (D-01..D-03), нормализация регистра и пунктуации только для детерминированного списка пяти фраз; произвольные формулировки покрывает LLM-маршрут `clear_dialog`, который тоже даёт лишь предупреждение.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Устаревший ledger коммитов плана**
- **Found during:** Task 1 (запись базы коммитов)
- **Issue:** файл `.git/gsd-plan-head-before-02-02` остался от прежнего этапа (v2.0) и указывал на `bc5b2c9`, измерение `commits:` дало бы неверное число.
- **Fix:** файл перезаписан реальной базой плана `f186a32` (родитель первого коммита плана); `commits: 2` измерен командой `git rev-list --count`.
- **Files modified:** `.git/gsd-plan-head-before-02-02` (вне истории git)

### Процессные заметки

- Тест LLM-маршрута и слэш-формы подменяют `handler.intent_router.route` (AsyncMock с `IntentResult(clear_dialog)`): реальный маршрутизатор без ключа не вернёт `clear_dialog` для `/clear@имя_бота`, а в продакшене такую форму перехватывает фильтр `Command("clear")` aiogram до текстового обработчика; ветка в `handle_user_text` является защитной (D-03).
- Вариант «Очисти диалог!» добавлен в параметризацию текстового теста при Task 2, а не Task 1: маршрутизатор получил нормализацию только в Task 2 (порядок плана сохранён).
- `tdd="true"` у Task 2 не оформлялся отдельными RED/GREEN-коммитами: план требует один коммит на задачу; поведение закреплено тестами, прошедшими вместе с кодом.
- `actuals.tokens` оценено как chars/4 по диффу плана (около 18,5 тыс. символов).

## Known Stubs

None.

## Threat Flags

None. Новых сетевых точек, путей аутентификации и обращений к файлам нет; поверхность сузилась (убран путь очистки из текста, голоса и движка). Модель угроз плана: T-02-04 закрыт тестами всех путей и AST-стражем, T-02-06 закрыт тестом неавторизованного пользователя, T-02-05 принят (alias-защита `protected` уже в `bot_handler`), T-02-SC не затронут (пакеты не ставились).

## Issues Encountered

Холодный запуск pytest и обработчика бота занимает десятки секунд; объединённый запуск четырёх наборов превысил лимит одной команды, поэтому тяжёлые наборы запускались порознь и в фоне. Сбоев тестов не было.

## Next Phase Readiness

Фаза рантаймовая: достижимость из живого бота доказывается в планах 02-14 (регистрация обработчиков) и 02-15 (живое сообщение боту). Рестарт `assistant-worker.service` не выполнялся; изменения вступят в силу после рестарта по явному разрешению владельца.

## Self-Check: PASSED

- `src/brain/dialog_safety.py`, `tests/test_clear_dialog_text_guard.py`: найдены
- коммиты `523736b` и `79e2a40` являются предками HEAD
