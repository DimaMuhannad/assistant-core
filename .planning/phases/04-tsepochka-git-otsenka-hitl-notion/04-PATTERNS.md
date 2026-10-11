# Phase 4: Цепочка Git → оценка → HITL → Notion - Pattern Map

**Mapped:** 2026-10-11
**Files analyzed:** 22 (новых и изменяемых)
**Analogs found:** 22 / 22 (все аналоги отслеживаются git; зеркал `.gsd/capabilities` нет)

## File Classification

| Файл | Роль | Data Flow | Ближайший аналог | Качество |
|------|------|-----------|------------------|----------|
| `src/security/airgap.py` (+`is_git_chain_eligible`) | utility (политика) | transform | он же, `is_nda_workspace` (стр. 158-196), но fail-OPEN | role-match (инвертировать) |
| `src/connectors/git/provider.py` (правки) | adapter | request-response (subprocess) | он же | exact |
| `src/connectors/notion/client.py` (+`find_project_activity`) | adapter | request-response | `log_project_activity` (стр. 288-321) | exact |
| `src/brain/git_evaluator.py` (переписать) | service | batch + event-driven | он же + `src/brain/summarizer.py` (LLM-кандидаты) | exact |
| `src/composition.py` (+`default_notion_client`, `default_git_evaluator`) | config/wiring | factory | `default_git_source_provider` (стр. 97-113) | exact |
| `src/persona/models.py` (+`_GitSourceParams`) | model | transform | `_TimesheetParams` / `_ROLE_PARAMS` (стр. 177-195) | exact |
| `src/persona/bindings.py` (+`git_source_settings`) | utility | transform | `schedule_source_settings`, `lms_settings` (стр. 81-104) | exact |
| `config/persona.yaml`, `.env.example`, `src/config.py` | config | — | существующие блоки `connectors`, `NOTION_*_DB_ID` | exact |
| `config/prompts/git_progress_default.jinja2` + `src/persona/prompts/git_progress.jinja2` | prompt | transform | они же (две идентичные копии) | exact |
| `src/core/domain/entities.py` (`Workspace.git_host/account`) | model | — | сам `Workspace` | exact |
| `src/main.py` (`run_git_progress_cycle`, `add_job`, создание оценщика) | scheduler | event-driven | `run_lms_monitor_cycle` (стр. 448) и `add_job` (стр. 772-790) | exact |
| `src/notifier/bot_handler.py` (`handle_cmd_git`, `ntn:*`) | controller | request-response | `cb_hitl_confirm` (стр. 2029-2080), `handle_cmd_lms_tasks` (стр. 2900) | role-match |
| `src/notifier/telegram.py` (`build_notion_sync_keyboard`) | utility | transform | `build_lms_tasks_keyboard` | role-match |
| `src/notifier/commands.py` (+`CommandSpec("git")`) | config | — | `CommandSpec(name="lms")` (стр. 148-155) | exact |
| `src/brain/intent_router.py` (`"git"` в `VALID_ACTIONS`) | config | — | существующий список | exact |
| `/opt/assistant-shared/assistant_shared/hitl/store.py` (+`reopen_action`, `find_confirmations`) | store | CRUD | `confirm_action`, `reject_action` (стр. 115-165) | exact |
| `tests/test_git_chain.py`, `test_git_chain_airgap.py` | test | — | `tests/test_git_airgap_trap.py` (SpyGenAIClient) | exact |
| `tests/test_phase4_reachability.py` | test | — | `tests/test_phase3_reachability.py` | exact |
| `tests/test_phase4_chain_e2e.py` | test | — | `tests/test_phase3_reachability.py` + `tests/test_notion_git_hitl.py` | role-match |
| правки `test_command_registry.py`, `test_bot_menu.py`, `test_notion_git_hitl.py` | test | — | они же | exact |

## Pattern Assignments

### `src/security/airgap.py` — шлюз допуска (utility, transform)

**Анализ:** `is_nda_workspace` (стр. 158-196) fail-OPEN: неизвестное значение, `None`, ошибка персоны дают `False`. Шлюз нужен обратный, как в RESEARCH Pattern 1. Сравнение `clearance in ("restricted_nda", WorkspaceClearance.RESTRICTED_NDA)` работает и для `str`, и для `StrEnum`.

```python
# airgap.py:158-175 — стиль (docstring с ID решения, getattr-доступ)
def is_nda_workspace(workspace: Any, persona: Any | None = None) -> bool:
    """Определить, относится ли рабочее пространство к контуру restricted_nda (D-05)."""
    ...
    clearance = (
        workspace.get("clearance")
        if isinstance(workspace, dict)
        else getattr(workspace, "clearance", None)
    )
```

Новая функция: разрешать только явное `public|internal`, остальное и любое исключение — `False` (D-13). `sanitize_*` не трогать (защита в глубину, тест `test_nda_notion_payload_is_sanitized` остаётся).

