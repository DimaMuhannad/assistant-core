# Phase 5: Ретро-верификация v2.0 - Research

**Researched:** 2026-10-18
**Domain:** верификация достижимости требований из рантайма (статическая трасса, read-only пробы, тесты с реальным входом). Код не меняется.
**Confidence:** HIGH для фактов по коду (прочитано в этой сессии, см. провенанс ниже); MEDIUM для предварительных вердиктов (окончательные вердикты выносятся в VERIFICATION.md); LOW для пунктов из раздела Assumptions Log.

**Провенанс в этом документе:** `[VERIFIED: путь:строки]` означает, что фрагмент открыт в этой сессии (Read, cat, sed) и цитата дана. `[GREP]` означает, что строка найдена поиском, а определение целиком не открывалось; в фазе исполнения такой факт перед вердиктом надо прочитать. `[ASSUMED]` означает вывод или гипотезу без проверки.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Метод: статическая трасса вызовов от `src/main.py` или хэндлера бота до функции плюс тест, который входит через реальный вход (хэндлер бота) на временной БД с заглушками внешних API. Одного юнит-теста недостаточно.
- **D-02:** Внешние сервисы: разрешены живые вызовы только для чтения (например `getMe`, чтение календаря). Запрет остаётся жёстким: содержимое NDA-пространств не уходит ни в какую внешнюю LLM, записи во внешние системы запрещены.
- **D-03:** Read-only смоук `python3 scripts/deploy.py` на работающем `assistant-worker` включается как доказательство (меню команд UXQ-01, задачи планировщика). Без `--restart` и `--backup`, без записи в боевую БД.
- **D-04:** Порог passed: если требование достижимо, но покрыто только трассой без теста с реальным входом, ставится `passed` с пометкой «доказано трассой, без e2e-теста». Слабое покрытие уходит в бэклог как улучшение, а не как gap.
- **D-05:** 6 файлов лежат в папке фазы 5: `V2-04-VERIFICATION.md` … `V2-09-VERIFICATION.md`, плюс итоговая сводная таблица 20 требований. Каждый файл ссылается на исходную фазу chat-app (`/opt/chat-app/.planning/milestones/v2.0-phases/0N-*`, только чтение).
- **D-06:** Запись требования — таблица: требование → статус → точка входа в рантайме (file:line) → тест или команда проверки → пометка «трасса/e2e».
- **D-07:** `test_concurrent_write_two_processes` прогоняется 30 раз подряд в двух режимах: на свободной системе и под нагрузкой (вместе с полным pytest). Учитывать VPS 2 ГБ RAM.
- **D-08:** Критерий: 0 сбоев из 30 = stable. Любой сбой = gap с частотой и текстом ошибки. skip/xfail запрещены гейтом, тест не скрывать.
- **D-09:** Gap по серьёзности: безопасность, HITL, NDA, целостность данных → новое требование с ID в REQUIREMENTS.md, привязка к будущей фазе. Улучшения и косметика → запись бэклога 999.x.
- **D-10:** Если gap касается безопасности (HITL, Air-Gap), в этой фазе он только записывается, без остановки и без внеочередного исправления. Владелец увидит его в итоговой сводке.
- **D-11:** agy (flash, только через `/opt/chat-app/scripts/agy_task.sh run --repo /opt/assistant-core --mode read`) собирает инвентаризацию точек входа по требованиям. Claude выносит вердикты, прогоняет тесты (в jail нет `.venv`, БД, git), пишет VERIFICATION.md и запускает гейт.

### Claude's Discretion

- Разбиение на планы и волны, порядок проверки фаз v2.0, формат сводной таблицы.
- FIN-01 подтверждается формально: `HARDCODE_BASELINE` пуст в обоих репозиториях.
- UXQ-02 проверяется на хранении, перенесённом в `0003` (Phase 3).

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope. Исправление найденных gaps планируется отдельно.

</user_constraints>

<phase_requirements>
## Phase Requirements

В ROADMAP и CONTEXT сказано «20 требований», но список содержит 20 ID вместе с VER-01. Проверяемых требований 19: DAT-02, DAT-03, DAT-04, SEC-01, SEC-02, SEC-03, HIT-01, ISO-01, ISO-02, ISO-03, ISO-04, FIN-01, ACT-01, ACT-02, ACT-03, ACT-04, UXQ-01, UXQ-02, UXQ-04. VER-01 — это сама фаза (VER-01 отмечен как Pending в REQUIREMENTS.md).

| ID | Описание (кратко; полный текст в REQUIREMENTS.md и в исходном v2.0) | Что даёт исследование |
|----|-----------------------------------------------------------------------|------------------------|
| VER-01 | Для фаз 4–9 v2.0 есть VERIFICATION.md по факту | Раздел «Структура артефактов» и маппинг фаз |
| DAT-02 | Путь к БД из настроек в обоих процессах | Точки конфигурации, проба пути (раздел «Пробы рантайма») |
| DAT-03 | WAL и busy_timeout; конкурентная запись двух процессов | Протокол 30 прогонов (раздел «Нестабильный тест») |
| DAT-04 | Тесты chat-app не трогают /opt/assistant-core | Проба strace (раздел «Пробы») |
| SEC-01 | Единая библиотека безопасности в assistant-shared у обоих репозиториев | Импортёры библиотеки |
| SEC-02 | security_shield тонкая обёртка без дрейфа | Сравнение трёх обёрток |
| SEC-03 | pre-commit hook установлен воспроизводимо и блокирует синтетический секрет | Проба в tmp-репозитории |
| HIT-01 | ConfirmationStore, @requires_confirmation, resume_action, миграция pending_confirmations | Декоратор отсутствует (см. разбор) |
| ISO-01 | Ключи Gemini в контексте персоны, глобальный ключ не мутируется | Тест test_key_rotator_no_global_config_mutation |
| ISO-02 | Маскировка тела, snippet и вложений NDA-почты для LLM работает | Метаданные NDA уходят в LLM (разбор) |
| ISO-03 | Zero-Trust scopes коннекторов | MissingScopeError в composition |
| ISO-04 | Нет cross-talk между персоной по умолчанию и синтетической | test_multi_persona_concurrency_isolation |
| FIN-01 | HARDCODE_BASELINE пуст в обоих репозиториях | Baseline пуст; allowlist сканера не пуст (разбор) |
| ACT-01 | Function calling: три инструмента вызывают бэкенд и возвращают function_response | Расхождение с HITL-дизайном (разбор) |
| ACT-02 | Промпт запрещает утверждать выполнение без tool_result; уточняющий вопрос | Текст промпта отличается от требования |
| ACT-03 | HITL-карточка с инлайн-кнопками; действие только после нажатия | Callbacks и resume_action |
| ACT-04 | Интенты calendar_schedule, create_reminder, draft_reply в FastIntentRouter | Список action и ветка маршрутизации |
| UXQ-01 | Меню команд строится из коннекторов персоны, обновляется при подключении и отключении | Обновление есть при старте и смене видимости; при подключении/отключении нет (ONB-02) |
| UXQ-02 | Алиасы, переименование и скрытие команд из чата; хранение в 0003 | Миграция 0003 и команды чата |
| UXQ-04 | Edge cache < 250 мс, телеметрия 👍/👎, проактивные алерты коннекторов | Алерты не имеют вызовов (разбор) |

</phase_requirements>

## Summary

Фаза проверяет по факту 19 требований, перенесённых из v2.0 без проверки. Исследование сопоставило каждое требование с исходной фазой chat-app, точкой входа в рантайме, кодом, тестами и способом доказательства. Код не менялся. Рантайм не трогался.

Предварительные вердикты (окончательные выносятся в VERIFICATION.md):

- **passed (предварительно), 10:** DAT-04, SEC-01, SEC-02 (с оговоркой), ISO-01, ISO-02 (в объёме формулировки v3), ISO-03, ISO-04 (нужен прогон), ACT-03, ACT-04, UXQ-02.
- **gap, 3:** HIT-01 (декоратор `@requires_confirmation` отсутствует; подтверждение очистки диалога выполняется без `resume_action`), UXQ-01 (меню не обновляется при подключении и отключении коннекторов, это ONB-02), UXQ-04 (проактивные алерты коннекторов определены, но никто их не вызывает).
- **Открыто, зависит от пробы или прогона, 3:** DAT-02 (фактический путь БД chat-app), DAT-03 (30 прогонов; по истории ожидается gap), SEC-03 (проба hook в tmp-репозитории).
- **Нужно решение владельца, 3:** FIN-01 (формально пройден, но allowlist сканера не пуст), ACT-01 и ACT-02 (спецификация требует function_response и tool_result, а дизайн HITL-first возвращает карточку подтверждения).

