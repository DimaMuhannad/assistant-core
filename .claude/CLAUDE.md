<!-- GSD:project-start source:PROJECT.md -->

## Project

**Assistant Core — персональный ассистент-секретарь**

`assistant-core` — демон персонального ассистента (`assistant-worker.service`). Он работает круглосуточно: собирает почту, расписание, табель, LMS и Telegram, готовит брифинги и дайджесты, а через Telegram-бота ведёт диалог секретаря с реальными инструментами (календарь, напоминания, черновики писем). Сейчас платформа настроена на одного владельца (преподаватель-физик ГУАП и исследователь в Тидекс). Цель — превратить её в универсальную, настраиваемую данными платформу для любого специалиста. Профиль владельца уже вынесен в `config/persona.yaml`.

**Core Value:** Ассистент надёжно выполняет ежедневную работу секретаря. При этом **ни одно содержимое NDA-пространств не уходит во внешнюю LLM** и **ни одно необратимое действие не выполняется без подтверждения человека (HITL)**.

### Constraints

- **Боевая БД**: `/opt/assistant-core/data/assistant.db` не открывать и не менять при разработке и тестах — живые данные владельца.
- **Сервисы**: `assistant-worker.service` и `chat-app.service` заморожены. Рестарт assistant-worker — только после фазы с изменениями рантайма, по явному разрешению владельца, со смоук-проверкой.
- **Качество**: тесты проходят на 100%. Пропуски, xfail и deselected делают гейт красным.
- **Безопасность**: HITL для любого необратимого действия; Air-Gap NDA (содержимое `restricted_nda` не уходит во внешнюю LLM); security-проверки только ужесточаются, fail-closed.
- **Стек**: Python 3.12, async-first (aiosqlite, httpx/aiohttp), Pydantic/dataclass. Новые зависимости — только с одобрения владельца.
- **Ресурсы VPS**: 2 ГБ RAM + 4,5 ГБ swap. Для Node — `NODE_OPTIONS="--max-old-space-size=1536"`.
- **Язык**: всё, что видит пользователь, — по-русски. Код и коммиты — по-английски или по-русски.
- **Git**: коммиты прямо в `main` разрешены, без worktree.

<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->

## Technology Stack

## Languages

- Python 3.11+ (Docker image) / 3.12 (declared target in CLAUDE.md and `/opt/assistant-shared/pyproject.toml`) - all daemon code under `src/`, tests under `tests/`, scripts under `scripts/`
- Jinja2 templates - LLM prompt templates in `config/prompts/*.jinja2`
- YAML - persona configuration in `config/persona.yaml`, import contracts in `.importlinter`
- SQL - schema migrations in `/opt/assistant-shared/assistant_shared/db/migrations/*.sql` (shared library, consumed via `src/storage/db.py`)
- Shell - `scripts/install_hooks.sh`, git hooks in `.githooks/`

## Runtime

- Python process run as `python -m src.main` (see `Dockerfile` CMD and `src/main.py`)
- Long-running asyncio event loop; service supervised by `systemd` unit `assistant-worker.service` (per CLAUDE.md)
- Docker image base: `python:3.11-slim` (`/opt/assistant-core/Dockerfile`). Note: this differs from the Python 3.12 target declared in CLAUDE.md and in `assistant-shared` (`requires-python = ">=3.12"`). Treat 3.12 as the authoritative runtime; the Dockerfile is out of date.
- Timezone: `TZ` env var, default `Europe/Moscow` (`src/config.py`)
- pip with plain requirements files (no lockfile detected)
- Lockfile: missing (`requirements.txt` uses `>=` lower bounds only; `markupsafe==3.0.3` and `jinja2>=3.1,<4` are the only pins)
- Local virtualenv: `/opt/assistant-core/.venv` (used by the test and security-scan commands in CLAUDE.md)
- Shared library install: `/opt/assistant-shared` (editable/local package `assistant-shared` 0.1.0, provides `assistant_shared.db` and `assistant_shared.hitl`, `assistant_shared.security`)

## Frameworks

