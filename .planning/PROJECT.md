# Assistant Core — персональный ассистент-секретарь

## What This Is

`assistant-core` — демон персонального ассистента (`assistant-worker.service`). Он работает круглосуточно: собирает почту, расписание, табель, LMS и Telegram, готовит брифинги и дайджесты, а через Telegram-бота ведёт диалог секретаря с реальными инструментами (календарь, напоминания, черновики писем). Сейчас платформа настроена на одного владельца (преподаватель-физик ГУАП и исследователь в Тидекс). Цель — превратить её в универсальную, настраиваемую данными платформу для любого специалиста. Профиль владельца уже вынесен в `config/persona.yaml`.

## Core Value

Ассистент надёжно выполняет ежедневную работу секретаря. При этом **ни одно содержимое NDA-пространств не уходит во внешнюю LLM** и **ни одно необратимое действие не выполняется без подтверждения человека (HITL)**.

## Requirements

### Validated

<!-- Выполнено в цикле v2.0 «Универсальная платформа» (общий .planning chat-app, тег v2.0) и подтверждено аудитом v2.0. -->

- ✓ Локальная страховочная сеть: baseline тестов, контракты import-linter (`core-is-pure`, `brain-no-adapters`, `live-ticker-no-adapters`), вторая синтетическая персона, единая команда-гейт — v2.0 (FND-01..04)
- ✓ Порты и домен: неизменяемые сущности в `src/core/domain`, async-порты `BaseConnector`/`BaseTimesheetProvider`/`BaseScheduleProvider`/`BaseCalendarSink`/`BaseLMSProvider`, адаптеры, корень композиции `src/composition.py`, конструкторная инъекция, внутрипроцессный `EventBus` — v2.0 (PRT-01..05)
- ✓ Персона как данные: `config/persona.yaml` (Pydantic, `extra=forbid`), таблицы `personas`/`workspaces`/`connector_bindings`, NDA-правила как данные рабочих пространств, Jinja2-промпты с побайтовыми эталонами, сканер хардкода с сокращаемым baseline, `test_persona_config.py` — v2.0 (PER-01..09)
- ✓ Обратная совместимость: персона `popov-da-default` воспроизводит прежнее поведение 1:1 — v2.0 (BCK-01..02)
- ✓ Собственный гейт качества `python3 scripts/gate.py` (10 строк: assistant-core и assistant-shared, ИТОГ «ЗЕЛЁНЫЙ»/«КРАСНЫЙ» по-русски), страж боевой БД в тестах, тесты и pre-commit hook assistant-shared, cross-AI адаптер запускает гейт цели, скрипт выкатки `scripts/deploy.py` (read-only смоук, `--backup`/`--restart` только по флагу) и `docs/OPS_DEPLOY.md` — Phase 1 (GATE-01..05, OPS-01)
- ✓ Существующие возможности демона: сборщики почты/Telegram/расписания/LMS/табеля AADHk, утренний и вечерний дайджест, методист, голосовой ввод (Groq Whisper), живое табло `/ticker`, ротация ключей Gemini — existing
- ✓ Предупреждение о внешней обработке почты ИИ-сервисами: текст из данных персоны в `/help` и при первом цикле почты (ровно одно сообщение, флаг в БД), вывод в `scripts/auth_google.py` — Phase 2 (PRIV-01)
- ✓ NDA-режим и аудит безопасности определяются данными рабочих пространств (`match_workspace`, fail-closed), в общей библиотеке нет доменных литералов и `CORPORATE_NDA_KEYWORDS`; hook, shield и CLI берут правила из `persona.yaml` — Phase 2 (SECF-01)
- ✓ Паритет web и CLI аудита: общая функция `scan_file_content`, web ищет слова NDA других пространств — Phase 2 (SECF-02)
- ✓ Текст и голос «очисти диалог» только предупреждают; очистка памяти диалога — лишь `/clear` через HITL-карточку — Phase 2 (SAFE-01)
- ✓ Находки ревью Phase 1 закрыты по прогнанным тестам (14 fixed, 6 deferred): path traversal Google Drive, `deploy.py`, `gate.py`, страж боевой БД, адаптер cross-AI — Phase 2 (DEBT-03 записан)
- ✓ Владение схемой БД: миграция `0003` в `/opt/assistant-shared`, единый путь Database, ветка `:memory:` не блокирует event loop — Phase 3 (DAT-01, SCH-01, SCH-02)
- ✓ Git → оценка → HITL → Notion достижимо из рантайма: `GitProgressEvaluator` в планировщике и команде /git бота, fail-closed airgap, карточки HITL в Notion — Phase 4 (GIT-01..04, NTN-01..02)

### Active

<!-- Цикл v3.0. Требования с ID — в REQUIREMENTS.md. -->

