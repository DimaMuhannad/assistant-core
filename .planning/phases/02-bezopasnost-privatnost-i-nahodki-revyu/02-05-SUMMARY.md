---
phase: 02-bezopasnost-privatnost-i-nahodki-revyu
plan: 05
subsystem: testing
tags: [guard, live-db, symlink, regex, WR-07, WR-11, WR-13, D-17]

# Dependency graph
requires:
  - phase: 01-sobstvennyy-geyt-kachestva-assistant-core
    provides: страж боевой БД tests/live_db_guard.py (GATE-02) и находки код-ревью 01-REVIEW (WR-07, WR-11, WR-13)
provides:
  - LIVE_DB_PATHS содержит абсолютные боевые пути /opt/assistant-core/data/assistant.db и /opt/assistant-core/assistant.db вместе с путями от CORE_DIR
  - is_live_db_path проверяет realpath и для символической ссылки с любым именем (префильтр по имени больше не пропускает ссылку)
  - test_menu_command_rendering проверяет отрисовку меню по существу (lms до и после отключения, пользовательский алиас)
  - страж правил tests/test_claude_md_gate_pointer.py использует регулярные выражения (путь к gate.py и составная команда cd + gate) с самопроверкой
affects: [02-14 (disposition WR-07, WR-11, WR-13), последующие планы phase 02 с тестами стража боевой БД]

# Actuals (#2632) — chars/4 по реальному диффу, не счётчик харнесса
actuals:
  tokens: 3069
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Префильтр стража: проверка по имени ИЛИ по факту символической ссылки, затем сравнение realpath с множеством заблокированных путей"
    - "Регулярные выражения собираются из частей, чтобы тест не становился источником ссылки для shield и хардкод-сканера"
    - "Самопроверка шаблонов: положительные образцы обязаны срабатывать, отрицательные не обязаны"

key-files:
  created: []
  modified:
    - tests/live_db_guard.py
    - tests/test_live_db_guard.py
    - tests/test_command_aliases.py
    - tests/test_claude_md_gate_pointer.py

key-decisions:
  - "WR-07: абсолютные пути добавляются к путям от CORE_DIR, дубликаты убираются через dict.fromkeys; множество заблокированных realpath пересчитывается из расширенного списка"
  - "WR-07: префильтр вызывает os.path.islink только для путей, чьё имя не совпало с боевыми именами; лишний lstat на открытие чужого файла пренебрежимо мал"
  - "WR-07: сравнение по inode (жёсткие ссылки) не вводится, остаточный риск записан ниже (T-02-16)"
  - "WR-13: проверка ссылки на гейт chat-app по двум шаблонам, а не по одной строке; сообщение об ошибке называет файл и вид ссылки, найденный фрагмент не печатается"
  - "WR-11: lms проверяется в каталоге по умолчанию, в get_active_commands и get_telegram_commands до и после set_command_setting; неиспользуемые переменные удалены"
  - "Файлы правил CLAUDE.md и .claude/CLAUDE.md не менялись: git log -- CLAUDE.md .claude/CLAUDE.md не содержит коммитов 02-05 (последний коммит правил 7451866, план 01-08)"

patterns-established:
  - "Страж стоит проверять на положительных и отрицательных образцах, иначе шаблон может молча не срабатывать"
  - "Тесты стража боевой БД работают только со строками путей и с существованием ссылки; сам боевой файл не открывается"

requirements-completed: []

coverage:
  - id: D1
    description: "Страж боевой БД охраняет абсолютные пути /opt/assistant-core/data/assistant.db и /opt/assistant-core/assistant.db с sidecar-файлами независимо от расположения checkout"
    requirement: "WR-07"
    verification:
      - kind: unit
        ref: "tests/test_live_db_guard.py#test_absolute_live_path_is_blocked_regardless_of_core_dir"
        status: pass
      - kind: unit
        ref: "tests/test_live_db_guard.py#test_live_db_paths_constant_has_core_relative_and_absolute_live_files"
        status: pass
    human_judgment: false
  - id: D2
    description: "Символическая ссылка с другим именем на боевую БД блокируется; обычный файл с другим именем не блокируется"
    requirement: "WR-07"
    verification:
      - kind: unit
        ref: "tests/test_live_db_guard.py#test_symlink_with_other_name_to_live_path_is_blocked"
        status: pass
      - kind: unit
        ref: "tests/test_live_db_guard.py#test_symlink_without_db_suffix_to_live_path_is_blocked"
        status: pass
      - kind: unit
        ref: "tests/test_live_db_guard.py#test_regular_file_with_other_name_is_not_blocked"
        status: pass
    human_judgment: false
  - id: D3
    description: "Тест отрисовки меню: lms в каталоге, исчезает из меню после отключения, пользовательский алиас разрешается в команду"
    requirement: "WR-11"
    verification:
      - kind: unit
        ref: "tests/test_command_aliases.py#test_menu_command_rendering"
        status: pass
    human_judgment: false
  - id: D4
    description: "Страж правил ловит ссылку на гейт chat-app регулярными выражениями (путь и составная команда); самопроверка на образцах проходит"
    requirement: "WR-13"
    verification:
      - kind: unit
        ref: "tests/test_claude_md_gate_pointer.py#test_rules_files_do_not_name_legacy_gate_command"
        status: pass
      - kind: unit
        ref: "tests/test_claude_md_gate_pointer.py#test_legacy_gate_patterns_self_check"
        status: pass
    human_judgment: false
  - id: D5
    description: "Тест латентности роутера (находка 02-03): прогрев перед замерами best-of-5, порог 50 мс и строгие проверки маршрута сохранены"
    requirement: ""
    verification:
      - kind: unit
        ref: "tests/test_command_aliases.py#test_fast_intent_router_aliases"
        status: pass
    human_judgment: false
