# Phase 4: Доказательства для VERIFICATION.md (04-VERIFICATION-EVIDENCE.md)

## Назначение
Настоящий документ сформирован в рамках планов 04-12 и 04-13 как доказательная база (evidence) для независимого верификатора GSD.
Итоговый файл `04-VERIFICATION.md` составляется исключительно верификатором GSD на основе данного перечня R1-R5 и проверок выкатки.
В документе отсутствуют персональные адреса электронной почты, токены API, строки журналов с NDA-содержимым и неразрешённые идентификаторы.

---

## Результаты проверок до рестарта

### Качество и безопасность (scripts/gate.py)
- Вердикт гейта: **ИТОГ: ЗЕЛЁНЫЙ** (10 проверок со значком ✓ пройдены успешно).
- `assistant-core`: pytest — 1149 тестов пройдено (0 failures, 0 errors, 0 skips, 0 xfail, 0 deselected).
- `assistant-core`: боевая `assistant.db` защищена (целостность схемы и строк подтверждена).
- `assistant-core`: import-linter пройден.
- `assistant-core`: security_shield (`--all`) пройден (только 3 известных допустимых срабатывания в `config/persona.yaml`, новых нет).
- `assistant-core`: дрейф синтетической персоны и токенов отсутствует.
- `assistant-shared`: pytest — 211 тестов пройдено.
- `assistant-shared`: security_shield (`--all`) пройден.
- Репозитории: pre-commit hook установлен и активен.

---

## Перечень доказательств R1-R5 по критериям успеха ROADMAP

| Критерий | Требования | Тесты и компоненты | Команда проверки | Статус | Живое доказательство |
|---|---|---|---|---|---|
| **R1** | Подключение репозиториев только через данные рабочего пространства (`git: host, account, ssh_alias, remote`), `default_git_source_provider`, `SshGitProvider` (только чтение по SSH, scope `git.read`). Пропуск без remote/каталога с отображением статуса (GIT-01, GIT-02). | `tests/test_phase4_reachability.py` (`test_composition_default_git_evaluator_*`), `tests/test_git_connector.py`, `tests/test_git_chain.py` (статусы пропусков: NO_REMOTE, NO_DIR, NOT_GIT). | `.venv/bin/pytest tests/test_phase4_reachability.py tests/test_git_connector.py tests/test_git_chain.py -k "not skipped" -q` | passed | Бот в ответе `/git` выводит видимые статусы («пропущено: нет каталога», оценка/«сбой SSH»). |
| **R2** | `GitProgressEvaluator` создаётся в планировщике `src/main.py` (расписание из персоны) и по команде бота `/git`, владелец получает по-русски оценку хода проекта для public- и internal-репозиториев (GIT-03). | `tests/test_phase4_reachability.py` (`test_main_registers_git_evaluator_before_bot`, `test_main_registers_scheduler_git_progress_job`, AST-проверки), `tests/test_git_chain.py` (форматирование сводки по-русски, определение застоя). | `.venv/bin/pytest tests/test_phase4_reachability.py tests/test_git_chain.py -q` | passed | Задача `run_git_progress_cycle` зарегистрирована в планировщике живого сервиса; бот отвечает на `/git` на русском языке. |
| **R3** | Пространства `restricted_nda` и неизвестный clearance исключены из цепочки: 0 обращений к git, LLM и Notion, статус «NDA: исключено из оценки». Доказано ловушками на рантайм-пути (GIT-04). | `tests/test_git_chain_airgap.py` (ловушки `TrapGitProvider`, `TrapLlm`, `TrapNotion` на путях `handle_cmd_git` и `run_git_progress_cycle` для 7 сценариев изоляции NDA; доказательство нефиктивности `test_traps_are_not_vacuous`). | `.venv/bin/pytest tests/test_git_chain_airgap.py -q` | passed | В живом ответе бота присутствует ровно одна строка «🔒 NDA: исключено из оценки», других упоминаний пространства нет. |
| **R4** | Обработчик `notion_project_sync` зарегистрирован в рантайме, связь «пространство → проект Notion» из персоны. Запись в Notion только после подтверждения HITL в Telegram: отклонение ничего не пишет, повтор не создает дублей, сбой SSH/Notion не роняет демон (NTN-01, NTN-02). | `tests/test_notion_git_hitl.py`, `tests/test_git_bot_commands.py`, `tests/test_git_chain.py` (колбэки `ntn:req:`, `ntn:conf:`, `ntn:rej:`, обработка `reopen_action` при сбоях, обработка дубликатов). | `.venv/bin/pytest tests/test_notion_git_hitl.py tests/test_git_bot_commands.py -q` | passed | Обработчик зарегистрирован в рантайме; без боевых ID выводится статус «Notion не настроен» без создания ошибочных карточек. |
| **R5** | Достижимость из рантайма доказана: задача планировщика в `src/main.py`, команда бота зарегистрирована, цепочка «команда → оценка → HITL → запись» проверена на временной БД со шпионами/ловушками. Единственный путь записи в Notion подтверждён AST-анализом. Рестарт выполнен по регламенту OPS-01 с резервной копией и смоуком. | `tests/test_phase4_chain_e2e.py` (5 сквозных сценариев), `tests/test_phase4_reachability.py` (`test_log_project_activity_called_only_from_handler`). | `.venv/bin/pytest tests/test_phase4_chain_e2e.py tests/test_phase4_reachability.py -q` | passed | Сервис перезапущен по согласованию с владельцем, смоук ЗЕЛЁНЫЙ, живой отклик бота подтверждён. |