- asyncio (stdlib) - main concurrency model; CLAUDE.md mandates async-first I/O
- aiogram >=3.5.0 - Telegram Bot API framework (`src/notifier/bot_handler.py`, `src/notifier/telegram.py`)
- Telethon >=1.36.0 - Telegram user-account client (MTProto) for message collection (`src/collector/tg_collector.py`, session `data/telethon_userbot.session`)
- APScheduler >=3.10.4 - `AsyncIOScheduler` drives periodic polling in `src/main.py` (timezone = `config.TZ`)
- FastAPI >=0.111.0 + Uvicorn >=0.30.0 - listed in `requirements.txt`; no FastAPI application was found in `src/` during this scan (see CONCERNS if relevant)
- Pydantic >=2.7.0 - models (`src/models/`, persona models in `src/persona/models.py`)
- aiosqlite >=0.20.0 - async SQLite driver
- SQLAlchemy >=2.0.0 - listed in requirements; the storage layer uses raw aiosqlite via `assistant_shared.db.connection` (`src/storage/db.py`)
- Migrations: `assistant_shared.db.migrator.run_migrations` (owned by `/opt/assistant-shared`)
- pytest >=8.0.0 with pytest-asyncio >=0.23.0 - config in `/opt/assistant-core/pytest.ini` (`asyncio_mode = auto`, `testpaths = tests`, `pythonpath = .`)
- import-linter >=2.15 and grimp >=3.17 - architecture contracts in `.importlinter`, enforced by `tests/test_architecture_contract.py` (dev-only, see `requirements-dev.txt`)
- No build step; container built from `Dockerfile` (apt: build-essential, curl, tzdata)
- docker-compose (`docker-compose.yml`, version 3.8) - single service `assistant-worker`, mounts `./data`, `credentials.json` (read-only), `token.json`
- Security gate: `scripts/security_shield.py` (run with `/opt/assistant-core/.venv/bin/python3`)
- Quality gate: `python3 /opt/chat-app/scripts/gate.py` (external, until assistant-core has its own)

## AI / ML Libraries

- google-genai >=0.1.1 - `from google import genai`; `genai.Client(api_key=...)` used across `src/brain/*.py` (summarizer, reply_generator, methodist, debrief_parser, intent_router, secretary_dialog)
- Gemini models referenced in code: default `gemini-3.5-flash-lite` (`GEMINI_MODEL` env, `src/config.py`); other model IDs appear as fallbacks/routing targets in `src/brain/` (for example `gemini-3.5-flash`, `gemini-3.6-flash`, `gemini-3.8-flash`, `gemini-flash-latest`, `gemini-2.5-flash`)
- `src/brain/key_rotator.py` - multi-key rotation over `GEMINI_API_KEYS` (comma-separated), caches one `genai.Client` per key
- faster-whisper >=1.0.0 - local CPU Whisper (defaults: model `base`, device `cpu`, compute `int8`, 2 threads; `WHISPER_*` env vars in `src/config.py`)
- Groq hosted Whisper - `large-v3-turbo` via HTTP (`src/brain/voice.py`), used when a Groq key is configured; the code falls back to local faster-whisper

## Key Dependencies