Важная находка по безопасности (D-10: только записать): метаданные NDA-почты (отправитель, тема, дата) передаются во внешнюю LLM в трёх путях диалога. Тело, snippet и вложения маскируются. Это совпадает с оговоркой NDAM-01 в v3, но противоречит исходному тексту ISO-02 в v2.0 («метаданные обрабатываются только локальным кодом») и ядру ценности проекта.

**Primary recommendation:** планировать фазу тремя волнами. Волна 1: механические пробы (маппинг точек входа, strace DAT-04, проба hook SEC-03, пути БД DAT-02). Волна 2: 30 прогонов DAT-03 в двух режимах и прогон целевых тестов ISO/ACT/UXQ. Волна 3: шесть V2-0N-VERIFICATION.md, сводка, фазовые 05-SUMMARY.md и 05-VERIFICATION.md, записи gap в REQUIREMENTS.md и ROADMAP.md (Backlog). Вопросы из раздела «Открытые вопросы» задать владельцу через опрос до волны 3.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Конфигурация пути БД (DAT-02) | API / Backend (процесс assistant-worker, chat-app) | Database / Storage | Путь задаётся настройками процесса, БД общая |
| WAL и busy_timeout (DAT-03) | Database / Storage | — | Фабрика соединений в assistant-shared |
| Security-библиотека (SEC-01/02) | Database / Storage (shared-библиотека) | API / Backend (обёртки, Security Tile) | Один код на оба репозитория |
| HITL-подтверждение (HIT-01, ACT-03) | API / Backend (bot handler) | Database / Storage (pending_confirmations) | Подтверждение приходит из Telegram-бота, состояние в БД |
| Air-Gap NDA (ISO-02) | API / Backend (brain, секретарь) | — | Маскировка перед LLM-вызовом |
| Scopes коннекторов (ISO-03) | API / Backend (composition root) | — | Фабрики в src/composition.py |
| Function calling секретаря (ACT-01/02) | API / Backend (brain/secretary_dialog) | — | Инструменты объявлены в brain, исполняются через bot handler |
| Меню и команды бота (UXQ-01/02) | API / Backend (bot handler) | Database / Storage (0003) | Telegram Bot API и настройки команд в БД |
| Edge cache, телеметрия, алерты (UXQ-04) | API / Backend (bot handler) | Database / Storage (dialog_feedback_log) | Кэш в памяти процесса, телеметрия в БД |

## Standard Stack

Новых пакетов фаза не добавляет. Используется то, что уже установлено.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | 9.1.1 | Прогон тестов assistant-core и chat-app | Проверено: `pytest --version` в обеих venv выводит 9.1.1 |
| pytest-asyncio | в requirements.txt (>=0.23.0) | Асинхронные тесты | `pytest.ini`: `asyncio_mode = auto` [VERIFIED: /opt/assistant-core/pytest.ini] |
| strace | системный (/usr/bin/strace) | Доказательство того, что процесс не открывал путь (DAT-04, изоляция БД) | Проверено: `command -v strace` вернул /usr/bin/strace |
| journalctl, systemctl show | системные | Read-only данные рантайма | Оба входят в белый список `ensure_read_only` в scripts/deploy.py |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| scripts/deploy.py | в репозитории | Read-only смоук assistant-worker | Без `--restart` и `--backup` |
| scripts/gate.py | в репозитории | Итоговый гейт ЗЕЛЁНЫЙ/КРАСНЫЙ | Один раз в конце фазы |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| strace для DAT-04 | ручной аудит-хук внутри pytest | strace не требует правок тестов chat-app; хук потребовал бы изменения chat-app, что запрещено |
| Пробы в scratchpad | Новые тесты в tests/ репозиториев | Новые тесты в репозитории противоречат «код не правим»; см. раздел «Wave 0» |

**Version verification:** версии установленных инструментов проверены в этой сессии (pytest 9.1.1 в обеих venv). Версии библиотек из requirements.txt не проверялись.

## Package Legitimacy Audit

Фаза не устанавливает внешних пакетов. Аудит не требуется. Все инструменты (pytest, strace, journalctl) уже установлены на VPS.

## Architecture Patterns

### Метод доказательства (D-01, D-04, D-06)

```
Требование (REQUIREMENTS.md)
   -> точка входа: src/main.py (scheduler / startup) или callback/команда bot_handler
      -> статическая трасса (grep + чтение функций, file:line)
         -> тест с реальным входом на временной БД (ASSUMED: в scratchpad, см. Wave 0)
            -> метка: «трасса/e2e» (D-04)
```

Каждая строка VERIFICATION.md (D-06): требование → статус → точка входа file:line → тест или команда → пометка «трасса/e2e».

### Структура артефактов (VER-01, D-05)

Папка: `/opt/assistant-core/.planning/phases/05-retro-verifikatsiya-v2-0/`

| Файл | Исходная фаза chat-app (только чтение) | Требования фазы 5 |
|------|----------------------------------------|-------------------|
| V2-04-VERIFICATION.md | `/opt/chat-app/.planning/milestones/v2.0-phases/04-vladelets-shemy-bd-i-obschaya-biblioteka-bezopasnosti/` | DAT-02, DAT-03, DAT-04, SEC-01, SEC-02, SEC-03 |
| V2-05-VERIFICATION.md | `.../05-edinyy-hitl-primitiv/` | HIT-01 (HIT-02..04 вне области, см. 999.2) |
| V2-06-VERIFICATION.md | `.../06-gotovnost-k-multitenantnosti/` | ISO-01, ISO-02, ISO-03, ISO-04, FIN-01 |
| V2-07-VERIFICATION.md | `.../07-git-istochniki-i-dashbordy-notion/` | Нет требований из списка фазы 5 (см. ниже) |
| V2-08-VERIFICATION.md | `.../08-ispolnitelnyy-kontur-tool-calling/` | ACT-01, ACT-02, ACT-03, ACT-04 |
| V2-09-VERIFICATION.md | `.../09-dinamicheskoe-menyu-i-interfeys/` | UXQ-01, UXQ-02, UXQ-04 (UXQ-03 вне области) |

**Фаза 07.** В списке фазы 5 нет ни одного требования фазы 07 (GIT и NTN). В v3 эти требования закрыты фазой 4 v3, у которой есть `04-VERIFICATION.md` со статусом passed и override по GIT-01 [VERIFIED: /opt/assistant-core/.planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-VERIFICATION.md:1-6, строки 115-118]. Поэтому V2-07 должен сказать «нет требований фазы 5, покрытие см. 04-VERIFICATION.md (v3)» и не быть пустым.

**Фазы 04–09 v2.0 в chat-app не имеют собственных VERIFICATION.md.** Проверено: в каталогах 04–09 есть PLAN, SUMMARY, CONTEXT, RESEARCH, VALIDATION (у 08 и 09 VALIDATION нет). Ссылки в V2-0N файлах идут на эти артефакты.

**Фазовая гигиена (CLAUDE.md, раздел 5).** Фаза закрывается только с SUMMARY.md и VERIFICATION.md в том же запуске, а VERIFICATION должна проверять достижимость из рантайма. Значит, помимо шести V2-0N-файлов, планировщик обязан включить `05-SUMMARY.md` и `05-VERIFICATION.md` фазы 5 (сводка 19 требований).

**Образец формата:** `/opt/assistant-core/.planning/phases/03-vladenie-shemoy-bd/03-VERIFICATION.md` (frontmatter `phase`, `verified`, `status`, `score`, `covered_files`, `gaps`) и `04-VERIFICATION.md`.

### Точки входа рантайма (для трасс)

- Старт и планировщик: `src/main.py`. `Database(config.SQLITE_DB_PATH)` на строке 646, лог `Database initialized at %s` на строке 648 [VERIFIED: src/main.py:646-648]. Регистрация задач `scheduler.add_job` начинается около строки 807 [VERIFIED: grep]. Меню команд: `await bot_handler.setup_bot_commands()` на строках 700 и 932 [VERIFIED: src/main.py:700, 932].
- Бот: `EmailBotHandler` в `src/notifier/bot_handler.py:124`. Callbacks регистрируются в блоке строк 394–423 [VERIFIED: grep строк 394–423].
- Секретарь: `src/brain/secretary_dialog.py`, функции function calling в строках 712–822 [VERIFIED: sed 690–835].
- Композиция: `src/composition.py`, фабрики `default_*` [VERIFIED: cat src/composition.py].

### Anti-Patterns to Avoid

