---
last_mapped_commit: 5997ad6c8c219390ead42ea5132f2660f488f15d
last_mapped_at: 2026-10-09
---
<!-- refreshed: 2026-10-09 -->

# Architecture

**Analysis Date:** 2026-10-09

## System Overview

```text
┌──────────────────────────────────────────────────────────────────────┐
│  Entry: src/main.py  main()  (systemd: assistant-worker.service)     │
│  DB init · persona seed · Bot/Dispatcher · AsyncIOScheduler          │
└──────────┬───────────────────────────┬──────────────────────────────┘
           │ APScheduler jobs          │ aiogram polling
           ▼                           ▼
┌──────────────────────────┐  ┌─────────────────────────────────────┐
│ Cycles (src/main.py)     │  │ Interface: src/notifier/            │
│ sentinel, collectors,    │  │ bot_handler.py (EmailBotHandler),   │
│ briefs, LMS, AADHk sync  │  │ commands.py, telegram.py,           │
│                          │  │ live_ticker.py                      │
└────────┬─────────────────┘  └──────────────┬──────────────────────┘
         │                                   │
         ▼                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Use-cases / "Brain": src/brain/  (intent_router, secretary_dialog,  │
│ methodist, summarizer, reply_generator, git_evaluator, voice, ...)  │
│ Must not import adapters (import-linter contract)                   │
└────────┬───────────────────────────────┬────────────────────────────┘
         │ ports (src/core/ports/)       │ security gate
         ▼                               ▼
┌──────────────────────────────┐  ┌──────────────────────────────────┐
│ Adapters: src/connectors/*,  │  │ src/security/airgap.py           │
│ src/calendar, src/parser,    │  │ NDA masking / git sanitizing     │
│ src/collector, src/sender    │  └──────────────────────────────────┘
│ wired in src/composition.py  │
└────────┬─────────────────────┘
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Storage: src/storage/db.py (Database, aiosqlite)                    │
│ on top of /opt/assistant-shared (assistant_shared.db, migrations)   │
└─────────────────────────────────────────────────────────────────────┘
```

## Pattern Overview

**Overall:** Layered "worker + brain + interface" daemon with a ports-and-adapters core (`src/core/`) enforced by import-linter contracts (`.importlinter`). Runtime is a single asyncio process: one aiogram dispatcher for Telegram plus one APScheduler `AsyncIOScheduler` for periodic cycles.

**Key Characteristics:**
- Single process, single event loop (`asyncio.run(main())` in `src/main.py`); blocking work is pushed to threads only where explicitly done (e.g. migrations, see `0da0dbe` in git history).
- Read autonomously, write with confirmation: collectors and sentinels fetch and store data in the background; any outward action (email send, grade/task change, calendar mutation triggered from chat) goes through HITL cards in the Telegram bot (`assistant_shared.hitl`).
- Two-stage filtering (documented in `docs/README_ARCH_GUIDE.md`): deterministic Python filters (hashes, regexes, diffs such as `src/detector/diff.py`, `src/detector/tg_filter.py`) run first; only selected items reach the LLM brain.
- Configuration-driven persona: `config/persona.yaml` is the single source (loaded by `src/persona/loader.py`, validated by Pydantic with `extra=forbid`) and is seeded into SQLite by `src/persona/seed.py`.

## Layers

**Core (pure domain and ports):**
- Purpose: Abstract entities and structural interfaces, no I/O.
- Location: `src/core/`
- Contains: `src/core/domain/entities.py` (ScheduleEvent, WorkRecord, AcademicSubmission, Task, EmailMessage, Workspace, GitCommit, GitProgressReport, Persona, ConnectorRole, WorkspaceClearance), `src/core/domain/events.py` (DomainEvent subclasses), `src/core/ports/connectors.py` and `src/core/ports/clients.py` (Protocols), `src/core/events/bus.py` (EventBus), `src/core/exceptions.py`.
- Depends on: stdlib and `src.core.*` only (contract `core-is-pure`).
- Used by: everything else.

**Ports (Protocols):**
- Purpose: Contracts that adapters satisfy.
- Location: `src/core/ports/connectors.py`
- Contains: `BaseConnector` (connector_id, required_scopes, health_check) and role-specific ports: `BaseTimesheetProvider`, `BaseScheduleProvider`, `BaseCalendarSink`, `BaseLMSProvider` (declares `REQUIRES_CONFIRMATION = {"submit_grade", "delete_task"}`), `BaseGitSourceProvider`. All are `@runtime_checkable`.
- Note: only `SshGitProvider` (`src/connectors/git/provider.py`) explicitly subclasses a port. Other adapters (`AadhkTimesheetProvider`, `LmsPortalProvider`, `ScheduleParserSource`, `GoogleCalendarSink`) are plain classes conforming structurally; conformance is checked in `tests/test_ports_conformance.py`.

