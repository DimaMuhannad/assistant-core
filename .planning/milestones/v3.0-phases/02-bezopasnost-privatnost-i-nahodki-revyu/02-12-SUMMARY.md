---
phase: 02-bezopasnost-privatnost-i-nahodki-revyu
plan: 12
subsystem: privacy
tags: [privacy, email, priv-01, d-15, d-16, d-19, daemon-runtime]
status: complete

requires:
  - phase: 02-bezopasnost-privatnost-i-nahodki-revyu
    provides: "02-11: email_ai_notice, EMAIL_AI_NOTICE_FLAG_KEY, текст предупреждения в данных персоны"
provides:
  - "Database.has_notice_shown(key) и Database.mark_notice_shown(key): флаг в существующей таблице daily_primed_context, ключи только с префиксом notice:"
  - "_announce_email_ai_notice(db, notifier, results) в src/main.py: запись в журнал и одно сообщение владельцу при первом успешном цикле почты"
  - "scripts/auth_google.py: _print_privacy_notice() в stderr до проверки credentials.json"
  - "Закомментированный блок почты с русским предупреждением в .env.example"
affects: [02-15]

actuals:
  tokens: 26000
  tasks: 2
  commits: 2
plan_head_before: e26b7c4259d7621e465d8ee36a0cadef8d43d99e
plan_head_after: f143d87cd3c00aed544f1a216e1bc62b74300995

key-files:
  created: []
  modified:
    - src/storage/db.py
    - src/main.py
    - src/persona/notices.py
    - scripts/auth_google.py
    - .env.example
    - tests/test_privacy_notice.py

key-decisions:
  - "Пустой результат send_message (список без id: Telegram не настроен или сообщение заблокировано) считается неудачей: флаг не ставится, предупреждение повторится в следующем цикле"
  - "Ключ «notice:» без суффикса тоже отвергается (ValueError), чтобы флаг не был пустым именем"
  - "Миграция не создавалась: флаг живёт в daily_primed_context (summary_text='shown', payload_json='{}'); читателей, перечисляющих все строки этой таблицы, в src нет"

requirements-completed: [PRIV-01]
---

# Phase 2 Plan 12: предупреждение о приватности почты при подключении Summary

**Предупреждение PRIV-01 показывается один раз, когда сборщик почты реально начал работать (журнал + одно сообщение владельцу), а также при запуске `auth_google.py` и в подсказках `.env.example`; флаг «показано» живёт в существующей таблице, без миграции.**

## Что сделано

- **Методы БД** (`src/storage/db.py`, рядом с `save_primed_context`):
  - `async def has_notice_shown(self, key: str) -> bool`
  - `async def mark_notice_shown(self, key: str) -> None`
  - Оба отвергают ключ без префикса `notice:` (`ValueError`, T-02-43). Запись идёт через `save_primed_context(key, "shown", "{}")`.
- **Критерий «ящик подключён»** (`_has_connected_mailbox` в `src/main.py`): среди пар результата `sync_all_accounts` есть словарь, ключ которого не входит в `_NON_ACCOUNT_RESULT_KEYS` (`reconciliation`, `aging`, `db_totals`, `active_actionable_count`), у которого `status` не начинается с «skipped» и нет ключа `error`.
- **Показ** (`_announce_email_ai_notice`): нет подключённых ящиков или флаг уже стоит - ничего; иначе запись в журнал `logger.info("PRIV-01: ...")`, `notifier.send_message("🔒 **Приватность почты**\n\n" + text)` (без `chat_id`, то есть владельцу), и только при непустом результате отправки `mark_notice_shown`. Вызов в `run_email_collector_cycle` стоит сразу после строки итога сбора, в собственном `try/except` с `logger.warning("Не удалось показать предупреждение PRIV-01: %s", e)`.
- **`email_ai_notice(persona=None)`**: `None` даёт нейтральный запасной текст.
- **`scripts/auth_google.py`**: `_print_privacy_notice()` - первая строка `main()`, текст персоны, при любой ошибке загрузки запасной; вывод в stderr. Поток OAuth не менялся.
- **`.env.example`**: закомментированный блок «Почта (сбор писем)» с русским предупреждением и строками `# MAILRU_EMAIL=`, `# MAILRU_PASSWORD=`, `# GMAIL_EMAIL=`, `# GMAIL_PASSWORD=` без значений.

