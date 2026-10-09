---
last_mapped_commit: 5997ad6c8c219390ead42ea5132f2660f488f15d
last_mapped_at: 2026-10-09
---
# Codebase Structure

**Analysis Date:** 2026-10-09

## Directory Layout

```
assistant-core/
├── src/                    # Daemon source (Python package)
│   ├── main.py             # Worker entry point (python3 -m src.main)
│   ├── composition.py      # Composition root factories (lazy adapter imports)
│   ├── config.py           # Env-driven settings
│   ├── core/               # Pure domain entities, ports, events, exceptions
│   ├── brain/              # LLM use-cases, dialogs, routing, summaries
│   ├── notifier/           # Telegram interface (aiogram handlers, HITL cards, HUD)
│   ├── connectors/         # Adapters: aadhk, gdrive, git, guap_lms, notion
│   ├── calendar/           # Google Calendar client and sink adapter
│   ├── parser/             # Schedule site parser (JSON/HTML)
│   ├── collector/          # Telegram userbot and email collectors
│   ├── sender/             # Email sending adapter
│   ├── detector/           # Deterministic diff and filter logic
│   ├── models/             # Pydantic/dataclass payload models
│   ├── persona/            # Persona loader, models, DB seeding, prompts
│   ├── security/           # Air-gap (NDA) masking and sanitizing
│   └── storage/            # SQLite Database facade (aiosqlite)
├── config/
│   ├── persona.yaml        # Declarative owner persona and bindings
│   └── prompts/            # Jinja2 prompt templates (*_default.jinja2)
├── tests/                  # pytest suites, fixtures, architecture contract tests
│   └── fixtures/           # Prompt snapshots and synthetic prompts
├── scripts/                # One-off and maintenance CLI scripts
├── docs/                   # Architecture guide, roadmap, specs, reports
├── .githooks/              # Git hooks (pre-commit)
├── .planning/              # GSD planning (codebase maps live in codebase/)
├── .importlinter           # Architecture contracts
├── pytest.ini              # Pytest configuration
├── requirements.txt        # Runtime dependencies
├── requirements-dev.txt    # Dev/test dependencies
├── Dockerfile              # Container build
├── docker-compose.yml      # Compose definition
├── .env.example            # Template for environment variables (do not read .env)
└── CLAUDE.md               # Project instructions
```

Runtime-only directories not tracked in git: `.venv/` (`/opt/assistant-core/.venv`), `data/` (SQLite `data/assistant.db`, production, never open for analysis), `logs/` if present.

## Directory Purposes

**`src/core/`:**
- Purpose: Framework-free core. Abstract entities and ports.
- Contains: `domain/entities.py`, `domain/events.py`, `ports/connectors.py`, `ports/clients.py`, `events/bus.py`, `exceptions.py`.
- Key files: `src/core/ports/connectors.py` (BaseConnector and role ports), `src/core/domain/entities.py` (ScheduleEvent, WorkRecord, AcademicSubmission, Task, EmailMessage, Workspace, GitCommit, Persona).
- Rule: imports only stdlib and `src.core.*` (import-linter `core-is-pure`).

**`src/brain/`:**
- Purpose: LLM-facing logic.
- Contains: `intent_router.py`, `secretary_dialog.py`, `tools_schema.py`, `methodist.py`, `summarizer.py`, `reply_generator.py`, `git_evaluator.py`, `debrief_parser.py`, `voice.py`, `key_rotator.py`.
- Key files: `src/brain/secretary_dialog.py` (859 lines), `src/brain/methodist.py` (686 lines), `src/brain/summarizer.py` (493 lines), `src/brain/intent_router.py` (439 lines).
- Rule: no direct imports of adapter packages (see `.importlinter`).

**`src/notifier/`:**
- Purpose: Telegram interface and owner interaction.
- Contains: `bot_handler.py` (EmailBotHandler, 3218 lines), `commands.py`, `telegram.py`, `live_ticker.py`.
- Key files: `src/notifier/bot_handler.py` (router, HITL callbacks), `src/notifier/live_ticker.py` (HUD ticker, 5-minute refresh).

**`src/connectors/`:**
- Purpose: External-system adapters, one package per system.
- Subpackages:
  - `aadhk/`: `parser.py` (AadhkIngestionService), `provider.py` (AadhkTimesheetProvider)
  - `gdrive/`: `client.py` (GoogleDriveClient, AADHk backup sync)
  - `git/`: `provider.py` (SshGitProvider, implements BaseGitSourceProvider)
  - `guap_lms/`: `client.py` (LmsPortalClient), `provider.py` (LmsPortalProvider)
  - `notion/`: `client.py`, `schema.py` (Notion adapter; wiring from `src/main.py` or `src/composition.py` not confirmed in this analysis)
- Each package has an `__init__.py`.

**`src/calendar/`:**
- Purpose: Google Calendar.
- Contains: `client.py` (GoogleCalendarClient, `sync_schedule`), `provider.py` (GoogleCalendarSink).

