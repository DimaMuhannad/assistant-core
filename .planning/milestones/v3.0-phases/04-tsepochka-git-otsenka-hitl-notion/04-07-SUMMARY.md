# Итоги плана 04-07 (Волна 3: HITL-карточки, дедупликация и строгий обработчик Notion)

## 1. Выполненные задачи

- **Task 1: Идемпотентность карточек, карточный замок и дедупликация запусков (D-07, D-08, D-10)**
  - Реализована функция `build_card_key(workspace_id, date_iso)` — единственная точка конструирования ключа `ws_id|date_iso` в `src/brain/git_evaluator.py`.
  - Добавлены атрибуты в `GitProgressEvaluator`:
    - `_card_lock: asyncio.Lock()` для защиты от параллельных гонок при создании карточек.
    - `_last_signature: tuple[tuple[str, int, str | None], ...] | None` для отслеживания сигнатуры последнего прогона.
  - Метод `propose_card(run, eval_entry)`:
    - Ищет существующие подтверждения по ключу `build_card_key(...)` в состояниях PENDING, CONFIRMED и REJECTED.
    - Если найдено CONFIRMED или REJECTED — возвращает существующую карточку (защита от повторного спама в Telegram после решения пользователя).
    - Если найдено PENDING — возвращает его без создания дубликата.
    - В противном случае атомарно создает новую запись `notion_project_sync` с полным payload (`workspace_id`, `notion_project_id`, `database_id`, `date_iso`, `commit_count`, `status`, `summary`).
  - Метод `propose_cards(run)`:
    - Итерируется по пространствам со статусом `notion_ready=True` и формирует список карточек.
  - Методы `register_run_signature(run)` и `format_background_summary(run)`:
    - Поддержка фонового планировщика и форматирование сводки.
  - Коммит: `e71082b`.

- **Task 2: Валидация идентификаторов Notion, повторная проверка допуска и строгий обработчик (D-06, D-09, D-10, NTN-01, NTN-02)**
  - В `src/brain/git_evaluator.py`:
    - Добавлен класс исключения `NotionSyncError(Exception)`.
    - Добавлена функция валидации `is_valid_notion_id(value: str | None) -> bool`:
      - Проверяет 32 hex-символа (с дефисами или без), отвергает заглушки (`00000000...`, `notion-project-placeholder`, `12345678901234567890123456789012`).
    - Реализован строгий обработчик `_handle_notion_sync(conf: PendingConfirmation)`:
      1. Повторная проверка допуска пространства по текущей персоне через `git_chain_workspaces` (любое сомнение/изменение допуска на `restricted_nda` блокирует вызов).
      2. Строгая валидация идентификаторов `notion_project_id` и `database_id` из payload (без дефолтов/подстановок извне).
      3. Проверка готовности `self.notion_client.is_configured`.
      4. Поиск существующей записи через duck-typing вызов `find_project_activity` (если найдена — возврат `{"success": True, "page_id": ..., "deduplicated": True}`).
      5. Публикация через `log_project_activity` (возврат `{"success": True, "page_id": ..., "deduplicated": False}`).
      6. Санитизированная обработка ошибок: исключения оборачиваются в `NotionSyncError` с указанием HTTP-статуса и типа ошибки, без утечки тела ответа или токенов авторизации.
  - В `tests/test_git_chain.py`:
    - Добавлены 4 теста валидации идентификаторов Notion и статусов готовности.
  - В `tests/test_notion_git_hitl.py`:
    - Добавлены тесты дедупликации, создания новой страницы, перехвата ошибок без утечки тела и повторной проверки допуска.
  - Коммит: `febd967`.

## 2. Ключевые архитектурные решения и инварианты

1. **Ключ карточки:** Единственное место генерации ключа — `build_card_key(workspace_id, date_iso)`. Никаких расхождений формата в кодовой базе.
2. **Безопасность идентификаторов:** Запрещено использовать `conf.target_id` в качестве фолбэка для базы данных. Идентификаторы берутся строго из валидированного payload карточки.
3. **Безопасность API-логов:** Исключения Notion API маскируют тело ответа, предотвращая утечку секретов в логи приложения.

## 3. Статус гейтов и тестов

- Все тесты интеграции `test_git_chain.py`, `test_notion_git_hitl.py`, `test_phase4_chain_e2e.py`, `test_git_airgap_trap.py` (57 тестов) успешно пройдены.
- Тесты архитектурных контрактов (`test_architecture_contract.py`, `test_core_architecture.py`, `test_hardcode_scanner.py`) успешно пройдены.
