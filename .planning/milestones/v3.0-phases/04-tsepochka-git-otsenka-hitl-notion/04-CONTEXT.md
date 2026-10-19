# Phase 4: Цепочка Git → оценка → HITL → Notion - Context

**Gathered:** 2026-10-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Владелец получает по-русски оценку хода проектов по git-репозиториям рабочих пространств и вносит её в Notion только после подтверждения HITL-карточкой в Telegram. Цепочка достижима из планировщика `src/main.py` и из команды бота. Требования: GIT-01, GIT-02, GIT-03, GIT-04, NTN-01, NTN-02 (`.planning/REQUIREMENTS.md`). Новых возможностей фаза не добавляет. Боевая БД не открывается, рестарт `assistant-worker` только с разрешения владельца по OPS-01.

</domain>

<decisions>
## Implementation Decisions

### Форма оценки (GIT-03)
- **D-01:** Для public/internal текст оценки формирует LLM (Gemini) по санитизированным коммитам, по-русски. При сбое или отсутствии LLM — запасной шаблон (как сейчас в `GitProgressEvaluator.evaluate_workspaces`). Нужна ловушка LLM-клиента в тестах.
- **D-02:** Порог «застоя» и окно анализа (сейчас жёстко 7 дней в `git_evaluator.py`) становятся полем персоны (`stagnation_days`, дефолт 7) в `src/persona/models.py` (`extra=forbid`) и `config/persona.yaml`. В коде остаётся только нейтральный запасной дефолт.

### Запуск и статус (GIT-02, GIT-03)
- **D-03:** Планировщик запускает оценку раз в неделю. Расписание — поле персоны (крон, дефолт воскресенье вечером). Задача `git_progress_job` регистрируется в `src/main.py` и видна в списке задач при старте. Планировщик делает оценку и сразу создаёт карточки Notion.
- **D-04:** Команда бота показывает оценку сразу по пространствам. Карточки Notion создаются по запросу (кнопка «Внести в Notion»), а не автоматически.
- **D-05:** Пропущенные пространства (нет remote или каталога) и сбои SSH видны строками в ответе команды («пропущено: нет remote», «сбой SSH») и записью в журнале уровня warning. Из фонового запуска одно сводное сообщение в Telegram, если статус изменился. Сбой не роняет демон.

### Notion: связь и дубли (NTN-01, NTN-02)
- **D-06:** `notion_project` в `config/persona.yaml` — заглушки `notion-proj-*` (коммит 1ee47fa), не ID страниц. Владелец сам пришлёт реальные ID страниц проектов и ID базы активности (секреты в чат не присылать). Код ничего не угадывает: ID, похожий на заглушку, или пусто → пространство пропускается со статусом «Notion не настроен», карточка не создаётся.
- **D-07:** `NOTION_ACTIVITY_DB_ID` отсутствует в `src/config.py` (в коде строка-заглушка `"project_activity_logs"`). Его нужно добавить в конфиг и `.env.example`. Свойства базы активности (`Name`, `Project` relation, `Date`, `Commits`, `Status`) должны совпадать с `log_project_activity`; проверить на Phase-4 исследовании. Скрипт `provision_notion.py` такую базу не создаёт.
- **D-08:** Идемпотентность: ключ «пространство + дата периода». Если карточка с таким ключом уже есть в `pending_confirmations` или запись уже выполнена, новая не создаётся. Повторное нажатие «подтвердить» не пишет вторую запись. Схему не менять, если хватает текущих полей.
- **D-09:** Сбой Notion при подтверждённой записи: владельцу сообщение «не записано, повторите», демон не падает, карточка остаётся для повтора. Автоповторов нет.
- **D-10:** Отклонение карточки ничего не пишет в Notion.

### Карточки HITL и NDA (GIT-04)
- **D-11:** Одна карточка на проект (как сейчас в `propose_notion_updates`). Отдельные подтверждение и отклонение.
- **D-12:** Пространства `restricted_nda` из цепочки исключаются полностью: ни обращений к git, ни оценки, ни карточки, ни записи в Notion. В ответе команды одна строка «NDA: исключено из оценки». Это решение владельца (опрос 2026-10-11) и оно **меняет ROADMAP**: критерий 3 и GIT-04 говорят про обезличенные агрегаты в Notion. До планирования нужно переписать GIT-04 и критерий 3 (через `/gsd-phase` и правку REQUIREMENTS.md), чтобы тесты и VERIFICATION проверяли «для NDA вызовов git, LLM и Notion нет», а не агрегаты. Это строже прежнего, поэтому Air-Gap только ужесточается.
- **D-13:** Fail-closed: если допуск пространства определить нельзя (ошибка персоны, remote вне правил), оно считается NDA и исключается по D-12. LLM и git для него не вызываются.
- **D-14:** Доказательство на рантайм-пути: ловушка LLM-клиента и ловушка Notion-клиента, вызываемые из цепочки «команда → оценка», показывают ноль обращений для NDA и неопределённого допуска.

