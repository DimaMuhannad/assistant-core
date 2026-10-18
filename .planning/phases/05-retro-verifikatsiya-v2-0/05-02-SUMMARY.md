# Phase 5 Plan 02: V2-06 верификация (ISO-01..ISO-04, FIN-01) Summary

**V2-06-VERIFICATION.md по фазе 06 v2.0: ISO-01, ISO-03, FIN-01 passed (трасса); ISO-02 gap (метаданные NDA-писем уходят во внешний LLM, против текста v2.0); ISO-04 gap (нестабильная параллельная запись подтверждений двух персон, `database is locked` в 2 из 9 прогонов). Код не менялся.**

---
phase: 05-retro-verifikatsiya-v2-0
plan: 02
subsystem: verification
tags: [retro-verification, v2.0, nda, air-gap, persona-isolation, zero-trust-scopes, hardcode-scanner, flaky-test]

requires:
  - phase: 03-vladenie-shemoy-bd
    provides: миграция 0003 (pending_confirmations с persona_id)
provides:
  - V2-06-VERIFICATION.md с вердиктами ISO-01 (passed), ISO-02 (gap), ISO-03 (passed), ISO-04 (gap), FIN-01 (passed, формально), трассой file:line и прогонами
  - доказательство, что метаданные NDA-писем (sender_name, sender_email, subject, date_sent) уходят во внешний LLM по трём путям диалога и в вечернем дайджесте
  - gap ISO-04: сбой теста конкурентной записи подтверждений
affects: [05-08]

key-files:
  created:
    - .planning/phases/05-retro-verifikatsiya-v2-0/V2-06-VERIFICATION.md
    - .planning/phases/05-retro-verifikatsiya-v2-0/05-02-SUMMARY.md

key-decisions:
  - "ISO-02 gap против текста v2.0 (решение владельца №5): маскировка тела, snippet и вложений работает, метаданные нет. Оформление ISO-05 (Phase 999.4) остаётся за планом 05-08"
  - "ISO-04 gap, а не passed: тест test_concurrent_confirmations_isolation упал с sqlite3.OperationalError: database is locked в 2 из 9 прогонов в связке с другими файлами; в изолированном прогоне 0 из 20. Вердикт не смягчён; классификация D-09 и оформление вынесены владельцу"
  - "ISO-01 и ISO-03 passed с меткой трасса (без e2e-теста, D-04). Часть ISO-03 про chat-app доказана только кодом (A6), вынесена владельцу"
  - "FIN-01 passed формально по решению владельца №1; непустой allowlist записан как наблюдение, FIN-02 не создан"
  - "Утверждения черновика об ISO-02 про тесты-ловушки скорректированы: тесты-ловушки не проверяют метаданные, parity-тесты не проверяют маскировку"

patterns-established:
  - "Черновик внешнего агента проверяется построчно по коду; ошибочные ссылки, имена тестов и вердикты перечисляются в ограничениях (36 пунктов ниже)"

requirements-verified: [ISO-01, ISO-02, ISO-03, ISO-04, FIN-01]
# Статусы в REQUIREMENTS.md не менялись: они принадлежат плану 05-08.

duration: "не измерена (время старта записано, длительность не сводилась)"
completed: 2026-10-18

actuals:
  tokens: 10330     # chars/4 над V2-06-VERIFICATION.md (41319 символов); SUMMARY не учтён
  tasks: 3          # задачи плана
  commits: 3        # MEASURED: git rev-list --count 9fd2bac..HEAD (#3968)
plan_head_before: 9fd2bac24f162bcc669437140cd6918f1170f407
plan_head_after: f05fd6fbac03a795f0faf7b4954dbb0af9ef1e39
---

# Phase 5 Plan 02 Summary

## Performance

- **Duration:** не измерена
- **Tasks:** 3 (все выполнены)
- **Files created:** 2 (`V2-06-VERIFICATION.md`, `05-02-SUMMARY.md`)

## Accomplishments

