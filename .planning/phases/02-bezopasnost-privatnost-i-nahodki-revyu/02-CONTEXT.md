# Phase 2: Безопасность, приватность и находки ревью - Context

**Gathered:** 2026-10-10
**Status:** Ready for planning

<domain>
## Phase Boundary

NDA-режим и аудит безопасности определяются данными рабочих пространств и одинаково работают в web и CLI. Текстовая «очисти диалог» не стирает память без защиты. Пользователь заранее предупреждён, что почта обрабатывается внешними ИИ-сервисами.

Требования: SECF-01, SECF-02, SAFE-01, PRIV-01 (`.planning/REQUIREMENTS.md`). Новых возможностей фаза не добавляет. Безопасность только ужесточается (fail-closed).

</domain>

<decisions>
## Implementation Decisions

### Защита «очисти диалог» (SAFE-01)
- **D-01:** Единственный путь очистки памяти — HITL-карточка `/clear` (`handle_cmd_clear_dialog` → `dlg:confirm_clear` / `dlg:cancel_clear` → кнопка «Восстановить»). `SecretaryDialogEngine` (`src/brain/secretary_dialog.py:611`) больше не вызывает `clear_dialog_history` сам.
- **D-02:** Текстовые фразы («очисти диалог», «забудь контекст», «сброс») и любое сообщение, смысл которого ведёт к очистке памяти (в том числе маршрут `clear_dialog` из intent_router), **ничего не очищают**. Бот отвечает по-русски предупреждением: очистка стирает память диалога, чтобы подтвердить её, нужно **вручную следующим сообщением** ввести команду со слэшем (`/clear`). Карточку из текста не показываем.
- **D-03:** Слэш-команды `/clear` и `/reset` идут через существующую HITL-карточку без изменения её поведения (в т.ч. «контекст уже пуст» без карточки).
- **D-04:** Поведение закреплено тестами: текстовое сообщение боту не меняет `bot_dialog_history`, выдаёт предупреждение; `/clear` показывает карточку; без подтверждения история остаётся.
- **D-05:** Ночной сброс 04:00 (`archive_dialog_history`) в фазу не входит. Предупреждение о ежесуточном сбросе памяти показывается при онбординге — это Phase 8 (см. Deferred).

### NDA-режим CLI-аудита из данных (SECF-01)
- **D-06:** Источник правил — `workspaces` из `config/persona.yaml` (`clearance`, `forbidden_remote_substrings`, `forbidden_keywords`, remote/путь). Боевую БД аудит не открывает. Библиотека `assistant_shared/security` остаётся чистой от домена: `scripts/security_shield.py` (wrapper в assistant-core) загружает персону и передаёт правила в `audit_repository`; точный интерфейс выбирает планировщик.
- **D-07:** Репозиторий сопоставляется с пространством по полям пути/remote в данных. Подстрока `"tydex" in path` в `auditor.py:210` и литерал личного аккаунта в `auditor.py` удаляются.
- **D-08:** Fail-closed: данные workspaces недоступны или битые → красный итог (ошибка). Данные есть, но репозиторий не сопоставлен ни с одним пространством → публичная проверка с явным предупреждением в выводе. Для `restricted_nda` без правил remote — как сейчас, нарушение.
- **D-09:** `CORPORATE_NDA_KEYWORDS` в `patterns.py` удаляется. Ключевые слова NDA берутся только из `forbidden_keywords` пространства. Список ложных срабатываний shield может только сокращаться (не расти).
- **D-10:** Тест паритета NDA (`tests/test_nda_script_parity.py`) переписывается и не читает литерал из исходника. Новый тест проверяет, что в `assistant_shared/security` нет подстроки «tydex» и литерала личного аккаунта.

### Общая функция сканирования Web/CLI (SECF-02)
- **D-11:** Общая функция `scan_file_content` живёт в `assistant_shared/security`. Построчное и многострочное сканирование (секреты, `forbidden_keywords`) в одном месте; `audit_path` (web) и CLI-путь оба вызывают её.
- **D-12:** `forbidden_keywords` едут внутри `NdaRemoteRule` (`nda_rule_for(ws)` читает их из того же словаря пространства, который chat-app уже передаёт из `db.py`). Исследователь проверяет, что правка chat-app не нужна; если нужна — только `/gsd-quick` в chat-app, pytest chat-app остаётся зелёным.
- **D-13:** Паритет проверяется синтетическими файлами во временном git-репозитории: чистый файл, файл с секретом, многострочный секрет (PEM), ключевое слово NDA, запрещённый файл (`.env`), пустой файл. `audit_repository` и `audit_path` дают одинаковый набор нарушений. Секреты в тесте собираются из частей, чтобы не срабатывал shield.

### Предупреждение об обработке почты ИИ (PRIV-01)
- **D-14:** Текст предупреждения и список сервисов (Gemini и др.) — поле в `config/persona.yaml` (модель Pydantic `extra=forbid` в `src/persona/models.py`). В коде — нейтральный запасной текст по умолчанию на русском. В тексте: содержимое писем обрабатывается внешними ИИ-сервисами, разработчик не отвечает за утечку секретов и личной информации.
- **D-15:** Места показа: (1) блок внизу `/help` (`handle_cmd_help`, `src/notifier/bot_handler.py:426`); (2) старт сборщика почты — запись в журнале и одно сообщение в Telegram при первом успешном запуске `email_collector`, флаг «показано» хранится в БД (на временной БД в тестах); (3) `scripts/auth_google.py` и подсказки `.env.example`.
- **D-16:** Только информирование, без кнопки «принимаю» и блокировки сбора. Мастер подключения почты и согласие — Phase 8/9.

