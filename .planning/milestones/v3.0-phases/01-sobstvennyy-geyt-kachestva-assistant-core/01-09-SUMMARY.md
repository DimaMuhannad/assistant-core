---
phase: 01-sobstvennyy-geyt-kachestva-assistant-core
plan: 09
subsystem: infra
tags: [cross-ai, agy, quality-gate, chat-app, adapter]

requires:
  - phase: 01-sobstvennyy-geyt-kachestva-assistant-core
    provides: "собственный scripts/gate.py assistant-core (10 строк таблицы) и задание 01-CHATAPP-QUICK-BRIEF.md (планы 01-01..01-08)"
provides:
  - "Адаптер cross-AI в chat-app запускает scripts/gate.py целевого репозитория (GATE-05, сторона chat-app)"
  - "Пробный прогон agy_cross_ai.sh --repo /opt/assistant-core: код 0, 271 с, гейт assistant-core ЗЕЛЁНЫЙ (10 строк, три из них assistant-shared)"
  - "Решение по cross_ai_timeout: 1200 с достаточно, config.json не менялся (допущение A8)"
affects: [phase-02, cross-ai-execution]

plan_head_before: d99b7b89b56f5bb22f26bc5c52ad96ff1a2c5dca
plan_head_after: d99b7b89b56f5bb22f26bc5c52ad96ff1a2c5dca

actuals:
  tokens: 3371       # chars/4 по diff кода в chat-app (коммит 6b3b2ac); в assistant-core кода нет
  tasks: 3
  commits: 0         # измерено в assistant-core: git rev-list --count d99b7b8..HEAD = 0 до коммита SUMMARY; код плана лежит в chat-app (2 коммита, см. ниже)

tech-stack:
  added: []
  patterns:
    - "Выбор гейта адаптером по порядку: AGY_GATE_CMD, затем $TOP/scripts/gate.py с cwd=$TOP, затем гейт chat-app"
    - "scripts/gate.py целевого репозитория доверяется, потому что он в PROTECTED адаптера (патч по нему отклоняется кодом 12)"

key-files:
  created: []
  modified:
    - "/opt/chat-app/scripts/agy_cross_ai.sh"
    - "/opt/chat-app/backend/tests/test_agy_cross_ai.py"
    - "/opt/chat-app/.claude/skills/agy-delegate/SKILL.md"

key-decisions:
  - "Правка адаптера сделана только малой задачей /gsd-quick в chat-app (D-15), executor assistant-core chat-app не трогал"
  - "workflow.cross_ai_timeout остаётся 1200: пробный прогон занял 271 с при пороге 1000 с (допущение A8 подтверждено)"

requirements-completed: [GATE-05]

coverage:
  - id: D1
    description: "Адаптер cross-AI запускает scripts/gate.py целевого репозитория (приоритет AGY_GATE_CMD, затем $TOP/scripts/gate.py с cwd=$TOP, затем откат на гейт chat-app); защиты адаптера не ослаблены, scripts/gate.py chat-app не изменён"
    requirement: GATE-05
    verification:
      - kind: unit
        ref: "/opt/chat-app/backend/tests/test_agy_cross_ai.py (18 passed)"
        status: pass
      - kind: other
        ref: "git -C /opt/chat-app diff 279dc5a 6b3b2ac -- scripts/agy_cross_ai.sh (только блок gate, комментарий шапки и текст отчёта; PROTECTED, проверка грязного дерева, откат при красном гейте и запрет автокоммита не тронуты)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Пробный прогон agy_cross_ai.sh --repo /opt/assistant-core на тривиальном плане даёт код 0 и ЗЕЛЁНЫЙ гейт assistant-core (критерий успеха 4 фазы); патч прочитан целиком (одна строка) и отброшен, деревья чисты"
    requirement: GATE-05
    verification:
      - kind: integration
        ref: "/var/tmp/gsd-phase01-trial/rc.txt = 0; gate-excerpt.txt содержит строки assistant-shared и «ИТОГ: ЗЕЛЁНЫЙ»; git status --short вне .planning/ пуст"
        status: pass
    human_judgment: false

duration: 126min  # астрономическое время от старта до завершения, включая ожидание чекпоинта /gsd-quick
completed: 2026-10-09
status: complete
---

# Phase 1 Plan 09: Переключение адаптера cross-AI на гейт assistant-core Summary

**Адаптер agy_cross_ai.sh при `--repo /opt/assistant-core` теперь запускает собственный scripts/gate.py репозитория; пробный прогон на тривиальном плане дал код 0 за 271 с и ЗЕЛЁНЫЙ гейт из десяти строк (с тремя строками assistant-shared).**

## Performance

- **Duration:** 126 мин астрономического времени (20:26:31Z - 22:32:26Z), из них прогон адаптера 271 с; остальное - ожидание чекпоинта и задачи /gsd-quick в chat-app
- **Started:** 2026-10-09T20:26:31Z
- **Completed:** 2026-10-09T22:32:26Z
- **Tasks:** 3 (Task 1 - трассер, Task 2 - чекпоинт, Task 3 - пробный прогон)
- **Files modified (в репозиториях):** 3 файла в chat-app, 0 в assistant-core (кроме этого SUMMARY и планировочных файлов)