- ISO-01 (`passed`, трасса): ключи Gemini привязаны к `persona_id` через `get_key_rotator` (`src/brain/key_rotator.py:194-213`), глобальный `config.GEMINI_API_KEY` не присваивается; 9 тестов `tests/test_key_rotator.py` зелёные.
- ISO-03 (`passed`, трасса): пять фабрик `src/composition.py` поднимают `MissingScopeError` при нехватке scope; `default_lms_client()` вызывается в `src/main.py:673` вне `try`, исключение доходит до `asyncio.run(main())` (fail-closed при старте). Часть chat-app: 0 LMS-совпадений в `backend/app` и 10 полей `Settings` без учётных данных LMS (предел A6 записан).
- ISO-02 (`gap`, против текста v2.0): тело, snippet и вложения маскируются (`src/security/airgap.py:132-157`, тесты-ловушки 12 passed). Метаданные NDA (`sender_name`, `sender_email`, `subject`, `date_sent`) попадают в промпт: `secretary_dialog.py:169-176` (overview), `:191-200` (поиск), `:778-783` (tool `search_emails`, `contents` на `:802-806`), `summarizer.py:343-347` (вечерний дайджест, `generate_content` на `:399`). Утренний бриф передаёт в LLM только число писем. Реальной утечки нет (нет NDA-ящика, A7), путь кода открыт.
- ISO-04 (`gap`): изоляция состояния подтверждена, но тест конкурентной записи дважды упал с `database is locked` (см. Decisions и Issues).
- FIN-01 (`passed`, формально): `HARDCODE_BASELINE = {}` в обоих репозиториях, 3 + 3 тестов сканера зелёные, git status chat-app до и после не изменился.

## Task Commits

1. **Task 1: ISO-04 и скелет файла** — `09f54a9` (docs)
2. **Task 2: ISO-01, ISO-03, FIN-01** — `e783b04` (docs)
3. **Task 3: ISO-02 и финализация** — `f05fd6f` (docs)

Коммиты только в `.planning/`. Код и тесты в репозиториях не менялись (D-10).

## Files Created/Modified

- `.planning/phases/05-retro-verifikatsiya-v2-0/V2-06-VERIFICATION.md` — вердикты, трасса, прогоны, наблюдения, gaps, ограничения.
- `.planning/phases/05-retro-verifikatsiya-v2-0/05-02-SUMMARY.md` — этот файл.

## Decisions Made

- ISO-02 оформлен как gap против исходного текста v2.0, по решению владельца №5. Gap записан с классом D-09 «NDA, безопасность», severity `high`, предложение ISO-05 (Phase 999.4, связка с NDAM-01). ISO-05 не создан, это работа плана 05-08.
- ISO-04 вынесен как `gap`, а не `passed`. По критерию D-08 (аналогично DAT-03) любой сбой теста — gap с частотой и текстом. Классификация (D-09 «целостность данных») и оформление (новое требование или backlog 999.x) вынесены владельцу.
- Тесты ISO-01 и ISO-03 доказаны трассой без e2e-теста: метка `трасса`, по D-04.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Неверные ссылки и имена в черновике агента Argon**
- **Found during:** Task 1–3 (сверка каждой ссылки с кодом)
- **Issue:** черновик содержал 36 ошибок: несуществующие тесты и имена, неверные номера строк, два ложных утверждения о коде, пять переписанных (не дословных) цитат требований v2.0 и две завышенные метки (полный перечень ниже).
- **Fix:** все ссылки перепроверены по коду, пробы выполнены, в документ внесены верные данные.
- **Files modified:** `V2-06-VERIFICATION.md`
- **Commit:** `09f54a9`, `e783b04`, `f05fd6f`

**Итог по черновику: исправлено 36 пунктов.**

