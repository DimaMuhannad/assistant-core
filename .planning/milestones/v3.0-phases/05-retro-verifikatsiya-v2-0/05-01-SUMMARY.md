---
phase: 05-retro-verifikatsiya-v2-0
plan: 01
subsystem: verification
tags: [retro-verification, v2.0, tool-calling, hitl, telegram, act-requirements]

requires:
  - phase: 03-vladenie-shemoy-bd
    provides: шаблон и формат VERIFICATION.md (образец 03-VERIFICATION.md)
provides:
  - V2-08-VERIFICATION.md с вердиктами ACT-01..ACT-04 и доказательствами достижимости из рантайма
  - gap ACT-03 (путь act:cal:retry вне resume_action) с классом HITL и предложением HIT-06 для плана 05-08
  - наблюдение о зависании процесса pytest в test_fast_intent_router.py (блокирует гейт)
affects: [05-08, 05-VERIFICATION, 05-EVIDENCE-DAT03]

actuals:
  tokens: 7955      # chars/4 над V2-08-VERIFICATION.md (31821 символов); SUMMARY не учтён
  tasks: 3
  commits: 3        # измерено: git rev-list --count 252970d..HEAD (до коммита SUMMARY)
plan_head_before: 252970dfe0fe08cac1fc961b3832cb769d273f58
plan_head_after: 4dd519d70f22b8ac2b503800f45382745afcf64b

tech-stack:
  added: []
  patterns:
    - "Вердикт passed только с трассой file:line и прогоном; passed без e2e помечается «трасса»"

key-files:
  created:
    - .planning/phases/05-retro-verifikatsiya-v2-0/V2-08-VERIFICATION.md
    - .planning/phases/05-retro-verifikatsiya-v2-0/05-01-SUMMARY.md
  modified:
    - .planning/STATE.md

key-decisions:
  - "ACT-01 и ACT-02 вынесены по HITL-first прочтению (решение владельца 2026-10-18 №2); ACT-05 не создаётся"
  - "ACT-03 получил gap: act:cal:retry пишет в Google Calendar вне resume_action и без проверки статуса записи; класс HITL, предложено HIT-06, номер фазы назначает 05-08"
  - "ACT-04 passed с меткой трасса+e2e: tests/test_tool_calling_flow.py:81 проходит реальный route() в handle_user_text"
  - "Зависание pytest (код 124 при 10 passed) записано наблюдением, а не gap требования: дефект инфраструктуры тестов; тесты не менялись (D-10)"

patterns-established:
  - "Черновик агента Argon принимается только после перепроверки каждой ссылки и каждой команды по коду и прогону"

requirements-completed: [ACT-01, ACT-02, ACT-04]  # ACT-03 — gap (не выполнено); VER-01 — вклад частичный (1 из 6 файлов фазы)

coverage:
  - id: D1
    description: "V2-08-VERIFICATION.md: вердикты ACT-01..ACT-04 с file:line и метками"
    requirement: "VER-01"
    verification:
      - kind: other
        ref: "grep '^| ACT-0[1-4] | (passed|gap) |' V2-08-VERIFICATION.md (4 строки) + 4 подраздела ### ACT"
        status: pass
    human_judgment: false

duration: ~40min (оценка по отметкам времени файлов; точный старт не записан)
completed: 2026-10-18
status: complete
---

# Phase 05 Plan 01: Ретро-верификация V2-08 (Tool Calling) — Summary

**V2-08 вынесен: ACT-01, ACT-02, ACT-04 passed, ACT-03 gap (retry-путь календаря обходит HITL-движок); 44 + 10 тестов ACT зелёные, зависание pytest в test_fast_intent_router.py записано наблюдением**

## Performance

- **Duration:** ~40 min (оценка)
- **Started:** не записан (план стартовал без записи времени в начале)
- **Completed:** 2026-10-18T21:08:09Z
- **Tasks:** 3 из 3
- **Files modified:** 2 создано, 1 изменён (STATE.md)

## Accomplishments

- Файл `V2-08-VERIFICATION.md` в папке фазы 5 по формату плана: frontmatter, источник (chat-app, только чтение), таблица вердиктов, доказательства по `### ACT-0N`, наблюдения, gaps, ограничения.
- ACT-04 доказан трассой от `src/notifier/bot_handler.py:1471` до `FastIntentRouter.route` и `VALID_ACTIONS`, плюс прогоны тестов.
- ACT-03: подтверждение, отклонение, авторизация, идемпотентность и истечение срока проверены через `resume_action`. Найден обход через `act:cal:retry` (gap).
- ACT-01: сквозная цепочка сообщение → маршрутизатор → SecretaryDialogEngine → карточка → обработчик → бэкенд непрерывна; HITL-first принят по решению владельца.
- ACT-02: правило промпта (`config/prompts/secretary_default.jinja2:27-31`) передаётся в модель и закреплено байтовым снимком; вердикт по трассе, без e2e (D-04).

## Task Commits

1. **Task 1: ACT-04 трасса и первая строка V2-08** — `c38ee85` (docs)
2. **Task 2: ACT-03, ACT-01, ACT-02, наблюдения и gap** — `026357f` (docs)
3. **Task 3: финализация frontmatter и ограничений** — `4dd519d` (docs)