---

# Phase 02 Plan 05: Страж боевой БД, тест меню и страж правил (WR-07, WR-11, WR-13) Summary

**Страж боевой БД охраняет абсолютные пути и символические ссылки с любым именем, тест меню проверяет lms и алиасы по существу, страж правил ловит ссылку на гейт chat-app регулярными выражениями с самопроверкой.**

## Performance

- **Duration:** около 30 мин (оценка; время старта не фиксировалось)
- **Started:** не фиксировалось
- **Completed:** 2026-10-10T12:33:22Z
- **Tasks:** 2 из 2
- **Files modified:** 4

## Accomplishments
- WR-07: `LIVE_DB_PATHS` дополнен абсолютными путями `/opt/assistant-core/data/assistant.db` и `/opt/assistant-core/assistant.db`; страж защищает боевые файлы из любого checkout, worktree или jail.
- WR-07: префильтр `is_live_db_path` проверяет realpath, если путь сам является символической ссылкой; ссылка `x.db` на боевую БД блокируется.
- WR-11: `test_menu_command_rendering` проверяет `get_active_commands` и `get_telegram_commands` до и после отключения `lms`, а также разрешение пользовательского алиаса; тест больше не может пройти на пустом содержимом.
- WR-13: страж правил использует два регулярных выражения (путь к `gate.py` и составная команда `cd` + запуск `gate.py`), собранные из частей; самопроверка подтверждает срабатывание на положительных образцах и отсутствие ложных срабатываний на отрицательных.
- Находка 02-03 (латентность роутера) закрыта без ослабления порога: добавлен прогрев, best-of-5 и строгие проверки маршрута сохранены.
- Код рантайма (`src/`) не менялся. Новых зависимостей, skip, xfail и deselected нет. Боевая БД не открывалась тестами.

## Task Commits

Each task was committed atomically:

1. **Task 1: WR-07 страж боевой БД: абсолютные пути и ссылка с другим именем** - `124d748` (fix)
2. **Task 2: WR-11 тест меню и WR-13 страж правил по регулярным выражениям** - `0c52a71` (test)

**Plan metadata:** коммит `docs(02-05)` с SUMMARY.md, STATE.md, ROADMAP.md (хэш указан в ответе исполнителя)

## Files Created/Modified
- `tests/live_db_guard.py` - абсолютные боевые пути в `LIVE_DB_PATHS`; префильтр `is_live_db_path` учитывает символические ссылки; модуль по-прежнему только stdlib
- `tests/test_live_db_guard.py` - переименованный тест констант и новые тесты: абсолютные пути со sidecar, ссылка с другим именем и без суффикса, обычный файл не блокируется
- `tests/test_command_aliases.py` - переписан `test_menu_command_rendering`; в `test_fast_intent_router_aliases` добавлен прогрев перед замерами
- `tests/test_claude_md_gate_pointer.py` - регулярные выражения вместо одной строки, тест самопроверки, сообщение об ошибке без найденного фрагмента

## Находка -> изменение -> тест

| Находка | Было | Изменение | Тест |
|---|---|---|---|
| WR-07: страж не закрывает часть путей | `LIVE_DB_PATHS` только от `CORE_DIR`; запуск из другого checkout не охранял боевой файл | добавлены абсолютные `/opt/assistant-core/...` пути, дубликаты убираются | `test_absolute_live_path_is_blocked_regardless_of_core_dir` (9 случаев: 2 файла x 4 суффикса, включая `-wal`, `-shm`, `-journal`), `test_live_db_paths_constant_has_core_relative_and_absolute_live_files` |
| WR-07: ссылка с другим именем обходит префильтр | префильтр смотрел только на имя файла | realpath проверяется и для символической ссылки (`os.path.islink`) | `test_symlink_with_other_name_to_live_path_is_blocked`, `test_symlink_without_db_suffix_to_live_path_is_blocked`, `test_regular_file_with_other_name_is_not_blocked` |
| WR-11: тест меню ничего не проверяет | неиспользуемые переменные, проверялась только запись в БД | проверки активных команд и меню до/после отключения `lms`, разрешение алиаса | `test_menu_command_rendering` |
| WR-13: страж правил ловит одну точную строку | одна подстрока `python3 /opt/chat-app/scripts/gate.py` | два регулярных выражения (путь, составная команда), самопроверка на образцах | `test_rules_files_do_not_name_legacy_gate_command`, `test_legacy_gate_patterns_self_check` |
| Находка 02-03: флаки латентности роутера | порог 50 мс на best-of-5 без прогрева | прогрев без замера перед каждым кейсом; порог и строгие проверки сохранены | `test_fast_intent_router_aliases` |

