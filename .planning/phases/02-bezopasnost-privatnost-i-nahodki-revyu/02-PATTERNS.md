# Phase 2: Безопасность, приватность и находки ревью - Pattern Map

**Mapped:** 2026-10-10
**Files analyzed:** 33 (новые и изменяемые)
**Analogs found:** 31 / 33

Все пути-аналоги проверены как git-отслеживаемые (`git ls-files`) в своих репозиториях. Зеркал `.gsd/capabilities` нет. Слова NDA и литерал личного аккаунта в этом документе намеренно не приводятся (гейт shield).

## File Classification

| Файл (новый/изменяемый) | Репо | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|---|
| `assistant_shared/security/scanner.py` (новый: `Finding`, `scan_file_content`) | shared | utility | transform | `auditor.py::_scan_lines` (стр. 32-52) | exact |
| `assistant_shared/security/rules.py` (+`forbidden_keywords`, `match_workspace`, `collect_protected_keywords`) | shared | utility | transform | `rules.py::nda_rule_for` (стр. 19-26) | exact |
| `assistant_shared/security/auditor.py` (`audit_path`, `audit_repository(workspaces=)`) | shared | service | file-I/O | сам файл, `audit_path` стр. 119-190 | exact |
| `assistant_shared/security/patterns.py` (удалить `CORPORATE_NDA_KEYWORDS`) | shared | config | - | сам файл, стр. 32-42 | exact |
| `assistant_shared/security/__init__.py` (реэкспорт) | shared | config | - | сам файл | exact |
| `/opt/assistant-core/scripts/security_shield.py` (реальная обёртка: load_persona -> workspaces) | core | utility (CLI) | request-response | текущий `scripts/security_shield.py` + `src/persona/loader.py` | exact |
| `/opt/assistant-shared/scripts/security_shield.py`, `/opt/chat-app/scripts/security_shield.py` (делегаторы) | shared/chat-app | utility (CLI) | request-response | текущий `scripts/security_shield.py` core (argparse, fail-closed) | role-match |
| `/opt/chat-app/backend/app/api/v1/security.py` (2 строки вызова `audit_path`), через `/gsd-quick` | chat-app | controller | request-response | сам файл, стр. 39 и 81 | exact |
| тесты shared: `test_scan_file_content.py`, `test_workspace_matching.py` (новые), `test_shield_parity.py` (расширить), `test_security_shared.py`, `test_shield_regressions.py` (правка) | shared | test | - | `tests/test_shield_parity.py` | exact |
| `tests/test_security_shield_cli.py` (новый) | core | test | subprocess | `tests/test_gate.py` (subprocess-стиль) + `tests/test_persona_loader.py` | role-match |
| `tests/test_nda_script_parity.py` (переписать), `tests/test_synthetic_persona.py::test_no_real_nda_keywords` | core | test | - | `tests/test_nda_script_parity.py` | exact |
| `src/brain/dialog_safety.py` (новый) | core | utility | transform | `src/brain/intent_router.py` стр. 41 (`VALID_ACTIONS`, константы модуля) | role-match |
| `src/brain/secretary_dialog.py` (ветка стр. 610-615) | core | service | request-response | сама ветка | exact |
| `src/brain/intent_router.py` (стр. 141: общий список) | core | service | request-response | сама ветка | exact |
| `src/notifier/bot_handler.py` (`_warn_clear_requires_slash`, ветки стр. 1430 и 2583, `handle_cmd_help` +блок) | core | controller | event-driven | `handle_cmd_clear_dialog` стр. 1857-1890 | exact |
| `tests/test_clear_dialog_text_guard.py` (новый), `tests/test_secretary_dialog.py::test_secretary_dialog_clear_command` (переписать) | core | test | request-response | `tests/test_hitl_safety_guardrails.py` стр. 40-70 | exact |
| `src/persona/models.py` (`PrivacyConfig`, `PersonaConfig.privacy`) | core | model | - | `UiConfig` + `ui: UiConfig = Field(default_factory=UiConfig)` (стр. 261) | exact |
| `src/persona/notices.py` (новый: `email_ai_notice`) | core | utility | transform | `src/persona/bindings.py` (чистые функции над персоной) | role-match |
| `config/persona.yaml` (+`privacy`) | core | config | - | блок `ui:` того же файла | exact |
| `src/storage/db.py` (`has_notice_shown` / `mark_notice_shown`) | core | service | CRUD | `save_primed_context`/`get_primed_context` (стр. 2706-2732) | exact |
| `src/main.py::run_email_collector_cycle` (+показ предупреждения) | core | service | event-driven | сама функция стр. 199-230 | exact |
| `scripts/auth_google.py`, `.env.example` (+предупреждение) | core | config/CLI | - | сами файлы | exact |
| `tests/test_privacy_notice.py` (новый) | core | test | request-response | `tests/test_email_reply_workflow.py` стр. 336-380 + `tests/test_deploy_script.py` стр. 1356-1373 | role-match |
| `src/connectors/gdrive/client.py` (CR-01, WR-01, WR-02) | core | service | file-I/O | сам файл стр. 118-135, 256-262 + рекомендация ревью | exact |
| `tests/test_gdrive_client.py` (WR-12) | core | test | file-I/O | сам файл стр. 82-119 | exact |
| `scripts/gate.py` (WR-03, WR-04) | core | utility | batch | `compare_shield_findings` стр. 362-376, `KNOWN_SHIELD_FALSE_POSITIVES` стр. 55-65 | exact |
| `tests/test_gate.py` (WR-10 autouse-фикстура), `tests/test_gate_red_cases.py` | core | test | - | `test_gate.py` стр. 1327-1355 | exact |
| `tests/live_db_guard.py` (WR-07), `tests/test_live_db_guard.py` | core | utility/test | event-driven | сам файл стр. 19-25, 62-67 | exact |
| `scripts/deploy.py` (WR-08, WR-09) | core | utility | file-I/O | `_write_private` стр. 594-607, `make_db_copy` стр. 937-955 | exact |
| `tests/test_deploy_script.py` (тесты WR-08/09) | core | test | file-I/O | сам файл стр. 1550 (symlink-тест) | role-match |
| `tests/test_command_aliases.py` (WR-11), `tests/test_claude_md_gate_pointer.py` (WR-13) | core | test | - | сами файлы | exact |
| `/opt/chat-app/scripts/agy_cross_ai.sh` (WR-05, WR-06, T-uo4-02), `backend/tests/test_agy_cross_ai.py`, через `/gsd-quick` | chat-app | utility (shell) | batch | сам файл стр. 80-83, 308-322; фикстура `sandbox` в тесте | exact |

