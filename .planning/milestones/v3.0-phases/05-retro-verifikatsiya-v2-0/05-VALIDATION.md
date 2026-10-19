---
phase: "05"
slug: "retro-verifikatsiya-v2-0"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-18"
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Фаза не меняет код: «тесты» здесь — прогоны существующих наборов, пробы вне репозиториев и записи в VERIFICATION.md. Источник: 05-RESEARCH.md § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 + pytest-asyncio (`asyncio_mode = auto`), обе venv |
| **Config file** | `/opt/assistant-core/pytest.ini`; у chat-app отдельного нет |
| **Quick run command** | `cd /opt/assistant-core && .venv/bin/pytest tests/test_key_rotator.py tests/test_concurrency_isolation.py tests/test_hitl_safety_guardrails.py -q` |
| **Full suite command** | `cd /opt/assistant-core && python3 scripts/gate.py` |
| **chat-app (только чтение)** | `cd /opt/chat-app && PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/pytest -p no:cacheprovider backend/tests` |
| **Estimated runtime** | гейт ~ несколько минут; DAT-03 30 прогонов строго последовательно |

---

## Sampling Rate

- **После каждой пачки требований:** quick run соответствующих тестов (см. карту ниже).
- **После каждой волны:** `python3 scripts/gate.py` → ЗЕЛЁНЫЙ.
- **Перед `/gsd-verify-work`:** гейт ЗЕЛЁНЫЙ, 30 прогонов DAT-03 записаны.
- **Ограничение ресурсов:** 1 vCPU, ~888 МБ свободно — прогоны не параллелить.

---

## Per-Task Verification Map

Заполняется планировщиком по ID задач. Карта требований → команд:

| Requirement | Test Type | Automated Command | File Exists |
|-------------|-----------|-------------------|-------------|
| DAT-02 | config + журнал | `.venv/bin/pytest tests/test_db_config.py -q`; journalctl «Database initialized at» | ✅ / P-5 зависит от решения владельца |
| DAT-03 | integration ×30 | `backend/tests/test_concurrent_write.py` (chat-app), протокол из RESEARCH | ✅ |
| DAT-04 | strace-проба | P-7 (вне репо) | ❌ W0 |
| SEC-01 | grep + parity | `grep -rn "assistant_shared.security"` | ✅ |
| SEC-02 | parity | `tests/test_nda_script_parity.py`, chat-app `test_shield_parity.py` | ✅ |
| SEC-03 | e2e в tmp-репо | P-8 (вне репо) | ❌ W0 |
| HIT-01 | unit + grep | `.venv/bin/pytest tests/test_hitl_safety_guardrails.py -q` | ✅ |
| ISO-01 | unit | `.venv/bin/pytest tests/test_key_rotator.py -k no_global_config_mutation -q` | ✅ |
| ISO-02 | trap | `.venv/bin/pytest tests/test_airgap_trap.py tests/test_nda_script_parity.py -q` | ✅ |
| ISO-03 | unit | `.venv/bin/pytest tests/test_phase4_reachability.py tests/test_ports_conformance.py -q` | ✅ |
| ISO-04 | integration | `.venv/bin/pytest tests/test_concurrency_isolation.py -q` | ✅ |
| FIN-01 | unit + Read | `.venv/bin/pytest tests/test_hardcode_scanner.py -q` | ✅ |
| ACT-01 | e2e | `.venv/bin/pytest tests/test_tool_calling_e2e.py tests/test_secretary_tools.py -q` | ✅ |
| ACT-02 | snapshot | `.venv/bin/pytest tests/test_prompt_snapshot.py -q` | ✅ |
| ACT-03 | e2e | `.venv/bin/pytest tests/test_hitl_telegram_cards.py -q` | ✅ |
| ACT-04 | unit | `.venv/bin/pytest tests/test_fast_intent_router.py -q` | ✅ |
| UXQ-01 | журнал | journalctl «Successfully registered»; `tests/test_bot_menu.py` | ✅ |
| UXQ-02 | unit | `.venv/bin/pytest tests/test_command_aliases.py tests/test_command_registry.py -q` | ✅ |
| UXQ-04 | unit + grep | `grep -rn "send_connector_health_alert(" src` | ✅ |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Каталог логов и проб вне репозиториев (scratchpad).
- [ ] Проба strace P-7 (DAT-04) — вне репозитория.
- [ ] Проба pre-commit hook P-8 (SEC-03) — во временном git-репо.
- [ ] Решение владельца по P-5 (DAT-02, путь БД chat-app).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Путь БД chat-app в рантайме | DAT-02 | chat-app.service неактивен; P-5 читает `.env` | по решению владельца |
| Поведение LLM по правилу промпта | ACT-02 | недетерминировано | вердикт по тексту промпта и снимку |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency acceptable
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
