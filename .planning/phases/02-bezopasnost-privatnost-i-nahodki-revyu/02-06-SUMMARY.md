---
phase: 02-bezopasnost-privatnost-i-nahodki-revyu
plan: 06
subsystem: security
tags: [assistant-shared, nda, air-gap, secf-01, secf-02, match_workspace, fail-closed]

requires:
  - phase: 02-bezopasnost-privatnost-i-nahodki-revyu
    provides: "02-01: scan_file_content, collect_protected_keywords, NdaRemoteRule.forbidden_keywords"
provides:
  - "rules.py: CLEARANCE_STRICTNESS и match_workspace(repo_path, remote_urls, workspaces)"
  - "auditor.py: audit_repository(repo_path, check_staged_only=True, *, workspaces=<приватный маркер>) с NDA-режимом по данным"
  - "auditor.py: _audit_repository_legacy (прежнее тело, удаляется планом 02-10)"
  - "экспорты match_workspace и CLEARANCE_STRICTNESS в assistant_shared.security"
  - "tests/test_workspace_matching.py (34 теста), паритет D-13 в tests/test_shield_parity.py (3 теста)"
affects: [02-08, 02-10, security_shield, chat-app]

actuals:
  tokens: 11900
  tasks: 3
  commits: 3
plan_head_before: c09124879d92354538cf747cff1ea5c531b06ddf
plan_head_after: a6132f2205e1668f84f073ecc6d169549a092236

tech-stack:
  added: []
  patterns:
    - "Режим NDA определяется данными: сопоставление по resolve()-пути и нормализованному remote, подстрока пути не используется"
    - "Приватный объект-маркер умолчания отличает «аргумент не передан» (прежняя схема) от None (данные недоступны, rc=1) и () (данных нет)"

key-files:
  created:
    - /opt/assistant-shared/tests/test_workspace_matching.py
  modified:
    - /opt/assistant-shared/assistant_shared/security/rules.py
    - /opt/assistant-shared/assistant_shared/security/auditor.py
    - /opt/assistant-shared/assistant_shared/security/__init__.py
    - /opt/assistant-shared/tests/test_shield_parity.py
    - /opt/assistant-shared/tests/test_security_shared.py
    - /opt/assistant-shared/tests/test_shield_regressions.py

key-decisions:
  - "workspaces=None даёт rc=1 и SECURITY SHIELD ERROR без сканирования; нестрого итерируемое значение (число, объект) трактуется так же (fail-closed)"
  - "Несопоставленный репозиторий при наличии данных проверяется как публичный; предупреждение печатается строкой с ⚠️ и никогда с 🚨, чтобы гейт assistant-core не разобрал его как находку"
  - "Пересекающиеся пространства сопоставляются в строжайшее; слова самого NDA в таком репозитории не ищутся (принятое допущение T-02-21, закреплено тестом)"
  - "Тест вызова audit_repository без workspaces (прежняя схема) в shared не оставлен: критерий приёмки требует workspaces= во всех вызовах; совместимость прежней ветки проверяется полным pytest chat-app"

patterns-established:
  - "Коммиты плана в /opt/assistant-shared (ветка master), SUMMARY и STATE/ROADMAP в assistant-core"

requirements-completed: []
requirements-progress: [SECF-01]

coverage:
  - id: C1
    description: "NDA-режим CLI-аудита определяется данными: сопоставление по resolve()-пути (точный, вложенный, символическая ссылка) и по нормализованному remote (ssh-алиас), строжайший побеждает, неизвестный уровень строжайший, относительный путь и корень игнорируются"
    requirement: SECF-01
    verification:
      - kind: unit
        ref: "tests/test_workspace_matching.py (15 тестов match_workspace)"
        status: pass
      - kind: integration
        ref: "tests/test_workspace_matching.py#test_nda_by_path_with_forbidden_remote_is_blocked, #test_nda_by_path_with_safe_remote_passes, #test_nda_matched_by_remote_only"
        status: pass
    human_judgment: false
  - id: C2
    description: "Fail-closed: workspaces=None rc=1 без сканирования; сбой git при чтении remote, restricted_nda без правил remote, некорректные правила, неизвестный уровень допуска дают нарушение CRITICAL; () и несопоставленный репозиторий допустимы с предупреждением без значка 🚨"
    requirement: SECF-01
    verification:
      - kind: integration
        ref: "tests/test_workspace_matching.py#test_none_workspaces_fail_closed, #test_non_iterable_workspaces_fail_closed, #test_empty_workspaces_scan_as_public_with_warning_not_violation, #test_nda_workspace_without_remote_rules_is_violation, #test_unknown_clearance_is_violation, #test_remote_listing_failure_is_violation, #test_malformed_nda_rules_are_violation"
        status: pass
    human_judgment: false
  - id: C3
    description: "Слова NDA ищутся без учёта регистра везде, кроме репозитория, сопоставленного с NDA; допуска вхождений нет даже для config/persona.yaml в обоих режимах чтения; сигнатура ровно repo_path, check_staged_only, workspaces"
    requirement: SECF-02
    verification:
      - kind: integration
        ref: "tests/test_workspace_matching.py#test_nda_word_found_in_public_repo_case_insensitive_but_legal_in_nda_repo, #test_persona_file_has_no_exemption_for_nda_words (2 режима), #test_audit_repository_signature_has_no_tolerance_parameters"
        status: pass
      - kind: other
        ref: "! grep -rniq allowance /opt/assistant-shared/assistant_shared/security (0 вхождений)"
        status: pass
    human_judgment: false
  - id: C4
    description: "Паритет web и CLI D-13 на нормализованных множествах (файл, вид, имя) и явном ожидаемом множестве из четырёх элементов: публичный режим; NDA-сопоставленный репозиторий (слово не ищется ни в одном пути, три остальных равны); чистый репозиторий"
    requirement: SECF-02
    verification:
      - kind: integration
        ref: "tests/test_shield_parity.py#test_parity_public_mode_on_synthetic_fixtures, #test_parity_nda_matched_repository_does_not_search_words, #test_parity_fixture_with_clean_files_only_is_empty_on_both_paths"
        status: pass
    human_judgment: false
  - id: C5
    description: "Аддитивность: потребитель chat-app и обёртка assistant-core остаются зелёными, прежние тесты shared переведены на итоговую форму (workspaces=(), без CORPORATE_NDA_KEYWORDS и литералов)"
    requirement: SECF-01
    verification:
      - kind: integration
        ref: "cd /opt/chat-app && backend/.venv/bin/pytest backend/tests -p no:cacheprovider -q (251 passed); python3 scripts/gate.py в assistant-core (ЗЕЛЁНЫЙ, shared 182 passed)"
        status: pass
    human_judgment: false

