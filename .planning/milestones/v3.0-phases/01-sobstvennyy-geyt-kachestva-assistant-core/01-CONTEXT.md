# Phase 1: Собственный гейт качества assistant-core - Context

**Gathered:** 2026-10-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Одна команда `python3 scripts/gate.py` в `/opt/assistant-core` проверяет assistant-core и `/opt/assistant-shared`. Она печатает по-русски таблицу «проверка → ✓/✗» и итог «ИТОГ: ЗЕЛЁНЫЙ» (rc 0) или «ИТОГ: КРАСНЫЙ» (rc ≠ 0) и не зависит от общего `/opt/chat-app/scripts/gate.py`. Тесты assistant-core физически не могут открыть боевую БД. У assistant-shared появляются собственные тесты и pre-commit hook. Cross-AI адаптер и `CLAUDE.md` переходят на новый гейт. Появляется скрипт выкатки со смоук-проверкой (OPS-01), которым пользуются все последующие фазы.

Требования: GATE-01, GATE-02, GATE-03, GATE-04, GATE-05, OPS-01 (`.planning/REQUIREMENTS.md`). Новых возможностей фаза не добавляет.

</domain>

<decisions>
## Implementation Decisions

### Тесты и hook assistant-shared (GATE-03)
- **D-01:** Тесты assistant-shared **переносятся из chat-app**. Берутся только те, что проверяют саму библиотеку: мигратор, HITL-примитив, библиотеку безопасности. Они адаптируются под `/opt/assistant-shared/tests/`. Тесты, которые проверяют, как chat-app использует библиотеку (web-HITL, dashboard API, конфиг БД chat-app), не переносятся. Недостающие случаи для трёх областей из GATE-03 дописываются.
- **D-02:** Копии тестов в chat-app **остаются**. chat-app заморожен, а его тесты проверяют библиотеку со стороны потребителя. Удалять их не нужно.
- **D-03:** Тесты assistant-shared запускаются через **`/opt/assistant-core/.venv`**: библиотека уже установлена туда, и с ней работает демон. Отдельный `.venv` не создаётся (ограничение RAM/диска VPS).
- **D-04:** pre-commit hook assistant-shared — **тот же security_shield, что в assistant-core**. В репозитории лежат `.githooks/pre-commit` и скрипт установки (по образцу `scripts/install_hooks.sh`). Установка воспроизводима через `core.hooksPath`. Гейт проверяет, что hook установлен, а тест доказывает, что hook блокирует синтетический секрет. Тесты в hook не запускаются.
- **D-05:** Гейт запускает по assistant-shared **две отдельные строки**: `pytest` и `security_shield --all`. Секрет в общей библиотеке тоже делает итог КРАСНЫМ. Это ужесточение относительно буквы GATE-03, где сказано только про тесты.

### Смоук «бот отвечает» (OPS-01)
- **D-06:** Смоук-проверка бота **смешанная**. Автоматически проверяются `getMe` (токен жив) и запись о старте polling в журнале сервиса. Затем скрипт просит владельца отправить боту команду, ждёт её обработки в `journalctl -u assistant-worker` и запрашивает подтверждение «ответ пришёл?». Скрипт **не вызывает `getUpdates`** (иначе он отнимет обновления у работающего бота) и **не использует Telethon-сессию** владельца (её одновременно использует сервис).
- **D-07:** Команда смоука — **`/help`** (уже существует, `src/notifier/bot_handler.py:332`). Исследователь обязан проверить, что обработчик `/help` ничего не пишет в БД. Если пишет, план эскалирует вопрос владельцу и не меняет команду молча.
- **D-08:** «Ошибка в журнале старта»: строки `ERROR`, `CRITICAL` или `Traceback` в окне после старта делают смоук КРАСНЫМ. `WARNING` перечисляются в отчёте и вердикт не меняют. Длину окна выбирает планировщик.
- **D-09:** Подтверждение «ответ пришёл?» Claude задаёт владельцу опросом (AskUserQuestion), а не через интерактивный ввод в терминале. Скрипт должен поддерживать неинтерактивный режим: шаги «ждать обработку команды» и «принять подтверждение» разделяются флагами или фазами запуска, и это не должно требовать TTY.