**`src/parser/`:**
- Purpose: Schedule site fetch and parse.
- Contains: `schedule_parser.py` (ScheduleParser), `provider.py` (ScheduleParserSource).

**`src/collector/`:**
- Purpose: Message ingestion.
- Contains: `tg_collector.py` (TelegramCollector, userbot), `email_collector.py` (EmailCollector, IMAP-style sync).

**`src/sender/`:**
- Purpose: Outgoing email. Contains `email_sender.py` (EmailSender).
- Note: `src/connectors` and `src/sender` are namespace directories without `__init__.py` for `src/sender`. `.importlinter` lists them explicitly because grimp otherwise skips them.

**`src/detector/`:**
- Purpose: Deterministic change and filter logic before any LLM call.
- Contains: `diff.py` (ScheduleChangeDetector), `temporal.py`, `tg_filter.py`.

**`src/models/`:**
- Purpose: Payload models.
- Contains: `schedule.py` (SchedulePayload, ScheduleDay, Lesson, LessonType), `message.py`, `second_brain.py`.

**`src/persona/`:**
- Purpose: Declarative owner profile and bindings.
- Contains: `loader.py` (yaml.safe_load plus validation), `models.py` (Pydantic), `bindings.py`, `current.py`, `seed.py` (writes persona into DB), `prompts.py`, and `prompts/git_progress.jinja2`.

**`src/security/`:**
- Purpose: NDA air-gap.
- Contains: `airgap.py`.

**`src/storage/`:**
- Purpose: SQLite facade.
- Contains: `db.py` (Database). Uses `assistant_shared.db.connection` and `assistant_shared.db.migrator`.

**`config/`:**
- Purpose: Declarative configuration.
- Contains: `persona.yaml`; `prompts/` with `debrief_default`, `evening_digest_default`, `git_progress_default`, `intent_router_default`, `methodist_default`, `methodist_scope_check_default`, `morning_brief_default`, `reply_generator_default`, `secretary_default` (`.jinja2`).

**`tests/`:**
- Purpose: pytest suites. Root conftest: `tests/conftest.py`.
- Contains: `test_*.py` modules, plus helpers `hardcode_baseline.py`, `persona_tokens.py`, `synthetic_persona.py`.
- Architecture guards: `test_architecture_contract.py`, `test_core_architecture.py`, `test_ports_conformance.py`, `test_composition_di.py`, `test_airgap_trap.py`, `test_git_airgap_trap.py`, `test_nda_script_parity.py`, `test_hardcode_scanner.py`.
- HITL guards: `test_hitl_safety_guardrails.py`, `test_bot_hitl_parity.py`, `test_hitl_telegram_cards.py`, `test_notion_git_hitl.py`.
- Fixtures: `tests/fixtures/prompts_snapshot/` (expected rendered prompts with `MANIFEST.json`), `tests/fixtures/synthetic_prompts/`.

**`scripts/`:**
- Purpose: Operator scripts, not on the daemon startup path.
- Contains: `auth_google.py`, `auth_telethon.py` (one-time auth), `reconcile_schedule.py`, `generate_brief.py`, `security_shield.py` (security scan), `install_hooks.sh` (git hook installer), `provision_notion.py`, `provision_dev_roadmap.py`, `publish_lab1_tasks.py`, `create_lab_tasks.py`, `download_fizikaguap_materials.py`, `notion_dev.py`, `populate_notion_retrospective.py`, `run_stt_stress_test.py`, `test_secretary_simulation.py`.

**`docs/`:**
- Purpose: Human documentation.
- Contains: `README_ARCH_GUIDE.md` (architecture decisions, Russian), `MULTI_PROJECT_ORCHESTRATION_AND_SECURITY.md`, `ROADMAP.md`, `SPEC_PHASE_1.md`, `DISK_USAGE_HISTORY.md`, `SECRETARY_CHAT_TEST_ISSUES.md`, `baseline/reconcile_report.json`.

**`.githooks/`:** `pre-commit` (enabled through `scripts/install_hooks.sh`).

## Key File Locations

**Entry Points:**
- `src/main.py`: daemon `main()` and cycle functions.
- `src/composition.py`: adapter factories.

**Configuration:**
- `config/persona.yaml`: persona, workspaces, bindings.
- `src/config.py`: environment variables (reads `.env` at runtime; do not read `.env` for analysis).
- `.env.example`: variable names template.
- `.importlinter`: architecture contracts.
- `pytest.ini`: test config.

**Core Logic:**
- `src/core/ports/connectors.py`: connector Protocols.
- `src/core/domain/entities.py`: domain entities.
- `src/notifier/bot_handler.py`: interaction and HITL.
- `src/brain/secretary_dialog.py`: dialog engine.
- `src/storage/db.py`: persistence.
- `src/security/airgap.py`: NDA rules.