- `google-api-python-client` >=2.125.0, `google-auth-httplib2` >=0.2.0, `google-auth-oauthlib` >=1.2.0 - Google Calendar, Drive and Gmail API access (`src/calendar/client.py`, `src/connectors/gdrive/client.py`, `src/collector/email_collector.py`)
- `httpx` >=0.27.0 - async HTTP for Notion, GUAP LMS and schedule-site fetches (`src/connectors/notion/client.py`, `src/connectors/guap_lms/client.py`)
- `beautifulsoup4` >=4.12.0 - HTML parsing for schedule and LMS pages (`src/parser/`, `src/connectors/guap_lms/`)
- `telegramify-markdown` >=1.4.0 - Markdown-to-Telegram formatting (`src/notifier/`)
- `python-dotenv` >=1.0.1 - loads `/opt/assistant-core/.env` at import of `src/config.py` (override=True)
- `pyyaml` >=6.0 - persona loading (`config/persona.yaml`)
- `jinja2` >=3.1,<4 and `markupsafe==3.0.3` - prompt rendering from `config/prompts/`
- `imapclient` - IMAP ingestion in `src/collector/email_collector.py`
- `pypdf` - PDF parsing (used by GUAP LMS / materials code)
- `html2text` - HTML-to-text conversion for email/LMS content
- `requests` - used by `src/connectors/guap_lms/client.py` and `scripts/download_fizikaguap_materials.py`; currently only available transitively via `google-auth-oauthlib`
- `faster_whisper` is declared; `telegramify_markdown` is declared
- `assistant-shared` (`/opt/assistant-shared`, deps: aiosqlite >=0.20.0, pydantic >=2.0.0) - DB schema migrations, connection helper with `sqlite_lower`, HITL helpers (`assistant_shared.hitl`, used by `src/notifier/bot_handler.py` and `src/brain/git_evaluator.py`), security library (`assistant_shared.security`). It is not declared in `requirements.txt`; it must be installed separately into the venv.
- stdlib `subprocess`-free async git: `asyncio.create_subprocess_exec` in `src/connectors/git/provider.py` (requires the `git` binary on the host)
- stdlib `sqlite3` - used in a few places alongside aiosqlite
- `zoneinfo` (stdlib) - timezone handling

## Configuration

- Loaded from `/opt/assistant-core/.env` via `python-dotenv` in `src/config.py`. A `.env` file exists at the repo root (contents intentionally not read); `.env.example` lists the variable names.
- Variable names (values never recorded here):
- Persona: `config/persona.yaml` (declarative user profile and source bindings; loaded by `src/persona/`). Prompts: `config/prompts/*.jinja2`.
- Secrets/credential files present at repo root (existence only): `.env`, `credentials.json` (Google OAuth client), `token.json` (Google OAuth token). Telethon session files live in `data/`.
- `pytest.ini`, `.importlinter`, `.githooks/` (pre-commit hooks installed by `scripts/install_hooks.sh`), `.gitignore`
- `Dockerfile`, `docker-compose.yml`

## Data Storage

- SQLite database, default `data/assistant.db` (path resolved relative to repo root in `src/config.py`). Production DB is not described further here.
- Schema and migrations are owned by `/opt/assistant-shared` (CLAUDE.md: assistant-core is schema owner side; chat-app is consumer).
- Telethon session file `data/telethon_userbot.session` and bot session `data/assistant_worker.session` (SQLite-backed).

## Platform Requirements

- Python 3.12 virtualenv at `/opt/assistant-core/.venv`
- Node 20 LTS is installed on the host (CLAUDE.md) but is not used by this Python project
- Git (for `src/connectors/git`)
- Host RAM is constrained (2 GB + 4.5 GB swap per CLAUDE.md); faster-whisper `base` model is chosen for this reason
- Single VPS, systemd service `assistant-worker.service` (or the Docker Compose service `assistant-worker`)
- Outbound network access to Telegram, Google APIs, Gemini API, Groq API, Notion API, IMAP/SMTP hosts, and the GUAP schedule/LMS sites

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

## Naming Patterns

