# Onboarding Summary

## Project State
- PROJECT.md: present
- REQUIREMENTS.md: present
- ROADMAP.md: present
- STATE.md: present

## Codebase Context
- Brownfield repo: yes
- Map readiness: complete
- Codebase map: .planning/codebase/ (complete codebase map)
- Fast map available: yes

## Docs Context
- Existing ADR/PRD/SPEC/RFC candidates: 1 (`docs/SPEC_PHASE_1.md` — skipped by owner: legacy spec of an already implemented schedule module; v2.0 history from `/opt/chat-app/.planning/` used instead)

## Owner Decisions (2026-10-09)
- Milestone v3.0, phases numbered from 1, thematic phases (order: gate → security → schema → runtime chains → v2.0 retro-verification → quick actions → onboarding).
- From backlog initiatives only ONB-01..03 enter v3.0; NDA mail work deferred (NDAM-01), user warning PRIV-01 instead.
- Cross-AI execution via `/opt/chat-app/scripts/agy_cross_ai.sh --repo /opt/assistant-core` — smoke run 2026-10-09: rc 0, gate ZELENYJ (421 tests), patch left uncommitted and removed.
- Services stay frozen; restart only after a phase, on explicit owner approval, with smoke check.

## Recommended Next Step
- /gsd-manager