## Сценарии тестов (tests/test_privacy_notice.py, временная БД, notifier и collector - AsyncMock)

- первый цикл с подключённым ящиком: одно сообщение с текстом персоны, запись в журнале (caplog), флаг стоит, `chat_id` не передан;
- второй цикл молчит;
- все ящики пропущены (`skipped_no_creds`, `skipped_no_token`): нет сообщения и флага;
- ящик с `error` в статистике: нет сообщения и флага;
- только служебные ключи результата: нет сообщения;
- пропущенные + один подключённый ящик: сообщение есть;
- `send_message` бросает исключение: флаг не стоит, цикл не падает, есть warning; после восстановления Telegram сообщение уходит и флаг ставится;
- пустой результат отправки: флаг не стоит;
- сбой показа не останавливает отправку карточек писем;
- `mark_notice_shown` / `has_notice_shown` с ключом без префикса и с ключом `notice:`: `ValueError`;
- флаг и `get_primed_context` независимы, повторная отметка идемпотентна;
- `email_ai_notice(None)`, `_print_privacy_notice()` (текст персоны в stderr, запасной текст при сбое `load_persona`), блок `.env.example` (русский текст, закомментированные строки, ни одна строка не совпадает с `SECRET_PATTERNS`), порядок в `main()` по AST (вызов до `creds_path.exists()`).

## Проверки

- `tests/test_privacy_notice.py` + `test_email_reply_workflow.py`: 38 passed (после задачи 1); `test_privacy_notice.py` + `test_persona_config.py`: 42 passed (после задачи 2); `test_architecture_contract`, `test_persona_storage`, `test_hardcode_scanner`: 18 passed.
- Shield в режиме фиксации на временном индексе (`GIT_INDEX_FILE`): rc=0, настоящий индекс не менялся; pre-commit hook обоих коммитов прошёл штатно (без `--no-verify`).
- `python3 scripts/gate.py`: ИТОГ: ЗЕЛЁНЫЙ (assistant-core 930 тестов, assistant-shared 197; хеш боевой БД до/после совпал `85ef04085268`; import-linter, дрейф персоны, hooks зелёные). Без красных строк, повторный прогон не потребовался.
- `scripts/security_shield.py . --all`: ровно 3 находки, все в `config/persona.yaml:44` (прежние).
- `/opt/assistant-shared`: `git status --short` пуст, миграций нет.

## Напоминание для плана 02-15 (владельцу)

После рестарта `assistant-worker` первый успешный цикл почты запишет флаг `notice:email_ai` в боевую БД (`daily_primed_context`) и отправит владельцу ОДНО сообщение с предупреждением. Это штатная запись демона, а не смоук-проверка. Если Telegram недоступен или результат отправки пуст, флаг не ставится и предупреждение повторится в следующем цикле (раз в 15 минут), пока отправка не удастся.

## Deviations from Plan

None - plan executed exactly as written. Уточнение в рамках плана: «успешной отправкой» считается непустой список id сообщений от `send_message` (иначе незаконфигурированный Telegram пометил бы предупреждение показанным).

## Known Stubs

Нет.

## Threat Flags

Нет новой поверхности атаки (нового сетевого входа нет; одна штатная запись в существующую таблицу и одно сообщение владельцу).

## Self-Check: PASSED

Файлы `src/storage/db.py`, `src/main.py`, `src/persona/notices.py`, `scripts/auth_google.py`, `.env.example`, `tests/test_privacy_notice.py` изменены; коммиты `72c9c3a` и `f143d87` в истории.
