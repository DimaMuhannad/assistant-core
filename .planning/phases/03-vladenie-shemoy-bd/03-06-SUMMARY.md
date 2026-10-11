---
phase: 03-vladenie-shemoy-bd
plan: 06
subsystem: ops
tags: [assistant-core, deploy, smoke, live-verification, backup, telegram, dat-01, sch-01, sch-02]

requires:
  - phase: 03-vladenie-shemoy-bd
    plan: 05
    provides: "согласование владельца и проверка миграции на герметичной копии"
provides:
  - ".planning/phases/03-vladenie-shemoy-bd/03-SMOKE-REPORT.md: регламентный отчёт смоука после выкатки и подтверждения"
  - ".planning/phases/03-vladenie-shemoy-bd/03-VERIFICATION-EVIDENCE.md: финальные доказательства достижимости R1-R5 для верификатора"
  - ".planning/codebase/CONCERNS.md: строка миграции 0003 закрыта"
affects: [assistant-core]

actuals:
  tokens: 42000
  tasks: 3
  commits: 1
plan_head_before: de2dbae
plan_head_after: de2dbae

tech-stack:
  added: []
  patterns:
    - "Регламентная выкатка по процедуре OPS-01 с резервной копией БД (backup API, mode=ro) и автоматическим смоуком"
    - "Фазы подтверждения без TTY (--await-help и --confirm-help) через интерактивный диалог с владельцем"
    - "Сквозные живые проверки команд бота (/help, /menu) и кнопок обратной связи в Telegram"
    - "Контрольная проверка на копии после рестарта для подтверждения no-op статуса миграции"

key-files:
  created:
    - .planning/phases/03-vladenie-shemoy-bd/03-SMOKE-REPORT.md
    - .planning/phases/03-vladenie-shemoy-bd/03-06-SUMMARY.md
  modified:
    - .planning/phases/03-vladenie-shemoy-bd/03-VERIFICATION-EVIDENCE.md
    - .planning/codebase/CONCERNS.md

key-decisions:
  - "D-06: Рестарт assistant-worker.service выполнен по строгому согласованию владельца (check-and-restart) с предварительной резервной копией"
  - "D-08 / D-13: Критерий успеха 5 доказан живыми данными: смоук ЗЕЛЁНЫЙ, бот ответил на /help и /menu, отзыв записан в dialog_feedback_log"
  - "chat-app.service не перезапускался"
  - "03-VERIFICATION.md пишет верификатор GSD по перечню R1-R5, этот план его не создаёт"

patterns-established:
  - "Полный цикл выкатки схемы: копия до рестарта -> рестарт с бэкапом -> смоук -> живой тест бота -> контрольная копия после рестарта"

requirements-completed: [DAT-01, SCH-01, SCH-02]

coverage:
  - id: OPS-01
    description: "Регламентная выкатка с бэкапом, рестартом, смоуком и живой верификацией"
    requirement: DAT-01
    verification:
      - kind: manual
        ref: "scripts/deploy.py --backup --restart --report (ИТОГ СМОУКА: ЗЕЛЁНЫЙ)"
        status: pass
      - kind: manual
        ref: "Живые тесты владельца в Telegram: /help, /menu, кнопки 👍/👎 (passed)"
        status: pass
      - kind: manual
        ref: "scripts/check_migration_on_copy.py --source data/assistant.db (ИТОГ: ЗЕЛЁНЫЙ, hash 83fece373834)"
        status: pass
      - kind: gate
        ref: "python3 scripts/gate.py (ИТОГ: ЗЕЛЁНЫЙ, 10 строк ✓)"
        status: pass
    human_judgment: true
---

# Итоги плана 03-06: Выкатка в рантайм, смоук-тесты OPS-01 и живые проверки (Критерий 5)

## 1. Task 1: Рестарт по процедуре OPS-01 с резервной копией и автоматический смоук

- **Выбор владельца (дословно):**
  `check-and-restart (Проверка на копии сейчас и рестарт с резервной копией в плане 03-06)`.
- **Резервная копия боевой БД:**
  - Путь: `/var/backups/assistant-core/assistant-20261011-005251.db` (создана через sqlite3 backup API в режиме `mode=ro`).
  - Размер: `8704000` байт (права `0600` в каталоге с правами `0700`).
  - Содержимое копии не читалось и не выводилось.
