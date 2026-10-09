---
last_mapped_commit: 5997ad6c8c219390ead42ea5132f2660f488f15d
last_mapped_at: 2026-10-09
---
# Testing Patterns

**Analysis Date:** 2026-10-09

## Test Framework

**Runner:**
- pytest `>=8.0.0` (`requirements.txt`), with `pytest-asyncio` in auto mode.
- Config: `/opt/assistant-core/pytest.ini`
  - `asyncio_mode = auto` (async tests need no marker, though some still use `@pytest.mark.asyncio`)
  - `testpaths = tests`
  - `pythonpath = .` (tests import `src.*` and `tests.*` from repo root)
- Architecture contract tests use `grimp` and `import-linter` (`requirements-dev.txt`: `import-linter>=2.15`, `grimp>=3.17`).

**Assertion Library:**
- Plain `assert` statements (pytest rewriting). Custom messages are used for loops and invariants: `assert stats_repeat["skipped"] == 1, f"Run {i} should have skipped..."`.

**Mocking:**
- `unittest.mock` (`MagicMock`, `AsyncMock`, `patch`, `patch.object`). About 36 test modules use mocks, fixtures, or `monkeypatch`.

**Run Commands:**

```bash
/opt/assistant-core/.venv/bin/pytest /opt/assistant-core/tests              # Run all tests (required form)
/opt/assistant-core/.venv/bin/pytest tests/test_brain.py -q                 # Single file
/opt/assistant-core/.venv/bin/pytest tests -k hitl                          # Keyword subset (dev only; not valid for the gate)
/opt/assistant-core/.venv/bin/pytest tests -p no:cacheprovider              # Match the gate's invocation
python3 /opt/chat-app/scripts/gate.py                                       # Full quality gate (both repos)
/opt/assistant-core/.venv/bin/python3 /opt/assistant-core/scripts/security_shield.py   # Security scan (staged files)
/opt/assistant-core/.venv/bin/python3 /opt/assistant-core/scripts/security_shield.py --all  # Security scan, all tracked files
```

- Coverage: no coverage tool is configured (`.coverage` is git-ignored, no `pytest-cov` in `requirements-dev.txt`). No coverage command is defined.
- Watch mode: not configured.

## Quality Gate (shared, read-only description)

assistant-core has no gate of its own yet (planned early task). The shared gate `/opt/chat-app/scripts/gate.py` is the current reference. For assistant-core it checks:

1. **pytest assistant-core** on `/opt/assistant-core/tests` using `/opt/assistant-core/.venv/bin/pytest`. The gate runs with `-v`, `-p no:cacheprovider`, a JUnit XML report, and its own `--basetemp`. Timeout: 900 s.
2. **lint-imports** with `/opt/assistant-core/.importlinter` (architecture contracts; see CONVENTIONS.md).
3. **security_shield** `--all` over tracked files, with a frozen list of known false positives. For assistant-core the only entry is `config/persona.yaml` (`nda-keyword`, 3 hits), to be removed by SEC-01.
4. **Persona drift**: SHA-256 of `tests/synthetic_persona.py` in chat-app and assistant-core must match.
5. **Production DB hash** before and after the run. Any change marks the gate red. The gate reads the live DB only through a read-only backup, and never the live DB itself for chat-app tests.

Gate pass rules that affect how tests must be written:
- Zero collected tests = red.
- Any skipped, xfail, xpass, or deselected test = red. **Do not use `pytest.skip`, `xfail`, or `-k`/`-m` filters to make a test pass in the gate.**
- Tests must not depend on the real `.env`, `credentials.json`, `token.json`, `*.session`, or the systemd services.

## Test File Organization

**Location:**
- All tests are in one flat directory: `/opt/assistant-core/tests/`. There are no co-located tests in `src/`.
- Approximately 60 test modules and about 378 `def test_` functions (static count across `tests/`).

**Naming:**
- `test_<subject>.py` for unit or module tests (`test_guap_lms.py`, `test_key_rotator.py`, `test_voice.py`).
- `test_<cross-cutting>.py` for contracts and guardrails (`test_architecture_contract.py`, `test_core_architecture.py`, `test_ports_conformance.py`, `test_hitl_safety_guardrails.py`, `test_airgap_trap.py`, `test_nda_script_parity.py`, `test_hardcode_scanner.py`).
- `test_phase1.py`, `test_phase2_filter.py` are phase-named regression suites; prefer subject-based names for new tests.

