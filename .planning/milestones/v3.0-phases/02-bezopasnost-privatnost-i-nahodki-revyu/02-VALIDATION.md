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
- **Порядок волн 5-10:** планы 02-10, 02-11, 02-12, 02-13, 02-14, 02-15 идут строго по одному (общее рабочее дерево, полные гейты, незакоммиченная правка персоны до чекпоинта 02-11); в каждой волне после 4-й ровно один план

---

## Per-Task Verification Map

Карта «задача -> требование -> тест» (ID задач `02-NN-MM`: номер плана и номер задачи). Команды запускаются из `/opt/assistant-core`, если не указано иное; shared запускается интерпретатором `.venv` assistant-core.

| Task ID | Plan | Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|-------------|----------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | SECF-02 | `scan_file_content`, слова NDA в правиле и web `audit_path` | unit (shared) | `cd /opt/assistant-shared && /opt/assistant-core/.venv/bin/pytest tests/test_scan_file_content.py -p no:cacheprovider -q` | создаётся в задаче | ⬜ pending |
| 02-01-02 | 01 | SECF-02 | CLI-проверки на общей функции; оба потребителя зелёные: полный pytest chat-app, тест assistant-core, аудит shield даёт прежние 3 находки | unit + regression | `cd /opt/assistant-shared && /opt/assistant-core/.venv/bin/pytest tests -p no:cacheprovider -q`, затем `cd /opt/chat-app && backend/.venv/bin/pytest backend/tests -p no:cacheprovider -q`, затем `.venv/bin/pytest tests/test_nda_script_parity.py -p no:cacheprovider -q` | да | ⬜ pending |
| 02-02-01 | 02 | SAFE-01 | текст «очисти диалог» -> предупреждение, история цела | unit | `.venv/bin/pytest tests/test_clear_dialog_text_guard.py tests/test_hitl_safety_guardrails.py -p no:cacheprovider -q` | создаётся в задаче | ⬜ pending |
| 02-02-02 | 02 | SAFE-01 | голос, движок, `/clear` -> карточка, AST-страж | unit | `.venv/bin/pytest tests/test_clear_dialog_text_guard.py tests/test_secretary_dialog.py tests/test_bot_hitl_parity.py -p no:cacheprovider -q` | да | ⬜ pending |
| 02-03-01..03 | 03 | D-17 (CR-01, WR-01, WR-02, WR-12) | безопасный путь, to_thread, удаление архива | unit | `.venv/bin/pytest tests/test_gdrive_client.py -p no:cacheprovider -q` | да | ⬜ pending |
| 02-04-01..02 | 04 | D-17 (WR-08, WR-09) | права каталога копий, запись состояния и отчёта | unit | `.venv/bin/pytest tests/test_deploy_script.py -p no:cacheprovider -q` | да | ⬜ pending |
| 02-05-01..02 | 05 | D-17 (WR-07, WR-11, WR-13) | страж БД, меню, страж правил | unit | `.venv/bin/pytest tests/test_live_db_guard.py tests/test_command_aliases.py tests/test_claude_md_gate_pointer.py -p no:cacheprovider -q` | да | ⬜ pending |
| 02-06-01..03 | 06 | SECF-01, SECF-02 | сопоставление пространств, fail-closed, паритет D-13 | unit + integration (shared) | `cd /opt/assistant-shared && /opt/assistant-core/.venv/bin/pytest tests/test_workspace_matching.py tests/test_shield_parity.py -p no:cacheprovider -v` | создаётся в задаче | ⬜ pending |
| 02-07-01..03 | 07 | SECF-01, SECF-02 | предпроверка на копии, задание chat-app, коммит `/gsd-quick` | regression (chat-app, read-only до чекпоинта) | `cd /opt/chat-app && backend/.venv/bin/pytest backend/tests -p no:cacheprovider -q` | да | ⬜ pending |
| 02-08-01..03 | 08 | SECF-01 | обёртка по данным персоны, fail-closed, без допуска слов и ослабления hook (D-21) | integration (subprocess) | `.venv/bin/pytest tests/test_security_shield_cli.py tests/test_nda_script_parity.py -p no:cacheprovider -q` | создаётся в задаче | ⬜ pending |
| 02-09-01..03 | 09 | D-17 (WR-05, WR-06, T-uo4-02) | задание и коммит chat-app для адаптера cross-AI | regression (chat-app) | `cd /opt/chat-app && backend/.venv/bin/pytest backend/tests/test_agy_cross_ai.py -p no:cacheprovider -q` | да | ⬜ pending |
| 02-10-01..03 | 10 | SECF-01 | предпроверка итогового состояния, делегатор shared, удаление прежних имён, D-10 | unit + regression | `.venv/bin/pytest tests/test_nda_script_parity.py -p no:cacheprovider -q` и pytest shared и chat-app | создаётся в задаче | ⬜ pending |
| 02-11-01..04 | 11 | PRIV-01 | схема `privacy`, `/help` с блоком, данные персоны; чекпоинт владельца и разовый коммит персоны `--no-verify` с указанием пути `--only -- config/persona.yaml` (D-21) | unit + manual checkpoint | `.venv/bin/pytest tests/test_privacy_notice.py tests/test_deploy_script.py::test_help_handler_does_not_touch_db -p no:cacheprovider -q` | создаётся в задаче | ⬜ pending |
| 02-12-01..02 | 12 | PRIV-01 | цикл почты: журнал + одно сообщение + флаг; `auth_google.py`; `.env.example` | unit | `.venv/bin/pytest tests/test_privacy_notice.py tests/test_email_reply_workflow.py -p no:cacheprovider -q` | да | ⬜ pending |
| 02-13-01..03 | 13 | D-17 (WR-03, WR-04, WR-10) | целостность БД, отпечатки строк, герметичные тесты | unit | `.venv/bin/pytest tests/test_gate.py tests/test_gate_red_cases.py -p no:cacheprovider -q` | да | ⬜ pending |
| 02-14-01 | 14 | все | достижимость из рантайма без рестарта | integration | `.venv/bin/pytest tests/test_phase2_reachability.py -p no:cacheprovider -v` | создаётся в задаче | ⬜ pending |
| 02-14-02..03 | 14 | D-17 | закрытие находок по прогнанным тестам, гейт и потребители | gate + regression | `python3 scripts/gate.py` | да | ⬜ pending |
| 02-15-01..04 | 15 | все | рестарт с разрешения владельца, смоук OPS-01, живые проверки | manual-only + deploy smoke | `python3 scripts/deploy.py --restart --report ...` только после «да» владельца | нет | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `/opt/assistant-shared/tests/test_scan_file_content.py` — SECF-02 (создаётся в задаче 02-01-01)
- [ ] `/opt/assistant-shared/tests/test_workspace_matching.py` — SECF-01 (создаётся в задаче 02-06-01)
- [ ] `/opt/assistant-core/tests/test_security_shield_cli.py` — SECF-01 (создаётся в задаче 02-08-01)
- [ ] `/opt/assistant-core/tests/test_clear_dialog_text_guard.py` — SAFE-01 (создаётся в задаче 02-02-01)
- [ ] `/opt/assistant-core/tests/test_privacy_notice.py` — PRIV-01 (создаётся в задаче 02-11-01)
- [ ] Предпроверка задания chat-app против копии библиотеки (`PYTHONPATH`) — задача 02-07-01; повторная предпроверка итогового состояния — задача 02-10-01

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Живая команда `/help` показывает предупреждение | PRIV-01 | Нужен рестарт сервиса по разрешению владельца | После рестарта отправить боту `/help` |
| Текстовое «очисти диалог» живому боту не стирает историю | SAFE-01 | Живой Telegram | Отправить текст, проверить ответ-предупреждение |
| Смоук OPS-01 после рестарта | все | Боевой сервис | `python3 scripts/deploy.py` |
| Разовый коммит `config/persona.yaml` с `--no-verify` | PRIV-01, D-21 | Hook и shield не ослабляются, обход допустим только с согласием владельца на каждый коммит | Чекпоинт плана 02-11 (Task 3, опрос в чате); перед коммитом `scripts/security_shield.py . --all` показывает ровно 3 известные находки в `config/persona.yaml`, в коммите только этот файл (команда с указанием пути `--only -- config/persona.yaml` плюс автоматические проверки Task 4) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 180s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
