---
phase: "1"
slug: "sobstvennyy-geyt-kachestva-assistant-core"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
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
| **Full suite command** | `python3 scripts/gate.py` (pytest core 421+, pytest shared, lint-imports, shield, drift, DB hash) |
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
| GATE-01 | `pytest_ok` rejects 0 tests, failed, error, skipped, xfailed, xpassed, deselected | unit | `pytest tests/test_gate.py -k pytest_ok -q` | ❌ W0 | ⬜ pending |
| GATE-01 | Red cases on mini-projects give `ok=False` | integration | `pytest tests/test_gate_red_cases.py -q` | ❌ W0 | ⬜ pending |
| GATE-01 | Failed step = red row, other rows still printed | unit | `pytest tests/test_gate.py -k safe_step -q` | ❌ W0 | ⬜ pending |
| GATE-01 | Russian table, `ИТОГ: ЗЕЛЁНЫЙ` rc 0 / `ИТОГ: КРАСНЫЙ` rc≠0 | unit | `pytest tests/test_gate.py -k render -q` | ❌ W0 | ⬜ pending |
| GATE-01 | Timing tests stable (no flaky `latency_ms` thresholds) | unit | `pytest tests/test_command_aliases.py -q` | ✅ (needs fix) | ⬜ pending |
| GATE-02 | Guard blocks `open`/`sqlite3`/`aiosqlite`/`file:` URI/relative path to prod DB | unit | `pytest tests/test_live_db_guard.py -q` | ❌ W0 | ⬜ pending |
| GATE-02 | `load_dotenv(override=True)` does not override isolated DB path | unit | `pytest tests/test_live_db_guard.py -k override -q` | ❌ W0 | ⬜ pending |
| GATE-02 | gdrive backup test does not touch prod files | unit | `pytest tests/test_gdrive_client.py -q` | ✅ (needs fix) | ⬜ pending |
| GATE-02 | DB hash before/after: equal, missing, mismatch | unit | `pytest tests/test_gate.py -k db_ -q` | ❌ W0 | ⬜ pending |
| GATE-03 | Shared tests (migrator, HITL, security) pass | integration | `cd /opt/assistant-shared && /opt/assistant-core/.venv/bin/pytest tests -p no:cacheprovider -q` | ❌ W0 | ⬜ pending |
| GATE-03 | Shared pre-commit hook blocks synthetic secret | integration | `pytest tests/test_pre_commit_hook.py` (shared) | ❌ W0 | ⬜ pending |
| GATE-03 | Shared rows shown separately in gate table | unit | `pytest tests/test_gate.py -k shared -q` | ❌ W0 | ⬜ pending |
| GATE-04 | Drift: match green, diff/missing red | unit | `pytest tests/test_gate.py -k drift -q` | ❌ W0 | ⬜ pending |
| GATE-04 | Frozen shield list: new finding and stale entry red | unit | `pytest tests/test_gate.py -k shield -q` | ❌ W0 | ⬜ pending |
| GATE-05 | Adapter picks `$TOP/scripts/gate.py` | integration (chat-app `/gsd-quick`) | `/opt/chat-app/backend/.venv/bin/pytest backend/tests/test_agy_cross_ai.py` | ✅ (extend) | ⬜ pending |
| OPS-01 | No `systemctl restart` without `--restart` | unit | `pytest tests/test_deploy_script.py -k no_restart -q` | ❌ W0 | ⬜ pending |
| OPS-01 | Journal parsing: ERROR/CRITICAL/Traceback red, WARNING reported only, redaction | unit | `pytest tests/test_deploy_script.py -k journal -q` | ❌ W0 | ⬜ pending |
| OPS-01 | Expected jobs from `ast` of `src/main.py` | unit | `pytest tests/test_deploy_script.py -k jobs -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_gate.py`, `tests/test_gate_red_cases.py`, `tests/test_live_db_guard.py`, `tests/test_deploy_script.py`
- [ ] Guard in `tests/conftest.py` + DB path override in `src/config.py`
- [ ] `create_server_backup_archive` directory parameter + `tests/test_gdrive_client.py` fix
- [ ] Timing test stabilisation (`tests/test_command_aliases.py`)
- [ ] `/opt/assistant-shared/tests/`, pytest section in `pyproject.toml`, `scripts/security_shield.py`, `.githooks/pre-commit`, `scripts/install_hooks.sh`
- [ ] No framework install needed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Read-only smoke on the live service (no restart) | OPS-01 | Needs the real service and an owner message to the bot | `python3 scripts/deploy.py smoke --report …`, record result in VERIFICATION.md |
| Trial `agy_cross_ai.sh --repo /opt/assistant-core` prints ЗЕЛЁНЫЙ | GATE-05 | Runs a real agent; clean tree required | Run last, check `gate.log` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
