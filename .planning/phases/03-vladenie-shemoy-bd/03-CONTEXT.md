# Phase 3: Владение схемой БД - Context

**Gathered:** 2026-10-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Схема БД принадлежит только миграциям `/opt/assistant-shared`. Три таблицы (`bot_command_settings`, `bot_custom_aliases`, `dialog_feedback_log`) переезжают из инлайн-DDL `src/storage/db.py` в миграцию `0003_*.sql`. Ветки `:memory:` и файловой БД идут одним неблокирующим путём миграций.

Требования: DAT-01, SCH-01, SCH-02 (`.planning/REQUIREMENTS.md`). Новых возможностей фаза не добавляет. Боевая БД не открывается и не меняется при разработке и тестах.

</domain>

<decisions>
## Implementation Decisions

### Единый путь миграций (SCH-01)
- **D-01:** В `Database` появляется один общий метод применения миграций. Для файловой БД он передаёт путь, для `:memory:` — единственное разделяемое sqlite3-соединение (оно уже `check_same_thread=False`). Обе ветки вызывают `asyncio.to_thread(run_migrations, цель)`, цикл событий не блокируется. Правки мигратора в `assistant-shared` не нужны. — **Reversibility:** reversible — локальная правка одного класса.
- **D-02:** Всё, что идёт после миграций (`_seed_initial_data_if_empty` и прочее), выносится в общий хвост `init_db`, одинаковый для обеих веток. Поведение сидирования не меняется. Дублирование блоков в двух ветках исчезает.
- **D-03:** Ветка `:memory:` сохраняется (тесты на ней живут). Переход на временные файлы и общий URI в памяти не выбраны.

### Форма миграции 0003 (DAT-01)
- **D-04:** `0003_*.sql` содержит точную копию текущего инлайн-DDL всех трёх таблиц с `CREATE TABLE IF NOT EXISTS`, без новых индексов, `CHECK` и смены DEFAULT. На боевой БД, где таблицы уже есть, миграция — no-op и не трогает данные. Усиления схемы (в том числе индекс по `dialog_feedback_log(message_id)`) — вне фазы. — **Reversibility:** one-way — применённая версия фиксируется в `schema_migrations` боевой БД и в chat-app, откат требует новой миграции.
- **D-05:** Проверка на копии боевой БД: копия делается во временный каталог (SQLite backup API, источник `?mode=ro`), хеш оригинала SHA-256 до и после совпадает, миграция применяется к копии, содержимое трёх таблиц до и после идентично. Сам оригинал тест не открывает на запись.
- **D-06:** (из Phase 1 D-11) Боевая БД мигрирует сама только при рестарте `assistant-worker`, разрешённом владельцем, по процедуре OPS-01. Выкатка идёт с флагом `--backup` перед применением `0003`; это шаг процедуры в плане и в VERIFICATION.md.

### Согласование с chat-app (SCH-02)
- **D-07:** Тест chat-app `backend/tests/test_migrations.py` жёстко ждёт ровно `0001` и `0002` (`ALL_MIGRATIONS`, `LATEST_SCHEMA_VERSION`, проверки `in applied`). После добавления `0003` он краснеет. Поэтому правка chat-app идёт одним `/gsd-quick` в chat-app **в том же проходе**, чтобы на момент коммита `0003` pytest chat-app не был красным. Прямых правок chat-app из assistant-core нет.
- **D-08:** Новый тест chat-app выводит `ALL_MIGRATIONS` и последнюю версию из каталога `*.sql` в `assistant-shared`, а `EXPECTED_CORE_TABLES` пополняется тремя таблицами. Список больше не надо править при каждой новой миграции.
- **D-09:** chat-app не создаёт эти таблицы сам (инлайн-DDL по ним в chat-app отсутствует, проверено поиском). SCH-02 подтверждается тестом: после общего мигратора таблицы есть. В assistant-shared есть собственный `tests/test_migrations.py` с `BASELINE_MIGRATIONS`, его тоже нужно обновить.

