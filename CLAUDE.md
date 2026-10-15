# CLAUDE.md: Antigravity Studio & Assistant Platform Guidelines

## 1. Project Overview & Architecture
This project is an advanced AI Agent IDE and Autonomous Assistant platform consisting of two complementary components:

1. **Antigravity Studio (`/opt/chat-app`):**
   - **Backend:** Python 3.12, FastAPI, Uvicorn, SQLite (`data/chat.db`), REST API v1, WebSocket streaming.
   - **Frontend:** Modern Web UI (HTML5, Tailwind CSS, Lucide Icons, interactive consoles, real-time metrics).
   - **Key Features:** Multi-project GitHub orchestration (personal vs corporate), visual Security Tiles (NDA air-gaps, secret leak scanning, remote origin verification), document editing, task tracking.

2. **Assistant Core (`/opt/assistant-core`):**
   - **Engine:** Python 3.12 daemon running 24/7 via `systemd` (`assistant-worker.service`).
   - **Interfaces:** Interactive Telegram bot (`@opd_guap_popov_bot`), fast intent routing (Gemini 3.5/3.6/3.8 Flash), speech-to-text voice analysis.
   - **Data Layer:** SQLite (`assistant.db`), transactional storage, conversational memory with HITL (Human-in-the-Loop) safeguards.

## 2. Core Strategic Goal: Generalization & Universalization
**Current State:** Highly effective but customized for a specific academic/industrial workflow (Associate Professor in Physics at GUAP + Optical Instrument Researcher at Tydex LLC).
**Target State:** Refactor into a **universal, general-purpose platform** suitable for any knowledge worker, developer, researcher, or educator.

### Key Refactoring Directives:
1. **Plugin / Connector Architecture:**
   - Abstract domain-specific integrations (GUAP LMS, Tydex AADHk timesheet) into modular plugins inheriting from `BaseConnector` or `BasePlugin`.
   - Core daemon must operate purely on abstract entities: `ScheduleEvent`, `WorkRecord`, `AcademicSubmission`, `EmailMessage`, `Task`.
2. **Configuration-Driven Personas:**
   - User profile and domain rules should live in declarative configuration files (`config/persona.yaml` or user preferences in SQLite), not hardcoded in business logic.
3. **White-Label Web UI:**
   - Keep the Security Tiles, Git Registry, and Task Dashboard adaptable for any combination of personal, academic, or corporate workspaces.
4. **Zero Regression & Safety First:**
   - Maintain 100% test pass rate across pytest suites.
   - Enforce HITL (Human-in-the-Loop) gates for any destructive action (memory wipes, data deletion).
   - Enforce strict Air-Gap isolation for corporate/NDA workspaces.

## 3. Development Commands & Environment
- **Node.js Environment:** Node 20 LTS installed. When running Node/Claude commands, use `NODE_OPTIONS="--max-old-space-size=1536"` to respect VPS RAM (2 GB + 4.5 GB Swap).
- **Run Backend Tests (`chat-app`):**
  ```bash
  /opt/chat-app/backend/.venv/bin/pytest backend/tests
  ```
- **Run Daemon Tests (`assistant-core`):**
  ```bash
  /opt/assistant-core/.venv/bin/pytest /opt/assistant-core/tests
  ```
- **Run Security Scan:**
  ```bash
  /opt/assistant-core/.venv/bin/python3 scripts/security_shield.py
  ```
- **Run Quality Gate:** run `python3 scripts/gate.py` from `/opt/assistant-core` — the own gate of this repo. It checks assistant-core (pytest, import-linter, security_shield with the frozen list of known false positives, drift of `synthetic_persona.py` and `persona_tokens.py` against the chat-app copies read-only, SHA-256 of the live DB before and after pytest, pre-commit hook installed) and assistant-shared (pytest, security_shield, hook installed); exit 0 = «ЗЕЛЁНЫЙ». The chat-app gate stays unchanged as the consumer's gate (D-15) and is not the way to check assistant-core.
- **Deploy / smoke check:** `python3 scripts/deploy.py` runs a read-only smoke check of `assistant-worker`; `--backup` and `--restart` only with explicit owner permission (procedure in `docs/OPS_DEPLOY.md`).
- **Restart Services (if modified):** restart `assistant-worker.service` only with explicit owner permission, via `python3 scripts/deploy.py --restart` (see `docs/OPS_DEPLOY.md`). The `chat-app.service` line is unchanged:
  ```bash
  systemctl restart chat-app.service
  ```

## 4. Coding Standards & Conventions
- **Language:** Code, comments, commits, and PR descriptions in English or Russian. User-facing outputs strictly Russian.
- **KISS & YAGNI:** Avoid over-engineering; prefer clear, typed dataclasses and Pydantic models.
- **Asyncio:** Async-first for all I/O, database interactions (`aiosqlite`), and network requests (`httpx`, `aiohttp`).

## 5. GSD Project & Delegation (since 2026-10-09)
- **Own GSD project:** assistant-core is planned in its own `/opt/assistant-core/.planning/` (owner decision 2026-10-09). The chat-app planning (`/opt/chat-app/.planning/`, milestone v2.0 archived) is frozen and is history/reference only: `milestones/v2.0-*`, `MILESTONES.md`, `RETROSPECTIVE.md`, `BACKLOG.md` (section «Перенесено в отдельный GSD-проект assistant-core» = starting backlog).
- **Shared code:** `/opt/assistant-shared` owns the DB schema (migrations) and the security library; assistant-core is the schema owner side, chat-app is a consumer. Changes to chat-app only via small `/gsd-quick` tasks there.
- **Delegate token-heavy routine to Antigravity agents** only via the jail wrapper in chat-app: `/opt/chat-app/scripts/agy_task.sh run --repo /opt/assistant-core --mode read|edit <<< "<task>"` (see `/opt/chat-app/.claude/skills/agy-delegate/SKILL.md`). Never run `agy` directly. The jail has no git history and no `.venv`/DB — tasks needing `git log`/tests stay with Claude.
  **Default routing (owner decision 2026-10-09, no need to ask):** bulk reading/inventories/log summaries, boilerplate code and test drafts, docs/translation, uniform edits across ≥4 files → agy. Always Claude: research, discuss/planning, architecture, security/NDA/HITL logic, code review, verification, edits of 1–3 files. Claude reads the full patch, runs the gate, commits.
- **Phase hygiene (lesson from v2.0):** a phase is closed only with SUMMARY.md written in the same run and a VERIFICATION.md that checks the feature is reachable from the runtime (not just unit-tested).

## 6. Режим жёсткой экономии токенов (решение владельца 2026-10-15)
- Все агенты GSD переведены на **Haiku**, кроме планировщиков (`gsd-planner`, `gsd-roadmapper`: Sonnet по решению владельца 2026-10-15): `.planning/config.json` → `model_profile: budget`, `models.*: haiku`, `model_overrides` для всех `gsd-*` агентов (в том числе планировщик, исполнитель, верификатор, ревьюер кода, security-аудитор). Риски снижения качества владелец принял на себя.
- Субагенты Antigravity (agy): по умолчанию самая лёгкая модель (`flash`), повышать только по явной команде владельца.
- Это не отменяет правил безопасности: HITL, Air-Gap NDA, 100% тестов и `python3 scripts/gate.py` обязательны независимо от модели. Результаты Haiku-агентов проверяет гейт, а не доверие к модели.
- Основная сессия Claude Code переключается отдельно командой `/model`; конфиг GSD её не меняет.
- Вернуть качество: `model_profile: balanced` и удалить `models` и `model_overrides` из `.planning/config.json`.
