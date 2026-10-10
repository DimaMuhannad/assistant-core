---
phase: 02-bezopasnost-privatnost-i-nahodki-revyu
plan: 09
subsystem: security
tags: [cross-ai-adapter, protected-paths, gate-environment, symlink, chat-app-quick, wr-05, wr-06, t-uo4-02, d-17]

requires:
  - phase: 02-bezopasnost-privatnost-i-nahodki-revyu
    provides: "02-07: chat-app quick 261010-ivt (делегатор shield); 02-10: библиотека безопасности без слов NDA"
provides:
  - "chat-app scripts/agy_cross_ai.sh: PROTECTED расширен восемью путями окружения гейта, каталоги-предки защищены, код 17 при символической ссылке на scripts или scripts/gate.py, GATE_KIND с предупреждением adapter-fallback"
  - "02-CHATAPP-CROSSAI-QUICK-BRIEF.md: задание для /gsd-quick"
  - "закрытие остаточного риска AR-01-04 (T-uo4-02) в 01-SECURITY.md"
affects: [02-14, chat-app, phase-02-verification]

actuals:
  tokens: 9937
  tasks: 3
  commits: 1
plan_head_before: d0875b60737a282e6093fe0a7b157aba50b3f749
plan_head_after: 04f55a2ce679fe54a12af5f9a471c5ab38fed7dc
chatapp_commits: 2
chatapp_head_before: 07a0b869a35649e1e4649eb1d1f84cdc2d4c0b90
chatapp_head_after: f92d95f

tech-stack:
  added: []
  patterns:
    - "Защитный код адаптера правит Claude, не agy; тесты на заглушках, настоящий гейт chat-app из тестов не вызывается"
    - "Мутационная проверка новых тестов: на старом адаптере падают 15 из 16 новых, без повторной проверки перед гейтом падает тест отката"

key-files:
  created:
    - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-CHATAPP-CROSSAI-QUICK-BRIEF.md
    - /opt/chat-app/.planning/quick/261010-cgx-cross-ai-adapter-gate-environment-protecti/261010-cgx-PLAN.md
    - /opt/chat-app/.planning/quick/261010-cgx-cross-ai-adapter-gate-environment-protecti/261010-cgx-SUMMARY.md
  modified:
    - /opt/chat-app/scripts/agy_cross_ai.sh
    - /opt/chat-app/backend/tests/test_agy_cross_ai.py
    - /opt/chat-app/.claude/skills/agy-delegate/SKILL.md
    - /opt/chat-app/backend/tests/test_security_shared.py
    - .planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-SECURITY.md

key-decisions:
  - "Правку chat-app провёл исполнитель в /opt/chat-app по явному разрешению владельца (опрос), малой задачей в стиле /gsd-quick (quick 261010-cgx)"
  - "В той же задаче по разрешению владельца заменён личный аккаунт в test_normalize_remote_formats на ExampleOrg и хост git.example.org"
  - "Каталоги-предки защищённых файлов (scripts, tests, src) считаются защищёнными путями: патч, подменяющий каталог ссылкой, трогает только сам путь"

requirements-completed: []

duration: 35min
completed: 2026-10-10
status: complete
---

# Phase 2 Plan 09: адаптер cross-AI в chat-app Summary

Адаптер `scripts/agy_cross_ai.sh` защищает окружение гейта цели, называет вид гейта и отказывает кодом 17 при символической ссылке на гейт; остаточный риск T-uo4-02 закрыт.

## Что сделано

- Task 1: база в `/var/tmp/gsd-phase02-crossai/baseline.txt` (HEAD chat-app 07a0b86, 18 тестов адаптера, номера блоков).
- Task 2: задание `02-CHATAPP-CROSSAI-QUICK-BRIEF.md` (9 разделов, проверка слов по данным персоны без печати значений), коммит `04f55a2`.
- Task 3: правка chat-app, коммит `27886b3` (код и тесты) и `f92d95f` (артефакты quick и STATE.md chat-app); в `01-SECURITY.md` строка AR-01-04 помечена закрытой с хешем.

## Находка -> изменение -> тест

