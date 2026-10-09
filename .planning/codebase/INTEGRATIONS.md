---
last_mapped_commit: 5997ad6c8c219390ead42ea5132f2660f488f15d
last_mapped_at: 2026-10-09
---
# External Integrations

**Analysis Date:** 2026-10-09

## APIs & External Services

**LLM (Google Gemini):**
- Google Generative AI via `google-genai` SDK - summarization, reply drafting, methodist scope checks, debrief parsing, intent routing, secretary dialog with tool calling
  - SDK/Client: `google-genai` (`from google import genai`), wrapped in `src/brain/key_rotator.py`
  - Model: `GEMINI_MODEL` (default `gemini-3.5-flash-lite`); tool schemas in `src/brain/tools_schema.py`
  - Auth: `GEMINI_API_KEY` or `GEMINI_API_KEYS` (comma-separated, rotated on failure)
  - Prompts: `config/prompts/*.jinja2`

**Speech-to-text (Groq):**
- Groq hosted Whisper endpoint `https://api.groq.com/openai/v1/audio/transcriptions` (model `whisper-large-v3-turbo`)
  - Implementation: raw HTTP with bearer auth in `src/brain/voice.py` (`_transcribe_groq`)
  - Auth: `GROQ_API_KEY`
  - Fallback: local faster-whisper (`WHISPER_*` env vars), also in `src/brain/voice.py`

**Telegram:**
- Bot API via aiogram - interactive bot, notifications, inline HITL cards
  - Client: `aiogram` (`src/notifier/bot_handler.py`, `src/notifier/telegram.py`, `src/notifier/live_ticker.py`)
  - Auth: `TELEGRAM_BOT_TOKEN`; restricted to owner via `TELEGRAM_USER_ID`
- MTProto user client via Telethon - collects messages from Telegram chats (`src/collector/tg_collector.py`)
  - Auth: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, session file at `TELEGRAM_SESSION_PATH` (default `data/assistant_worker.session`); helper script `scripts/auth_telethon.py`

**Google Workspace:**
- Google Calendar API - schedule events sync (`src/calendar/client.py`, `GoogleCalendarClient`); scopes `https://www.googleapis.com/auth/calendar` and `.../calendar.events`; calendar ID `GOOGLE_CALENDAR_ID` (default `primary`)
- Google Drive API - file access (`src/connectors/gdrive/client.py`, `GoogleDriveClient`); scope `https://www.googleapis.com/auth/drive`
- Gmail API (read) - email collection via `googleapiclient` in `src/collector/email_collector.py`; scope `https://www.googleapis.com/auth/gmail.readonly`
  - Auth for all three: OAuth 2.0 installed-app flow. Client secrets in `credentials.json` (`GOOGLE_CREDENTIALS_FILE`), user token in `token.json` (`GOOGLE_TOKEN_FILE`). Setup via `scripts/auth_google.py`. Both files are mounted read-only/read-write in `docker-compose.yml`.

**Notion:**
- Notion REST API `https://api.notion.com/v1` - task, project, waiting-for and journal databases ("Second Brain")
  - Client: `src/connectors/notion/client.py` (httpx), schema in `src/connectors/notion/schema.py`
  - Auth: `NOTION_API_KEY`; database IDs `NOTION_TASKS_DB_ID`, `NOTION_PROJECTS_DB_ID`, `NOTION_WAITING_DB_ID`, `NOTION_JOURNAL_DB_ID`
  - Provisioning scripts: `scripts/provision_notion.py`, `scripts/notion_dev.py`, `scripts/provision_dev_roadmap.py`
  - HITL-gated writes covered by `tests/test_notion_git_hitl.py`

**University LMS (GUAP, persona-bound):**
- Professor LMS at `https://pro.guap.ru` (base URL from `config/persona.yaml`, `lms` connector binding) - list submitted reports and task details, poll every cycle (`lms_monitor_job` in `src/main.py`)
  - Client: `src/connectors/guap_lms/client.py` (requests/httpx-based HTTP scraping), provider in `src/connectors/guap_lms/provider.py`
  - Auth: university account credentials via env (`ACADEMIC_*` / legacy `GUAP_*` names); the LMS password variable is distinct from the mail password
  - Composition: resolved lazily via `default_lms_client()` in `src/composition.py`, which checks persona scopes first
- Schedule source: `https://guap.ru/rasp` (persona `schedule_source` binding, `config/persona.yaml`) overridable by `SCHEDULE_URL`; target ID `SCHEDULE_TARGET_ID` (default `2903`), parameter name `SCHEDULE_PARAM_NAME` (default `pr`), polled every `SCHEDULE_POLL_INTERVAL_HOURS` (default 2). Parsed by `src/parser/schedule_parser.py`, changes detected by `src/detector/diff.py`.

**Timesheet (AADHk, Tydex-specific):**
- Work-hours ingestion from spreadsheets/Drive files: `src/connectors/aadhk/parser.py`, `src/connectors/aadhk/provider.py`, `src/parser/`; triggered from `src/main.py` alongside the Drive client
- Uses `GoogleDriveClient` for file retrieval (no separate API key)

