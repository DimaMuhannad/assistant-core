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
- **Restart Services (if modified):**
  ```bash
  systemctl restart chat-app.service
  systemctl restart assistant-worker.service
  ```

## 4. Coding Standards & Conventions
- **Language:** Code, comments, commits, and PR descriptions in English or Russian. User-facing outputs strictly Russian.
- **KISS & YAGNI:** Avoid over-engineering; prefer clear, typed dataclasses and Pydantic models.
- **Asyncio:** Async-first for all I/O, database interactions (`aiosqlite`), and network requests (`httpx`, `aiohttp`).
