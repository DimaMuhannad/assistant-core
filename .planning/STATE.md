---
gsd_state_version: "1.0"
milestone: v3.0
milestone_name: Стабилизация платформы и онбординг
current_phase: 02
current_phase_name: Безопасность, приватность и находки ревью
status: executing
stopped_at: Completed 02-05-PLAN.md
last_updated: "2026-10-10T12:34:43.141Z"
last_activity: 2026-10-10
last_activity_desc: Phase 02 execution started
state_head: 0c52a71d4b7822f4c9a623142d2c962ff8055920
progress:
  total_phases: 9
  completed_phases: 1
  total_plans: 25
  completed_plans: 15
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-10)

**Core value:** Ассистент надёжно выполняет ежедневную работу секретаря. Ни одно содержимое NDA-пространств не уходит во внешнюю LLM, и ни одно необратимое действие не выполняется без подтверждения человека (HITL).
**Current focus:** Phase 02 — Безопасность, приватность и находки ревью

## Current Position

Phase: 02 (Безопасность, приватность и находки ревью) — EXECUTING
Plan: 6 of 15
Status: Ready to execute
Last activity: 2026-10-10 — Phase 02 execution started

Progress: [█░░░░░░░░░] 11%

## Performance Metrics

**Velocity:**
- Total plans completed: 10
- Average duration: -
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 10 | - | - |

**Recent Trend:**
- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 01 P01 | 25 min | 3 tasks | 7 files |
| Phase 01 P02 | 12 min | 3 tasks | 6 files |
| Phase 01 P06 | 35 min | 3 tasks | 2 files |
| Phase 01 P03 | 2 min | 2 tasks | 5 files |
| Phase 01 P04 | 19 min | 3 tasks | 2 files |
| Phase 01 P07 | 21 min | 3 tasks | 3 files |
| Phase 01 P05 | 10 min | 3 tasks | 3 files |
| Phase 01 P08 | 9 min | 3 tasks | 8 files |
| Phase 01 P09 | 126 min | 3 tasks | 3 files |
| Phase 01 P10 | 15 min | 3 tasks | 2 files |
| Phase 02 P01 | 25min | 2 tasks | 5 files |
| Phase 02 P02 | 40min | 2 tasks | 6 files |
| Phase 02 P03 | 45min | 3 tasks | 2 files |
| Phase 02 P04 | n/a | 2 tasks | 3 files |
| Phase 02 P05 | 30min | 2 tasks | 4 files |

## Accumulated Context

### Decisions

Полный журнал решений — в таблице Key Decisions файла PROJECT.md.
Решения, влияющие на текущую работу:

- [Roadmap]: Порядок фаз выбран владельцем (вариант A): гейт → безопасность → схема БД → сквозные цепочки → ретро-верификация → UXQ-03 → онбординг.
- [Roadmap]: Сквозные цепочки разделены на Phase 4 (Git → Notion) и Phase 5 (web-HITL → Telegram), онбординг — на Phase 8 (мастер) и Phase 9 (коннекторы и брифинги). Итого 9 фаз.
- [Roadmap]: Фаза, меняющая рантайм, закрывается достижимостью из `src/main.py` или команды бота (VERIFICATION.md) и рестартом `assistant-worker` только по разрешению владельца со смоук-проверкой OPS-01.
- [Process]: Исполнение механических планов — через `agy_cross_ai.sh`, без автокоммита; Claude читает патч целиком, гоняет гейт и коммитит сам.
- [Phase 01]: 01-01: страж боевой БД на sys.addaudithook в tests/conftest.py плюс ASSISTANT_DB_PATH_OVERRIDE, захваченный в src/config.py до load_dotenv(override=True)
- [Phase 01]: 01-01: тайминговые пороги проверяются по минимуму из LATENCY_SAMPLES=5 замеров, без skip/xfail
- [Phase 01]: 01-02: tests of assistant-shared run only in /opt/assistant-core/.venv (D-03); CR-02 CLI tests use the assistant-core security_shield.py wrapper
- [Phase 01]: 01-02: shared hitl.decorators imports fastapi which is not in shared pyproject dependencies (hidden defect, left for owner/next plan)
- [Phase 01]: 01-06: окно ошибок старта смоука = до «Run polling for bot» плюс 60 с (STARTUP_TAIL_SECONDS); белого списка внешних ошибок нет
- [Phase 01]: 01-06: scripts/deploy.py допускает только белый список команд (systemctl show, journalctl, git rev-parse HEAD); фазы без TTY сверяют InvocationID
- [Phase 01]: 01-03: shared scripts/security_shield.py is a small copy of the assistant-core wrapper (OQ5); drift between copies is not checked
- [Phase 01]: 01-04: gate row «боевая БД не изменена» может краснеть из-за записи живого assistant-worker в окне pytest; вердикт не смягчается, стратегию решает 01-05/владелец
- [Phase 01]: 01-07: команда рестарта формируется только в restart_service и недоступна без --restart; откат только печатается (D-12)
- [Phase 01]: 01-07: копия БД самодостаточна (journal_mode=DELETE), Phase 3 обязана вызвать выкатку с --backup перед миграцией 0003 (docs/OPS_DEPLOY.md)
- [Phase 01]: 01-07: после рестарта выдерживается окно старта 60 с перед смоуком (строгий D-08)
- [Phase 01]: 01-05: решение владельца 2026-10-09 «Повтор при записи сервиса»: при расхождении хеша боевой БД, активном assistant-worker и mtime БД внутри окна измерения гейт делает ОДИН повторный замер в тихом окне (два хеша через 5 с); совпали - строка зелёная с пометкой в info, иначе КРАСНЫЙ как раньше (fail-closed); основная защита остаётся tests/live_db_guard.py
- [Phase 01]: 01-05: чтение боевой БД mode=ro оставляет пустые assistant.db-wal и -shm в data/ (допущение A7 подтверждено, вреда нет); вопрос чистки вынесен в deferred-items.md
- [Phase 01]: 01-08: общий гейт chat-app упомянут в правилах как неизменяемый гейт потребителя (D-15), способом проверки assistant-core назван python3 scripts/gate.py; страж-тест tests/test_claude_md_gate_pointer.py против возврата прежней команды
- [Phase 01]: 01-09: adapter cross-AI uses the target repo scripts/gate.py (chat-app commit 6b3b2ac); cross_ai_timeout stays 1200 (trial 271 s)
- [Phase 01]: 01-10: серия гейта прошла с первой попытки (3 из 6), смоук на живом сервисе ЗЕЛЁНЫЙ без рестарта
- [Phase 01]: [Owner 2026-10-09]: fastapi missing in assistant-shared deps (hitl.decorators) — task for Phase 2/3 (optional dep or move decorator out of shared).
- [Phase 01]: [Owner 2026-10-09]: empty assistant.db-wal/-shm left in data/ by mode=ro reads — resolve in Phase 3 (read method + cleanup).
- [Phase 01]: [Owner 2026-10-09]: cross-AI adapter residual risk T-uo4-02 (scripts symlink in repo without tracked scripts/) — add refusal + test in Phase 2.
- [Phase 01]: [Owner 2026-10-09]: ASSISTANT_DB_PATH_OVERRIDE absence in live .env unverified (secret-read hook forbids reading .env; owner has no shell). Proposed: deploy.py --restart refuses if the key is present — before first restart (Phase 3), pending owner confirmation.
- [Phase 02]: 02-01: у проверки слов NDA нет механизма допуска для отдельного файла (D-21); сигнатуры закреплены тестами inspect.signature
- [Phase 02]: 02-01: check_index_content приводит CRLF/CR к LF, чтобы номера строк индекса и рабочей копии совпадали
- [Phase 02]: SAFE-01: очистка памяти диалога только через HITL-карточку /clear или /reset; текст, голос, LLM-маршрут и движок только предупреждают
- [Phase 02]: 02-03: имя файла с Drive с «/», «\» или нулевым байтом отвергается целиком (CR-01); серверный бэкап (архив .env и сессии) удалён (WR-02)
- [Phase 02]: WR-08/WR-09 (D-17): каталог копий и состояние проверяются по владельцу и правам; запись через временный файл и os.replace; путь состояния /var/lib/assistant-core (0700)
- [Phase 02]: WR-07: страж боевой БД охраняет абсолютные пути /opt/assistant-core/... и символические ссылки по realpath (02-05)
- [Phase 02]: WR-13: страж правил использует регулярные выражения, собранные из частей, с самопроверкой (02-05)

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 2]: 20 находок код-ревью Phase 1 (`01-REVIEW-DISPOSITION.md`, все deferred), включая CR-01 (path traversal при загрузке с Google Drive, демон от root) — вход планирования Phase 2.
- [Phase 2]: адаптер cross-AI: отказ при подмене `scripts` симлинком (T-uo4-02) и доверие к `conftest.py` цели (WR-05/06).
- [Phase 2/3]: `fastapi` отсутствует в зависимостях assistant-shared (`hitl.decorators`).
- [Phase 3]: пустые `assistant.db-wal/-shm` в `data/` после ro-чтения; перед первым живым `--backup` проверить WR-08/WR-09 (права, `/var/tmp`).
- [Phase 2]: SAFE-01 ждёт решения владельца (HITL-карточка или обратимый архив с командой отмены) на этапе discuss-phase.
- [Phase 3]: Боевая БД получает миграцию `0003` только при рестарте, разрешённом владельцем. Перед ним нужна резервная копия по процедуре OPS-01.
- [Phase 5]: Статус «ожидает / подтверждено / отклонено» для web (HIT-04) может потребовать мелкой правки chat-app через `/gsd-quick`.
- [Phase 6]: Нестабильный `test_concurrent_write_two_processes` (DAT-03) нужно прогнать повторно и честно записать результат.

## Deferred Items

Items acknowledged and deferred at milestone close, most recent first:

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| *(none)* | | | | |

## Session Continuity

Last session: 2026-10-10T12:34:42.739Z
Stopped at: Completed 02-05-PLAN.md
Resume file: None