## Pattern Assignments

### `assistant_shared/security/scanner.py` (utility, transform) - SECF-02

**Analog:** `/opt/assistant-shared/assistant_shared/security/auditor.py::_scan_lines` (стр. 32-52) и `_forbidden_name_violation` (стр. 24-29).

Исходная построчная логика, которую нужно обобщить (слова приходят параметром, а не из константы):
```python
def _scan_lines(display_path, lines, is_public_repo, custom_keywords):
    keywords = custom_keywords if custom_keywords is not None else CORPORATE_NDA_KEYWORDS
    for idx, line in enumerate(lines, 1):
        for name, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                violations.append(f"{display_path}:{idx} - Found potential {name}")
        if is_public_repo:
            for kw in keywords:
                if kw in line:
                    violations.append(f"{display_path}:{idx} - Found proprietary corporate keyword '{kw}' in public repository!")
```
Правила: чистая функция (текст на вход, `list[Finding]` на выход), без `open`. Чтение файла остаётся в `auditor.py` (тест S09 chat-app патчит `auditor.open`). Короткое замыкание по запрещённому имени (как `check_file_content`, стр. 68-72). Форматтеры `format_cli` / `format_web` сохраняют текущие строки (гейт разбирает префиксы: `Forbidden file pattern committed:`, `CRITICAL`, `<путь>:<строка> - Found potential <имя>`, `... - Found proprietary corporate keyword`, `... - Read error`; `scripts/gate.py:305-359`). Сравнение слов через `casefold` (A4).

**Паттерн стиля модуля:** docstring на русском с ID требования (`"""... (SEC-01, SEC-02)."""`), `from pathlib import Path`, абсолютные импорты `assistant_shared.security.*`.

---

### `assistant_shared/security/rules.py` (utility, transform) - SECF-01/02

