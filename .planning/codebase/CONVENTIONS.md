---
last_mapped_commit: 5997ad6c8c219390ead42ea5132f2660f488f15d
last_mapped_at: 2026-10-09
---
# Coding Conventions

**Analysis Date:** 2026-10-09

## Naming Patterns

**Files:**
- Python modules are `snake_case.py`, grouped by layer under `src/`: `src/core/`, `src/brain/`, `src/connectors/<system>/`, `src/storage/`, `src/notifier/`, `src/persona/`, `src/models/`.
- Each adapter package has an `__init__.py` and a `provider.py` or `client.py` entry point, e.g. `src/connectors/guap_lms/client.py`, `src/connectors/aadhk/provider.py`, `src/connectors/git/provider.py`.
- Tests are `tests/test_<area>.py` (e.g. `tests/test_brain.py`, `tests/test_core_architecture.py`, `tests/test_hitl_safety_guardrails.py`). Shared helpers live in `tests/conftest.py`, `tests/synthetic_persona.py`, `tests/persona_tokens.py`, `tests/hardcode_baseline.py`.
- Scripts in `scripts/` are `snake_case.py` CLI entry points (e.g. `scripts/security_shield.py`, `scripts/reconcile_schedule.py`).

**Functions and methods:**
- `snake_case`, verbs first: `fetch_schedule_raw`, `ingest_backup_file`, `get_monthly_pacing`, `generate_morning_brief`, `extract_json_object`.
- Async I/O methods are `async def` (no `_async` suffix): `async def health_check(self) -> bool` in `src/core/ports/connectors.py`.
- Private helpers are prefixed with a single underscore: `_ensure_dir_exists` in `src/storage/db.py`, `_testsuites` and `_safe_pytest_step` in `scripts/gate.py`.
- Test functions are `test_<behavior>` in `snake_case`, often long and descriptive: `test_summarizer_fallback_brief_generation`, `test_dialog_history_hitl_and_undo`.

**Classes:**
- `PascalCase`: `Database` (`src/storage/db.py`), `GuapLmsClient` (`src/connectors/guap_lms/client.py`), `ScheduleEvent`, `WorkRecord` (`src/core/domain/entities.py`).
- Protocol ports end in the role name: `BaseConnector`, `BaseTimesheetProvider`, `BaseScheduleProvider` (`src/core/ports/connectors.py`), `CommandResolver` (`src/brain/intent_router.py`).
- Exceptions end in `Error`: `AirGapViolationError`, `MissingScopeError` (`src/core/exceptions.py`).
- Enums are `StrEnum` with lowercase string values: `ConnectorRole`, `WorkspaceClearance` (`src/core/domain/entities.py`).

**Variables and constants:**
- Module constants are `UPPER_SNAKE_CASE`: `VALID_ACTIONS` (`src/brain/intent_router.py`), `MAX_IGNORED_IMPORTS` and `LINT_ARGS` (`tests/test_architecture_contract.py`), `KNOWN_SHIELD_FALSE_POSITIVES` (`/opt/chat-app/scripts/gate.py`).
- Module-level logger is always `logger = logging.getLogger(__name__)`, with one exception: `src/main.py` uses `logging.getLogger("assistant-worker")`.
- Private module constants use a leading underscore: `_CONF_COL`, `_CAT_STUD` in `src/storage/db.py`.

**Types:**
- Type hints use PEP 604 unions (`str | None`) and built-in generics (`dict[str, Any]`), with `from __future__ import annotations` in core and newer modules. `typing.Any`, `Protocol`, `ClassVar` are imported from `typing`.
- Ports in `src/core/ports/` deliberately use `Any` for storage and model types so the core stays free of adapter imports (see the header of `src/core/ports/connectors.py`).

## Code Style

**Formatting:**
- No formatter configuration is committed (no `pyproject.toml`, `ruff.toml`, `.editorconfig`, `setup.cfg`, or `.prettierrc` in the repository root). Formatting follows the observed style: 4-space indent, double quotes, lines commonly up to ~100–120 characters. Do not reformat unrelated code in a diff.
- Trailing commas in multi-line calls and literals are the norm.

