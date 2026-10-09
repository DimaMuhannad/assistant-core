---
phase: "1"
slug: "sobstvennyy-geyt-kachestva-assistant-core"
status: secured
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-09"
---

# Phase 1 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (`<threat_model>` in 01-01…01-10-PLAN.md); verified by gsd-security-auditor 2026-10-09 (ASVS L1, block_on: high).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| tests → live DB | pytest of assistant-core must never touch `data/assistant.db` | owner's live data (high) |
| gate → live DB | gate hashes the live DB read-only (`mode=ro`), never writes | DB content hash only |
| gate → chat-app | gate reads chat-app copies of persona fixtures for drift, never writes | test fixtures |
| deploy.py → systemd / journal / Telegram API | read-only smoke; restart and backup only by explicit flag | service state, journal lines (redacted), bot token (never printed) |
| cross-AI adapter → target repo | agent patch applied only after protected-path check and green target gate | code patch |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-01-01 | Tampering | tests/live_db_guard.py | high | mitigate | audit hook on `open`/`sqlite3.connect`, installed in conftest before `src` import; URI/relative/sidecar normalisation; tests per bypass form | closed |
| T-01-02 | Information Disclosure | gdrive backup test | high | mitigate | `core_dir` parameter; test on synthetic bytes in tmp_path | closed |
| T-01-03 | Tampering | src/config.py `ASSISTANT_DB_PATH_OVERRIDE` | medium | mitigate | captured from process env BEFORE `load_dotenv(override=True)` (`src/config.py:9` vs `:12`) — a key in `.env` is inert by construction; unit has no `Environment=`/`EnvironmentFile`, worker env has no key (auditor, read-only) | closed |
| T-01-04 | Denial of Service | audit hook cost | low | mitigate | basename prefilter before realpath; re-entry flag | closed |
| T-01-05 | Information Disclosure | secret/NDA literals in shared tests | high | mitigate | literals assembled from parts; shield `--all` on shared rc 0 | closed |
| T-01-06 | Repudiation | Phase-2 behaviour tests | low | accept | ported as-is with SECF-01 markers | closed (accepted) |
| T-01-07 | Tampering | missing hook in fresh shared clone | high | mitigate | reproducible installer; gate row «pre-commit hook установлен» | closed |
| T-01-08 | Elevation of Privilege | interpreter choice via VIRTUAL_ENV | low | accept | fixed lookup order; owner-local env | closed (accepted) |
| T-01-09 | Information Disclosure | shield output in gate table | high | mitigate | normalised to (path, kind, count); no-leak test | closed |
| T-01-10 | Repudiation | false GREEN on skipped checks | high | mitigate | fail-closed pytest/shield parsing; red cases on mini-projects | closed |
| T-01-11 | Tampering | command injection via paths/output | medium | mitigate | arg lists, `shell=False`, timeouts, whitelist | closed |
| T-01-12 | Tampering | writes into chat-app | low | mitigate | chat-app only read (`rb`); test `never_modifies_chat_copy` | closed |
| T-01-13 | Repudiation | false GREEN when shared/hook/copy missing | high | mitigate | each absence → red row | closed |
| T-01-14 | Tampering | PYTEST_ADDOPTS narrowing | high | mitigate | empty PYTEST_ADDOPTS; red-case test | closed |
| T-01-15 | Tampering | ro read creating sidecar files | medium | mitigate | single-transaction `mode=ro` dump; data/ listing compared; residual deferred (see log) | closed |
| T-01-16 | Information Disclosure | bot token in errors/output | high | mitigate | only HTTP code / exception class printed | closed |
| T-01-17 | Information Disclosure | e-mail/groups/messages in report | high | mitigate | `redact` before truncation; report re-redacted; live files 0 e-mail/0 tokens | closed |
| T-01-18 | Denial of Service | getUpdates/Telethon stealing updates | high | mitigate | no getUpdates/Telethon/.session in scripts; test | closed |
| T-01-19 | Tampering | injection via journal content | medium | mitigate | journal only parsed; InvocationID `fullmatch` | closed |
| T-01-20 | Information Disclosure | smoke state file | low | mitigate | 0600, outside repo, no secrets | closed |
| T-01-21 | Elevation of Privilege | unrequested restart | high | mitigate | restart built in one place, reachable only under `--restart`; tests | closed |
| T-01-22 | Tampering | automatic rollback | high | mitigate | rollback printed only; runner silent after report | closed |
| T-01-23 | Information Disclosure | DB backup copy | high | mitigate | outside git, 0700/0600, `O_EXCL`, ro source; only by `--backup` | closed |
| T-01-24 | Tampering | `--report`/`--backup-dir` paths | low | mitigate | `.git` refused, parent must exist | closed |
| T-01-25 | Repudiation | stale gate command in docs | medium | mitigate | all sources updated; guard test | closed |
| T-01-26 | Tampering | quick brief weakening adapter | high | mitigate | explicit prohibitions in brief | closed |
| T-01-27 | Tampering | adapter change weakening guards | high | mitigate | PROTECTED / rc 10 / revert unchanged 279dc5a..6b3b2ac; 18 tests | closed |
| T-01-28 | Tampering | trial patch left in tree | medium | mitigate | patch read and discarded; trees clean | closed |
| T-01-29 | Elevation of Privilege | agent editing gate/hook/shield | high | mitigate | in adapter PROTECTED; cross_ai forbidden for gate plans | closed |
| T-01-30 | Information Disclosure | smoke report / evidence | high | mitigate | script-built from redacted data; 0 e-mail/tokens | closed |
| T-01-31 | Elevation of Privilege | accidental restart/backup during checks | high | mitigate | InvocationID/NRestarts/MainPID unchanged; no backup dir | closed |
| T-01-32 | Repudiation | false green series | medium | mitigate | 3 consecutive runs on one HEAD, hash stable | closed |
| T-01-SC | Tampering | package installs | high | mitigate | no dependency files changed; stdlib-only scripts | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01-01 | T-01-06 | Shared tests that pin Phase-2 behaviour ported unchanged with SECF-01 markers; rewritten in Phase 2 | plan 01-02 (owner-approved plan) | 2026-10-09 |
| AR-01-02 | T-01-08 | Hook interpreter selected via VIRTUAL_ENV with a fixed lookup order; environment is owner-local | plan 01-03 (owner-approved plan) | 2026-10-09 |
| AR-01-03 | T-01-15 (residual) | Empty `assistant.db-wal`/`-shm` in `data/` after ro reads (also produced by the daemon's own WAL mode); harmless, gitignored; handling deferred to Phase 3 | owner (poll) | 2026-10-09 |
| AR-01-04 | T-uo4-02 (chat-app quick 261009-uo4) | Adapter: a `scripts` symlink could substitute gate.py only in a repo with no tracked `scripts/`; not applicable to chat-app/assistant-core/assistant-shared (rc 12); refusal + test scheduled for Phase 2 | owner (poll) | 2026-10-09 |

*Accepted risks do not resurface in future audit runs.*

**Informational (auditor, non-blocking):** the live-DB guard matches by basename (a renamed copy/symlink of the live DB is not caught — documented plan assumption); group names in journal error lines are protected only by truncation + pattern redaction; `--report`/`--state-file` accept any operator-chosen writable path.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-09 | 33 | 33 | 0 | gsd-security-auditor (sonnet), orchestrator verified T-01-03 in `src/config.py` |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