- **Вердикт по зелёному юнит-тесту.** Тест без входа через бот или main не доказывает достижимость (D-01).
- **Чтение `.env` для проверки пути.** Скрипты и агенты не читают `.env` (хук). Путь проверяется через журнал или через `systemctl show` без вывода Environment.
- **Запись в репозиторий chat-app.** pytest по умолчанию пишет `.pytest_cache` и `__pycache__` в дерево. Нужно `-p no:cacheprovider` и `PYTHONDONTWRITEBYTECODE=1`.
- **Вывод `systemctl show ... -p Environment`.** Строка Environment может содержать секреты.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Проверка, что процесс не открывал БД | Свой аудит-хук в тестах chat-app | `strace -f -e trace=openat` | Не требует правок репозитория; дает доказательство от ОС |
| Проверка меню команд | Новый скрипт вызова Telegram API | Журнал старта: строка `Successfully registered` и read-only journalctl | getMe в deploy.py не проверяет меню; журнал уже пишется кодом |
| Гейт качества | Ручной подсчёт тестов | `python3 scripts/gate.py` | Гейт сам запрещает skip, xfail и deselected |
| Учёт gap | Новый формат записи | Формат REQUIREMENTS.md и ROADMAP.md Backlog (раздел «Формат записей gap») | Совместимость с существующими записями |

**Key insight:** D-03 предполагает, что `deploy.py` проверяет меню команд. Это не так. Скрипт проверяет сервис, журнал, окно ошибок, задачи планировщика по журналу «Added job» и `getMe`. Меню в нём не проверяется [VERIFIED: scripts/deploy.py:958-997 (автоматическая часть), 568-582 (getMe)]. Для UXQ-01 нужна отдельная проба журнала (см. «Пробы рантайма»).

## Разбор требований (evidence map)

Формат: требование → исходная фаза chat-app → код → вход в рантайме → тесты → предварительный вердикт.

### DAT-02 (путь к БД) — OPEN, зависит от пробы

- **Исходная фаза:** chat-app 04. Требование: хардкод `/opt/assistant-core/data/assistant.db` в chat-app убран.
- **Код chat-app:** `SQLITE_DB_PATH: str = Field(` с значением по умолчанию `"./data/assistant.db"` и алиасом `AliasChoices("SQLITE_DB_PATH", "DATABASE_PATH")` [VERIFIED: /opt/chat-app/backend/app/core/config.py:20-23]. Хардкод `/opt/assistant-core` в config.py отсутствует, тест `test_no_hardcoded_assistant_core_path_in_config` это проверяет [VERIFIED: /opt/chat-app/backend/tests/test_db_config.py:33-37].
- **Код assistant-core:** `DATABASE_URL` берётся из окружения, относительный путь приводится к `BASE_DIR` [VERIFIED: src/config.py:9-23]. Переопределение `ASSISTANT_DB_PATH_OVERRIDE` есть для тестов (GATE-02).
- **Рантайм:** `chat-app.service` неактивен (`ActiveState=inactive`), `WorkingDirectory=/opt/chat-app/backend` [VERIFIED: systemctl show chat-app.service, 2026-10-18]. `assistant-worker.service` активен, `WorkingDirectory=/opt/assistant-core` [VERIFIED: systemctl show assistant-worker.service, 2026-10-18].
- **Риск:** при значении по умолчанию chat-app резолвит `./data/assistant.db` относительно своего CWD, то есть в `/opt/chat-app/backend/data/assistant.db`, если `.env` не переопределяет путь. Это не та БД, что у бота. Тот же риск записан в backlog 999.2 [VERIFIED: /opt/assistant-core/.planning/ROADMAP.md, Phase 999.2, строка «Код-разведка»].
- **Тесты:** `test_db_config.py` проверяет, что по умолчанию путь `./data/assistant.db` [VERIFIED: test_db_config.py:14].
- **Вердикт:** ОТКРЫТО. Из кода не следует, что обе стороны указывают на один файл. Нужна проба пути (раздел «Пробы рантайма», проба P-2). Если путь совпадает с боевым, требование passed. Если нет, DAT-02 — gap, запись в DAT-06 (целостность данных, D-09).

### DAT-03 (WAL, busy_timeout, конкурентная запись) — OPEN, протокол D-07/D-08

- **Код:** фабрика `get_sync_connection` и `get_async_connection` включает `PRAGMA busy_timeout = 30000;` и `PRAGMA journal_mode = WAL;` [VERIFIED: /opt/assistant-shared/assistant_shared/db/connection.py:39-45, 57-64].
- **Тест:** `test_concurrent_write_two_processes` в `/opt/chat-app/backend/tests/test_concurrent_write.py:57-77`. Два процесса через `multiprocessing.Pool(processes=2)`, по 100 транзакций каждый, проверка 200 строк в четырёх таблицах [VERIFIED: test_concurrent_write.py:57-77]. Миграции в тесте применяются один раз в родительском процессе до пула (строка 60).
- **История сбоев (записи в репозиториях, не проверялись повторно):** `OperationalError` при полном прогоне chat-app `1 failed, 260 passed` [CITED: assistant-core/.planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-10-SUMMARY.md:167]; `1 failed, 250 passed` [CITED: chat-app/.planning/quick/261009-uo4-.../261009-uo4-SUMMARY.md:59]; один сбой в гейте и три прохода подряд [CITED: chat-app/.planning/quick/261010-ivt-.../261010-ivt-SUMMARY.md:42]; 2026-10-11 один сбой из двух полных прогонов, принято как A-1 [CITED: /opt/assistant-core/.planning/STATE.md:164].
- **Тексты ошибок в записях не сохранены**, кроме слова `OperationalError`. Поэтому протокол прогонов обязан сохранять полный текст исключения.
- **Вердикт:** по истории ожидается сбой, а D-08 не допускает ни одного сбоя. Вердикт выносится только по 30 прогонам. Предполагаемая причина [ASSUMED]: гонка за блокировку при `PRAGMA journal_mode = WAL` на каждом соединении и при повышении блокировки в транзакции; на машине с 1 vCPU под нагрузкой это проявляется. Не проверено.
- **Машина:** `nproc` = 1, RAM 1967 МБ, доступно около 888 МБ [VERIFIED: nproc, free -m, 2026-10-18]. Режим «под нагрузкой» на одном ядре реально создаёт конкуренцию.

### DAT-04 (тесты chat-app не трогают /opt/assistant-core) — PASSED (предв.), проба strace обязательна

- **Код:** `conftest.py` в chat-app описывает изоляцию, каталог `/opt/assistant-core` не используется, нет subprocess к seed-CLI и нет копирования боевой БД [VERIFIED: /opt/chat-app/backend/tests/conftest.py:1-6].
- **Тесты:** `test_database_isolated.py` проверяет, что путь БД не указывает на assistant-core [GREP: chat-app/backend/tests/test_database_isolated.py:14].
- **Единственное упоминание пути в тестах:** golden-фикстура `test_security_golden.py` содержит строку `/opt/assistant-core` как данные воркспейса, без обращения к файлам [GREP: chat-app/backend/tests/test_security_golden.py:29].
- **Проба (обязательная, D-08 в духе «positive falsification»):** `strace -f -e trace=openat,open,stat,access -o <лог> /opt/chat-app/backend/.venv/bin/pytest backend/tests -p no:cacheprovider` из `/opt/chat-app`, затем `grep /opt/assistant-core <лог>`. Пустой результат для путей `/opt/assistant-core/data/` подтверждает DAT-04. Непустой результат опровергает.
- **Важно:** `grep` по `/opt/assistant-core` в логе покажет и `/opt/assistant-shared` (это другой каталог, не трогать). Фильтр должен быть точным: `/opt/assistant-core/`.

### SEC-01 (единая библиотека в обоих репозиториях) — PASSED (предв.)

- **Импорт в chat-app:** `from assistant_shared.security import (` в `/opt/chat-app/backend/app/api/v1/security.py:10` (Security Tile) [VERIFIED: sed 1-20 security.py].
- **Импорт в assistant-core:** `from assistant_shared.security import audit_repository` в `/opt/assistant-core/scripts/security_shield.py:19` [VERIFIED: security_shield.py:18-24].
- **Тесты эквивалентности:** `chat-app/backend/tests/test_nda_equivalence.py`, `test_shield_parity.py`, `test_security_shared.py` [GREP: listing tests].
- **Вход в рантайм:** Security Tile через роутер `security.py` (chat-app, процесс не активен, см. ниже). Для assistant-core вход — shield-команда `security_shield.py` и pre-commit hook.

### SEC-02 (shield без дрейфа, тонкая обёртка) — PASSED с оговоркой

