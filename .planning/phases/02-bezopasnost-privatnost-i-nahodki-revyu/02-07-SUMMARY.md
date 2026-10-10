---
phase: 02-bezopasnost-privatnost-i-nahodki-revyu
plan: 07
subsystem: security
tags: [chat-app, gsd-quick, nda, air-gap, secf-01, secf-02, delegator, precheck]

requires:
  - phase: 02-bezopasnost-privatnost-i-nahodki-revyu
    provides: "02-01: collect_protected_keywords, NdaRemoteRule.forbidden_keywords; 02-06: audit_repository(workspaces=...), match_workspace"
provides:
  - "02-CHATAPP-QUICK-BRIEF.md: задание /gsd-quick для chat-app, основанное на измеренном списке падений"
  - "chat-app переведён на данные пространств: web-аудит ищет слова NDA других пространств, scripts/security_shield.py - делегатор в assistant-core, тесты не ссылаются на CORPORATE_NDA_KEYWORDS"
  - "Копия итогового состояния библиотеки /var/tmp/gsd-phase02-precheck/shared-final для повторных проверок плана 02-10"
affects: [02-08, 02-09, 02-10, chat-app, security_shield]

actuals:
  tokens: 14000
  tasks: 3
  commits: 1
plan_head_before: 8701e8edf423efce9289e3e4f02828f49fd134fb
plan_head_after: 72899d9482937ad393bd391bb05eb4a7d43948ef

tech-stack:
  added: []
  patterns:
    - "Потребитель (chat-app) делегирует CLI-проверку assistant-core: каталог из ASSISTANT_CORE_DIR, интерпретатор .venv assistant-core, fail-closed rc=1 при отсутствии"
    - "Предпроверка удаления имён из общей библиотеки на копии через PYTHONPATH до правки настоящей библиотеки"

key-files:
  created:
    - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-CHATAPP-QUICK-BRIEF.md
  modified: []

key-decisions:
  - "Правка chat-app проведена только процедурой /gsd-quick в репозитории chat-app (D-12, D-18); владелец разрешил /opt/chat-app рабочим каталогом, правку провёл исполнитель в chat-app"
  - "test_security_audit_all: основной тест на синтетике во временной папке (audited_count == 4), живой вариант с замороженным набором находок (решение владельца, вариант A)"
  - "Слова NDA убраны из архивного 04-REVIEW.md в chat-app (решение владельца); scripts/gate.py chat-app не менялся (D-15)"

patterns-established:
  - "Задание для /gsd-quick содержит раздел «Предпроверка» с числами из измерения и допустимым исключением против копии"

requirements-completed: []
requirements-progress: [SECF-01, SECF-02]

coverage:
  - id: C1
    description: "Предпроверка на копии итоговой библиотеки измерила зависимость chat-app от удаляемых имён: 19 упавших, 226 прошло, 1 ошибка сбора; настоящие репозитории не менялись"
    requirement: SECF-01
    verification:
      - kind: other
        ref: "/var/tmp/gsd-phase02-precheck/before.txt, failed-files.txt (7 файлов)"
        status: pass
    human_judgment: false
  - id: C2
    description: "Задание 02-CHATAPP-QUICK-BRIEF.md: девять разделов плюс «Предпроверка» и «Известное последствие», все файлы из failed-files.txt упомянуты, запрещённых слов и адресов из данных персоны нет"
    requirement: SECF-02
    verification:
      - kind: other
        ref: "автоматические проверки Task 2 (структура, поиск по данным персоны без печати значений): OK"
        status: pass
    human_judgment: false
  - id: C3
    description: "chat-app переведён на данные: web-аудит передаёт слова всех NDA-пространств, обёртка shield стала делегатором, тесты переведены, chat-app зелёный на текущей библиотеке"
    requirement: SECF-02
    verification:
      - kind: integration
        ref: "cd /opt/chat-app && backend/.venv/bin/pytest backend/tests -p no:cacheprovider -q: 261 passed (было 251)"
        status: pass
      - kind: integration
        ref: "python3 scripts/gate.py chat-app: ИТОГ ЗЕЛЁНЫЙ (проверено оркестратором); gate assistant-core: ЗЕЛЁНЫЙ (883 core, 182 shared)"
        status: pass
    human_judgment: false
  - id: C4
    description: "Против копии итогового состояния падают только тесты, запускающие обёртку assistant-core через делегатор (допустимое исключение, закрывается планом 02-08)"
    requirement: SECF-01
    verification:
      - kind: integration
        ref: "PYTHONPATH=/var/tmp/gsd-phase02-precheck/shared-final pytest backend/tests: 8 failed, 253 passed (5 test_pre_commit_hook, 2 test_shield_delegator, 1 test_cr02_flag_first_is_not_treated_as_path)"
        status: pass
    human_judgment: false

