---
last_mapped_commit: 4ef89375cad045faaab6c362041879d2d4863602
last_mapped_at: 2026-10-10
---

# Coding Conventions

**Analysis Date:** 2026-10-10

## Naming Patterns

**Files:**
- Modules are `snake_case.py`, grouped by layer under `src/`: `src/core/`, `src/brain/`, `src/connectors/<system>/`, `src/storage/`, `src/notifier/`, `src/persona/`, `src/models/`, `src/security/`.
- Adapter packages expose an entry module named `provider.py` or `client.py`, e.g. `src/connectors/git/provider.py`, `src/connectors/guap_lms/client.py`, `src/connectors/aadhk/provider.py`.
- Tests are `tests/test_<subject>.py` (e.g. `tests/test_brain.py`, `tests/test_key_rotator.py`). Cross-cutting guardrails use `test_<cross-cutting>.py` (e.g. `tests/test_hitl_safety_guardrails.py`, `tests/test_airgap_trap.py`).
- Shared test helpers: `tests/conftest.py`, `tests/live_db_guard.py`, `tests/synthetic_persona.py`, `tests/persona_tokens.py`, `tests/hardcode_baseline.py`.
- CLI entry points in `scripts/` are `snake_case.py` (e.g. `scripts/security_shield.py`, `scripts/gate.py`).

**Functions:**
- `snake_case`, verb first: `fetch_schedule_raw`, `ingest_backup_file`, `generate_morning_brief`, `extract_json_object` (`src/brain/intent_router.py`).
- Async I/O methods are plain `async def` with no `_async` suffix: `async def health_check(self) -> bool` in `src/core/ports/connectors.py`.
- Private helpers have a single leading underscore: `_ensure_dir_exists` in `src/storage/db.py`, `_safe_pytest_step` in `scripts/gate.py`.
- Test functions are `test_<behavior>` in `snake_case`, often long and descriptive: `test_summarizer_fallback_brief_generation` (`tests/test_brain.py`), `test_dialog_history_hitl_and_undo` (`tests/test_hitl_safety_guardrails.py`).

**Variables:**
- `snake_case`. Module constants are `UPPER_SNAKE_CASE`: `VALID_ACTIONS` (`src/brain/intent_router.py`), `MAX_IGNORED_IMPORTS` and `LINT_ARGS` (`tests/test_architecture_contract.py`), `KNOWN_SHIELD_FALSE_POSITIVES` (`scripts/gate.py`).
- Module-private constants carry a leading underscore: `_CONF_COL`, `_CAT_STUD` in `src/storage/db.py`.
- Environment-derived settings are plain module-level names in `src/config.py` (e.g. `GEMINI_MODEL`, `SQLITE_DB_PATH`), read via `os.getenv(...)` with defaults.

**Types:**
- `PascalCase`: `Database` (`src/storage/db.py`), `GuapLmsClient` (`src/connectors/guap_lms/client.py`), `ScheduleEvent`, `WorkRecord` (`src/core/domain/entities.py`).
- Protocol ports end in the role name: `BaseConnector`, `BaseTimesheetProvider`, `BaseScheduleProvider` (`src/core/ports/connectors.py`), `CommandResolver` (`src/brain/intent_router.py`).
- Exceptions end in `Error`: `AirGapViolationError`, `MissingScopeError` (`src/core/exceptions.py`), `LiveDatabaseAccessError` (`tests/live_db_guard.py`).
- Enums subclass `StrEnum` with lowercase string values: `ConnectorRole`, `WorkspaceClearance` (`src/core/domain/entities.py`).

## Code Style

**Formatting:**
- No formatter configuration is committed to assistant-core: no `pyproject.toml`, `ruff.toml`, `.editorconfig`, `setup.cfg` or `.prettierrc` in the repository root.
- Observed style: 4-space indent, double quotes, lines up to roughly 100–120 characters, trailing commas in multi-line calls and literals.
- Do not reformat unrelated code in a diff. Match the surrounding file.