- `/opt/assistant-core/scripts/security_shield.py` (79 строк) вызывает `audit_repository` из библиотеки [VERIFIED: 18-30 строки].
- `/opt/chat-app/scripts/security_shield.py` и `/opt/assistant-shared/scripts/security_shield.py` являются делегаторами: запускают обёртку assistant-core подпроцессом интерпретатора assistant-core [VERIFIED: docstring chat-app строки 2-9; assistant-shared строки 2-7; subprocess.run в обоих].
- **Оговорка:** требование говорит «тонкая CLI-обёртка над библиотекой» в обоих репозиториях. Обёртки chat-app и assistant-shared обёрткой над библиотекой не являются, они делегируют. Дрейфа нет, потому что логика одна. Записать как оговорку, не gap (D-04 не применим, это вопрос формулировки; решение владельца см. «Открытые вопросы»).
- **Тесты:** `test_nda_script_parity.py`, `test_security_shield_cli.py` (assistant-core), `test_shield_parity.py` (chat-app).

### SEC-03 (pre-commit hook воспроизводимо установлен и блокирует секрет) — OPEN, проба

- **Установка:** в обоих репозиториях `core.hooksPath = .githooks` [VERIFIED: `git -C /opt/assistant-core config --get core.hooksPath` и то же для chat-app, оба вывода `.githooks`].
- **Hook:** `/opt/assistant-core/.githooks/pre-commit` (858 байт) запускает `exec "${PYTHON_BIN}" "${REPO_ROOT}/scripts/security_shield.py" "${REPO_ROOT}"` [VERIFIED: .githooks/pre-commit, целиком].
- **Ограничение:** hook зависит от `scripts/security_shield.py` внутри того же репозитория. Hook в assistant-shared — отдельный файл. Записано как DEBT-03 IN-05 (зависимость от пути assistant-core) [CITED: ROADMAP.md, backlog 999.x].
- **Проба (SEC-03):** создать временный git-репозиторий в каталоге вне боевых путей, скопировать туда `scripts/security_shield.py` и `.githooks/pre-commit`, выставить `core.hooksPath`, закоммитить файл с синтетическим секретом (фикстура из tests/, не реальный ключ). Ожидание: коммит отклонён с ненулевым кодом. Одновременно проверить, что тот же файл без секрета коммитится. Коммит в репозиторий assistant-core не делать.
- **Синтетический секрет:** использовать явно поддельный ключ-шаблон из существующих синтетических фикстур теста `test_security_shield_cli.py` (не писать реальный формат ключа в RESEARCH или VERIFICATION).

### HIT-01 (примитив подтверждения) — GAP (предв.)

- **Есть:** `ConfirmationStore` с `create_confirmation`, `confirm_action`, `reject_action` (`/opt/assistant-shared/assistant_shared/hitl/store.py`, строки 20–166) [GREP]; `resume_action` в `engine.py:28` [VERIFIED: engine.py:28-62]; `PendingConfirmation` в models.py:24 [GREP]; миграция `0002_pending_confirmations.sql` [GREP: каталог миграций].
- **Отсутствует:** декоратор `@requires_confirmation`. Файл `assistant_shared/hitl/decorators.py` целиком содержит только функцию `create_hitl_conflict_exception` (строки 13–26) [VERIFIED: decorators.py:1-26]. Поиск `requires_confirmation` по `/opt/assistant-shared`, `/opt/assistant-core/src`, `/opt/assistant-core/tests` даёт ноль попаданий в коде (только в документах: REQUIREMENTS, план chat-app 05-01) [GREP]. Заявление в SUMMARY фазы chat-app 05 о наличии декоратора не подтверждается кодом.
- **Обход единой точки:** `cb_dlg_confirm_clear` (очистка диалога) создаёт запись `clear_dialog`, сразу подтверждает её через `store.confirm_action`, затем вызывает `self.db.clear_dialog_history` напрямую, без `resume_action` [VERIFIED: src/notifier/bot_handler.py:1932-1950]. Пользовательское подтверждение кнопкой `dlg:confirm_clear` при этом есть; но запись создаётся постфактум и через единую точку не проходит.
- **Работающий путь:** `hitl:confirm:` → `cb_hitl_confirm` → `resume_action` (`bot_handler.py:2051-2078`) [GREP]; `act:*` → `_handle_hitl_action_callback` → `resume_action` (`bot_handler.py:2358`, вызов на 2401) [GREP].
- **Тесты:** `tests/test_hitl_safety_guardrails.py` (очистка и отмена), `tests/test_bot_hitl_parity.py`, `tests/test_hitl_telegram_cards.py` [GREP: listing].
- **Вердикт (предв.):** gap. Декоратор из текста требования отсутствует. Обход единой точки для очистки диалога. По D-09 это HITL → новое требование (HIT-05). По D-10 исправлять в фазе нельзя.
- **Владельцу:** требует ли HIT-01 декоратор буквально или достаточно ConfirmationStore + resume_action (тогда текст требования меняется).

### ISO-01 (ключи Gemini в контексте персоны) — PASSED (предв.)

- `src/brain/key_rotator.py`: `_current_rotator: ContextVar[GeminiKeyRotator | None] = ContextVar("current_key_rotator", default=None)` (строка 190) и `get_key_rotator(persona_id)` (строка 194) [VERIFIED: key_rotator.py:188-200].
- Тест: `test_key_rotator_no_global_config_mutation` проверяет, что `config.GEMINI_API_KEY` не меняется после `mark_exhausted`, и что `.env` переписывается только при явном `env_path` [VERIFIED: tests/test_key_rotator.py:111-125].
- **Замечание:** `sync_active_key_to_env` переписывает строку `GEMINI_API_KEY=` в файле `.env` (строки 120–131) [GREP]. Это запись в файл, а не мутация глобального конфига. В VERIFICATION отметить как побочный эффект.

### ISO-02 (маскировка NDA для LLM) — PASSED по объёму v3, с отдельной записью gap по метаданным

- **Маскировка:** `mask_nda_email_data` заменяет `body_plain`, `body_html` (на пустую строку), `snippet`, `attachments` (пустой список) и `body` маркером `[NDA: тело и вложения скрыты Air-Gap]` [VERIFIED: src/security/airgap.py:132-157; NDA_MASK_MARKER строка 19].
- **Места вызова:** `secretary_dialog.py` в `_get_email_overview` (строки 160–180), `_search_email_context` (182–200, вызов на строке 338) и в tool-ответе `search_emails` (758–790); `summarizer.py` (62, 327, 331, 436, 440); `reply_generator.py:45` (для NDA — исключение `AirGapViolationError`) [VERIFIED: secretary_dialog.py:160-200, 758-790; GREP для summarizer и reply_generator].
- **Метаданные в LLM (найдено):** во всех трёх путях диалога `sender`, `sender_email`, `subject`, `date_sent` передаются в LLM для NDA-писем, маскируются только тело, snippet и вложения. В tool-ответе: `"sender": em.get("sender_name") or em.get("sender_email")`, `"subject": em.get("subject", "")`, `"date_sent": str(em.get("date_sent", ""))` [VERIFIED: secretary_dialog.py:775-784].
- **Сравнение формулировок:** v2.0 ISO-02 говорит «метаданные обрабатываются только локальным кодом» [CITED: chat-app/.planning/milestones/v2.0-REQUIREMENTS.md, ISO-02]. v3 ISO-02 сужает объём до тела, snippet и вложений, а метаданные выносит в NDAM-01 [VERIFIED: /opt/assistant-core/.planning/REQUIREMENTS.md:53-54].
- **Реальная ситуация:** NDA-почтового ящика сейчас не подключено (решение владельца 2026-10-09, NDAM-01 в v2 требованиях). Утечки на текущих данных нет, но путь кода открыт.
- **Вердикт:** ISO-02 passed в объёме v3-формулировки. Метаданные NDA в LLM записываются как отдельный gap ISO-05 (безопасность, D-09, D-10). Владелец выбирает: оставить NDAM-01 или завести ISO-05 сейчас (см. «Открытые вопросы»).
- **Тесты-ловушки:** `tests/test_airgap_trap.py`, `tests/test_git_airgap_trap.py`, `tests/test_nda_script_parity.py` [GREP: listing]. Ловушка проверяет тело и вложения; метаданные она не проверяет.

### ISO-03 (Zero-Trust scopes) — PASSED (предв.)