**Structure:**

```
tests/
├── conftest.py                 # Shared fixtures (synthetic_persona, default_persona_config)
├── __init__.py
├── synthetic_persona.py        # Synthetic persona data (must match chat-app copy by hash)
├── persona_tokens.py           # Owner-token classes for hardcode scanning
├── hardcode_baseline.py        # Frozen baseline of known hardcoded-token debt (may not grow)
├── fixtures/
│   ├── prompts_snapshot/       # Golden prompt text (debrief.txt, evening_digest.txt, ...)
│   └── synthetic_prompts/      # Synthetic prompt inputs
└── test_*.py
```

## Test Structure

**Suite organization:**
Tests are plain module-level functions, not classes. Group by behaviour with comments or prefixes, not `class Test...`.

```python

# tests/test_brain.py (pattern)

from src.brain.summarizer import GeminiSummarizer

def test_summarizer_initialization_offline() -> None:
    summarizer = GeminiSummarizer(api_key="")
    assert not summarizer.is_configured

async def test_summarizer_fallback_brief_generation() -> None:
    summarizer = GeminiSummarizer(api_key="")
    brief = await summarizer.generate_morning_brief(today, lessons, action_items)
    assert "Утренний дайджест" in brief
```

**Patterns:**
- **Setup:** construct objects directly with empty or synthetic inputs (`api_key=""`, `email="user@guap.ru"`). Use fixtures for shared state.
- **Teardown:** rely on `tmp_path` (pytest auto-cleans) and `patch` context managers. No global teardown fixtures are standard.
- **Assertions:** check on substrings of rendered output and exact values of dataclass fields. Brief/prompt output is checked against golden text in `tests/fixtures/prompts_snapshot/`.

**Fixtures (`tests/conftest.py`):**
- `synthetic_persona` (function scope): deep copy of `SYNTHETIC_PERSONA` from `tests/synthetic_persona.py`, so tests can mutate it safely.
- `default_persona_config` (session scope): `load_persona().model_dump(mode="json")` from `config/persona.yaml`, with `PERSONA_CONFIG_PATH` temporarily removed. Use this when a test needs real owner profile fields; do not copy them into test code (PER-08, D-16).

## Mocking

**Framework:** `unittest.mock` (`MagicMock`, `AsyncMock`, `patch`, `patch.object`) and `pytest` `monkeypatch`.

**Patterns:**

```python

# tests/test_guap_lms.py (pattern)

from unittest.mock import MagicMock, patch

def test_is_authenticated_check():
    client = GuapLmsClient(email="user@guap.ru", password="pass")
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch.object(client.session, "get", return_value=mock_resp):
        assert client.is_authenticated()
```

- Patch at the object you own: `patch.object(client.session, "get", ...)` rather than global module paths when possible.
- For async collaborators use `AsyncMock` or a small fake class implementing the port Protocol. `tests/test_ports_conformance.py` checks that fakes and real providers satisfy `runtime_checkable` Protocols.

**What to Mock:**
- Network clients and HTTP sessions (`requests`/`httpx` sessions, Gemini `genai` client, Telegram bot API).
- External clocks or randomness when output depends on time.
- Key rotation and LLM responses (use canned JSON through `extract_json_object`).

**What NOT to Mock:**
- The domain layer (`src/core/`): test real frozen dataclasses and enums.
- SQLite storage in storage tests: use a real database file under `tmp_path` (`Database(str(tmp_path / "t.db"))`) or `:memory:`. `Database` supports `:memory:` with a shared connection (`src/storage/db.py`).
- The import-linter contract: it is tested by running `lint-imports` on synthetic packages in `tmp_path` (`tests/test_architecture_contract.py`), not by mocking.

## Fixtures and Factories

**Test Data:**
- Synthetic persona: `tests/synthetic_persona.py` (`SYNTHETIC_PERSONA` dict). A second persona validates that nothing depends on the owner profile (FND-03). The copy in chat-app must stay byte-identical (gate checks SHA-256).
- Golden prompt snapshots: `tests/fixtures/prompts_snapshot/*.txt`. Updating a snapshot is an intentional change, reviewed as a diff; see `tests/test_prompt_snapshot.py`.
- Domain object factories: build inline, e.g. `Lesson(subject=..., lesson_type=LessonType.LECTURE, date=today, start_time=time(9, 30), ...)`.

