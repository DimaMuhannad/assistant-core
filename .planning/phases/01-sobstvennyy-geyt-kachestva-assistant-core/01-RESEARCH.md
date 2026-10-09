# Phase 1: Собственный гейт качества assistant-core - Research

**Researched:** 2026-10-09
**Domain:** dev-tooling и эксплуатация на stdlib Python 3.12 (pytest-гейт, изоляция БД в тестах, git-hook, systemd/journalctl-смоук); Package Legitimacy: новых пакетов нет
**Confidence:** HIGH (почти всё проверено чтением кода, запуском и журналом сервиса; открытые места помечены `[ASSUMED]`)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Тесты и hook assistant-shared (GATE-03)**
- **D-01:** Тесты assistant-shared **переносятся из chat-app**. Берутся только те, что проверяют саму библиотеку: мигратор, HITL-примитив, библиотеку безопасности. Они адаптируются под `/opt/assistant-shared/tests/`. Тесты, которые проверяют, как chat-app использует библиотеку (web-HITL, dashboard API, конфиг БД chat-app), не переносятся. Недостающие случаи для трёх областей из GATE-03 дописываются.
- **D-02:** Копии тестов в chat-app **остаются**. chat-app заморожен, а его тесты проверяют библиотеку со стороны потребителя. Удалять их не нужно.
- **D-03:** Тесты assistant-shared запускаются через **`/opt/assistant-core/.venv`**: библиотека уже установлена туда, и с ней работает демон. Отдельный `.venv` не создаётся (ограничение RAM/диска VPS).
- **D-04:** pre-commit hook assistant-shared — **тот же security_shield, что в assistant-core**. В репозитории лежат `.githooks/pre-commit` и скрипт установки (по образцу `scripts/install_hooks.sh`). Установка воспроизводима через `core.hooksPath`. Гейт проверяет, что hook установлен, а тест доказывает, что hook блокирует синтетический секрет. Тесты в hook не запускаются.
- **D-05:** Гейт запускает по assistant-shared **две отдельные строки**: `pytest` и `security_shield --all`. Секрет в общей библиотеке тоже делает итог КРАСНЫМ. Это ужесточение относительно буквы GATE-03, где сказано только про тесты.

**Смоук «бот отвечает» (OPS-01)**
- **D-06:** Смоук-проверка бота **смешанная**. Автоматически проверяются `getMe` (токен жив) и запись о старте polling в журнале сервиса. Затем скрипт просит владельца отправить боту команду, ждёт её обработки в `journalctl -u assistant-worker` и запрашивает подтверждение «ответ пришёл?». Скрипт **не вызывает `getUpdates`** (иначе он отнимет обновления у работающего бота) и **не использует Telethon-сессию** владельца (её одновременно использует сервис).
- **D-07:** Команда смоука — **`/help`** (уже существует, `src/notifier/bot_handler.py:332`). Исследователь обязан проверить, что обработчик `/help` ничего не пишет в БД. Если пишет, план эскалирует вопрос владельцу и не меняет команду молча.
- **D-08:** «Ошибка в журнале старта»: строки `ERROR`, `CRITICAL` или `Traceback` в окне после старта делают смоук КРАСНЫМ. `WARNING` перечисляются в отчёте и вердикт не меняют. Длину окна выбирает планировщик.
- **D-09:** Подтверждение «ответ пришёл?» Claude задаёт владельцу опросом (AskUserQuestion), а не через интерактивный ввод в терминале. Скрипт должен поддерживать неинтерактивный режим: шаги «ждать обработку команды» и «принять подтверждение» разделяются флагами или фазами запуска, и это не должно требовать TTY.

**Скрипт выкатки (OPS-01)**
- **D-10:** Без флага рестарта скрипт выполняет **только read-only смоук** текущего сервиса: is-active, журнал, задачи планировщика, getMe, `/help`. Рестарт выполняется только при явном флаге (например, `--restart`). Claude передаёт этот флаг **только после «да» владельца в опросе** в чате. Владелец может запустить скрипт и сам.
- **D-11:** Резервная копия боевой БД делается **только по флагу** (например, `--backup`), через `sqlite3` backup API с источником в режиме `?mode=ro`, как `make_db_copy` в общем гейте. Копия кладётся вне дерева git. **Phase 3 обязана вызывать выкатку с этим флагом перед применением миграции `0003`.** Это зафиксировано здесь, чтобы планировщик Phase 3 не пропустил шаг. — **Reversibility:** reversible
- **D-12:** При КРАСНОМ смоуке после рестарта скрипт **останавливается и печатает отчёт**: что именно упало и команды отката (предыдущий коммит, восстановление из резервной копии, если она была сделана). **Автоотката нет**: откат — новое необратимое действие и требует нового разрешения владельца.
- **D-13:** Результат смоука сохраняется **markdown-файлом отчёта** (по флагу, например `--report <путь>`) с датой, коммитом HEAD и таблицей проверок. Claude включает его в VERIFICATION.md фазы. В отчёт не попадают секреты, токены и содержимое сообщений.
- **D-14:** «Планировщик зарегистрировал задачи» проверяется **без записи в боевую БД**: по журналу или иному read-only признаку. Ожидаемый список id задач берётся из `src/main.py`. Способ выбирает исследователь.

**Общий гейт chat-app (GATE-04, GATE-05)**
- **D-15:** `/opt/chat-app/scripts/gate.py` **не трогается**: он и дальше проверяет assistant-core и assistant-shared как потребитель. Со стороны chat-app меняется только адаптер `agy_cross_ai.sh` (GATE-05), отдельной мелкой задачей `/gsd-quick` в репозитории chat-app.
- **D-16:** Проверка дрейфа `tests/synthetic_persona.py` и `tests/persona_tokens.py` с копиями chat-app работает только на чтение. Если копии chat-app нет, проверка **КРАСНАЯ** (fail-closed) и называет причину. «Не проверено» как зелёный вариант недопустимо.
- **D-17:** Список известных ложных срабатываний shield для assistant-core (`config/persona.yaml`, `nda-keyword`: 3) переносится в новый гейт как замороженный: записи только удаляются, устаревшая запись делает гейт красным. Для assistant-shared список начинается пустым.

### Claude's Discretion
- Как изолировать БД тестов от `load_dotenv(..., override=True)` (GATE-02): правка приоритета в `src/config.py`, страж в `tests/conftest.py`, который роняет тесты при попытке открыть `data/assistant.db`, или их сочетание. Ограничения такие: поведение рантайма с боевым `.env` не меняется, а тест доказывает изоляцию. Гейт дополнительно сверяет SHA-256 боевой БД до и после прогона.
- Устройство `scripts/gate.py`: перенос и адаптация общего гейта (только stdlib, `CheckResult`, разбор junit XML, нормализация вывода shield без утечки текста) и формат таблицы. Ориентир — общий гейт: новый не слабее и не обрывается на первой ошибке.
- Имена флагов и файла скрипта выкатки, таймауты и окно анализа журнала.
- Порядок и разбиение на планы. Правки `CLAUDE.md` и `.planning/config.json` этого проекта делаются в этой фазе. Правка `agy_cross_ai.sh` делается в chat-app через `/gsd-quick`.

### Deferred Ideas (OUT OF SCOPE)
- Удаление дублирующих тестов assistant-shared из chat-app — не делается: владелец решил оставить копии (D-02).
- Удаление части assistant-core из общего гейта chat-app — не делается (D-15).
- GATE-06 (полный `requirements.txt`, Dockerfile на 3.12) — будущие требования, не эта фаза.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GATE-01 | Один `python3 scripts/gate.py`: pytest core, `lint-imports`, `security_shield --all`; таблица по-русски, ИТОГ ЗЕЛЁНЫЙ/КРАСНЫЙ; 0 тестов/skip/xfail/xpass/deselected = красный; не обрывается на первой ошибке | Готовый образец `/opt/chat-app/scripts/gate.py` (582 строки, stdlib) переносится почти целиком; `pytest_ok`, `pytest_summary_flags`, `_safe_*_step`. Базовый прогон: 421 тест, 1 флакнувший по времени (см. Pitfall 1) — гейт нельзя считать зелёным до его стабилизации |
| GATE-02 | Тесты не могут открыть `data/assistant.db`; `load_dotenv(override=True)` не перебивает изоляцию (доказано тестом); SHA-256 до/после | Зонд `sys.addaudithook` показал, что сегодня боевую БД читает ровно один тест (`test_create_server_backup_archive`); audit-hook подтверждённо блокирует `sqlite3.connect`, `aiosqlite` и `open`; нужен разбор `file:`-URI; правка приоритета в `src/config.py` (4 строки) |
| GATE-03 | У assistant-shared свои pytest-тесты (мигратор, HITL, security) и воспроизводимо установленный hook; отдельная строка гейта | 5 файлов-источников в chat-app (1099 строк) проверяют только библиотеку; shared сегодня без `tests/`, `scripts/`, `.githooks/`, `core.hooksPath` не задан; shield по shared сегодня rc 0 (20 файлов) |
| GATE-04 | Не слабее общего гейта по части core: дрейф persona/tokens (read-only), замороженный список FP | Копии chat-app сейчас идентичны (sha256 совпали); таблица соответствия строк общего гейта и нового — в разделе Architecture |
| GATE-05 | `agy_cross_ai.sh --repo /opt/assistant-core` и `CLAUDE.md` используют новый гейт; пробный прогон ЗЕЛЁНЫЙ | Адаптер жёстко вызывает `python3 "$SCRIPT_DIR/gate.py"` из каталога chat-app (строки блока `# ---------- gate ----------`); нужен выбор гейта по `$TOP`; список PROTECTED уже защищает `scripts/gate.py` целевого репозитория от правок агента |
| OPS-01 | Процедура выкатки + скрипт: рестарт только по флагу, смоук (active, журнал без ошибок, задачи планировщика, бот отвечает), без записи в боевую БД | Выяснено по журналу: старт выполняет начальные циклы ДО `scheduler.start()` (~50 с), останов может длиться 90 с до SIGKILL, ERROR в штатном журнале частые (Pitfall 4-6); `/help` не пишет в БД (проверено чтением) |
</phase_requirements>

