# Phase 4: Цепочка Git → оценка → HITL → Notion - Research

**Researched:** 2026-10-11
**Domain:** Python-демон (asyncio, aiogram 3, APScheduler 3, SQLite-HITL `assistant_shared.hitl`, Notion REST API, git CLI). Новых зависимостей нет.
**Confidence:** HIGH по коду репозитория (всё прочитано в этой сессии), MEDIUM по поведению внешнего Notion (нет живой базы активности, ID ещё не выданы владельцем).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Для public/internal текст оценки формирует LLM (Gemini) по санитизированным коммитам, по-русски. При сбое или отсутствии LLM — запасной шаблон (как сейчас в `GitProgressEvaluator.evaluate_workspaces`). Нужна ловушка LLM-клиента в тестах.
- **D-02:** Порог «застоя» и окно анализа (сейчас жёстко 7 дней в `git_evaluator.py`) становятся полем персоны (`stagnation_days`, дефолт 7) в `src/persona/models.py` (`extra=forbid`) и `config/persona.yaml`. В коде остаётся только нейтральный запасной дефолт.
- **D-03:** Планировщик запускает оценку раз в неделю. Расписание — поле персоны (крон, дефолт воскресенье вечером). Задача `git_progress_job` регистрируется в `src/main.py` и видна в списке задач при старте. Планировщик делает оценку и сразу создаёт карточки Notion.
- **D-04:** Команда бота показывает оценку сразу по пространствам. Карточки Notion создаются по запросу (кнопка «Внести в Notion»), а не автоматически.
- **D-05:** Пропущенные пространства (нет remote или каталога) и сбои SSH видны строками в ответе команды («пропущено: нет remote», «сбой SSH») и записью в журнале уровня warning. Из фонового запуска одно сводное сообщение в Telegram, если статус изменился. Сбой не роняет демон.
- **D-06:** `notion_project` в `config/persona.yaml` — заглушки `notion-proj-*` (коммит 1ee47fa), не ID страниц. Владелец сам пришлёт реальные ID страниц проектов и ID базы активности (секреты в чат не присылать). Код ничего не угадывает: ID, похожий на заглушку, или пусто → пространство пропускается со статусом «Notion не настроен», карточка не создаётся.
- **D-07:** `NOTION_ACTIVITY_DB_ID` отсутствует в `src/config.py` (в коде строка-заглушка `"project_activity_logs"`). Его нужно добавить в конфиг и `.env.example`. Свойства базы активности (`Name`, `Project` relation, `Date`, `Commits`, `Status`) должны совпадать с `log_project_activity`; проверить на Phase-4 исследовании. Скрипт `provision_notion.py` такую базу не создаёт.
- **D-08:** Идемпотентность: ключ «пространство + дата периода». Если карточка с таким ключом уже есть в `pending_confirmations` или запись уже выполнена, новая не создаётся. Повторное нажатие «подтвердить» не пишет вторую запись. Схему не менять, если хватает текущих полей.
- **D-09:** Сбой Notion при подтверждённой записи: владельцу сообщение «не записано, повторите», демон не падает, карточка остаётся для повтора. Автоповторов нет.
- **D-10:** Отклонение карточки ничего не пишет в Notion.
- **D-11:** Одна карточка на проект (как сейчас в `propose_notion_updates`). Отдельные подтверждение и отклонение.
- **D-12:** Пространства `restricted_nda` из цепочки исключаются полностью: ни обращений к git, ни оценки, ни карточки, ни записи в Notion. В ответе команды одна строка «NDA: исключено из оценки». (Решение владельца, опрос 2026-10-11; GIT-04 и критерий 3 ROADMAP уже переписаны — проверено чтением REQUIREMENTS.md и ROADMAP.md.)
- **D-13:** Fail-closed: если допуск пространства определить нельзя (ошибка персоны, remote вне правил), оно считается NDA и исключается по D-12. LLM и git для него не вызываются.
- **D-14:** Доказательство на рантайм-пути: ловушка LLM-клиента и ловушка Notion-клиента, вызываемые из цепочки «команда → оценка», показывают ноль обращений для NDA и неопределённого допуска.

### Claude's Discretion
- Имена полей персоны (`stagnation_days`, крон) и задачи планировщика; формат строк статуса в ответе бота.
- Промпт оценки (Jinja2 в `config/prompts/`), модель из уже используемых в `src/brain/`.
- Где хранить ключ идемпотентности (поле payload/target_id или существующая таблица) без новой миграции, если возможно.
- Порядок и разбиение на планы; что делегировать agy по правилам CLAUDE.md.

### Deferred Ideas (OUT OF SCOPE)
- Мастер подключения Notion, который сам находит страницы проектов по имени — отдельная возможность (Phase 8/9).
- Автоповтор неудавшейся записи в Notion — не входит в фазу.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GIT-01 | `BaseGitSourceProvider`/`SshGitProvider` (только чтение, scope `git.read`) вызываются из рантайма через `default_git_source_provider` | Фабрика есть (`composition.py:97-113`), вызывающих в `src/` нет. Нужен единый `default_git_evaluator(db)` в composition, вызываемый один раз из `main()`. См. «Архитектура», Pitfall 1, 2 |
| GIT-02 | Репозитории подключаются данными пространства; без remote/каталога — пропуск с видимым статусом | `SshGitProvider.list_repositories()` пропускает не то (берёт пространства с `remote or ssh_alias` даже без каталога). Нужна явная классификация статусов в оценщике. Pitfall 3, 4 |
| GIT-03 | `GitProgressEvaluator` создаётся в планировщике и по команде бота; оценка по-русски для public/internal | Задача `git_progress_job` + команда `/git`, LLM-текст с запасным шаблоном, `stagnation_days` из персоны. Разделы «Persona», «Scheduler», «Command» |
| GIT-04 | `restricted_nda` и неопределённый допуск исключены полностью: ни git, ни LLM, ни Notion. Ловушки клиентов на рантайм-пути | Единый fail-closed предикат допуска ДО любых обращений; защита в глубину в провайдере. Pitfall 5, раздел «Валидация» |
| NTN-01 | `notion_project_sync` зарегистрирован в рантайме; связь «пространство → проект» из персоны | Регистрация происходит в `GitProgressEvaluator.__init__` (`git_evaluator.py:60`), значит evaluator должен создаваться при старте демона, а не лениво. Pitfall 2 |
| NTN-02 | Запись в Notion только после HITL; отклонение ничего не пишет; повтор без дублей; сбой не роняет демон и виден | Выделенные колбэки `ntn:*`, идемпотентность по ключу + проверка в Notion, `reopen` при сбое. Pitfall 6, 7, 8 |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

Источники: `/opt/assistant-core/CLAUDE.md` и `/opt/assistant-core/.claude/CLAUDE.md` (оба прочитаны).

