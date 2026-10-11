---
phase: 03-vladenie-shemoy-bd
verified: 2026-10-11T09:00:00Z
status: passed
score: 5/5 must-haves verified
covered_files:
  - .planning/phases/03-vladenie-shemoy-bd/03-01-PLAN.md
  - .planning/phases/03-vladenie-shemoy-bd/03-01-SUMMARY.md
  - .planning/phases/03-vladenie-shemoy-bd/03-02-PLAN.md
  - .planning/phases/03-vladenie-shemoy-bd/03-02-SUMMARY.md
  - .planning/phases/03-vladenie-shemoy-bd/03-03-PLAN.md
  - .planning/phases/03-vladenie-shemoy-bd/03-03-SUMMARY.md
  - .planning/phases/03-vladenie-shemoy-bd/03-04-PLAN.md
  - .planning/phases/03-vladenie-shemoy-bd/03-04-SUMMARY.md
  - .planning/phases/03-vladenie-shemoy-bd/03-05-PLAN.md
  - .planning/phases/03-vladenie-shemoy-bd/03-05-SUMMARY.md
  - .planning/phases/03-vladenie-shemoy-bd/03-06-PLAN.md
  - .planning/phases/03-vladenie-shemoy-bd/03-06-SUMMARY.md
  - docs/OPS_DEPLOY.md
  - scripts/check_migration_on_copy.py
  - src/storage/db.py
  - tests/test_check_migration_on_copy.py
  - tests/test_init_db_migrations.py
  - tests/test_no_inline_ddl.py
  - tests/test_phase3_reachability.py
  - tests/test_schema_parity.py
covered_digest: "v3:sha256:f921ce30fb50d215d8b622d941c03a689eee2fd4785762982787dadf43529dc6"
behavior_unverified: 0
overrides_applied: 0
gaps: []
human_verification: []
---

# Phase 3: Владение схемой БД. Отчёт верификации

**Цель фазы:** Схема БД принадлежит только миграциям `/opt/assistant-shared`, а тесты и боевой запуск используют один и тот же неблокирующий путь миграций. Это закрывает расщепление владения схемой между репозиториями.
**Проверено:** 2026-10-11
**Статус:** passed (все 5 критериев успеха ROADMAP подтверждены кодом, герметичными тестами, гейтом качества и живыми данными рантайма)
**Повторная верификация:** нет, первичная

Три репозитория проверены по факту:
- `/opt/assistant-core` (main, коммиты планов `833514f`, `5413266`, `236ee9a`, `2ffa865`, `de2dbae`, `1c097c3`).
- `/opt/assistant-shared` (master, коммит `5c85613`).
- `/opt/chat-app` (master, коммит `011f9c2`).

Проверка выполнена строго по принципу Goal-backward: факты проверены независимым чтением кода, выполнением тестов и скриптов проверки. Боевая БД на запись агентом не открывалась, `.env` не читался, персональные данные владельца и адреса e-mail в отчёт не вносятся.

## Достижение цели

### Наблюдаемые истины (критерии успеха ROADMAP)