- `src/composition.py` проверяет `required_scopes` коннектора против `binding.scopes` и поднимает `MissingScopeError`: строки 37 (schedule_source), 57 (timesheet), 78 (lms), 111 (git_source) [VERIFIED: composition.py:20-111 через cat].
- `default_lms_client()` вызывается в `src/main.py:673` (`lms_client = default_lms_client()`) вне блока try. Отсутствие scope при старте приводит к падению процесса (fail-closed) [VERIFIED: src/main.py:673].
- **Часть про chat-app:** «процесс chat-app не держит учётные данные LMS». Поиск по `/opt/chat-app/backend/app` на `lms|guap` (без учёта регистра) вернул ноль совпадений [GREP]. Это отрицательный результат поиска в коде; для VERIFICATION фиксировать как «код LMS в chat-app отсутствует (поиск по app/)». Доказательство «нет учётных данных» из отсутствия кода — только вывод [ASSUMED по строгости правила].
- **Тесты:** `tests/test_phase4_reachability.py`, `tests/test_ports_conformance.py`, `tests/test_concurrency_isolation.py` (MissingScopeError) [GREP].

### ISO-04 (нет cross-talk) — PASSED (предв., нужен прогон)

- `tests/test_concurrency_isolation.py:44` `test_multi_persona_concurrency_isolation` запускает воркеры персоны по умолчанию и синтетической персоны параллельно, с отдельными `gemini_keys` и проверкой `get_key_rotator` и `default_timesheet_service` [VERIFIED: test_concurrency_isolation.py:44-60]. Есть также `test_concurrent_confirmations_isolation` (строка 97) и `test_high_concurrency_persona_switching` (166).
- Синтетическая персона: `tests/synthetic_persona.py`; проверки `tests/test_synthetic_persona.py` [GREP].
- **Вердикт:** passed после зелёного прогона этих тестов. Прогон в фазе исполнения.

### FIN-01 (HARDCODE_BASELINE пуст) — КОНФЛИКТ ФОРМУЛИРОВОК, решение владельца

- **Формально (CONTEXT):** baseline пуст в обоих репозиториях. Проверено чтением:
  - `/opt/assistant-core/tests/hardcode_baseline.py:14`: `HARDCODE_BASELINE: dict[str, dict[str, int]] = {}` [VERIFIED].
  - `/opt/chat-app/backend/tests/hardcode_baseline.py:14`: `HARDCODE_BASELINE: dict[str, dict[str, int]] = {}` [VERIFIED].
- **Буква требования (v2.0 FIN-01 и v3 «пустой allowlist»):** «сканер хардкода работает с пустым allowlist». Фактический allowlist в обоих сканерах: `ALLOWLIST_PREFIXES = ("config/", "tests/", "backend/tests/", "docs/", ".planning/")` и `ALLOWLIST_SUFFIXES = (".md",)` [GREP: tests/test_hardcode_scanner.py:47-48; chat-app/backend/tests/test_hardcode_scanner.py:47]. Комментарий в файле: «Фаза 6 ужесточает до пустого allowlist (FIN-01)», то есть цель не достигнута.
- **Вывод:** формально FIN-01 пройден (baseline пуст, это CONTEXT-решение). По букве требования allowlist не пуст. Владелец решает, что считать FIN-01 (см. «Открытые вопросы»). Если по букве, это приватность (персональные данные в файлах), то новое требование FIN-02.

### ACT-01 (function calling с function_response) — GAP по букве, решение владельца

- **Инструменты объявлены:** `tool_create_calendar_event`, `tool_create_reminder`, `tool_draft_email_reply`, `tool_search_emails` [GREP: src/brain/tools_schema.py:21, 38, 53, 66].
- **Фактический путь для create_*:** инструмент не исполняет бэкенд. Вызов превращается в `ActionProposal` и карточку подтверждения [VERIFIED: secretary_dialog.py:712-726 и 816-822 (`_build_action_proposal`)]. Бэкенд (`GoogleCalendarClient`, `db.create_reminder`, черновик письма) вызывается только в обработчиках подтверждения: `_handle_create_calendar_event`, `_handle_create_reminder`, `_handle_draft_email_reply` (`src/notifier/bot_handler.py:228-299`) [VERIFIED: bot_handler.py:228-240 и регистрация 297-299].
- **function_response:** возвращается модели только для `search_emails` (`secretary_dialog.py:787-788`) [VERIFIED]. Для create_* function_response не формируется.
- **Текст требования:** «вызов реального API бэкенда и передача результата function_response обратно в модель» [VERIFIED: /opt/assistant-core/.planning/REQUIREMENTS.md:58 (v3 ACT-01) и BACKLOG chat-app, ACT-01 (описание)]. Текущий дизайн (HITL-first, ACT-03) с этим требованием расходится.
- **Вердикт (предв.):** gap по букве. Решение владельца: принять HITL-first как спецификацию (тогда текст ACT-01 меняется) или сохранить букву (тогда gap и новый ACT-05 по HITL).

### ACT-02 (запрет утверждать выполнение без tool_result) — PARTIAL по букве

- **Правило в промпте:** `config/prompts/secretary_default.jinja2:28`: «КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО утверждать, заявлять или создавать иллюзию, что событие внесено в календарь, создано напоминание или подготовлен черновик, если в текущем диалоге не был вызван соответствующий инструмент и не сформирована карточка подтверждения!» [VERIFIED: secretary_default.jinja2:26-31].
- **Расхождение:** требование говорит «не был успешно вызван инструмент и не получен tool_result». Промпт говорит «не был вызван» и «не сформирована карточка». Слов «успешно» и «tool_result» в правиле нет.
- **Уточняющий вопрос:** есть, `secretary_default.jinja2:30` (правило про время события) [VERIFIED].
- **Тесты:** `tests/test_secretary_tools.py`, снимок промпта `tests/fixtures/prompts_snapshot/secretary.txt` [GREP]. Поведение LLM детерминированно не проверяется, это [ASSUMED].
- **Вердикт (предв.):** решение владельца вместе с ACT-01.

### ACT-03 (HITL-карточка с инлайн-кнопками) — PASSED (предв.)

- Callbacks: `act:cal:conf:`, `act:cal:rej:`, `act:cal:retry:`, `act:rem:conf:`, `act:rem:rej:`, `act:drf:conf:`, `act:drf:rej:` зарегистрированы в `src/notifier/bot_handler.py:403-409` [VERIFIED].
- Карточки: `src/notifier/telegram.py:113-131` и `195-228` (создание и подтверждение для `create_calendar_event`, `create_reminder`, `draft_email_reply`) [GREP].
- Исполнение только после нажатия: `_handle_hitl_action_callback` → `resume_action` (`bot_handler.py:2358`, вызов на 2401) [GREP].
- Тесты: `tests/test_hitl_telegram_cards.py`, `tests/test_tool_calling_e2e.py`, `tests/test_tool_calling_flow.py` [GREP].

### ACT-04 (интенты планирования) — PASSED (предв.)

- Допустимые действия (константа) включают `"calendar_schedule"`, `"create_reminder"`, `"draft_reply"` [VERIFIED: src/brain/intent_router.py:43-48].
- Ветки роутера создают `action="create_reminder"` (строки 224, 263) и `action="calendar_schedule"` (235, 247) [GREP].
- Вход в рантайм: `src/notifier/bot_handler.py:1471` — `elif route_res.action in ("calendar_schedule", "create_reminder", "draft_reply"):` [GREP].
- Тесты: `tests/test_fast_intent_router.py` [GREP].

### UXQ-01 (меню команд) — GAP (предв.), частично: при подключении и отключении не обновляется

- **Построение и установка:** `setup_bot_commands` берёт команды из `command_registry.get_telegram_commands()` и вызывает `set_my_commands` с `BotCommandScopeDefault` и `BotCommandScopeChat(chat_id=...)` [VERIFIED: bot_handler.py:911-935].
- **Вызовы:** при старте `src/main.py:700` и `932`; при скрытии, показе и алиасах в чате (`setup_bot_commands(chat_id=message.chat.id)` на строках 1363, 1376, 1397, 1408) [GREP].
- **Нет:** обновления при подключении и отключении коннекторов. Подключение из диалога — это ONB-02 (v3 Phase 8). Такого пути в рантайме нет.
- **Журнал как доказательство:** при старте код пишет `Successfully registered %d Telegram bot menu commands across categories: ...` [VERIFIED: bot_handler.py:933]. Строка в journalctl подтверждает регистрацию при запуске.
- **Live-подтверждение:** в фазе 03 живая проверка `/menu` прошла при рестарте владельцем [VERIFIED: /opt/assistant-core/.planning/STATE.md:150].
- **Вердикт (предв.):** gap по части «при подключении и отключении». Записать как связь с ONB-02 (Phase 8), а не новое требование (D-09: не безопасность). Часть «строится из коннекторов персоны и обновляется при смене видимости» — passed.

### UXQ-02 (алиасы, переименование, скрытие команд) — PASSED (предв.)