## Summary

Фаза состоит из трёх независимых по сути блоков, склеенных новым `scripts/gate.py`: (1) изоляция тестов от боевой БД и порт гейта; (2) собственный набор тестов и hook у `/opt/assistant-shared`; (3) скрипт выкатки со смоуком и мелкая правка адаптера в chat-app. Образец гейта уже есть и хорошо спроектирован, поэтому основной риск не в написании кода, а в четырёх вещах, которых нет в CONTEXT.md и которые выяснились только при реальном запуске.

Во-первых, **базовый прогон не зелёный**: 421 тест за 194 с, 420 прошли, 1 упал (`tests/test_command_aliases.py::test_fast_intent_router_aliases`, `latency_ms < 50.0`, получено 61.7). Три повторных прогона файла отдельно прошли. Это жёсткое по времени условие на загруженной VPS (свободно около 650 МБ, демон работает). Критерий успеха 1 требует ЗЕЛЁНЫЙ на чистом дереве, поэтому стабилизация этого теста (и такого же `< 250` в соседнем) входит в фазу. Во-вторых, **единственный тест, касающийся боевой БД, это `test_create_server_backup_archive`**: он читает `/opt/assistant-core/data/assistant.db`, `.env` и `*.session` по жёстким абсолютным путям из `src/connectors/gdrive/client.py` и пакует их в архив. Страж его уронит, поэтому тест нужно переписать, а функции дать параметр каталога. В-третьих, **смоук по D-08 в буквальном виде будет часто краснеть на здоровом демоне**: в журнале за сутки ERROR дают сбой логина LMS (с Traceback), таймауты IMAP, `database is locked` и сеть aiogram, а при старте до `scheduler.start()` выполняются начальные циклы коллекторов. В-четвёртых, **сравнение хеша боевой БД до/после может краснеть из-за штатной записи демона**, а не из-за тестов; нужен диагностический вывод и узкое окно измерения.

**Primary recommendation:** перенести общий гейт в `scripts/gate.py` почти построчно (stdlib, `CheckResult`, junit-разбор, нормализация shield), добавить строки assistant-shared и hook, изоляцию БД сделать тремя слоями (audit-hook страж в `tests/conftest.py` с разбором `file:`-URI + явная переменная-переопределение в `src/config.py`, захваченная до `load_dotenv` + SHA-256 дампа до/после вокруг pytest), а скрипт выкатки писать на stdlib с внедряемым раннером подпроцессов, чтобы все ветки (в том числе «рестарт не вызывается без флага») проверялись юнит-тестами без systemd.

## Architectural Responsibility Map

Здесь «уровни» это слои инструментария, а не web-тиры.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Агрегация проверок и вердикт ЗЕЛЁНЫЙ/КРАСНЫЙ | `scripts/gate.py` (stdlib, вне venv) | — | Должен запускаться любым `python3`, не зависеть от окружения тестов |
| Запрет открытия боевой БД в тестах | Тестовая оснастка (`tests/conftest.py`, audit-hook) | Рантайм-конфиг (`src/config.py`, переменная-переопределение) | Аудит-хук работает в процессе pytest и ловит любой путь; конфиг убирает сам повод попасть на боевой путь |
| Независимое доказательство «БД не тронута» | Гейт (хеш дампа до/после) | — | Проверка снаружи процесса тестов, не может быть отключена тестом |
| Тесты библиотеки схемы/HITL/security | `/opt/assistant-shared/tests` (запуск через core `.venv`) | Гейт (отдельная строка) | Библиотека владеет собственной проверкой, гейт только запускает |
| Блокировка секрета при коммите shared | `/opt/assistant-shared/.githooks/pre-commit` + `scripts/security_shield.py` | Гейт (проверка «hook установлен») + тест hook | Установка через `core.hooksPath`, воспроизводима скриптом |
| Смоук сервиса | Скрипт выкатки (`scripts/deploy.py`, stdlib) | systemd/journald (источник истины) | Читает состояние снаружи, не пишет в БД, не импортирует `src` |
| Решение «рестартовать» | Владелец (через опрос Claude) | Флаг `--restart` | Необратимое с точки зрения сервиса действие; флаг не выставляется без «да» |
| Выбор гейта для cross-AI | Адаптер `agy_cross_ai.sh` в chat-app | — | Правка только через `/gsd-quick` в chat-app |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib (`subprocess`, `hashlib`, `sqlite3`, `xml.etree`, `argparse`, `ast`, `urllib.request`, `json`) | 3.12.3 `[VERIFIED: python3 --version]` | `scripts/gate.py` и `scripts/deploy.py` | Требование контекста: гейт запускается любым `python3`; образец уже на stdlib |
| pytest | 9.1.1 `[VERIFIED: .venv/bin/pip list]` | Запуск тестов core и shared | Уже установлен в `/opt/assistant-core/.venv` (D-03) |
| pytest-asyncio | 1.4.0 `[VERIFIED: .venv/bin/pip list]` | `asyncio_mode = auto` в core; нужен shared | Уже установлен |
| import-linter / grimp | 2.15 / 3.17 `[VERIFIED: .venv/bin/pip list]` | Строка `lint-imports` | Уже в `requirements-dev.txt` |
| git | 2.43.0 `[VERIFIED: git --version]` | Shield, hook, дрейф-проверка, откат | Уже требуется проектом |
| systemd `systemctl`/`journalctl` | host `[VERIFIED: systemctl cat/show, journalctl чтение]` | Смоук и рестарт | Единственный источник состояния сервиса |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `assistant_shared` (editable через `.pth`) | 0.1.0 `[VERIFIED: pyproject.toml, ls site-packages]` | Предмет тестов shared | Импортируется из core `.venv` |
| aiogram | 3.31.0 `[VERIFIED: pip list]` | Только источник форматов строк журнала («Update id=… is handled»), не зависимость скрипта | Для разбора журнала |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| audit-hook в процессе pytest | Подмена `Database`/`aiosqlite.connect` через monkeypatch | Monkeypatch не ловит `open()`, `sqlite3.connect` напрямую и `tar.add`; audit-hook нельзя снять, ловит всё |
| Хеш логического дампа | SHA-256 байтов файла | Файл в WAL-режиме меняется при checkpoint без изменения данных; дамп в одной транзакции стабилен (прецедент WR-10 в chat-app gate, `db_content_hash`) |
| `getMe` по токену из `.env` | Строка журнала `Run polling for bot @… id=…` (эквивалент `getMe` внутри aiogram) | Журнал не требует токена, но подтверждает только момент старта; D-06 требует `getMe`, поэтому: основной путь `getMe`, журнал как независимое подтверждение |
| Отдельный `.venv` для shared | core `.venv` | Решено в D-03 |

**Installation:** новых зависимостей нет. Для shared допустимо добавить в `pyproject.toml` только метаданные `[project.optional-dependencies] dev = ["pytest", "pytest-asyncio"]` без установки `[ASSUMED: вариант оформления, не обязателен]`.

**Version verification:** версии получены командой `.venv/bin/pip list` в этой сессии; обновление пакетов не требуется.

## Package Legitimacy Audit

Фаза не устанавливает внешних пакетов. Все используемые (`pytest`, `pytest-asyncio`, `import-linter`, `grimp`) уже стоят в `/opt/assistant-core/.venv` и перечислены в `requirements*.txt` проекта.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| — (новых нет) | — | — | — | — | — | Approved (не устанавливаются) |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

Ограничение проекта «новые зависимости только с одобрения владельца» соблюдено: `pytest-timeout`, `pytest-xdist`, `pytest-cov` НЕ предлагаются (их нет в venv; таймауты обеспечивает `subprocess.run(timeout=…)`).

## Architecture Patterns

### System Architecture Diagram