**Linting:**
- No ruff, flake8, pylint or mypy configuration exists for assistant-core.
- The only enforced static check is architectural: `import-linter` with contracts in `.importlinter` (`core-is-pure`, `brain-no-adapters`, `bot-handler-no-adapters`, `live-ticker-no-adapters`). It runs through `scripts/gate.py` and `tests/test_architecture_contract.py`.
- `scripts/security_shield.py` is a secret/NDA keyword scanner, not a style linter. It runs from the pre-commit hook `.githooks/pre-commit`.

**Typing:**
- PEP 604 unions (`str | None`) and built-in generics (`dict[str, Any]`). `from __future__ import annotations` is used in core and newer modules (e.g. `src/core/ports/connectors.py`).
- `typing.Any`, `Protocol`, `runtime_checkable`, `ClassVar` are imported from `typing`.
- Use `X | None` for optional values, not sentinel strings.

## Import Organization

**Order (observed):**
1. Stdlib (`asyncio`, `json`, `logging`, `dataclasses`, `pathlib`)
2. Third-party (`pytest`, `aiogram`, `google.genai`, `pydantic`)
3. Project (`from src.core.domain.entities import ...`, `from src import config`)

**Path Aliases:**
- None. Imports are absolute from the repository root. `pytest.ini` sets `pythonpath = .`, so tests import `src.*` and `tests.*` the same way (`from .synthetic_persona import ...` is used only inside `tests/` package helpers).
- `src/connectors` and `src/sender` are namespace directories in some cases. They are listed explicitly in `.importlinter` `root_packages`; do not rely on implicit discovery.
- Indirect imports through `src/composition.py` are allowed by design (`allow_indirect_imports = True`, decision D-12).

## Architectural Import Rules

- `src/core/` imports only the stdlib and `src.core.*` (contract `core-is-pure`). Domain entities are `@dataclass(frozen=True, slots=True)` with `tuple` collections (`src/core/domain/entities.py`).
- `src/brain/` (use cases) must not import adapters directly (`src.connectors`, `src.calendar`, `src.parser`, `src.sender`, `src.collector`, `src.notifier`). Wiring goes through `src/composition.py`, the only module that knows concrete classes.
- `src/notifier/bot_handler.py` and `src/notifier/live_ticker.py` must not import adapters directly.

## Error Handling

**Domain errors:**
- Raise typed exceptions from `src/core/exceptions.py`: `AirGapViolationError(RuntimeError)` for NDA air-gap violations, `MissingScopeError(PermissionError)` for missing connector scopes. Do not raise bare `Exception` from new code.

**Boundary pattern (I/O loops):**
- Connectors and external calls degrade gracefully: return a result object or `None` with an error message instead of raising into the bot loop. Example: `GeminiSummarizer(api_key="")` is valid and `generate_morning_brief` falls back to a non-LLM template (`tests/test_brain.py`).
- Background steps in `src/main.py` wrap each cycle in `try/except Exception as e` and log `logger.warning("...: %s", e)`, then continue. Keep this for long-running workers so one failing source does not stop the daemon.
- `except Exception` appears in about 29 files under `src/`. Treat it as a boundary pattern for I/O loops only. Do not add broad catches inside `src/core/` or pure logic.

**Security and safety paths:**
- Fail closed. `scripts/security_shield.py` uses argparse so unknown flags exit with code 2 rather than being treated as a path.
- Never swallow errors silently in HITL, memory-wipe or deletion paths. They must be explicit and gated (see `tests/test_hitl_safety_guardrails.py`).

**Optional subsystems:**
- Guard optional bindings with `has_binding(...)` and return `None` (e.g. `default_lms_client` in `src/composition.py`).

## Logging

**Framework:** standard library `logging`.

**Pattern:**
- Module top: `logger = logging.getLogger(__name__)`. Exception: `src/main.py` uses `logging.getLogger("assistant-worker")`.
- Use `%s` lazy formatting, never f-strings, in log calls: `logger.warning("Could not parse schedule as JSON: %s", e)` (`src/main.py`).
- `warning` for recoverable skips, `info` for cycle progress, `error` only when an operation is lost.
- Never log secrets, tokens or credentials. Log the status code and error message only.
- `print(` is not allowed in new code under `src/`; only about 4 legacy calls remain. Use the logger.
- Router decisions are persisted to SQLite table `router_audit_log` (`src/brain/intent_router.py`). This is an audit trail, not a log replacement.

