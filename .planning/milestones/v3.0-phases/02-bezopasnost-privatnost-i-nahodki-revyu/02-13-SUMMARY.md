---
phase: 02-bezopasnost-privatnost-i-nahodki-revyu
plan: 13
subsystem: quality-gate
tags: [gate, wr-03, wr-04, wr-10, d-17, db-integrity, shield-fingerprint, hermetic-tests]
status: complete

requires:
  - phase: 02-bezopasnost-privatnost-i-nahodki-revyu
    provides: "02-10, 02-11, 02-12: файл персоны зафиксирован (02-11), рабочее дерево без чужих правок к моменту полных гейтов (02-12)"
provides:
  - "scripts/gate.py: db_integrity_snapshot, compare_integrity, RUNTIME_DELETES_FROM, параметр snapshots у db_unchanged_check, сбор снимков в _run_all"
  - "scripts/gate.py: line_fingerprint, UNREADABLE_FINGERPRINT, parse_shield_findings с отпечатками строк, новая форма KNOWN_SHIELD_FALSE_POSITIVES"
  - "tests/test_gate.py: тесты на временных SQLite и файлах, автофикстура герметичности"
affects: [02-15]

actuals:
  tokens: 15000
  tasks: 3
  commits: 3
plan_head_before: be66257003b2d89f64a29c19aa29b2d923be9c67
plan_head_after: 9d6d0e85cf0d4327e6e19de125447646d3b15403

key-files:
  created: []
  modified:
    - scripts/gate.py
    - tests/test_gate.py

key-decisions:
  - "Смягчение «повтор при записи сервиса» (решение владельца 2026-10-09) сохранено, но допускается только при совместимых снимках целостности «до» и «после»: та же схема и в таблицах вне RUNTIME_DELETES_FROM число строк не уменьшилось; нет снимка - КРАСНЫЙ"
  - "Снимок хранит ещё и хеши отдельных объектов схемы (ключ objects), чтобы причина красной строки называла изменившиеся объекты; сравнение по-прежнему идёт по общему хешу схемы"
  - "Отпечаток находки это sha256 от «путь, NUL, точный текст строки файла»; метка unreadable не покрывается записью, а запись с такой меткой всегда устаревшая"
  - "Строка файла читается только внутри репозитория (абсолютные пути, «..» и ссылки наружу дают unreadable)"

requirements-completed: []
---

# Phase 2 Plan 13: усиление scripts/gate.py (WR-03, WR-04, WR-10) Summary

**Смягчение проверки боевой БД теперь сравнивает с исходным снимком схемы и счётчиков, замороженный список shield привязан к sha256 точных строк файлов, а тесты проверки БД и службы не трогают ни `systemctl`, ни боевой файл.**

## Таблица «находка -> изменение -> тест»

| Находка | Изменение | Тесты (tests/test_gate.py) |
|---------|-----------|----------------------------|
| WR-03: смягчение сравнивало два тихих замера друг с другом | `db_integrity_snapshot(db)` (только `mode=ro`, схема и счётчики, без данных), `compare_integrity`, `RUNTIME_DELETES_FROM`; `db_unchanged_check(..., snapshots=)` проверяет снимки ПЕРЕД тихим замером, без снимков или при несовместимых - КРАСНЫЙ с причиной (только имена таблиц/объектов); `_run_all` берёт `snap_before` рядом с хешем «до» и `snap_after` сразу за pytest ядра | `test_integrity_snapshot_*` (схема и счётчики, FTS5 и служебные таблицы исключены, сбой чтения даёт None, только URI `mode=ro`), `test_compare_integrity_*` (рост, смена схемы, убыль вне списка, убыль в таблице рантайма, исчезнувшая таблица, None), `test_db_unchanged_check_mitigation_*` (совместимые - зелёная; другая схема, без снимков, None, убыль строк, мусор вместо снимков - красная), `test_run_all_passes_snapshots_*` (поведение и AST), `test_runtime_deletes_from_matches_delete_statements_in_storage_layer` |
| WR-04: замороженный список держался на счётчике | `line_fingerprint`, ключ тройка (путь, вид, отпечаток), `KNOWN_SHIELD_FALSE_POSITIVES = {(путь, вид): {отпечаток: число}}`, `parse_shield_findings` читает строку по номеру из вывода shield, `compare_shield_findings` сравнивает тройки, пометка «строка файла изменилась (обновите запись осознанно)» | `test_line_fingerprint_*`, `test_parse_shield_findings_*` (нумерация строк как у shield, unreadable, чтение только внутри репозитория), `test_compare_shield_findings_same_count_on_another_line_is_new_and_stale`, `test_compare_shield_findings_unreadable_is_never_covered`, `test_known_shield_false_positives_core_entry_matches_real_persona_file` (слова читаются из данных персоны во время теста и не печатаются), `test_run_shield_step_core_same_count_on_a_replaced_line_is_red`, `..._moved_to_another_line_is_red`, `..._unreadable_line_is_red`, `..._never_contains_fingerprints_or_line_text` |
| WR-10: тесты запускали настоящий `systemctl` и делали stat боевой БД | автофикстура `_hermetic_live_db_and_service` (подмена `_db_diagnostics`, `_service_state`, `LIVE_DB` на несуществующий файл в tmp_path); тесты самих функций берут настоящие `_REAL_*` явно | `test_autouse_fixture_replaces_*`, `test_db_checks_run_without_any_real_subprocess` (`subprocess.run` бросает), `test_db_checks_never_stat_the_real_live_db`, `test_tests_with_own_live_db_path_still_override_the_fixture` |