---

### `src/connectors/git/provider.py` (adapter, request-response)

**Analog:** сам файл (195 строк).

**Защита класса** (стр. 25-33): `required_scopes = ("git.read",)`, `role`, `connector_id`. Сохранить.

**Правки по месту:**
- `list_repositories` (стр. 39-57): `current_persona().workspaces` отдаёт `WorkspaceConfig`, не `Workspace`. Брать `persona.to_domain().workspaces` и применять шлюз допуска. Ошибку персоны оставить `return []` (уже fail-closed).
- `fetch_remote` (стр. 59-90): добавить проверку допуска в начало (`raise AirGapViolationError` из `src/core/exceptions.py`); `env` с `GIT_TERMINAL_PROMPT=0`, `GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=10"`; в ветке `except asyncio.TimeoutError` сделать `proc.kill()` и `await proc.wait()`.
- `get_commits_since` (стр. 92-135): в `cmd` после `"log"` добавить `"--branches", "--remotes"`; шаблон `cmd`:
```python
cmd = [self.git_bin, "-C", str(p), "log", f"-n{max_commits}",
       "--format=format:COMMIT_RECORD%x1f%H%x1f%an%x1f%aI%x1f%s", "--shortstat"]
if since is not None:
    cmd.append(f"--since={since.isoformat()}")
```
- Стиль ошибок: `logger.warning("... %s: %s", workspace.id, e)`, возврат `[]`/`False`, без raise в бот-цикл (кроме `AirGapViolationError`).

---

### `src/connectors/notion/client.py` (+`find_project_activity`, adapter)

**Analog:** `log_project_activity` (стр. 288-321), контекст `async with self._client() as client`:
```python
async with self._client() as client:
    resp = await client.post("/pages", json=payload)
    resp.raise_for_status()
    return resp.json()
```
Копировать эту структуру для `POST /databases/{id}/query` с `and[relation contains, date equals]` (RESEARCH, «Проверка уже записано»). Имена свойств `Name/Project/Date/Commits/Status` не менять. Добавить `required_scopes` по образцу провайдера git. Логировать только статус/код (без тела ответа и ключа).

---

### `src/brain/git_evaluator.py` (service, batch + event-driven)

**Analog:** сам файл (245 строк) + LLM-вызов из `src/brain/summarizer.py:175-195`.

**Конструктор и регистрация обработчика** (стр. 48-60) — сохранить, убрать заглушку:
```python
register_action_handler("notion_project_sync", self._handle_notion_sync)
# убрать: getattr(config, "NOTION_ACTIVITY_DB_ID", "project_activity_logs")  -> config.NOTION_ACTIVITY_DB_ID
```

**LLM с запасными моделями** (summarizer.py:175-195), копировать:
```python
candidate_models = [self.model]
for fallback_m in ["gemini-flash-latest", "gemini-3.5-flash-lite", "gemini-3.8-flash"]:
    if fallback_m not in candidate_models:
        candidate_models.append(fallback_m)
for cand in candidate_models:
    try:
        response = await client.aio.models.generate_content(
            model=cand, contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system_instruction, temperature=0.2),
        )
        if response and response.text:
            return response.text.strip()
    except Exception as model_err:
        logger.warning("Gemini model %s failed: %s, trying next candidate...", cand, model_err)
```
Для `brain` клиент внедрять через DI (import-linter), промпт через `render_prompt("git_progress", ...)`.

**Запасной шаблон** — текущая ветка public/internal (стр. 109-124): `"Зафиксировано N коммитов. Последние изменения: ..."`. NDA-ветку (стр. 110-114) удалить: NDA не доходит до оценщика (D-12).

**Исправления:** шлюз допуска первым, до `list_repositories`/`fetch_remote`/`get_commits_since` (сейчас стр. 84-92 вызывает их безусловно); `timedelta(days=7)` (стр. 76, 107) заменить `stagnation_days`; `target_id=f"{ws_id}|{date}"` вместо `report.workspace_id` (стр. 178); дату считать в `ZoneInfo(config.TZ)` (стр. 163); убрать `or conf.target_id` (стр. 223), валидировать ID Notion регэкспом (RESEARCH, «Проверка формата ID»).

**Обработчик HITL** (стр. 221-245) оставить формой: возвращает `{"success": True, "page_id": ...}`; исключение Notion не глотать (его ловит колбэк и делает `reopen_action`).

---

### `src/composition.py` (wiring, factory)