**Linting:**
- No ruff, flake8, pylint, or mypy config exists for assistant-core.
- The only enforced static check is architectural: `import-linter` with the contracts in `/opt/assistant-core/.importlinter`. Run through the shared gate (`lint-imports`).
- `scripts/security_shield.py` is a security scan (secret/NDA keywords), not a style linter. It runs through the pre-commit hook `/opt/assistant-core/.githooks/pre-commit`.

**Dependency direction (enforced by `.importlinter`):**
- `src/core/` imports only stdlib and `src.core.*` (contract `core-is-pure`). Domain entities are `@dataclass(frozen=True, slots=True)` with `tuple` collections.
- `src/brain/` (use cases) must not import adapters (`src.connectors`, `src.calendar`, `src.parser`, `src.sender`, `src.collector`, `src.notifier`). Wiring goes through `src/composition.py`, which is the only place allowed to know concrete classes.
- `src/notifier/bot_handler.py` and `src/notifier/live_ticker.py` must not import adapters directly either.
- Indirect imports through `src.composition` are intentionally allowed (`allow_indirect_imports = True`).

## Import Organization

**Order (observed):**
1. Standard library (`import asyncio`, `import logging`, `from dataclasses import dataclass`).
2. Third-party (`import aiosqlite`, `from google import genai`, `import pytest`, `import grimp`).
3. Project imports (`from src import config`, `from src.storage.db import Database`), usually after third-party.

Blank lines separate the groups in most modules, but not strictly: `src/brain/intent_router.py` interleaves a `Protocol` class between imports. When editing, keep new imports in the group that matches their origin, and do not move existing imports unless the diff needs it.

**Path Aliases:**
- None. Imports are absolute from the repository root (`from src.core.domain.entities import ...`). `pytest.ini` sets `pythonpath = .`, so tests import `src.*` and `tests.*` the same way.
- Namespace directories `src/connectors` and `src/sender` have no `__init__.py` in some cases; `.importlinter` lists them as `root_packages` explicitly. Do not rely on implicit discovery.

## Error Handling

**Patterns:**
- Domain errors are typed exceptions in `src/core/exceptions.py`. `AirGapViolationError(RuntimeError)` for NDA air-gap violations; `MissingScopeError(PermissionError)` for missing connector scopes. Raise these, do not raise bare `Exception`.
- Connectors and external calls degrade gracefully: functions return result objects or `None` with an error message instead of raising into the bot loop. Example: `GeminiSummarizer(api_key="")` is valid and `generate_morning_brief` falls back to a non-LLM template (`tests/test_brain.py`).
- Startup and background loops in `src/main.py` wrap each step in `try/except Exception as e` and log with `logger.warning("...: %s", e)`, then continue or skip the cycle. Keep this pattern for long-running workers so one failing source does not stop the daemon.
- `except Exception` appears about 200 times in `src/`. Treat it as the boundary pattern for I/O loops only. Do not introduce new broad catches inside pure domain or core code.
- Fail closed for security checks: `scripts/security_shield.py` uses argparse so unknown flags exit with code 2 instead of being treated as a path.

**Patterns to avoid:**
- Silently swallowing errors in HITL, memory-wipe, or deletion paths. These must be explicit and gated (see `tests/test_hitl_safety_guardrails.py`).

## Logging

**Framework:** standard library `logging`.

**Patterns:**
- Use `logger = logging.getLogger(__name__)` at module top.
- Use `%s` lazy formatting, never f-strings, in log calls: `logger.warning("Could not parse schedule as JSON: %s", e)` (`src/main.py`).
- Use `warning` for recoverable skips, `info` for cycle progress, `error` only when an operation is lost.
- Some legacy code still contains `print(` calls (about 30 matches in `src/`). Do not add new `print` calls to `src/`; use the logger.
- Never log secrets, tokens, or email/password values. Log the status code and error message instead, as in `src/main.py`.
- Router decisions are persisted to SQLite `router_audit_log` (see `src/brain/intent_router.py`), which is an audit trail, not a log replacement.