**Analog:** сам файл, `/opt/assistant-shared/assistant_shared/security/rules.py` стр. 11-26.
```python
@dataclass(frozen=True)
class NdaRemoteRule:
    forbidden_remote_substrings: tuple[str, ...]
    violation_message: str
    # ДОБАВИТЬ: forbidden_keywords: tuple[str, ...] = ()   # default сохраняет конструктор chat-app

def nda_rule_for(ws: dict[str, Any]) -> NdaRemoteRule | None:
    if ws.get("clearance") != "restricted_nda":
        return None
    return NdaRemoteRule(
        forbidden_remote_substrings=tuple(s for s in (ws.get("forbidden_remote_substrings") or ()) if s),
        violation_message=ws.get("remote_violation_message") or DEFAULT_REMOTE_VIOLATION,
    )
```
Новое: `match_workspace(repo, remote_urls, workspaces)` и `collect_protected_keywords(workspaces)` (эскиз в RESEARCH, раздел Code Examples): сравнение по `Path.resolve()` и `normalize_remote` (стр. 33-63 того же файла), при споре строжайший clearance, неизвестный clearance считается строжайшим. Подстроку пути не использовать.

---

### `assistant_shared/security/auditor.py` (service, file-I/O) - SECF-01/02

**Analog:** сам файл.

**NDA-блок из данных (копировать структуру `audit_path`, стр. 134-155) в `audit_repository`** вместо `is_tydex_repo` (стр. 210-225):
```python
if nda_rule is not None and not nda_rule.forbidden_remote_substrings:
    violations.append("CRITICAL: у NDA-пространства не заданы правила remote (fail-closed)")
if nda_rule is not None:
    try:
        remote_urls = list_remote_urls(target_path)
    except GitError as e:
        violations.append(f"CRITICAL: не удалось проверить remote NDA-пространства (fail-closed): {e}")
    else:
        forbidden_norm = [normalize_remote(sub) for sub in nda_rule.forbidden_remote_substrings]
        if any(norm_sub and norm_sub in normalize_remote(url) for url in remote_urls for norm_sub in forbidden_norm):
            violations.append(nda_rule.violation_message)
```
**Fail-closed вход (стр. 193-197):**
```python
if not repo_path.is_dir() or run_cmd(["git", "rev-parse", "--git-dir"], cwd=str(repo_path))[0] != 0:
    print(f"\n❌ SECURITY SHIELD ERROR: {repo_path} не является git-репозиторием.\n")
    return 1
```
Добавить: `workspaces is None` -> такой же `❌ ... ERROR` и `return 1` (D-20). Несопоставленный репозиторий -> строка `   ⚠️ ...` (не `🚨`, иначе `_SHIELD_LINE_RE` гейта сочтёт находкой). Заголовок профиля сохраняет слова `RESTRICTED` / `PUBLIC` (тест S01 chat-app).

**Формат вывода нарушений (стр. 252-257), не менять:**
```python
print("\n❌ SECURITY VIOLATIONS DETECTED:")
for v in violations:
    print(f"   🚨 {v}")
```
`audit_path`: добавить параметр `forbidden_keywords=()`; искать их при `nda_rule is None`; запрещённое имя файла = короткое замыкание (сейчас web сканирует содержимое дальше, стр. 174-185).

---

### `/opt/assistant-core/scripts/security_shield.py` (utility CLI, request-response) - SECF-01, D-06/D-08/D-18

**Analog:** текущая обёртка (`scripts/security_shield.py`, 24 строки) + `src/persona/loader.py::load_persona`.

**Сохранить:** импорт с запасным `sys.path` на `/opt/assistant-shared`, argparse (неизвестные флаги = exit 2), `sys.exit(audit_repository(...))`:
```python
parser = argparse.ArgumentParser(description="Security Shield: scan staged (default) or all tracked files.")
parser.add_argument("path", nargs="?", default=".", help="repository path (default: current directory)")
parser.add_argument("--all", action="store_true", help="scan all tracked files instead of staged ones")
args = parser.parse_args()  # unknown flags exit with code 2 (fail-closed), never treated as a path
sys.exit(audit_repository(Path(args.path).resolve(), check_staged_only=not args.all))
```
**Добавить** (эскиз из RESEARCH): до импорта `src.persona.loader` вставить корень репозитория в `sys.path`; `workspaces = [ws.model_dump() for ws in load_persona().workspaces]`; любое исключение -> печать `❌ SECURITY SHIELD ERROR: ... {type(exc).__name__}` без значений и `sys.exit(1)`. Убрать импорт и `__all__` с `CORPORATE_NDA_KEYWORDS`.