```
владелец / Claude
      |
      v
python3 scripts/gate.py  (stdlib, один процесс, последовательно, RAM 2 ГБ)
      |
      +--> [hash_before] sha256 дампа data/assistant.db (sqlite3 ?mode=ro, одна транзакция)
      |
      +--> pytest core  --env ASSISTANT_DB_PATH_OVERRIDE=<tmp>, PYTEST_ADDOPTS очищен-->  .venv/bin/pytest tests -v --junitxml
      |        |  (внутри процесса pytest: tests/conftest.py ставит audit-hook;
      |        |   любой open/sqlite3.connect на боевой путь -> RuntimeError -> тест красный)
      |        v
      |     junit XML + последняя строка итога -> pytest_ok(): rc==0, tests>0, нет failed/error/skipped/xfailed/xpassed/deselected
      |
      +--> [hash_after] sha256 дампа сразу после pytest core  -> совпал? (иначе КРАСНЫЙ + диагностика «демон писал?»)
      +--> lint-imports --no-logo --no-cache (core)
      +--> security_shield core --all  -> parse_shield_findings -> compare с замороженным KNOWN (только «новая находка / устаревшая запись»)
      +--> дрейф tests/synthetic_persona.py и tests/persona_tokens.py vs /opt/chat-app/backend/tests/* (read-only, нет файла -> КРАСНЫЙ)
      +--> pytest shared  (cwd /opt/assistant-shared, core .venv, -p no:cacheprovider)
      +--> security_shield shared --all (KNOWN пустой)
      +--> hook shared установлен? (core.hooksPath == .githooks, файл исполняемый)
      v
render_report(): таблица «репозиторий | проверка | ✓/✗» + «↳ деталь» + «ИТОГ: ЗЕЛЁНЫЙ|КРАСНЫЙ»; rc 0 / 1


python3 scripts/deploy.py [--backup] [--restart] [--report PATH] [фазы смоука]
      |
      +--(--backup)--> sqlite3 backup API, источник file:...?mode=ro -> /var/backups/assistant-core/*.db (0600, вне git)
      +--(--restart)--> проверка: дерево git чистое -> запомнить HEAD и предыдущую инвокацию -> systemctl restart (timeout >= 300 c)
      +--> смоук (read-only):
              systemctl show (ActiveState, MainPID, InvocationID, NRestarts)
              journalctl _SYSTEMD_INVOCATION_ID=<id>  ->  окно старта, ERROR/CRITICAL/Traceback, WARNING, 'Added job "<func>"'
              ast(src/main.py) -> ожидаемые функции задач  vs  'Added job' в журнале
              getMe (токен из .env, только ключ TELEGRAM_BOT_TOKEN, не печатается)
              фаза 2: ждать 'Update id=N is handled' после метки времени (без getUpdates, без Telethon)
              фаза 3: --confirm-help yes|no  (ответ владельца, приходит от Claude через опрос)
      +--> отчёт .md (дата, HEAD, таблица), КРАСНЫЙ после рестарта -> стоп + команды отката (печать, не выполнение)
```

### Recommended Project Structure

```
/opt/assistant-core/
├── scripts/
│   ├── gate.py                  # НОВЫЙ: гейт (stdlib), защищён списком PROTECTED адаптера
│   └── deploy.py                # НОВЫЙ: выкатка + смоук (имя на усмотрение планировщика)
├── tests/
│   ├── conftest.py              # + audit-hook страж боевой БД, env-переопределение до импорта src
│   ├── test_live_db_guard.py    # НОВЫЙ: страж блокирует; override=True не перебивает путь
│   ├── test_gate.py             # НОВЫЙ: порт ~35 юнит-тестов chat-app + строки shared/hook
│   ├── test_gate_red_cases.py   # НОВЫЙ: мини-проекты в tmp: сломанный/skip/xfail/xpass/deselected/0 тестов -> КРАСНЫЙ
│   └── test_deploy_script.py    # НОВЫЙ: чистые функции + фейковый раннер
├── docs/OPS_DEPLOY.md           # НОВЫЙ: описание процедуры (docs/ в allowlist сканера хардкода)
└── src/config.py                # + захват переопределения до load_dotenv (4 строки)

/opt/assistant-shared/           # отдельный git-репозиторий
├── .githooks/pre-commit         # копия образца core (тот же порядок поиска Python)
├── scripts/security_shield.py   # тонкая обёртка (как в core), импорт assistant_shared.security
├── scripts/install_hooks.sh     # по образцу core
├── pyproject.toml               # + [tool.pytest.ini_options] asyncio_mode=auto, testpaths=tests
└── tests/
    ├── test_migrations.py       # из chat-app (динамический список миграций)
    ├── test_hitl_shared.py      # из chat-app (anyio -> asyncio)
    ├── test_security_shared.py  # из chat-app
    ├── test_shield_regressions.py  # из chat-app без WR-13 (app.*)
    ├── test_shield_parity.py    # из chat-app
    └── test_pre_commit_hook.py  # из chat-app (4 теста hook + 3 теста установщика)
```

### Pattern 1: Страж боевой БД на `sys.addaudithook`

**What:** в самом начале `tests/conftest.py` (до `from src...`) регистрируется audit-hook. Хук нельзя снять до конца процесса, он видит `open`, `sqlite3.connect` (включая вызовы из потока `aiosqlite`).
**When to use:** всегда в процессе pytest core.
**Verified behaviour:** эксперимент в этой сессии: хук на `sqlite3.connect` и `open` бросает `RuntimeError`; для `sqlite3.connect(path)` и `aiosqlite.connect(path)` исключение дошло до вызывающего кода `[VERIFIED: запуск .venv/bin/python в scratchpad]`. Для URI `file:/…?mode=ro` аргумент `database` содержит `file:` и `?mode=ro`, простая проверка `endswith` не сработала (запрос прошёл до реальной попытки открыть) `[VERIFIED: тот же запуск]`, поэтому нужен разбор URI.
**Example:**
```python
# tests/conftest.py (начало файла, до любых импортов src)  -- эскиз, не готовый код
import os, sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

_CORE = Path(__file__).resolve().parents[1]
_LIVE = {  # боевая БД и сопутствующие файлы; корневой assistant.db (544 КБ) тоже закрыт
    _CORE / "data" / "assistant.db",
    _CORE / "assistant.db",
}
_SUFFIXES = ("", "-wal", "-shm", "-journal")
_BLOCKED = {os.path.realpath(str(p) + s) for p in _LIVE for s in _SUFFIXES}
_BASENAMES = ("assistant.db", "assistant.db-wal", "assistant.db-shm", "assistant.db-journal")
_busy = False

def _normalize(raw):
    if isinstance(raw, bytes):
        raw = os.fsdecode(raw)
    if not isinstance(raw, (str, os.PathLike)):
        return None
    text = os.fspath(raw)
    if text.startswith("file:"):                     # sqlite URI: file:/abs/path?mode=ro
        text = unquote(urlsplit(text).path)
    return text

def _guard(event, args):
    global _busy
    if _busy or event not in ("open", "sqlite3.connect") or not args:
        return
    text = _normalize(args[0])
    if not text or not text.endswith(_BASENAMES):    # дешёвый префильтр: хук вызывается на каждый open()
        return
    _busy = True
    try:
        if os.path.realpath(text) in _BLOCKED:
            raise RuntimeError(f"тест пытался открыть боевую БД: {text}")
    finally:
        _busy = False

sys.addaudithook(_guard)
```
Замечания: относительный путь (`./data/assistant.db`) нормализуется через `realpath` от текущего cwd. Префильтр по имени файла обязателен ради скорости (pytest делает тысячи `open`). Страж должен иметь собственный тест, который проверяет все четыре формы (прямой путь, `aiosqlite`, `file:` URI, относительный путь) на временной БД под именем, совпадающим с шаблоном; сам тест не должен трогать боевой файл (его путь только сравнивается строкой).

### Pattern 2: Приоритет пути БД в `src/config.py` (минимальная правка)

**What:** захватить явное переопределение из окружения ДО `load_dotenv(..., override=True)` и применить после.
**Текущий код** `[VERIFIED: src/config.py:8,12,14-16]`:
```
load_dotenv(BASE_DIR / ".env", override=True)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/assistant.db")
SQLITE_DB_PATH = DATABASE_URL.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
if not os.path.isabs(SQLITE_DB_PATH):
    SQLITE_DB_PATH = str(BASE_DIR / SQLITE_DB_PATH)
```
**Эскиз правки:**
```python
_DB_OVERRIDE = os.environ.get("ASSISTANT_DB_PATH_OVERRIDE")   # читается ДО load_dotenv
load_dotenv(BASE_DIR / ".env", override=True)
...
if _DB_OVERRIDE:                                              # в боевом запуске переменной нет -> поведение прежнее
    SQLITE_DB_PATH = _DB_OVERRIDE
```
**Тест, доказывающий требование GATE-02** (не зависит от содержимого `.env`, которое читать нельзя): подменить `dotenv.load_dotenv` фейком, который эмулирует `override=True` (выставляет `os.environ["DATABASE_URL"]` на боевой URL), выставить `ASSISTANT_DB_PATH_OVERRIDE=<tmp>`, `importlib.reload(src.config)`, проверить `config.SQLITE_DB_PATH == <tmp>`; парный тест: без переменной результат равен значению из «dotenv» (рантайм не изменён). Оба теста в `finally` перезагружают `src.config` в исходное состояние (иначе соседние тесты увидят подмену). Второй слой: `tests/conftest.py` выставляет `ASSISTANT_DB_PATH_OVERRIDE` в каталог `tmp_path_factory`-уровня до импорта `src`, гейт передаёт ту же переменную подпроцессу pytest.
Имя переменной `[ASSUMED]`: любое, лишь бы её не было в боевом `.env`.