## Decisions Made
- Абсолютные пути добавлены, а не заменены: пути от `CORE_DIR` остались для текущего checkout.
- Сравнение по inode не вводилось (выходит за область WR-07), см. остаточный риск ниже.
- Регулярные выражения собраны из частей, как и прежняя строка: сам тест не становится источником обратной ссылки для shield и хардкод-сканера.
- Файлы правил `CLAUDE.md` и `.claude/CLAUDE.md` не изменены.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality, находка 02-03] Прогрев перед замерами латентности**
- **Found during:** Task 2 (тест `test_fast_intent_router_aliases` в том же файле, что и WR-11)
- **Issue:** `test_fast_intent_router_aliases` краснел при нагрузке VPS (наблюдение 02-03). В рабочем дереве уже был best-of-5 по минимуму; оставшийся риск - первый вызов на холодном старте (поток aiosqlite, кэш), который попадает в минимум, если остальные замеры тоже медленные.
- **Fix:** перед каждым кейсом один непосчитанный вызов `router.route` с проверкой маршрута; порог 50 мс, best-of-5 и проверки `action`, `model`, `confidence` на каждом замере сохранены. Ослабления порога нет.
- **Files modified:** `tests/test_command_aliases.py`
- **Verification:** файл зелёный (21 тест в трёх файлах вместе с `test_command_registry.py`), полный гейт зелёный
- **Committed in:** `0c52a71`

Других отклонений нет.

**Total deviations:** 1 auto-fixed (находка из 02-03, Rule 2). **Impact on plan:** в объём плана, код рантайма не затронут.

## Issues Encountered
- Полный гейт `python3 scripts/gate.py` зелёный (ИТОГ: ЗЕЛЁНЫЙ, EXIT=0). Во время прогона гейт сообщил о записи в боевую БД в окне 12:30:26-12:32:46 UTC и связал её с сервисом `assistant-worker` (сервис активен, в выводе гейта указано время изменения БД). Гейт повторил измерение в тихом окне 5 с, два замера SHA-256 совпали (`153ef5e6a844`). По выводу гейта запись связана с сервисом, не с тестами; сам этот план тесты боевую БД не открывают (страж блокирует открытие). Сервис не перезапускался и не менялся этим планом. Атрибуцию записи стоит проверить владельцу.
- Однократно в прогоне `tests/test_live_db_guard.py` появилось `PytestUnhandledThreadExceptionWarning` из потока aiosqlite («Event loop is closed»). Предупреждение связано с тестом `test_aiosqlite_connect_to_live_path_is_blocked` (существовал до плана). В двух последующих прогонах оно не воспроизвелось; тест и страж в этой части не менялись. Зафиксировано как наблюдение, не исправлялось (вне области WR-07/WR-11/WR-13).
- В рабочем дереве до старта плана есть незакоммиченные `.planning/config.json` (изменение `_auto_chain_active`), `.planning/milestone.lock` и `.planning/state.json`. Они не относятся к этому плану и в коммиты плана не включались.

## Остаточный риск

- **Жёсткая ссылка (hardlink) на боевую БД с другим именем** не распознаётся (T-02-16, принято). Сравнение по inode вне области WR-07. Вектор требует права записи в каталог, где создаётся ссылка.
- **Каталог-ссылка на каталог боевой БД с файлом другого имени** не считается боевой БД (допущение плана). Файл с именем `assistant.db` (и его sidecar-файлы) внутри такого каталога блокируется через realpath, файл с любым другим именем - нет.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None.

## Threat Flags
None.

## Self-Check: PASSED

Проверено:
- `tests/live_db_guard.py`, `tests/test_live_db_guard.py`, `tests/test_command_aliases.py`, `tests/test_claude_md_gate_pointer.py` существуют и изменены коммитами `124d748` и `0c52a71` (`git merge-base --is-ancestor` для обоих хэшей - FOUND).
- `tests/test_live_db_guard.py` 43 теста, `tests/test_gdrive_client.py` + `tests/test_gate.py` 166 тестов, `tests/test_command_aliases.py` + `tests/test_claude_md_gate_pointer.py` + `tests/test_command_registry.py` 21 тест, `tests/test_hardcode_scanner.py` 3 теста - все зелёные.
- Полный гейт `python3 scripts/gate.py`: ИТОГ ЗЕЛЁНЫЙ (assistant-core pytest 883, assistant-shared pytest 145).
- Файлы правил не менялись коммитами плана.

## Next Phase Readiness
- WR-07, WR-11, WR-13 закрыты кодом и тестами; для плана 02-14 это готовая disposition по D-17.
- Страж боевой БД усилен, GATE-02 не ослаблен: список охраняемых путей только расширен, `open` и `sqlite3.connect` по-прежнему блокируются до обращения к файлу.
