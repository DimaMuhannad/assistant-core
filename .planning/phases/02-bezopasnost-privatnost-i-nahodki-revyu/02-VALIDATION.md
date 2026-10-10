---
phase: "02"
slug: "bezopasnost-privatnost-i-nahodki-revyu"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-10"
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Источник: `02-RESEARCH.md` §«Validation Architecture».

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8 + pytest-asyncio (`asyncio_mode = auto`) |
| **Config file** | `/opt/assistant-core/pytest.ini`; shared — `[tool.pytest.ini_options]` в `/opt/assistant-shared/pyproject.toml` |
| **Quick run command** | `cd /opt/assistant-core && .venv/bin/pytest <файл> -p no:cacheprovider -v` |
| **Shared suite** | `cd /opt/assistant-shared && /opt/assistant-core/.venv/bin/pytest tests -p no:cacheprovider -q` |
| **Consumer check (chat-app, read-only)** | `cd /opt/chat-app && backend/.venv/bin/pytest backend/tests -p no:cacheprovider -q` |
| **Full suite command** | `cd /opt/assistant-core && python3 scripts/gate.py` (ожидается «ИТОГ: ЗЕЛЁНЫЙ») |
| **Estimated runtime** | ~180 seconds (гейт целиком) |

---

## Sampling Rate

- **After every task commit:** `.venv/bin/pytest <изменённые тесты> -p no:cacheprovider -v`
- **After every plan wave:** shared suite, затем consumer check chat-app, затем `python3 scripts/gate.py`
- **Before `/gsd-verify-work`:** гейт ЗЕЛЁНЫЙ и полный pytest chat-app зелёный
- **Max feedback latency:** 180 seconds

---

## Per-Task Verification Map

Заполняется после планирования (ID задач `02-NN-MM`). Карта «требование → тест»:

| Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|----------|-----------|-------------------|-------------|--------|
| SECF-01 | Нет «tydex»/литерала аккаунта в `assistant_shared/security`; тест не читает литерал из исходника | unit | `.venv/bin/pytest tests/test_nda_script_parity.py -p no:cacheprovider -v` | переписать | ⬜ pending |
| SECF-01 | Сопоставление репозитория с пространством; `workspaces=None` → rc 1 (D-20) | unit (shared) | `cd /opt/assistant-shared && /opt/assistant-core/.venv/bin/pytest tests/test_workspace_matching.py -p no:cacheprovider -v` | ❌ W0 | ⬜ pending |
| SECF-01 | Обёртка CLI с временной персоной, fail-closed | integration | `.venv/bin/pytest tests/test_security_shield_cli.py -p no:cacheprovider -v` | ❌ W0 | ⬜ pending |
| SECF-02 | Паритет `audit_path`/`audit_repository` на синтетических фикстурах | integration (shared) | `cd /opt/assistant-shared && /opt/assistant-core/.venv/bin/pytest tests/test_shield_parity.py -p no:cacheprovider -v` | расширить | ⬜ pending |
| SECF-02 | `scan_file_content` (построчно, многострочно, дедупликация, casefold) | unit (shared) | `cd /opt/assistant-shared && /opt/assistant-core/.venv/bin/pytest tests/test_scan_file_content.py -p no:cacheprovider -v` | ❌ W0 | ⬜ pending |
| SECF-01/02 | Потребитель chat-app зелёный | regression | `cd /opt/chat-app && backend/.venv/bin/pytest backend/tests -p no:cacheprovider -q` | ✅ | ⬜ pending |
| SAFE-01 | Текст/голос/движок не меняют историю, выдают предупреждение с `/clear` | unit | `.venv/bin/pytest tests/test_clear_dialog_text_guard.py -p no:cacheprovider -v` | ❌ W0 | ⬜ pending |
| SAFE-01 | `/clear` → карточка; подтверждение/отмена/восстановление | unit | `.venv/bin/pytest tests/test_hitl_safety_guardrails.py tests/test_bot_hitl_parity.py tests/test_secretary_dialog.py -p no:cacheprovider -v` | ✅ (переписать clear_command) | ⬜ pending |
| PRIV-01 | `/help` с текстом из персоны, без БД | unit | `.venv/bin/pytest tests/test_privacy_notice.py tests/test_deploy_script.py::test_help_handler_does_not_touch_db -p no:cacheprovider -v` | ❌ W0 | ⬜ pending |
| PRIV-01 | Первый цикл почты: журнал + одно сообщение + флаг в `daily_primed_context` (D-19) | unit | `.venv/bin/pytest tests/test_privacy_notice.py tests/test_email_reply_workflow.py -p no:cacheprovider -v` | ❌ W0 | ⬜ pending |
| CR-01, WR-*, T-uo4-02 | Регрессионный тест на каждую закрытую находку ревью (D-17) | unit | по плану | ❌ W0 | ⬜ pending |
| все | Гейт ЗЕЛЁНЫЙ, находки shield не выросли | gate | `python3 scripts/gate.py` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `/opt/assistant-shared/tests/test_scan_file_content.py` — SECF-02
- [ ] `/opt/assistant-shared/tests/test_workspace_matching.py` — SECF-01
- [ ] `/opt/assistant-core/tests/test_security_shield_cli.py` — SECF-01
- [ ] `/opt/assistant-core/tests/test_clear_dialog_text_guard.py` — SAFE-01
- [ ] `/opt/assistant-core/tests/test_privacy_notice.py` — PRIV-01
- [ ] Предпроверка задания chat-app против копии библиотеки (`PYTHONPATH`)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Живая команда `/help` показывает предупреждение | PRIV-01 | Нужен рестарт сервиса по разрешению владельца | После рестарта отправить боту `/help` |
| Текстовое «очисти диалог» живому боту не стирает историю | SAFE-01 | Живой Telegram | Отправить текст, проверить ответ-предупреждение |
| Смоук OPS-01 после рестарта | все | Боевой сервис | `python3 scripts/deploy.py` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 180s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