## Accomplishments

- Блок gate адаптера выбирает гейт по порядку: `AGY_GATE_CMD` (только тесты), затем `$TOP/scripts/gate.py` с рабочим каталогом `$TOP`, затем гейт chat-app. В журнал пишется строка о выбранном гейте и каталоге. Для самого chat-app поведение прежнее.
- Защиты адаптера не тронуты: кортеж PROTECTED (в нём `scripts/gate.py`, `.githooks/`, `.importlinter`, `.planning/` и др.), отказ при грязном дереве (код 10), откат патча при красном гейте (код 15), отсутствие автокоммита. `scripts/gate.py` chat-app не менялся (проверено `git diff 279dc5a HEAD -- scripts/gate.py` - пусто).
- Пробный прогон доказал путь от адаптера до гейта assistant-core: журнал задания содержит строку `гейт качества: python3 /opt/assistant-core/scripts/gate.py (каталог /opt/assistant-core)`.

## Базовая линия (Task 1, трассер, без коммита)

- Старт плана: 2026-10-09T20:26:31Z (epoch 1791577591).
- HEAD до: assistant-core `d99b7b89b56f5bb22f26bc5c52ad96ff1a2c5dca`; assistant-shared `74aa9286406631f8cba13f55e5a1d337acecdaf7`; chat-app `279dc5a50b6cb17168a6f328d3392038639b6fcd`.
- Тесты адаптера до правки: `backend/tests/test_agy_cross_ai.py` - 16 passed.
- Блок gate до правки: строка 304 всегда запускала гейт chat-app из `$SCRIPT_DIR/..`; кортеж PROTECTED на строке 75.
- Конфигурация: `workflow.cross_ai_timeout=1200`; `cross_ai_command=/opt/chat-app/scripts/agy_cross_ai.sh --repo /opt/assistant-core`.

## Task Commits

1. **Task 1: Базовая линия** - без коммита (только фиксация состояния)
2. **Task 2: Переключение адаптера (чекпоинт, /gsd-quick 261009-uo4 в chat-app)** - `6b3b2ac` в chat-app (`fix(cross-ai): adapter runs the target repository gate (GATE-05)`: ровно три файла, 93 вставки, 9 удалений) и `4b73019` в chat-app (документы quick-задачи: PLAN/SUMMARY/STATE)
3. **Task 3: Пробный прогон** - без коммита (патч пробного прогона отброшен намеренно)

**Plan metadata:** коммит `docs(01-09)` с этим SUMMARY, STATE.md, ROADMAP.md, REQUIREMENTS.md (хеш в журнале git).

## Проверка Task 2 (выполнена независимо после возврата управления)

| Проверка | Результат |
|----------|-----------|
| HEAD chat-app отличается от `279dc5a` | да: `4b73019` (код - `6b3b2ac`) |
| Коммит кода перечисляет ровно `scripts/agy_cross_ai.sh`, `backend/tests/test_agy_cross_ai.py`, `.claude/skills/agy-delegate/SKILL.md` | да |
| `scripts/gate.py` chat-app в коммитах не затронут | да (`git diff 279dc5a HEAD -- scripts/gate.py` пуст) |
| Блок gate содержит выбор по `$TOP/scripts/gate.py` | да (строки 312-318) |
| PROTECTED, проверка грязного дерева, откат при красном гейте, запрет автокоммита | `git diff 279dc5a 6b3b2ac -- scripts/agy_cross_ai.sh` меняет только комментарий шапки, блок gate и текст отчёта; PROTECTED - в неизменённом контексте |
| Тесты адаптера | 18 passed (16 прежних + 2 новых теста выбора гейта) |
| `git -C /opt/chat-app status --short` | пусто |

Со слов исполнителя quick-задачи: полный `backend/tests` chat-app - 251 passed; общий гейт chat-app `python3 scripts/gate.py` на втором запуске ЗЕЛЁНЫЙ. **Первый запуск гейта был КРАСНЫЙ из-за известного нестабильного теста `backend.tests.test_concurrent_write::test_concurrent_write_two_processes`** (не связан с этой правкой; учтён как DAT-03 для фазы 6). Этот факт записан здесь по требованию задания.

## Пробный прогон (Task 3)

- **Команда:** `/opt/chat-app/scripts/agy_cross_ai.sh --repo /opt/assistant-core < /var/tmp/gsd-phase01-trial/prompt.md`
- **Попыток:** 1
- **Код возврата:** 0
- **Длительность:** 271 с (агент `gemini-3.8-flash-high` - 88 с, остальное - сборка копии, проверки адаптера и гейт). Порог 1000 с не превышен.
- **Задание:** `20261009-222737-560160` (удалено через `agy_task.sh clean`)
- **Токены Antigravity:** вход 125049, выход 6491
- **Патч:** прочитан целиком через `git diff -- docs/OPS_DEPLOY.md`: единственная добавленная строка `<!-- adapter trial -->` в конец файла, больше ничего. Отброшен `git checkout -- docs/OPS_DEPLOY.md`.
- **Агент напрямую не запускался**, только через адаптер.