### Тест паритета и защита от инлайн-DDL
- **D-10:** Тест паритета сравнивает множество `(type, name, нормализованный sql)` из `sqlite_master` для трёх источников: `:memory:` после `init_db`, файловая БД после `init_db`, чистая БД после `run_migrations` из `assistant-shared`. Покрывает таблицы, индексы и триггеры; ловит расхождение порядка колонок и DEFAULT. Нормализация: схлопывание пробелов и регистра, исключение служебных `sqlite_*` и `schema_migrations.applied_at`-значений.
- **D-11:** Защитный тест сканирует исходники всех файлов `src/` и падает на любом `CREATE TABLE|CREATE INDEX|CREATE VIRTUAL TABLE|CREATE TRIGGER|ALTER TABLE` в строках кода. Без белого списка. Проверка: сейчас такой DDL есть только в `src/storage/db.py`, в остальном `src/` его нет. Тест входит в обычный pytest и поэтому в гейт.
- **D-12:** Тест на неблокирование: в обеих ветках `init_db` не держит цикл событий (параллельная корутина-«пульс» продолжает тикать во время миграции).

### Достижимость из рантайма (критерий 5)
- **D-13:** VERIFICATION.md показывает цепочку `src/main.py` → `Database.init_db` на временной БД: применяется `0003`, затем работают функции на этих таблицах (алиасы и скрытие команд, обратная связь 👍/👎) на мигрированной схеме.

### Claude's Discretion
- Имя файла `0003_*.sql` (по смыслу, в стиле `0002_pending_confirmations`).
- Имя общего метода миграций и способ получения «сырого» sqlite3-соединения из aiosqlite.
- Точная нормализация SQL в тесте паритета и способ статического поиска DDL (regex или ast).
- Порядок и разбиение на планы; какие шаги делегировать в agy по правилам CLAUDE.md (правки ≥4 файлов однотипные — вряд ли).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Требования и роадмап
- `.planning/ROADMAP.md` §«Phase 3: Владение схемой БД» — цель и 5 критериев успеха
- `.planning/REQUIREMENTS.md` — DAT-01, SCH-01, SCH-02 (и UXQ-02, зависящий от DAT-01)
- `.planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-CONTEXT.md` D-11 — выкатка с `--backup` перед миграцией `0003`
- `docs/OPS_DEPLOY.md` — процедура выкатки, рестарт только по разрешению владельца

### Код
- `src/storage/db.py` строки 56–135 — `init_db` с двумя ветками и инлайн-DDL; функции на таблицах — строки ~2940–3035
- `/opt/assistant-shared/assistant_shared/db/migrator.py` — `run_migrations`, `BEGIN IMMEDIATE`, baseline-логика
- `/opt/assistant-shared/assistant_shared/db/migrations/` — `0001_initial_schema.sql`, `0002_pending_confirmations.sql`
- `/opt/assistant-shared/tests/test_migrations.py` — `BASELINE_MIGRATIONS`
- `/opt/chat-app/backend/tests/test_migrations.py` — жёсткий список миграций (правка только через `/gsd-quick`)
- `scripts/gate.py` — гейт; новые тесты должны входить в него без исключений

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `assistant_shared.db.migrator.run_migrations` — принимает путь, sqlite3 и aiosqlite-соединение; безопасен при конкурентном запуске.
- `make_db_copy` из `/opt/chat-app/scripts/gate.py` и бэкап-логика Phase 1 в `scripts/` — шаблон копии боевой БД через `?mode=ro`.
- Проверка SHA-256 боевой БД до и после прогона в `scripts/gate.py` (GATE-02).

### Established Patterns
- Миграции — последовательные SQL-файлы, `IF NOT EXISTS` для совместимости с baseline-БД.
- `Database.connection()` — `@asynccontextmanager`, для `:memory:` одно разделяемое соединение.
- Миграция уже вынесена в поток для файловой БД (WR-06), `:memory:` вызывает её синхронно в цикле.

### Integration Points
- `src/main.py` → `Database.init_db` при старте демона.
- chat-app как потребитель использует общий мигратор в `backend/tests/conftest.py` и `test_hitl_shared.py`.

</code_context>

<specifics>
## Specific Ideas

- Для `:memory:` берётся то же разделяемое sqlite3-соединение, что у `Database.connection()`; поток-обёртка допустима, потому что соединение создано с `check_same_thread=False`, а инициализация идёт до старта прочей работы.

</specifics>

<deferred>
## Deferred Ideas

- Индекс по `dialog_feedback_log(message_id)` и прочие усиления схемы (`CHECK`, `NOT NULL`) — отдельная миграция после фазы.
- Перевод тестов с `:memory:` на временные файлы — не нужен, пока ветка работает одним путём.

</deferred>

---

*Phase: 3-Владение схемой БД*
*Context gathered: 2026-10-10*