**Use-cases ("Brain"):**
- Purpose: LLM-assisted logic, dialogs, classification, summaries.
- Location: `src/brain/`
- Contains: `intent_router.py` (fast intent routing), `secretary_dialog.py` (SecretaryDialogEngine, tool-calling dialog), `tools_schema.py`, `methodist.py`, `summarizer.py` (GeminiSummarizer), `reply_generator.py`, `git_evaluator.py`, `debrief_parser.py`, `voice.py`, `key_rotator.py`.
- Depends on: `src/core`, `src/persona`, `src/security`, `assistant_shared.hitl`. Must not import `src.connectors`, `src.calendar`, `src.parser`, `src.sender`, `src.collector`, `src.notifier` directly (contract `brain-no-adapters`; indirect imports through `src.composition` are allowed by design, D-12).

**Adapters (infrastructure):**
- Purpose: Talk to external systems.
- Location: `src/connectors/{aadhk,gdrive,git,guap_lms,notion}/`, `src/calendar/`, `src/parser/`, `src/collector/`, `src/sender/`
- Depends on: `src/core`, `src/storage`, external SDKs.
- Used by: `src/composition.py` factories and `src/main.py`.

**Interface (Telegram):**
- Purpose: Owner-facing UI, commands, HITL cards, live HUD ticker.
- Location: `src/notifier/`
- Contains: `bot_handler.py` (`EmailBotHandler`, about 3200 lines, the main router), `commands.py`, `telegram.py` (TelegramNotifier), `live_ticker.py` (LiveTickerService).
- Restriction: `bot_handler` and `live_ticker` may not import adapters directly (contracts `bot-handler-no-adapters`, `live-ticker-no-adapters`).

**Storage:**
- Purpose: SQLite persistence for events, snapshots, emails, HITL confirmations, sources, personas.
- Location: `src/storage/db.py` (`Database`, ~3000 lines), models in `src/models/` (`schedule.py`, `message.py`, `second_brain.py`).
- Connection and migrations come from the shared library: `assistant_shared.db.connection.get_async_connection`, `sqlite_lower`, `assistant_shared.db.migrator.run_migrations`. Schema migrations live in `/opt/assistant-shared/assistant_shared/db/migrations/` (`0001_initial_schema.sql`, `0002_pending_confirmations.sql`). assistant-core is the schema owner side.

**Security:**
- Purpose: Air-gap for NDA/corporate workspaces.
- Location: `src/security/airgap.py`
- Contains: `is_nda_email`, `mask_nda_email_data` (marker `[NDA: тело и вложения скрыты Air-Gap]`), `is_nda_workspace`, `sanitize_git_commits_for_llm`, `sanitize_notion_payload_for_airgap`.
- Used by: `src/brain/secretary_dialog.py`, `src/brain/reply_generator.py`, `src/brain/git_evaluator.py`, `src/brain/summarizer.py`. Test guards: `tests/test_airgap_trap.py`, `tests/test_git_airgap_trap.py`, `tests/test_nda_script_parity.py`.

## Composition Root and Wiring

**Composition root:** `src/composition.py` is documented as the only place (besides `src/main.py`) that knows concrete classes. Its factories import adapters lazily inside functions:
- `default_timesheet_service(db)` → `AadhkTimesheetProvider(AadhkIngestionService(db))`, gated by persona binding `timesheet`
- `default_lms_client()` → `LmsPortalClient`, gated by binding `lms`
- `default_git_source_provider()` → `SshGitProvider`, gated by binding `git_source`
- `default_schedule_parser(...)`, `default_email_collector(db)`, `default_email_sender()`, `default_drive_client()`
- `schedule_site_url()` reads `config.SCHEDULE_URL` first, then the `schedule_source` persona binding.

Each factory checks `required_scopes` against the persona binding scopes and raises `MissingScopeError` on mismatch (zero-trust scope validation, D-09 to D-11).

**In practice `src/main.py` also instantiates concrete classes directly** (`Bot`, `Dispatcher`, `TelegramNotifier`, `ReplyGenerator`, `EmailSender`, `GeminiSummarizer` (twice), `GoogleCalendarClient`, `EmailBotHandler`, `ScheduleParser`, `TelegramCollector`, `EmailCollector`, `SecretaryDialogEngine`). So the composition root is partial: factories exist and are used for LMS, Git, schedule URL, and the parser, but many dependencies are built inline in `main()`.

