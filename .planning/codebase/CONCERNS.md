---
last_mapped_commit: 5997ad6c8c219390ead42ea5132f2660f488f15d
last_mapped_at: 2026-10-09
---
# Codebase Concerns

**Analysis Date:** 2026-10-09

## Verification of Known v2.0 Audit Gaps

| Item | Status | Evidence |
|------|--------|----------|
| GitEvaluator (Git → Notion) not instantiated at runtime | Resolved (Phase 4) | Resolved in Phase 4: `GitProgressEvaluator` is instantiated at runtime via `default_git_evaluator(db)` in `src/composition.py` and wired into `src/main.py` (before `EmailBotHandler` and as a scheduled cron job `git_progress_job`), and into Telegram bot handler for `/git` (see summaries `04-01-SUMMARY.md` and `04-08-SUMMARY.md`). |
| `send_web_hitl_card` defined but never called | Confirmed | Defined at `src/notifier/bot_handler.py:1951`; only reference outside definition is the test `tests/test_bot_hitl_parity.py:30,51`. No call site in `src/`. |
| Shared migration 0003 missing for `bot_command_settings` / `bot_custom_aliases` / `dialog_feedback_log` | Resolved (Phase 3) | Resolved in Phase 3: migration 0003 added in assistant-shared (commit `5c85613`), inline DDL removed and unified non-blocking path in assistant-core (commit `5413266`), chat-app synced (commit `011f9c2`). |
| NDA email subject/sender/date possibly unmasked in `search_emails` | Confirmed (leak) | `src/brain/secretary_dialog.py:186-191`: `date_str`, `sender`, and `subj` are read from the raw row before/independently of the NDA branch; `mask_nda_email_data` (`src/security/airgap.py:128-150`) only replaces `body`, `body_plain`, `snippet`, `body_html`, `attachments`. The line-based output at `secretary_dialog.py:196` therefore prints the real sender and subject for NDA mail. The tool path at `secretary_dialog.py:764-780` also passes `sender` through unmasked after masking. `search_emails` itself (`src/storage/db.py:1007`) does not filter NDA rows. |
| Phase-4 review findings WR-03/04/07/11 skipped | Partly confirmed | WR-04 is referenced only as a comment at `src/persona/models.py:157` and `tests/test_persona_loader.py:380`. No WR-03/07/11 markers exist in code. Treat as unresolved; no fix trace found. |
| WR-06 in-memory migration branch still synchronous | Confirmed | `src/storage/db.py:58-62`: the `:memory:` branch calls `run_migrations(raw_conn)` directly on the event loop. Only the file branch uses `asyncio.to_thread(run_migrations, self.db_path)` (`src/storage/db.py:96`). |

## Tech Debt

**Oversized modules:**
- Issue: Several modules concentrate many responsibilities.
- Files: `src/notifier/bot_handler.py` (3218 lines), `src/storage/db.py` (3019 lines), `src/main.py` (862), `src/brain/secretary_dialog.py` (859), `src/collector/email_collector.py` (829).
- Impact: Hard to review; the NDA leak above and the unwired HITL card went unnoticed in such files.
- Fix approach: Split `db.py` by domain repository (email, tasks, bot settings, feedback); split `bot_handler.py` into command handlers and HITL cards.

**Schema ownership split and inline DDL:**
- Issue: `src/storage/db.py` runs `CREATE TABLE IF NOT EXISTS` for tables that are not in the shared migrations (see table above), duplicated in two branches (`:memory:` and file).
- Files: `src/storage/db.py:56-125`
- Impact: Schema drift between in-memory tests and production; chat-app cannot rely on the shared schema.
- Fix approach: Add `0003_*.sql` to `/opt/assistant-shared` with the three tables; remove inline DDL; run the same migrator for both branches.

**Duplicated init DDL:**
- Issue: The same table definitions appear twice in `init_db`.
- Files: `src/storage/db.py:64-83` and `src/storage/db.py:100-119`
- Fix approach: One DDL constant executed in both branches.

**Broad exception handling:**
- Issue: 77 `except:` or `except Exception:` blocks in `src/`; at least some are bare `except:`.
- Files: e.g. `src/brain/secretary_dialog.py` (`_search_email_context`, around line 180) and many in `src/notifier/bot_handler.py`.
- Impact: Failures in security filters (NDA masking) degrade silently.
- Fix approach: Narrow exceptions; log at warning level; never fall through to unmasked output on error in NDA paths.