**Делегаторы (shared и chat-app):** аналога нет, база - эта же обёртка (argparse не нужен, аргументы пробрасываются); запуск `<ASSISTANT_CORE_DIR or /opt/assistant-core>/.venv/bin/python <core>/scripts/security_shield.py <argv>`, возврат кода; отсутствие файла -> `rc=1` с сообщением (fail-closed). Хук: `/opt/assistant-shared/.githooks/pre-commit`.

---

### `/opt/chat-app/backend/app/api/v1/security.py` (controller, request-response) - только `/gsd-quick`

**Analog:** сам файл, стр. 39 и 81:
```python
res = await asyncio.to_thread(audit_path, p_path, nda_rule=nda_rule_for(p))
```
Заменить на `audit_path(p_path, nda_rule=nda_rule_for(p), forbidden_keywords=collect_protected_keywords(workspaces))`. Данные берутся из `db.py:56-70` (`forbidden_keywords` уже в таблице). Побочные правки тестов chat-app перечислены в RESEARCH (матрица, 13 failed + ошибка сбора): `test_security_shared.py`, `test_nda_equivalence.py` S01/S02/S04/S05/P03, `test_shield_regressions.py`, `test_persona_api.py`, `test_synthetic_persona.py`, `test_pre_commit_hook.py`. Задание писать по образцу `01-CHATAPP-QUICK-BRIEF.md` (Phase 1) и проверять на копии библиотеки через `PYTHONPATH`.

---

### Тесты shared: `test_scan_file_content.py`, `test_workspace_matching.py`, `test_shield_parity.py`

**Analog:** `/opt/assistant-shared/tests/test_shield_parity.py` стр. 1-40.

**Импорты и фикстура временного git-репозитория:**
```python
from assistant_shared.security import audit_path, audit_repository, check_file_content, get_staged_or_tracked_files

def _init_test_git_repo(repo_path: Path) -> Path:
    repo_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=str(repo_path), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.org"], cwd=str(repo_path), check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(repo_path), check=True)
    (repo_path / "secret.py").write_text("api" + "_key = 'super_secret_token_12345'\n", encoding="utf-8")
    (repo_path / "private_key.txt").write_text("-----BEGIN " + "RSA PRIVATE KEY-----\nfake\n-----END " + "RSA PRIVATE KEY-----\n", encoding="utf-8")
    (repo_path / ".env.prod").write_text("SECRET=12345\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(repo_path), check=True)
```
Секреты только из частей. Синтетическое слово NDA передавать аргументом (не реальные слова). Расширить фикстурами D-13: пустой файл, слово NDA. Сравнивать нормализованные множества `(путь, вид, имя)`, не сырые строки. Тесты `workspaces=()` явно (D-20).

---

### `tests/test_nda_script_parity.py` (test) - D-10

**Analog:** сам файл (стр. 1-40): загрузка скрипта через `importlib.util.spec_from_file_location`, `_nda_workspace()` из `load_persona()`, булева переменная вместо печати значения (`same = ...; assert same, "..."` без значений). Переписать: тест 1 - `CORPORATE_NDA_KEYWORDS` отсутствует в `assistant_shared.security`; тест 2 - в `*.py` каталога `/opt/assistant-shared/assistant_shared/security` нет подстроки «tydex» и литерала аккаунта. Литералы в файле теста не писать: брать из `ws.forbidden_remote_substrings` и `ws.id`/`ws.path` во время теста. Прежнее чтение исходника регулярным выражением `"([^"]+)" in origin_norm` убрать.

---

### `tests/test_security_shield_cli.py` (test, subprocess) - SECF-01

**Analog:** `tests/test_gate.py` (запуск скриптов) и `tests/test_persona_loader.py` / `tests/conftest.py::default_persona_config` для временной персоны через `PERSONA_CONFIG_PATH` (см. `src/persona/loader.py:17-30,41-62`). Сценарии: NDA-репозиторий с запрещённым remote -> rc 1; слово NDA в публичном -> rc 1; битая персона -> rc 1; несопоставленный репозиторий -> rc 0 и `⚠️` в выводе. Секреты и слова собирать из частей/параметров.

---

### `src/brain/dialog_safety.py` (utility, transform) - SAFE-01