- **Инвокация сервиса:**
  - Базовая линия до рестарта: `InvocationID=25ff0740810d4783ae1ba7721b6f836c`.
  - Новая инвокация после рестарта: `InvocationID=0dc5531ee9824fb7a6145d333f5eef65`.
- **Автоматический смоук:**
  - Все 7 автоматических проверок пройдены (новая инвокация, сервис active, доступность журнала, отсутствие ошибок/WARNING/Traceback в 60-секундном окне старта, запуск polling, 10 из 10 задач планировщика, getMe).
  - Ошибок в окне старта: `0`.
  - Предупреждений (WARNING): `0`.
  - Команды отката зафиксированы справочно: **не исполнялись**.
  - Сервис потребителя: **`chat-app.service` не перезапускался**.

## 2. Task 2: Фазы подтверждения и живые проверки владельца в Telegram

- **Проверка `/help`:**
  - Владелец отправил команду `/help` боту в Telegram.
  - Журнал зафиксировал обработку: `scripts/deploy.py --await-help` (обновление успешно обработано).
  - Владелец подтвердил получение ответа в интерактивном опросе: `scripts/deploy.py --confirm-help yes`.
  - Статус: **passed**, итоговый вердикт смоука зафиксирован в `.planning/phases/03-vladenie-shemoy-bd/03-SMOKE-REPORT.md`: **ИТОГ СМОУКА: ЗЕЛЁНЫЙ**.
- **Проверка `/menu`:**
  - Владелец отправил боту `/menu`.
  - Бот отобразил интерактивное меню со списком команд, их статусом активности и блоком «Персональные псевдонимы». Обработчик бота успешно прочитал обе мигрированные таблицы `bot_command_settings` и `bot_custom_aliases`.
  - Статус: **passed** (источник: подтверждение владельца).
- **Проверка кнопок обратной связи 👍/👎:**
  - Владелец нажал кнопку 👍/👎 под сообщением бота.
  - Бот выдал всплывающее уведомление «Спасибо за отзыв!».
  - В боевой БД в таблице `dialog_feedback_log` зафиксирована 1 строка.
  - Статус: **passed** (источник: подтверждение владельца и контрольный замер счётчика строк).

## 3. Task 3: Контрольная проверка, CONCERNS.md, evidence и гейт качества

- **Повторная проверка на копии после рестарта:**
  - Выполнена команда: `.venv/bin/python scripts/check_migration_on_copy.py --source data/assistant.db`.
  - Хеш источника до и после совпал: `83fece373834`.
  - Применено на копии: `[]` (no-op, миграция `0003_bot_commands_and_feedback` уже присутствует в схеме).
  - Счётчики строк таблиц бота:
    - `bot_command_settings`: 1 строк.
    - `bot_custom_aliases`: 1 строк.
    - `dialog_feedback_log`: 1 строк (зафиксирована строка от живого нажатия кнопки 👍/👎).
  - Вердикт: **ИТОГ: ЗЕЛЁНЫЙ**.
- **Закрытие строки в CONCERNS.md:**
  - Строка `Shared migration 0003 missing for bot_command_settings / bot_custom_aliases / dialog_feedback_log` переведена в статус `Resolved (Phase 3)` со ссылкой на коммиты `5c85613` (`assistant-shared`), `5413266` (`assistant-core`) и `011f9c2` (`chat-app`).
- **Гейт качества (`scripts/gate.py`):**
  - Вердикт: **ИТОГ: ЗЕЛЁНЫЙ** (10 из 10 проверок ✓).
  - 1027 passed в `assistant-core`, 202 passed в `assistant-shared`.
  - Хеш боевой БД до и после гейта: `83fece373834` (совпали, неизменность гарантирована).
- **Доказательный базис:**
  - Файл `.planning/phases/03-vladenie-shemoy-bd/03-VERIFICATION-EVIDENCE.md` финализирован, все заглушки и ссылки ожидания удалены, столбцы доказательств R1-R5 заполнены.
  - **Пометка верификатору:** Файл `03-VERIFICATION.md` пишет верификатор GSD по перечню R1-R5, данный план его не создаёт.
- **Открытые пункты:**
  - Усиления схемы (дополнительные индексы, ограничения CHECK, NOT NULL) отложены на отдельную миграцию решением владельца D-04.