duration: 90min
completed: 2026-10-10
status: complete
---

# Phase 2 Plan 07: Перевод chat-app на данные пространств (предпроверка, задание, /gsd-quick) Summary

**Правка chat-app проверена на копии итоговой библиотеки, оформлена заданием и проведена через /gsd-quick: web-аудит находит слова NDA других пространств, `scripts/security_shield.py` стал делегатором в assistant-core (fail-closed), тесты потребителя больше не зависят от удаляемой константы; chat-app зелёный на текущей библиотеке (261 passed).**

## Performance

- **Duration:** около 90 мин (Task 1-2 исполнитель, Task 3 оркестратор с владельцем)
- **Completed:** 2026-10-10
- **Tasks:** 3 (tracer, auto, checkpoint:human-action)
- **Files:** 1 в assistant-core (задание); 12 файлов в chat-app (коммит 568ecf2)

## Accomplishments

- Task 1: копия `/opt/assistant-shared` без `.git` приведена к итоговому состоянию (константа слов NDA, её экспорт, `_audit_repository_legacy` и маркер умолчания удалены, `custom_keywords=None` означает «слов нет», `workspaces=None` по умолчанию). Полный pytest chat-app против копии: **19 failed, 226 passed, 1 error** (ошибка сбора `test_security_shared.py`). Для получения полного списка пришлось добавить `--continue-on-collection-errors` (иначе pytest прерывается на первом модуле).
- Файлы из `failed-files.txt`: `test_nda_equivalence.py` (5), `test_persona_api.py` (1), `test_pre_commit_hook.py` (5), `test_security_shared.py` (ошибка сбора), `test_shield_parity.py` (1), `test_shield_regressions.py` (6), `test_synthetic_persona.py` (1). `test_shield_parity.py` в список исследования не входил.
- Task 2: `02-CHATAPP-QUICK-BRIEF.md` (142 строки): контекст, текущее и требуемое поведение, раздел «Предпроверка», итоговый контракт библиотеки, перевод тестов по файлам, ограничения, проверка перед коммитом с допустимым исключением, «Известное последствие».
- Task 3 (оркестратор): правка chat-app по заданию.

## Chat-app: что изменено (Task 3)

Коммиты в `/opt/chat-app` (ветка `master`):

| Коммит | Содержание |
|---|---|
| `568ecf2` | `fix(security)`: `backend/app/api/v1/security.py` (слова всех NDA-пространств в оба вызова `audit_path`), `scripts/security_shield.py` (делегатор), перевод тестов, новые `nda_helpers.py`, `test_shield_delegator.py`, `test_web_nda_keywords.py`, расширен `test_security_api.py`; 12 файлов, +450/-118 |
| `d4e4696` | docs quick-261010-ivt (PLAN, SUMMARY, STATE chat-app) |
| `07a0b86` | маскирование слов NDA в архивном `04-REVIEW.md` |

Каталог quick: `/opt/chat-app/.planning/quick/261010-ivt-shield-rules-from-workspace-data-web-aud/`.

## Проверки

| Проверка | Результат |
|---|---|
| pytest chat-app против настоящей библиотеки | 261 passed (было 251); повторно прогнан мной после чекпоинта |
| pytest chat-app против копии итогового состояния | 8 failed, 253 passed: только допустимое исключение (5 `test_pre_commit_hook.py`, 2 `test_shield_delegator.py`, `test_cr02_flag_first_is_not_treated_as_path`); все запускают обёртку assistant-core, которая до плана 02-08 импортирует удаляемую константу |
| общий гейт chat-app | «ИТОГ: ЗЕЛЁНЫЙ» (оркестратор, повторно) |
| гейт assistant-core | «ИТОГ: ЗЕЛЁНЫЙ» (883 core, 182 shared) |
| `grep -c assistant_shared /opt/chat-app/scripts/security_shield.py` | 0 |
| `scripts/gate.py` chat-app в коммитах | не затронут |
| `git -C /opt/chat-app status --short` | только `?? .watchdog_disabled` (существовал до работ) |
| `/opt/assistant-shared` | не менялся (чист) |

## Известное последствие для владельца

