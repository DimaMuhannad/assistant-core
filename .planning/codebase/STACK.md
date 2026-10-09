---
last_mapped_commit: 5997ad6c8c219390ead42ea5132f2660f488f15d
last_mapped_at: 2026-10-09
---
# Technology Stack

**Analysis Date:** 2026-10-09

## Languages

**Primary:**
- Python 3.11+ (Docker image) / 3.12 (declared target in CLAUDE.md and `/opt/assistant-shared/pyproject.toml`) - all daemon code under `src/`, tests under `tests/`, scripts under `scripts/`

**Secondary:**
- Jinja2 templates - LLM prompt templates in `config/prompts/*.jinja2`
- YAML - persona configuration in `config/persona.yaml`, import contracts in `.importlinter`
- SQL - schema migrations in `/opt/assistant-shared/assistant_shared/db/migrations/*.sql` (shared library, consumed via `src/storage/db.py`)
- Shell - `scripts/install_hooks.sh`, git hooks in `.githooks/`

## Runtime

**Environment:**
- Python process run as `python -m src.main` (see `Dockerfile` CMD and `src/main.py`)
- Long-running asyncio event loop; service supervised by `systemd` unit `assistant-worker.service` (per CLAUDE.md)
- Docker image base: `python:3.11-slim` (`/opt/assistant-core/Dockerfile`). Note: this differs from the Python 3.12 target declared in CLAUDE.md and in `assistant-shared` (`requires-python = ">=3.12"`). Treat 3.12 as the authoritative runtime; the Dockerfile is out of date.
- Timezone: `TZ` env var, default `Europe/Moscow` (`src/config.py`)

**Package Manager:**
- pip with plain requirements files (no lockfile detected)
- Lockfile: missing (`requirements.txt` uses `>=` lower bounds only; `markupsafe==3.0.3` and `jinja2>=3.1,<4` are the only pins)
- Local virtualenv: `/opt/assistant-core/.venv` (used by the test and security-scan commands in CLAUDE.md)
- Shared library install: `/opt/assistant-shared` (editable/local package `assistant-shared` 0.1.0, provides `assistant_shared.db` and `assistant_shared.hitl`, `assistant_shared.security`)

## Frameworks

**Core:**
- asyncio (stdlib) - main concurrency model; CLAUDE.md mandates async-first I/O
- aiogram >=3.5.0 - Telegram Bot API framework (`src/notifier/bot_handler.py`, `src/notifier/telegram.py`)
- Telethon >=1.36.0 - Telegram user-account client (MTProto) for message collection (`src/collector/tg_collector.py`, session `data/telethon_userbot.session`)
- APScheduler >=3.10.4 - `AsyncIOScheduler` drives periodic polling in `src/main.py` (timezone = `config.TZ`)
- FastAPI >=0.111.0 + Uvicorn >=0.30.0 - listed in `requirements.txt`; no FastAPI application was found in `src/` during this scan (see CONCERNS if relevant)
- Pydantic >=2.7.0 - models (`src/models/`, persona models in `src/persona/models.py`)

**Persistence:**
- aiosqlite >=0.20.0 - async SQLite driver
- SQLAlchemy >=2.0.0 - listed in requirements; the storage layer uses raw aiosqlite via `assistant_shared.db.connection` (`src/storage/db.py`)
- Migrations: `assistant_shared.db.migrator.run_migrations` (owned by `/opt/assistant-shared`)

**Testing:**
- pytest >=8.0.0 with pytest-asyncio >=0.23.0 - config in `/opt/assistant-core/pytest.ini` (`asyncio_mode = auto`, `testpaths = tests`, `pythonpath = .`)
- import-linter >=2.15 and grimp >=3.17 - architecture contracts in `.importlinter`, enforced by `tests/test_architecture_contract.py` (dev-only, see `requirements-dev.txt`)

**Build/Dev:**
- No build step; container built from `Dockerfile` (apt: build-essential, curl, tzdata)
- docker-compose (`docker-compose.yml`, version 3.8) - single service `assistant-worker`, mounts `./data`, `credentials.json` (read-only), `token.json`
- Security gate: `scripts/security_shield.py` (run with `/opt/assistant-core/.venv/bin/python3`)
- Quality gate: `python3 /opt/chat-app/scripts/gate.py` (external, until assistant-core has its own)

## AI / ML Libraries

**LLM SDK:**
- google-genai >=0.1.1 - `from google import genai`; `genai.Client(api_key=...)` used across `src/brain/*.py` (summarizer, reply_generator, methodist, debrief_parser, intent_router, secretary_dialog)
- Gemini models referenced in code: default `gemini-3.5-flash-lite` (`GEMINI_MODEL` env, `src/config.py`); other model IDs appear as fallbacks/routing targets in `src/brain/` (for example `gemini-3.5-flash`, `gemini-3.6-flash`, `gemini-3.8-flash`, `gemini-flash-latest`, `gemini-2.5-flash`)
- `src/brain/key_rotator.py` - multi-key rotation over `GEMINI_API_KEYS` (comma-separated), caches one `genai.Client` per key

**Speech-to-text:**
- faster-whisper >=1.0.0 - local CPU Whisper (defaults: model `base`, device `cpu`, compute `int8`, 2 threads; `WHISPER_*` env vars in `src/config.py`)
- Groq hosted Whisper - `large-v3-turbo` via HTTP (`src/brain/voice.py`), used when a Groq key is configured; the code falls back to local faster-whisper

## Key Dependencies