### Скрипт выкатки (OPS-01)
- **D-10:** Без флага рестарта скрипт выполняет **только read-only смоук** текущего сервиса: is-active, журнал, задачи планировщика, getMe, `/help`. Рестарт выполняется только при явном флаге (например, `--restart`). Claude передаёт этот флаг **только после «да» владельца в опросе** в чате. Владелец может запустить скрипт и сам.
- **D-11:** Резервная копия боевой БД делается **только по флагу** (например, `--backup`), через `sqlite3` backup API с источником в режиме `?mode=ro`, как `make_db_copy` в общем гейте. Копия кладётся вне дерева git. **Phase 3 обязана вызывать выкатку с этим флагом перед применением миграции `0003`.** Это зафиксировано здесь, чтобы планировщик Phase 3 не пропустил шаг. — **Reversibility:** reversible
- **D-12:** При КРАСНОМ смоуке после рестарта скрипт **останавливается и печатает отчёт**: что именно упало и команды отката (предыдущий коммит, восстановление из резервной копии, если она была сделана). **Автоотката нет**: откат — новое необратимое действие и требует нового разрешения владельца.
- **D-13:** Результат смоука сохраняется **markdown-файлом отчёта** (по флагу, например `--report <путь>`) с датой, коммитом HEAD и таблицей проверок. Claude включает его в VERIFICATION.md фазы. В отчёт не попадают секреты, токены и содержимое сообщений.
- **D-14:** «Планировщик зарегистрировал задачи» проверяется **без записи в боевую БД**: по журналу или иному read-only признаку. Ожидаемый список id задач берётся из `src/main.py`. Способ выбирает исследователь.

### Общий гейт chat-app (GATE-04, GATE-05)
- **D-15:** `/opt/chat-app/scripts/gate.py` **не трогается**: он и дальше проверяет assistant-core и assistant-shared как потребитель. Со стороны chat-app меняется только адаптер `agy_cross_ai.sh` (GATE-05), отдельной мелкой задачей `/gsd-quick` в репозитории chat-app.
- **D-16:** Проверка дрейфа `tests/synthetic_persona.py` и `tests/persona_tokens.py` с копиями chat-app работает только на чтение. Если копии chat-app нет, проверка **КРАСНАЯ** (fail-closed) и называет причину. «Не проверено» как зелёный вариант недопустимо.
- **D-17:** Список известных ложных срабатываний shield для assistant-core (`config/persona.yaml`, `nda-keyword`: 3) переносится в новый гейт как замороженный: записи только удаляются, устаревшая запись делает гейт красным. Для assistant-shared список начинается пустым.

### Claude's Discretion
- Как изолировать БД тестов от `load_dotenv(..., override=True)` (GATE-02): правка приоритета в `src/config.py`, страж в `tests/conftest.py`, который роняет тесты при попытке открыть `data/assistant.db`, или их сочетание. Ограничения такие: поведение рантайма с боевым `.env` не меняется, а тест доказывает изоляцию. Гейт дополнительно сверяет SHA-256 боевой БД до и после прогона.
- Устройство `scripts/gate.py`: перенос и адаптация общего гейта (только stdlib, `CheckResult`, разбор junit XML, нормализация вывода shield без утечки текста) и формат таблицы. Ориентир — общий гейт: новый не слабее и не обрывается на первой ошибке.
- Имена флагов и файла скрипта выкатки, таймауты и окно анализа журнала.
- Порядок и разбиение на планы. Правки `CLAUDE.md` и `.planning/config.json` этого проекта делаются в этой фазе. Правка `agy_cross_ai.sh` делается в chat-app через `/gsd-quick`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Требования и рамки фазы
- `.planning/ROADMAP.md` §«Phase 1» и §«Сквозные ограничения цикла» — цель, критерии успеха 1–5, заметки для планирования
- `.planning/REQUIREMENTS.md` — GATE-01..05, OPS-01 (а также GATE-06 в будущих требованиях — вне этой фазы)
- `.planning/PROJECT.md` — Constraints, Key Decisions (гейт, рестарт по запросу)
- `.planning/STATE.md` §Blockers/Concerns — заметки по Phase 1 (`agy_cross_ai.sh`, `load_dotenv override`)

### Образец гейта (только чтение)
- `/opt/chat-app/scripts/gate.py` — эталон: `make_db_copy`, `pytest_ok`, `parse_shield_findings`, `compare_shield_findings`, `KNOWN_SHIELD_FALSE_POSITIVES`, `persona_drift_check`, `db_content_hash`, `render_report`
- `/opt/chat-app/scripts/agy_cross_ai.sh` — адаптер, который нужно переключить на новый гейт (правка только через `/gsd-quick` в chat-app)
- `/opt/chat-app/.claude/skills/agy-delegate/SKILL.md` — правила делегирования