### Pattern 3: Строки гейта и соответствие общему гейту (GATE-04)

| Строка общего гейта (по части core) | В новом гейте | Примечание |
|---|---|---|
| pytest assistant-core (`-v`, `-p no:cacheprovider`, junit, `--basetemp`) | Да, без изменений + `PYTEST_ADDOPTS` очищается, добавляется `-o xfail_strict=true` (xpass тогда падает, а не проходит молча) `[ASSUMED]` | Таймаут 900 с, базовый прогон 194 с |
| import-linter (`lint-imports --no-logo --no-cache`) | Да | Сегодня: 5 контрактов kept, 0 broken `[VERIFIED: запуск]` |
| security_shield `--all` с замороженным списком | Да, словарь только для `assistant-core`: `("config/persona.yaml", "nda-keyword"): 3` | Сегодня shield core rc 1, ровно эти 3 находки `[VERIFIED: запуск]` |
| дрейф `synthetic_persona.py` | Да, read-only, отсутствие файла = КРАСНЫЙ | SHA совпали сейчас `[VERIFIED: sha256sum]` |
| дрейф `persona_tokens.py` | Да | то же |
| боевая БД не изменена | Да, но окно сужено (см. Pitfall 3) | |
| (новое) pytest shared | Да, отдельная строка | D-05 |
| (новое) security_shield shared `--all` | Да, список пуст | сегодня rc 0, 20 файлов `[VERIFIED: запуск]` |
| (новое) hook shared установлен | Да | `git config core.hooksPath == .githooks`, файл `.githooks/pre-commit` исполняемый |
| (опционально) hook core установлен | Да, дёшево, симметрично | сейчас `core.hooksPath = .githooks` `[VERIFIED: git config]` |
| копия боевой БД для pytest chat-app, pytest chat-app, lint chat-app, shield chat-app | Нет (не часть core) | остаётся в общем гейте chat-app (D-15) |

### Pattern 4: Смоук по журналу текущей инвокации

Фильтр по `_SYSTEMD_INVOCATION_ID`, а не по времени: временные метки приложения смешаны (первые строки в UTC, остальные в MSK, потому что `TZ` выставляется после старта логирования) `[VERIFIED: журнал 2026-10-08 09:30:48 против 12:30:49]`, а метки journald однозначны.
```bash
INV=$(systemctl show assistant-worker -p InvocationID --value)
journalctl -u assistant-worker _SYSTEMD_INVOCATION_ID=$INV --no-pager -o short-iso
```
Проверено на текущей инвокации: 5680 строк `[VERIFIED: journalctl … | wc -l]`.

Факты журнала, на которых строится смоук `[VERIFIED: journalctl -u assistant-worker, старт 2026-10-08 09:30:34]`:
- Планировщик логирует `apscheduler.scheduler: Added job "run_sentinel_cycle" to job store "default"` (имя ФУНКЦИИ, а не `id=`) для 10 задач, затем `apscheduler.scheduler: Scheduler started`, `assistant-worker: Scheduler started. Reset/Priming at 04:00…`, `assistant-worker: Starting Telegram Bot dispatcher polling…`, `aiogram.dispatcher: Start polling`, `aiogram.dispatcher: Run polling for bot @… id=… - '…'`.
- Вся эта группа появилась через ~49 с после старта процесса (09:30:34 → 09:31:23), потому что `main()` до `scheduler.start()` последовательно выполняет начальные циклы (`src/main.py:703-707`: sentinel, Telegram-коллектор, почта, LMS).
- Обработанный апдейт: `aiogram.event: Update id=797886290 is handled. Duration 182 ms by bot id=…`; формат подтверждён исходником `aiogram/dispatcher/dispatcher.py:182` («handled» / «not handled»).

Ожидаемые задачи берутся разбором `src/main.py` через `ast` (поиск вызовов `scheduler.add_job`, аргумент 0 это имя функции, `id=` строковый литерал). Сейчас в файле десять id, дословно `[VERIFIED: src/main.py:728,737,746,755,765,775,784,794,805,814]`:
`schedule_sentinel_job`, `telegram_collector_job`, `email_collector_job`, `lms_monitor_job`, `morning_brief_job`, `evening_digest_job`, `aadhk_gdrive_sync_job`, `nightly_reset_and_priming_job`, `weekly_memory_review_job`, `live_ticker_refresh_job`.
Соответствие id → имя функции в журнале (`run_sentinel_cycle`, `run_telegram_collector_cycle`, `run_email_collector_cycle`, `run_lms_monitor_cycle`, `run_morning_brief_cycle`, `run_evening_digest_cycle`, `run_aadhk_gdrive_sync_cycle`, `run_nightly_reset_and_priming_cycle`, `run_weekly_memory_review_cycle`, `run_live_ticker_refresh_cycle`) подтверждено строками журнала `Added job`. Разбор `ast` автоматически подхватит задачи, которые добавят фазы 4 и 5 (GIT-03, NTN-01, HIT-02); задачи под `if` считать необязательными и печатать как «условная».

### Anti-Patterns to Avoid

- **Повторять `getUpdates`/Telethon в смоуке:** отнимет обновления у бота (запрещено D-06).
- **Сравнивать хеш файла БД вместо дампа:** WAL-checkpoint меняет файл без изменения данных.
- **Печатать сырой вывод shield, journalctl или исключений `urllib`:** в них бывают адреса, e-mail, URL с токеном бота.
- **Полагаться на `time.sleep` для ожидания старта:** использовать опрос журнала инвокации с дедлайном.
- **Запускать gate-в-тесте полностью:** рекурсия (тот же запрет, что в chat-app `test_gate.py`). Красные случаи проверять на мини-проектах в `tmp_path`.
- **Класть в `scripts/*.py` токены профиля владельца** (имя, организация, аккаунт бота, домены): `tests/test_hardcode_scanner.py` сканирует `scripts/` и baseline пуст `[VERIFIED: tests/test_hardcode_scanner.py, tests/hardcode_baseline.py:15]`. Пути вида `/opt/chat-app`, `/opt/assistant-core` не флагуются `[VERIFIED: запуск token_classes_in_line]`, а `@opd_guap_popov_bot`, «ГУАП», «tydex_*» флагуются.
- **Тестовые литералы секретов целиком:** `tests/` не в allowlist shield. Токен Telegram-формата, `AIzaSy…`, `sk-…` собирать из частей (`"AIzaSy" + "A1B2…"`), как в образце `test_pre_commit_hook.py`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Нормализация вывода shield | Новый разбор | `parse_shield_findings` / `compare_shield_findings` из `/opt/chat-app/scripts/gate.py:316-368` | Уже отлажены, не пропускают текст NDA-слов и e-mail |
| Строгий критерий pytest | Свой разбор stdout | `pytest_counts` + `pytest_summary_flags` + `pytest_ok` (`gate.py:159-207`) | Покрывают 0 тестов, skipped, xfailed/xpassed/deselected |
| Консистентная копия БД | `shutil.copy` | `sqlite3` backup API с `file:…?mode=ro` (`make_db_copy`, `gate.py:97-113`) | Целостный снимок в WAL, не создаёт файлов рядом |
| Хеш содержимого БД | Хеш файла | `db_content_hash` (`gate.py:466-481`, `iterdump` в одной транзакции) | Устойчив к checkpoint |
| Блокировка боевой БД в тестах | Патчи `Database.connection` | `sys.addaudithook` | Ловит `open`, `sqlite3`, `aiosqlite`, `tarfile`, subprocess-в-процессе |
| Список запланированных задач | Жёсткий список id в скрипте | `ast`-разбор `src/main.py` | Не отстаёт от фаз 4-5 |
| Фильтр журнала сервиса | Разбор временных меток приложения | `journalctl _SYSTEMD_INVOCATION_ID=…` | Метки приложения смешаны UTC/MSK |
| Установка hook | Копирование в `.git/hooks` | `core.hooksPath=.githooks` + скрипт установки (образец `scripts/install_hooks.sh`) | Воспроизводимо, переживает worktree (тест WR-09 в chat-app) |
| Таймаут тестов | `pytest-timeout` | `subprocess.run(timeout=…)` | Новых зависимостей нельзя |

**Key insight:** почти всё нужное уже написано и покрыто тестами в chat-app. Ценность фазы в трёх добавках, которых там нет: страж боевой БД, строки shared/hook, смоук-скрипт. Остальное это перенос с заменой констант `CHAT_*` на `CORE_*`/`SHARED_*`.

## Runtime State Inventory

