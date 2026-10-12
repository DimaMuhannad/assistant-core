# Phase 4: Доказательства для VERIFICATION.md (04-VERIFICATION-EVIDENCE.md)

## Назначение
Настоящий документ сформирован в рамках плана 04-12 как доказательная база (evidence) для независимого верификатора GSD.
Итоговый файл `04-VERIFICATION.md` составляется исключительно верификатором GSD на основе данного перечня R1-R5 и живых проверок выкатки.
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

| Критерий | Требования | Тесты и компоненты | Команда проверки | Результат |
|---|---|---|---|---|
| **R1** | Подключение репозиториев только через данные рабочего пространства (`git: host, account, ssh_alias, remote`), `default_git_source_provider`, `SshGitProvider` (только чтение по SSH, scope `git.read`). Пропуск без remote/каталога с отображением статуса (GIT-01, GIT-02). | `tests/test_phase4_reachability.py` (`test_composition_default_git_evaluator_*`), `tests/test_git_connector.py`, `tests/test_git_chain.py` (статусы пропусков: NO_REMOTE, NO_DIR, NOT_GIT). | `.venv/bin/pytest tests/test_phase4_reachability.py tests/test_git_connector.py tests/test_git_chain.py -k "not skipped" -q` | 33 passed |
| **R2** | `GitProgressEvaluator` создаётся в планировщике `src/main.py` (расписание из персоны) и по команде бота `/git`, владелец получает по-русски оценку хода проекта для public- и internal-репозиториев (GIT-03). | `tests/test_phase4_reachability.py` (`test_main_registers_git_evaluator_before_bot`, `test_main_registers_scheduler_git_progress_job`, AST-проверки), `tests/test_git_chain.py` (форматирование сводки по-русски, определение застоя). | `.venv/bin/pytest tests/test_phase4_reachability.py tests/test_git_chain.py -q` | 30 passed |
| **R3** | Пространства `restricted_nda` и неизвестный clearance исключены из цепочки: 0 обращений к git, LLM и Notion, статус «NDA: исключено из оценки». Доказано ловушками на рантайм-пути (GIT-04). | `tests/test_git_chain_airgap.py` (ловушки `TrapGitProvider`, `TrapLlm`, `TrapNotion` на путях `handle_cmd_git` и `run_git_progress_cycle` для 7 сценариев изоляции NDA; доказательство нефиктивности `test_traps_are_not_vacuous`). | `.venv/bin/pytest tests/test_git_chain_airgap.py -q` | 22 passed |
| **R4** | Обработчик `notion_project_sync` зарегистрирован в рантайме, связь «пространство → проект Notion» из персоны. Запись в Notion только после подтверждения HITL в Telegram: отклонение ничего не пишет, повтор не создает дублей, сбой SSH/Notion не роняет демон (NTN-01, NTN-02). | `tests/test_notion_git_hitl.py`, `tests/test_git_bot_commands.py`, `tests/test_git_chain.py` (колбэки `ntn:req:`, `ntn:conf:`, `ntn:rej:`, обработка `reopen_action` при сбоях, обработка дубликатов). | `.venv/bin/pytest tests/test_notion_git_hitl.py tests/test_git_bot_commands.py -q` | 19 passed |
| **R5** | Достижимость из рантайма доказана: задача планировщика в `src/main.py`, команда бота зарегистрирована, цепочка «команда → оценка → HITL → запись» проверена на временной БД со шпионами/ловушками. Единственный путь записи в Notion подтверждён AST-анализом. | `tests/test_phase4_chain_e2e.py` (5 сквозных сценариев), `tests/test_phase4_reachability.py` (`test_log_project_activity_called_only_from_handler`). | `.venv/bin/pytest tests/test_phase4_chain_e2e.py tests/test_phase4_reachability.py -q` | 30 passed |

---

## Не проверено до рестарта

Следующие проверки требуют реального выполнения сервиса и выполняются в плане 04-13 после согласования с владельцем:
1. Наличие строки в системном журнале: `Added job "run_git_progress_cycle" to jobstore with run time …` при старте сервиса.
2. Интерактивный вызов команды `/git` в Telegram-боте владельцем.
3. Прохождение процедуры регламентного смоука OPS-01 (`scripts/deploy.py --backup --restart`).

---

## Рестарт и смоук

*(Раздел заполняется в плане 04-13)*
- Статус: Ожидает согласования владельца и выполнения плана 04-13.
- Резервная копия боевой БД: запланирована через `scripts/deploy.py --backup`.

---

## Живые проверки

*(Раздел заполняется в плане 04-13)*
- `/help`: проверка отображения команды `/git` в списке команд.
- `/git`: живой отклик бота и формирование сообщения со статусами репозиториев.

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

## Покрытие внешнего API

- Ссылка на матрицу покрытия: `COVERAGE.md`.
- Все контрактные методы интеграции `BaseGitSourceProvider`, `NotionAsyncClientLike`, `GitProgressEvaluator` покрыты тестами.