duration: 40min
completed: 2026-10-10
status: complete
---

# Phase 2 Plan 06: NDA-режим CLI-аудита по данным рабочих пространств Summary

**`audit_repository` в assistant-shared определяет NDA-режим по данным пространств (`match_workspace` по resolve()-пути и нормализованному remote, строжайший допуск побеждает) и fail-closed при отсутствии данных; паритет web/CLI доказан на синтетических фикстурах; прежняя ветка осталась рядом до плана 02-10.**

## Performance

- **Duration:** около 40 мин
- **Completed:** 2026-10-10
- **Tasks:** 3 (tracer, tdd-auto, auto)
- **Files:** 7 в репозитории shared (1 новый, 6 изменённых)

## Accomplishments

- `rules.py`: `CLEARANCE_STRICTNESS` (public 0, internal 1, restricted_nda 2) и `match_workspace`. Сопоставление только по реальному пути (`resolve()`: сам путь или вложенный) и нормализованному remote; относительные пути и корень файловой системы в данных игнорируются; не-Mapping элементы пропускаются; сбой `resolve()` не роняет аудит. Выбирается строжайший, при равенстве первый по порядку данных; неизвестный и нестроковый уровень строжайший.
- `auditor.py`: прежнее тело перенесено в `_audit_repository_legacy`; новая `audit_repository` различает три состояния `workspaces`: маркер умолчания (прежняя схема), `None` (rc=1), кортеж данных (включая `()`).
- Профиль и правила: для `restricted_nda` заголовок «RESTRICTED (NDA workspace: id)», правила remote берутся из `nda_rule_for` (все remote и push-URL, пустые правила дают CRITICAL), слова NDA не ищутся; для остальных ищутся слова всех NDA-пространств (`collect_protected_keywords`).
- Тесты: 34 теста сопоставления и контракта, 3 теста паритета D-13, прежние тесты переведены. Все слова собраны из частей, адреса `example.org`.

## Сигнатуры

- `match_workspace(repo_path: Path, remote_urls: Iterable[str], workspaces: Iterable[Mapping[str, Any]]) -> Mapping[str, Any] | None`
- `audit_repository(repo_path: Path, check_staged_only: bool = True, *, workspaces: Any = <_DEFAULT_WORKSPACES>) -> int` (параметров допуска слов нет, D-21)
- `_audit_repository_legacy(repo_path, check_staged_only=True) -> int` (приватная, удаляется планом 02-10)

## Состояния вывода audit_repository (новая ветка)

| Состояние | Результат |
|---|---|
| не git-репозиторий | rc=1, «SECURITY SHIELD ERROR ... не является git-репозиторием» |
| `workspaces=None` или не итерируемое | rc=1, «SECURITY SHIELD ERROR: данные рабочих пространств недоступны...», без «Scanning» |
| сопоставлен с `restricted_nda` | «🔒 RESTRICTED (NDA workspace: id)», правила remote, слова не ищутся |
| сопоставлен с другим допуском | «🌐 PUBLIC / ACADEMIC (workspace: id)», слова NDA ищутся |
| не сопоставлен (в том числе `()`) | «🌐 PUBLIC / ACADEMIC (not matched)» и отдельная строка «   ⚠️ Репозиторий не сопоставлен ...», слова ищутся |
| сбой git при чтении remote / нет правил remote / некорректные правила / неизвестный допуск | нарушение «CRITICAL: ...» с префиксом, который разбирает гейт, rc=1 |