Фаза не переименовывает и не мигрирует, раздел не обязателен. Тем не менее новые артефакты оставляют состояние вне git:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Боевая `data/assistant.db` только читается (хеш, `--backup`); корневой `/opt/assistant-core/assistant.db` (544 КБ, mtime 2026-10-08, в `.gitignore` по `*.db`) происхождение неизвестно `[VERIFIED: ls -la]` | Включить оба пути в страж; не удалять (решение владельца, SCH-03 вне фазы) |
| Live service config | `systemctl cat assistant-worker`: `WorkingDirectory=/opt/assistant-core`, `TimeoutStopUSec=1min 30s`, `Restart=always`, `RestartSec=15` `[VERIFIED]` | Таймаут рестарта в скрипте >= 300 с |
| OS-registered state | `core.hooksPath` у core = `.githooks`; у shared не задан `[VERIFIED: git config]` | Установить у shared скриптом установки; гейт проверяет |
| Secrets/env vars | `TELEGRAM_BOT_TOKEN` в `.env` (имя подтверждено `.env.example`); читать значение нельзя в разговоре | Скрипт выкатки читает только этот ключ, не печатает, редактирует исключения |
| Build artifacts | `.import_linter_cache/`, `.grimp_cache/`, `.pytest_cache/` в core (в `.gitignore`) | Гейт использует `--no-cache` и `-p no:cacheprovider` |

## Common Pitfalls

### Pitfall 1: Гейт краснеет на чистом дереве из-за таймингов
**What goes wrong:** `tests/test_command_aliases.py::test_fast_intent_router_aliases` упал в полном прогоне: `assert 61.73347705043852 < 50.0` (`tests/test_command_aliases.py:30`). Три отдельных прогона файла (12 тестов) прошли за 28-64 с `[VERIFIED: запуск]`. В том же файле ещё два порога `< 250.0` (строки 181, 213) на `time.perf_counter()`.
**Why it happens:** ограничение по настенному времени на VPS 2 ГБ с работающим демоном и подкачкой (свободно ~650 МБ, swap занят ~1.9 ГБ `[VERIFIED: free -m]`).
**How to avoid:** до первого «зелёного» заявления стабилизировать: брать минимум из N замеров (`min(latency for _ in range(5))`) или `time.process_time()`, оставляя смысл «детерминированный алиас без LLM быстрее порога»; не удалять и не помечать xfail/skip (это тоже красный). Повторить полный прогон гейта не менее трёх раз подряд.
**Warning signs:** красная строка pytest с одним упавшим тестом «latency».

### Pitfall 2: Страж уронит `test_create_server_backup_archive`
**What goes wrong:** зонд (audit-hook в режиме записи в журнал, `sys.addaudithook` через плагин из scratchpad) зафиксировал единственные обращения к боевому пути: два события `open … ('r', 524288)` на `/opt/assistant-core/data/assistant.db` из `tests/test_gdrive_client.py::test_create_server_backup_archive` `[VERIFIED: probe_log.tsv]`. Причина: `GoogleDriveClient.create_server_backup_archive` жёстко использует `/opt/assistant-core/data/assistant.db`, `/opt/assistant-core/data/assistant_worker.session`, `/opt/assistant-core/.env` (`src/connectors/gdrive/client.py:185-205`) и тест проверяет `assistant.db` в архиве. Тест копирует секреты и БД в `tmp_path`.
**How to avoid:** добавить необязательный параметр (например `core_dir: str | Path = "/opt/assistant-core"`) к `create_server_backup_archive`; единственный вызов в рантайме без аргументов (`client.py:224`) остаётся прежним. Тест передаёт `tmp_path` с поддельными `data/assistant.db`, `.env`, `data/assistant_worker.session`. Правка src минимальна и поведенчески нейтральна, но это изменение `src/`, поэтому в SUMMARY отметить «рестарт не требуется».
**Warning signs:** `RuntimeError: тест пытался открыть боевую БД` в этом тесте.

### Pitfall 3: Хеш боевой БД может измениться из-за самого демона
**What goes wrong:** сервис `active` и пишет в ту же БД (коллекторы каждые 15/30 мин, табло каждые 5 мин, бот). Журнал за сутки содержит `[gmail] Error fetching Gmail messages: database is locked`, то есть реальные конкурирующие записи. Окно «до/после» в общем гейте охватывает весь прогон (минуты).
**Why it happens:** гейт доказывает «тесты не трогали БД» только косвенно.
**How to avoid:** (a) измерять «после» сразу после pytest core, а не в конце гейта; (b) при расхождении печатать `diagnostic`: `systemctl is-active assistant-worker` и mtime файла БД, но вердикт оставить КРАСНЫМ (fail-closed) с текстом «повторите прогон; основная защита это страж»; (c) страж даёт прямое доказательство: любой доступ тестов к БД упадёт до записи.
**Warning signs:** красная строка «хеш изменился» при зелёном pytest. `[ASSUMED]`: что вероятность ложного срабатывания заметна; за последние 30+ минут mtime БД не менялся (14:16:48 при проверке около 14:50 `[VERIFIED: stat]`), то есть записи не каждые 5 минут.

### Pitfall 4: ERROR в журнале штатно и часто (D-08 в буквальном виде)
**What goes wrong:** за 2026-10-09 в журнале: 2 ошибки логина LMS (`Invalid URL '/theme/switch/save': No scheme supplied`) с Traceback, 2 строки `Error in LMS submissions monitor cycle`, 1 `database is locked` (Gmail), 1 `aiogram.dispatcher … TelegramNetworkError`; за 2026-10-08 десятки таймаутов IMAP `[VERIFIED: journalctl | grep ERROR | uniq -c]`. Начальные циклы при старте включают LMS и почту, поэтому рестарт в неудачный момент даст КРАСНЫЙ смоук на полностью живом демоне.
**How to avoid:** окно ошибок = от начала инвокации до строки `Run polling for bot` (фаза запуска) плюс короткий хвост после неё (например 60 с); в отчёте для каждой ошибки печатать `logger` и усечённое сообщение (с редактированием). Вердикт по D-08 оставить строгим, но отчёт должен позволять владельцу отличить сбой внешнего сервиса (`src.collector.*`, `src.connectors.*`, `aiogram.dispatcher` сеть) от сбоя запуска (`assistant-worker`, `Traceback` в `src.main`, `ImportError`). Это вопрос владельцу, см. Open Questions 1.
**Warning signs:** красный смоук с единственной строкой `[guap] … timed out`.

### Pitfall 5: Рестарт долгий и «грязный»
**What goes wrong:** предыдущий останов закончился `State 'stop-sigterm' timed out. Killing.` → SIGKILL → `Failed with result 'timeout'` через 90 с `[VERIFIED: журнал 2026-10-08 09:29-09:30]`. Затем старт занял ~50 с до polling.
**How to avoid:** таймаут `systemctl restart` не менее 180 с, ожидание готовности (`Run polling for bot`) до ~300 с; строки останова принадлежат ПРЕДЫДУЩЕЙ инвокации и в окно ошибок нового запуска не попадают благодаря фильтру по `InvocationID`; перед рестартом запомнить старый `InvocationID`, после рестарта ждать, пока он изменится.

### Pitfall 6: «Планировщик зарегистрировал задачи» невидим при ротации журнала
**What goes wrong:** строки `Added job` пишутся один раз при старте. На долго живущей инвокации их могут вытеснить; в read-only режиме на текущем сервисе (работает с 2026-10-08 09:30) они пока есть (журнал 319 МБ).
**How to avoid:** трёхзначный результат по каждой задаче: «зарегистрирована (Added job)», «виден запуск (Running job/executed successfully)», «нет данных». Для рестарта «нет данных» = КРАСНЫЙ, для read-only режима на старой инвокации — КРАСНЫЙ с пометкой «ротация журнала?» либо ЖЁЛТЫЙ по решению планировщика (в таблице нет третьего значения «✓/✗», поэтому проще КРАСНЫЙ и повтор после рестарта).

### Pitfall 7: Адаптер cross-AI запускает не тот гейт
**What goes wrong:** блок `# ---------- gate ----------` в `/opt/chat-app/scripts/agy_cross_ai.sh` берёт `GATE=(python3 "$SCRIPT_DIR/gate.py")` и выполняет `cd "$SCRIPT_DIR/.."`, то есть всегда гейт chat-app из каталога chat-app, независимо от `--repo` `[VERIFIED: чтение адаптера]`. Для `--repo /opt/assistant-core` гейт chat-app не знает про новые строки.
**How to avoid:** `/gsd-quick` в chat-app: предпочитать `"$TOP/scripts/gate.py"` с `cd "$TOP"` (для chat-app это тот же файл), иначе откат на гейт chat-app. Безопасно: `scripts/gate.py` целевого репозитория входит в PROTECTED (`helper.py`), агент не может его изменить до запуска. Тест: sandbox из `test_agy_cross_ai.py` уже кладёт в репозиторий `scripts/gate.py` заглушку; добавить тест выбора без `AGY_GATE_CMD`.
**Warning signs:** в `gate.log` задания видна таблица chat-app.