**Critical (declared in `requirements.txt`):**
- `google-api-python-client` >=2.125.0, `google-auth-httplib2` >=0.2.0, `google-auth-oauthlib` >=1.2.0 - Google Calendar, Drive and Gmail API access (`src/calendar/client.py`, `src/connectors/gdrive/client.py`, `src/collector/email_collector.py`)
- `httpx` >=0.27.0 - async HTTP for Notion, GUAP LMS and schedule-site fetches (`src/connectors/notion/client.py`, `src/connectors/guap_lms/client.py`)
- `beautifulsoup4` >=4.12.0 - HTML parsing for schedule and LMS pages (`src/parser/`, `src/connectors/guap_lms/`)
- `telegramify-markdown` >=1.4.0 - Markdown-to-Telegram formatting (`src/notifier/`)
- `python-dotenv` >=1.0.1 - loads `/opt/assistant-core/.env` at import of `src/config.py` (override=True)
- `pyyaml` >=6.0 - persona loading (`config/persona.yaml`)
- `jinja2` >=3.1,<4 and `markupsafe==3.0.3` - prompt rendering from `config/prompts/`

**Undeclared imports (used in code, absent from `requirements.txt`):**
- `imapclient` - IMAP ingestion in `src/collector/email_collector.py`
- `pypdf` - PDF parsing (used by GUAP LMS / materials code)
- `html2text` - HTML-to-text conversion for email/LMS content
- `requests` - used by `src/connectors/guap_lms/client.py` and `scripts/download_fizikaguap_materials.py`; currently only available transitively via `google-auth-oauthlib`
- `faster_whisper` is declared; `telegramify_markdown` is declared

These should be added to `requirements.txt` to make installs reproducible.

**Shared internal library:**
- `assistant-shared` (`/opt/assistant-shared`, deps: aiosqlite >=0.20.0, pydantic >=2.0.0) - DB schema migrations, connection helper with `sqlite_lower`, HITL helpers (`assistant_shared.hitl`, used by `src/notifier/bot_handler.py` and `src/brain/git_evaluator.py`), security library (`assistant_shared.security`). It is not declared in `requirements.txt`; it must be installed separately into the venv.

**Infrastructure:**
- stdlib `subprocess`-free async git: `asyncio.create_subprocess_exec` in `src/connectors/git/provider.py` (requires the `git` binary on the host)
- stdlib `sqlite3` - used in a few places alongside aiosqlite
- `zoneinfo` (stdlib) - timezone handling

## Configuration

**Environment:**
- Loaded from `/opt/assistant-core/.env` via `python-dotenv` in `src/config.py`. A `.env` file exists at the repo root (contents intentionally not read); `.env.example` lists the variable names.
- Variable names (values never recorded here):
  - Core: `TZ`, `DEBUG`, `DATABASE_URL` (default `sqlite+aiosqlite:///./data/assistant.db`)
  - Schedule source: `SCHEDULE_URL`, `SCHEDULE_TARGET_ID`, `SCHEDULE_PARAM_NAME`, `SCHEDULE_POLL_INTERVAL_HOURS`
  - Google: `GOOGLE_CREDENTIALS_FILE`, `GOOGLE_TOKEN_FILE`, `GOOGLE_CALENDAR_ID`
  - Telegram: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_USER_ID`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION_PATH`
  - LLM: `GEMINI_API_KEY`, `GEMINI_API_KEYS`, `GEMINI_MODEL`
  - STT: `GROQ_API_KEY`, `WHISPER_MODEL_SIZE`, `WHISPER_DEVICE`, `WHISPER_COMPUTE_TYPE`, `WHISPER_CPU_THREADS`
  - Notion: `NOTION_API_KEY`, `NOTION_TASKS_DB_ID`, `NOTION_PROJECTS_DB_ID`, `NOTION_WAITING_DB_ID`, `NOTION_JOURNAL_DB_ID`
  - Mail: `MAILRU_*`, `GMAIL_*` (EMAIL, PASSWORD, IMAP/SMTP server and port), `ACADEMIC_*` (with legacy `GUAP_*` aliases kept for backward compatibility), `ACADEMIC_IMAP_ENABLED`
  - Materials: `PHYSICS_MATERIALS_BASE_URL`
- Persona: `config/persona.yaml` (declarative user profile and source bindings; loaded by `src/persona/`). Prompts: `config/prompts/*.jinja2`.
- Secrets/credential files present at repo root (existence only): `.env`, `credentials.json` (Google OAuth client), `token.json` (Google OAuth token). Telethon session files live in `data/`.

**Build / tooling config:**
- `pytest.ini`, `.importlinter`, `.githooks/` (pre-commit hooks installed by `scripts/install_hooks.sh`), `.gitignore`
- `Dockerfile`, `docker-compose.yml`

## Data Storage

- SQLite database, default `data/assistant.db` (path resolved relative to repo root in `src/config.py`). Production DB is not described further here.
- Schema and migrations are owned by `/opt/assistant-shared` (CLAUDE.md: assistant-core is schema owner side; chat-app is consumer).
- Telethon session file `data/telethon_userbot.session` and bot session `data/assistant_worker.session` (SQLite-backed).

## Platform Requirements

**Development:**
- Python 3.12 virtualenv at `/opt/assistant-core/.venv`
- Node 20 LTS is installed on the host (CLAUDE.md) but is not used by this Python project
- Git (for `src/connectors/git`)
- Host RAM is constrained (2 GB + 4.5 GB swap per CLAUDE.md); faster-whisper `base` model is chosen for this reason

**Production:**
- Single VPS, systemd service `assistant-worker.service` (or the Docker Compose service `assistant-worker`)
- Outbound network access to Telegram, Google APIs, Gemini API, Groq API, Notion API, IMAP/SMTP hosts, and the GUAP schedule/LMS sites

---

*Stack analysis: 2026-10-09*