Таблица гейта из `gate.log` задания (копия: `/var/tmp/gsd-phase01-trial/gate-excerpt.txt`):

| Репозиторий | Проверка | Результат |
|-------------|----------|-----------|
| assistant-core | pytest - тестов: 792 | ✓ |
| assistant-core | боевая assistant.db не изменена | ✓ |
| assistant-core | import-linter | ✓ |
| assistant-core | security_shield (--all) | ✓ |
| assistant-core | синтетическая персона (дрейф SHA-256) | ✓ |
| assistant-core | токены персоны (дрейф SHA-256) | ✓ |
| assistant-core | pre-commit hook установлен | ✓ |
| assistant-shared | pytest - тестов: 91 | ✓ |
| assistant-shared | security_shield (--all) | ✓ |
| assistant-shared | pre-commit hook установлен | ✓ |

**ИТОГ: ЗЕЛЁНЫЙ**

Побочное наблюдение: из копии задания адаптер удалил возможные секреты (`.env.example`) - это штатная очистка jail-обёртки, на результат не влияет.

## Решение по cross_ai_timeout (допущение A8)

Допущение A8 (1200 с достаточно для агента до 300 с плюс гейта около 6 минут) подтверждено: весь прогон занял 271 с, что меньше порога 1000 с. `.planning/config.json` для `cross_ai_timeout` **не менялся** (значение остаётся 1200). Замечание: в рабочем дереве есть чужая правка orchestrator в `config.json` (`_auto_chain_active: false`) - она не относится к этому плану и в коммит плана не включалась. Один замер на тривиальном плане; на планах с большим числом файлов агент может идти дольше (потолок 300 с на попытку заложен адаптером), поэтому запас 1200 с оставлен.

## Decisions Made

- Переключение адаптера выполнено только задачей `/gsd-quick` в chat-app; executor assistant-core chat-app не правил (D-15).
- Таймаут не менять: данные пробного прогона не показывают превышения.

## Deviations from Plan

None - plan executed exactly as written. (Task 2 был чекпоинтом и выполнен оркестратором по просьбе владельца «Запусти сам»; отклонений от задания 01-CHATAPP-QUICK-BRIEF.md нет.)

## Issues Encountered

- Нестабильный тест chat-app `test_concurrent_write_two_processes` дал красный первый запуск общего гейта chat-app; повторный запуск зелёный. Не связан с правкой; отслеживается как DAT-03 (фаза 6).
- Не выполнялась отдельная установка пакетов, новых зависимостей нет.

## Остаточный риск и кандидат на фазу 2

Принятый планировщиком остаточный риск T-uo4-02 (низкий): в репозитории, у которого в HEAD нет каталога `scripts/`, патч агента мог бы добавить симлинк `scripts` и подменить `gate.py`. К chat-app, assistant-core и assistant-shared это не относится (`scripts/` отслеживается и защищён, патч получает код 12). Кандидат на закрытие в фазе 2: явный отказ адаптера, если `$TOP/scripts` не отслеживаемый каталог (или запрет симлинков в `scripts`).

## Known Stubs

Нет: плана не создано заглушек.

## Threat Flags

Нет новой поверхности атаки в assistant-core. Реестр угроз: T-01-27 (ослабление защит адаптера) - снята проверкой Task 2 (PROTECTED и откат не тронуты, `gate.py` chat-app не в коммите); T-01-28 (патч остаётся в дереве) - снята: патч прочитан и отброшен, деревья чисты; T-01-29 (агент правит гейт/hook/shield) - прежняя защита PROTECTED сохранена; T-01-SC - пакеты не ставились.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Фаза 1: все планы 01-01..01-09 выполнены, GATE-05 закрыт; готово к проверке фазы (`/gsd-verify-work`), в VERIFICATION.md проверить достижимость из рантайма: `cross_ai_command` из config.json действительно приводит к гейту assistant-core (это и показал пробный прогон).
- Блокеров нет. Деревья assistant-core (вне `.planning/`), assistant-shared и chat-app чисты.

## Self-Check: PASSED

- chat-app коммиты `6b3b2ac` и `4b73019` существуют в истории chat-app.
- `/var/tmp/gsd-phase01-trial/` содержит `prompt.md`, `summary.out`, `adapter.err`, `rc.txt` (0), `gate-excerpt.txt`.
- Проверка Task 3 (`rc.txt` = 0, «ИТОГ: ЗЕЛЁНЫЙ», строки assistant-shared, чистое дерево) прошла.

---
*Phase: 01-sobstvennyy-geyt-kachestva-assistant-core*
*Completed: 2026-10-09*