### Pitfall 8: Хук и `ls-files` не видят неиндексированные файлы
**What goes wrong:** `security_shield --all` сканирует `git ls-files`: новые тесты shared, пока они не добавлены в индекс, не сканируются. Хук в staged-режиме на коммите отработает, но гейт «зелёный» до `git add` ничего не доказывает.
**How to avoid:** в плане: `git add` до первого запуска гейта; в тестах shared не писать литералы секретов и ключевых слов NDA (использовать сборку из частей).

### Pitfall 9: Перенос тестов миграций ломается в Phase 3
**What goes wrong:** `test_migrations.py` жёстко содержит `LATEST_SCHEMA_VERSION = "0002_pending_confirmations"` и `ALL_MIGRATIONS = ["0001_initial_schema", "0002_pending_confirmations"]` (`/opt/chat-app/backend/tests/test_migrations.py:48-49`), а Phase 3 добавляет `0003_*.sql`.
**How to avoid:** при переносе вычислять список из каталога `assistant_shared/db/migrations/*.sql` и добавить проверку префикса `[:2] == [0001, 0002]` (защита от удаления) и «подмножество» для `EXPECTED_CORE_TABLES`.

### Pitfall 10: Перенос `@pytest.mark.anyio` и тест, закрепляющий поведение Phase 2
**What goes wrong:** `test_hitl_shared.py` использует `@pytest.mark.anyio` (строки 54, 85, 112, 150), в core стоит `pytest-asyncio` с `asyncio_mode=auto` `[VERIFIED: pytest.ini]`; совместная работа двух плагинов на помеченных тестах не проверялась `[ASSUMED]`. Кроме того, `test_cr05_cli_checks_all_remotes_and_aliases` использует каталог с именем из подстроки «tydex» (`tmp_path / "tydex-work"`), на которой держится режим NDA в `audit_repository` (`auditor.py:210`, `"tydex" in str(repo_path).lower()`), а Phase 2 (SECF-01) эту подстроку убирает.
**How to avoid:** заменить `anyio`-метки на asyncio-режим shared; для теста с «tydex-work» либо перенести с пометкой в плане Phase 2 «переписать при SECF-01», либо переписать сразу на данные пространства, если API уже позволяет. Решение планировщика, вынести в Open Questions 6.

## Code Examples

### Строгий критерий pytest (из образца, без изменений)
```python
# Source: /opt/chat-app/scripts/gate.py:198-207  [VERIFIED: чтение файла]
def pytest_ok(returncode, counts, flags):
    return (
        returncode == 0
        and counts.get("tests", 0) > 0
        and counts.get("failures", 0) == 0
        and counts.get("errors", 0) == 0
        and counts.get("skipped", 0) == 0
        and not flags
    )
```
Дополнение: `_SUMMARY_WORDS = {"failed","error","errors","skipped","deselected","xfailed","xpassed"}` (`gate.py:75-77`). Итоговая строка ищется как `=`-строка с ` in `, поэтому pytest должен запускаться с `-v`, не с `-q` (при `-q` строки со знаком `=` нет; это видно в нашем прогоне с `-q`: «1 failed, 420 passed, 35 warnings in 194.67s» без `=`).

### Известные ложные срабатывания (замороженный словарь)
```python
# Source: /opt/chat-app/scripts/gate.py:60-69  [VERIFIED]
KNOWN_SHIELD_FALSE_POSITIVES = {
    "assistant-core": {("config/persona.yaml", "nda-keyword"): 3},
}   # новый гейт: ключ "assistant-shared": {} (пуст), chat-app не входит
```

### Хвост адаптера, который меняется в chat-app (GATE-05)
```bash
# Source: /opt/chat-app/scripts/agy_cross_ai.sh, блок "# ---------- gate ----------"  [VERIFIED: чтение]
# сейчас:
if [ -n "${AGY_GATE_CMD:-}" ]; then GATE=("$AGY_GATE_CMD"); else GATE=(python3 "$SCRIPT_DIR/gate.py"); fi
( cd "$SCRIPT_DIR/.." && exec "${GATE[@]}" ) < /dev/null > "$GATE_LOG" 2>&1 &
# рекомендуемая правка (эскиз): гейт целевого репозитория, откат на гейт chat-app
if [ -n "${AGY_GATE_CMD:-}" ]; then GATE=("$AGY_GATE_CMD"); GATE_DIR="$SCRIPT_DIR/.."
elif [ -f "$TOP/scripts/gate.py" ]; then GATE=(python3 "$TOP/scripts/gate.py"); GATE_DIR="$TOP"
else GATE=(python3 "$SCRIPT_DIR/gate.py"); GATE_DIR="$SCRIPT_DIR/.."; fi
( cd "$GATE_DIR" && exec "${GATE[@]}" ) < /dev/null > "$GATE_LOG" 2>&1 &
```
Заодно обновить текст SUMMARY, который сейчас фиксирует «`python3 scripts/gate.py` завершился с кодом 0» (адаптер печатает путь журнала), и строку скилла `agy-delegate/SKILL.md` («гейт покрывает только их»).

### Разбор задач планировщика из `src/main.py`
```python
# Эскиз для scripts/deploy.py (stdlib)
import ast
def expected_jobs(main_py_text: str) -> list[tuple[str, str]]:
    tree, jobs = ast.parse(main_py_text), []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_job" and node.args and isinstance(node.args[0], ast.Name)):
            job_id = next((kw.value.value for kw in node.keywords
                           if kw.arg == "id" and isinstance(kw.value, ast.Constant)), "")
            jobs.append((node.args[0].id, job_id))
    return jobs   # [(run_sentinel_cycle, "schedule_sentinel_job"), ...]
```

### Фазы смоука без TTY (D-09)
```
python3 scripts/deploy.py smoke                      # read-only: active, журнал, задачи, getMe; печатает "отправьте /help", пишет метку времени в state-файл вне репозитория
python3 scripts/deploy.py smoke --await-help         # ждёт 'Update id=… is handled' после метки (дедлайн), не требует TTY
python3 scripts/deploy.py smoke --confirm-help yes   # ответ владельца, полученный Claude через AskUserQuestion; дописывает строку в отчёт
python3 scripts/deploy.py smoke --report PATH.md     # итоговый отчёт
python3 scripts/deploy.py --backup --restart --report PATH.md   # полный цикл по "да" владельца
```
Имена флагов и подкоманд `[ASSUMED]` (на усмотрение планировщика, D-10..D-13 фиксируют только смысл).

## Состояние `/help` (D-07)

Обработчик `handle_cmd_help` (`src/notifier/bot_handler.py:426-456`) вызывает `_is_authorized`, три функции имён из кэша `current_persona()` и `self.notifier.send_message(...)`. Обращений к `self.db` нет. В `src/notifier/telegram.py` нет упоминаний `db`/`Database`/`sqlite` `[VERIFIED: grep]`. `Command("start", "help")` зарегистрирован на строке 332, универсальный `F.text` обработчик (строка 415) идёт позже и команду не перехватывает `[VERIFIED: чтение]`. Вывод: `/help` не пишет в БД, эскалация владельцу по D-07 не нужна. Оговорка: Phase 2 (PRIV-01) добавит предупреждение в текст справки; запись в БД это не вносит, но смоук-проверку «нет записи» стоит повторить при изменении обработчика.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Защита боевой БД только хешем в общем гейте (STATE.md, Blockers) | Страж audit-hook + env-переопределение + хеш | эта фаза | Нарушение видно сразу и точно, а не постфактум |
| Общий гейт chat-app проверяет core как потребитель | Собственный гейт core + shared; общий остаётся для chat-app | эта фаза | Гейт зелёный без chat-app (кроме read-only дрейфа) |

**Deprecated/outdated:**
- Формулировка `.claude/CLAUDE.md:63` («`python3 /opt/chat-app/scripts/gate.py` (external, until assistant-core has its own)») и `CLAUDE.md:47` («Run Quality Gate (until assistant-core has its own)») подлежат замене на `python3 scripts/gate.py`. Аналогично раздел «Quality Gate (shared, read-only description)» в `.planning/codebase/TESTING.md`.
- Комментарий в общем гейте про снятие записи персоны правилом «Фазы 4 (SEC-01)» устарел для новой нумерации; в новом гейте не копировать, ссылаться на D-17.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| python3 | гейт, деплой-скрипт | ✓ | 3.12.3 | — |
| `/opt/assistant-core/.venv` (pytest, lint-imports, assistant_shared) | pytest core/shared, shield | ✓ | pytest 9.1.1 | — |
| git | shield, hook, дрейф | ✓ | 2.43.0 | — |
| systemctl / journalctl | смоук | ✓ (сервис `active`, MainPID 295112, NRestarts 0) | systemd host | — |
| curl, jq | не нужны скрипту | ✓ | — | — |
| CLI `sqlite3` | не нужен | ✗ | — | модуль `sqlite3` stdlib (D-11 так и сформулирован) |
| `/opt/chat-app/backend/tests/{synthetic_persona,persona_tokens}.py` | дрейф | ✓ | идентичны core | при отсутствии КРАСНЫЙ (D-16) |
| Telegram API (`getMe`) | смоук | `[ASSUMED]` доступен (бот работает; токен читать нельзя, не проверялось) | — | журнал `Run polling for bot` |
| Диск | резервная копия | ✓ 7.8 ГБ свободно, БД 8.4 МБ | — | — |
| RAM | гейт | ограничено: ~650 МБ доступно | — | запускать строго последовательно, без параллельных пулов |

