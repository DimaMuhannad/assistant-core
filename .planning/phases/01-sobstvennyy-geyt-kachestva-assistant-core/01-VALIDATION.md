---
phase: "1"
slug: "sobstvennyy-geyt-kachestva-assistant-core"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: true) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-10-09"
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `01-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode = auto`) |
| **Config file** | `/opt/assistant-core/pytest.ini`; for shared — `[tool.pytest.ini_options]` in `/opt/assistant-shared/pyproject.toml` (Wave 0) |
| **Quick run command** | `/opt/assistant-core/.venv/bin/pytest tests/test_gate.py tests/test_live_db_guard.py tests/test_deploy_script.py -p no:cacheprovider -q` |
| **Full suite command** | `python3 scripts/gate.py` (pytest core 792, pytest shared, lint-imports, shield, drift, DB hash) |
| **Estimated runtime** | quick ~10 s; full ~300–360 s |

---

## Sampling Rate

- **After every task commit:** Run the quick command (shared tasks: `cd /opt/assistant-shared && /opt/assistant-core/.venv/bin/pytest tests -p no:cacheprovider -q`)
- **After every plan wave:** Run `python3 scripts/gate.py`
- **Before `/gsd-verify-work`:** three consecutive green gate runs + read-only smoke on the live service + trial `agy_cross_ai.sh --repo /opt/assistant-core` run
- **Max feedback latency:** 30 seconds (quick set)

---

## Per-Task Verification Map

Filled by the planner per task; requirement-level map:

| Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|----------|-----------|-------------------|-------------|--------|
| GATE-01 | `pytest_ok` rejects 0 tests, failed, error, skipped, xfailed, xpassed, deselected | unit | `pytest tests/test_gate.py -k pytest_ok -q` | ✅ | ✅ green |
| GATE-01 | Red cases on mini-projects give `ok=False` | integration | `pytest tests/test_gate_red_cases.py -q` | ✅ | ✅ green |
| GATE-01 | Failed step = red row, other rows still printed | unit | `pytest tests/test_gate.py -k "safe or never_aborts" -q` | ✅ | ✅ green |
| GATE-01 | Russian table, `ИТОГ: ЗЕЛЁНЫЙ` rc 0 / `ИТОГ: КРАСНЫЙ` rc≠0 | unit | `pytest tests/test_gate.py -k render -q` | ✅ | ✅ green |
| GATE-01 | Timing tests stable (no flaky `latency_ms` thresholds) | unit | `pytest tests/test_command_aliases.py -q` | ✅ | ✅ green |
| GATE-02 | Guard blocks `open`/`sqlite3`/`aiosqlite`/`file:` URI/relative path to prod DB | unit | `pytest tests/test_live_db_guard.py -q` | ✅ | ✅ green |
| GATE-02 | `load_dotenv(override=True)` does not override isolated DB path | unit | `pytest tests/test_live_db_guard.py -k override -q` | ✅ | ✅ green |
| GATE-02 | gdrive backup test does not touch prod files | unit | `pytest tests/test_gdrive_client.py -q` | ✅ | ✅ green |
| GATE-02 | DB hash before/after: equal, missing, mismatch | unit | `pytest tests/test_gate.py -k db_ -q` | ✅ | ✅ green |
| GATE-03 | Shared tests (migrator, HITL, security) pass | integration | `cd /opt/assistant-shared && /opt/assistant-core/.venv/bin/pytest tests -p no:cacheprovider -q` | ✅ | ✅ green |
| GATE-03 | Shared pre-commit hook blocks synthetic secret | integration | `pytest tests/test_pre_commit_hook.py` (shared) | ✅ | ✅ green |
| GATE-03 | Shared rows shown separately in gate table | unit | `pytest tests/test_gate.py -k shared -q` | ✅ | ✅ green |
| GATE-04 | Drift: match green, diff/missing red | unit | `pytest tests/test_gate.py -k drift -q` | ✅ | ✅ green |
| GATE-04 | Frozen shield list: new finding and stale entry red | unit | `pytest tests/test_gate.py -k shield -q` | ✅ | ✅ green |
| GATE-05 | Adapter picks `$TOP/scripts/gate.py` | integration (chat-app `/gsd-quick`) | `/opt/chat-app/backend/.venv/bin/pytest backend/tests/test_agy_cross_ai.py` | ✅ | ✅ green |
| OPS-01 | No `systemctl restart` without `--restart` | unit | `pytest tests/test_deploy_script.py -k restart -q` | ✅ | ✅ green |
| OPS-01 | Journal parsing: ERROR/CRITICAL/Traceback red, WARNING reported only, redaction | unit | `pytest tests/test_deploy_script.py -k journal -q` | ✅ | ✅ green |
| OPS-01 | Expected jobs from `ast` of `src/main.py` | unit | `pytest tests/test_deploy_script.py -k jobs -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_gate.py`, `tests/test_gate_red_cases.py`, `tests/test_live_db_guard.py`, `tests/test_deploy_script.py`
- [x] Guard in `tests/conftest.py` + DB path override in `src/config.py`
- [x] `create_server_backup_archive` directory parameter + `tests/test_gdrive_client.py` fix
- [x] Timing test stabilisation (`tests/test_command_aliases.py`)
- [x] `/opt/assistant-shared/tests/`, pytest section in `pyproject.toml`, `scripts/security_shield.py`, `.githooks/pre-commit`, `scripts/install_hooks.sh`
- [x] No framework install needed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Read-only smoke on the live service (no restart) | OPS-01 | Needs the real service and an owner message to the bot | `python3 scripts/deploy.py smoke --report …`, record result in VERIFICATION.md |
| Trial `agy_cross_ai.sh --repo /opt/assistant-core` prints ЗЕЛЁНЫЙ | GATE-05 | Runs a real agent; clean tree required | Run last, check `gate.log` |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-10-09 (validate-phase audit: 18/18 rows green; manual-only: live smoke ЗЕЛЁНЫЙ — 01-SMOKE-REPORT.md, adapter trial ЗЕЛЁНЫЙ — 01-09-SUMMARY.md)