**Analog (значения дословно):** `src/brain/secretary_dialog.py:611` и `src/brain/intent_router.py:141`:
```python
if cleaned_text.lower() in ("/clear", "/reset", "очисти диалог", "забудь контекст", "сброс"):
if lower in ("/clear", "сброс", "очисти диалог", "забудь контекст", "/reset"):
```
Свести к одной константе `CLEAR_DIALOG_TRIGGERS` и тексту `CLEAR_DIALOG_TEXT_WARNING` (эскиз в RESEARCH). Модуль не импортирует адаптеры (`brain-no-adapters`). Маршрут `clear_dialog` в `FastIntentRouter` не удалять (`tests/test_fast_intent_router.py:19-32`).

### `src/brain/secretary_dialog.py` (service) - SAFE-01

**Analog:** сама ветка стр. 610-615. Структура возврата (сохранить все три формы `return_proposal` / `return_files`):
```python
if cleaned_text.lower() in CLEAR_DIALOG_TRIGGERS:
    msg = CLEAR_DIALOG_TEXT_WARNING   # БЕЗ await self.db.clear_dialog_history(user_id)
    if return_proposal:
        return (msg, [], None) if return_files else (msg, None)
    return (msg, []) if return_files else msg
```

### `src/notifier/bot_handler.py` (controller, event-driven) - SAFE-01, PRIV-01

**Analog:** `handle_cmd_clear_dialog` (стр. 1857-1890): `_is_authorized` в начале, ответ через `self.notifier.send_message(...)` с запасом `message.answer(...)`.
```python
if not self._is_authorized(message.from_user.id):
    return
...
if self.notifier:
    await self.notifier.send_message(text, chat_id=message.chat.id)
else:
    await message.answer(text)
```
Ветки `elif route_res.action == "clear_dialog": await self.handle_cmd_clear_dialog(message)` (стр. 1430-1431 текст, стр. 2583-2584 голос) заменить на `_warn_clear_requires_slash(message)`; для сообщения, начинающегося с `/`, оставить карточку: `(message.text or "").lstrip().startswith("/")` (у голоса `text is None`, Pitfall 8). `Command("clear","reset")` на стр. 411 и колбэки `dlg:*` не трогать. **Для `handle_cmd_help` (стр. 426-456):** блок PRIV-01 добавить в конец текста перед `self.notifier.send_message(text, chat_id=message.chat.id)`; брать только из `current_persona()`, без `self.db` (AST-тест `tests/test_deploy_script.py:1356-1373`).

### `tests/test_clear_dialog_text_guard.py`, `tests/test_secretary_dialog.py` (test)

**Analog:** `tests/test_hitl_safety_guardrails.py` стр. 40-70:
```python
db_file = tmp_path / "test_hitl_bot.db"
db = Database(f"sqlite+aiosqlite:///{db_file}")
await db.init_db()
await db.save_dialog_message(user_id=user_id, role="user", content="Hello")
handler = EmailBotHandler(bot=MagicMock(), db=db, allowed_user_id=user_id)
msg = MagicMock(); msg.from_user.id = user_id; msg.chat.id = user_id; msg.answer = AsyncMock()
await handler.handle_cmd_clear_dialog(msg)
assert await db.get_active_dialog_count(user_id) == 2
await db.close()
```
Настоящий `Bot` не создавать (токен/shield, Pitfall 7). Для `test_secretary_dialog_clear_command` (`tests/test_secretary_dialog.py:44-60`): сейчас `assert "очищен" in res.lower()` и `len(hist) == 0`; переписать на `len(hist) == 1` и `"/clear" in res`. Использовать `Database(db_path=":memory:")` как в файле.

---

### `src/persona/models.py` (model) - PRIV-01

**Analog:** `UiConfig` и поле персоны `ui: UiConfig = Field(default_factory=UiConfig)` (`models.py:261`); стиль модели из `WorkspaceConfig` (стр. 49-76):
```python
class PrivacyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    email_ai_notice: str | None = None
    external_ai_services: list[str] = Field(default_factory=list)
# PersonaConfig: privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
```
Поле необязательное, `tests/synthetic_persona.py` менять не нужно (дрейф проверяет гейт).

### `src/persona/notices.py` (utility, transform)