## Runtime Entry Point and Startup Sequence

**Entry:** `src/main.py`, run as `python3 -m src.main` (`/etc/systemd/system/assistant-worker.service`, `WorkingDirectory=/opt/assistant-core`, venv `/opt/assistant-core/.venv`).

`main()` sequence:
1. Parse CLI flags: `--once`, `--brief`, `--evening`, `--prime`, `--review`, `--send-email-cards`, `--send-email-id`.
2. `Database(config.SQLITE_DB_PATH).init_db()` (runs shared migrations).
3. `current_persona()` then `seed_persona(db, persona)` writes workspaces and bindings into the DB; missing env vars are logged.
4. Build `Bot`, `Dispatcher`, `TelegramNotifier`, `ReplyGenerator`, `EmailSender`, `GeminiSummarizer`, `default_lms_client()`, `GoogleCalendarClient`, then `EmailBotHandler`; `dp.include_router(bot_handler.router)`; `setup_bot_commands()`.
5. Build `ScheduleParser`, `TelegramCollector`, `EmailCollector`; upsert monitored sources `daily_morning_brief` and `daily_evening_digest`.
6. Handle one-shot CLI flags (send brief, digest, prime, review, email cards) and exit.
7. Register APScheduler jobs and run `dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())`.

**Scheduled jobs (`AsyncIOScheduler` in `src/main.py`):**

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

1. `ScheduleParser.fetch_schedule_raw` fetches the schedule site (`src/parser/schedule_parser.py`), JSON or HTML (`parse_json_payload` / `parse_html_payload`).
2. Previous snapshot loaded via `Database.get_latest_snapshot` and validated as `SchedulePayload` (`src/models/schedule.py`).
3. `ScheduleChangeDetector.compare` (`src/detector/diff.py`) produces a diff; no change → log and stop.
4. On change: `Database.save_snapshot`, then `GoogleCalendarClient.sync_schedule` (`src/calendar/client.py`, port `BaseCalendarSink`).
5. `TelegramNotifier.send_schedule_diff_alert` notifies the owner.
6. `AadhkIngestionService.reconcile_all_conflicts()` cross-checks timesheet records (`src/connectors/aadhk/parser.py`).
7. If the fetch or parse fails, the cycle is skipped to preserve the current calendar.

### Email Path (collector → HITL card)

1. `run_email_collector_cycle` calls `EmailCollector.sync_all_accounts(days=3)` (`src/collector/email_collector.py`), inserting into `db.list_recent_emails`.
2. Actionable academic/department mail (filtered by category, `requires_action`, not answered, not expired, no card yet) becomes a card via `TelegramNotifier.send_actionable_email_card`; the message id is stored with `set_email_card_msg_id`.
3. Owner acts through inline buttons handled in `src/notifier/bot_handler.py`; replies are drafted by `ReplyGenerator` and sent by `EmailSender` only after confirmation.

### Chat / Intent Path

1. aiogram update → `EmailBotHandler.router` in `src/notifier/bot_handler.py`.
2. `src/brain/intent_router.py` classifies the message; commands are parsed in `src/notifier/commands.py`.
3. Multi-turn tasks go to `SecretaryDialogEngine` (`src/brain/secretary_dialog.py`) using tool schemas from `src/brain/tools_schema.py`; NDA data is masked first by `src/security/airgap.py`.
4. Destructive or external actions create a pending confirmation (`assistant_shared.hitl`, table from migration `0002_pending_confirmations.sql`) and a card; execution happens only after the owner's callback.

**State Management:**
- Durable state lives in SQLite (`data/assistant.db`; path from `config.SQLITE_DB_PATH`). Do not open it directly in analysis.
- In-process state: APScheduler jobs, aiogram FSM/router state, `EmailBotHandler` message-id registry (`register_message`), `LiveTickerService` state.

## Key Abstractions

**Domain entities (dataclasses, `src/core/domain/entities.py`):**
- Purpose: Abstract records the core daemon operates on: `ScheduleEvent`, `WorkRecord`, `AcademicSubmission`, `Task`, `EmailMessage`, `Workspace`, `GitCommit`, `GitProgressReport`, `Persona`.
- Pattern: frozen-style dataclasses with `ConnectorRole` and `WorkspaceClearance` StrEnums.

**Connector ports:**
- Purpose: Swap GUAP LMS, AADHk timesheet, schedule site, Google Calendar, Git sources.
- Examples: `src/core/ports/connectors.py`; implementations in `src/connectors/*/provider.py`, `src/calendar/provider.py`, `src/parser/provider.py`.
- Pattern: `typing.Protocol` with `runtime_checkable`, `required_scopes` class variable, and persona-driven scope checks in `src/composition.py`.