**Synchronous sqlite3 in connector:**
- Issue: `AadhkIngestionService` uses blocking `sqlite3.connect` inside an async service.
- Files: `src/connectors/aadhk/parser.py:4`, `src/connectors/aadhk/parser.py:123-124`
- Impact: Blocks the daemon event loop; the same problem WR-06 addressed for migrations.
- Fix approach: Use `aiosqlite` (project standard per `CLAUDE.md` section 4) or run in `asyncio.to_thread`.

**Stray untracked directory:**
- Issue: A directory literally named `sqlite+aiosqlite:` (with `data/` and ~95 `tmp/` subfolders) exists in the repo root; it is not tracked by git.
- Files: `/opt/assistant-core/sqlite+aiosqlite:/`
- Impact: Artifact of a DB URL passed as a path; clutter and possible data leakage if committed.
- Fix approach: Remove after confirming it is not used; normalise DB URL parsing in `src/storage/db.py`.

## Domain Hardcoding vs. Generalization Goal

These conflict with the directive in `CLAUDE.md` section 2 (universal platform, config-driven personas).

- `src/storage/db.py:1398-1400`: seed data hardcodes GUAP course names, rooms (`м431к`, `м562`), and an AADHk "Сектор приборов" project, inserted by `_seed_initial_data_if_empty`. Seed data runs for every fresh database.
- `src/connectors/guap_lms/` and `src/connectors/aadhk/` are concrete connectors, but they are imported directly rather than loaded via a plugin registry (see `tests/test_connector_params.py:178-187`, which hardcodes `timesheet` and `lms` provider names).
- `src/connectors/aadhk/parser.py` default project name `"Тидекс"` is asserted in `tests/test_connector_params.py:134`, indicating a Tydex default baked into code.
- `src/persona/models.py` and `tests/test_persona_loader.py:405` use `provider: aadhk_timesheet`, so the persona schema is coupled to a specific connector.
- Category literals `guap_dept` and `tydex` appear in tests (`tests/test_secretary_dialog.py:131`, `tests/test_memory_review.py:18`) and are likely used by production classification logic.
- `src/storage/db.py` also contains `ГУАП`-tagged test-like data in tests (`tests/test_bot_hitl_parity.py:80,139`).
- Fix approach: Move the GUAP/Tydex seed and default project into `config/persona.yaml`; express LMS/timesheet connectors as plugins registered by name; remove hardcoded default `"Тидекс"`.

## Security Considerations

**NDA data leakage through email search output:**
- Risk: Sender address, sender name, and subject of NDA emails reach the LLM prompt and the Telegram reply unmasked.
- Files: `src/brain/secretary_dialog.py:186-197`, `src/brain/secretary_dialog.py:764-780`, `src/security/airgap.py:128-150`, `src/storage/db.py:1007`
- Current mitigation: Body and snippet are replaced with `NDA_MASK_MARKER`.
- Recommendations: Extend `mask_nda_email_data` to replace `subject`, `sender_name`, `sender_email`, and `date_sent` (or a documented subset) for NDA workspaces; compute masked copy before any field read; add a regression test that asserts no subject/sender appears in NDA search output.

**Secrets on disk in the project root:**
- Risk: `.env`, `credentials.json`, and `token.json` live in the repo root. They are git-ignored (`.gitignore`) but present with mode 600/644 mix. Contents were not read in this analysis.
- Files: `/opt/assistant-core/.env`, `/opt/assistant-core/credentials.json`, `/opt/assistant-core/token.json`
- Current mitigation: Git ignore rules; `.env.example` provided.
- Recommendations: Confirm `.env` is mode 600; move OAuth tokens to a secrets directory outside the repo.

**Subprocess execution for git operations:**
- Risk: Git commands run through `asyncio.create_subprocess_exec` with values derived from workspace config.
- Files: `src/connectors/git/provider.py:72`, `src/connectors/git/provider.py:121`
- Current mitigation: `exec` (not shell) is used, so no shell injection; argument validation not verified in this pass.
- Recommendations: Validate `path` and `ssh_alias` against an allowlist from `workspaces` config before building argv.

**Air-gap enforcement is not evidenced at the connector layer:** [закрыто фазой 4: см. 04-01-SUMMARY.md, 04-08-SUMMARY.md, 04-10-SUMMARY.md]
- Status: Resolved (Phase 4). Production dispatcher routes through strict fail-closed `git_chain_workspaces` guard, verified by runtime traps in `tests/test_git_chain_airgap.py` and reachability tests in `tests/test_phase4_reachability.py`.
- Risk: NDA workspace git actions (`tests/test_git_airgap_trap.py`) are tested, but the production dispatcher that calls `GitProvider` was not confirmed to route through the trap; `GitEvaluator` (the Git → Notion path) is not wired at all.
- Files: `src/connectors/git/provider.py`, `tests/test_git_airgap_trap.py`
- Recommendations: Add an integration test that invokes the production dispatcher with an NDA workspace.