- Миграция `0003_bot_commands_and_feedback.sql` создаёт `bot_command_settings` (строки 2–7), `bot_custom_aliases` (9–13) и `dialog_feedback_log` (15–21) [VERIFIED: 0003_bot_commands_and_feedback.sql, целиком].
- Инлайн-DDL удалён из `src/storage/db.py`, проверяет `tests/test_no_inline_ddl.py` [GREP].
- Команды из чата: скрыть (`m_hide_cmd`, `set_command_setting(is_enabled=False)`), показать, алиас (`m_alias`), удалить алиас (`m_del_alias`) [VERIFIED: bot_handler.py ~1355–1412 через grep по именам]; `setup_bot_commands` после каждого изменения.
- Тесты: `tests/test_command_aliases.py`, `tests/test_command_registry.py` [GREP].
- **Оговорка:** пример «переименуй /timesheet в /часы» требует проверки в фазе исполнения (парсер команд чата). Записать как шаг пробы.

### UXQ-04 (edge cache, телеметрия, алерты) — GAP (предв.) по алертам; passed по телеметрии; бэклог по кэшу

- **Телеметрия 👍/👎 — PASSED:** `build_dialog_feedback_keyboard` прикрепляется к ответам секретаря (`bot_handler.py:2631`); callback `fb:` → `cb_dialog_feedback` (2698) → `db.log_dialog_feedback` (2724) → вставка в `dialog_feedback_log` [VERIFIED: db.py:2955-2966 — INSERT INTO dialog_feedback_log].
- **Edge cache — частично:** кэш `self._edge_cache: dict[str, tuple[float, str]] = {}` в памяти процесса (`bot_handler.py:189`), TTL 15 минут для расписания (`549-593`) и 30 минут для табеля (`1722-1795`). Это не SQLite и не измерено относительно «< 250 мс». Логи пишут «< 50ms» как текст, не измерение [VERIFIED: bot_handler.py:549-593].
  - По D-04: достижимо трассой, слабое покрытие (нет замера задержки) → passed с пометкой и запись в бэклог 999.x «измерить и сохранить в SQLite».
- **Проактивные алерты коннекторов — GAP:** `send_connector_health_alert` определён в `EmailBotHandler` (`bot_handler.py:2660`), кнопка `chk:` зарегистрирована (422) и обрабатывается `cb_connector_health_check` (2692) [VERIFIED]. Вызовов `send_connector_health_alert(` в `src/` нет: поиск по `send_connector_health_alert(` даёт только строку определения 2660 [GREP]. Планировщик `scheduler.add_job` в `src/main.py` задачи проверки коннекторов не содержит (список job id в main.py строки 807–914) [VERIFIED: main.py:807-914 через grep add_job]. Путь мёртв: алерт не может прийти владельцу.
  - По D-09 не безопасность и не HITL → запись в бэклог 999.x (функция не доставляется), статус требования gap.

## Пробы рантайма (read-only, D-03)

| ID | Что доказывает | Команда | Что записать в VERIFICATION | Ограничения |
|----|----------------|---------|-----------------------------|-------------|
| P-1 | Сервис жив, задачи планировщика зарегистрированы, getMe | `cd /opt/assistant-core && python3 scripts/deploy.py` | Вывод проверок (без токена) | Без `--restart`, `--backup`, `--await-help`. Меню команд не проверяет |
| P-2 | Путь БД, который открыл assistant-worker | `journalctl -u assistant-worker.service --since "-24h" \| grep "Database initialized at"` | Строка с путём | Печатает путь, не значения секретов |
| P-3 | Меню команд зарегистрировано при старте | `journalctl -u assistant-worker.service --since "-24h" \| grep "Successfully registered"` | Строка с числом команд | Только журнал |
| P-4 | Задачи планировщика | `journalctl -u assistant-worker.service --since "-24h" \| grep "Added job"` | Список job | Уже покрыто P-1 |
| P-5 | Путь БД chat-app (DAT-02) | Не выполнять без разрешения владельца. Требует, чтобы pydantic прочитал `/opt/chat-app/backend/.env`. Вариант: владелец запускает сам и присылает только путь | Резолвленный путь | Нарушение запрета на чтение `.env` Claude. Вопрос владельцу |
| P-6 | Состояние сервисов | `systemctl show chat-app.service -p ActiveState -p WorkingDirectory` и то же для `assistant-worker.service` | Состояние | Не выводить `Environment` |
| P-7 | DAT-04 изоляция chat-app | `strace -f -e trace=openat,open,stat,access -o <лог-вне-репо> /opt/chat-app/backend/.venv/bin/pytest backend/tests -p no:cacheprovider` (cwd `/opt/chat-app`) | Пустой результат по `/opt/assistant-core/` | Полный прогон chat-app, нагрузка на 1 vCPU |
| P-8 | SEC-03 hook | Временный git-репозиторий вне боевых путей (раздел «Wave 0») | Вывод отказа hook | Коммит в assistant-core не делать |

**P-2 — важная находка:** `src/main.py:648` пишет `Database initialized at %s` с `config.SQLITE_DB_PATH` [VERIFIED: src/main.py:646-648]. Журнал даёт фактический путь процесса worker без чтения `.env`. Для chat-app такого лога нет, а сервис неактивен, поэтому его путь доказывается только статически (P-5) или владельцем.

**Ограничение D-03:** `deploy.py` (`scripts/deploy.py:958-997`) проверяет сервис, журнал, окно ошибок, задачи планировщика по журналу и getMe. Меню, алерты и путь БД он не проверяет. Считать, что D-03 «меню через deploy.py» выполняется пробами P-3 и P-2, а не самим deploy.py.

**Гейт и боевая БД:** гейт сверяет SHA-256 боевой БД до и после прогона (GATE-02, по проекту допустимо). Фаза сама БД не открывает. По 01-04 SUMMARY гейт может покраснеть из-за записи живого worker в окне прогона; повтор в тихом окне по решению 01-05 [CITED: 01-04 и 01-05 summaries в /opt/assistant-core/.planning/phases/01-*]. Учесть при финальном прогоне.

## Нестабильный тест DAT-03: протокол

**Тест:** `/opt/chat-app/backend/tests/test_concurrent_write.py::test_concurrent_write_two_processes`.

**Запуск изолированно (30 раз, свободная система, D-07):**

```bash
cd /opt/chat-app
for i in $(seq 1 30); do
  PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/pytest -p no:cacheprovider -q \
    "backend/tests/test_concurrent_write.py::test_concurrent_write_two_processes" \
    --basetemp="/tmp/dat03-free-$i" > "<лог-вне-репо>/free-$i.log" 2>&1
  echo "run $i rc=$?"
done
```

`--basetemp` задаёт каталог tmp_path вне репозитория chat-app. Сам тест работает с `tmp_path`, а не с боевой БД. Путь `/tmp/dat03-free-$i` указан как каталог вне репозиториев; при желании заменить на каталог scratchpad.

**Под нагрузкой (D-07):** на тот же цикл наложить полный прогон chat-app в фоне:

```bash
cd /opt/chat-app && PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/pytest backend/tests -p no:cacheprovider -q > <лог> 2>&1 &
```

Прогонять по одному циклу за раз (1 vCPU, 888 МБ свободно). Нельзя запускать параллельно с `scripts/gate.py`.

**Критерий (D-08):** 0 сбоев из 30 в каждом режиме = stable. Любой сбой = gap. Для каждого сбоя записать номер прогона, режим, полный текст исключения (`grep -m3 -E "Error|locked"`), время.

**Гигиена:** `skip`, `xfail` и `deselected` не ставить; тест не менять. Логи лежат вне репозиториев.

**Гипотезы причины [ASSUMED]:** (1) `PRAGMA journal_mode = WAL` выполняется на каждом соединении и требует блокировки; (2) транзакция `with conn:` в sqlite3 начинается отложенно, и повышение блокировки при конкуренции не ждёт `busy_timeout`; (3) на 1 vCPU два процесса переключаются, и окно конкуренции растёт. Проверить по тексту исключения из прогонов. Не подтверждено.

## Wave 0 и пробы вне репозиториев

Код не меняется, новые тесты в `tests/` не добавляются. D-01 требует вход через реальный хэндлер на временной БД. Решение:

- Пробы-e2e пишутся в каталог вне репозиториев (scratchpad), запускаются с `ASSISTANT_DB_PATH_OVERRIDE=<tmp>` и под `strace -e trace=openat` на `/opt/assistant-core/data/`. Тогда guard `tests/conftest.py` не действует, поэтому strace обязателен.
- Если владелец разрешит добавление тестов, то это отдельная задача вне фазы 5. По D-04 пока допустим passed «трасса, без e2e».
- Заглушки внешних API: Gemini, Telegram, Google, Notion. Живые вызовы только чтения (D-02). Для NDA-данных живых вызовов LLM не делать.

