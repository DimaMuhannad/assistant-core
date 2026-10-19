# Независимый аудит достижимости рантайма (Волна 5: 04-REVIEW-REACHABILITY.md)

Дата: 2026-10-12
Аудитор: субагент `reader` (Runtime Reachability Auditor)
Статус: **ОДОБРЕНО (Полная достижимость подтверждена)**

---

## 1. Проверенные точки входа и рантайм-связки

1. **Периодическая задача `git_progress_job`:**
   - Регистрация в планировщике: `src/main.py:904-913` (`scheduler.add_job(run_git_progress_cycle, "cron", ...)`).
   - Расписание (`day_of_week`, `hour`, `minute`) динамически читается из `git_source_settings()` (`src/main.py:903, 907-909`).
   - Реализация фонового цикла: `src/main.py:604-632` (`run_git_progress_cycle`).

2. **Команда `/git`:**
   - Регистрация в каталоге команд: `src/notifier/commands.py:173-179` (`CommandSpec(name="git", ...)`).
   - Привязка хэндлера в роутере aiogram: `src/notifier/bot_handler.py:425` (`Command("git") -> handle_cmd_git`).
   - Диспетчеризация через роутер намерений: `src/notifier/bot_handler.py:1463-1465`.
   - Обработчик команды: `src/notifier/bot_handler.py:2154-2191` (`handle_cmd_git`).

3. **Колбэки `ntn:*`:**
   - Регистрация фильтров: `src/notifier/bot_handler.py:416-418` (`ntn:req:`, `ntn:conf:`, `ntn:rej:`).
   - Запрос карточки: `src/notifier/bot_handler.py:2193-2240` (`cb_ntn_request` -> `evaluator.propose_card`).
   - Подтверждение HITL: `src/notifier/bot_handler.py:2241-2293` (`cb_ntn_confirm` -> `resume_action`).
   - Отклонение HITL: `src/notifier/bot_handler.py:2294-2311` (`cb_ntn_reject` -> `store.reject_action`).

4. **Порядок инициализации в рантайме:**
   - Сборка фабрики: `src/main.py:674-679` (`git_evaluator = default_git_evaluator(db)`).
   - Внедрение в обработчик: `src/main.py:687-698` (`EmailBotHandler(..., git_evaluator=git_evaluator)`).
   - Порядок гарантирован: `default_git_evaluator` (строка 675) строго предшествует `EmailBotHandler` (строка 687) и `scheduler.add_job` (строка 808+).
   - Привязка HITL-экшена: `src/brain/git_evaluator.py:191` (`register_action_handler("notion_project_sync", ...)`).
   - Проверено компоновочными и AST-тестами: `tests/test_phase4_reachability.py:31-131, 182-194`.

---

## 2. Обработка ошибок и отказоустойчивость рантайма

- **Дедупликация:**
  - На уровне HITL: составной ключ `workspace_id|date_iso` под `_card_lock` предотвращает повторные запросы в тот же день (`src/brain/git_evaluator.py:63, 513-527`).
  - В цикле: Telegram-карточка отправляется только для `proposal.created=True` (`src/main.py:614`).
  - На уровне Notion: проверка `find_project_activity` исключает дублирование страниц в базе активности (`src/brain/git_evaluator.py:685-697`).
  - В фоновой сводке: `register_run_signature` отсекает повторные неизменившиеся сводки (`src/main.py:626`, `src/brain/git_evaluator.py:567-579`).
- **Механизм Reopen:**
  - При `NotionSyncError`, `LookupError` или сбоях API карточка возвращается в PENDING через `store.reopen_action(conf_id)` (`src/notifier/bot_handler.py:2281, 2285, 2291`), сохраняя возможность повтора.
- **Сбои SSH и сети:**
  - Ошибки `fetch_remote` изолируются per-workspace со статусом `FETCH_FAILED` (`src/brain/git_evaluator.py:388-416`) и не прерывают обход остальных репозиториев.
  - Исключения в `run_git_progress_cycle` и отправке Telegram-сообщений перехватываются (`src/main.py:619-624, 630-631`), планировщик и сервис не падают.

---

## 3. Итоговый вердикт

Полная достижимость цепочки Git -> Оценка -> HITL -> Notion из рантайма сервиса **подтверждена**. Все точки входа зарегистрированы, зависимости связаны корректно, идемпотентность и обработка сбоев обеспечены.
