# Milestones

## v3.0 Стабилизация платформы и онбординг (Shipped: 2026-10-19)

**Phases completed:** 5 phases (1–5), 52 plans, 55 tasks
**Timeline:** 2026-10-09 → 2026-10-19
**Closeout type:** override_closeout — закрыта как есть по решению владельца 2026-10-19
**Archive:** `milestones/v3.0-ROADMAP.md`, `milestones/v3.0-REQUIREMENTS.md`, `milestones/v3.0-phases/`

**Delivered:** Собственный гейт качества и процедура выкатки, ужесточённая безопасность (NDA-режим из данных, «очисти диалог» только через HITL, предупреждение PRIV-01), владение схемой БД в assistant-shared, цепочка Git → оценка → HITL → Notion в рантайме и ретро-верификация v2.0 с переводом найденных gaps в бэклог.

**Key accomplishments:**
- Собственный гейт `python3 scripts/gate.py` (assistant-core + assistant-shared, 10 строк, ЗЕЛЁНЫЙ/КРАСНЫЙ), страж боевой БД в тестах, hook и тесты assistant-shared; `scripts/deploy.py` (read-only смоук, `--backup`/`--restart` по флагу) и `docs/OPS_DEPLOY.md` (Phase 1).
- NDA-режим и аудит безопасности из данных рабочих пространств, паритет web/CLI, «очисти диалог» только через `/clear` с HITL-карточкой, предупреждение PRIV-01; закрыты 14 находок ревью, включая path traversal Google Drive (Phase 2).
- Миграция `0003` в assistant-shared и единый неблокирующий путь миграций для файловой и `:memory:` БД, проверка на копии боевой БД, выкатка со смоуком (Phase 3).
- Оценка хода проектов по git достижима из планировщика и команды `/git`, запись в Notion только после HITL-подтверждения, fail-closed допуск (Phase 4).
- Ретро-верификация фаз 4–9 v2.0: 9 требований passed, 10 gap; каждый gap оформлен записью бэклога 999.3–999.16 (Phase 5).

**Known verification overrides:** 5 newly acknowledged, 0 carried forward from a prior close (see STATE.md Deferred Items).

### Known Gaps

- VERIFICATION.md фаз 1–3 устарели (stale), фаза 4 — human_needed → бэклог 999.19.
- Требования UXQ-03, GEN-01, ONB-01, ONB-02, ONB-03 не выполнены: фазы 6–8 перенесены в бэклог 999.20–999.22.
- Фазы 05.1–05.3 (вставлены 2026-10-19) не начаты; переходят во входные данные новой вехи «Автономный секретарь» (`.planning/notes/v3.0-carryover-phases-05.x.md`, `.planning/notes/proactive-owner-picture.md`).
- Gaps ретро-верификации v2.0 (DAT-02/03/04, ISO-02/03/04, ACT-03, UXQ-01/02/04, HIT-05) — бэклог 999.3–999.16.

---