**Сквозные цепочки в рантайме**
- [ ] Web-карточки HITL доставляются в Telegram: поллер `ConfirmationChannel.WEB` + `send_web_hitl_card` (HIT-02..04)

**Ретро-верификация v2.0**
- [ ] VERIFICATION фаз 4–9 v2.0 по факту: DAT, SEC, HIT-01, ISO-01/03/04, FIN-01, ACT-01..04, UXQ-01/02/04

**Интерфейс**
- [ ] UXQ-03 (план 09-03 в новом виде): быстрые действия с учётом времени суток без постоянной Reply-клавиатуры

**Онбординг (ONB-CON)**
- [ ] ONB-01: мастер первого запуска создаёт персону
- [ ] ONB-02: подключение и отключение коннекторов из диалога с `health_check`
- [ ] ONB-03: настройка брифингов и дайджестов через диалог

### Out of Scope

- **GSD-AGENT** (обучение chat-app стандарту GSD, фоновые субагенты в web-чате): целиком на стороне chat-app, а его планирование заморожено (решение владельца 2026-10-09).
- **Правки chat-app** сверх мелких `/gsd-quick` в его собственном репозитории: chat-app — потребитель схемы, отдельно не развивается.
- **ONB-04/05** (проактивный секретарь, поэтапное раскрытие функций): следующий цикл, после того как заработают ONB-01..03.
- **RUS-LOC, SPEC-AGENTS, CHAT-BUILDER (BLD-01..08)**: крупные инициативы следующих циклов. Первый цикл стабилизирует платформу.
- **Маскирование метаданных NDA-почты (тема, отправитель, дата)**: NDA-ящика сейчас нет, а его подключение — сложная отдельная задача (v2, NDAM-01). Существующая маскировка тела NDA-писем остаётся (решение владельца 2026-10-09).
- **Постоянная экранная Reply-клавиатура** (исходный 09-03): загромождает экран смартфона; отклонена владельцем 2026-10-07.
- **CORS и аутентификация Web API (OPS-05)**: это chat-app.
- **Разделение `bot_handler.py`/`db.py` (>3000 строк)**: важный долг, но рефакторинг ради рефакторинга вне цикла. Касаемся только по месту правок.

## Context

- **Brownfield.** Python, асинхронный демон в одном процессе: aiogram + APScheduler, хранилище — aiosqlite поверх `assistant_shared.db`. LLM — Gemini (`google-genai`) с ротацией ключей по персоне; Telethon для сбора Telegram; OAuth Google Calendar/Drive/Gmail; Notion API; IMAP/SMTP. Подробно — в `.planning/codebase/`.
- **Тесты:** 789 тестов pytest assistant-core (`asyncio_mode = auto`, базовая линия плана 01-05) в плоском `tests/` и 91 тест assistant-shared, эталоны промптов в `tests/fixtures/prompts_snapshot/`. Покрытие не измеряется, ruff/mypy не настроены.
- **Гейт собственный:** команда `python3 scripts/gate.py` из `/opt/assistant-core` (скрипт `scripts/gate.py`); десять строк: assistant-core (pytest, хеш боевой БД до и после, import-linter, security_shield с замороженным списком ложных срабатываний, дрейф `synthetic_persona.py` и `persona_tokens.py` против копий chat-app только на чтение, hook установлен) и assistant-shared (pytest, security_shield, hook установлен); ЗЕЛЁНЫЙ на 2026-10-09 (789 тестов core, 91 тест shared). Хотя `src/config.py` вызывает `load_dotenv(..., override=True)`, теперь БД тестов подменяется `ASSISTANT_DB_PATH_OVERRIDE` (читается до `load_dotenv`), а страж `tests/live_db_guard.py` и хеш боевой БД дают двойную защиту. Общий гейт chat-app остаётся неизменным гейтом потребителя (D-15).
- **Общий код:** `/opt/assistant-shared` — владелец схемы БД (мигратор, миграции `0001`, `0002`), HITL-примитив `pending_confirmations` и библиотека безопасности. assistant-core — сторона владельца схемы, chat-app — потребитель. У assistant-shared есть собственные тесты (91) и pre-commit hook, их запускает собственный гейт (WR-11 закрыт).
- **История:** цикл v2.0 закрыт с оговоркой (override closeout): 20 из 42 требований подтверждено, у фаз 4–9 нет VERIFICATION.md. Справка (только чтение): `/opt/chat-app/.planning/MILESTONES.md`, `RETROSPECTIVE.md`, `milestones/v2.0-*`, `BACKLOG.md`.
- **Уроки v2.0:** юнит-тесты не доказывают, что функция достижима из рантайма (две цепочки оказались «сиротами»). SUMMARY пишется в том же прогоне, что и код. Тесты-ловушки пишутся до правки. Security-логика только ужесточается (fail-closed).
- **Найдено при онбординге (карта кода):** импортируются, но не объявлены в `requirements.txt` пакеты `imapclient`, `pypdf`, `html2text`, `requests`, `assistant-shared`. Dockerfile на Python 3.11 при целевом 3.12. В корне лежит неотслеживаемый каталог-артефакт `sqlite+aiosqlite:/`. Синхронный sqlite3 в `src/connectors/aadhk/parser.py`. 77 широких `except`.
- **Делегирование:** рутина — агентам Antigravity только через `/opt/chat-app/scripts/agy_task.sh`, а исполнение механических планов — через cross-AI адаптер `/opt/chat-app/scripts/agy_cross_ai.sh --repo /opt/assistant-core`. Пробный прогон 2026-10-09: rc 0, гейт ЗЕЛЁНЫЙ, патч без коммита. Claude читает патч целиком, гоняет гейт и коммитит сам.