### Источники тестов assistant-shared (только чтение, в chat-app)
- `/opt/chat-app/backend/tests/test_migrations.py` — мигратор
- `/opt/chat-app/backend/tests/test_hitl_shared.py` — HITL-примитив
- `/opt/chat-app/backend/tests/test_security_shared.py`, `test_shield_regressions.py`, `test_shield_parity.py` — библиотека безопасности
- `/opt/chat-app/backend/tests/conftest.py` — фикстуры, которые могут понадобиться при переносе

### Кодовая база
- `.planning/codebase/TESTING.md`, `.planning/codebase/CONVENTIONS.md`, `.planning/codebase/CONCERNS.md`
- `src/config.py` — `load_dotenv(BASE_DIR / ".env", override=True)` и вычисление `SQLITE_DB_PATH`
- `src/main.py` — регистрация задач APScheduler (`add_job`, id задач) для смоук-проверки
- `src/notifier/bot_handler.py:332` — обработчик `/start` и `/help`
- `.githooks/pre-commit`, `scripts/install_hooks.sh`, `scripts/security_shield.py` — образец hook и shield
- `/opt/assistant-shared/assistant_shared/{db,hitl,security}/` — код, который покрывается тестами

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `/opt/chat-app/scripts/gate.py` (582 строки, только stdlib): почти вся логика гейта переносится с адаптацией: junit-счётчики, строгий `pytest_ok`, нормализация shield без утечки NDA-слов, хеш боевой БД, проверка дрейфа, `_safe_*_step` (не обрывается на первой ошибке), `--save` снимков.
- `make_db_copy` (sqlite3 backup, источник `mode=ro`) подходит для `--backup` в скрипте выкатки.
- `.githooks/pre-commit` и `scripts/install_hooks.sh` assistant-core — шаблон для hook assistant-shared.

### Established Patterns
- Гейт и скрипты на stdlib запускаются любым `python3`. Подпроцессы вызываются списком аргументов, без shell и с таймаутами.
- Вывод shield никогда не печатается сырым: только «новая находка / устаревшая запись».
- Гейт не читает `.env`, `credentials.json`, `token.json`, `*.session` и не трогает systemd. Скрипт выкатки трогает systemd только по флагу.
- Сейчас изоляция БД тестов assistant-core держится только на хеше: `override=True` не даёт переопределить путь окружением. Тесты используют `tmp_path` (например, `tests/test_aadhk_parser.py`). `tests/test_gdrive_client.py` упоминает `assistant.db`, и исследователю нужно проверить, не читает ли он реальный `data/`.

### Integration Points
- Новый `scripts/gate.py` в assistant-core. Новый каталог `/opt/assistant-shared/tests/` и hook там. Новый скрипт выкатки в `scripts/`.
- `CLAUDE.md` (`/opt/assistant-core/CLAUDE.md` §3 и `.claude/CLAUDE.md`) переходит с общего гейта на новый.
- `agy_cross_ai.sh` в chat-app переходит на гейт assistant-core при `--repo /opt/assistant-core`.
- assistant-shared — отдельный git-репозиторий (`/opt/assistant-shared/.git`), его коммиты делаются там.

</code_context>

<specifics>
## Specific Ideas

- Таблица гейта разделена по репозиториям: строки assistant-core (pytest, import-linter, shield, дрейф персоны, хеш БД) и строки assistant-shared (pytest, shield, hook установлен).
- Смоук: автоматическая часть, затем «отправьте /help», затем ожидание в журнале, затем вопрос владельцу опросом. Read-only часть запускается на текущем сервисе без рестарта, и её результат записывается в VERIFICATION.md этой фазы.

</specifics>

<deferred>
## Deferred Ideas

- Удаление дублирующих тестов assistant-shared из chat-app — не делается: владелец решил оставить копии (D-02).
- Удаление части assistant-core из общего гейта chat-app — не делается (D-15).
- GATE-06 (полный `requirements.txt`, Dockerfile на 3.12) — будущие требования, не эта фаза.

</deferred>

---

*Phase: 01-sobstvennyy-geyt-kachestva-assistant-core*
*Context gathered: 2026-10-09*