**Plan metadata:** коммит `docs(05-01)` с этим SUMMARY, STATE.md и ROADMAP.md (хеш в `git log`).

## Прогоны (код возврата и итоги)

| Команда | Код | Итог |
|---------|-----|------|
| `pytest tests/test_fast_intent_router.py -q` | 124 (зависание после итога) | 10 passed (9.80 s) |
| `pytest tests/test_tool_calling_flow.py -q` | 0 | 6 passed (29.56 s) |
| пять файлов ACT (hitl_cards, e2e, flow, secretary_tools, prompt_snapshot) | 0 | 44 passed (16.71 s): 9 + 3 + 6 + 7 + 19 |

Прогоны выполнены с `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`. Боевая БД не открывалась, `.env` напрямую не читался, живых вызовов внешних API не было (D-02).

## Files Created/Modified

- `.planning/phases/05-retro-verifikatsiya-v2-0/V2-08-VERIFICATION.md` — вердикты ACT-01..ACT-04.
- `.planning/phases/05-retro-verifikatsiya-v2-0/05-01-SUMMARY.md` — этот файл.
- `.planning/STATE.md` — позиция, метрики, решения, сессия.

## Decisions Made

- HITL-first как спецификация для ACT-01 и ACT-02 (решение владельца 2026-10-18 №2). ACT-05 не создаётся. Формулировки в REQUIREMENTS.md обновит план 05-08.
- ACT-03 — gap класса HITL. Предложение: HIT-06, номер фазы 999.N назначает 05-08 по его правилу.
- `requirements.mark-complete` не вызывался: статусы в REQUIREMENTS.md ведёт план 05-08 (ACT-01/02 с новой формулировкой, ACT-03 — gap).

## Deviations from Plan

### Auto-fixed Issues

Исправлений кода и тестов нет (D-10). Ниже отклонения от плана и от черновика.

**1. [Процесс — черновик Argon] Черновик перепроверен, исправлено 10 пунктов**
- **Found during:** Task 1–3, перепроверка каждой ссылки и команды
- **Issue:** черновик агента Argon (acc2, gemini-4-argon-high) содержал неверные утверждения: вердикт ACT-03 passed с «единственной точкой запуска» 2401 (retry-путь обходит её), «gaps нет», ожидание exit 0 у pytest (фактически зависание), счётчики 41/23 (фактически 44/26), строку 944 вместо 934, ссылки на чистый клон `/var/tmp/argon-p5…`, утверждение «.venv отсутствует».
- **Fix:** все пункты исправлены в V2-08 по коду и прогонам; полный список в разделе «Ограничения проверки» файла V2-08.
- **Verification:** grep по file:line, прогоны каждой команды, построчная сверка выборочных диапазонов.
- **Committed in:** 026357f, 4dd519d

**2. [Rule 3 — блокирующий, не исправлен] Зависание pytest в test_fast_intent_router.py**
- **Found during:** Task 1 (автоматическая проверка `pytest ... && grep`)
- **Issue:** итог «10 passed», процесс не выходит: три не-демонических потока `aiosqlite` от тестов `test_bot_handler_dispatch_*`. Код возврата 124, автоматическая проверка Task 1 не прошла.
- **Fix:** не исправлено. Закрытие соединений требует правки тестов, что запрещено D-10. Записано как наблюдение 5 в V2-08 с предложением владельцу: `/gsd-quick` или бэклог.
- **Verification:** четыре полных прогона дали код 124; бисекция по `-k`; дамп потоков плагином вне репозитория.
- **Committed in:** c38ee85 (наблюдение), 026357f

---

**Total deviations:** 2 (1 процессный — черновик Argon, 1 блокирующий — не исправлен из-за D-10)
**Impact on plan:** вердикты получены по коду и прогонам. Гейт не запускался: он хеширует боевую БД, а по коду зависание даёт КРАСНЫЙ.

## Issues Encountered

- Зависание pytest (см. выше) — требует решения владельца.
- Журнал коммитов по протоколу 0c не был создан до первого коммита. Базой взят `state_head` из STATE.md (`252970d`), число коммитов измерено `git rev-list --count 252970d..HEAD`.
- STATE.md и `.planning/config.json` имели незакоммиченные изменения до старта (состояние оркестратора). Не относятся к плану. STATE.md закоммичен вместе с обновлением позиции, config.json не трогался.

## User Setup Required

Нет.

## Known Stubs

Нет (документы, без кода).

## Threat Flags

Нет новых поверхностей: изменены только файлы `.planning/`.

## Self-Check

Проверка по выполненным командам:

- `V2-08-VERIFICATION.md`: найден; frontmatter `status: gaps_found`, `score: "3 из 4 требований passed"`, `gaps: [ACT-03]`; четыре строки `| ACT-0N | ... |` и четыре подраздела `### ACT-0N`.
- Коммиты `c38ee85`, `026357f`, `4dd519d`: найдены в истории `main`.
- `git status --porcelain` вне `.planning/`: пусто. Код и тесты не изменены.
- Адреса e-mail в V2-08: не найдены.

## Self-Check: PASSED