- Python modules are `snake_case.py`, grouped by layer under `src/`: `src/core/`, `src/brain/`, `src/connectors/<system>/`, `src/storage/`, `src/notifier/`, `src/persona/`, `src/models/`.
- Each adapter package has an `__init__.py` and a `provider.py` or `client.py` entry point, e.g. `src/connectors/guap_lms/client.py`, `src/connectors/aadhk/provider.py`, `src/connectors/git/provider.py`.
- Tests are `tests/test_<area>.py` (e.g. `tests/test_brain.py`, `tests/test_core_architecture.py`, `tests/test_hitl_safety_guardrails.py`). Shared helpers live in `tests/conftest.py`, `tests/synthetic_persona.py`, `tests/persona_tokens.py`, `tests/hardcode_baseline.py`.
- Scripts in `scripts/` are `snake_case.py` CLI entry points (e.g. `scripts/security_shield.py`, `scripts/reconcile_schedule.py`).
- `snake_case`, verbs first: `fetch_schedule_raw`, `ingest_backup_file`, `get_monthly_pacing`, `generate_morning_brief`, `extract_json_object`.
- Async I/O methods are `async def` (no `_async` suffix): `async def health_check(self) -> bool` in `src/core/ports/connectors.py`.
- Private helpers are prefixed with a single underscore: `_ensure_dir_exists` in `src/storage/db.py`, `_testsuites` and `_safe_pytest_step` in `scripts/gate.py`.
- Test functions are `test_<behavior>` in `snake_case`, often long and descriptive: `test_summarizer_fallback_brief_generation`, `test_dialog_history_hitl_and_undo`.
- `PascalCase`: `Database` (`src/storage/db.py`), `GuapLmsClient` (`src/connectors/guap_lms/client.py`), `ScheduleEvent`, `WorkRecord` (`src/core/domain/entities.py`).
- Protocol ports end in the role name: `BaseConnector`, `BaseTimesheetProvider`, `BaseScheduleProvider` (`src/core/ports/connectors.py`), `CommandResolver` (`src/brain/intent_router.py`).
- Exceptions end in `Error`: `AirGapViolationError`, `MissingScopeError` (`src/core/exceptions.py`).
- Enums are `StrEnum` with lowercase string values: `ConnectorRole`, `WorkspaceClearance` (`src/core/domain/entities.py`).
- Module constants are `UPPER_SNAKE_CASE`: `VALID_ACTIONS` (`src/brain/intent_router.py`), `MAX_IGNORED_IMPORTS` and `LINT_ARGS` (`tests/test_architecture_contract.py`), `KNOWN_SHIELD_FALSE_POSITIVES` (`/opt/chat-app/scripts/gate.py`).
- Module-level logger is always `logger = logging.getLogger(__name__)`, with one exception: `src/main.py` uses `logging.getLogger("assistant-worker")`.
- Private module constants use a leading underscore: `_CONF_COL`, `_CAT_STUD` in `src/storage/db.py`.
- Type hints use PEP 604 unions (`str | None`) and built-in generics (`dict[str, Any]`), with `from __future__ import annotations` in core and newer modules. `typing.Any`, `Protocol`, `ClassVar` are imported from `typing`.
- Ports in `src/core/ports/` deliberately use `Any` for storage and model types so the core stays free of adapter imports (see the header of `src/core/ports/connectors.py`).

## Code Style

- No formatter configuration is committed (no `pyproject.toml`, `ruff.toml`, `.editorconfig`, `setup.cfg`, or `.prettierrc` in the repository root). Formatting follows the observed style: 4-space indent, double quotes, lines commonly up to ~100–120 characters. Do not reformat unrelated code in a diff.
- Trailing commas in multi-line calls and literals are the norm.
- No ruff, flake8, pylint, or mypy config exists for assistant-core.
- The only enforced static check is architectural: `import-linter` with the contracts in `/opt/assistant-core/.importlinter`. Run through the shared gate (`lint-imports`).
- `scripts/security_shield.py` is a security scan (secret/NDA keywords), not a style linter. It runs through the pre-commit hook `/opt/assistant-core/.githooks/pre-commit`.
- `src/core/` imports only stdlib and `src.core.*` (contract `core-is-pure`). Domain entities are `@dataclass(frozen=True, slots=True)` with `tuple` collections.
- `src/brain/` (use cases) must not import adapters (`src.connectors`, `src.calendar`, `src.parser`, `src.sender`, `src.collector`, `src.notifier`). Wiring goes through `src/composition.py`, which is the only place allowed to know concrete classes.
- `src/notifier/bot_handler.py` and `src/notifier/live_ticker.py` must not import adapters directly either.
- Indirect imports through `src.composition` are intentionally allowed (`allow_indirect_imports = True`).

## Import Organization

- None. Imports are absolute from the repository root (`from src.core.domain.entities import ...`). `pytest.ini` sets `pythonpath = .`, so tests import `src.*` and `tests.*` the same way.
- Namespace directories `src/connectors` and `src/sender` have no `__init__.py` in some cases; `.importlinter` lists them as `root_packages` explicitly. Do not rely on implicit discovery.