**Persona bindings:**
- Purpose: Map each connector role to a workspace and its allowed scopes.
- Examples: `src/persona/models.py` (Pydantic, `extra=forbid`), `src/persona/bindings.py` (`binding`, `has_binding`, `schedule_source_settings`, `lms_settings`, `timesheet_settings`), `src/persona/current.py`, `src/persona/prompts.py`.
- Prompts are Jinja2 templates in `config/prompts/*.jinja2` (loaded with fallbacks from `src/persona/prompts/`).

**Event bus (defined, not wired):**
- `src/core/events/bus.py` (`EventBus`) and `src/core/domain/events.py` (`ScheduleChanged`, `TimesheetSynced`, `TaskCreated`, `SecurityViolationDetected`, `DialogMemoryCleared`, `DelegatedToSpecialist`) exist, but no `src` module instantiates or publishes them. They are exercised only by `tests/test_core_events.py`. Treat them as planned infrastructure, not a live communication path.

**Parser and detector:**
- `src/parser/schedule_parser.py` produces `SchedulePayload`; `src/detector/diff.py` produces `ScheduleChangeDetector` diffs; `src/detector/temporal.py` and `src/detector/tg_filter.py` provide time and Telegram filtering.

## Entry Points

**Daemon:**
- Location: `src/main.py` (`main()`, `if __name__ == "__main__"`)
- Triggers: systemd `assistant-worker.service`; manual `python3 -m src.main [flags]`
- Responsibilities: Full startup, polling, scheduler.

**Composition factories:**
- Location: `src/composition.py`
- Triggers: imported from `src/main.py`, `src/brain/*`, `src/notifier/bot_handler.py`.

**Maintenance scripts (outside the daemon):**
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

**What happens:** `src/main.py` creates `GeminiSummarizer` twice and builds most adapters inline, while `src/composition.py` offers factories for some of the same objects.
**Why it's wrong:** Two sources of truth for construction; tests that patch one path may miss the other.
**Do this instead:** Add new adapters as factories in `src/composition.py` with a scope check, and inject them into `EmailBotHandler` and cycle functions from `main()`.

### Defining ports without enforcing them at runtime

**What happens:** `BaseLMSProvider.REQUIRES_CONFIRMATION` and the `EventBus`/`DomainEvent` set are declared but not enforced or published.
**Why it's wrong:** Code reading the architecture docs may assume a guarantee that does not exist at runtime.
**Do this instead:** For any new destructive operation, route it through `assistant_shared.hitl` (see `src/notifier/bot_handler.py`) and add a test in `tests/test_hitl_safety_guardrails.py`.

### Large single-module handlers

**What happens:** `src/notifier/bot_handler.py` (about 3200 lines) and `src/storage/db.py` (about 3000 lines) hold most of the interaction and persistence logic.
**Why it's wrong:** Hard to review and easy to break; increases coupling to the Telegram layer.
**Do this instead:** Put new use-case logic in `src/brain/` or a new module, and keep handlers thin.

## Error Handling

**Strategy:** Cycle functions catch broad exceptions, log with `logger.exception`, and return so that the scheduler continues (see `run_telegram_collector_cycle`, `run_email_collector_cycle`, `run_aadhk_gdrive_sync_cycle`). Domain-level failures use exceptions in `src/core/exceptions.py` (for example `MissingScopeError`). Parse or fetch failures in the sentinel skip the cycle instead of overwriting the calendar.

**Patterns:**
- Early return on unsuccessful fetch (sentinel).
- Optional subsystems are guarded by `has_binding(...)` and return `None` (for example `default_lms_client`).
- Non-critical enrichment (AADHk reconcile after schedule change) is wrapped in try/except with debug logging.

## Cross-Cutting Concerns

**Logging:** Standard `logging` to stdout, configured in `src/main.py` (`DEBUG` level when `config.DEBUG`). Logger name `assistant-worker`.
**Validation:** Pydantic models for persona (`src/persona/models.py`), schedule payloads (`src/models/schedule.py`), and config loading (`src/config.py`).
**Authentication:** Telegram owner check via `config.TELEGRAM_USER_ID` (`allowed_user_id` in `EmailBotHandler`). Google OAuth via `config.GOOGLE_CREDENTIALS_FILE` / `GOOGLE_TOKEN_FILE`. Credentials are not documented here.
**Air-gap:** NDA workspaces are masked before any LLM call (`src/security/airgap.py`).

---

*Architecture analysis: 2026-10-09*