---

## Рестарт и смоук

- **Выбор владельца (дословно)**: `(Recommended) Рестарт сейчас с резервной копией и смоуком` (`choice=check-and-restart`).
- **Хеш HEAD на момент рестарта**: `f27408203cee358ac25fa893750298a97048c873`.
- **InvocationID сервиса**:
  - До рестарта: `0dc5531ee9824fb7a6145d333f5eef65`
  - После рестарта: `69c90347816645e189d120c842337483`
- **Резервная копия**:
  - Путь: `/var/backups/assistant-core/assistant-20261012-120659.db` (размер: 8765440 байт, права 0600 в каталоге 0700). Содержимое копии не читалось.
- **Статус автоматического смоука**:
  - Команда: `python3 scripts/deploy.py --backup --restart --report .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-SMOKE-REPORT.md`
  - Итог: **ИТОГ СМОУКА: ЗЕЛЁНЫЙ** (отчёт сохранён в `.planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-SMOKE-REPORT.md`).
  - Ошибки в окне старта: 0.
  - Предупреждения (WARNING): 0.
  - Планировщик: задачи зарегистрированы (11 из 11), включая `git_progress_job` (`run_git_progress_cycle`).
  - Polling бота запущен, getMe токен жив.
  - Команды отката: не исполнялись.
  - Сервис потребителя: **chat-app.service не перезапускался**.

---

## Живые проверки

Живые проверки выполнены владельцем в Telegram через интерактивные опросы:

1. **Команда `/help`**:
   - Обработка в журнале зафиксирована скриптом (`scripts/deploy.py --await-help`, статус: `handled`).
   - Ответ бота получен владельцем в Telegram: подтверждено (`deploy.py --confirm-help yes`). Ответ содержит справочную строку о команде `/git`.
   - Статус: **passed** (источник: опрос владельца, `04-SMOKE-REPORT.md`).

2. **Команда `/git`**:
   - а) Бот ответил на русском языке со списком рабочих пространств: **passed** (источник: опрос владельца).
   - б) Пространство без локального каталога показано как «пропущено: нет каталога»: **passed** (источник: опрос владельца).
   - в) Присутствует ровно одна строка «🔒 NDA: исключено из оценки», других упоминаний NDA-пространства нет: **passed** (источник: опрос владельца).
   - г) Пространства показаны со статусом «Notion не настроен» без кнопки «Внести в Notion»: **passed** (источник: опрос владельца).
   - д) Для доступных публичных пространств сформирована оценка по-русски либо статус «сбой SSH», сервис продолжил стабильную работу: **passed** (источник: опрос владельца).

---

## Отклонения и gap

1. **Конфигурация персоны (План 04-11, D-02, D-03, D-21)**:
   - Блок `config` привязки `git_source` внесен в `config/persona.yaml` с параметрами `stagnation_days: 7`, `day_of_week: sun`, `hour: 20`, `minute: 0`.
   - Коммит выполнен с разовым обходом pre-commit hook (`--no-verify`) после явного утверждения владельцем в чате (коммит `50378ea`, `04-11-SUMMARY.md`).
   - Нарушений или ослаблений защитных рубежей `security_shield` и `gate.py` нет.

2. **Идентификаторы Notion (D-06, D-07)**:
   - Реальные ID базы активности и страниц проектов Notion не хардкодятся и задаются владельцем через переменные окружения и `config/persona.yaml` согласно `docs/GIT_NOTION_SETUP.md`.
   - В отсутствие привязки пространства корректно получают статус «Notion не настроен» (D-06).

---

## Открытые пункты

1. Реальные ID Notion (notion_project, ID базы активности) от владельца и реальная запись в живой Notion не проверялись в бою: до выдачи ID пространства показывают «Notion не настроен», полная цепочка доказана тестами на временной БД (D-06, D-07, NTN-01).
2. Файл `04-VERIFICATION.md` пишется независимым верификатором GSD по этому файлу и перечню R1-R5, данный план его не создает.

---

## Покрытие внешнего API

- Ссылка на матрицу покрытия: `COVERAGE.md`.
- Все контрактные методы интеграции `BaseGitSourceProvider`, `NotionAsyncClientLike`, `GitProgressEvaluator` покрыты тестами.