## Constraints

- **Боевая БД**: `/opt/assistant-core/data/assistant.db` не открывать и не менять при разработке и тестах — живые данные владельца.
- **Сервисы**: `assistant-worker.service` и `chat-app.service` заморожены. Рестарт assistant-worker — только после фазы с изменениями рантайма, по явному разрешению владельца, со смоук-проверкой.
- **Качество**: тесты проходят на 100%. Пропуски, xfail и deselected делают гейт красным.
- **Безопасность**: HITL для любого необратимого действия; Air-Gap NDA (содержимое `restricted_nda` не уходит во внешнюю LLM); security-проверки только ужесточаются, fail-closed.
- **Стек**: Python 3.12, async-first (aiosqlite, httpx/aiohttp), Pydantic/dataclass. Новые зависимости — только с одобрения владельца.
- **Ресурсы VPS**: 2 ГБ RAM + 4,5 ГБ swap. Для Node — `NODE_OPTIONS="--max-old-space-size=1536"`.
- **Язык**: всё, что видит пользователь, — по-русски. Код и коммиты — по-английски или по-русски.
- **Git**: коммиты прямо в `main` разрешены, без worktree.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Отдельный GSD-проект assistant-core, планирование chat-app заморожено | Один `.planning/` на два репозитория связывал сервисы и раздувал гейт (урок v2.0) | ✓ Good |
| Первый цикл — v3.0, фазы с 1 | Продолжение истории после v2.0 | — Pending |
| Порядок: гейт → NDA → схема → проводка → ретро-верификация → UXQ-03 → онбординг | Сначала инструмент проверки, затем безопасность и целостность, потом функции | — Pending |
| Собственный гейт проверяет assistant-core и assistant-shared | Закрывает WR-11; общий gate.py тестирует оба сервиса | ✓ Good (Phase 1: 3 зелёных прогона подряд) |
| В v3.0 из инициатив — только ONB-01..03 | Цикл стабилизации плюс один шаг к универсальной платформе | — Pending |
| UXQ-03 переосмыслен: без постоянной Reply-клавиатуры | Владелец отклонил загромождение экрана 2026-10-07 | — Pending |
| NDA-почта не развивается в v3.0, вместо этого — предупреждение об обработке почты ИИ | Такой почты сейчас нет, задача подключения сложная | — Pending |
| Рестарт сервиса — после фазы, по запросу, со смоук-проверкой | Проверка «достижимо из рантайма» без бесконтрольной разморозки | ✓ Good (Phase 2: рестарт владельцем, смоук ЗЕЛЁНЫЙ, живые проверки пройдены) |
| Хеш боевой БД в гейте: при записи работающего сервиса один тихий повторный замер | Работающий assistant-worker законно пишет в БД во время pytest; основная защита — страж тестов | — Pending (WR-03 ревью: пересмотреть в Phase 2) |
| 20 находок код-ревью Phase 1 (вкл. CR-01 path traversal в gdrive) — в Phase 2 | Phase 2 целиком про безопасность и находки ревью | ✓ Good (14 fixed, 6 deferred) |
| cross-AI исполнение через agy_cross_ai.sh, без автокоммита | agy сообщает SUCCESS на неполной работе — результат проверяет Claude | ✓ Good |
| NDA-режим из данных рабочих пространств; shield в shared и chat-app — делегаторы в assistant-core | Один источник правил, нет личных литералов в общей библиотеке, fail-closed | ✓ Good (Phase 2) |
| Три известные находки слов NDA в `config/persona.yaml` остаются; единственный `--no-verify` при коммите файла персоны (95812d1) по согласию владельца (D-21) | Hook блокирует файл, который сам объявляет слова; допусков слов нет, shield и hook не ослаблены | ⚠ Revisit (решение Phase 8) |
| Предупреждения ревью Phase 2 (WR-01..WR-06, IN-01..IN-05) приняты как отложенные риски 2026-10-10 | Не ломают критерии фазы; WR-01 и WR-02 исправить до Phase 8 (мастер персоны) | ⚠ Revisit |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-10-10 after Phase 2*