## Формат записей gap

### REQUIREMENTS.md (безопасность, HITL, NDA, целостность — D-09)

Формат существующих записей v3 [VERIFIED: /opt/assistant-core/.planning/REQUIREMENTS.md:12-17]:

```
- [ ] **ID**: текст требования. Доказательство: VERIFICATION фазы 5 (раздел, строка). Привязка: Phase N.
```

Предлагаемые ID (свободны в v3: DAT-05, DAT-06, ISO-05, HIT-05, ACT-05, FIN-02; HIT-02..04 уже заняты отложенными требованиями, поэтому HIT начинается с 05):

| Кандидат | Причина | Классификация D-09 | Условие |
|----------|---------|--------------------|---------|
| HIT-05 | декоратор отсутствует; очистка диалога без resume_action | HITL | gap подтверждён |
| ISO-05 | метаданные NDA-почты (отправитель, тема, дата) в LLM | Air-Gap | вместо NDAM-01 или вместе с ним (решение владельца) |
| DAT-05 | нестабильная конкурентная запись (DAT-03) | целостность данных | если хотя бы один сбой из 30 |
| DAT-06 | путь БД chat-app не совпадает с боевым | целостность данных | только если P-5 покажет расхождение |
| ACT-05 | function_response и tool_result по букве ACT-01/02 | HITL | только если владелец сохраняет букву |
| FIN-02 | allowlist сканера не пуст (персональные данные в файлах) | приватность | только если владелец принимает букву FIN-01 |
| SEC-04 | pre-commit hook не блокирует синтетический секрет | безопасность | только если проба P-8 красная |

Привязка к фазе: у v3 есть Phase 6 (UXQ-03), 7 (GEN-01, ONB-01), 8 (ONB-02, ONB-03). Для безопасных gap нужна новая фаза или включение в существующую. Решение владельца.

### ROADMAP.md, раздел Backlog (косметика, улучшения — D-09)

Формат существующих записей [VERIFIED: /opt/assistant-core/.planning/ROADMAP.md:290-304]:

```
### Phase 999.N: Название (BACKLOG)

**Goal**: ...
**Source phase**: 05
**Deferred at**: 2026-10-18 ...
**Follow-ups:**
- [ ] ...
```

Существующие: 999.1 и 999.2. Следующие: 999.3, 999.4. Кандидаты:
- 999.3: UXQ-04 — проактивные алерты коннекторов не вызываются (мёртвый путь `send_connector_health_alert`).
- 999.4: UXQ-04 — edge cache измерить относительно 250 мс и вынести в SQLite; сейчас in-memory (D-04).
- 999.5: SEC-02 — оговорка о делегаторах chat-app и assistant-shared (если владелец сочтёт важным).
- 999.6: DEBT, зафиксированные ранее (IN-05 hook зависит от пути assistant-core), если не закрыты.

UXQ-01 (подключение и отключение) — ссылка на ONB-02, отдельная запись не нужна.

## Открытые вопросы (задать владельцу через опрос; главный агент задаёт AskUserQuestion)

1. **FIN-01:** считать ли пройденным по формальному критерию (`HARDCODE_BASELINE` пуст, как в CONTEXT) или по букве (пустой allowlist)? Рекомендация: формально, с записью FIN-02 по букве.
2. **ACT-01/ACT-02:** принять HITL-first (карточка подтверждения вместо function_response и tool_result) как спецификацию, или сохранить букву (тогда gap ACT-05)? Рекомендация: зафиксировать HITL-first в тексте требования.
3. **ISO-02/ISO-05:** оставить метаданные NDA в NDAM-01 (v2) или завести ISO-05 сейчас? Рекомендация: ISO-05, потому что сейчас путь кода открыт, а не только будущий ящик.
4. **HIT-01:** требовать декоратор `@requires_confirmation` буквально или считать достаточным ConfirmationStore + resume_action? Рекомендация: gap HIT-05 для обхода в очистке диалога в любом случае; вопрос только о декораторе.
5. **P-5 (путь БД chat-app):** разрешить ли чтение `.env` через pydantic в процессе (вывод только пути), или владелец запускает проверку сам? Без этого DAT-02 остаётся открытым.
6. **Привязка новых gap к фазам:** новая фаза «Безопасность HITL и Air-Gap» или включение в Phase 6? Решение владельца.
7. **V2-07:** подтвердить, что фаза 07 закрывается ссылкой на v3 `04-VERIFICATION.md`.
8. **Счёт требований:** подтвердить, что проверяются 19 ID, а VER-01 — сама фаза (в ROADMAP и CONTEXT написано «20»).

## Validation Architecture

> Включено: `workflow.nyquist_validation` в `.planning/config.json` не задан явно как false (`"nyquist_validation": true`) [VERIFIED: /opt/assistant-core/.planning/config.json].

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (обе venv), pytest-asyncio (`asyncio_mode = auto`) |
| Config file | `/opt/assistant-core/pytest.ini` [VERIFIED: pytest.ini: `asyncio_mode = auto`, `testpaths = tests`, `pythonpath = .`]; у chat-app отдельного pytest.ini в backend/ и корне не найдено [VERIFIED: ls] |
| Quick run (assistant-core) | `cd /opt/assistant-core && .venv/bin/pytest tests/test_key_rotator.py tests/test_concurrency_isolation.py tests/test_hitl_safety_guardrails.py -q` |
| Full suite (assistant-core) | `cd /opt/assistant-core && python3 scripts/gate.py` (ИТОГ: ЗЕЛЁНЫЙ, rc 0) |
| Quick run (chat-app, DAT-03) | `cd /opt/chat-app && PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/pytest -p no:cacheprovider backend/tests/test_concurrent_write.py -q` |
| Full suite (chat-app) | `cd /opt/chat-app && PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/pytest -p no:cacheprovider backend/tests` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DAT-02 | путь БД из настроек | config + журнал | P-2, P-5 | ✅ test_db_config.py; P-5 ❌ (нужно разрешение) |
| DAT-03 | конкурентная запись | integration | 30 прогонов (протокол выше) | ✅ chat-app test_concurrent_write.py |
| DAT-04 | изоляция chat-app | strace-проба | P-7 | ✅ conftest; strace-проба ❌ (не запускалась) |
| SEC-01 | библиотека в обоих | import-проверка | `grep -rn "assistant_shared.security"` + тесты parity | ✅ |
| SEC-02 | без дрейфа | parity | `test_nda_script_parity.py`, chat-app `test_shield_parity.py` | ✅ |
| SEC-03 | hook блокирует секрет | e2e в tmp-репо | P-8 | ❌ нет теста, пробу писать вне репо |
| HIT-01 | примитив | unit + grep | `pytest tests/test_hitl_safety_guardrails.py`; grep `requires_confirmation` | ✅ тесты; декоратора нет |
| ISO-01 | ключи в контексте | unit | `pytest tests/test_key_rotator.py -k no_global_config_mutation` | ✅ |
| ISO-02 | маскировка NDA для LLM | trap | `pytest tests/test_airgap_trap.py tests/test_nda_script_parity.py` | ✅ (метаданные не покрыты) |
| ISO-03 | scopes | unit | `pytest tests/test_phase4_reachability.py tests/test_ports_conformance.py` | ✅ |
| ISO-04 | cross-talk | integration | `pytest tests/test_concurrency_isolation.py` | ✅ |
| FIN-01 | baseline пуст | unit | `pytest tests/test_hardcode_scanner.py` + Read baseline | ✅ |
| ACT-01 | инструменты и бэкенд | e2e | `pytest tests/test_tool_calling_e2e.py tests/test_secretary_tools.py` | ✅ |
| ACT-02 | правило промпта | snapshot | `pytest tests/test_prompt_snapshot.py` | ✅ (поведение LLM не проверяется) |
| ACT-03 | карточка и подтверждение | e2e | `pytest tests/test_hitl_telegram_cards.py` | ✅ |
| ACT-04 | интенты | unit | `pytest tests/test_fast_intent_router.py` | ✅ |
| UXQ-01 | меню | журнал | P-3 | ✅ tests/test_bot_menu.py; журнал при подключении ❌ |
| UXQ-02 | алиасы и скрытие | unit | `pytest tests/test_command_aliases.py tests/test_command_registry.py` | ✅ |
| UXQ-04 | телеметрия, кэш, алерты | unit + grep | `grep -rn "send_connector_health_alert("` (пусто) | ✅ частично |

