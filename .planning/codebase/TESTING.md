---
last_mapped_commit: 4ef89375cad045faaab6c362041879d2d4863602
last_mapped_at: 2026-10-10
---

# Testing Patterns

**Analysis Date:** 2026-10-10

## Test Framework

**Runner:**
- pytest >=8.0.0 with pytest-asyncio >=0.23.0 (see `requirements-dev.txt`)
- Config: `/opt/assistant-core/pytest.ini`
  - `asyncio_mode = auto` (async tests need no marker, but existing files use `@pytest.mark.asyncio`)
  - `testpaths = tests`
  - `pythonpath = .`

**Assertion Library:**
- Plain pytest `assert`. Pytest rewriting gives detailed diffs; custom messages are used for loops (e.g. `assert stats_repeat["skipped"] == 1, f"Run {i} should have skipped ..."` in `tests/test_phase1.py`).

**Mocking:**
- `unittest.mock` (`MagicMock`, `AsyncMock`, `patch`) and pytest `monkeypatch`.

**Run Commands:**

```bash
/opt/assistant-core/.venv/bin/pytest /opt/assistant-core/tests        # Run all tests (daemon suite)
/opt/assistant-core/.venv/bin/pytest tests/test_brain.py -q           # Single module
/opt/assistant-core/.venv/bin/pytest -k test_name                     # Filter (local debugging only; never in the gate)
python3 scripts/gate.py                                               # Full quality gate (run from /opt/assistant-core)
/opt/assistant-core/.venv/bin/python3 scripts/security_shield.py      # Security scan
```

- Coverage: no coverage tool is configured. No watch mode is configured.

## Quality Gate Pass Rules

`scripts/gate.py` is the authority for "green". The rules that affect how tests are written:
- Zero collected tests = red.
- Any skipped, xfail, xpass or deselected test = red. Do not use `pytest.skip`, `pytest.mark.xfail`, or `-k`/`-m` filters to make a test pass in the gate.
- The gate also checks: import-linter contracts, security_shield with the frozen `KNOWN_SHIELD_FALSE_POSITIVES` list, read-only drift of `tests/synthetic_persona.py` and `tests/persona_tokens.py` against the chat-app copies (SHA-256, fail-closed if the copy is missing), SHA-256 of the live DB before and after pytest, and the pre-commit hook being installed.
- Tests must not depend on `.env`, `credentials.json`, `token.json`, `*.session` files, or systemd services.

## Test File Organization

**Location:**
- All tests live in one flat directory: `/opt/assistant-core/tests/`. No tests are co-located in `src/`.
- 53 test modules (`tests/test_*.py`) at the time of this analysis.

**Naming:**
- `test_<subject>.py` for module tests: `tests/test_guap_lms.py`, `tests/test_key_rotator.py`, `tests/test_voice.py`.
- `test_<cross-cutting>.py` for contracts and guardrails: `tests/test_architecture_contract.py`, `tests/test_core_architecture.py`, `tests/test_ports_conformance.py`, `tests/test_hitl_safety_guardrails.py`, `tests/test_airgap_trap.py`, `tests/test_git_airgap_trap.py`, `tests/test_nda_script_parity.py`, `tests/test_hardcode_scanner.py`.
- `tests/test_phase1.py`, `tests/test_phase2_filter.py` are phase-named regression suites. Prefer subject-based names for new tests.
- `tests/test_gate.py` and `tests/test_gate_red_cases.py` test the gate itself.

**Helper modules inside `tests/`:**
- `tests/conftest.py`: shared fixtures, installs the live-DB guard, sets isolated DB path.
- `tests/live_db_guard.py`: audit hook that blocks access to the live DB.
- `tests/synthetic_persona.py`: second, synthetic persona (`SYNTHETIC_PERSONA`) so nothing depends on the owner profile (FND-03).
- `tests/persona_tokens.py`, `tests/hardcode_baseline.py`: data for the hardcode scanner.

## Test Structure

**Suite Organization (observed pattern, `tests/test_brain.py`):**

```python
from datetime import date, time
import pytest
from src.brain.summarizer import GeminiSummarizer
from src.models.schedule import Lesson, LessonType

def test_summarizer_initialization_offline() -> None:
    summarizer = GeminiSummarizer(api_key="")
    assert not summarizer.is_configured

@pytest.mark.asyncio
async def test_summarizer_fallback_brief_generation() -> None:
    summarizer = GeminiSummarizer(api_key="")
    today = date(2026, 9, 28)
    ...
    brief = await summarizer.generate_morning_brief(today, lessons, action_items)
    assert "Утренний дайджест" in brief
```

- Flat module-level `test_*` functions. No test classes are the dominant style.
- Fixed dates (e.g. `date(2026, 9, 28)`) rather than `date.today()`.
- Test names and assertion messages are Russian or English, following the module.

