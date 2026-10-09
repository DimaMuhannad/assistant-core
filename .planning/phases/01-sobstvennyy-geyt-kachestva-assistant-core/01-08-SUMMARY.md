---
phase: 01-sobstvennyy-geyt-kachestva-assistant-core
plan: 08
subsystem: docs
tags: [gate, claude-md, codebase-maps, guard-test, chat-app-brief, agy]

requires:
  - phase: 01-sobstvennyy-geyt-kachestva-assistant-core
    provides: "01-05 собственный гейт scripts/gate.py (10 строк); 01-07 scripts/deploy.py и docs/OPS_DEPLOY.md"
provides:
  - "CLAUDE.md и .claude/CLAUDE.md называют гейтом assistant-core python3 scripts/gate.py; рестарт assistant-worker только по явному разрешению владельца через scripts/deploy.py --restart (docs/OPS_DEPLOY.md)"
  - "tests/test_claude_md_gate_pointer.py: страж от возврата к прежней команде общего гейта chat-app"
  - "Карты кодовой базы (TESTING, STACK, CONVENTIONS) и PROJECT.md описывают собственный гейт из десяти строк"
  - "01-CHATAPP-QUICK-BRIEF.md: готовое задание для /gsd-quick в chat-app (адаптер cross-AI выбирает гейт целевого репозитория)"
affects: [01-09, 01-10, gate]

actuals:
  tokens: 7345
  tasks: 3
  commits: 3
plan_head_before: e464169396c512ff1b8d5a80cb9d8d3e26f51a0f
plan_head_after: f4508b0bfbd777f1cde2d360012ec8fea28809af

tech-stack:
  added: []
  patterns:
    - "Прежняя команда гейта в тесте-страже собрана из частей, тест не становится источником обратной ссылки"
    - "Формулировки правятся и в картах .planning/codebase, из которых частично генерируется .claude/CLAUDE.md"

key-files:
  created:
    - tests/test_claude_md_gate_pointer.py
    - .planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-CHATAPP-QUICK-BRIEF.md
  modified:
    - CLAUDE.md
    - .claude/CLAUDE.md
    - .planning/codebase/TESTING.md
    - .planning/codebase/STACK.md
    - .planning/codebase/CONVENTIONS.md
    - .planning/PROJECT.md

key-decisions:
  - "Общий гейт chat-app в правилах упомянут одной фразой как неизменяемый гейт потребителя (D-15) без команды запуска как способа проверки assistant-core"
  - "Число тестов в PROJECT.md обновлено с устаревших 421 до 789 (core, базовая линия 01-05) и 91 (shared); на момент закрытия плана гейт видит 792 теста core (789 + 3 стража)"

requirements-completed: [GATE-05]

coverage:
  - id: D1
    description: "Правила CLAUDE.md и .claude/CLAUDE.md указывают на python3 scripts/gate.py и порядок рестарта только по явному разрешению владельца; возврат к прежней команде ловится тестом"
    requirement: GATE-05
    verification:
      - kind: unit
        ref: "tests/test_claude_md_gate_pointer.py#test_root_claude_md_names_own_gate"
        status: pass
      - kind: unit
        ref: "tests/test_claude_md_gate_pointer.py#test_rules_files_do_not_name_legacy_gate_command"
        status: pass
      - kind: unit
        ref: "tests/test_claude_md_gate_pointer.py#test_root_claude_md_mentions_ops_deploy_doc"
        status: pass
    human_judgment: false
  - id: D2
    description: "Карты кодовой базы и PROJECT.md описывают собственный гейт: десять строк в фактическом порядке, хеш боевой БД, замороженный список (D-17), fail-closed (D-16), тесты и hook assistant-shared"
    requirement: GATE-05
    verification:
      - kind: other
        ref: "grep по четырём документам (scripts/gate.py есть, устаревших формулировок нет) и сверка названий строк с python3 scripts/gate.py"
        status: pass
    human_judgment: true
    rationale: "Точность прозы документов проверена построчным чтением патча agy и сверкой с фактическим выводом гейта, но тест на смысл текста карт не пишется"
  - id: D3
    description: "Файл-задание 01-CHATAPP-QUICK-BRIEF.md для /gsd-quick в chat-app: три ветки приоритета гейта, файлы, ограничения D-15, проверка, коммит, что вернуть"
    requirement: GATE-05
    verification:
      - kind: other
        ref: "grep AGY_GATE_CMD, test_agy_cross_ai.py, SKILL.md, D-15 в файле; git -C /opt/chat-app status --short пуст"
        status: pass
    human_judgment: true
    rationale: "Выполнимость и полнота задания подтвердятся только его исполнением в chat-app (план 01-09)"