### Claude's Discretion
- Точное устройство интерфейса `audit_repository` и передачи правил из wrapper; имена функций и модулей.
- Как определять «смысл ведёт к очистке памяти» для D-02 (детерминированный список фраз и маршрут `clear_dialog` или LLM-намерение); достаточно покрыть существующие триггеры и маршрут `intent_router`.
- Имя поля в `persona.yaml` и схема хранения флага показа (в рамках существующих таблиц или миграции в assistant-shared — выбрать минимальное; боевая БД не трогается).
- Порядок и разбиение на планы.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Рамки фазы
- `.planning/ROADMAP.md` §«Phase 2» и §«Сквозные ограничения цикла» — цель, критерии успеха 1–5
- `.planning/REQUIREMENTS.md` — SECF-01, SECF-02, SAFE-01, PRIV-01
- `.planning/PROJECT.md` — Constraints (боевая БД, рестарт по разрешению, fail-closed)
- `.planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-CONTEXT.md` — гейт, смоук OPS-01, правила shield
- `docs/OPS_DEPLOY.md` — процедура рестарта и смоука

### Безопасность (код)
- `/opt/assistant-shared/assistant_shared/security/auditor.py` — `audit_repository` (CLI, литерал «tydex» на строке ~210), `audit_path` (web)
- `/opt/assistant-shared/assistant_shared/security/rules.py` — `NdaRemoteRule`, `nda_rule_for`
- `/opt/assistant-shared/assistant_shared/security/patterns.py` — `SECRET_PATTERNS`, `FORBIDDEN_FILES`, `CORPORATE_NDA_KEYWORDS`
- `/opt/assistant-shared/assistant_shared/security/runner.py` — git-обёртки
- `scripts/security_shield.py` — тонкая обёртка CLI
- `/opt/chat-app/backend/app/api/v1/security.py` и `/opt/chat-app/backend/app/db.py` (чтение `forbidden_keywords`) — web-аудит, потребитель (только чтение)
- `/opt/chat-app/backend/tests/test_nda_equivalence.py`, `tests/test_nda_script_parity.py` — паритет NDA
- `config/persona.yaml` (workspaces: `clearance`, `forbidden_remote_substrings`, `forbidden_keywords`), `src/persona/models.py`

### Диалог и HITL
- `src/notifier/bot_handler.py` (`handle_cmd_clear_dialog` ~1857, `cb_dlg_confirm_clear`, `cb_dlg_cancel_clear`, `cb_dlg_undo_clear`, `handle_cmd_undo_clear`, маршруты `clear_dialog` ~1430 и ~2583)
- `src/brain/secretary_dialog.py:611` — прямая очистка, подлежит замене на предупреждение
- `src/brain/intent_router.py:141` — триггеры `clear_dialog`
- `src/storage/db.py` — `clear_dialog_history`, `restore_dialog_history`, `get_active_dialog_count`
- `tests/test_hitl_safety_guardrails.py`, `tests/test_bot_hitl_parity.py` — образцы тестов HITL

### Предупреждение PRIV-01
- `src/notifier/bot_handler.py:426` (`handle_cmd_help`), `src/collector/email_collector.py`, `src/main.py` (`run_email_collector_cycle`), `scripts/auth_google.py`, `.env.example`

No external specs beyond the above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- HITL-карточка `/clear` с архивом (`is_archived`) и кнопкой «Восстановить» (`restore_dialog_history`) уже работает и покрыта тестами.
- `nda_rule_for(ws)`, `NdaRemoteRule`, `normalize_remote`, `list_remote_urls` — основа NDA-проверки remote.
- `persona.yaml` уже содержит `clearance`, `forbidden_remote_substrings`, `forbidden_keywords` для NDA-пространства.
- `src/persona/loader.py`, `src/persona/models.py` — загрузка и валидация персоны.

### Established Patterns
- Библиотека безопасности не знает про домен; домен приходит параметрами. Shield — тонкая обёртка (SEC-02).
- Fail-closed: сбой проверки = нарушение. Секреты в тестах собираются из частей.
- Тексты для пользователя только по-русски; профильные значения — из `persona.yaml`, не из кода (`tests/test_hardcode_scanner.py` с замороженной базой).

### Integration Points
- Правки в `/opt/assistant-shared` (отдельный git-репозиторий) затрагивают chat-app как потребителя: его pytest остаётся зелёным.
- Гейт `python3 scripts/gate.py` (ЗЕЛЁНЫЙ) — обязательное условие закрытия.
- Рестарт `assistant-worker` только с разрешения владельца, затем смоук OPS-01 (`scripts/deploy.py`).

</code_context>

<specifics>
## Specific Ideas

- Предупреждение «очисти диалог» требует, чтобы человек сам набрал команду со слэшем следующим сообщением.
- Предупреждение PRIV-01 показывается в трёх местах, но без блокировки и без согласия.

</specifics>

<deferred>
## Deferred Ideas

- Предупреждение при онбординге о ежесуточном сбросе памяти диалога в 04:00 — Phase 8 (мастер первого запуска).
- Уведомление после ночного сброса с возможностью восстановить — новая возможность, в бэклог.
- Кнопка «прочитал и принимаю» для PRIV-01 — Phase 8/9 (онбординг, мастер почты).
- Мастер подключения почты — Phase 9.

</deferred>

---

*Phase: 02-bezopasnost-privatnost-i-nahodki-revyu*
*Context gathered: 2026-10-10*