| Находка | Изменение | Тест |
|---|---|---|
| WR-05 | в `PROTECTED` восемь новых путей, список стал 19 записей, прежние 11 сохранены; шапка уточняет границы доверия | `test_gate_environment_path_refused` x8: код 12, путь в stderr, агент вызван один раз, гейт не вызван, дерево как до запуска |
| WR-06 | `GATE_KIND` (test, target, adapter-fallback); для adapter-fallback предупреждение в stderr и в SUMMARY, текст «Гейт качества целевого репозитория...» заменён | `test_fallback_gate_warns_in_stderr_and_summary`, `test_target_gate_has_no_fallback_warning`, `test_test_gate_cmd_has_no_fallback_warning` |
| T-uo4-02 (путь-предок) | `is_protected` защищает каталоги-предки (`scripts`, `tests`, `src`) | `test_scripts_directory_replaced_by_symlink_refused`: код 12 |
| T-uo4-02 (ссылка в репозитории) | код 17 до запуска агента, если `scripts` или `scripts/gate.py` ссылка (при неустановленном `AGY_GATE_CMD`) | `test_symlinked_gate_path_refused_before_agent` x2 (dir, file): агент не вызван, коммитов не добавлено; `test_symlinked_gate_path_ignored_with_test_gate_cmd` |
| T-uo4-02 (повторная проверка) | та же проверка перед гейтом, патч откатывается, код 17 | `test_gate_path_turned_into_symlink_before_gate_reverts_patch` |

## Новые записи PROTECTED

`tests/conftest.py`, `tests/live_db_guard.py`, `pytest.ini`, `pyproject.toml`, `scripts/deploy.py`, `src/config.py`, `requirements.txt`, `requirements-dev.txt`. Кортеж нового состояния является надмножеством прежнего (проверено разбором по `git show HEAD:` до коммита).

## Код 17

«`scripts` или `scripts/gate.py` цели — символическая ссылка (риск подмены гейта)»: проверяется до агента (агент не запускается) и перед гейтом (патч откатывается). Описан в шапке адаптера и в таблице кодов `SKILL.md`. Остальные коды не менялись.

## Проверка

- Тесты адаптера: 18 до, 34 после (`34 passed`).
- Полный `backend/tests` chat-app: `277 passed`.
- Общий гейт chat-app (`python3 scripts/gate.py`): «ИТОГ: ЗЕЛЁНЫЙ» с первого прогона (chat-app 277, assistant-core 897, import-linter, security_shield, дрейф, боевая assistant.db не изменена).
- Мутационная проверка: на старом адаптере 15 из 16 новых тестов красные (оставшийся тест «ссылка игнорируется при AGY_GATE_CMD» проходит по определению); без повторной проверки перед гейтом красный тест отката.
- `git -C /opt/chat-app show --stat HEAD~1` (коммит `27886b3`): четыре файла, `scripts/gate.py` не затронут; `git status --short` chat-app после коммитов: только `?? .watchdog_disabled`.
- `bash -n scripts/agy_cross_ai.sh`: без ошибок.
- Агент agy и `chat-app.service` не запускались, `assistant-worker` не перезапускался, боевая БД не открывалась.

## Deviations from Plan

### По решению владельца

**1. Правка chat-app проведена исполнителем, а не оркестратором.** План 02-09 предусматривал чекпоинт Task 3 (человек-оркестратор запускает `/gsd-quick`). Владелец разрешил (опрос) провести её сразу из исполнения плана в `/opt/chat-app`; оформлена как quick 261010-cgx (PLAN, SUMMARY, строка в STATE.md chat-app). Чекпоинт поэтому не возвращался.

**2. Четвёртый файл в коммите chat-app.** По разрешению владельца в тот же коммит вошёл `backend/tests/test_security_shared.py`: `test_normalize_remote_formats` переведён на синтетические значения (`ExampleOrg`, `git.example.org`; 5 вхождений личного аккаунта, значение читалось из `config/persona.yaml` во время правки и не печаталось). Критерий плана «ровно три файла» заменён на «четыре файла»; покрытие форматов https, ssh://, scp и http с хвостовым слешем сохранено, тест зелёный.

### Auto-fixed Issues

**3. [Rule 1 - Bug] Двойной `state.advance-plan`.** Мой диагностический повтор команды сдвинул счётчик плана STATE.md дважды (12 из 15); значение возвращено правкой на 11 из 15. Побочных эффектов нет.

Остальное: план выполнен как написан.

## Known Stubs

Нет.

## Threat Flags

Нет новых поверхностей: изменения только ужесточают проверки адаптера.

## Остаточный долг

- Disposition WR-05 и WR-06 в `01-REVIEW-DISPOSITION.md` обновляет план 02-14.
- Требования плану не назначены (`requirements: []`), отметок в REQUIREMENTS.md нет.
- Живой прогон адаптера с реальным агентом не выполнялся (достаточно заглушек, по плану).

## Self-Check: PASSED

- FOUND: `02-CHATAPP-CROSSAI-QUICK-BRIEF.md`, `/var/tmp/gsd-phase02-crossai/baseline.txt`, `261010-cgx-SUMMARY.md`
- FOUND коммиты: assistant-core `04f55a2`; chat-app `27886b3`, `f92d95f`