- Боевую БД `/opt/assistant-core/data/assistant.db` не открывать и не менять; тесты только на `tmp_path`. `.env` не читать.
- Сервисы `assistant-worker`/`chat-app` заморожены: рестарт только по явному разрешению владельца через `python3 scripts/deploy.py --restart` (опрос в чате), затем смоук OPS-01.
- Тесты 100%: skip, xfail, deselected делают гейт красным. Проверять: `python3 scripts/gate.py` (ЗЕЛЁНЫЙ, exit 0). Сейчас собирается 1027 тестов [VERIFIED: `pytest --collect-only`].
- Новые зависимости только с одобрения владельца. В этой фазе они не нужны.
- Безопасность: HITL для необратимого, Air-Gap NDA, проверки только ужесточаются, fail-closed.
- Стек: Python 3.12, async-first (`aiosqlite`, `httpx`), dataclass/Pydantic. KISS/YAGNI.
- Всё, что видит пользователь, — по-русски. Логи: `logger = logging.getLogger(__name__)`, ленивое `%s`, без f-строк, без `print`, без секретов в логах.
- Профильные значения (имена владельца, организации) только из `config/persona.yaml`; `tests/test_hardcode_scanner.py` держит пустой `HARDCODE_BASELINE` (`tests/hardcode_baseline.py`: `HARDCODE_BASELINE: dict[str, dict[str, int]] = {}`), новый хардкод токенов владельца в `src/` покраснит тест.
- Import-linter: `src.brain` не импортирует `src.connectors/calendar/parser/sender/collector/notifier` прямо; `bot_handler` и `live_ticker` не импортируют адаптеры напрямую; `src.core` чистый; `src.persona` лист (не импортирует `src.config`, `src.brain`, `src.composition` и др.). Сборка адаптеров только в `src/composition.py`.
- Не править `tests/synthetic_persona.py` и `tests/persona_tokens.py`: гейт сверяет их с копиями chat-app (дрейф краснит гейт).
- Делегирование agy (решение владельца 2026-10-09): шаблонные тесты/документацию/однотипные правки ≥4 файлов можно отдавать в agy; исследование, безопасность/NDA/HITL, архитектура, ревью, правки 1–3 файлов — только Claude.
- Фаза закрывается только с SUMMARY.md и VERIFICATION.md, которая доказывает достижимость из рантайма.
- Коммиты прямо в `main` разрешены.

## Summary

Все компоненты цепочки уже написаны в v2.0, но из рантайма недостижимы: `GitProgressEvaluator` создаётся только в `tests/test_notion_git_hitl.py`, у `default_git_source_provider` нет вызывающих в `src/`, `NotionAsyncClient` нигде не создаётся, команды бота и задачи планировщика нет [VERIFIED: grep по `src/`, `.planning/codebase/CONCERNS.md`]. Фаза в основном «проводка» (wiring) плюс исправление шести реальных дефектов существующего кода, которые молча сломали бы цепочку или нарушили Air-Gap. Главные из них: (1) оценщик сейчас вызывает `fetch_remote`/`get_commits_since` для NDA-пространств и создаёт для них карточки, а D-12 требует ноль обращений; (2) `resume_action` из `assistant_shared.hitl` переводит карточку в `confirmed` ДО выполнения обработчика, поэтому после сбоя Notion повторить на той же карточке нельзя, а D-09 требует «карточка остаётся для повтора»; (3) колбэки `hitl:confirm:`/`hitl:reject:` ведут в `cb_hitl_confirm`, который отвечает «успешно удален(а)» — для Notion нужны отдельные колбэки; (4) `git log` без `--branches --remotes` смотрит только HEAD и не видит ничего, что подтянул `git fetch` (проверено экспериментом), то есть оценка по «удалённому» состоянию не работает; (5) пространства из персоны — `WorkspaceConfig` (строка `clearance`, поле `label`), а не доменные `Workspace`; (6) обработчик берёт `payload.get("notion_project_id") or conf.target_id` — при пустом ID в Notion уйдёт идентификатор пространства.

Реалии окружения: из 4 пространств персоны реально существуют каталоги только `/opt/chat-app` и `/opt/assistant-core`; `/opt/personal/guap-physics` и `/opt/work-tydex` отсутствуют [VERIFIED: `ls -d`]. У `chat-app` нет git-remote (`git remote -v` пуст) при `remote: https://github.com/...` в персоне [VERIFIED]. В `~/.ssh` только `authorized_keys` и `known_hosts`, закрытых ключей нет [VERIFIED], поэтому SSH-fetch приватных репозиториев на этом VPS работать не будет (публичные https-remote — будут). Реальные ID Notion владелец ещё не выдал, значит в живом рантайме после выкатки все пространства получат статус «Notion не настроен»: полная цепочка до записи доказывается на временной БД с подменёнными SSH и Notion (критерий 5), а живой контур проверяет только достижимость (задача в списке, команда отвечает).

**Primary recommendation:** Один раз в `main()` собрать `GitProgressEvaluator` через `composition.default_git_evaluator(db)` (регистрирует обработчик `notion_project_sync` при старте), передать его и в `EmailBotHandler` (команда `/git`, колбэки `ntn:*`), и в `run_git_progress_cycle` (`id="git_progress_job"`, безусловная регистрация). Единственный fail-closed предикат допуска (`public`/`internal` — иначе NDA) применять ДО любого обращения к git/LLM/Notion; в `SshGitProvider` дублировать проверку (`AirGapViolationError`). Подтверждение/повтор — собственные колбэки с `reopen` карточки при сбое Notion и проверкой «уже записано» в самой Notion перед созданием страницы.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Допуск пространства (fail-closed `public`/`internal` иначе NDA) | `src/security/airgap.py` (политика) | `src/connectors/git/provider.py` (защита в глубину) | Политика Air-Gap живёт в `src/security`; адаптер git не доверяет вызывающему и сам отказывает |
| Чтение git (fetch/log), статусы «нет каталога/remote» | Адаптер `SshGitProvider` | Оценщик (классификация статусов) | Только чтение, scope `git.read`; решение «пропустить» принимает оценщик по данным пространства |
| Оценка (текст, застой) | `src/brain/git_evaluator.py` | LLM Gemini через key_rotator; запасной шаблон | Use-case; адаптеры внедряются через DI, прямых импортов нет |
| Сборка графа зависимостей | `src/composition.py` | `src/main.py` | Единственное место, знающее конкретные классы (контракт `brain-no-adapters`) |
| Периодический запуск | `src/main.py` (APScheduler) | Параметры расписания из персоны | Все `run_*_cycle` живут в `main.py`; смоук `deploy.py` читает `add_job` ast-разбором |
| Команда и кнопки | `src/notifier/bot_handler.py` + `telegram.py` | `commands.py` (реестр) | Единственный UI владельца; авторизация `_is_authorized` |
| HITL-состояние (карточки, статус) | `assistant_shared.hitl` (`pending_confirmations`) | Расширение `ConfirmationStore` (reopen/find) | Общая таблица уже есть, схема не меняется |
| Запись в Notion | `src/connectors/notion/client.py` | Проверка «уже есть» перед созданием | Внешний API без ключа идемпотентности |
| Параметры (stagnation_days, расписание, ID Notion) | `config/persona.yaml` + `src/persona/` | `src/config.py` + `.env` (только `NOTION_ACTIVITY_DB_ID`) | Профильные значения — данные персоны; ID базы — окружение, как остальные `NOTION_*_DB_ID` |

## Standard Stack