| # | Истина | Статус | Доказательства |
|---|--------|--------|----------------|
| 1 | Таблицы `bot_command_settings`, `bot_custom_aliases`, `dialog_feedback_log` создаются миграцией `0003_*.sql` в `/opt/assistant-shared`, а в `src/storage/db.py` нет инлайн-`CREATE TABLE` ни в одной из двух веток (DAT-01) | ✓ VERIFIED | Файл `/opt/assistant-shared/assistant_shared/db/migrations/0003_bot_commands_and_feedback.sql` создан (коммит `5c85613`), содержит канонические DDL трёх таблиц с триггером `update_bot_command_settings_updated_at`. В `src/storage/db.py` инлайн-DDL полностью удалён из обеих веток (коммит `5413266`). Сканер DDL без белого списка `tests/test_no_inline_ddl.py` проверил все файлы каталога `src/` (13 passed, 0 находок) |
| 2 | На копии боевой БД, сделанной во временный каталог при неизменном хеше оригинала, миграция применяется без изменения существующих данных (DAT-01) | ✓ VERIFIED | Создан скрипт `scripts/check_migration_on_copy.py` (backup API, режим подключения strictly `mode=ro`, копия во временном каталоге 0700). Проверено на синтетическом источнике формы боевой (`tests/test_check_migration_on_copy.py`, 10 passed). Выполнена живая проверка на боевой БД с разрешения владельца (`scripts/check_migration_on_copy.py --source data/assistant.db`): хеш источника до и после совпал (`47559fb19642`), данные таблиц до и после идентичны, вердикт `ИТОГ: ЗЕЛЁНЫЙ` |
| 3 | Ветки `:memory:` и файловой БД используют один путь миграций, ни одна не блокирует event loop, а тест паритета подтверждает совпадение схемы `:memory:`, файловой БД и миграций `assistant-shared` (SCH-01) | ✓ VERIFIED | В `src/storage/db.py` реализован единый метод `_apply_migrations` с единственным вызовом `await asyncio.to_thread(run_migrations, target)` (для `:memory:` передаётся коннект, для файла — путь). Тест `tests/test_init_db_migrations.py` (12 passed) проверяет единый путь и фоновый поток. Тест `tests/test_schema_parity.py` (5 passed) доказывает попарный паритет всех 85 объектов схемы между чистой БД мигратора, `:memory:` и файловой БД |
| 4 | `chat-app` получает таблицы `0003` через общий мигратор и не создаёт их сам, его pytest остаётся зелёным. Любая правка chat-app делается только через `/gsd-quick` (SCH-02) | ✓ VERIFIED | Тесты `chat-app` согласованы с динамическим каталогом миграций библиотеки `assistant-shared` (коммит `011f9c2`, сделан до релиза библиотеки через `/gsd-quick`). Все 279 тестов `chat-app` пройдены успешно (100% зелёный прогон). Собственного DDL таблиц бота в `chat-app` нет |
| 5 | VERIFICATION.md показывает достижимость из рантайма: старт демона (`src/main.py` → `Database.init_db`) на временной БД применяет `0003`, а функции на этих таблицах работают на мигрированной схеме. Боевая БД мигрирует сама только при рестарте по процедуре OPS-01 с резервной копией (DAT-01, SCH-01, SCH-02) | ✓ VERIFIED | Тест достижимости `tests/test_phase3_reachability.py` (9 passed) доказывает цепочку через AST `main.py`/`db.py`, старт на временных БД и выполнение реальных обработчиков бота. Выкатка выполнена по регламенту OPS-01 (`scripts/deploy.py --backup --restart`): создана резервная копия `/var/backups/assistant-core/assistant-20261011-005251.db` (8.7 MB), смоук `ИТОГ СМОУКА: ЗЕЛЁНЫЙ`. Владелец подтвердил живые ответы бота на `/help` и `/menu`, нажатие кнопки отзыва зафиксировано строкой в `dialog_feedback_log`. Повторная проверка на копии после рестарта подтвердила присутствие `0003` в боевой БД (`83fece373834`, ЗЕЛЁНЫЙ) |

**Оценка:** 5/5 критериев подтверждены. Непроверенных поведенческих истин (`behavior_unverified`): 0.

### Охват требований (REQUIREMENTS.md)

| Требование | Планы | Описание | Статус | Доказательства |
|------------|-------|----------|--------|----------------|
| DAT-01 | 03-01, 03-02, 03-03, 03-04, 03-05, 03-06 | Перенос владения схемы трёх таблиц бота в assistant-shared (0003) и удаление инлайн-DDL | ✓ SATISFIED | Миграция `0003_bot_commands_and_feedback.sql`, удаление инлайн-DDL из `db.py`, проверка на герметичной копии, живой запуск и рестарт |
| SCH-01 | 03-02, 03-04, 03-06 | Единый неблокирующий путь init_db и паритет схемы | ✓ SATISFIED | Метод `_apply_migrations` в рабочем потоке `asyncio.to_thread`, паритет 85 объектов схемы (`test_schema_parity.py`) |
| SCH-02 | 03-01, 03-04, 03-06 | Согласование потребителя chat-app без поломки тестов | ✓ SATISFIED | Коммит `chat-app` `011f9c2`, 279 passed, импорт мигратора из `assistant-shared` |

Все требования фазы присутствуют в `requirements:` frontmatter планов. Потерянных или неучтённых требований нет.

### Достижимость из рантайма (R1-R5)