Перечень исправлений (черновик → проверенный код):
1. Вердикт ISO-04 `passed` → `gap` (нестабильный тест).
2. Описание `test_multi_persona_concurrency_isolation`: проверки `binding("email")`, `has_binding("lms")`, `schedule_site_url()`, `mark_exhausted("429")`, `active_index` не существуют → реальные: persona id, число рабочих пространств (4 и 3), активный ключ из своего пула, `MissingScopeError` для синтетической персоны.
3. Имена `test_zero_token_overlap_with_default_persona` и `test_composition_switches_cleanly_under_synthetic_persona` не существуют → `test_no_owner_tokens`, `test_every_identifying_field_differs_from_default_persona`, `test_no_real_nda_keywords` и др.
4. `SYNTHETIC_PERSONA_ID`/`SYNTHETIC_GEMINI_KEYS` (строки 18, 29) и `build_synthetic_persona*` не существуют → `SYNTHETIC_PERSONA` (`:39`), id (`:40`); ключи — `MOCK_SYNTH_KEYS` в тесте (`:29-30`).
5. Имя ContextVar персоны `current_persona_override` → `persona_override` (`src/persona/current.py:17`).
6. Сигнатура `mark_exhausted(error_msg)` → `mark_exhausted(key, retry_delay)` (`key_rotator.py:87`).
7. Комментарий «Removed global config.GEMINI_API_KEY mutation» в `key_rotator.py:67` не существует.
8. Утверждение «`sync_active_key_to_env` никто не вызывает» ложно: вызывается из `mark_exhausted` (`:107`, `:115`); в рантайме `env_path=None`, зафиксировано наблюдением.
9. `_current_rotator` (ContextVar ключей) подан как рантайм-путь; в `src/` не выставляется, только в тесте (`:141`).
10. Номера строк `tests/test_key_rotator.py` (15, 22, 34, 48, 56, 75, 111, 128, 138) → определения на `:27-138`.
11. `test_key_rotator_persona_isolation` описан как «default против synthetic» с `mark_exhausted("429")` → реально `tenant-p1`/`tenant-p2`, подмена `_current_rotator`, cooldown.
12. `src/brain/git_evaluator.py:88-89` (`get_client`) — несуществующий код → используется `key_rotator` в `:305-311`.
13. `intent_router.py:354-366` и `self._get_client()` → `:368-376`, прямой вызов `execute_with_failover` в `:381`.
14. `src/main.py:700` (`include_router`) → `:699`.
15. Polling описан как `await dp.start_polling` → `asyncio.create_task` (`src/main.py:933-935`).
16. Конструктор `GeminiKeyRotator` `25-39` → `28-48`.
17. `mark_exhausted` в `execute_with_failover` `:170, :181` → `:171`.
18. Вызов `prime_morning_context` из `src/main.py:391` → `:517` и `:773`.
19. Строки тестов `test_airgap_trap.py` (96, 125, 141, 184, 206, 243, 263, 275) → `:103, 109, 121, 134, 200, 237, 280, 314`.
20. `tests/test_nda_script_parity.py` описаны как проверка маскировки → проверяют обёртку `security_shield` и словари слов; маскировки нет.
21. `sections.append` (строка 352) → список `blocks` (`secretary_dialog.py:348-356`).
22. Утренний бриф «принудительно заменяет текст NDA в промпте» → промпт содержит только число писем (`summarizer.py:91-96`); маскировка `:62` влияет на fallback.
23. Вызов `function_call` «строка 761» → `:758`.
24. Тесты `test_scope_enforcement_*` (шесть, `test_phase4_reachability.py:322-377`) не существуют → реальные `test_composition_default_git_evaluator_missing_scope_raises` (`:91-120`) и `test_composition_missing_scope_error` (`test_ports_conformance.py:297-310`); прямых тестов для lms и schedule нет.
25. `test_provider_declares_required_scopes` (`test_ports_conformance.py:55-68`) → `test_connectors_declare_required_scopes` (`:284-295`).
26. Ожидание probe `-k "scope or required_scopes"`: «11 passed» → фактически `3 passed, 38 deselected`.
27. `MissingScopeError` «в `src/composition.py:17-18`» → определён в `src/core/exceptions.py:10`.
28. `ConnectorBinding` `src/persona/models.py:249-260` → `ConnectorBindingConfig` (`:147`).
29. Метка ISO-03 `трасса+e2e` → `трасса` (нет e2e-теста).
30. Имена тестов FIN-01 (`test_no_new_hardcoded_persona_data`, `test_hardcode_baseline_is_empty`, `test_hardcode_baseline_has_no_stale_entries`) → `test_no_new_hardcode_outside_baseline` (`:149`), `test_baseline_has_no_stale_entries` (`:155`), `test_scanner_counts_lines_and_respects_allowlist` (`:114`); теста на пустоту baseline нет.
31. Импорт baseline «`:21`» → `:18`; `owner_tokens` находится в `tests/persona_tokens.py:35`, не в сканере.
32. Функция `is_allowlisted` (`:51-59`) → `is_scanned` (`:51-55`).
33. Метка FIN-01 `трасса+e2e` → `трасса`.
34. Метка ISO-01 `трасса+e2e` → `трасса` (нет e2e-теста, D-04).
35. Дословная цитата ISO-01 в черновике не совпала с `v2.0-REQUIREMENTS.md:83` → заменена на дословный текст.
36. Дословные цитаты ISO-02, ISO-03, ISO-04, FIN-01 не совпали с `v2.0-REQUIREMENTS.md:84, 85, 86, 87` → заменены на дословный текст.

