---
phase: 02-bezopasnost-privatnost-i-nahodki-revyu
plan: 10
subsystem: security
tags: [security-library, nda, air-gap, delegator, fail-closed, secf-01, d-10, pre-commit-hook]

requires:
  - phase: 02-bezopasnost-privatnost-i-nahodki-revyu
    provides: "02-06: audit_repository(workspaces=...); 02-07: chat-app на данных и делегаторе; 02-08: обёртка assistant-core на данных персоны"
provides:
  - "assistant-shared: библиотека безопасности без слов NDA и без ветки по подстроке пути; audit_repository(repo_path, check_staged_only, *, workspaces=None)"
  - "assistant-shared scripts/security_shield.py: тонкий делегатор в обёртку assistant-core (fail-closed)"
  - "tests/test_nda_script_parity.py: проверки D-10 (нет констант слов NDA, нет организаций и аккаунтов персоны в assistant_shared/security)"
affects: [02-11, chat-app, pre-commit-hook, phase-02-verification]

actuals:
  tokens: 5500
  tasks: 3
  commits: 1
plan_head_before: 16c3da57f5af7eacfd7e634cf372dd83989d5b73
plan_head_after: e4ac82268e356499fb8662ab64ebaea869f2bb4a
shared_commits: 3
shared_head_before: a6132f2205e1668f84f073ecc6d169549a092236
shared_head_after: 022bb3e342ff34981aa60032f1db1b6bd23d3c5f

tech-stack:
  added: []
  patterns:
    - "Удаление публичного имени общей библиотеки: предпроверка на копии при уже переведённых потребителях, затем делегатор, затем удаление"
    - "Делегатор shield: только stdlib, отсутствие обёртки/интерпретатора/сигнал дочернего процесса = rc=1"
    - "D-10: токены персоны читаются во время теста из load_persona, сравнение булево, значения не печатаются"

key-files:
  created:
    - /opt/assistant-shared/tests/test_security_shield_delegator.py
  modified:
    - /opt/assistant-shared/scripts/security_shield.py
    - /opt/assistant-shared/README.md
    - /opt/assistant-shared/assistant_shared/security/patterns.py
    - /opt/assistant-shared/assistant_shared/security/__init__.py
    - /opt/assistant-shared/assistant_shared/security/auditor.py
    - /opt/assistant-shared/tests/test_scan_file_content.py
    - /opt/assistant-shared/tests/test_workspace_matching.py
    - tests/test_nda_script_parity.py

key-decisions:
  - "Итоговая сигнатура: audit_repository(repo_path, check_staged_only=True, *, workspaces=None); workspaces=None даёт rc=1 без сканирования (D-20); параметров допуска слов нет (D-21)"
  - "custom_keywords=None у check_file_content и check_index_content означает «слов нет» (D-09)"
  - "Делегатор shared отличается от делегатора chat-app только текстом сообщения; файл предпроверки и настоящий файл идентичны"

patterns-established:
  - "Предпроверка итогового состояния общей библиотеки: копия вне репозиториев + PYTHONPATH, прогон потребителей до правки настоящей библиотеки"

requirements-completed: [SECF-01]

coverage:
  - id: C1
    description: "Итоговое состояние библиотеки доказано безопасным на копии до правки настоящей библиотеки (chat-app, shared, assistant-core)"
    requirement: SECF-01
    verification:
      - kind: integration
        ref: "/var/tmp/gsd-phase02-precheck/after.txt (chat-app 261 passed, shared 182 passed, assistant-core целевые 175 passed)"
        status: pass
    human_judgment: false
  - id: C2
    description: "Делегатор shared: проброс аргументов и кода, fail-closed при отсутствии каталога/обёртки/интерпретатора/прав, rc=1 при сигнале, hook блокирует секрет"
    requirement: SECF-01
    verification:
      - kind: unit
        ref: "/opt/assistant-shared/tests/test_security_shield_delegator.py (14 тестов, AST: нет импорта assistant_shared)"
        status: pass
    human_judgment: false
  - id: C3
    description: "Из библиотеки удалены слова NDA, прежняя ветка по подстроке пути и приватный маркер; audit_repository(repo) без данных даёт rc=1"
    requirement: SECF-01
    verification:
      - kind: unit
        ref: "tests/test_workspace_matching.py::test_default_workspaces_is_none_and_fails_closed, tests/test_scan_file_content.py::test_check_file_content_default_has_no_keywords"
        status: pass
    human_judgment: false
  - id: C4
    description: "D-10: в assistant_shared/security нет ни констант слов NDA, ни названий и псевдонимов организаций, ни частей аккаунтов персоны"
    requirement: SECF-01
    verification:
      - kind: unit
        ref: "tests/test_nda_script_parity.py::test_d10_library_has_no_nda_word_constants, ::test_d10_library_sources_have_no_organization_or_account_tokens (против старой библиотеки HEAD~: оба красные)"
        status: pass
    human_judgment: false
  - id: C5
    description: "Три репозитория зелёные после удаления имён: pytest shared 197, pytest chat-app 261, гейт assistant-core, гейт chat-app; находок shield --all в assistant-core ровно 3"
    requirement: SECF-01
    verification:
      - kind: integration
        ref: "python3 scripts/gate.py (assistant-core и chat-app): ИТОГ ЗЕЛЁНЫЙ"
        status: pass
    human_judgment: false

