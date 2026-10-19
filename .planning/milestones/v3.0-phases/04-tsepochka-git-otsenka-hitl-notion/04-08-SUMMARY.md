# Итоги плана 04-08 (Волна 4: Фабрики композиции, интеграция в main.py и планировщик git_progress_job)

## 1. Выполненные задачи

- **Task 1: Фабрики default_notion_client и default_git_evaluator в корне композиции (GIT-01, NTN-01)**
  - В `src/composition.py`:
    - Реализована функция `default_notion_client()`: ленивый импорт `NotionAsyncClient`, проверка наличия привязки `notion`, проверка областей доступа `NotionAsyncClient.required_scopes` (`notion.read`, `notion.write`) с выбросом `MissingScopeError` при нехватке.
    - Реализована функция `default_git_evaluator(db)`: получает Git-провайдер из `default_git_source_provider()` (возвращает `None`, если привязка `git_source` отсутствует), клиента Notion из `default_notion_client()`, инициализирует `ConfirmationStore(db.db_path)`, передает `default_activity_db_id=config.NOTION_ACTIVITY_DB_ID` и `use_key_rotator=True`.
    - Все импорты классов коннекторов и оценщика выполнены лениво внутри функций, запрет верхнеуровневых импортов соблюден.
  - Коммит: `c4bd77e`.

- **Task 2: Интеграция оценщика в main.py, недельная задача планировщика и безопасный цикл (GIT-01, GIT-03, NTN-01)**
  - В `src/main.py`:
    - Реализована функция `run_git_progress_cycle(evaluator, notifier)`:
      - Проверяет `evaluator is None` (информационная запись в лог и выход без падения).
      - Вызывает `evaluator.evaluate()` и `evaluator.propose_cards(run)`.
      - Рассылает Telegram-карточки только для вновь созданных предложений (`proposal.created == True`) с кнопками `ntn:conf` и `ntn:rej`.
      - Отправка каждой карточки изолирована в собственном блоке `try/except` (сбой отправки одной не прерывает остальные).
      - Проверяет смену сигнатуры через `evaluator.register_run_signature(run)` и отправляет единую сводку `format_background_summary(run)` только при ее изменении.
      - Все внешние ошибки логируются на уровне `logger.warning` без `logger.exception` и без использования `print`.
    - В функции `main()`:
      - Экземпляр `git_evaluator` создается сразу после `lms_client` строго до создания `EmailBotHandler`.
      - При ошибке сборки цепочка переходит в безопасное отключенное состояние (`fail-closed`, `git_evaluator = None`).
      - Параметр `git_evaluator=git_evaluator` передан в конструктор `EmailBotHandler`.
      - В планировщик добавлена безусловная задача `git_progress_job` (`scheduler.add_job(run_git_progress_cycle, "cron", ...)`), считывающая параметры расписания `day_of_week`, `hour`, `minute` из `git_source_settings()`.
      - Цикл не запускается при старте сервиса и в служебных режимах `--once`, `--brief`, `--evening`, `--prime`, `--review`.
  - Коммит: `a9a3442`.

## 2. Результаты тестов достижимости (`tests/test_phase4_reachability.py`)

Все 11 тестов файла пройдены:
1. `test_composition_default_git_evaluator_default_persona` — создание полного оценщика с `SshGitProvider` и `NotionAsyncClient`, привязка обработчика `notion_project_sync`.
2. `test_composition_default_git_evaluator_without_git_source` — возврат `None` при отсутствии привязки `git_source`.
3. `test_composition_default_git_evaluator_synthetic_without_notion` — сборка оценщика без клиента Notion при отсутствии привязки `notion`.
4. `test_composition_default_git_evaluator_missing_scope_raises` — вызов `MissingScopeError` при нехватке scopes.
5. `test_composition_default_git_evaluator_db_path` — соответствие пути `ConfirmationStore` переданной базе данных.
6. `test_main_creates_git_evaluator_before_bot_handler` — AST-проверка очередности инициализации (`default_git_evaluator` -> `EmailBotHandler` -> `scheduler.add_job`).
7. `test_main_registers_git_progress_job_unconditionally` — AST и deploy смоук: задача видна `load_expected_jobs`, не под `if`, параметры cron передаются атрибутами настроек персоны.
8. `test_main_does_not_run_git_cycle_at_startup` — AST: отсутствие прямых вызовов цикла при старте.
9. `test_git_cycle_skips_when_evaluator_missing` — пропуск цикла без ошибок при отсутствии оценщика.
10. `test_git_cycle_never_raises` — подавление исключений на уровне цикла с предупреждением в журнал без ERROR.
11. `test_git_cycle_sends_cards_only_for_new_and_one_summary` — отправка карточек только для `created=True`, неповторение при неизменной сигнатуре, изоляция сбоев Telegram.

## 3. Регрессионное тестирование

- Пройдены тесты контрактов, смоук-тесты планировщика и смоук-скрипт деплоя (`tests/test_phase2_reachability.py`, `tests/test_phase3_reachability.py`, `tests/test_deploy_script.py`, `tests/test_lms_bot_workflow.py`, `tests/test_architecture_contract.py`, `tests/test_phase4_chain_e2e.py`, `tests/test_hardcode_scanner.py`): 245 тестов успешно.
- Количество вызовов `print` в `src/main.py` не увеличилось.