Новых пакетов нет. Всё уже установлено в `/opt/assistant-core/.venv` [VERIFIED: `.venv/bin/pip list`].

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| aiogram | 3.31.0 | Команда `/git`, колбэки `ntn:*`, `InlineKeyboardMarkup` | Уже единственный бот-фреймворк проекта |
| APScheduler | 3.11.3 | `scheduler.add_job(..., "cron", day_of_week=..., hour=..., minute=...)` | Планировщик демона; `CronTrigger` валидирует поля (`ValueError` на мусор) [VERIFIED: запуск `CronTrigger(day_of_week="xyz")`] |
| google-genai | 2.25.0 | `client.aio.models.generate_content(model, contents, config=types.GenerateContentConfig(system_instruction=...))` | Паттерн `summarizer.py:187-195`; ключи через `key_rotator` |
| httpx | 0.28.1 | Notion REST (`NotionAsyncClient`) | Уже используется клиентом |
| assistant-shared (editable) | 0.1.0 | `ConfirmationStore`, `register_action_handler`, `resume_action`, `get_async_connection` | Владелец схемы и HITL-примитива |
| pytest / pytest-asyncio | 9.1.1 / 1.4.0 | Тесты (`asyncio_mode = auto`) | Конфиг `pytest.ini` |
| git CLI | 2.43.0 | `fetch`, `log` | Уже используется провайдером |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Jinja2 SandboxedEnvironment (через `render_prompt`) | в venv | Промпт оценки `git_progress` | Рендер с `StrictUndefined`; персона-контекст без `workspaces` (белый список `TEMPLATE_PERSONA_FIELDS`) |
| zoneinfo (stdlib) | — | Дата периода в `config.TZ` | Ключ идемпотентности «дата периода» |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Структурные поля расписания (`day_of_week`, `hour`, `minute`) | Строка cron | Строка требует разбора/валидации; структурные поля сразу идут в `add_job` и валидируются Pydantic-диапазонами |
| Расширение `ConfirmationStore` в assistant-shared (reopen/find) | Прямой SQL в `src/storage` | Прямой SQL в ядре дублирует знание о чужой таблице; расширение аддитивно, миграции не нужны, chat-app не затронут (читает только `get_confirmation`) [VERIFIED: `/opt/chat-app/backend/app/api/v1/confirmations.py`] |
| Новая карточка вместо reopen при сбое | `reopen_action` | Новая карточка не требует правок shared, но оставляет старую `confirmed` без записи и ломает проверку «уже выполнено» |

**Installation:** не требуется.

**Version verification:** версии взяты из `.venv/bin/pip list` в этой сессии (aiogram 3.31.0, aiosqlite 0.22.1, APScheduler 3.11.3, google-genai 2.25.0, httpx 0.28.1, pytest 9.1.1, pytest-asyncio 1.4.0); Python 3.12.3.

## Package Legitimacy Audit

Фаза не устанавливает внешних пакетов (правило CLAUDE.md: новые зависимости только с одобрения владельца). Проверка `package-legitimacy` не требовалась.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| — | — | — | — | — | — | Новых пакетов нет |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
 ВХОД 1: планировщик (cron из персоны)          ВХОД 2: Telegram /git (или алиас)
 main(): add_job(run_git_progress_cycle,        EmailBotHandler.handle_cmd_git
         id="git_progress_job")                          |
            |                                            |
            +------------------+-------------------------+
                               v
              GitProgressEvaluator.evaluate()   (один экземпляр, создан в main() при старте;
                               |                 в __init__ регистрирует "notion_project_sync")
        persona.to_domain().workspaces
                               |
              [ШЛЮЗ ДОПУСКА fail-closed: clearance строго public|internal]
               |                                   |
   NDA / неопределён ---------+                    | допущены
   ничего не вызывается,                           v
   счётчик nda_excluded += 1        для каждого допущенного пространства:
   (в ответе одна строка            1. нет remote?   -> статус "пропущено: нет remote"
    «NDA: исключено из оценки»)     2. нет каталога? -> "пропущено: нет каталога"
                                    3. нет .git?     -> "пропущено: не git-репозиторий"
                                    4. fetch_remote  -> сбой -> "сбой SSH" + warning (карточку не создавать)
                                    5. get_commits_since(--branches --remotes), sanitize
                                    6. LLM(prompt git_progress) --сбой--> запасной шаблон
                                    7. notion_project валиден? нет -> "Notion не настроен"
                               |
                 EvaluationRun (статусы + отчёты)
                  |                          |
     команда: ответ владельцу        планировщик: propose_cards(run)
     + кнопка «Внести в Notion»      (ключ ws|дата уже есть? -> пропуск)
       (создаёт карточку по запросу)          |
                  +-----------+---------------+
                              v
        ConfirmationStore.create_confirmation(action_type="notion_project_sync",
                 target_id="<ws>|<YYYY-MM-DD>", channel=TELEGRAM)  -> pending_confirmations
                              v
        Telegram: карточка [Опубликовать в Notion | Отклонить]  (callback ntn:conf:/ntn:rej:)
              |                                        |
  ntn:rej -> reject_action (в Notion ничего)    ntn:conf -> _is_authorized
                                                     -> resume_action (pending->confirmed, атомарно)
                                                     -> _handle_notion_sync:
                                                          NotionAsyncClient.find (проект+дата)
                                                          есть -> вернуть существующий id (без дубля)
                                                          нет  -> log_project_activity (POST /pages)
                                                     -> сбой: reopen_action(confirmed->pending),
                                                        «не записано, повторите», кнопки остаются
```

### Recommended Project Structure
```
src/
├── security/airgap.py          # + git_chain_eligibility()/partition (fail-closed), существующие sanitize_* остаются
├── core/domain/entities.py     # Workspace: + git_host, account (опциональные поля в конце)
├── persona/models.py           # _GitSourceParams в _ROLE_PARAMS; to_domain() передаёт git_host/account
├── persona/bindings.py         # git_source_settings() -> GitSourceSettings(stagnation_days, расписание)
├── brain/git_evaluator.py      # переписан: статусы, шлюз допуска, LLM+запасной шаблон, идемпотентность
├── connectors/git/provider.py  # защита в глубину, --branches --remotes, kill по таймауту, GIT_TERMINAL_PROMPT=0
├── connectors/notion/client.py # + find_project_activity(), required_scopes
├── composition.py              # + default_notion_client(), default_git_evaluator(db)
├── notifier/bot_handler.py     # + /git, ntn:* колбэки, git_evaluator внедряется в __init__
├── notifier/telegram.py        # + build_notion_sync_keyboard(), форматирование карточки
├── notifier/commands.py        # + CommandSpec "git" (connector_id="git_source")
├── brain/intent_router.py      # + "git" в VALID_ACTIONS
├── config.py                   # + NOTION_ACTIVITY_DB_ID
└── main.py                     # + run_git_progress_cycle, add_job(id="git_progress_job")
config/persona.yaml             # git_source.config: stagnation_days, расписание
config/prompts/git_progress_default.jinja2 (+ копия src/persona/prompts/git_progress.jinja2)
.env.example                    # + NOTION_ACTIVITY_DB_ID (только имя, без значения)
/opt/assistant-shared/assistant_shared/hitl/store.py  # + reopen_action(), find_confirmations()
```

### Pattern 1: Шлюз допуска (единственная точка истины, fail-closed)
**What:** Допущено только пространство, чей `clearance` равен ровно `public` или `internal`. Любое другое значение, исключение, отсутствие персоны, пересечение path/remote/ssh_alias с NDA-пространством → «исключено».
**When to use:** первая операция оценщика, до `list_repositories`/`fetch`/`log`/LLM/Notion.
**Example:**
```python
# Значения из src/core/domain/entities.py:30-32 (прочитаны):
#   PUBLIC = "public"
#   INTERNAL = "internal"
#   RESTRICTED_NDA = "restricted_nda"
_ELIGIBLE = frozenset({"public", "internal"})