**Analog:** `src/persona/bindings.py` (функции над `PersonaConfig`, без `src.config`; пакет `src/persona/__init__.py:1-4` не тянет `.env`). `email_ai_notice(persona) -> str`: поле персоны, иначе нейтральный русский запасной текст со списком сервисов из данных. Токены владельца в коде не писать (`tests/test_hardcode_scanner.py`).

### `src/storage/db.py` (service, CRUD) - D-19

**Analog:** `save_primed_context` / `get_primed_context` (стр. 2706-2732):
```python
async with self.connection() as conn:
    await conn.execute(
        """INSERT OR REPLACE INTO daily_primed_context (date_key, summary_text, payload_json, created_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP);""",
        (date_key, summary_text, payload_json),
    )
    await conn.commit()
...
cursor = await conn.execute("SELECT date_key, ... FROM daily_primed_context WHERE date_key = ?;", (date_key,))
row = await cursor.fetchone()
```
`has_notice_shown(key)` / `mark_notice_shown(key)` оборачивают эти вызовы с ключом `notice:email_ai`; миграцию не создавать.

### `src/main.py::run_email_collector_cycle` (service, event-driven) - PRIV-01

**Analog:** сама функция (стр. 199-230): вся логика в `try ... except Exception as e: logger.exception("Error during email collection cycle: %s", e)`; `res = await email_collector.sync_all_accounts(days=3)`, `isinstance(r, dict)`. Добавить после `sync_all_accounts`: если есть результат с `status` не начинающимся с `skipped` и флаг не стоит -> `logger.info(...)`, `await notifier.send_message(text)`, `mark_notice_shown`. Логи: `%s`, без f-строк. Тест-образец: `tests/test_email_reply_workflow.py:336-380` (`AsyncMock` notifier, временная БД).

---

### `src/connectors/gdrive/client.py` (service, file-I/O) - CR-01, WR-01, WR-02

**Analog:** сам файл + фикс из ревью.

**Уязвимый код (стр. 258-262):**
```python
remote_name = backup_file["name"]
local_dest = Path(f"/opt/chat-app/uploads/gdrive_{remote_name}")
self.download_file(file_id, local_dest)
ingestion = AadhkIngestionService(db)
res = await ingestion.ingest_backup_file(local_dest)
```
**Паттерн исправления (01-REVIEW CR-01):**
```python
UPLOADS_DIR = Path("/opt/chat-app/uploads")
safe_name = Path(remote_name).name
if not safe_name or safe_name in {".", ".."}:
    raise ValueError("недопустимое имя файла на Google Drive")
local_dest = (UPLOADS_DIR / f"gdrive_{safe_name}").resolve()
if UPLOADS_DIR.resolve() not in local_dest.parents:
    raise ValueError("путь загрузки вышел за пределы каталога uploads")
```
(`download_file` стр. 118-135 делает `dest.parent.mkdir(parents=True)` и `open(dest, "wb")`.) Ошибку возвращать словарём `{"status": "error", ...}` по правилу «адаптеры не бросают в цикл бота» (`.claude/CLAUDE.md`, Error Handling) либо ловить на границе вызова. **WR-01:** `await asyncio.to_thread(self.find_latest_aadhk_backup)`, `await asyncio.to_thread(self.download_file, file_id, local_dest)`; то же для `upload_file`, `create_server_backup_archive`. **WR-02:** либо удалить `backup_server_data_to_drive` с тестами, либо `sqlite3.Connection.backup` + `os.open(..., 0o600)` вне `uploads`, без `.env`. Решение выбрать планировщику (метод нигде не вызывается).

### `tests/test_gdrive_client.py` (test) - WR-12 и тест CR-01

**Analog:** сам файл, стр. 82-119: декораторы `@patch("src.connectors.gdrive.client.build")`, `@patch("src.connectors.gdrive.client.Credentials")`, `token_file` с `scopes`, `mock_service.files().list().execute...`. Заменить единый `return_value` на `side_effect` (папка и файлы раздельно); добавить тест `sync_aadhk_from_drive` с именем `aadhk/../../../../escaped/evil.db` и проверкой, что файл не вышел за `tmp_path` (подменить `UPLOADS_DIR` через `monkeypatch`).

---

### `scripts/gate.py` (utility, batch) - WR-03, WR-04

