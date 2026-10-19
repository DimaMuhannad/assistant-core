---
phase: "04"
slug: tsepochka-git-otsenka-hitl-notion
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-11"
---

# Phase 04 — Validation Strategy

> Контракт проверки фазы 4 (цепочка git → оценка → HITL → Notion). Источник: раздел «Validation Architecture» в 04-RESEARCH.md.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode = auto`) |
| **Config file** | `/opt/assistant-core/pytest.ini` (`testpaths = tests`, `pythonpath = .`) |
| **Quick run command** | `.venv/bin/pytest tests/test_git_chain.py tests/test_notion_git_hitl.py tests/test_git_airgap_trap.py tests/test_git_connector.py -q` |
| **Full suite command** | `python3 scripts/gate.py` |
| **Estimated runtime** | ~30 s (быстрый прогон), гейт дольше |

---

## Sampling Rate

- **After every task commit:** `pytest <файлы задачи> -x -q`
- **After every plan wave:** `python3 scripts/gate.py`
- **Before `/gsd-verify-work`:** гейт ЗЕЛЁНЫЙ
- **Max feedback latency:** 60 секунд на задачу

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-GIT-01 | 04-08 (+04-01) | 4 (+1) | GIT-01 | — | оценщик собирается по привязке и scope `git.read`, вызывается из `main()` | unit + ast | `pytest tests/test_phase4_reachability.py -k composition -x` | ❌ W0 | ⬜ pending |
| 04-GIT-02 | 04-06 (+04-01, 04-05) | 2 (+1, 2) | GIT-02 | — | нет remote / каталога / `.git` → статус-строка, ни LLM, ни Notion | unit | `pytest tests/test_git_chain.py -k skipped -x` | ❌ W0 | ⬜ pending |
| 04-GIT-03 | 04-06, 04-08, 04-09 | 2, 4, 4 | GIT-03 | — | `/git` по-русски, задача в расписании, запасной шаблон при сбое LLM | unit + ast | `pytest tests/test_git_chain.py tests/test_phase4_reachability.py -x` | ❌ W0 | ⬜ pending |
| 04-GIT-04 | 04-10 (+04-01, 04-05) | 5 (+1, 2) | GIT-04 | NDA air-gap | NDA / неизвестный допуск / ошибка персоны → ноль вызовов git, LLM, Notion | integration (ловушки) | `pytest tests/test_git_chain_airgap.py -x` | ❌ W0 | ⬜ pending |
| 04-NTN-01 | 04-07 (+04-08) | 3 (+4) | NTN-01 | — | обработчик `notion_project_sync` зарегистрирован; нет ID → «Notion не настроен» | unit | `pytest tests/test_git_chain.py -k notion -x` | ❌ W0 | ⬜ pending |
| 04-NTN-02 | 04-10 (+04-01, 04-07, 04-09) | 5 (+1, 3, 4) | NTN-02 | HITL | запись в Notion только после подтверждения; отклонение → 0 вызовов; повтор → 1 запись | integration | `pytest tests/test_phase4_chain_e2e.py -x` | ❌ W0 | ⬜ pending |
| 04-SHARED | 04-02 | 1 | GIT-04 / NTN-02 | — | `reopen_action`, `find_confirmations` в assistant-shared | unit | `/opt/assistant-core/.venv/bin/pytest /opt/assistant-shared/tests/test_hitl_shared.py -x` | ✅ файл есть | ⬜ pending |
| 04-REG | 04-09 | 4 | — | — | счётчики команд 9→10, ожидания NDA-карточек переписаны | unit | `pytest tests/test_command_registry.py tests/test_bot_menu.py tests/test_notion_git_hitl.py -x` | ✅ править | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_git_chain.py` — статусы пространств, LLM/запасной шаблон, `stagnation_days`, идемпотентность ключа, валидация ID Notion
- [ ] `tests/test_git_chain_airgap.py` — ловушки LLM/git/Notion на путях `handle_cmd_git` и `run_git_progress_cycle`
- [ ] `tests/test_phase4_reachability.py` — ast `main.py` (`add_job` с `id="git_progress_job"`), регистрация `Command("git")`, колбэков `ntn:*`
- [ ] `tests/test_phase4_chain_e2e.py` — сквозной сценарий на `tmp_path` с `run_migrations`
- [ ] Тесты `reopen_action` / `find_confirmations` в `/opt/assistant-shared/tests/test_hitl_shared.py`

Новых фикстур в `conftest.py` не нужно; страж боевой БД `tests/live_db_guard.py` действует автоматически.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Живой смоук после рестарта `assistant-worker` | GIT-03 | рестарт только с явного разрешения владельца | `python3 scripts/deploy.py` (read-only смоук); в журнале «Added job … run_git_progress_cycle»; `/git` отвечает |

---

## Validation Sign-Off

- [ ] У всех задач есть `<automated>` проверка или зависимость от Wave 0
- [ ] Нет 3 подряд задач без автоматической проверки
- [ ] Wave 0 покрывает все MISSING-ссылки
- [ ] Нет watch-флагов
- [ ] Задержка обратной связи < 60 с
- [ ] `nyquist_compliant: true` в frontmatter

**Approval:** pending