| Пункт | Автоматическое доказательство | Живое доказательство | Статус |
|-------|-------------------------------|----------------------|--------|
| R1. Старт демона и init_db | AST-проверка порядка вызовов в `src/main.py` и `src/storage/db.py`, старт на временных БД применяет 0003 (`tests/test_phase3_reachability.py`) | Автоматический смоук без ошибок в окне старта (`03-SMOKE-REPORT.md`), версия `0003` подтверждена в боевой БД после рестарта | ✓ passed |
| R2. Обработчики бота на схеме | Тест реального роутера `EmailBotHandler`: «скрой/покажи команду», алиасы, /menu, 👍/👎 с дедупликацией на мигрированной схеме | Живой ответ бота на `/help` и `/menu` в Telegram; нажатие кнопки 👍/👎 зафиксировано строкой в `dialog_feedback_log` | ✓ passed |
| R3. Единый неблокирующий путь | `tests/test_init_db_migrations.py` (12 passed), `tests/test_no_inline_ddl.py` (13 passed), `tests/test_schema_parity.py` (5 passed) | Подтверждено автоматическими тестами, живой шаг не требуется | ✓ passed |
| R4. chat-app получает таблицы | `chat-app` коммит `011f9c2`, отдельный прогон pytest: 279 passed | Подтверждено тестами потребителя | ✓ passed |
| R5. Копия БД, выкатка и рестарт | `scripts/check_migration_on_copy.py` (10 passed), регламент раздела 13 `docs/OPS_DEPLOY.md` (198 passed) | Копия до рестарта: ЗЕЛЁНАЯ; бэкап 8.7 MB; рестарт по разрешению владельца; смоук ЗЕЛЁНЫЙ; контрольная копия после рестарта: ЗЕЛЁНАЯ | ✓ passed |

### Поведенческие проверки

| Набор проверок | Команда | Результат | Статус |
|----------------|---------|-----------|--------|
| Тесты фазы 3 в assistant-core | `pytest tests/test_init_db_migrations.py tests/test_schema_parity.py tests/test_no_inline_ddl.py tests/test_check_migration_on_copy.py tests/test_phase3_reachability.py` | 49 passed | ✓ PASS |
| Полный pytest assistant-core | `.venv/bin/pytest tests` | 1027 passed | ✓ PASS |
| Полный pytest assistant-shared | `pytest tests` в `/opt/assistant-shared` | 202 passed | ✓ PASS |
| Полный pytest chat-app | `pytest` в `/opt/chat-app/backend` | 279 passed | ✓ PASS |
| Гейт качества проекта | `python3 scripts/gate.py` | ИТОГ: ЗЕЛЁНЫЙ (10 из 10 строк ✓, hash боевой БД совпал) | ✓ PASS |
| Проверка на копии до рестарта | `python3 scripts/check_migration_on_copy.py --source data/assistant.db` | ИТОГ: ЗЕЛЁНЫЙ, hash 47559fb19642 совпал | ✓ PASS |
| Смоук OPS-01 после рестарта | `python3 scripts/deploy.py --confirm-help yes --report ...` | ИТОГ СМОУКА: ЗЕЛЁНЫЙ | ✓ PASS |
| Проверка на копии после рестарта | `python3 scripts/check_migration_on_copy.py --source data/assistant.db` | ИТОГ: ЗЕЛЁНЫЙ, hash 83fece373834 совпал, 0003 подтверждена | ✓ PASS |

## Антипаттерны и технический долг

- Строка в `.planning/codebase/CONCERNS.md` о недостающей миграции 0003 переведена в статус `Resolved (Phase 3)` со ссылкой на коммиты `5c85613`, `5413266` и `011f9c2`.
- Заглушек, блокирующих комментариев или обходов проверок в коде фазы нет.
- Все обращения к боевой БД производятся строго в режиме `mode=ro` (read-only) через sqlite3 backup API.

## Открытые пункты и решения человека

1. Усиления схемы (дополнительные индексы, ограничения CHECK, NOT NULL) отложены на отдельную миграцию решением владельца D-04.
2. Сервис потребителя `chat-app.service` во время выкатки не перезапускался; его рестарт не требовался, так как библиотека `assistant-shared` подключена в виртуальном окружении в editable/symlinked режиме.

## Резюме пробелов

Пробелов (`gaps: []`) не обнаружено. Все 5 критериев успеха выполнены в полном объёме, подтверждены автоматическими тестами, гейтом качества и живым поведением в рантайме. Фаза готова к закрытию со статусом `passed`.

---

_Проверено: 2026-10-11_  
_Верификатор: Claude (gsd-verifier)_