### Sampling Rate
- **Per requirement batch:** quick run соответствующих тестов.
- **Per wave merge:** полный pytest assistant-core (через гейт).
- **Phase gate:** `python3 scripts/gate.py` ЗЕЛЁНЫЙ; 30 прогонов DAT-03 записаны.

### Wave 0 Gaps
- [ ] Каталог для логов и проб вне репозиториев (scratchpad или каталог вне `/opt`). Создать в начале фазы.
- [ ] Проба strace (P-7) — команда описана, не выполнялась.
- [ ] Проба hook (P-8) — tmp-репозиторий, не выполнялась.
- [ ] Разрешение владельца на P-5 или решение «владелец запускает сам».

## Security Domain

> Включено: `security_enforcement` не отключён (`"security_enforcement": true`, `"security_asvs_level": 1`, `"security_block_on": "high"`) [VERIFIED: config.json].

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | нет (вход в бот через `allowed_user_id`) | Проверка `_is_authorized` в callbacks (проверено в `bot_handler.py`, например строки 1934, 2054) |
| V4 Access Control | да | HITL: подтверждение только авторизованным пользователем (`_is_authorized` в `cb_dlg_confirm_clear`, `_handle_hitl_action_callback`) |
| V5 Input Validation | да | Pydantic-модели персоны; `fromisoformat` в обработчиках подтверждения |
| V6 Cryptography | нет | Не применяется фазой |
| V7 Error Handling and Logging | да | Логи без токенов (deploy.py не печатает токен, `telegram_get_me` не выводит тело ответа) |
| V8 Data Protection | да | Air-Gap для NDA (`airgap.py`), маскировка тела и вложений |
| V11 Business Logic | да | HITL-идемпотентность через `resume_action` (одно выполнение); обход в `clear_dialog` |
| V14 Configuration | да | Путь БД, `.env` не читается инструментами |

### Known Threat Patterns для этой фазы

| Pattern | STRIDE | Standard Mitigation | Статус |
|---------|--------|---------------------|--------|
| Обход подтверждения: запись подтверждается постфактум, действие без resume_action | Elevation / Tampering | Единая точка `resume_action`, декоратор | HIT-05 (gap) |
| Утечка метаданных NDA во внешнюю LLM | Information Disclosure | Маскировка всех полей, fail-closed | ISO-05 (gap) |
| Чтение `.env` верификацией | Information Disclosure | Не читать `.env`; путь из журнала (P-2) | Учтено |
| Запись в репозиторий chat-app верификацией (`__pycache__`, `.pytest_cache`) | Tampering | `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider` | Учтено |
| Запись в живую БД тестами или пробами | Tampering | `ASSISTANT_DB_PATH_OVERRIDE` и strace-контроль | Учтено |
| Относительный путь БД в chat-app, другая БД | Tampering / Integrity | Абсолютный путь через env | DAT-02 (открыт) |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| assistant-core venv (`/opt/assistant-core/.venv`) | тесты, гейт | ✓ | pytest 9.1.1 | — |
| chat-app venv (`/opt/chat-app/backend/.venv`) | тесты DAT-03/DAT-04 | ✓ | pytest 9.1.1 | — |
| strace | P-7 | ✓ | `/usr/bin/strace` | ручной анализ тестов |
| journalctl и systemctl show | P-2..P-6 | ✓ (проверено systemctl show) | — | — |
| assistant-worker.service | P-1..P-4 | ✓ active | — | — |
| chat-app.service | DAT-02/DAT-04 живой вход | ✗ inactive | — | статические доказательства и тесты |
| CPU | DAT-03 под нагрузкой | 1 vCPU | — | нагрузка от полного pytest |
| RAM | все | 1967 МБ, около 888 МБ доступно | — | последовательные прогоны |
| agy (`/opt/chat-app/scripts/agy_task.sh`) | инвентаризация (D-11) | скрипт есть; по STATE A-6 делегирование не работает | — | Claude выполняет инвентаризацию сам |

**Missing with no fallback:** нет.
**Missing with fallback:** chat-app.service неактивен (живой вход chat-app недоступен; доказательство статическое и тестовое, это записывается в VERIFICATION). agy (A-6 в STATE.md) — делегирование не подтверждено, план должен предусматривать выполнение Claude.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Причина нестабильности DAT-03: гонка при `PRAGMA journal_mode` и повышении блокировки | DAT-03, протокол | Неверная гипотеза не меняет вердикт (он по 30 прогонам), но влияет на план исправления |
| A2 | Chat-app без `.env` резолвит `./data/assistant.db` в `/opt/chat-app/backend/data/` | DAT-02 | Если неверно, DAT-02 passed, а P-5 не нужен |
| A3 | Latency-цель 250 мс не измерена нигде | UXQ-04 | Если есть замер, UXQ-04 cache — passed без бэклога |
| A4 | ISO-04 и ISO-01 тесты зелёные сейчас | ISO-01, ISO-04 | Нужен прогон; вердикт предварительный |
| A5 | Поведение LLM по ACT-02 не проверяется детерминированно | ACT-02 | Вердикт опирается на текст промпта и снимок |
| A6 | Отсутствие кода LMS в chat-app означает отсутствие учётных данных | ISO-03 | Нужна проверка конфигурации chat-app, а не только поиска по коду |
| A7 | Метаданные NDA сейчас не утекают (нет подключённого NDA-ящика) | ISO-02 | По коду путь открыт независимо от факта подключения |
| A8 | В корне `/opt/assistant-core` лежит файл `assistant.db`, не открывался (не боевая БД по пути `data/`) | Открытые вопросы | Требует проверки происхождения, не открывать |

**Если таблица пустая:** не применимо, таблица не пустая. Все помеченные пункты требуют подтверждения до волны 3.

## Sources

### Primary (HIGH confidence, прочитано в сессии)
- `/opt/assistant-core/.planning/phases/05-retro-verifikatsiya-v2-0/05-CONTEXT.md` (полностью)
- `/opt/assistant-core/.planning/REQUIREMENTS.md`, `STATE.md` (полностью)
- `/opt/assistant-shared/assistant_shared/db/connection.py` (полностью), `hitl/decorators.py` (полностью), `hitl/engine.py` (1–90), `db/migrations/0003_bot_commands_and_feedback.sql` (полностью)
- `/opt/chat-app/backend/tests/test_concurrent_write.py` (полностью), `hardcode_baseline.py` в обоих репозиториях (полностью), `app/core/config.py` (1–40)
- `/opt/assistant-core/src/main.py` (634–965), `src/composition.py` (полностью), `src/brain/secretary_dialog.py` (175–200, 690–835), `src/notifier/bot_handler.py` (228–240, 905–935, 1932–1968, 2655–2690), `src/security/airgap.py` (132–157), `src/brain/key_rotator.py` (188–200), `tests/test_key_rotator.py` (111–127), `tests/test_concurrency_isolation.py` (44–60), `config/prompts/secretary_default.jinja2` (26–31)
- `/opt/assistant-core/.planning/ROADMAP.md` (288–312), `.planning/phases/04-*/04-VERIFICATION.md` (1–12, 99–118), `.planning/phases/03-*/03-VERIFICATION.md` (1–45)
- `/opt/chat-app/.planning/milestones/v2.0-MILESTONE-AUDIT.md` (полностью), `v2.0-REQUIREMENTS.md` (фрагменты DAT, SEC, HIT, ISO, FIN), `BACKLOG.md` (ACT, UXQ, строки 115–176, 280–296)
- Read-only системные команды этой сессии: `systemctl show` (chat-app и assistant-worker, без Environment), `git config core.hooksPath`, `pytest --version`, `nproc`, `free -m`, `command -v strace`

### Secondary (MEDIUM, поиск по коду и записи)
- Истории сбоев DAT-03 в `02-10-SUMMARY.md`, `261009-uo4-SUMMARY.md`, `261010-ivt-SUMMARY.md`, `STATE.md:164`
- Grep-находки: импортёры security, `send_connector_health_alert` (нет вызовов), `requires_confirmation` (нет в коде), allowlist сканера

### Tertiary (LOW, [ASSUMED])
- Гипотезы причины DAT-03, ожидаемое поведение LLM, латентность кэша (см. Assumptions Log)

## Metadata

**Confidence breakdown:**
- Точки входа и код по требованиям: HIGH для проверенных фрагментов, MEDIUM для grep-only
- Предварительные вердикты: MEDIUM (окончательные — в VERIFICATION после прогонов и проб)
- DAT-03: LOW до 30 прогонов
- Pitfalls и протоколы: HIGH (основаны на прочитанных скриптах)

**Research date:** 2026-10-18
**Valid until:** до изменения кода в assistant-core, assistant-shared или chat-app (фаза 5 не меняет код; повторная проверка нужна при любом коммите)