### Plan-level observations (не auto-fix)

- Task 2 `<verify>` команда в одном прогоне дала код 1 (`database is locked`), в другом код 0 (`56 passed`). Прогон зафиксирован в таблице доказательств, не скрыт.
- Task 1 `<verify>` команда тоже дала код 1 в одном из 6 повторов. Это тот же тест и то же основание для gap ISO-04.
- Команда пробы ISO-02 (`test_airgap_trap` + `test_nda_script_parity`) дала 12 passed, как ожидалось. Метаданные при этом не проверяются.

## Issues Encountered

- **ISO-04: нестабильный тест конкурентной записи подтверждений.** `tests/test_concurrency_isolation.py:97-163` (`test_concurrent_confirmations_isolation`) дважды упал с `sqlite3.OperationalError: database is locked` при INSERT в `assistant_shared/hitl/store.py:52`: 2 из 9 прогонов в связке (таблица доказательств ISO-04 в V2-06: сбои — третий повтор прогона 2 и прогон 3; прогон Task 2 (прогон 6) прошёл). Изолированно (20 прогонов файла) сбоев не было, один прогон занял 47.5 с. Причина не установлена. Гипотеза (не проверена): `PRAGMA journal_mode = WAL` на каждом подключении (`assistant_shared/db/connection.py:45`). Исправление не выполнялось (D-10).
- **Пустой allowlist FIN-01.** Буква v2.0 требует пустой allowlist, он содержит `config/`, `tests/`, `backend/tests/`, `docs/`, `.planning/` и `.md`. Passed по решению владельца №1; наблюдение записано.

## Owner decisions needed

1. **ISO-04:** подтвердить gap и классификацию D-09 (целостность данных). Оформить как новое требование с ID (через 05-08) или как запись backlog 999.x. Исправление — отдельной задачей вне фазы.
2. **ISO-03, часть chat-app:** текст v2.0 требует «проверяемый тест», теста нет (только поиск по коду). Оставить passed по коду или перевести в gap.
3. **ISO-05 (состав):** подтвердить, что в требование ISO-05 (Phase 999.4) входит и вечерний дайджест (`summarizer.py:343-347`) как дополнительный путь того же класса, помимо трёх путей диалога.

## Verification results

- `tests/test_key_rotator.py`: 9 passed, код 0 (ISO-01).
- `tests/test_concurrency_isolation.py` + `tests/test_synthetic_persona.py`: 10 passed, код 0 в 5 из 6 повторов; 1 прогон код 1 (ISO-04 gap).
- `tests/test_phase4_reachability.py` + `tests/test_ports_conformance.py`: 41 passed, код 0 (ISO-03).
- `tests/test_airgap_trap.py` + `tests/test_nda_script_parity.py`: 12 passed, код 0 (ISO-02, часть а).
- `tests/test_hardcode_scanner.py` (assistant-core): 3 passed, код 0; `backend/tests/test_hardcode_scanner.py` (chat-app): 3 passed, код 0; `git status` chat-app не изменён (FIN-01).
- Общий прогон 5 файлов (Task 2 verify): 56 passed, код 0 в этом прогоне.
- Проба в памяти: привязка `lms` со `scopes=["lms.read"]` → `default_lms_client()` поднимает `MissingScopeError`; исходная персона не изменена.
- Гейт `scripts/gate.py` не запускался (по инструкции плана и оркестратора).

## Known Stubs

None.

## Threat Flags

None. Файлы плана — только документы в `.planning/`, новых поверхностей не добавлено.

## Self-Check

Проверка: файлы существуют, коммиты в истории.

- `V2-06-VERIFICATION.md` — найден.
- `09f54a9`, `e783b04`, `f05fd6f` — в истории `main`.
- В файлах нет адресов e-mail, содержимого писем и значений из `.env`.
- Вне `.planning/` изменений нет.

## Self-Check: PASSED

## Next Steps

- Владелец решает три вопроса выше (ISO-04, ISO-03 chat-app, состав ISO-05).
- План 05-08 оформляет ISO-05 и, по решению владельца, требование или backlog для ISO-04; статусы в REQUIREMENTS.md обновляет 05-08.