**Analog:** сам файл. WR-04: ключ списка сейчас `(путь, вид) -> число` (стр. 55-65), сравнение `compare_shield_findings` (стр. 362-376) по счётчику. Паттерн исправления из ревью: хранить `sha256(путь + "\0" + строка файла)` и сравнивать отпечатки; `_SHIELD_AT_LINE_RE` (стр. 306) даёт путь и номер строки. Формат вывода `new`/`stale` (`"новая находка: ..."`, `"устаревшая запись (удалите из KNOWN_SHIELD_FALSE_POSITIVES): ..."`) сохранить. Список может только сокращаться. WR-03: см. рекомендации ревью (различение записей сервиса и теста; минимум - красная строка при >=2 смягчениях подряд).

### `tests/test_gate.py` (test) - WR-10

**Analog:** сам файл, стр. 1327-1355: тесты вызывают `gate.db_unchanged_check("a","b", evidence_fn=..., remeasure_fn=...)` без `diagnostics_fn`. Добавить autouse-фикстуру модуля:
```python
@pytest.fixture(autouse=True)
def _hermetic_db_diagnostics(monkeypatch):
    monkeypatch.setattr(gate, "_db_diagnostics", lambda: "диагностика")
    monkeypatch.setattr(gate, "_service_state", lambda: "inactive")
```

### `tests/live_db_guard.py` (utility, event-driven) - WR-07

**Analog:** сам файл, стр. 19-25 и 62-67:
```python
LIVE_DB_PATHS: tuple[Path, ...] = (CORE_DIR / "data" / "assistant.db", CORE_DIR / "assistant.db")
...
if not text or not text.endswith(_BASENAMES):   # префильтр пропускает симлинки с другим именем
    return False
return os.path.realpath(text) in BLOCKED_REALPATHS
```
Добавить абсолютный `Path("/opt/assistant-core/data/assistant.db")`; для префильтра сравнивать `realpath` либо `samefile`. Обновить `tests/test_live_db_guard.py::test_live_db_paths_constant_lists_both_live_files`. Модуль только stdlib, `src` не импортировать.

### `scripts/deploy.py` (utility, file-I/O) - WR-08, WR-09

**Analog:** сам файл. `_write_private` (стр. 594-607) использует `os.open(path, O_WRONLY|O_CREAT|O_TRUNC, 0o600)` + `os.fchmod`; исправление - `O_NOFOLLOW | O_CREAT | O_EXCL` во временный файл и `os.replace`, путь состояния в `/var/lib/assistant-core/` (0700). `make_db_copy` (стр. 937-955): `os.makedirs(target_dir, mode=0o700, exist_ok=True); os.chmod(target_dir, 0o700)` - `chmod` только для созданного каталога; `_inside_core` (стр. 937-939) расширить на поиск `.git` у родителей. Исключения: `BackupPathError`. Тесты: `tests/test_deploy_script.py` (symlink-пример на стр. 1550: `link.symlink_to(fake_core)`).

### `tests/test_command_aliases.py` (WR-11), `tests/test_claude_md_gate_pointer.py` (WR-13)

**Analog:** сами файлы. WR-13: `LEGACY_GATE_COMMAND = "python3 " + "/opt/chat-app" + "/scripts/" + "gate.py"` (сборка из частей сохранить) заменить регулярным выражением на `chat-app/(scripts/)?gate\.py`, также собранным из частей. WR-11: добавить `assert any(c.command == "lms" for c in catalog)` (`registry._build_default_catalog`).

### `/opt/chat-app/scripts/agy_cross_ai.sh` (shell) - WR-05, WR-06, T-uo4-02 (только `/gsd-quick`)

**Analog:** сам файл. `PROTECTED` (стр. 82-83) расширить: `tests/conftest.py`, `tests/live_db_guard.py`, `pytest.ini`, `scripts/deploy.py`, `src/config.py`, `requirements*.txt`. Выбор гейта (стр. 312-319):
```bash
elif [ -f "$TOP/scripts/gate.py" ]; then
  GATE=(python3 "$TOP/scripts/gate.py"); GATE_DIR="$TOP"
else
  GATE=(python3 "$SCRIPT_DIR/gate.py"); GATE_DIR="$SCRIPT_DIR/.."
fi
```
WR-06: ветка 3 -> отдельный код выхода / `GATE_KIND`. T-uo4-02: отказ, если `$TOP/scripts` или `$TOP/scripts/gate.py` - симлинк (`[ -L ... ]`), отдельный код выхода. Тест: `/opt/chat-app/backend/tests/test_agy_cross_ai.py` - фикстура `sandbox` (стр. 147-193: временный репозиторий, `scripts/gate.py` dummy, `AGY_GATE_CMD`), `run_adapter(sandbox)`, образец проверки отказа `test_dirty_tracked_file_refused` (стр. 271-279): `res.returncode == 10`, текст в `res.stderr`, `not sandbox.agy_log.exists()`, `commit_count` не изменился. Новый тест: заменить `scripts` симлинком, закоммитить, ожидать отказ до вызова агента.