**Git hosting:**
- Git repositories accessed through the local `git` binary via `asyncio.create_subprocess_exec` (`src/connectors/git/provider.py`), no GitHub REST client found. Remote URLs appear only in tests and docs. Security checks (NDA air-gap, remote origin verification) in `src/security/airgap.py`.

**Email (IMAP/SMTP):**
- Mail.ru, Gmail and the academic mailbox over IMAP (`imapclient`, undeclared in requirements) for collection (`src/collector/email_collector.py`) and SMTP for sending replies (`src/sender/email_sender.py`, stdlib `smtplib`)
  - Hosts (defaults in `src/config.py`): `imap.mail.ru:993`, `smtp.mail.ru:587`, `imap.gmail.com:993`, `smtp.gmail.com:587`, academic IMAP/SMTP default under the university domain
  - Auth: `MAILRU_PASSWORD`, `GMAIL_PASSWORD`, `ACADEMIC_PASSWORD` (app passwords expected); toggle `ACADEMIC_IMAP_ENABLED`
  - Gmail also has the OAuth Gmail API path above

**Physics course materials:**
- `PHYSICS_MATERIALS_BASE_URL` - source for `scripts/download_fizikaguap_materials.py` (downloads course files via `requests`)

## Data Storage

**Databases:**
- SQLite only
  - Connection: `DATABASE_URL` (default `sqlite+aiosqlite:///./data/assistant.db`), resolved by `src/config.py`
  - Client: `aiosqlite` through `assistant_shared.db.connection.get_async_connection` and `sqlite_lower`; wrapper class `Database` in `src/storage/db.py`
  - Migrations: `assistant_shared.db.migrator.run_migrations` (SQL files in `/opt/assistant-shared/assistant_shared/db/migrations/`); assistant-core is the schema owner
  - Note: the production database file must not be opened by analysis or tooling outside the service

**File Storage:**
- Local filesystem only: `data/` (DB, Telethon sessions, benchmarks, `reconcile_report.json`, methodist data), `config/prompts/`, `config/persona.yaml`
- Docker: `./data` bind-mounted to `/app/data`

**Caching:**
- None (no Redis/memcached). In-process caches only: `genai.Client` instances in `src/brain/key_rotator.py`, live ticker state in `src/notifier/live_ticker.py`

## Authentication & Identity

**Auth Provider:**
- No end-user auth service. Access control is by Telegram identity: the bot only responds to `TELEGRAM_USER_ID`.
- Google: OAuth 2.0 installed-app flow (`credentials.json` + `token.json`)
- Telegram user client: Telethon session file
- Implementation: credentials loaded from environment and files in `src/config.py`; HITL confirmation cards in `src/notifier/bot_handler.py` via `assistant_shared.hitl`

## Monitoring & Observability

**Error Tracking:**
- None detected (no Sentry or similar SDK)

**Logs:**
- Python `logging` module in `src/main.py` and modules; `DEBUG` env toggles verbosity
- Reports: `data/reconcile_report.json`

## CI/CD & Deployment

**Hosting:**
- Self-hosted single VPS; systemd unit `assistant-worker.service` (CLAUDE.md), or Docker Compose service `assistant-worker` (`docker-compose.yml`, `restart: unless-stopped`)

**CI Pipeline:**
- None detected in-repo (no `.github/workflows`). Local gates: pytest suites, import-linter (`.importlinter`), `scripts/security_shield.py`, git hooks in `.githooks/` installed by `scripts/install_hooks.sh`

## Environment Configuration

**Required env vars (names only):**
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_USER_ID` - bot operation
- `GEMINI_API_KEY` or `GEMINI_API_KEYS` - all LLM features
- `GOOGLE_CREDENTIALS_FILE`, `GOOGLE_TOKEN_FILE` - Calendar, Drive, Gmail
- `DATABASE_URL` - optional, defaults to local SQLite
- Optional per feature: `NOTION_*`, `GROQ_API_KEY`, `MAILRU_*`, `GMAIL_*`, `ACADEMIC_*`, `SCHEDULE_*`, `WHISPER_*`

**Secrets location:**
- `/opt/assistant-core/.env` (dotenv, loaded with override in `src/config.py`) - exists, not read for this document
- `/opt/assistant-core/credentials.json` (Google OAuth client, mode 600) and `/opt/assistant-core/token.json` (OAuth token) - exist, not read
- `data/*.session` - Telethon sessions
- Template of variable names: `.env.example`

## Webhooks & Callbacks

**Incoming:**
- None detected. The Telegram bot uses long polling via aiogram (no webhook server). No HTTP route handlers found in `src/`.

**Outgoing:**
- Telegram Bot API messages and inline cards (`src/notifier/`)
- SMTP email replies (`src/sender/email_sender.py`)
- Calendar event create/update (`src/calendar/client.py`)
- Notion page writes (`src/connectors/notion/client.py`), HITL-gated

---

*Integration audit: 2026-10-09*