## Error Handling

- Domain errors are typed exceptions in `src/core/exceptions.py`. `AirGapViolationError(RuntimeError)` for NDA air-gap violations; `MissingScopeError(PermissionError)` for missing connector scopes. Raise these, do not raise bare `Exception`.
- Connectors and external calls degrade gracefully: functions return result objects or `None` with an error message instead of raising into the bot loop. Example: `GeminiSummarizer(api_key="")` is valid and `generate_morning_brief` falls back to a non-LLM template (`tests/test_brain.py`).
- Startup and background loops in `src/main.py` wrap each step in `try/except Exception as e` and log with `logger.warning("...: %s", e)`, then continue or skip the cycle. Keep this pattern for long-running workers so one failing source does not stop the daemon.
- `except Exception` appears about 200 times in `src/`. Treat it as the boundary pattern for I/O loops only. Do not introduce new broad catches inside pure domain or core code.
- Fail closed for security checks: `scripts/security_shield.py` uses argparse so unknown flags exit with code 2 instead of being treated as a path.
- Silently swallowing errors in HITL, memory-wipe, or deletion paths. These must be explicit and gated (see `tests/test_hitl_safety_guardrails.py`).

## Logging

- Use `logger = logging.getLogger(__name__)` at module top.
- Use `%s` lazy formatting, never f-strings, in log calls: `logger.warning("Could not parse schedule as JSON: %s", e)` (`src/main.py`).
- Use `warning` for recoverable skips, `info` for cycle progress, `error` only when an operation is lost.
- Some legacy code still contains `print(` calls (about 30 matches in `src/`). Do not add new `print` calls to `src/`; use the logger.
- Never log secrets, tokens, or email/password values. Log the status code and error message instead, as in `src/main.py`.
- Router decisions are persisted to SQLite `router_audit_log` (see `src/brain/intent_router.py`), which is an audit trail, not a log replacement.

## Comments and Documentation

- Docstrings and comments are predominantly in Russian, with some English (e.g. `tests/test_core_architecture.py`, `src/brain/intent_router.py` module docstring mixes English architecture notes). Per project rules, code comments may be English or Russian; keep the language of the surrounding file.
- Module docstrings explain the architectural role and the decision ID when one exists, e.g. `"""Порты коннекторов: структурные Protocol без привязки к конкретным системам."""` and references like `(D-01, D-02)`, `(PER-08, D-16)`, `(SEC-02)`.
- Explain *why* a constraint exists (security, air-gap, import-linter exceptions), not what the line does.
- Reference requirement or decision IDs for guardrails; they link code to `.planning/` decisions.
- Triple-double-quoted, one-line summary first. Dataclasses and protocols have short class docstrings. Methods on ports use a one-line docstring in Russian (`"""Загрузить резервную копию табеля и сохранить смены."""`).
- No enforced docstring format (no Google/NumPy/Sphinx convention). Do not add type restatements in docstrings; the annotations are the type source.

## Function Design

- Keyword-friendly defaults; ports use `...` (Ellipsis) as "value supplied by the implementation" (`default_project: str = ...` in `src/core/ports/connectors.py`).
- Profile-specific values (owner names, project tags, daily norms) must come from `config/persona.yaml` or the persona loader (`src/persona/loader.py`), never be hardcoded. `tests/test_hardcode_scanner.py` enforces this with a frozen baseline.
- Domain returns are frozen dataclasses. Connector/API results are `dict[str, Any]` in ports; concrete providers may return typed models.
- Use `Optional` via `X | None`, not sentinel strings.
- Async-first for all I/O: `aiosqlite` for storage, `httpx` or `aiohttp` for network. Use `asyncio` tasks with explicit cancellation in workers.
- Use `@asynccontextmanager` for connections (`Database.connection()` in `src/storage/db.py`).

## Module Design

- Public names are plain (no leading underscore). Use `__all__` in CLI-wrapper modules that re-export shared symbols (`scripts/security_shield.py`).
- Package `__init__.py` files exist and are small; import concrete modules directly in new code rather than adding barrel re-exports.
- Database schema and security library are owned by `/opt/assistant-shared` (`assistant_shared.db`, `assistant_shared.security`). Import them; do not copy them into `src/`. The schema changes only via migrations in that package.

