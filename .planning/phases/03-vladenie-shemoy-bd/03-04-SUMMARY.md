---
phase: 03-vladenie-shemoy-bd
plan: 04
subsystem: testing
tags: [assistant-core, reachability, gate, verification, evidence, bot-handlers, dat-01, sch-01, sch-02]

requires:
  - phase: 03-vladenie-shemoy-bd
    plan: 02
    provides: "единый неблокирующий путь init_db и удаление инлайн-DDL"
  - phase: 03-vladenie-shemoy-bd
    plan: 03
    provides: "scripts/check_migration_on_copy.py и регламент выкатки"
provides:
  - "tests/test_phase3_reachability.py: тесты достижимости цепочки main -> init_db -> 0003 -> bot handlers"
  - ".planning/phases/03-vladenie-shemoy-bd/03-VERIFICATION-EVIDENCE.md: сводка доказательств R1-R5 и заготовки для планов 03-05 и 03-06"
affects: [03-05, 03-06, assistant-core]

actuals:
  tokens: 45000
  tasks: 2
  commits: 1
plan_head_before: 236ee9a
plan_head_after: 236ee9a

tech-stack:
  added: []
  patterns:
    - "AST-анализ порядка вызовов в main() и init_db() с контролем чувствительности"
    - "Сквозная проверка обработчиков бота через роутер EmailBotHandler на схеме, созданной миграцией"
    - "Сбор доказательств достижимости для верификатора GSD (R1-R5) без раскрытия персональных данных"

key-files:
  created:
    - tests/test_phase3_reachability.py
    - .planning/phases/03-vladenie-shemoy-bd/03-VERIFICATION-EVIDENCE.md
    - .planning/phases/03-vladenie-shemoy-bd/03-04-SUMMARY.md

key-decisions:
  - "D-13: Достижимость фазы 3 доказана сквозной цепочкой: AST main.py/db.py -> старт на временных БД -> реальные роуты бота"
  - "03-VERIFICATION.md пишет верификатор GSD по перечню R1-R5, данный план его не создаёт"

patterns-established:
  - "Контроль чувствительности AST-тестов: синтетическая перестановка вызовов детектируется тестом"

requirements-completed: [DAT-01, SCH-01, SCH-02]

coverage:
  - id: R1-R5
    description: "Достижимость миграции 0003 и обработчиков бота из рантайма"
    requirement: DAT-01
    verification:
      - kind: unit
        ref: "assistant-core tests/test_phase3_reachability.py (9 passed)"
        status: pass
      - kind: gate
        ref: "python3 scripts/gate.py (ИТОГ: ЗЕЛЁНЫЙ, 10 строк ✓)"
        status: pass
    human_judgment: false
---

# Итоги плана 03-04: Достижимость из рантайма и доказательства для верификатора

## 1. Task 1: tests/test_phase3_reachability.py (D-13, критерий 5)

- **Реализация тестов достижимости:**
  Создан `tests/test_phase3_reachability.py` (9 тестов):
  - `test_main_creates_database_and_awaits_init_db_before_persona_and_bot`: AST-разбор `src/main.py` подтверждает строгий порядок: инициализация `Database(config.SQLITE_DB_PATH)`, `await db.init_db()` ДО вызова `seed_persona` и ДО инстанцирования `EmailBotHandler(db=db)`.
  - `test_init_db_calls_migrations_before_seeding`: AST-разбор `src/storage/db.py` подтверждает, что `self._apply_migrations` вызывается строго раньше сидирования, а инлайн-DDL таблиц отсутствует.
  - `test_startup_on_empty_temp_db_applies_0003`: старт на чистой временной БД накатывает миграцию `0003_bot_commands_and_feedback`, все три таблицы созданы и пусты.
  - `test_startup_on_legacy_shaped_db_keeps_rows_and_adds_0003`: старт на БД формы боевой сохраняет все существующие строки трёх таблиц и фиксирует версию `0003`.
  - `test_bot_hide_show_and_alias_flows_use_migrated_tables`: реальный роутер бота `EmailBotHandler` выполняет скрытие/показ команд («скрой команду lms», «покажи команду lms») и управление алиасами («называй карточки как timesheet», «удали алиас карточки») с записью в мигрированные таблицы.
  - `test_menu_command_reads_both_tables`: обработчик команды `/menu` корректно считывает обе таблицы и формирует ответ с пометками и алиасами.
  - `test_feedback_buttons_from_keyboard_reach_the_log`: нажатия кнопок 👍/👎, сгенерированных функцией `build_dialog_feedback_keyboard`, фиксируются в `dialog_feedback_log` с дедупликацией повторных голосов.
  - `test_feedback_keyboard_is_attached_in_runtime_code`: AST-проверка подтверждает подключение клавиатуры обратной связи и регистрацию callback-обработчика по префиксу `fb:`.
  - `test_order_check_detects_reordered_calls`: контрольный тест чувствительности AST-проверки гарантирует детекцию перестановки вызовов в коде.
- **Чувствительность проверок:**
  Поведенческие проверки обработчиков бота после плана 03-02 были зелёными сразу, так как схема уже мигрирована; чувствительность тестов обеспечена прямой проверкой модификации состояния и дедупликации в БД при каждом вызове. Тест формы боевой БД утверждает отсутствие версии 0003 ДО `init_db` и её присутствие ПОСЛЕ (краснеет при отсутствии миграции). Контрольный AST-тест гарантирует падение при нарушении порядка шагов инициализации.
- **Итог проверки:** `9 passed in 4.96s`.
  Совместный прогон всех тестов фазы 3 (`test_phase3_reachability.py`, `test_init_db_migrations.py`, `test_schema_parity.py`, `test_no_inline_ddl.py`, `test_check_migration_on_copy.py`): `49 passed in 15.36s`.

## 2. Task 2: Гейт качества и сбор доказательств (03-VERIFICATION-EVIDENCE.md)

- **Гейт качества (`scripts/gate.py`):**
  - Запущен `python3 scripts/gate.py`, полный вывод сохранён в `/var/tmp/gsd-phase03-verify/gate-after-03-04.txt`.
  - Вердикт: **ИТОГ: ЗЕЛЁНЫЙ** (10 строк из 10 со статусом ✓).
  - Тесты: 1027 passed в `assistant-core`, 202 passed в `assistant-shared`.
  - Боевая база данных `data/assistant.db` **НЕ ОТКРЫВАЛАСЬ** на запись: SHA-256 боевой БД до и после совпали (`7d071cf43c1c`).
- **Файл доказательств (`.planning/phases/03-vladenie-shemoy-bd/03-VERIFICATION-EVIDENCE.md`):**
  - Сформирован сводный документ доказательств с перечнем достижимости R1-R5.
  - Содержит разделы-заготовки: «Копия боевой БД» (заполняет план 03-05), «Рестарт и смоук» (заполняет план 03-06), «Живые проверки» (заполняет план 03-06) и «Открытые пункты».
  - Автоматически проверен на отсутствие адресов e-mail, токенов ботов и ключевых слов NDA.
  - Пометка: `03-VERIFICATION.md` пишет верификатор GSD по перечню R1-R5, этот план его не создаёт.