## Performance Bottlenecks

**Synchronous migrations on the in-memory branch:**
- Problem: Blocks the loop during `init_db` in test/in-memory mode.
- Files: `src/storage/db.py:58-62`
- Cause: Direct call to `run_migrations` on event loop thread (WR-06 partial).
- Improvement path: Wrap in `asyncio.to_thread` or run migrations over a dedicated sync connection before the async loop starts.

**Synchronous SQLite in AADHk ingestion:**
- Problem: Blocking reads during timesheet ingestion.
- Files: `src/connectors/aadhk/parser.py:123-124`
- Improvement path: Switch to `aiosqlite` or `to_thread`.

**Large single-file modules:** see Tech Debt; `bot_handler.py` and `db.py` exceed 3000 lines each and mix many concerns, which hinders profiling.

## Fragile Areas

**`search_emails` ranking and stemming:**
- Files: `src/storage/db.py:1007-1110`
- Why fragile: Hand-written Russian stemming (`stem_token`), stopword list and fallback "latest emails from sender" path. Results change silently with query wording.
- Safe modification: Add tests for each branch (sender-only, query-only, both, no match fallback) before changing ranking.
- Test coverage: `tests/test_email_collector.py`, `tests/test_secretary_tools.py` cover parts; NDA masking on subject/sender not covered.

**Bot dialog flow:**
- Files: `src/notifier/bot_handler.py`, `src/brain/secretary_dialog.py`
- Why fragile: HITL confirmation cards are split across modules; `send_web_hitl_card` exists without caller, so web-initiated actions have no Telegram confirmation path in production.
- Safe modification: Wire the call from the web action endpoint, then extend `tests/test_bot_hitl_parity.py`.

**Project planning state:**
- Files: `/opt/assistant-core/.planning/` does not exist; `/opt/chat-app/.planning/` is frozen history.
- Why fragile: `CLAUDE.md` section 5 requires a dedicated assistant-core GSD project; the starting backlog has not been materialised in this repo, so these concerns have no tracked phase.

## Scaling Limits

**SQLite single file:**
- Current capacity: Single-user daemon; `assistant.db` about 0.5 MB (size only; not opened).
- Limit: Concurrent writers from daemon and chat-app consumer on the same file.
- Scaling path: Enforce WAL and busy_timeout in one shared place (`/opt/assistant-shared`).

## Dependencies at Risk

Not assessed in detail for this pass. Shared library `/opt/assistant-shared` is a cross-repo dependency with an incomplete migration set (see verification table).

## Missing Critical Features

**Git → Notion evaluation:** [закрыто фазой 4: см. 04-01-SUMMARY.md, 04-08-SUMMARY.md]
- Status: Resolved (Phase 4). Fully wired into `src/main.py` and `src/notifier/bot_handler.py`.
- Problem: `GitEvaluator` is not instantiated; the feature described in v2.0 is not reachable from runtime.
- Blocks: Automated Git status reporting to Notion; phase verification that requires runtime reachability.

**Web HITL confirmation:**
- Problem: No runtime caller for `send_web_hitl_card`.
- Blocks: Telegram confirmation of Web-originated destructive actions (HITL requirement in `CLAUDE.md` section 2.4).

## Test Coverage Gaps

**NDA masking of metadata:**
- What's not tested: subject/sender/date masking in `search_emails` outputs.
- Files: `src/brain/secretary_dialog.py:186-197`, `tests/test_secretary_tools.py`
- Risk: The leak above passes existing tests.
- Priority: High

**Runtime reachability:** [GitEvaluator закрыто фазой 4: см. 04-01-SUMMARY.md, 04-08-SUMMARY.md; send_web_hitl_card ожидает Phase 5]
- Status: GitEvaluator resolved in Phase 4 via `tests/test_phase4_reachability.py` and `tests/test_phase4_chain_e2e.py`.
- What's not tested: `GitEvaluator` and `send_web_hitl_card` are only exercised by unit tests or not at all.
- Files: `tests/test_bot_hitl_parity.py`, `tests/test_git_airgap_trap.py`
- Risk: Features appear green while unreachable from the daemon.
- Priority: High

**Migration parity:**
- What's not tested: Equality of schema between `:memory:` and file branches, and between repo DDL and shared migrations.
- Files: `src/storage/db.py:56-125`
- Priority: Medium

---

*Concerns audit: 2026-10-09*