**Testing:**
- `tests/`: all suites. Run with `/opt/assistant-core/.venv/bin/pytest /opt/assistant-core/tests`.

## Naming Conventions

**Files:**
- Snake_case Python modules: `schedule_parser.py`, `email_collector.py`, `reply_generator.py`.
- Provider or client split per adapter: `client.py` (low-level SDK wrapper), `provider.py` (implements a core port), `parser.py` (ingestion logic).
- Tests: `tests/test_<area>.py`, with architecture guards named `test_<topic>_architecture.py` or `*_trap.py`.
- Prompts: `config/prompts/<name>_default.jinja2`.
- Migrations (shared lib): `NNNN_<description>.sql`, zero-padded and sequential.

**Directories:**
- Packages are lowercase single words, one per adapter or use-case domain (`guap_lms`, `aadhk`, `gdrive`).
- Note: the LMS package is named `guap_lms` in the tree. Code reaches it via `importlib.import_module("src.connectors." + "g" + "uap_lms.client")` in `src/composition.py`, which is a deliberate indirection tied to the hardcode scanner in `tests/test_hardcode_scanner.py`.

**Classes:**
- Ports: `Base*` prefix (`BaseConnector`, `BaseLMSProvider`).
- Adapters: `<System><Role>` (`AadhkTimesheetProvider`, `SshGitProvider`, `GoogleCalendarSink`).
- Engines and services: `*Engine`, `*Service`, `*Handler`, `*Client`.

## Where to Add New Code

**New external connector (plugin):**
- Port: add a role Protocol in `src/core/ports/connectors.py` if no existing role fits, with `required_scopes` and a `health_check`.
- Implementation: `src/connectors/<system>/provider.py` (plus `client.py` for the SDK wrapper, `__init__.py`). Keep `__init__.py` exports consistent with the package.
- Factory: add `default_<role>()` to `src/composition.py` with a `MissingScopeError` scope check, lazy import inside the function.
- Persona: add a binding entry in `config/persona.yaml` and the Pydantic model in `src/persona/models.py`.
- Tests: `tests/test_<system>.py`, plus conformance in `tests/test_ports_conformance.py`.

**New scheduled cycle:**
- Cycle function: `src/main.py` (`run_<name>_cycle`), following the try/except and logger pattern.
- Registration: `scheduler.add_job(..., id="<name>_job")` in `main()`.
- Manual trigger: add a `--<flag>` option in `main()`.

**New LLM use-case:**
- Implementation: `src/brain/<name>.py`. Use prompts from `config/prompts/<name>_default.jinja2` via `src/persona/prompts.py`.
- Must not import adapter packages. Inject adapters through the composition root.
- Air-gap: call `src/security/airgap.py` helpers before sending NDA content to an LLM.

**New Telegram command or HITL flow:**
- Handler: `src/notifier/bot_handler.py` (router) or `src/notifier/commands.py` (command definitions).
- Destructive actions: require HITL via `assistant_shared.hitl`; add tests in `tests/test_hitl_safety_guardrails.py` and `tests/test_bot_hitl_parity.py`.

**New domain entity or event:**
- Entity: `src/core/domain/entities.py` (dataclass).
- Event: `src/core/domain/events.py`. Publishing is not wired yet (see ARCHITECTURE.md).

**New persistent table or column:**
- Migration: in `/opt/assistant-shared/assistant_shared/db/migrations/` as the next `NNNN_*.sql`. assistant-core owns the schema; chat-app consumes it via small `/gsd-quick` changes.
- Access: methods on `src/storage/db.py` (`Database`), async via aiosqlite.

**Utilities:**
- Shared helpers in the package closest to the caller. Cross-project security and DB helpers belong in `/opt/assistant-shared`, not in `src/`.

**Tests:**
- Unit tests: `tests/test_<module>.py`.
- Architecture contract: `tests/test_architecture_contract.py` and `tests/test_core_architecture.py` must pass after any import change. Run `lint-imports` if available.

## Special Directories

**`.venv/`:**
- Purpose: Python 3.12 virtualenv for the daemon and tests.
- Generated: Yes. Committed: No.

**`data/`:**
- Purpose: SQLite database `data/assistant.db`. Production data. Never open or modify from analysis or tests that touch production.
- Generated: Yes at runtime. Committed: No.

**`.planning/`:**
- Purpose: GSD project state for assistant-core (owner decision 2026-10-09). `codebase/` holds these maps.
- Generated: Yes (by GSD). Committed: Yes.

**`/opt/assistant-shared/`** (outside the repo):
- Purpose: `assistant_shared` package (`db/`, `hitl/`, `security/`) and migrations, shared with chat-app.
- Generated: No. Committed: Yes (separate git repo).

**`.githooks/`:**
- Purpose: Git hooks. Installed by `scripts/install_hooks.sh`.
- Committed: Yes.

---

*Structure analysis: 2026-10-09*