## Data Modelling

- Domain entities: frozen, slotted dataclasses in `src/core/domain/entities.py` (`ScheduleEvent`, `WorkRecord`, `AcademicSubmission`).
- Config and API payloads: Pydantic v2 models (`pydantic>=2.7`), e.g. persona models in `src/persona/models.py`; serialise with `model_dump(mode="json")`.
- Schedule/lesson models: `src/models/schedule.py`, `src/models/message.py`, `src/models/second_brain.py`.

## Practical Rules for New Code

<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

## System Overview

```text

```

## Pattern Overview

- Single process, single event loop (`asyncio.run(main())` in `src/main.py`); blocking work is pushed to threads only where explicitly done (e.g. migrations, see `0da0dbe` in git history).
- Read autonomously, write with confirmation: collectors and sentinels fetch and store data in the background; any outward action (email send, grade/task change, calendar mutation triggered from chat) goes through HITL cards in the Telegram bot (`assistant_shared.hitl`).
- Two-stage filtering (documented in `docs/README_ARCH_GUIDE.md`): deterministic Python filters (hashes, regexes, diffs such as `src/detector/diff.py`, `src/detector/tg_filter.py`) run first; only selected items reach the LLM brain.
- Configuration-driven persona: `config/persona.yaml` is the single source (loaded by `src/persona/loader.py`, validated by Pydantic with `extra=forbid`) and is seeded into SQLite by `src/persona/seed.py`.

## Layers

- Purpose: Abstract entities and structural interfaces, no I/O.
- Location: `src/core/`
- Contains: `src/core/domain/entities.py` (ScheduleEvent, WorkRecord, AcademicSubmission, Task, EmailMessage, Workspace, GitCommit, GitProgressReport, Persona, ConnectorRole, WorkspaceClearance), `src/core/domain/events.py` (DomainEvent subclasses), `src/core/ports/connectors.py` and `src/core/ports/clients.py` (Protocols), `src/core/events/bus.py` (EventBus), `src/core/exceptions.py`.
- Depends on: stdlib and `src.core.*` only (contract `core-is-pure`).
- Used by: everything else.
- Purpose: Contracts that adapters satisfy.
- Location: `src/core/ports/connectors.py`
- Contains: `BaseConnector` (connector_id, required_scopes, health_check) and role-specific ports: `BaseTimesheetProvider`, `BaseScheduleProvider`, `BaseCalendarSink`, `BaseLMSProvider` (declares `REQUIRES_CONFIRMATION = {"submit_grade", "delete_task"}`), `BaseGitSourceProvider`. All are `@runtime_checkable`.
- Note: only `SshGitProvider` (`src/connectors/git/provider.py`) explicitly subclasses a port. Other adapters (`AadhkTimesheetProvider`, `LmsPortalProvider`, `ScheduleParserSource`, `GoogleCalendarSink`) are plain classes conforming structurally; conformance is checked in `tests/test_ports_conformance.py`.
- Purpose: LLM-assisted logic, dialogs, classification, summaries.
- Location: `src/brain/`
- Contains: `intent_router.py` (fast intent routing), `secretary_dialog.py` (SecretaryDialogEngine, tool-calling dialog), `tools_schema.py`, `methodist.py`, `summarizer.py` (GeminiSummarizer), `reply_generator.py`, `git_evaluator.py`, `debrief_parser.py`, `voice.py`, `key_rotator.py`.
- Depends on: `src/core`, `src/persona`, `src/security`, `assistant_shared.hitl`. Must not import `src.connectors`, `src.calendar`, `src.parser`, `src.sender`, `src.collector`, `src.notifier` directly (contract `brain-no-adapters`; indirect imports through `src.composition` are allowed by design, D-12).
- Purpose: Talk to external systems.
- Location: `src/connectors/{aadhk,gdrive,git,guap_lms,notion}/`, `src/calendar/`, `src/parser/`, `src/collector/`, `src/sender/`
- Depends on: `src/core`, `src/storage`, external SDKs.
- Used by: `src/composition.py` factories and `src/main.py`.
- Purpose: Owner-facing UI, commands, HITL cards, live HUD ticker.
- Location: `src/notifier/`
- Contains: `bot_handler.py` (`EmailBotHandler`, about 3200 lines, the main router), `commands.py`, `telegram.py` (TelegramNotifier), `live_ticker.py` (LiveTickerService).
- Restriction: `bot_handler` and `live_ticker` may not import adapters directly (contracts `bot-handler-no-adapters`, `live-ticker-no-adapters`).
- Purpose: SQLite persistence for events, snapshots, emails, HITL confirmations, sources, personas.
- Location: `src/storage/db.py` (`Database`, ~3000 lines), models in `src/models/` (`schedule.py`, `message.py`, `second_brain.py`).
- Connection and migrations come from the shared library: `assistant_shared.db.connection.get_async_connection`, `sqlite_lower`, `assistant_shared.db.migrator.run_migrations`. Schema migrations live in `/opt/assistant-shared/assistant_shared/db/migrations/` (`0001_initial_schema.sql`, `0002_pending_confirmations.sql`). assistant-core is the schema owner side.
- Purpose: Air-gap for NDA/corporate workspaces.
- Location: `src/security/airgap.py`
- Contains: `is_nda_email`, `mask_nda_email_data` (marker `[NDA: тело и вложения скрыты Air-Gap]`), `is_nda_workspace`, `sanitize_git_commits_for_llm`, `sanitize_notion_payload_for_airgap`.
- Used by: `src/brain/secretary_dialog.py`, `src/brain/reply_generator.py`, `src/brain/git_evaluator.py`, `src/brain/summarizer.py`. Test guards: `tests/test_airgap_trap.py`, `tests/test_git_airgap_trap.py`, `tests/test_nda_script_parity.py`.