После рестарта `chat-app.service` (он заморожен и в этом плане не перезапускался) web-аудит публичного пространства assistant-core покажет находки по слову NDA в `config/persona.yaml`: файл объявляет слова и лежит в публичном репозитории. Это верная находка о публичном репозитории, а не дефект правки; решение (убрать слова из публичного репозитория) относится к Phase 8. Решение владельца D-21 это не меняет: допуска слов для файла персоны нет ни в web, ни в CLI, shield и hook не ослаблены, три известные находки режима `--all` и замороженные списки гейтов не растут, коммиты `config/persona.yaml` в фазе идут разовым обходом хука по согласию владельца (план 02-11).

**chat-app.service не перезапускался.**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Предпроверка требовала опции продолжения после ошибки сбора**
- **Found during:** Task 1
- **Issue:** команда плана остановилась на ошибке сбора `test_security_shared.py` («1 error in 5.00s»), список падений не получен.
- **Fix:** повторный прогон с `-rfE --continue-on-collection-errors`; в `before.txt` результат повторного прогона.
- **Files modified:** `/var/tmp/gsd-phase02-precheck/before.txt`
- **Commit:** нет (файл вне репозиториев)

### Отклонения при выполнении Task 3 (решения владельца)

- `test_security_audit_all` не входил в предпроверку: тест зависел от живого набора пространств. Вариант A (решение владельца): основной тест на синтетике во временной папке (`audited_count == 4`), живой вариант с замороженным набором находок. Замороженный живой тест теперь видит 2 из 3 находок (подмножество).
- Гейт chat-app был красным из-за слова NDA в архивном `04-REVIEW.md` (файл переехал при архивации v2.0, коммит `13c674e`). Владелец выбрал убрать слова из файла; `scripts/gate.py` не менялся (D-15).
- `/opt/chat-app` разрешён как рабочий каталог (решение владельца): правку провёл исполнитель непосредственно в chat-app по процедуре /gsd-quick, а не отдельная сессия.

### Процессные заметки

- `git -C /opt/chat-app status --short` не пуст: `?? .watchdog_disabled` лежит там до начала работ; буквальный критерий «пуст» не выполним без вмешательства в чужой репозиторий.
- Задачи 1 не имеют коммита: результаты лежат вне репозиториев. `commits: 1` измерено от ledger `.git/gsd-plan-head-before-02-07` (8701e8e) на момент записи SUMMARY (коммит задания 72899d9); завершающий коммит docs(02-07) идёт после.
- SECF-01 в REQUIREMENTS.md не отмечен: литералы остаются в библиотеке до плана 02-10, обёртка assistant-core переключается планом 02-08. SECF-02 отмечен планом 02-01.

## Остаточный долг

- В chat-app `backend/tests/test_security_shared.py::test_normalize_remote_formats` остался старый литерал личного аккаунта (вне задания). Учесть при ревизии литералов в плане 02-10 или отдельной малой задачей /gsd-quick.
- Тесты `test_pre_commit_hook.py`, `test_shield_delegator.py` и `test_cr02_flag_first...` краснеют против копии итогового состояния, пока не заменена обёртка assistant-core (план 02-08); перед планом 02-10 повторить прогон против копии и убедиться, что красных нет.

## Для плана 02-08

`tests/test_synthetic_persona.py` в assistant-core нужно перевести так же, как в chat-app: слова брать из фикстуры `default_persona_config`, без `CORPORATE_NDA_KEYWORDS` и `_load_shield`; проверить наличие фикстуры в `conftest.py` assistant-core (файл уже входит в `files_modified` 02-08).

## Known Stubs

None.

## Threat Flags

None. Новых сетевых точек и путей аутентификации в assistant-core нет; в chat-app делегатор fail-closed (T-02-23), подмена `ASSISTANT_CORE_DIR` принята и задокументирована (T-02-25). Задание не содержит слов NDA и адресов (T-02-24, проверено по данным персоны).

## Next Phase Readiness

План 02-08 заменяет обёртку assistant-core данными персоны (после чего тесты исключения против копии станут зелёными); план 02-10 удаляет прежние имена из библиотеки, chat-app к этому готов (на копии итогового состояния падают только перечисленные тесты).

## Self-Check: PASSED

- `02-CHATAPP-QUICK-BRIEF.md`, `/var/tmp/gsd-phase02-precheck/before.txt`, `failed-files.txt` найдены
- коммит `72899d9` (assistant-core) и `568ecf2`, `d4e4696`, `07a0b86` (chat-app) существуют; `scripts/gate.py` в них не затронут