def is_git_chain_eligible(ws: Any, nda_peers: Sequence[Any] = ()) -> bool:
    """True только при явном public/internal; любая ошибка или неизвестное значение = NDA (D-13)."""
    try:
        clearance = getattr(ws, "clearance", None)
        value = getattr(clearance, "value", clearance)      # StrEnum или str из WorkspaceConfig
        if str(value) not in _ELIGIBLE:
            return False
        for peer in nda_peers:                               # пересечение с NDA-пространством
            if _overlaps(ws, peer):
                return False
        return True
    except Exception:
        return False
```
Существующие `is_nda_workspace`/`sanitize_*` fail-OPEN (неизвестное → `False`, `airgap.py:158-196`), поэтому использовать их как шлюз нельзя; оставить как есть для прочих мест.

### Pattern 2: Выделенные колбэки и откат карточки
**What:** Колбэки `ntn:conf:{id}` / `ntn:rej:{id}` (до 64 байт: 9 + 36 символов uuid4). Подтверждение: `_is_authorized` → проверка статуса pending/не истёк → `resume_action` (атомарный переход в `confirmed`, затем обработчик) → при исключении `store.reopen_action(id)`, сообщение «Не записано в Notion, повторите», клавиатура остаётся.
**Example:**
```python
try:
    await resume_action(conf_id, store, confirmed_by=str(callback.from_user.id))
except ValueError:                      # уже обработано / нет (гонка двойного нажатия)
    await callback.answer("Запрос уже обработан", show_alert=True); return
except Exception as exc:                # сбой Notion внутри обработчика (D-09)
    logger.warning("Запись в Notion не выполнена: %s", exc)
    await store.reopen_action(conf_id)  # confirmed -> pending, только из confirmed
    await callback.answer("Не записано, повторите", show_alert=True); return