---

## Shared Patterns

### Fail-closed security
**Source:** `/opt/assistant-shared/assistant_shared/security/auditor.py` стр. 193-197, 225-232 (`return 1` с `❌ SECURITY SHIELD ERROR`), `rules.py::nda_rule_for`.
**Apply to:** библиотека аудита, обёртки shield, делегаторы, `agy_cross_ai.sh`, `deploy.py`. Сбой чтения данных = красный итог; значения (слова, remote) не печатать.

### Вывод shield, который разбирает гейт
**Source:** `scripts/gate.py:307-359` (`_SHIELD_LINE_RE = ^\s+\U0001F6A8 (?P<body>.*)$`).
**Apply to:** любые новые сообщения `audit_repository`: находки с `🚨` и прежними префиксами, предупреждения только с `⚠️`.

### Тесты без секретов и слов NDA
**Source:** `/opt/assistant-shared/tests/test_shield_parity.py` стр. 28-33 (сборка из частей), `tests/test_nda_script_parity.py` (булева переменная, сообщения без значений).
**Apply to:** все новые тесты и документы (.planning, SUMMARY). `KNOWN_SHIELD_FALSE_POSITIVES` не растёт.

### HITL и Telegram-ответ
**Source:** `bot_handler.py::handle_cmd_clear_dialog` (стр. 1857-1890), `tests/test_hitl_safety_guardrails.py`.
**Apply to:** SAFE-01 (предупреждение), PRIV-01 (сообщение при старте почты): `_is_authorized`, `notifier.send_message(...)` с запасом `message.answer`.

### Логирование и границы импортов
**Source:** `src/main.py` (`logger.exception("... %s", e)`), `.importlinter`.
**Apply to:** `src/brain/dialog_safety.py` (без адаптеров), `src/persona/notices.py` (без `src.config`), `bot_handler` (без прямых импортов адаптеров). Без `print` в `src/`; логи `%s`.

### Данные вместо хардкода
**Source:** `src/persona/models.py` (`extra="forbid"`), `config/persona.yaml`, `tests/test_hardcode_scanner.py`.
**Apply to:** текст PRIV-01, правила NDA, имена пространств.

### Временная БД в тестах
**Source:** `Database(f"sqlite+aiosqlite:///{tmp_path/...}")` и `Database(db_path=":memory:")`; страж `tests/live_db_guard.py`. Боевую БД не открывать.

## No Analog Found

| Файл | Role | Data Flow | Причина |
|------|------|-----------|---------|
| `assistant_shared/security/scanner.py::Finding` (структурный тип находки) | model | transform | В библиотеке нет типа находки: сейчас находки - строки; брать форму из RESEARCH (Паттерн B), форматирование из `auditor.py` |
| Делегатор shield в shared и chat-app | utility | request-response | Подобных делегаторов нет; собрать из текущей обёртки и правил fail-closed (RESEARCH, раздел «Обёртки CLI») |

## Metadata

**Analog search scope:** `/opt/assistant-core` (src, scripts, tests), `/opt/assistant-shared` (security, tests, scripts), `/opt/chat-app` (scripts, backend/tests; чтение).
**Files scanned:** около 30 (прочитаны построчно целевые участки; `bot_handler.py`, `db.py`, `deploy.py`, `gate.py` - выборочно по строкам).
**Tracked-source gate:** `git ls-files` подтверждён для `scripts/deploy.py`, `tests/live_db_guard.py`, `tests/test_gdrive_client.py`, `/opt/chat-app/scripts/agy_cross_ai.sh`, `/opt/chat-app/scripts/security_shield.py`, `/opt/chat-app/backend/tests/test_agy_cross_ai.py`; все файлы `/opt/assistant-shared/assistant_shared/security/*` и тесты shared отслеживаются.
**Pattern extraction date:** 2026-10-10