### Claude's Discretion
- Имена полей персоны (`stagnation_days`, крон) и задачи планировщика; формат строк статуса в ответе бота.
- Промпт оценки (Jinja2 в `config/prompts/`), модель из уже используемых в `src/brain/`.
- Где хранить ключ идемпотентности (поле payload/target_id или существующая таблица) без новой миграции, если возможно.
- Порядок и разбиение на планы; что делегировать agy по правилам CLAUDE.md.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Требования и роадмап
- `.planning/ROADMAP.md` §«Phase 4» — цель и 5 критериев (критерий 3 и GIT-04 пересматриваются по D-12)
- `.planning/REQUIREMENTS.md` — GIT-01..04, NTN-01, NTN-02
- `.planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-CONTEXT.md` — fail-closed NDA, shield не ослабляется (D-21)
- `.planning/phases/03-vladenie-shemoy-bd/03-CONTEXT.md` — схема только через миграции assistant-shared; OPS-01
- `docs/OPS_DEPLOY.md` — рестарт только с разрешения владельца
- `.planning/codebase/CONCERNS.md` — «GitEvaluator не создаётся в рантайме»

### Код
- `src/brain/git_evaluator.py` — `GitProgressEvaluator`, `propose_notion_updates`, `_handle_notion_sync`
- `src/connectors/git/provider.py` — `SshGitProvider` (только чтение)
- `src/composition.py:97` — `default_git_source_provider`
- `src/connectors/notion/client.py` ~288 — `log_project_activity`
- `src/config.py:60-64` — переменные Notion; `.env.example`
- `src/security/airgap.py` — `is_nda_workspace`, `sanitize_*`
- `src/notifier/bot_handler.py` ~197, 390, 2029, 2084 — HITL-обработчики и колбэки `hitl:confirm|reject`
- `src/main.py` ~772 — регистрация задач планировщика
- `src/persona/models.py`, `src/persona/bindings.py`, `config/persona.yaml` — привязки `git_source`, `notion`
- `tests/test_notion_git_hitl.py`, `tests/test_git_airgap_trap.py` — существующие юнит-тесты цепочки
- `scripts/provision_notion.py` — создание баз Notion (базы активности нет)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `GitProgressEvaluator` (245 строк): опрос, санитизация, `format_telegram_card`, обработчик `notion_project_sync` через `register_action_handler`. Создаётся только в тестах.
- `ConfirmationStore` / `PendingConfirmation` из `assistant_shared.hitl`, колбэки `hitl:confirm:` и `hitl:reject:` уже в боте.
- `NotionClient.log_project_activity`.

### Established Patterns
- Порты в `src/core/ports`, сборка через `src/composition.py`; `brain` не импортирует адаптеры напрямую (import-linter).
- Профильные значения — только из `config/persona.yaml`; `tests/test_hardcode_scanner.py` держит замороженный baseline.
- Фоновые циклы `run_*_cycle` в `src/main.py` оборачивают шаги в `try/except` с логом `warning`.

### Integration Points
- Новая задача и цикл в `src/main.py`; сборка оценщика в `src/composition.py`; команда в `src/notifier/commands.py` и `bot_handler.py`.
- Поля персоны → `src/persona/models.py` и `config/persona.yaml`; ID Notion → `src/config.py`, `.env.example`.

</code_context>

<specifics>
## Specific Ideas

Владелец сам даст реальные ID страниц проектов Notion и ID базы активности. Пока их нет, пространства со статусом «Notion не настроен» пропускаются, а не пишут в заглушку.

</specifics>

<deferred>
## Deferred Ideas

- Мастер подключения Notion, который сам находит страницы проектов по имени — отдельная возможность (Phase 8/9).
- Автоповтор неудавшейся записи в Notion — не входит в фазу.

</deferred>

---

*Phase: 4-Цепочка Git → оценка → HITL → Notion*
*Context gathered: 2026-10-11*