```
`ValueError` бросает именно `resume_action` при неудачном `confirm_action` [VERIFIED: `engine.py` Read]; `LookupError` — нет обработчика.

### Pattern 3: Идемпотентность двух уровней
1. Карточка: `target_id = f"{workspace_id}|{period_date}"` (дата в `config.TZ`). Перед созданием искать `action_type="notion_project_sync"` с этим `target_id` в статусах `pending`, `confirmed`, `rejected`; при совпадении не создавать. `expired` не блокирует (после истечения TTL допустима новая карточка за тот же день).
2. Notion: перед `POST /pages` запрос `POST /databases/{id}/query` с фильтром `and[relation contains project_id, date equals date_iso]`; нашлась страница → вернуть её id, ничего не создавать. Защищает от потерянного ответа и двойного нажатия. Ключа идемпотентности у Notion нет [CITED: developers.notion.com/reference/post-page — в документе не описан].

### Anti-Patterns to Avoid
- **Вызов `fetch_remote`/`get_commits_since` до проверки допуска** (так сейчас в `evaluate_workspaces`, `git_evaluator.py:84-92`). NDA не должен доходить даже до `list_repositories`, если ловушка считает любой вызов.
- **Ленивое создание оценщика на каждую команду**: реестр обработчиков HITL глобальный и в памяти (`_ACTION_HANDLERS`), после рестарта карточка, созданная до рестарта, подтвердится только если оценщик создан при старте.
- **Использовать колбэки `hitl:*` для Notion**: попадёт в `cb_hitl_confirm`, который пишет «успешно удален(а)» (`bot_handler.py:2072-2076`).
- **Фолбэк `conf.target_id` в качестве ID проекта Notion** (`git_evaluator.py:223`).
- **`logger.exception`/`ERROR` для штатных статусов** («Notion не настроен», «сбой SSH»): строка ERROR в окне старта краснит смоук OPS-01 (`docs/OPS_DEPLOY.md` §5). Штатные статусы — WARNING.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Состояние HITL, атомарное «ровно один раз» | Свои таблицы/флаги | `ConfirmationStore` + `resume_action` (`UPDATE ... WHERE status='pending'` атомарен) | Гонка двойного нажатия уже решена; схема не меняется |
| Разбор расписания | Парсер cron-строки | Структурные поля + `CronTrigger` kwargs | `CronTrigger` валидирует и бросает `ValueError` |
| Ротация ключей Gemini при 429/503 | Свои ретраи | `key_rotator.execute_with_failover` / паттерн кандидатов моделей из `summarizer.py` | Уже изолирует ключи по персоне (ISO-01) |
| Рендер промпта | f-строки | `render_prompt("git_progress", ...)` | Песочница, `StrictUndefined`, белый список персоны |
| Валидация ID Notion | Эвристика «не похоже на заглушку» | Положительный регэксп: 32 hex или UUID 8-4-4-4-12 | Заглушка `notion-proj-*` и пусто отсекаются автоматически, ничего не угадывается (D-06) |
| Идемпотентность записи | Локальный «журнал отправленного» | Запрос к Notion по (проект, дата) | Источник истины — сама база; локальный журнал расходится при сбое |
| Тест «ноль обращений» | Проверка по логам | Ловушки-обёртки (счётчик вызовов, `AsyncMock`/spy) на LLM, git, Notion внутри реального пути `handle_cmd_git` | Критерий 3 требует рантайм-путь, не юнит |

**Key insight:** вся инфраструктура HITL, персоны, шлюза Air-Gap и планировщика готова; риск фазы — в стыках (порядок проверок, жизненный цикл статусов карточки, различие `WorkspaceConfig` и `Workspace`), а не в новых библиотеках.

## Common Pitfalls

### Pitfall 1: NDA доходит до git (нарушение GIT-04/D-12)
**What goes wrong:** `SshGitProvider.list_repositories()` возвращает все пространства с `remote`/`ssh_alias`, включая `restricted_nda` (`provider.py:51-57`); оценщик делает `fetch_remote` и `get_commits_since` по каждому и создаёт NDA-карточку (тест `test_git_evaluator_creates_individual_pending_confirmations` сейчас ожидает NDA-карточку).
**How to avoid:** фильтр допуска первым шагом оценщика; в провайдере `fetch_remote`/`get_commits_since`/`list_repositories` тоже отказывают (`AirGapViolationError`, он уже есть в `src/core/exceptions.py`: `class AirGapViolationError(RuntimeError)`). Существующие тесты с ожиданием NDA-карточек переписать: `tests/test_notion_git_hitl.py` (создание карточек для обоих пространств, `test_nda_notion_payload_is_sanitized` в `tests/test_git_airgap_trap.py` остаётся, т.к. `sanitize_*` сохраняются как защита в глубину).
**Warning signs:** ловушка git-клиента фиксирует вызов с `ws.id` NDA-пространства.

### Pitfall 2: Обработчик `notion_project_sync` не зарегистрирован после рестарта
**What goes wrong:** регистрация идёт в `GitProgressEvaluator.__init__` (`git_evaluator.py:60`). Если оценщик создаётся лениво на `/git`, карточка, созданная планировщиком до рестарта и подтверждённая после, даст `LookupError: No handler registered`, а статус уже `confirmed` (потеря записи).
**How to avoid:** создать оценщик в `main()` сразу после `Database`/бота, внедрить в `EmailBotHandler` и в задачу. Проверка в VERIFICATION: `get_action_handler("notion_project_sync") is not None` после старта.

### Pitfall 3: Пропущенное пространство выглядит как «Застой»
**What goes wrong:** для пространства без каталога `get_commits_since` возвращает `[]` с warning (`provider.py:103-105`), оценщик считает `commit_count == 0 → is_stagnant` и показывает «Застой». На VPS каталоги `/opt/personal/guap-physics` и `/opt/work-tydex` отсутствуют [VERIFIED].
**How to avoid:** классификация до чтения: нет `remote` → «пропущено: нет remote»; `not Path(path).is_dir()` → «пропущено: нет каталога»; нет `.git` → «пропущено: не git-репозиторий». Эти пространства не попадают ни в LLM, ни в карточки.

### Pitfall 4: `git log` видит только HEAD
**What goes wrong:** `get_commits_since` запускает `git log` без ссылок (`provider.py:108-116`). После `git fetch` новые коммиты лежат в `refs/remotes/*`, HEAD не двигается. Эксперимент в этой сессии: после `fetch` `git log` показал 1 коммит, `git log --branches --remotes` — 2 [VERIFIED: локальный эксперимент].
**How to avoid:** добавить `--branches --remotes` в команду. Заметить: `--since` фильтрует по дате коммита (committer), а парсится `%aI` (author); расхождение допустимо, документировать. `max_commits=100` ограничивает `commit_count` сверху — писать «100+» при достижении предела.

### Pitfall 5: Типы пространства разных слоёв
**What goes wrong:** `SshGitProvider.list_repositories()` возвращает `WorkspaceConfig` из `current_persona()` (поля `label`, `clearance: str`), а порт и оценщик говорят про доменный `Workspace` (`name`, `clearance: WorkspaceClearance`). `WorkspaceConfig.model_config` — `frozen=True`, у него нет `name`.
**How to avoid:** брать `persona.to_domain().workspaces` (`models.py:to_domain` строит `Workspace(id, name=label, clearance=WorkspaceClearance(...), path, remote, ssh_alias, notion_project)`). Для критерия 1 («host, account») добавить в `Workspace` опциональные `git_host: str | None = None`, `account: str = ""` в конец и передать в `to_domain()`; поля `git_host`/`account` уже есть в `WorkspaceConfig` (`models.py`), сейчас `git_host` нигде не используется [VERIFIED: grep]. Конструкторов `Workspace(` в коде/тестах 17: поля с дефолтами не ломают вызовы; перед правкой проверить `tests/test_core_domain.py`.

### Pitfall 6: Подтверждённая карточка после сбоя Notion не повторяется
**What goes wrong:** `resume_action` сначала `confirm_action` (pending → confirmed), потом обработчик (`engine.py`). При исключении в обработчике статус остаётся `confirmed`; повторное нажатие даёт `ValueError ... current status: confirmed`. D-09 требует «карточка остаётся для повтора».
**How to avoid:** добавить в `ConfirmationStore` метод `reopen_action(id)` (`UPDATE ... SET status='pending', confirmed_by=NULL, confirmed_at=NULL WHERE id=? AND status='confirmed'`) и вызывать его в колбэке при исключении; тест в `/opt/assistant-shared/tests/test_hitl_shared.py`. Остаточный риск: падение демона между `confirm_action` и записью оставляет `confirmed` без страницы Notion — принять и описать (проверка «уже есть в Notion» защищает от обратного — дубля).

### Pitfall 7: Колбэки `hitl:*` дают неверный текст
См. Anti-Patterns. Дополнительно: `format_telegram_card` возвращает клавиатуру `list[list[dict]]` с `hitl:confirm:`; `TelegramNotifier.send_message(reply_markup: Any)` ждёт aiogram-объект, словари не примет. Клавиатуру строить в `src/notifier/telegram.py` как `build_hitl_action_keyboard`, а оценщику оставить только текст.

### Pitfall 8: Ключ даты в UTC, а расписание в Москве
`propose_notion_updates` берёт `report.period_end.date()` из UTC (`git_evaluator.py:163`). Воскресенье 20:00 MSK = 17:00 UTC, дата совпадает, но ручной запуск в 01:00 MSK понедельника — это воскресенье по UTC: ключ «воскресенье» вместо «понедельник». Считать дату в `ZoneInfo(config.TZ)`.

### Pitfall 9: Таймаут git оставляет процесс
`fetch_remote` при `asyncio.TimeoutError` не убивает дочерний процесс (`provider.py:88-90`, `proc` остаётся). Приватный remote без ключей может ждать ввода пароля. Передавать `env` с `GIT_TERMINAL_PROMPT=0` и `GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=10"`, при таймауте `proc.kill()` + `await proc.wait()`. Как и `git fetch --all`: тянет ВСЕ локальные remotes, а не только заявленный в персоне; предпочтительно `fetch --prune <имя remote из персоны>` — но в персоне хранится URL, не имя; оставить `--all` и принять (`--prune` удаляет только локальные remote-tracking refs).

### Pitfall 10: Смоук OPS-01 и задача планировщика
`scripts/deploy.py` ищет вызовы `<что-то>.add_job(<Name>, ..., id="...")` ast-разбором: первый аргумент обязан быть `ast.Name`, `id=` строковой константой; регистрация под `if` помечается «условной» и смоук не краснит, но и не требует (`deploy.py:452-535`). Журнал: строка `Added job "<func>" to job store`. Регистрировать задачу безусловно, `id="git_progress_job"`, функцию-цикл передавать именем; параметры расписания из `git_source_settings()`. Не запускать цикл при старте: строка ERROR/Traceback в окне старта (до «Run polling for bot» + 60 с) краснит смоук.

### Pitfall 11: Notion API
`NotionAsyncClient.NOTION_VERSION = "2022-06-28"`. Версии ≤ 2022-06-28 продолжают принимать `parent.database_id`, пока у базы один data source; при добавлении второго data source создание страниц ломается [CITED: developers.notion.com/guides/get-started/upgrade-faqs-2025-09-03]. Миграция на `2025-09-03` вне фазы; зафиксировать как known limitation. Автосоздание неизвестной опции `select` (`Status`: «Активно»/«Застой») документация create-page явно не подтверждает [CITED: post-page page: "doesn't say"], реальное поведение — [ASSUMED]; владельцу сообщить заранее перечень опций или проверить в живой базе при первом подтверждении.

### Pitfall 12: Тесты, которые фиксируют старое поведение
Затронуты: `tests/test_command_registry.py` (`len(active) == 9`, `len(tg_cmds) == 9`) и `tests/test_bot_menu.py` (`len(called_commands) == 9`) → станет 10 при активной привязке `git_source`; `tests/test_notion_git_hitl.py`, `tests/test_git_airgap_trap.py` (рендерят `src/persona/prompts/git_progress.jinja2` через обычный `jinja2.Template`); `tests/test_persona_config.py` (`len(default_domain.workspaces) == 4`) и `tests/test_ports_conformance.py`. Шаблон `git_progress` НЕ входит в `tests/fixtures/prompts_snapshot/MANIFEST.json` [VERIFIED], но существует в двух идентичных копиях (`config/prompts/git_progress_default.jinja2` — используется рантаймом через `persona.prompts["git_progress"]`, и `src/persona/prompts/git_progress.jinja2` — читается тестами); править обе одинаково. Литерал «более 7 дней» в шаблоне заменить переменной `stagnation_days`.

## Code Examples

### Поля персоны для git_source (по образцу `_ROLE_PARAMS`)
```python
# Source: паттерн src/persona/models.py (_TimesheetParams, _ROLE_PARAMS), прочитан в этой сессии.
class _GitSourceParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stagnation_days: int = Field(default=7, ge=1, le=365)
    day_of_week: str = Field(default="sun", pattern=r"^(mon|tue|wed|thu|fri|sat|sun)$")
    hour: int = Field(default=20, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)

_ROLE_PARAMS["git_source"] = _GitSourceParams   # добавить в словарь; пустой config валиден (все поля с дефолтами)
```
`config/persona.yaml` (блок `git_source`, ключ `config:`): `stagnation_days: 7`, `day_of_week: sun`, `hour: 20`, `minute: 0`. Новые поля с дефолтами не ломают `tests/synthetic_persona.py` (его править нельзя).

### Регистрация задачи
```python
# Source: паттерн src/main.py:772-865 (add_job с id=..., replace_existing=True).
gs = git_source_settings()          # из src/persona/bindings.py, дефолты при отсутствии привязки
scheduler.add_job(
    run_git_progress_cycle,
    "cron",
    day_of_week=gs.day_of_week, hour=gs.hour, minute=gs.minute,
    args=[db, git_evaluator, notifier],
    id="git_progress_job",
    replace_existing=True,
)
```
Первый аргумент — имя (`ast.Name`), как требует `deploy.py`.

### Тело цикла (граница try/except как у остальных циклов)
```python
async def run_git_progress_cycle(db, evaluator, notifier) -> None:
    try:
        run = await evaluator.evaluate()                 # шлюз допуска внутри
        cards = await evaluator.propose_cards(run)       # идемпотентно по ключу ws|дата
        ...                                              # отправка карточек и одной сводки при смене статуса
    except Exception as e:
        logger.warning("Ошибка цикла оценки git: %s", e)  # не падает демон; без logger.exception
```

### Ловушка для критерия 3 (на рантайм-пути)
```python
# Source: паттерн tests/test_git_airgap_trap.py (SpyGenAIClient) + tests/test_phase3_reachability.py (_make_handler).
class Trap:
    def __init__(self): self.calls = []
    def __getattr__(self, name):
        async def _rec(*a, **k): self.calls.append((name, a, k)); return []
        return _rec

handler = EmailBotHandler(bot=AsyncMock(), db=tmp_db, allowed_user_id=USER_ID, git_evaluator=evaluator_with_traps)
await handler.handle_cmd_git(message)          # реальный обработчик команды
assert [c for c in trap_git.calls if c[1] and c[1][0].id == nda_ws_id] == []
assert trap_llm.calls_for(nda_ws_id) == [] and trap_notion.calls == []
assert "NDA: исключено из оценки" in reply_text
```

### Проверка «уже записано» в Notion
```python
# Source: фильтры relation.contains + date.equals, объединённые в and [CITED: developers.notion.com/reference/post-database-query-filter]
payload = {"filter": {"and": [
    {"property": "Project", "relation": {"contains": project_page_id}},
    {"property": "Date", "date": {"equals": date_iso}},
]}, "page_size": 1}
resp = await client.post(f"/databases/{database_id}/query", json=payload)
resp.raise_for_status()
results = resp.json().get("results", [])
```
Имена свойств `Name`, `Project`, `Date`, `Commits`, `Status` и типы `title`/`relation`/`date`/`number`/`select` берутся из `log_project_activity` (`client.py:298-306`, прочитан); базы активности с такими свойствами пока нет, её создаёт владелец (D-07).

### Проверка формата ID Notion
```python
_NOTION_ID = re.compile(r"^(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12})$")
def is_valid_notion_id(value: str | None) -> bool:
    return bool(value) and bool(_NOTION_ID.match(value.strip()))
```
Формат совпадает с тем, что принимает `clean_page_id` в `scripts/provision_notion.py` (32 hex или 8-4-4-4-12). Применять дважды: при оценке (статус «Notion не настроен») и в обработчике перед записью. Тест: заглушки `notion-proj-*` и пустая строка отвергаются.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Notion `parent.database_id`, версия `2022-06-28` | Data sources, версия `2025-09-03` | Notion, 2025 | Старая версия работает, пока у базы один data source; миграция вне фазы [CITED: upgrade-faqs-2025-09-03] |
| Оценщик создаётся в тестах | Один экземпляр при старте через composition | эта фаза | Обработчик HITL зарегистрирован в рантайме |
| NDA → обезличенные агрегаты в Notion | NDA исключён целиком | решение владельца 2026-10-11 (D-12) | Строже прежнего; `sanitize_*` остаются как защита в глубину |

**Deprecated/outdated:**
- `ConnectorRole` docstring («портов и реализаций у них нет до Фазы 7», `entities.py`): устарел, порт git есть; поправить комментарий попутно, не критично.
- `getattr(config, "NOTION_ACTIVITY_DB_ID", "project_activity_logs")` (`git_evaluator.py:57`): удалить заглушку, использовать `config.NOTION_ACTIVITY_DB_ID` и валидатор ID.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Notion автоматически создаёт неизвестную опцию `select` для `Status` при создании страницы | Pitfall 11 | Запись упадёт 400 до тех пор, пока владелец не заведёт опции «Активно»/«Застой» в базе; поймается как «не записано, повторите» |
| A2 | Расширение `ConfirmationStore` методами `reopen_action`/`find_confirmations` в assistant-shared приемлемо владельцу как аддитивное (без миграции) | Standard Stack, Pitfall 6 | Если запрещено — запасной путь: прямой SQL-хелпер в `src/storage` (более громоздко) или новая карточка при сбое |
| A3 | Публичные https-remote `chat-app`/`assistant-core` доступны для анонимного `git fetch` с VPS (репозитории публичные) | Summary, Environment | Если приватные — fetch упадёт, в ответе «сбой SSH/fetch», оценка идёт без карточек; живой смоук это покажет |
| A4 | Политика при сбое fetch: оценивать по локальным данным не следует, карточка не создаётся | Architecture | Владелец может предпочесть «оценить по локальному состоянию»; решается строкой статуса |
| A5 | Поведение: для `rejected` ключ ws\|дата не пересоздаётся в тот же день, для `expired` пересоздаётся | Pattern 3 | Иная трактовка D-08 изменит только фильтр статусов |
| A6 | Хранить снимок результата команды для кнопки «Внести в Notion» в памяти обработчика (по короткому токену), после рестарта просить повторить команду | Architecture | Иначе нужен снимок в `daily_primed_context`; цена — небольшая |
| A7 | TTL карточки 1440 мин (по умолчанию в коде) подходит для воскресной карточки | Pattern 3 | Владелец, не открывший бота до понедельника вечером, увидит «срок истёк»; можно увеличить константой |
| A8 | Пересечение path/remote/ssh_alias допущенного пространства с NDA-пространством считать «remote вне правил» (D-13) и исключать | Pattern 1 | Трактовка D-13 «remote вне правил» в CONTEXT не раскрыта (см. Open Questions) |

## Open Questions

1. **Что именно значит «remote вне правил» в D-13?**
   - Известно: для NDA-пространства есть `forbidden_remote_substrings` (в персоне, например подстрока личного аккаунта) и `remote_violation_message`; для public/internal правил нет.
   - Неясно: считать ли «вне правил» только ошибку загрузки персоны/неизвестный `clearance`, или ещё и пересечение с данными NDA-пространств.
   - Рекомендация: реализовать минимум обязательно (неизвестный/ошибочный допуск → NDA) и пересечение path/remote/ssh_alias с любым NDA-пространством как дешёвое ужесточение (A8); подтвердить при планировании одним вопросом владельцу.

2. **Реальные ID Notion.** Владелец пришлёт ID страниц проектов и базы активности. До этого все пространства получают «Notion не настроен». Нужны ли в фазе проверка структуры базы по живому Notion (отдельный read-only запрос `GET /databases/{id}`) — по умолчанию нет, только проверка формата ID. Решает владелец после получения ID; на сам код фазы не влияет.

3. **Доступность публичных репозиториев для fetch с VPS (A3).** Проверяется живой частью VERIFICATION (`/git` после рестарта); критерий успеха не зависит от результата, оба исхода дают видимый статус.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python venv | всё | ✓ | 3.12.3 | — |
| git | `SshGitProvider` | ✓ | 2.43.0 (`/usr/bin/git`) | — |
| ssh | fetch по ssh-remote | ✓ бинарь `/usr/bin/ssh`; ключей нет (`~/.ssh`: `authorized_keys`, `known_hosts`) | — | Только https-remote публичных репозиториев; приватные дадут «сбой SSH» |
| `/opt/chat-app` (git, без remote) | живая проверка | ✓ каталог, `.git` есть, `git remote -v` пуст | — | Статус по данным персоны (remote задан в персоне) |
| `/opt/assistant-core` (git, origin https) | живая проверка | ✓ | — | — |
| `/opt/personal/guap-physics`, `/opt/work-tydex` | пространства персоны | ✗ каталогов нет | — | Статус «пропущено: нет каталога» (штатный путь GIT-02) |
| Реальные ID Notion, ключ Notion | запись | ✗ ID не выданы; ключ не проверялся (`.env` не читался) | — | «Notion не настроен»; полная цепочка на подменённом Notion |
| Gemini API | оценка | не проверялся (ключи в `.env`) | — | Запасной шаблон (D-01) |

**Missing dependencies with no fallback:** нет.
**Missing dependencies with fallback:** приватный SSH, каталоги двух пространств, ID Notion — все закрыты статусами.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode = auto`) |
| Config file | `/opt/assistant-core/pytest.ini` (`testpaths = tests`, `pythonpath = .`) |
| Quick run command | `.venv/bin/pytest tests/test_git_chain.py tests/test_notion_git_hitl.py tests/test_git_airgap_trap.py tests/test_git_connector.py -q` |
| Full suite command | `python3 scripts/gate.py` (содержит pytest, import-linter, shield, drift, SHA-256 боевой БД) |

Базовая линия: выбранные существующие файлы (`test_notion_git_hitl`, `test_git_airgap_trap`, `test_git_connector`, `test_notion_client`, `test_composition_di`, `test_ports_conformance`) — 77 passed за ~29 с [VERIFIED].

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GIT-01 | `default_git_evaluator` собирает `SshGitProvider` по привязке и scope `git.read`; вызывается из `main()` (ast) | unit + ast | `pytest tests/test_phase4_reachability.py -k composition -x` | ❌ Wave 0 |
| GIT-02 | Нет remote / нет каталога / нет `.git` → статус-строка, ни LLM, ни Notion; fetch-сбой → «сбой SSH» + warning, демон жив | unit (временные каталоги, `git init`) | `pytest tests/test_git_chain.py -k skipped -x` | ❌ Wave 0 |
| GIT-03 | `/git` отвечает по-русски; задача `git_progress_job` в `add_job` (ast) и расписание из персоны; LLM сбой → запасной шаблон; `stagnation_days` из персоны | unit + ast | `pytest tests/test_git_chain.py tests/test_phase4_reachability.py -x` | ❌ Wave 0 |
| GIT-04 | NDA, неизвестный `clearance`, ошибка персоны, пересечение с NDA → ноль вызовов git/LLM/Notion через `handle_cmd_git` и `run_git_progress_cycle`; строка «NDA: исключено из оценки» | integration с ловушками | `pytest tests/test_git_chain_airgap.py -x` | ❌ Wave 0 |
| NTN-01 | После сборки в `main()`-пути `get_action_handler("notion_project_sync")` не `None`; ID не из персоны/заглушка → «Notion не настроен» без карточки | unit | `pytest tests/test_git_chain.py -k notion -x` | ❌ Wave 0 |
| NTN-02 | Цепочка «команда → оценка → кнопка → карточка → подтверждение → запись» на `tmp_path`-БД с подменёнными SSH/Notion; отклонение: 0 вызовов Notion; повторное нажатие/повторный прогон: 1 запись; сбой Notion: «не записано, повторите», карточка снова pending, повторное нажатие пишет | integration | `pytest tests/test_phase4_chain_e2e.py -x` | ❌ Wave 0 |
| shared | `reopen_action`, `find_confirmations` | unit (assistant-shared) | `/opt/assistant-core/.venv/bin/pytest /opt/assistant-shared/tests/test_hitl_shared.py -x` | ✅ файл есть, тестов нет |
| регрессии | счётчики команд 9→10, ожидание NDA-карточек в старых тестах переписано | unit | `pytest tests/test_command_registry.py tests/test_bot_menu.py tests/test_notion_git_hitl.py -x` | ✅ править |

### Sampling Rate
- **Per task commit:** `pytest <файлы задачи> -x -q`
- **Per wave merge:** `python3 scripts/gate.py`
- **Phase gate:** гейт ЗЕЛЁНЫЙ; затем (только после ответа «да» владельца в опросе) `python3 scripts/deploy.py --backup --restart` и смоук OPS-01, живые проверки: задача в журнале «Added job … run_git_progress_cycle», `/git` отвечает.

### Wave 0 Gaps
- [ ] `tests/test_git_chain.py` — статусы пространств, LLM/запасной шаблон, `stagnation_days`, идемпотентность ключа, валидация ID Notion.
- [ ] `tests/test_git_chain_airgap.py` — ловушки LLM/git/Notion на пути `handle_cmd_git` и `run_git_progress_cycle` (NDA, неизвестный допуск, исключение при чтении персоны).
- [ ] `tests/test_phase4_reachability.py` — ast `main.py` (`add_job` с `id="git_progress_job"`, создание оценщика до `EmailBotHandler`), регистрация `Command("git")`, колбэков `ntn:*`; образец — `tests/test_phase3_reachability.py` (`check_execution_order`, `_make_handler`, `_make_callback`).
- [ ] `tests/test_phase4_chain_e2e.py` — сквозной сценарий на `tmp_path` с `run_migrations`.
- [ ] Тесты `reopen_action`/`find_confirmations` в `/opt/assistant-shared/tests/test_hitl_shared.py`.
- [ ] Рамочный pytest уже установлен; новых фикстур в `conftest.py` не требуется (страж боевой БД `tests/live_db_guard.py` действует автоматически).

## Security Domain

`security_enforcement` включён (ключ в `.planning/config.json`: `"security_enforcement": true`, ASVS level 1).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | частично | Только владелец: `EmailBotHandler._is_authorized(user_id)` в каждом новом обработчике (команда и оба колбэка) |
| V3 Session Management | нет | — |
| V4 Access Control | да | Подтверждение записи в Notion только из Telegram владельца (`channel=TELEGRAM`); статус через `ConfirmationStore` |
| V5 Input Validation | да | Положительная валидация ID Notion; Pydantic-ограничения полей расписания; `callback_data` разбирается по префиксу и uuid |
| V6 Cryptography | нет | Секреты (`NOTION_API_KEY`, Gemini) только из окружения, в логи не попадают |
| V8/V10 Data protection / LLM | да | Air-Gap: NDA не доходит до LLM/Notion/git; коммит-сообщения только public/internal; сводка клампится до 2000 символов (`summary[:2000]` в клиенте) |

### Known Threat Patterns for этого стека

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Утечка NDA во внешнюю LLM или Notion | Information Disclosure | Шлюз допуска fail-closed до любых вызовов + защита в провайдере + ловушки (D-12..D-14) |
| Запись в Notion без подтверждения | Tampering / Elevation | Единственный путь записи — обработчик `notion_project_sync` после `resume_action`; прямого вызова `log_project_activity` из оценщика/команды нет (тест по ast/ловушке) |
| Дублирование записи (двойное нажатие, повторный прогон) | Repudiation / Tampering | Атомарный `confirm_action` + ключ ws\|дата + проверка в Notion |
| Подмена ID проекта (заглушка, `target_id` как ID) | Tampering | Валидатор формата, удалить фолбэк `or conf.target_id` |
| Prompt injection через текст коммита в публичном репозитории | Tampering | Вывод LLM попадает только в карточку HITL; владелец видит текст до записи; клампинг длины; промпт передаёт коммиты как данные, не как инструкции |
| Зависание/утечка процесса git на закрытом remote | Denial of Service | `GIT_TERMINAL_PROMPT=0`, `BatchMode`, `kill()` по таймауту |
| Command injection в аргументах git | Tampering | `create_subprocess_exec` со списком аргументов (уже так); `-C` + путь из персоны, без shell |
| Несанкционированный пользователь нажимает кнопку | Spoofing | `_is_authorized` первым действием в колбэках; чужой `callback.from_user.id` → «Доступ запрещен» |
| Утечка секретов в логи | Information Disclosure | Логировать только статус/код и ID пространства; не логировать тело ответа Notion целиком, ключи, содержимое коммитов NDA |

## Sources

### Primary (HIGH confidence)
- Исходники репозитория, прочитанные в сессии: `src/brain/git_evaluator.py`, `src/connectors/git/provider.py`, `src/connectors/notion/client.py`, `src/security/airgap.py`, `src/composition.py`, `src/main.py` (500-911), `src/notifier/bot_handler.py` (100-420, 585-640, 890-940, 1355-1470, 1960-2250, 2590-2620), `src/notifier/commands.py`, `src/notifier/telegram.py` (части), `src/persona/models.py`, `bindings.py`, `current.py`, `prompts.py`, `seed.py`, `src/core/domain/entities.py`, `src/core/ports/clients.py`, `src/core/exceptions.py`, `src/brain/key_rotator.py`, `src/brain/summarizer.py`, `src/brain/intent_router.py`, `src/config.py`, `config/persona.yaml`, `config/prompts/git_progress_default.jinja2`, `.importlinter`, `scripts/deploy.py` (448-535), `docs/OPS_DEPLOY.md`, `tests/test_notion_git_hitl.py`, `tests/test_git_airgap_trap.py`, `tests/test_phase3_reachability.py`, `tests/test_command_registry.py`, `tests/test_bot_menu.py`
- `/opt/assistant-shared/assistant_shared/hitl/{models,engine,store}.py`, миграция `0002_pending_confirmations.sql`, `db/connection.py`
- `.planning/{REQUIREMENTS,STATE,ROADMAP,config}`, `04-CONTEXT.md`, `04-DISCUSSION-LOG.md`
- Локальные эксперименты: `git log` против `git log --branches --remotes` после `git fetch`; `CronTrigger` валидация; `APScheduler` default `misfire_grace_time=1` (`base.py:911`)

### Secondary (MEDIUM confidence)
- https://developers.notion.com/reference/post-page — типы свойств; идемпотентность не описана
- https://developers.notion.com/reference/post-database-query-filter — фильтры `relation.contains`, `date.equals`, `and`
- https://developers.notion.com/guides/get-started/upgrade-faqs-2025-09-03 — совместимость версий ≤ 2022-06-28 при одном data source

### Tertiary (LOW confidence)
- Автосоздание опций `select` в Notion (A1) — не подтверждено документацией страницы create-page.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — зависимостей нет, версии сняты с venv.
- Architecture: HIGH — построена на прочитанном коде; точки интеграции (ast-смоук, контракты import-linter) проверены.
- Pitfalls: HIGH для 1-10 (подтверждены чтением кода и экспериментом), MEDIUM для 11 (внешний API).
- Notion поведение вживую: MEDIUM-LOW — базы активности и ID ещё нет.

**Research date:** 2026-10-11
**Valid until:** 2026-11-10 (код стабилен; Notion API версия может измениться раньше)

## Рекомендуемое разбиение на планы (для планировщика)

Порядок и волны — на усмотрение планировщика (Claude's Discretion). Предлагаемая последовательность, где зависимости идут сверху вниз:

1. **Фундамент данных (Wave 1):** поля персоны `git_source` (`_GitSourceParams`, `git_source_settings`, `persona.yaml`, `Workspace.git_host/account`), `NOTION_ACTIVITY_DB_ID` в `config.py` и `.env.example` (только имя ключа), валидатор ID Notion, расширение `ConfirmationStore` (`reopen_action`, `find_confirmations`) с тестами в assistant-shared. Правки 1–3 файлов каждая — Claude.
2. **Безопасное ядро цепочки (Wave 2):** шлюз допуска в `airgap.py`, защита в глубину и исправления в `SshGitProvider` (допуск, `--branches --remotes`, kill по таймауту, env), переписанный `GitProgressEvaluator` (статусы, LLM + запасной шаблон, `stagnation_days`, ключ `ws|дата`, обработчик без фолбэка `target_id`), `NotionAsyncClient.find_project_activity` + `required_scopes`, шаблоны промпта (обе копии). Безопасность/NDA/HITL — только Claude.
3. **Проводка (Wave 3):** `composition.default_notion_client` / `default_git_evaluator`, создание в `main()` до `EmailBotHandler`, `/git` + `CommandSpec` + `VALID_ACTIONS` + диспетчеризация текста/голоса, колбэки `ntn:*` с откатом, `run_git_progress_cycle` и `add_job(id="git_progress_job")`, клавиатура/карточка в `telegram.py`.
4. **Тесты и обновление старых (Wave 4):** тест-файлы из Wave 0 Gaps, правка `test_command_registry`/`test_bot_menu`/`test_notion_git_hitl`. Шаблонные тесты-черновики допустимо отдать в agy, итог читает и гоняет гейт Claude.
5. **Верификация и выкатка (Wave 5):** гейт ЗЕЛЁНЫЙ, `04-VERIFICATION.md` (ast-достижимость, сквозной тест на временной БД, ловушки), затем опрос владельца о рестарте (`deploy.py --backup --restart`), смоук OPS-01 и живая проверка `/git`; `04-SUMMARY.md` в тот же прогон. До получения реальных ID Notion в живом рантайме ожидается статус «Notion не настроен» по всем пространствам.