## Composition Root and Wiring

- `default_timesheet_service(db)` → `AadhkTimesheetProvider(AadhkIngestionService(db))`, gated by persona binding `timesheet`
- `default_lms_client()` → `LmsPortalClient`, gated by binding `lms`
- `default_git_source_provider()` → `SshGitProvider`, gated by binding `git_source`
- `default_schedule_parser(...)`, `default_email_collector(db)`, `default_email_sender()`, `default_drive_client()`
- `schedule_site_url()` reads `config.SCHEDULE_URL` first, then the `schedule_source` persona binding.

## Runtime Entry Point and Startup Sequence

| Job id | Cycle function | Trigger |
|---|---|---|
| `schedule_sentinel_job` | `run_sentinel_cycle` | interval |
| `telegram_collector_job` | `run_telegram_collector_cycle` | every 30 min |
| `email_collector_job` | `run_email_collector_cycle` | every 15 min |
| `lms_monitor_job` | `run_lms_monitor_cycle` | every 30 min |
| `morning_brief_job` | `run_morning_brief_cycle` | daily 08:00 |
| `evening_digest_job` | `run_evening_digest_cycle` | daily 21:00 |
| `aadhk_gdrive_sync_job` | `run_aadhk_gdrive_sync_cycle` | interval |
| `nightly_reset_and_priming_job` | `run_nightly_reset_and_priming_cycle` | daily 04:00 |
| `weekly_memory_review_job` | `run_weekly_memory_review_cycle` | weekly, 09:00 |
| `live_ticker_refresh_job` | `run_live_ticker_refresh_cycle` | every 5 min |

## Data Flow

### Schedule Change Path (sentinel)

### Email Path (collector → HITL card)

### Chat / Intent Path

- Durable state lives in SQLite (`data/assistant.db`; path from `config.SQLITE_DB_PATH`). Do not open it directly in analysis.
- In-process state: APScheduler jobs, aiogram FSM/router state, `EmailBotHandler` message-id registry (`register_message`), `LiveTickerService` state.

## Key Abstractions