**Async tests:**
- Mark with `@pytest.mark.asyncio` (used in about 30 files) or rely on `asyncio_mode = auto`. Match the surrounding file.
- Async fixtures use `@pytest_asyncio.fixture` or `@pytest.fixture` with `async def` under auto mode. Example: `test_db` fixture in `tests/test_fast_intent_router.py`.

**Setup and teardown:**
- Database state: create a `Database` on `tmp_path` and call `await db.init_db()`:

```python
@pytest.mark.asyncio
async def test_dialog_history_hitl_and_undo(tmp_path):
    db_file = tmp_path / "test_hitl.db"
    db = Database(f"sqlite+aiosqlite:///{db_file}")
    await db.init_db()
```

- Shared fixtures in `tests/conftest.py`:
  - `synthetic_persona` (function scope): deep copy of `SYNTHETIC_PERSONA`.
  - `default_persona_config` (session scope): `load_persona().model_dump(mode="json")` from `config/persona.yaml`, with `PERSONA_CONFIG_PATH` temporarily removed. Use this when a test needs owner values.
- Temporary directories: `tmp_path` (pytest) is used in roughly 240 places. `tempfile.mkdtemp` is used only in `conftest.py` for the isolated DB directory, removed via `atexit`.
- Environment: `os.environ.setdefault("ASSISTANT_DB_PATH_OVERRIDE", ...)` in `conftest.py` points `src/config.py` at the isolated DB before the first `src` import.

**Patterns:**
- Assert on return values and DB state after an action; then assert again after the reversal (undo, restore).
- Confirm HITL: call the handler, assert the DB is unchanged, then assert the confirmation card was sent with the expected callback data (`tests/test_hitl_safety_guardrails.py`).

## Mocking

**Framework:** `unittest.mock` (`MagicMock`, `AsyncMock`) and `patch`; `monkeypatch` for environment and attributes.

**Patterns (observed):**

```python
from unittest.mock import AsyncMock, MagicMock

handler = EmailBotHandler(bot=MagicMock(), db=db, allowed_user_id=user_id)
msg = MagicMock()
msg.from_user.id = user_id
msg.chat.id = user_id
msg.answer = AsyncMock()

await handler.handle_cmd_clear_dialog(msg)
msg.answer.assert_called_once()
args, kwargs = msg.answer.call_args
```

Patch targets are full import paths of the module under test:

```python
patch("src.connectors.gdrive.client.Credentials")
patch("src.connectors.gdrive.client.build")
patch("httpx.AsyncClient.post")
patch("asyncio.create_subprocess_exec")
```

**What to Mock:**
- External network clients: Gemini (`google.genai`), Telegram (`aiogram` bot), Google APIs, Notion, LMS/schedule HTTP, git subprocesses.
- Telegram bot objects: `MagicMock()` for `bot`, `AsyncMock()` for `msg.answer`.
- Without a real API key, prefer the constructor's offline mode (e.g. `GeminiSummarizer(api_key="")`, `is_configured == False`) over a mock. This exercises the real fallback path.

**What NOT to Mock:**
- Do not mock `src/core` or the SQLite layer. Use a real `Database` on `tmp_path`. The repo rule is "mock external network clients; do not mock `src/core` or the SQLite layer."
- Do not mock the air-gap or HITL decision logic. Those guard tests must run the real code path (`tests/test_airgap_trap.py`, `tests/test_git_airgap_trap.py`).

## Fixtures and Factories

**Test Data:**
- Build domain objects inline with explicit fields, e.g. `Lesson(subject=..., lesson_type=LessonType.LECTURE, date=today, start_time=time(9, 30), ...)`.
- Synthetic persona dict in `tests/synthetic_persona.py` is the source of profile-like data for tests. Do not invent new personal data; do not copy the owner's values into tests.
- Synthetic persona copy in chat-app must stay byte-identical (gate checks SHA-256).

**Location:**
- Shared fixtures: `tests/conftest.py`. Module-specific fixtures live in their test module (e.g. `tests/test_notion_git_hitl.py`, `tests/test_git_airgap_trap.py`).
- No `fixtures/` directory exists under `tests/` or `.claude/`.

**Gate self-tests:**
- `tests/test_gate_red_cases.py` builds mini-projects in `tmp_path`, runs the real `gate.run_pytest_step` in a subprocess, and asserts red cases (`ok is False`) and one green control (`ok is True`).

## Coverage

**Requirements:** None enforced by a tool. The gate requires 100% pass with zero skipped/xfail/deselected tests.

**View Coverage:**
- Not configured. Add `pytest-cov` only with owner approval (new dependencies require approval).

## Test Types