## Проверки

| Проверка | До | После |
|---|---|---|
| pytest shared | 145 passed | 182 passed |
| полный pytest chat-app | - | 251 passed |
| `python3 scripts/gate.py` (assistant-core) | - | ЗЕЛЁНЫЙ (883 теста core, 182 shared, живая БД не менялась) |
| grep allowance в `assistant_shared/security` | 0 | 0 |
| реальные слова NDA, литерал аккаунта, «закреплено до Phase 2» в тестах shared | - | 0 вхождений |

## Task Commits

Коммиты сделаны в `/opt/assistant-shared` (ветка `master`):

1. **Task 1 (tracer): match_workspace и audit_repository(workspaces=...)** - `aae4fb8` (feat). Tracer проверен сквозным тестом (репозиторий внутри пути NDA-пространства с запрещённым remote даёт rc=1, с безопасным rc=0) и полным прогоном shared до расширения.
2. **Task 2: fail-closed контракт, D-21, паритет D-13** - `e803825` (test)
3. **Task 3: перевод прежних тестов shared** - `a6132f2` (test)

**Plan metadata:** коммит docs(02-06) в assistant-core (SUMMARY, STATE, ROADMAP).

## Decisions Made

См. frontmatter.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Нестрого итерируемое и некорректное значение данных**
- **Found during:** Task 1
- **Issue:** план требует rc=1 только для `None`; число или объект в `workspaces` дали бы `TypeError` внутри аудита, а некорректные `forbidden_remote_substrings` (не итерируемое значение) падали бы в `nda_rule_for`, а не давали нарушение; нехэшируемый `clearance` падал бы на проверке `in`.
- **Fix:** не итерируемое значение даёт rc=1 как `None`; `TypeError` из `nda_rule_for` даёт нарушение «CRITICAL: правила NDA-пространства заданы некорректно (fail-closed)»; проверка допуска сначала проверяет `isinstance(str)`. Тесты `test_non_iterable_workspaces_fail_closed`, `test_malformed_nda_rules_are_violation`.
- **Files modified:** `assistant_shared/security/auditor.py`
- **Commit:** `aae4fb8`

### Процессные заметки

- Тест вызова `audit_repository` БЕЗ `workspaces` (прежняя схема) был написан в Task 2 и удалён в Task 3: критерий приёмки Task 3 требует `workspaces=` во всех вызовах в `tests/`. Совместимость прежней ветки подтверждена полным pytest chat-app (251 passed) и гейтом assistant-core, обёртка которого вызывает `audit_repository` без `workspaces`.
- `git -C /opt/chat-app status --short` не пуст: там лежит `?? .watchdog_disabled`, файл существовал до начала плана (виден в начальном состоянии), мной не создавался и не менялся; изменений отслеживаемых файлов chat-app нет. Критерий «пуст» в буквальном виде не выполним без вмешательства в чужой репозиторий.
- Tracer-вставка: `tdd="true"` в Task 2 без RED-фазы: код Task 1 уже существовал, тесты Task 2 характеризуют его (дефектов не выявили, правок кода Task 1 по итогам Task 2 не потребовалось).
- SECF-01 в REQUIREMENTS.md намеренно НЕ отмечен выполненным: литералы (подстрока пути, личный аккаунт, `CORPORATE_NDA_KEYWORDS`) остаются в прежней ветке до плана 02-10, обёртка переключается планом 02-08. `requirements mark-complete` был вызван, результат откатан; SECF-02 уже был отмечен планом 02-01.
- Команда `state advance-plan` по ошибке вызвана дважды, указатель «Plan» в STATE.md исправлен вручную на 7 of 15.
- Журнал базового коммита в assistant-core записан вручную в `.git/gsd-plan-head-before-02-06` (3fcf59d), в shared — в его `.git` (c091248).
- Авторская идентичность в `/opt/assistant-shared` по-прежнему не настроена (git выдаёт предупреждение), конфигурация не менялась.

## Known Stubs

None.

## Threat Flags

None. Новых сетевых точек и путей аутентификации нет; поверхность сузилась (сопоставление по данным вместо подстроки имени каталога). Предупреждения и ошибки не печатают слова NDA и адреса правил remote; в заголовке только идентификатор пространства.

## Issues Encountered

Один прогон тестов занял 64 с вместо 2 с из-за нагрузки на VPS; повторный прогон прошёл за 3 с, дефекта нет.

## Next Phase Readiness

План 02-08 может передать в `audit_repository(..., workspaces=...)` данные персоны из обёртки assistant-core; план 02-10 удалит `_audit_repository_legacy`, маркер умолчания и `CORPORATE_NDA_KEYWORDS`. Репозитории assistant-shared и временные репозитории тестов не входят в `workspaces` персоны и проверяются как публичные с предупреждением `⚠️`.

## Self-Check: PASSED

- test_workspace_matching.py: найден; rules.py, auditor.py, __init__.py изменены
- коммиты `aae4fb8`, `e803825`, `a6132f2` являются предками HEAD в `/opt/assistant-shared`