**Analog:** `default_git_source_provider` (стр. 97-113):
```python
def default_git_source_provider() -> BaseGitSourceProvider | None:
    from src.core.exceptions import MissingScopeError
    from src.persona.bindings import binding, has_binding
    if not has_binding("git_source"):
        return None
    from src.connectors.git.provider import SshGitProvider
    bound = binding("git_source")
    req = set(SshGitProvider.required_scopes)
    actual = set(bound.scopes)
    if not req.issubset(actual):
        raise MissingScopeError(f"Коннектор git_source требует scopes {req}, у персоны только {actual}")
    return SshGitProvider()
```
`default_notion_client()` и `default_git_evaluator(db)` строить так же: ленивые импорты адаптеров внутри функции, гейт `has_binding`, проверка scopes, `ConfirmationStore(db_path)`. Это единственное место, знающее конкретные классы.

---

### `src/persona/models.py` + `bindings.py` + `persona.yaml`

**Analog models.py:177-195:**
```python
class _TimesheetParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    default_project: str = Field(min_length=1)
    daily_norm_hours: float = Field(gt=0)

_ROLE_PARAMS: dict[str, type[BaseModel]] = {
    "schedule_source": _ScheduleSourceParams, "timesheet": _TimesheetParams, "lms": _LmsParams,
}
```
Добавить `_GitSourceParams` (поля с дефолтами из RESEARCH «Code Examples») и ключ `"git_source"`. Валидатор (стр. 220-232) выводит только `loc` и `msg` без значений, сохранить.

**Analog bindings.py:81-104:** frozen dataclass `*Settings` + функция `*_settings(persona=None)` через `binding(role, persona)` и `_config_value(bound, role, key)`. Для `git_source_settings` использовать дефолты при отсутствии ключей (все поля опциональны), в отличие от `_config_value`, которая требует ключ.

---

### `src/main.py` (scheduler, event-driven)

**Analog цикла:** `run_lms_monitor_cycle` (стр. 448-): сигнатура `(db, client, notifier)`, `logger.info("Starting ... cycle...")`, всё в `try/except Exception as e` с `logger.warning("...: %s", e)`.

**Analog регистрации** (стр. 772-790):
```python
scheduler.add_job(
    run_sentinel_cycle, "interval", hours=config.SCHEDULE_POLL_INTERVAL_HOURS,
    args=[db, schedule_parser, calendar_client, notifier],
    id="schedule_sentinel_job", replace_existing=True,
)
```
Для `git_progress_job` использовать `"cron"` с `day_of_week/hour/minute` из `git_source_settings()`, первый аргумент `ast.Name`, `id=` строковой константой, регистрация безусловная (смоук `scripts/deploy.py:452-535`). Оценщик создавать через `composition.default_git_evaluator(db)` до `EmailBotHandler` и передать в оба места. Не использовать `logger.exception`/ERROR для штатных статусов, не запускать цикл при старте.

---

### `src/notifier/bot_handler.py` (controller, request-response)

**Analog колбэка:** `cb_hitl_confirm` (стр. 2029-2080). Копировать каркас проверок:
```python
if not self._is_authorized(callback.from_user.id):
    await callback.answer("⛔ Доступ запрещен", show_alert=True); return
conf_id = callback.data.split(":", 2)[2]
store = self._get_confirmation_store()
conf = await store.get_confirmation(conf_id)
if not conf: ...                       # "Запрос не найден"
if conf.status == ConfirmationStatus.EXPIRED or conf.is_expired(): ...
if conf.status != ConfirmationStatus.PENDING: ...   # "Запрос уже обработан"
await resume_action(conf_id, store, confirmed_by=str(callback.from_user.id))
```
Отличия для `ntn:conf:`: текст успеха «записано в Notion» (не «удален»); `except` с `logger.warning` (не `logger.exception`), затем `await store.reopen_action(conf_id)` и `callback.answer("Не записано, повторите", show_alert=True)`. Регистрация колбэков по образцу стр. 390: `self.router.callback_query(F.data.startswith("ntn:conf:"))(self.cb_ntn_confirm)`. Не использовать префикс `hitl:*` (даст текст «удален(а)»).

**Analog команды:** `handle_cmd_lms_tasks` (стр. 2900-2918): `_is_authorized(message.from_user.id)` → `status_msg = await message.answer("⏳ ...")` → `try/except` → `status_msg.edit_text(text, reply_markup=kb)`. Клавиатура через aiogram `InlineKeyboardMarkup`/`InlineKeyboardButton` (как в `handle_cmd_timesheet`, стр. 1702-1706), а не словари из `format_telegram_card`. Ввод `git_evaluator` в `__init__` как необязательный параметр (как `lms_client`). В ответе строки статусов и «NDA: исключено из оценки».

---

### `src/notifier/commands.py` и `intent_router.py`