duration: 9min
completed: 2026-10-09
status: complete
---

# Phase 1 Plan 08: Правила и карты кодовой базы на собственный гейт Summary

**CLAUDE.md, .claude/CLAUDE.md, три карты кодовой базы и PROJECT.md переведены на `python3 scripts/gate.py` (десять строк) с порядком рестарта только по разрешению владельца, страж-тест не даёт вернуться к команде общего гейта chat-app, а для `/gsd-quick` в chat-app подготовлено ограниченное задание на переключение адаптера cross-AI.**

## Performance

- **Duration:** 9 мин (544 с)
- **Started:** 2026-10-09T20:14:34Z
- **Completed:** 2026-10-09T20:23:38Z
- **Tasks:** 3
- **Files modified:** 8 (2 созданы, 6 изменены)

## Accomplishments

- **Правила (Task 1, tracer).** В корневом `CLAUDE.md` раздел 3: пункт «Run Quality Gate» теперь `python3 scripts/gate.py` с перечнем проверок обоих репозиториев и «ЗЕЛЁНЫЙ при exit 0»; оговорка «until assistant-core has its own» удалена; общий гейт chat-app упомянут как неизменяемый гейт потребителя (D-15). Добавлен пункт про `python3 scripts/deploy.py` (read-only смоук, `--backup`/`--restart` только с явным разрешением владельца, `docs/OPS_DEPLOY.md`). Пункт «Restart Services»: `assistant-worker` только по explicit owner permission через `scripts/deploy.py --restart`, строка `chat-app.service` не менялась. В `.claude/CLAUDE.md` исправлены три места (строка Quality gate, место `KNOWN_SHIELD_FALSE_POSITIVES`, фраза про запуск import-linter). Остальные части обоих файлов (GSD, профиль, архитектура) не тронуты.
- **Страж-тест.** `tests/test_claude_md_gate_pointer.py`: три теста (`test_root_claude_md_names_own_gate`, `test_rules_files_do_not_name_legacy_gate_command`, `test_root_claude_md_mentions_ops_deploy_doc`). RED подтверждён до правок (3 падения), GREEN после (3 passed). Прежняя команда задана константой из частей.
- **Карты кодовой базы и PROJECT.md (Task 2).** `TESTING.md`: «Quality Gate (own)» с десятью строками в фактическом порядке и названиями как в выводе гейта, изоляция БД тестов (`tests/live_db_guard.py`, `ASSISTANT_DB_PATH_OVERRIDE`), замороженный список D-17, fail-closed D-16, `--save-pytest-output`, правила прохождения сохранены дословно, команда тестов shared, Known Gaps переписан. `STACK.md`, `CONVENTIONS.md`: указатели на `scripts/gate.py`. `PROJECT.md`: «Гейт собственный», у assistant-shared есть тесты (91) и hook (WR-11 закрыт), число тестов обновлено.
- **Задание для chat-app (Task 3).** `01-CHATAPP-QUICK-BRIEF.md`, 68 строк, девять пронумерованных разделов: приоритет `AGY_GATE_CMD` → `$TOP/scripts/gate.py` с cwd `$TOP` → откат на гейт chat-app; файлы (`scripts/agy_cross_ai.sh`, `backend/tests/test_agy_cross_ai.py` с двумя новыми тестами, `.claude/skills/agy-delegate/SKILL.md`); запрет менять `scripts/gate.py` chat-app (D-15) и ослаблять защищённые пути и коды 10/12/15; проверка; шаблон коммита; вне задачи; что вернуть. Эскиз bash из исследования помечен «эскиз, не готовый код».
- **chat-app не тронут:** `git -C /opt/chat-app status --short` пуст до и после плана.

## Task Commits

1. **Task 1: правила на собственный гейт и страж-тест** - `7451866` (feat)
2. **Task 3: задание для /gsd-quick в chat-app** - `7a177d0` (docs)
3. **Task 2: карты кодовой базы и PROJECT.md** - `f4508b0` (docs)