## Comments and Documentation

**Language:**
- Docstrings and comments are predominantly in Russian, with some English (e.g. `tests/test_core_architecture.py`, `src/brain/intent_router.py` module docstring mixes English architecture notes). Per project rules, code comments may be English or Russian; keep the language of the surrounding file.
- Module docstrings explain the architectural role and the decision ID when one exists, e.g. `"""Порты коннекторов: структурные Protocol без привязки к конкретным системам."""` and references like `(D-01, D-02)`, `(PER-08, D-16)`, `(SEC-02)`.

**When to Comment:**
- Explain *why* a constraint exists (security, air-gap, import-linter exceptions), not what the line does.
- Reference requirement or decision IDs for guardrails; they link code to `.planning/` decisions.

**Docstrings:**
- Triple-double-quoted, one-line summary first. Dataclasses and protocols have short class docstrings. Methods on ports use a one-line docstring in Russian (`"""Загрузить резервную копию табеля и сохранить смены."""`).
- No enforced docstring format (no Google/NumPy/Sphinx convention). Do not add type restatements in docstrings; the annotations are the type source.

## Function Design

**Size:** Functions are short where possible, but the connectors and `src/main.py` contain long procedural functions (cycle orchestration). Do not grow these further; extract helpers.

**Parameters:**
- Keyword-friendly defaults; ports use `...` (Ellipsis) as "value supplied by the implementation" (`default_project: str = ...` in `src/core/ports/connectors.py`).
- Profile-specific values (owner names, project tags, daily norms) must come from `config/persona.yaml` or the persona loader (`src/persona/loader.py`), never be hardcoded. `tests/test_hardcode_scanner.py` enforces this with a frozen baseline.

**Return Values:**
- Domain returns are frozen dataclasses. Connector/API results are `dict[str, Any]` in ports; concrete providers may return typed models.
- Use `Optional` via `X | None`, not sentinel strings.

**Async:**
- Async-first for all I/O: `aiosqlite` for storage, `httpx` or `aiohttp` for network. Use `asyncio` tasks with explicit cancellation in workers.
- Use `@asynccontextmanager` for connections (`Database.connection()` in `src/storage/db.py`).

## Module Design

**Exports:**
- Public names are plain (no leading underscore). Use `__all__` in CLI-wrapper modules that re-export shared symbols (`scripts/security_shield.py`).

**Barrel files:**
- Package `__init__.py` files exist and are small; import concrete modules directly in new code rather than adding barrel re-exports.

**Shared code:**
- Database schema and security library are owned by `/opt/assistant-shared` (`assistant_shared.db`, `assistant_shared.security`). Import them; do not copy them into `src/`. The schema changes only via migrations in that package.

## Data Modelling

- Domain entities: frozen, slotted dataclasses in `src/core/domain/entities.py` (`ScheduleEvent`, `WorkRecord`, `AcademicSubmission`).
- Config and API payloads: Pydantic v2 models (`pydantic>=2.7`), e.g. persona models in `src/persona/models.py`; serialise with `model_dump(mode="json")`.
- Schedule/lesson models: `src/models/schedule.py`, `src/models/message.py`, `src/models/second_brain.py`.

## Practical Rules for New Code

1. Place new use cases under `src/brain/`, new external-system adapters under `src/connectors/<system>/` with `provider.py` + `client.py`, and wire them only in `src/composition.py`.
2. Add a port (`Protocol`) in `src/core/ports/` before writing a second implementation.
3. Use frozen dataclasses for domain values; Pydantic for config and external payloads.
4. Use `logger = logging.getLogger(__name__)` and `%s` formatting.
5. Raise `AirGapViolationError` or `MissingScopeError` for policy failures.
6. Write tests with `async def test_...` (pytest-asyncio auto mode) and `tmp_path` for file/DB state.
7. Do not hardcode owner or profile values; read them from the persona config.

---

*Convention analysis: 2026-10-09*