Дополнительно прогнан весь `tests/test_gate.py` с наблюдателем, пишущим любой вызов `subprocess.run(["systemctl", ...])` в файл: журнал пуст, `systemctl` не вызывался ни разу.

## Итоговый состав RUNTIME_DELETES_FROM

Получен свежим поиском `DELETE FROM` (без учёта регистра, в том числе по `src/`, `scripts/`, `assistant_shared`) и совпал с составом на момент планирования; находки только в `src/storage/db.py`:

| Таблица | Основание (место в коде) |
|---------|--------------------------|
| workspaces, connector_bindings | `Database.upsert_persona` (замена рабочих пространств и привязок персоны) |
| projects, tasks, reminders, documents | `delete_project`, `delete_task`, `delete_reminder`, `delete_document` |
| methodist_chunks, methodist_toc_index | `replace_methodist_chunks`, `save_methodist_toc_entries` (замена содержимого документа; триггеры сами чистят FTS5) |
| bot_live_ticker | `delete_live_ticker` |
| bot_custom_aliases | `remove_custom_alias` |

Каскады `ON DELETE CASCADE` идут от `methodist_documents` и `personas`, из которых рантайм не удаляет, поэтому в список они не добавлены; `ON DELETE SET NULL` счётчики не меняет. Тест `test_runtime_deletes_from_matches_delete_statements_in_storage_layer` краснеет, если в `src/storage/db.py` появится `DELETE FROM` новой таблицы: список надо пополнять осознанно.

## Остаточный риск WR-03 (принят, T-02-45)

Смягчение не закрывает добавление и изменение строк тестом через дочерний процесс, не охваченный стражем, при совпадающей схеме и неубывающих счётчиках. Основной барьер остаётся прежним: страж `tests/live_db_guard.py` (усилен WR-07), а применение смягчения видно в `info` строки прогона. Возможен и ложный красный (fail-closed, «повторите прогон») при неявном уменьшении счётчика дочерней таблицы; список пополняется только после проверки кода.

## Что сделано по задачам

1. **Task 1 (tracer, WR-03)** - коммит `1a2285d`. Снимок, сравнение, параметр `snapshots`, сбор снимков в `_run_all`; существующие тесты смягчения переведены на совместимые снимки, заглушки шагов `_run_all` получили подмену `db_integrity_snapshot`. Сквозной тест на временных БД зелёный до расширения.
2. **Task 2 (WR-04)** - коммит `e22a292`. Предусловие выполнено (`git log -1 --format=%s -- config/persona.yaml` даёт «feat(02-11): privacy notice text in persona data», файл не изменён). Отпечаток записи для `config/persona.yaml` вычислен самой функцией гейта по строке 44 текущего файла (все три находки на одной строке), печатался только hex. Записей не добавлено, число находок прежнее (3). Список assistant-shared пуст.
3. **Task 3 (WR-10)** - коммит `9d6d0e8`. Автофикстура и тесты герметичности; `scripts/gate.py` не менялся (обращений к боевому файлу в тестах без подмены сверх уже найденных не обнаружено).

## Результаты проверок

- `.venv/bin/pytest tests/test_gate.py tests/test_gate_red_cases.py -p no:cacheprovider -q`: 193 passed (без skipped, xfail, deselected).
- `python3 scripts/gate.py` (assistant-core): ИТОГ: ЗЕЛЁНЫЙ, десять строк; assistant-core 969 тестов, assistant-shared 197; «SHA-256 до/после совпали: 74b8b9feb027»; import-linter, shield, дрейф персоны и токенов, оба hook зелёные. Повторный прогон не потребовался.
- `cd /opt/chat-app && python3 scripts/gate.py`: ИТОГ: ЗЕЛЁНЫЙ (chat-app 277 тестов, assistant-core 969). Замороженные записи chat-app не менялись (D-15). `git -C /opt/chat-app status --short` показывает только `?? .watchdog_disabled`: файл создан 2026-10-10 11:58 UTC, до старта этого плана, к плану не относится.
- `security_shield.py . --all`: ровно 3 находки в `config/persona.yaml` (строка 44), как и раньше.
- Боевая БД: открывалась только на чтение самим гейтом (хеш, снимок); тесты работали на временных БД.

## Deviations from Plan

None - plan executed exactly as written. Уточнения в рамках плана:

- Снимок помимо `schema` и `rows` содержит `objects` (хеши объектов схемы) только ради читаемой причины красной строки; вердикт определяется общим хешем схемы.
- `test_core_pytest_env_refuses_live_db` теперь берёт путь боевой БД из запомненной константы `_REAL_LIVE_DB`, иначе после подмены `LIVE_DB` автофикстурой тест проверял бы временный путь.
- В тесте 6 число находок сверяется по парам (строка, слово), как их считает shield; для текущего файла это совпадает с числом объявленных слов.

## Known Stubs

Нет.

## Threat Flags

Нет новой поверхности атаки (изменения только в локальном гейте и его тестах; боевая БД читается лишь через `mode=ro`, схема и счётчики).

## Self-Check: PASSED

Файлы `scripts/gate.py`, `tests/test_gate.py` изменены; коммиты `1a2285d`, `e22a292`, `9d6d0e8` в истории (`git merge-base --is-ancestor` для каждого).