## Comments and Documentation

**Language:**
- Docstrings and comments are predominantly Russian, with some English (`src/brain/intent_router.py` module docstring). Keep the language of the surrounding file. User-facing strings are Russian.

**When to comment:**
- Explain *why* a constraint exists (security, air-gap, import-linter exceptions, decision IDs), not what the line does.
- Reference decision or requirement IDs for guardrails, e.g. `(D-01, D-02)`, `(PER-08, D-16)`, `(SEC-02)`, `(GATE-02)`. They link code to `.planning/` decisions.

**Module docstrings:**
- Triple double quotes, one-line summary first, then the architectural role. Examples: `"""Порты коннекторов: структурные Protocol без привязки к конкретным системам."""` (`src/core/ports/connectors.py`), `"""Доменные сущности ядра.` (`src/core/domain/entities.py`).

**Method docstrings:**
- One line on port methods, in Russian: `"""Загрузить резервную копию табеля и сохранить смены."""`.
- No Google/NumPy/Sphinx format is enforced. Do not restate types in docstrings; annotations are the type source.

## Function Design

**Size:** keep functions focused. Large single-module handlers exist (`src/notifier/bot_handler.py`, about 3200 lines; `src/storage/db.py`, about 3000 lines). Do not grow them further; add a new module for a new use case.

**Parameters:**
- Keyword-friendly defaults. Ports use `...` (Ellipsis) to mean "value supplied by the implementation", e.g. `default_project: str = ...` in `src/core/ports/connectors.py`.

**Return values:**
- Domain returns are frozen dataclasses. Connector and API results in ports are `dict[str, Any]`; concrete providers may return typed Pydantic models.

**Async:**
- Async-first for all I/O: `aiosqlite` for storage, `httpx` or `aiohttp` for network, `asyncio.create_subprocess_exec` for git.
- Use `@asynccontextmanager` for connections (`Database.connection()` in `src/storage/db.py`).
- Workers use `asyncio` tasks with explicit cancellation.

## Module Design

**Exports:**
- Public names have no leading underscore. Use `__all__` in CLI-wrapper modules that re-export shared symbols (`scripts/security_shield.py`).

**Barrel files:**
- Package `__init__.py` files exist and are small. Import concrete modules directly in new code; do not add barrel re-exports.

**Shared libraries:**
- Database schema and security library are owned by `/opt/assistant-shared` (`assistant_shared.db`, `assistant_shared.security`, `assistant_shared.hitl`). Import them; do not copy them into `src/`. Schema changes happen only through migrations in that package.

## Data Modelling

- Domain entities: frozen, slotted dataclasses in `src/core/domain/entities.py` (`ScheduleEvent`, `WorkRecord`, `AcademicSubmission`, `Workspace`, `GitCommit`).
- Config and external payloads: Pydantic v2 models with `extra=forbid` for persona config (`src/persona/models.py`). Serialize with `model_dump(mode="json")`.
- Schedule and message models: `src/models/schedule.py`, `src/models/message.py`, `src/models/second_brain.py`.

## Profile Values

- Owner-specific values (names, project tags, daily norms, schedule targets) come from `config/persona.yaml` through `src/persona/loader.py`, never hardcoded. `tests/test_hardcode_scanner.py` enforces this with a frozen baseline (`tests/hardcode_baseline.py`) that can only shrink.

## Practical Rules for New Code

1. Place use cases under `src/brain/`, external adapters under `src/connectors/<system>/` (`provider.py` + `client.py`), and wire them only in `src/composition.py`.
2. Add a `Protocol` port in `src/core/ports/` before a second implementation exists.
3. Use frozen dataclasses for domain values; Pydantic for config and external payloads.
4. Use `logger = logging.getLogger(__name__)` and `%s` formatting.
5. Raise `AirGapViolationError` or `MissingScopeError` for policy failures.
6. Write tests as `async def test_...` (pytest-asyncio `asyncio_mode = auto`) and use `tmp_path` for file and DB state.
7. Do not hardcode owner or profile values; read them from the persona config.

---

*Convention analysis: 2026-10-10*