duration: 30min
completed: 2026-10-10
status: complete
---

# Phase 2 Plan 10: Удаление прежних имён из библиотеки безопасности Summary

**Из `assistant-shared` удалены слова NDA и ветка по подстроке пути; `scripts/security_shield.py` стал делегатором в обёртку assistant-core; тесты D-10 доказывают, что в `assistant_shared/security` нет ни слов NDA, ни токенов организаций и аккаунтов персоны.**

## Performance

- **Duration:** около 30 мин
- **Completed:** 2026-10-10
- **Tasks:** 3 (tracer, auto tdd, auto)
- **Коммиты:** assistant-core 1 (по ledger от 16c3da5), assistant-shared 3 (от a6132f2); коммит docs(02-10) идёт после

## Итоги предпроверки (Task 1)

Копия `/var/tmp/gsd-phase02-precheck/shared-final-2` (без `.git`, `__pycache__`) с итоговым состоянием библиотеки; настоящие репозитории не менялись. Результаты в `/var/tmp/gsd-phase02-precheck/after.txt`:

| Набор | Результат |
|---|---|
| полный pytest chat-app против копии (интерпретатор chat-app) | 261 passed |
| pytest `tests` копии (`.venv` assistant-core) | 182 passed |
| целевые тесты assistant-core (CLI shield, parity, synthetic persona, gate, gate red cases) | 175 passed |

Импорт против копии подтверждён: `assistant_shared.security.__file__` в копии, константы слов NDA нет.

## Итоговая сигнатура

`audit_repository(repo_path: Path, check_staged_only: bool = True, *, workspaces: Any = None) -> int`. `None` (и нечитаемые данные) даёт rc=1 «данные рабочих пространств недоступны» без сканирования (D-20); `()` означает «пространств нет»; параметров допуска слов нет (D-21). `check_file_content` и `check_index_content`: `custom_keywords=None` = «слов нет». Удалены: `CORPORATE_NDA_KEYWORDS` с `_KW_*`, `_audit_repository_legacy`, `_DefaultWorkspaces` и `_DEFAULT_WORKSPACES`.

## Результаты итоговой проверки (после удаления)

| Проверка | Результат |
|---|---|
| pytest shared | 197 passed (было 182; +14 делегатор, +1 умолчание workspaces) |
| pytest chat-app | 261 passed (число не менялось) |
| целевые тесты assistant-core (parity, CLI, synthetic) | 23 passed |
| гейт assistant-core | ИТОГ: ЗЕЛЁНЫЙ (897 core, 197 shared, SHA-256 боевой БД до/после совпали) |
| гейт chat-app | ИТОГ: ЗЕЛЁНЫЙ со второго прогона (см. «Заметки»); 261 chat-app, 897 core |
| `shield . --all` в assistant-core | rc=1, находок ровно 3, все в `config/persona.yaml` (как до фазы, D-21) |
| `shield --all` в assistant-shared (через делегатор) | rc=0, находок нет |
| слово allowance в библиотеке и трёх обёртках | не найдено |
| `git -C /opt/chat-app status --short` | только `?? .watchdog_disabled` (существовал до фазы) |

Замороженные списки обоих гейтов не менялись и не росли; `scripts/gate.py` обоих репозиториев не менялись.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Тест shared закреплял прежнее умолчание слов**
- **Found during:** Task 1 (предпроверка, подготовка копии) и Task 3
- **Issue:** `tests/test_scan_file_content.py::test_check_file_content_default_keywords_remain_the_legacy_list` импортировал удаляемую константу и утверждал прежнее умолчание. План 02-06 его не переводил (он намеренно ждал плана 02-10), поэтому без правки pytest shared краснел бы.
- **Fix:** заменён на `test_check_file_content_default_has_no_keywords`: без `custom_keywords` и с `None` находок нет, явно заданное слово даёт одну находку в публичном режиме и ноль в NDA-режиме. Проверка не ослаблена: она фиксирует новый контракт D-09.
- **Files modified:** `/opt/assistant-shared/tests/test_scan_file_content.py`
- **Commit:** 022bb3e (shared)