- Purpose: Abstract records the core daemon operates on: `ScheduleEvent`, `WorkRecord`, `AcademicSubmission`, `Task`, `EmailMessage`, `Workspace`, `GitCommit`, `GitProgressReport`, `Persona`.
- Pattern: frozen-style dataclasses with `ConnectorRole` and `WorkspaceClearance` StrEnums.
- Purpose: Swap GUAP LMS, AADHk timesheet, schedule site, Google Calendar, Git sources.
- Examples: `src/core/ports/connectors.py`; implementations in `src/connectors/*/provider.py`, `src/calendar/provider.py`, `src/parser/provider.py`.
- Pattern: `typing.Protocol` with `runtime_checkable`, `required_scopes` class variable, and persona-driven scope checks in `src/composition.py`.
- Purpose: Map each connector role to a workspace and its allowed scopes.
- Examples: `src/persona/models.py` (Pydantic, `extra=forbid`), `src/persona/bindings.py` (`binding`, `has_binding`, `schedule_source_settings`, `lms_settings`, `timesheet_settings`), `src/persona/current.py`, `src/persona/prompts.py`.
- Prompts are Jinja2 templates in `config/prompts/*.jinja2` (loaded with fallbacks from `src/persona/prompts/`).
- `src/core/events/bus.py` (`EventBus`) and `src/core/domain/events.py` (`ScheduleChanged`, `TimesheetSynced`, `TaskCreated`, `SecurityViolationDetected`, `DialogMemoryCleared`, `DelegatedToSpecialist`) exist, but no `src` module instantiates or publishes them. They are exercised only by `tests/test_core_events.py`. Treat them as planned infrastructure, not a live communication path.
- `src/parser/schedule_parser.py` produces `SchedulePayload`; `src/detector/diff.py` produces `ScheduleChangeDetector` diffs; `src/detector/temporal.py` and `src/detector/tg_filter.py` provide time and Telegram filtering.

## Entry Points

- Location: `src/main.py` (`main()`, `if __name__ == "__main__"`)
- Triggers: systemd `assistant-worker.service`; manual `python3 -m src.main [flags]`
- Responsibilities: Full startup, polling, scheduler.
- Location: `src/composition.py`
- Triggers: imported from `src/main.py`, `src/brain/*`, `src/notifier/bot_handler.py`.
- `scripts/*.py` (for example `scripts/reconcile_schedule.py`, `scripts/generate_brief.py`, `scripts/security_shield.py`, `scripts/auth_google.py`, `scripts/auth_telethon.py`, `scripts/provision_notion.py`). They are not part of the worker startup path.

## Architectural Constraints

- **Threading:** Single asyncio event loop. Heavy synchronous work must be offloaded. Example: migrations were moved to a worker thread for file DBs (commit `0da0dbe`, partial).
- **Global state:** `src/config.py` (module-level env reads), `src/persona/current.py` (current persona cache), module-level logging setup in `src/main.py`.
- **Path handling:** `src/main.py` mutates `sys.path` at import time to put the project root first and drop the script directory, so that the stdlib `calendar` module is not shadowed by `src/calendar/`.
- **Circular imports:** Avoided by lazy imports inside composition factories and inside `main()` (for example the AADHk imports inside `run_sentinel_cycle` and `run_aadhk_gdrive_sync_cycle`).
- **Declarative-only safety:** `BaseLMSProvider.REQUIRES_CONFIRMATION` lists `submit_grade` and `delete_task`, but the docstring states no enforcement mechanism exists yet. The bot's HITL delete dialog is currently the only deletion path.
- **Shared schema ownership:** Migrations and security library live in `/opt/assistant-shared`; changes there affect chat-app as a consumer.

## Anti-Patterns

### Dual wiring of collaborators in `main()`

### Defining ports without enforcing them at runtime

### Large single-module handlers

## Error Handling

- Early return on unsuccessful fetch (sentinel).
- Optional subsystems are guarded by `has_binding(...)` and return `None` (for example `default_lms_client`).
- Non-critical enrichment (AADHk reconcile after schedule change) is wrapped in try/except with debug logging.

## Cross-Cutting Concerns

<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-fast` for a trivial task inline, with no subagents and no PLAN.md
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