Порядок коммитов Task 3 перед Task 2 объясняется тем, что задание agy по Task 2 выполнялось ~8 минут в фоне, пока готовился файл-задание.

**Plan metadata:** следующие коммиты docs(01-08).

## Files Created/Modified

- `CLAUDE.md` - раздел 3: собственный гейт, выкатка, порядок рестарта
- `.claude/CLAUDE.md` - три указателя на `scripts/gate.py`
- `tests/test_claude_md_gate_pointer.py` - страж от возврата к прежней команде гейта
- `.planning/codebase/TESTING.md`, `STACK.md`, `CONVENTIONS.md` - описание собственного гейта
- `.planning/PROJECT.md` - гейт собственный, shared с тестами и hook, число тестов
- `.planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-CHATAPP-QUICK-BRIEF.md` - задание для chat-app

## Decisions Made

- Общий гейт chat-app в правилах упомянут одной фразой как неизменяемый гейт потребителя (D-15); команда его запуска не указана.
- Число тестов в PROJECT.md взято из SUMMARY 01-05 (789 core, 91 shared) вместо устаревших 421; после стража гейт видит 792 теста core.

## Делегирование agy

Правка четырёх документов (Task 2) выполнена агентом agy через `agy_task.sh run --mode edit --agent docs` (SUCCESS, input 87391 / output 22142 токенов Antigravity, задание `20261009-201618-527085`). Патч прочитан целиком; применён `git apply`; задание очищено командой `clean`. Правка Claude после патча: устаревшее число тестов `421` в PROJECT.md (agy его не менял, в задании не было). Остальное совпало с заданием и фактическим выводом гейта.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Устаревшее число тестов в PROJECT.md**
- **Found during:** Task 2 (проверка патча agy)
- **Issue:** строка «Тесты: 421 теста pytest» противоречила фактическим 789 (core) и 91 (shared) и новому абзацу про гейт.
- **Fix:** строка приведена к 789 core (базовая линия 01-05) и 91 shared.
- **Files modified:** .planning/PROJECT.md
- **Committed in:** f4508b0

---

**Total deviations:** 1 auto-fixed (Rule 1)
**Impact on plan:** без расширения объёма; документ согласован.

Процессная заметка: Task 1 помечен tracer и tdd, `workflow.tdd_mode` не включён; RED (3 падения) и GREEN (3 passed) прогонялись вручную, отдельного `test(...)` коммита нет (тест и правки в одном коммите, как требует задача).

## Issues Encountered

None.

## Verification

- `tests/test_claude_md_gate_pointer.py`: 3 passed.
- `grep -rn "until assistant-core has its own" CLAUDE.md .claude/CLAUDE.md .planning/codebase`: пусто.
- Прежняя команда общего гейта в `CLAUDE.md`, `.claude/CLAUDE.md`, `TESTING.md`, `STACK.md`: 0 вхождений.
- `python3 scripts/gate.py`: 10 строк ✓ (core pytest 792, shared pytest 91, SHA-256 боевой БД до/после совпали `88aaf13e6cbd`), `ИТОГ: ЗЕЛЁНЫЙ`, rc 0, 2 мин 15 с.
- `git -C /opt/chat-app status --short`: пусто.

## Known Stubs

None.

## Threat Flags

None. Новых сетевых точек, путей аутентификации и зависимостей нет (T-01-25: правки во всех источниках плюс страж-тест; T-01-26: в задании явный запрет менять защиты адаптера и `scripts/gate.py` chat-app; T-01-SC: пакеты не устанавливались).

## Next Phase Readiness

- План 01-09 берёт `01-CHATAPP-QUICK-BRIEF.md` как вход для `/gsd-quick` в chat-app, проверяет diff на ослабление защит адаптера и делает пробный прогон cross-AI на assistant-core.
- Запрос GATE-05 закрывается полностью после 01-09 (переключение адаптера); сторона assistant-core готова.

## Self-Check: PASSED

- FOUND: CLAUDE.md, .claude/CLAUDE.md, tests/test_claude_md_gate_pointer.py, .planning/codebase/TESTING.md, 01-CHATAPP-QUICK-BRIEF.md
- FOUND коммиты (предки HEAD): 7451866, 7a177d0, f4508b0
- Полный гейт: ИТОГ ЗЕЛЁНЫЙ, rc 0

---
*Phase: 01-sobstvennyy-geyt-kachestva-assistant-core*
*Completed: 2026-10-09*