**Unit Tests:**
- Pure logic and domain: `tests/test_core_domain.py`, `tests/test_persona_loader.py`, `tests/test_key_rotator.py`, `tests/test_aadhk_parser.py`.
- Use cases with a real DB and mocked LLM or network: `tests/test_brain.py`, `tests/test_fast_intent_router.py`, `tests/test_secretary_dialog.py`.

**Integration Tests:**
- Database-backed flows on `tmp_path`: `tests/test_phase1.py`, `tests/test_email_reply_workflow.py`, `tests/test_lms_bot_workflow.py`, `tests/test_memory_review.py`.
- Bot handler dispatch with mocked `bot` and real `Database`: `tests/test_bot_hitl_parity.py`, `tests/test_hitl_telegram_cards.py`, `tests/test_command_aliases.py`.
- Tool-calling end-to-end with mocked model: `tests/test_tool_calling_e2e.py`, `tests/test_tool_calling_flow.py`.

**Architecture and Contract Tests:**
- `tests/test_architecture_contract.py`: runs `lint-imports` (`Path(sys.executable).parent / "lint-imports"`) against the real `.importlinter` and against synthetic copies in `tmp_path`. It checks that the contract fails on violations and that the ignore-import debt stays at or below `MAX_IGNORED_IMPORTS`.
- `tests/test_core_architecture.py`, `tests/test_ports_conformance.py`: structural checks. Conformance uses `isinstance(make(), port)` on `@runtime_checkable` Protocols and checks `inspect.iscoroutinefunction` on each method.
- `tests/test_hardcode_scanner.py`: scans tracked git files for owner tokens; the baseline may only shrink.

**Safety Guardrail Tests (required for new policy rules):**
- `tests/test_hitl_safety_guardrails.py`: destructive actions (dialog clear, deletion) must show a HITL card and must not change data before confirmation; undo must restore.
- `tests/test_airgap_trap.py`, `tests/test_git_airgap_trap.py`, `tests/test_nda_script_parity.py`: NDA content must not reach external LLM flows.
- `tests/live_db_guard.py`: audit hook (`sys.addaudithook`) that raises `LiveDatabaseAccessError` on `open` or `sqlite3.connect` to `data/assistant.db` or `assistant.db` (plus `-wal`, `-shm`, `-journal` sidecars). It is installed by `conftest.py` before any `src` import and cannot be removed for the process lifetime.

**E2E Tests:**
- Not used. No browser or live-service tests. `scripts/test_secretary_simulation.py` and `scripts/run_stt_stress_test.py` are manual scripts outside `tests/`.

## Common Patterns

**Async Testing:**

```python
@pytest.mark.asyncio
async def test_router_fallback_on_model_quota_error(test_db):
    ...
```

**Error Testing:**

```python
import pytest
from src.core.exceptions import AirGapViolationError

with pytest.raises(AirGapViolationError):
    ...
```

- Use `pytest.raises` with the specific exception type. For subprocess-based checks, assert on `returncode` and `stdout`/`stderr` text from `subprocess.run(..., capture_output=True, text=True)`.

**Subprocess Tests:**

```python
result = subprocess.run([...], cwd=tmp_path, capture_output=True, text=True)
```

- Pass `cwd=tmp_path`. Use `sys.executable` and `Path(sys.executable).parent / "<tool>"` for venv tools. Do not call `.resolve()` on the interpreter path: the venv python is a symlink to the system interpreter and resolve() drops the venv `bin` directory.

## Rules for Writing New Tests

1. Put the file at `/opt/assistant-core/tests/test_<subject>.py`. Import from `src.` and `tests.` at the repo root.
2. Do not skip, xfail or deselect. A skipped test makes the gate red.
3. Use `tmp_path` for any database, file or session path. Never open `data/assistant.db`, `.env`, `credentials.json`, `token.json` or `*.session` from tests.
4. Use fixed dates and synthetic persona data. Read owner-specific values only through `default_persona_config`.
5. Mock external network clients. Do not mock `src/core` or the SQLite layer.
6. For new policy rules (HITL, air-gap, deletion), add a guardrail test in the style of `tests/test_hitl_safety_guardrails.py` and `tests/test_airgap_trap.py`.
7. Keep golden-file updates (e.g. prompt snapshots in `tests/test_prompt_snapshot.py`) in the same commit as the prompt change.

## Known Gaps

- No coverage measurement is configured.
- The number of collected tests changes over time; the gate reports the total at run time.
- `tests/test_phase1.py` and similar phase-named files reach across several modules. Splitting them is optional debt.
- Shield false positives are frozen in `KNOWN_SHIELD_FALSE_POSITIVES` in `scripts/gate.py`; entries may only be removed.

---

*Testing analysis: 2026-10-10*