**Analog** `CommandSpec` (стр. 148-155):
```python
CommandSpec(name="lms", description=f"🎓 Отчеты и задания {lms_name}", category="academic",
            connector_id="lms", default_aliases=["задания", "отчеты", "labs"], handler_action="lms")
```
Новая: `name="git"`, `connector_id="git_source"`, `handler_action="git"`. Затем `"git"` в `VALID_ACTIONS` (`src/brain/intent_router.py`) и счётчики 9→10 в `tests/test_command_registry.py`, `tests/test_bot_menu.py`.

---

### `/opt/assistant-shared/assistant_shared/hitl/store.py`

**Analog:** `confirm_action` (стр. 115-139) и `reject_action` (стр. 140-164): атомарный `UPDATE ... WHERE id=? AND status='pending'`, чтение через `get_async_connection(self.db_path)`. `reopen_action` строить так же: `UPDATE ... SET status='pending', confirmed_by=NULL, confirmed_at=NULL WHERE id=? AND status='confirmed'`. `find_confirmations(action_type, target_id, statuses)` по образцу `list_pending` (стр. 99). Тесты в `/opt/assistant-shared/tests/test_hitl_shared.py`. Изменение аддитивное, без миграции (A2).

---

### Тесты

**Ловушка LLM:** `tests/test_git_airgap_trap.py:30-50` — `SpyGenAIClient` (`self.aio.models.generate_content = AsyncMock(side_effect=...)`, `recorded_calls`). Копировать для `test_git_chain_airgap.py`; ловушки git и Notion — обёртка со счётчиком вызовов (RESEARCH, «Ловушка для критерия 3»).

**Фабрики:** `tests/test_phase3_reachability.py:59-85` — `_make_handler(db)`, `_make_message(text)`, `_make_callback(data)`; `check_execution_order(func_node, patterns)` (стр. 88) для ast-проверки порядка «оценщик создан до `EmailBotHandler`». Для `add_job(id="git_progress_job")` тот же ast-подход.

**БД:** только `tmp_path` с `run_migrations`; боевая БД закрыта страж-фикстурой `tests/live_db_guard.py`. Не править `tests/synthetic_persona.py`, `tests/persona_tokens.py`.

## Shared Patterns

### Логирование и ошибки
**Источник:** `src/main.py` (циклы), `src/connectors/git/provider.py`.
**Применять:** ко всем новым модулям.
```python
logger = logging.getLogger(__name__)
logger.warning("Не удалось выполнить fetch для %s: %s", ws.id, e)   # %s, без f-строк, без print, без секретов
```
Штатные статусы («Notion не настроен», «сбой SSH») идут на WARNING, не ERROR (смоук OPS-01).

### Авторизация владельца
**Источник:** `src/notifier/bot_handler.py:299` (`_is_authorized`) первым действием в команде и обоих колбэках `ntn:*`.

### Air-Gap fail-closed
**Источник:** новая функция в `src/security/airgap.py`. Вызывать первой операцией в оценщике и в провайдере (`AirGapViolationError`, `src/core/exceptions.py`). Прямых вызовов `log_project_activity` вне HITL-обработчика быть не должно.

### Слои import-linter
`brain` не импортирует адаптеры (`src.connectors`, `src.notifier` и т.д.); `bot_handler` тоже. Конкретные классы создаёт только `src/composition.py`. `src.persona` не импортирует `src.config`/`src.brain`.

### Персона вместо хардкода
Значения профиля (`stagnation_days`, расписание) только из `config/persona.yaml` через `src/persona/bindings.py`; `tests/test_hardcode_scanner.py` с пустым baseline покраснит новый хардкод.

### Идемпотентность и HITL-карточка
Ключ `target_id = f"{workspace_id}|{YYYY-MM-DD}"` (дата в `config.TZ`), поиск через `find_confirmations`; payload и `ConfirmationChannel.TELEGRAM` как в текущем `propose_notion_updates` (стр. 168-184).

## No Analog Found

| Файл / элемент | Роль | Data Flow | Причина |
|----------------|------|-----------|---------|
| Валидатор ID Notion (`is_valid_notion_id`) | utility | transform | Ближайший образец — `clean_page_id` в `scripts/provision_notion.py`, но в `src/` такого нет; брать регэксп из RESEARCH |
| Откат карточки `confirmed → pending` в колбэке | controller | event-driven | В кодовой базе нет ни `reopen`, ни повторяемой карточки; шаблон только из RESEARCH Pattern 2 |
| Хранение снимка результата для кнопки «Внести в Notion» (A6) | controller | request-response | Аналога токен-снимка в памяти обработчика нет; ближайший по духу `self._edge_cache` в `bot_handler.py` (стр. 1707) |

## Metadata

**Analog search scope:** `src/brain`, `src/connectors`, `src/composition.py`, `src/security`, `src/persona`, `src/notifier`, `src/main.py`, `tests/`, `/opt/assistant-shared/assistant_shared/hitl`
**Files scanned:** около 25 (точечные чтения по номерам строк)
**Pattern extraction date:** 2026-10-11