**Missing dependencies with no fallback:** none
**Missing dependencies with fallback:** CLI `sqlite3` (использовать stdlib).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode = auto`) `[VERIFIED: pytest.ini, pip list]` |
| Config file | `/opt/assistant-core/pytest.ini`; для shared создать `[tool.pytest.ini_options]` в `/opt/assistant-shared/pyproject.toml` (Wave 0) |
| Quick run command | `/opt/assistant-core/.venv/bin/pytest tests/test_gate.py tests/test_live_db_guard.py tests/test_deploy_script.py -p no:cacheprovider -q` |
| Full suite command | `python3 scripts/gate.py` (содержит pytest core 421+ тестов ~3-4 мин, pytest shared, lint, shield, дрейф, хеш) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GATE-01 | `pytest_ok` отвергает 0 тестов, failed, error, skipped, xfailed, xpassed, deselected | unit | `pytest tests/test_gate.py -k pytest_ok -q` | ❌ Wave 0 |
| GATE-01 | Красные случаи на мини-проектах (сломанный, skip, xfail, xpass, deselected через `addopts -k`, 0 тестов) дают `CheckResult(ok=False)` | integration (подпроцесс pytest в tmp) | `pytest tests/test_gate_red_cases.py -q` | ❌ Wave 0 |
| GATE-01 | Гейт не обрывается: сбой шага = красная строка, остальные строки есть | unit | `pytest tests/test_gate.py -k safe_step -q` | ❌ Wave 0 |
| GATE-01 | Рендер таблицы по-русски, `ИТОГ: ЗЕЛЁНЫЙ` rc 0 / `ИТОГ: КРАСНЫЙ` rc≠0; пустой список = красный | unit | `pytest tests/test_gate.py -k render -q` | ❌ Wave 0 |
| GATE-02 | Страж бросает на `open`, `sqlite3.connect`, `aiosqlite.connect`, `file:`-URI, относительный путь к боевому файлу | unit | `pytest tests/test_live_db_guard.py -q` | ❌ Wave 0 |
| GATE-02 | `load_dotenv(override=True)` (эмуляция) не перебивает `ASSISTANT_DB_PATH_OVERRIDE`; без переменной путь прежний | unit | `pytest tests/test_live_db_guard.py -k override -q` | ❌ Wave 0 |
| GATE-02 | `test_create_server_backup_archive` не касается боевых файлов | unit | `pytest tests/test_gdrive_client.py -q` | ✅ (требует правки) |
| GATE-02 | Хеш до/после: равенство, `None`, расхождение; WAL-checkpoint не меняет хеш | unit | `pytest tests/test_gate.py -k db_ -q` | ❌ Wave 0 |
| GATE-03 | Перенесённые тесты shared проходят | integration | `cd /opt/assistant-shared && /opt/assistant-core/.venv/bin/pytest tests -p no:cacheprovider -v` | ❌ Wave 0 |
| GATE-03 | Hook блокирует синтетический секрет и `.env`, пропускает чистый коммит; установщик (worktree, нет файла, чужой hooksPath) | integration | `…/pytest tests/test_pre_commit_hook.py` в shared | ❌ Wave 0 |
| GATE-03 | Строки shared (pytest, shield, hook) присутствуют в таблице гейта отдельно | unit | `pytest tests/test_gate.py -k shared -q` | ❌ Wave 0 |
| GATE-04 | Дрейф: совпадение зелёное, различие и отсутствие файла красные; обе пары проверяются | unit | `pytest tests/test_gate.py -k drift -q` | ❌ Wave 0 |
| GATE-04 | Замороженный список: новая находка и устаревшая запись красные, текст находки не печатается | unit | `pytest tests/test_gate.py -k shield -q` | ❌ Wave 0 |
| GATE-05 | Адаптер выбирает `$TOP/scripts/gate.py` без `AGY_GATE_CMD`; красный гейт откатывает патч | integration (chat-app, `/gsd-quick`) | `/opt/chat-app/backend/.venv/bin/pytest backend/tests/test_agy_cross_ai.py` | ✅ (дополнить) |
| GATE-05 | Пробный прогон `agy_cross_ai.sh --repo /opt/assistant-core` печатает ЗЕЛЁНЫЙ в `gate.log` | manual-like e2e (Claude запускает, ~агент) | см. Wave плана | — |
| OPS-01 | Без `--restart` команда `systemctl restart` не вызывается (фейковый раннер записывает вызовы) | unit | `pytest tests/test_deploy_script.py -k no_restart -q` | ❌ Wave 0 |
| OPS-01 | Разбор журнала: окно старта, ERROR/CRITICAL/Traceback = красный, WARNING только в отчёте, редактирование e-mail/токенов | unit | `pytest tests/test_deploy_script.py -k journal -q` | ❌ Wave 0 |
| OPS-01 | `ast`-разбор `src/main.py` даёт 10 пар (функция, id) сейчас; `Added job` сопоставляется | unit | `pytest tests/test_deploy_script.py -k jobs -q` | ❌ Wave 0 |
| OPS-01 | `--backup`: копия через `mode=ro` во временный каталог, целостна, права 0600 | unit (tmp БД) | `pytest tests/test_deploy_script.py -k backup -q` | ❌ Wave 0 |
| OPS-01 | Read-only смоук на живом сервисе (без рестарта) → отчёт в VERIFICATION.md | manual-only: нужен реальный сервис и сообщение владельца боту | `python3 scripts/deploy.py smoke --report …` | — |

### Sampling Rate
- **Per task commit:** быстрый набор из трёх новых тестовых файлов (секунды); для shared — `pytest tests` в `/opt/assistant-shared`.
- **Per wave merge:** `python3 scripts/gate.py` целиком.
- **Phase gate:** три подряд зелёных прогона гейта (из-за таймингового теста) + read-only смоук на текущем сервисе + пробный прогон адаптера, затем `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/test_gate.py`, `tests/test_gate_red_cases.py`, `tests/test_live_db_guard.py`, `tests/test_deploy_script.py` в core
- [ ] страж в `tests/conftest.py` и правка `src/config.py` (GATE-02)
- [ ] правка `create_server_backup_archive` + `tests/test_gdrive_client.py`
- [ ] стабилизация таймингового теста (Pitfall 1)
- [ ] `/opt/assistant-shared/tests/`, `pyproject.toml` с pytest-секцией, `scripts/security_shield.py`, `.githooks/pre-commit`, `scripts/install_hooks.sh`
- [ ] Установка hook shared (`core.hooksPath`) и первый коммит в shared уже проходит через hook
- [ ] Фреймворк ставить не нужно

## Security Domain

`security_enforcement` включён (config.json: `security_enforcement: true`, `security_asvs_level: 1`).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (владелец локально, нет нового входа) | — |
| V3 Session Management | no | — |
| V4 Access Control | yes (минимально) | Рестарт только флагом после «да»; деплой-скрипт и гейт от root локально; отчёт и резервная копия с правами 0600/0700 |
| V5 Input Validation | yes | Журнал и вывод подпроцессов это недоверенный ввод: разбор регулярными выражениями, никогда `shell=True`, аргументы списком; `--report` путь нормализовать (запись только в заданный файл, не перезаписывать существующие чужие файлы без явного пути) |
| V6 Cryptography | no | SHA-256 только для сравнения целостности (`hashlib`) |
| V7 Error handling & Logging | yes | Не печатать исключения `urllib` с URL токена, не печатать сырой вывод shield/journald, редактировать e-mail и токены |
| V8 Data Protection | yes | Резервная копия вне git, каталог 0700, файл 0600; в отчёт не попадает содержимое сообщений |
| V14 Configuration | yes | `.env` читается только для ключа `TELEGRAM_BOT_TOKEN`, значение не логируется; гейт `.env` не читает вовсе |

### Known Threat Patterns for stdlib-скрипты + systemd + git hook

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Утечка токена бота через текст исключения (`urllib` кладёт URL в сообщение) | Information Disclosure | Печатать только класс исключения и HTTP-код; редактор по шаблону токена Telegram |
| Внедрение команд через содержимое журнала/имена файлов | Tampering | Подпроцессы списком аргументов, без shell; данные журнала только парсятся |
| Незапрошенный рестарт/откат сервиса | Elevation / DoS | Флаг `--restart` не по умолчанию; автооткат отсутствует (D-12); тест «без флага рестарт не вызывается» |
| Секреты и содержимое NDA в отчётах или кэше | Information Disclosure | Нормализация (путь, вид, число), отчёт без текста сообщений; артефакты в tmp с 0700 и удалением (`shutil.rmtree`) |
| Обход стража через `file:` URI, относительный путь, `-wal`/`-shm` | Tampering | Нормализация URI и `realpath`, четыре суффикса, тест на каждую форму |
| Запись агента в гейт/hook | Tampering | `scripts/gate.py`, `.githooks/`, `scripts/security_shield.py` уже в PROTECTED адаптера; эти файлы правит только Claude |
| Ложный ЗЕЛЁНЫЙ при пропущенных проверках | Repudiation | Fail-closed: отсутствие файла/бинарника/каталога, 0 тестов, `code 1 без находок` = красный |

## Project Constraints (from CLAUDE.md)

Директивы из `/opt/assistant-core/CLAUDE.md` и `.claude/CLAUDE.md`, обязательные для планировщика:
- Боевую БД `data/assistant.db` не открывать и не менять при разработке и тестах; сервисы заморожены; рестарт `assistant-worker` только по явному разрешению владельца со смоуком.
- Тесты проходят на 100%; skip, xfail, deselected делают гейт красным. Новые зависимости только с одобрения владельца.
- Стек: Python 3.12, async-first (I/O через `aiosqlite`, `httpx`/`aiohttp`); для скриптов-инструментов, выполняемых вне event loop, допустим синхронный stdlib (как существующий гейт).
- Логи: `logging.getLogger(__name__)`, ленивое форматирование `%s`, без `print` в `src/`; скрипты CLI могут печатать (как `security_shield.py`). Не логировать секреты.
- Профильные значения владельца не хардкодить (сканер `tests/test_hardcode_scanner.py` с пустым baseline); `scripts/` сканируется, `tests/`, `docs/`, `config/`, `.planning/` в allowlist.
- Язык: всё, что видит пользователь, по-русски; комментарии и коммиты на английском или русском, в стиле окружающего файла.
- GSD: правки только через GSD-команды; маршрутизация agy: security/HITL/гейт и правки 1-3 файлов остаются у Claude; `cross_ai: true` недопустим для планов, трогающих `scripts/gate.py`, `.githooks/`, `scripts/security_shield.py`, `.importlinter`.
- Фаза закрывается только с SUMMARY.md и VERIFICATION.md, где проверена достижимость из рантайма (для этой фазы: гейт запущен командой владельца; смоук-скрипт запущен на живом сервисе read-only).
- Git: коммиты прямо в `main`, без worktree; коммиты в `/opt/assistant-shared` делаются в его отдельном репозитории, коммиты chat-app только через `/gsd-quick` там.
- Узлы chat-app read-only для этой фазы, кроме одной правки адаптера (D-15).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Имя переменной `ASSISTANT_DB_PATH_OVERRIDE` и форма правки `src/config.py` (захват до `load_dotenv`) подходят; в боевом `.env` такой переменной нет | Pattern 2 | Если переменная окажется в `.env`, рантайм пойдёт на другую БД; проверить владельцем/`grep -c` по имени ключа в `.env.example` (имя там отсутствует) |
| A2 | `-o xfail_strict=true` в гейте безопасен для всех 421 тестов | Pattern 3 | Если какой-то тест неявно ксфейлится, гейт покраснеет; проверить прогоном |
| A3 | `anyio`-метки и `pytest-asyncio` (auto) конфликтуют или дублируют обработку | Pitfall 10 | Если нет, достаточно оставить метки; конвертация метки всё равно безопасна |
| A4 | Расхождение хеша БД из-за записи демона возможно и заметно | Pitfall 3 | Если невозможно, диагностика лишняя, но безвредная |
| A5 | `getMe` с VPS достижим по токену из `.env` | Environment | Если нет доступа, смоук опирается на строку журнала `Run polling for bot` |
| A6 | Имена флагов/подкоманд скрипта выкатки, каталог резервных копий `/var/backups/assistant-core` | Code Examples, Runtime State | Низкий: выбор планировщика (Claude's Discretion) |
| A7 | Чтение БД в `mode=ro` на WAL-базе без `-shm` может создать вспомогательные файлы в `data/` | Pitfall 3 | Не проверялось (БД не открывалась); подтвердить на первом реальном прогоне гейта и записать в SUMMARY |
| A8 | Полный гейт укладывается примерно в 5-6 минут на загруженной VPS; `cross_ai_timeout: 1200` достаточно для агента + гейта | Pattern 3, GATE-05 | При превышении поднять `cross_ai_timeout` в `.planning/config.json` (это и есть возможная правка config.json) |
| A9 | Окно ошибок старта: от начала инвокации до `Run polling for bot` плюс ~60 с | Pitfall 4 | Слишком короткое пропустит ошибку, слишком длинное поймает штатные сбои коллекторов |

## Open Questions

1. **Строгость D-08 при штатных внешних сбоях**
   - Что известно: за сутки в журнале ERROR-строки от LMS-логина (с Traceback), IMAP, `database is locked`, сети aiogram; начальные циклы старта включают LMS и почту.
   - Что неясно: владелец принимает КРАСНЫЙ в таких случаях или хочет классификацию «внешний сбой».
   - Рекомендация: реализовать D-08 строго и печатать у каждой ошибки логгер и усечённое сообщение; вердикт остаётся КРАСНЫМ, решение о повторе принимает владелец (D-12 уже предполагает стоп без автооткатa). Если планировщик захочет смягчить, задать вопрос владельцу опросом, а не менять молча.
2. **Стабилизация таймингового теста**
   - Что известно: порог 50 мс упал при 61.7 мс под нагрузкой; соседние пороги 250 мс.
   - Рекомендация: минимум из N замеров или `process_time`; не снижать смысл теста и не использовать skip/xfail.
3. **Правка `create_server_backup_archive`** (изменение `src/`, рантайм без рестарта): параметр каталога либо переписывание теста через патч `os.path.exists`/константы. Рекомендация: параметр с прежним значением по умолчанию.
4. **Окно хеша БД:** брать «после» сразу после pytest core; при расхождении диагностика (сервис active, mtime), вердикт КРАСНЫЙ.
5. **Дублирование `scripts/security_shield.py` в shared:** D-04 требует «тот же security_shield»; рекомендация: копия тонкой обёртки (15 строк), синхронизацию дрейфа не проверять (не требуется), отметить в SUMMARY.
6. **Тесты shared, закрепляющие поведение, которое меняет Phase 2** (`tmp_path / "tydex-work"` в CLI-тесте NDA, литерал личного аккаунта в `test_security_shared.py`): решить при переносе и записать пометку для Phase 2.
7. **Порядок пробного прогона адаптера:** адаптер отказывает при грязном дереве вне `.planning/` (exit 10), поэтому trial-прогон делать последним, после коммита всех правок и правки адаптера в chat-app; для него нужен тривиальный план с `files` в незащищённом пути (например документ в `docs/`).

## Sources

### Primary (HIGH confidence)
- `/opt/chat-app/scripts/gate.py` (582 строки, прочитан целиком) - образец гейта
- `/opt/chat-app/scripts/agy_cross_ai.sh` (прочитан целиком) - контракт адаптера, PROTECTED, блок гейта
- `/opt/chat-app/backend/tests/{test_migrations,test_hitl_shared,test_security_shared,test_shield_regressions,test_shield_parity,test_pre_commit_hook,test_gate,conftest}.py` - источники переносимых тестов
- `/opt/assistant-core/src/config.py`, `src/main.py:556-860`, `src/notifier/bot_handler.py:297-456`, `src/connectors/gdrive/client.py:185-224`, `src/storage/db.py:15-60`, `src/persona/seed.py`, `.githooks/pre-commit`, `scripts/install_hooks.sh`, `scripts/security_shield.py`, `.importlinter`, `pytest.ini`
- `/opt/assistant-shared/` (дерево, `pyproject.toml`, `db/connection.py`, `security/{patterns,runner,auditor}.py`)
- Запуски в этой сессии: полный pytest core с зондом audit-hook (421 тест, 1 упал), `lint-imports`, `security_shield --all` для core и shared, `sha256sum` копий персоны, эксперимент с audit-hook (`sqlite3`, `aiosqlite`, URI), `journalctl -u assistant-worker` (read-only), `systemctl cat/show`, `free -m`, `df`
- `/opt/assistant-core/.venv/lib/python3.12/site-packages/aiogram/dispatcher/dispatcher.py:150-182,380` - формат строк журнала

### Secondary (MEDIUM confidence)
- `.planning/codebase/TESTING.md`, `CONVENTIONS`, `ROADMAP.md` (Phase 1), `REQUIREMENTS.md`, `STATE.md`

### Tertiary (LOW confidence)
- Нет внешних веб-источников: исследование опиралось на код и запуск, внешний поиск не потребовался. Поведение `sqlite3` read-only в WAL (A7) и совместная работа плагинов anyio/pytest-asyncio (A3) не проверялись и помечены `[ASSUMED]`.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - всё уже стоит в venv, версии сняты командой
- Architecture: HIGH - образец гейта прочитан целиком, зонды выполнены
- Pitfalls: HIGH для 1-7 (воспроизведены/взяты из реального журнала), MEDIUM для 8-10
- Смоук и рестарт: MEDIUM - рестарт не выполнялся (запрещено), поведение выведено из журнала прошлого рестарта

**Research date:** 2026-10-09
**Valid until:** 2026-11-08 (стабильные инструменты; журнальные примеры и базовый счёт тестов устареют быстрее, пересчитать перед планированием, если код менялся)
