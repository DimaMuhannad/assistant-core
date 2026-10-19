# Итоги плана 04-10 (Волна 5: Ловушки Air-Gap на рантайм-пути и сквозные тесты обоих входов)

## 1. Выполненные задачи

- **Task 1: Ловушки git, LLM и Notion на путях handle_cmd_git и run_git_progress_cycle (GIT-02, GIT-04, NTN-02)**
  - В `tests/test_git_chain_airgap.py`:
    - Реализованы шпионские классы ловушек:
      - `TrapGitProvider`: регистрирует все вызовы `list_repositories`, `fetch_remote`, `get_commits_since`, возвращает коммиты с маркером пространства.
      - `TrapLlm`: перехватывает запросы к моделям (`aio.models.generate_content`), логируя модели, промпты и системные инструкции.
      - `TrapNotion`: отслеживает вызовы `find_project_activity` и `log_project_activity`.
    - Добавлен стенд `create_trap_stand` с уникальным нейтральным маркером `TEST_NDA_SECRET_MARKER_999`.
    - Добавлен параметризованный тест `test_runtime_traps_nda_scenarios` (7 сценариев: `only_nda`, `mixed`, `unknown_clearance`, `persona_error`, `persona_none`, `overlap_remote`, `overlap_path`): доказано 0 обращений по NDA/ошибочным пространствам, отсутствие утечки маркера в текстах бота и вызовах клиентов.
    - Добавлен параметризованный тест `test_runtime_traps_scheduler_cycle`: аналогичные 7 сценариев доказаны для циклической задачи планировщика `run_git_progress_cycle`.
    - Добавлен контрольный тест `test_traps_are_not_vacuous`: подтвердил срабатывание всех трёх ловушек на публичном пространстве, исключив фиктивность проверок.
  - Коммит: `c43d0ae`.

- **Task 2: Сквозные сценарии от обоих входов и ast-проверки достижимости (GIT-03, NTN-02)**
  - В `tests/test_phase4_chain_e2e.py`:
    - Добавлены 5 сквозных тестов:
      1. `test_reject_writes_nothing_and_blocks_same_day` — отклонение карточки блокирует запись в Notion и выводит уведомление при повторном запросе за тот же день.
      2. `test_rerun_same_day_keeps_single_card` — два запуска команды `/git` и два нажатия `ntn:req` оставляют ровно одну запись в БД.
      3. `test_page_already_in_notion_not_duplicated` — дедупликация: при найденной странице Notion `log_project_activity` не вызывается.
      4. `test_ssh_failure_status_line_and_daemon_alive` — реальный сетевой сбой SSH выводит строку `сбой SSH` без падения демона.
      5. `test_scheduler_cycle_card_to_notion_write` — цикл планировщика присылает карточку, подтверждение которой публикует отчет в Notion ровно один раз.
  - В `tests/test_phase4_reachability.py`:
    - Добавлены 2 AST-проверки:
      1. `test_bot_registers_git_command_and_ntn_callbacks` — проверка наличия `Command("git")` и префиксов `ntn:req:`, `ntn:conf:`, `ntn:rej:` в `_register_handlers`.
      2. `test_log_project_activity_called_only_from_handler` — поиск по всем файлам `src/**/*.py` подтвердил, что метод `log_project_activity` вызывается исключительно внутри `GitProgressEvaluator._handle_notion_sync`.
  - Коммит: `1aa4f82`.

## 2. Результаты тестирования

- `tests/test_git_chain_airgap.py`: 22 passed.
- `tests/test_phase4_chain_e2e.py`: 17 passed.
- `tests/test_phase4_reachability.py`: 13 passed.
- Отклонений `fix(04-10)` не потребовалось: код фаз 1–4 полностью удовлетворил всем строгим контрактам.