**2. [Rule 2 - Missing critical] Тест умолчания `workspaces`**
- **Found during:** Task 3
- **Issue:** критерий «`audit_repository(repo)` без аргументов возвращает 1» и «умолчание `None`» не покрывался тестом (покрыт был явный `workspaces=None`).
- **Fix:** добавлен `test_default_workspaces_is_none_and_fails_closed` (default is None, rc=1, нет сканирования).
- **Files modified:** `/opt/assistant-shared/tests/test_workspace_matching.py`
- **Commit:** 022bb3e (shared)

### Уточнения без отклонения от замысла

- В копию для предпроверки положены итоговые варианты делегатора shared и обновлённого теста (иначе старая обёртка shared и тест прежнего умолчания краснили бы набор копии по причине, не связанной с риском для потребителей). Настоящие файлы затем созданы побайтно такими же (`diff -rq` копии и настоящего репозитория: расхождения только README и новый файл тестов делегатора).
- Первый полный прогон chat-app против копии дал `1 failed, 260 passed`: `test_concurrent_write.py::test_concurrent_write_two_processes` (`OperationalError`, нагрузка на SQLite между процессами). Тест к библиотеке безопасности не обращается; изолированно он зелёный на копии (дважды) и на настоящей библиотеке; повторный полный прогон `261 passed`. Записано в `first-run-flaky-note.txt`, в `after.txt` вошёл полный зелёный прогон.
- Критерий «`git -C /opt/chat-app status --short` пуст» буквально невыполним: `.watchdog_disabled` лежит там до начала фазы (см. 02-07); других изменений нет.
- Task 3: первый прогон гейта chat-app дал КРАСНЫЙ только по строке «хеш боевой БД изменился во время прогона»: процесс `assistant-worker.service` (active, работает круглосуточно) записал в `assistant.db` во время двухминутного прогона (mtime файла 15:16:34 пришёлся на него). Тесты БД не открывают, гейт assistant-core в то же время показал совпадение хешей. Повторный прогон без правок: ИТОГ ЗЕЛЁНЫЙ, mtime БД не менялся. Это гонка гейта с живым демоном, а не дефект правки; код и гейт не менялись. Стоит учесть при ревизии гейта (отдельная задача, не этот план).

**Total deviations:** 2 auto-fixed (1 blocking, 1 missing-critical). **Impact:** оба — тесты shared под итоговый контракт, код библиотеки в точности соответствует проверенной копии.

## Auth gates

None.

## Known Stubs

None.

## Threat Flags

None. T-02-34 (красный pytest chat-app) закрыт предпроверкой на копии и итоговой проверкой трёх репозиториев; T-02-35 (молчаливый проход делегатора) закрыт тестами отсутствия каталога, обёртки, интерпретатора, прав исполнения и сигнала; T-02-36 (литералы в библиотеке) закрыт тестами D-10; T-02-37 принят (ASSISTANT_CORE_DIR из доверенного окружения, задокументировано в docstring делегатора).

## Остаточный долг (вне области плана)

- **chat-app:** `backend/tests/test_security_shared.py` (функция `test_normalize_remote_formats`) по-прежнему содержит литерал личного аккаунта (5 вхождений, проверено по данным персоны, значение не печаталось). Это долг из 02-07; chat-app в этом плане read-only. Закрывается малой задачей `/gsd-quick` в chat-app (заменить на синтетический `example.org`). Библиотеку и критерии SECF-01 он не затрагивает; shield и оба гейта его не видят.
- **assistant-shared:** `tests/test_migrations.py` и схема `assistant_shared/db/migrations/0001_initial_schema.sql` содержат название организации как данные схемы (как оговорено в «Flagged assumptions»; D-10 охватывает только `assistant_shared/security`).
- **Гейт:** проверка хеша боевой БД гонится с работающим `assistant-worker.service` (см. выше).
- **REQUIREMENTS.md:** критерии SECF-01 для этого плана проверены, но чекбокс не отмечен: идентификатор объявляют ещё планы 02-14 и 02-15 без SUMMARY, и защита общих идентификаторов (`requirements.ready-ids`, #2388) не даёт отметить его раньше них. Отметка ставится при завершении последнего из объявляющих планов.
- `config/persona.yaml` по-прежнему даёт 3 находки shield (D-21); коммит файла персоны остаётся разовым обходом хука по согласию владельца (план 02-11).

## Self-Check: PASSED

- `/opt/assistant-shared/scripts/security_shield.py`, `/opt/assistant-shared/tests/test_security_shield_delegator.py`, `tests/test_nda_script_parity.py` найдены
- коммиты shared `b99eb46`, `7124251`, `022bb3e` и assistant-core `e4ac822` существуют (проверка `merge-base --is-ancestor`)
- `grep` по `/opt/assistant-shared/assistant_shared/security` не находит `CORPORATE_NDA_KEYWORDS`, `_audit_repository_legacy`, `_DEFAULT_WORKSPACES`