**Location:**
- Shared data: `tests/` root modules and `tests/fixtures/`.
- Test-only DB files: `tmp_path`, never `data/assistant.db`.

**Dates:** tests use fixed dates (e.g. `date(2026, 9, 28)`), not `date.today()`, so output is deterministic.

## Coverage

**Requirements:** None enforced. No coverage threshold in config or gate.

**View coverage:** not configured. To measure locally, install `pytest-cov` into the venv (not in requirements) and run `pytest --cov=src tests`. Do not add it to the gate without a decision.

## Test Types

**Unit Tests:**
- Most modules: `test_<module>.py`, pure functions and classes with mocks at I/O boundaries (`test_key_rotator.py`, `test_debrief_parser.py`, `test_aadhk_parser.py`, `test_fast_intent_router.py`).

**Integration Tests:**
- Database and workflow: `test_phase1.py` (ingest and idempotency against real SQLite under `tmp_path`), `test_lms_bot_workflow.py`, `test_email_reply_workflow.py`, `test_tool_calling_flow.py`, `test_tool_calling_e2e.py`.
- Bot HITL flows with real `Database` in `tmp_path`: `test_hitl_safety_guardrails.py` (dialog history, clear, undo, confirm/cancel callbacks).

**Guardrail and contract tests (run as part of the suite, enforced by the gate):**
- `test_architecture_contract.py`, `test_core_architecture.py`: import-linter contract and runtime purity of `src.core`.
- `test_airgap_trap.py`, `test_git_airgap_trap.py`: air-gap must block NDA data flows.
- `test_hardcode_scanner.py` with `hardcode_baseline.py`: owner-profile tokens may not appear in tracked code beyond the frozen baseline. The baseline can only shrink.
- `test_prompt_snapshot.py`: prompts match golden files.
- `test_nda_script_parity.py`: parity between NDA keyword lists in shared code and scripts.

**E2E Tests:**
- No browser or live-service E2E. `test_tool_calling_e2e.py` runs the tool-calling path with fakes. Do not call real Telegram, Google, Gemini, or pro.guap.ru in tests.

## Common Patterns

**Async Testing:**

```python

# pytest-asyncio auto mode: async def test_* runs without a marker.

async def test_dialog_history_hitl_and_undo(tmp_path):
    db = Database(str(tmp_path / "assistant.db"))
    ...
```

- Some older tests still add `@pytest.mark.asyncio`; both forms work under `asyncio_mode = auto`. Use the bare `async def` form in new tests.

**Error Testing:**

```python
import pytest
from src.core.exceptions import MissingScopeError

def test_connector_requires_scopes():
    with pytest.raises(MissingScopeError):
        ...  # construct connector without required scopes
```

- Use `pytest.raises(...)` with the specific exception type, not bare `Exception`.
- Check the message only when it is a stable contract.

**Subprocess-based architecture tests:**
- Run `lint-imports` or a Python probe with `subprocess.run([...], cwd=tmp_path, capture_output=True, text=True)`. Use `sys.executable` and `Path(sys.executable).parent / "lint-imports"`, not `.resolve()` (venv symlink).

## Rules for Writing New Tests

1. Put the file in `/opt/assistant-core/tests/test_<subject>.py`. Import from `src.` and `tests.` at the repo root.
2. Do not skip, xfail, or deselect. A skipped test makes the gate red.
3. Use `tmp_path` for any database, file, or session path. Never open `data/assistant.db`, `.env`, `credentials.json`, `token.json`, or `*.session` from tests.
4. Use fixed dates and synthetic persona data; read owner-specific values only via `default_persona_config`.
5. Mock external network clients; do not mock `src/core` or the SQLite layer.
6. For new policy rules (HITL, air-gap, deletion), add a guardrail test in the same style as `test_hitl_safety_guardrails.py` and `test_airgap_trap.py`.
7. Keep golden-file updates in the same commit as the prompt change.

## Known Gaps

- No coverage measurement is configured.
- Count of `test_` functions is static (~378); the gate reports the collected total at run time.
- `tests/test_phase1.py` and similar phase-named files reach across several modules; splitting them is optional debt, not a requirement.
- Shared `security_shield` findings for `config/persona.yaml` are excepted in the gate until SEC-01 is done.

---

*Testing analysis: 2026-10-09*
