---
phase: 01-sobstvennyy-geyt-kachestva-assistant-core
plan: 06
subsystem: ops
tags: [deploy, smoke, systemd, journalctl, ast, telegram-getMe, redaction]

requires:
  - phase: 01-sobstvennyy-geyt-kachestva-assistant-core
    provides: "Страж боевой БД (план 01-01): тесты скрипта не открывают assistant.db"
provides:
  - "scripts/deploy.py: read-only смоук сервиса assistant-worker без флагов (ядро OPS-01)"
  - "Фазы без TTY: --await-help и --confirm-help yes|no по файлу состояния вне репозитория"
  - "Markdown-отчёт смоука по --report без токенов, e-mail и сырых строк журнала"
  - "Тест D-07 по ast: handle_cmd_help не обращается к self.db"
affects: [01-07, 01-10, phases 2-5, phases 7-9]

actuals:
  tokens: 23700
  tasks: 3
  commits: 3
plan_head_before: 43de1c1f27f5230b7e2361631e6d340cb3fce5fd
plan_head_after: 98a847277a112db9d1ca02c9850ef4210839a1a3

tech-stack:
  added: []
  patterns:
    - "Внедряемый раннер подпроцессов плюс белый список команд ensure_read_only (только systemctl show, journalctl, git rev-parse HEAD)"
    - "Журнал фильтруется по _SYSTEMD_INVOCATION_ID, время берётся из префикса journald (метки приложения смешаны UTC/MSK)"
    - "Ожидаемые задачи планировщика берутся ast-разбором src/main.py, а не жёстким списком"
    - "Очистка redact до усечения; наружу только имена логгеров, очищенные сообщения и счётчики"

key-files:
  created:
    - scripts/deploy.py
    - tests/test_deploy_script.py
  modified: []

key-decisions:
  - "STARTUP_TAIL_SECONDS = 60: окно ошибок от начала инвокации до строки «Run polling for bot» плюс 60 с"
  - "Белый список команд ensure_read_only вместо чёрного списка глаголов: любая команда вне списка отвергается до запуска"
  - "Перед --await-help и --confirm-help сверяется InvocationID: состояние старого запуска не подтверждает новый"
  - "Файл отчёта и файл состояния пишутся с правами 0600, права существующего файла сужаются"

patterns-established:
  - "Скрипты эксплуатации на stdlib, загружаются тестами по пути через importlib (как gate)"
  - "Тесты на фейковом раннере и синтетическом журнале без реальных systemctl/journalctl/сети"

requirements-completed: [OPS-01]

coverage:
  - id: D1
    description: "Смоук без флагов read-only: ActiveState, журнал инвокации, окно ошибок старта, polling, ни одной изменяющей команды"
    requirement: OPS-01
    verification:
      - kind: unit
        ref: "tests/test_deploy_script.py#test_main_runner_sees_only_read_only_commands"
        status: pass
      - kind: unit
        ref: "tests/test_deploy_script.py#test_ensure_read_only_rejects_state_changing_commands"
        status: pass
    human_judgment: false
  - id: D2
    description: "Строгое окно ошибок: ERROR, CRITICAL, Traceback краснят смоук без белого списка, WARNING только считаются"
    requirement: OPS-01
    verification:
      - kind: unit
        ref: "tests/test_deploy_script.py#test_main_error_in_startup_window_is_red_without_allowlist"
        status: pass
      - kind: unit
        ref: "tests/test_deploy_script.py#test_main_error_after_tail_does_not_redden"
        status: pass
    human_judgment: false
  - id: D3
    description: "Задачи планировщика по ast и журналу; getMe без утечки токена"
    requirement: OPS-01
    verification:
      - kind: unit
        ref: "tests/test_deploy_script.py#test_expected_jobs_on_real_main_contains_ten_known_pairs"
        status: pass
      - kind: unit
        ref: "tests/test_deploy_script.py#test_main_get_me_failure_is_red_and_token_never_printed"
        status: pass
    human_judgment: false
  - id: D4
    description: "Фазы без TTY: итог ЗЕЛЁНЫЙ только при зелёной автоматической части, обработанном обновлении и «да» владельца"
    requirement: OPS-01
    verification:
      - kind: unit
        ref: "tests/test_deploy_script.py#test_final_verdict_rules"
        status: pass
      - kind: unit
        ref: "tests/test_deploy_script.py#test_confirm_help_yes_without_handled_update_is_red_with_explanation"
        status: pass
    human_judgment: false
  - id: D5
    description: "Отчёт и файл состояния не содержат токенов, e-mail и сырых строк журнала; /help не пишет в БД (D-07)"
    requirement: OPS-01
    verification:
      - kind: unit
        ref: "tests/test_deploy_script.py#test_render_report_md_contains_no_emails_tokens_or_raw_lines"
        status: pass
      - kind: unit
        ref: "tests/test_deploy_script.py#test_help_handler_does_not_touch_db"
        status: pass
    human_judgment: false
  - id: D6
    description: "Фактическая работа смоука на живом сервисе в составе процедуры выкатки (рестарт, ответ бота на /help)"
    verification: []
    human_judgment: true
    rationale: "Живая проверка с рестартом и ответом владельца выполняется планами 01-07 и 01-10; здесь выполнен только read-only прогон без флагов"

duration: ~35min
completed: 2026-10-09
status: complete
---

# Phase 1 Plan 06: Ядро скрипта выкатки (read-only смоук) Summary

**scripts/deploy.py: read-only смоук assistant-worker по журналу текущей инвокации (окно ошибок старта, задачи планировщика по ast, getMe без утечки токена), фазы подтверждения /help без TTY и очищенный markdown-отчёт; 122 теста на фейковом раннере.**

## Performance

- **Duration:** ~35 мин (время старта не фиксировалось, оценка)
- **Completed:** 2026-10-09T17:58Z
- **Tasks:** 3
- **Files modified:** 2 (оба новые: `scripts/deploy.py`, `tests/test_deploy_script.py`)

## Accomplishments

- Без флагов `scripts/deploy.py` проверяет сервис: ActiveState, журнал по `_SYSTEMD_INVOCATION_ID`, ошибки в окне старта, запись о старте polling, регистрацию десяти задач планировщика, `getMe`. Любая команда вне белого списка (`systemctl show`, `journalctl`, `git rev-parse HEAD`) отвергается функцией `ensure_read_only` ещё до запуска. БД не открывается, `src` не импортируется, `getUpdates` и сессии Telethon не используются.
- Окно ошибок старта: от начала инвокации до «Run polling for bot» плюс **60 секунд** (`STARTUP_TAIL_SECONDS`). Причина: окно захватывает начальные циклы коллекторов, которые `main()` выполняет примерно 50 с до запуска планировщика, и первые секунды работы, но не штатные сбои дальнейшей жизни сервиса. ERROR, CRITICAL и Traceback в окне краснят смоук без белого списка (решение владельца 2026-10-09), WARNING только считаются по логгерам. Для каждой ошибки печатается логгер и очищенное усечённое сообщение (до 160 символов).
- Ожидаемые задачи берутся `ast`-разбором `src/main.py` (на реальном файле найдены все десять пар функция/id, условные под `if` помечаются и не краснят), регистрация подтверждается строками «Added job» и «Scheduler started».
- Токен бота читается только по ключу `TELEGRAM_BOT_TOKEN`, наружу идут класс исключения или HTTP-код; тест доказывает отсутствие токена в выводе, таблице и файле состояния даже при исключении с токеном в тексте.
- Фазы без TTY: обычный запуск сохраняет файл состояния (права 0600, `/var/tmp/assistant-core-smoke-state.json` по умолчанию) и печатает трёхшаговую инструкцию; `--await-help` ждёт в журнале обработанное обновление после метки (шаг 5 с, дедлайн `--await-timeout`, по умолчанию 120 с); `--confirm-help yes|no` принимает ответ владельца, полученный Claude опросом. Итог ЗЕЛЁНЫЙ достижим только при зелёной автоматической части, обработанном обновлении и «да».
- `--report PATH` пишет markdown-отчёт (дата UTC, HEAD, таблица, ошибки, счётчики WARNING, подтверждение бота, итог). Путь внутри `.git` и несуществующий каталог отвергаются кодом 2 до запуска любых команд.
- Тест D-07 по `ast`: `handle_cmd_help` не обращается к `self.db`; если справка начнёт писать в БД, тест покраснеет, а вопрос вернётся владельцу.

**Число тестов:** 122 в `tests/test_deploy_script.py` (по задачам: 44, 73, 122). Полный прогон набора: **577 passed** (455 до плана плюс 122), 0 skipped/deselected/xfail (запуск с `-o xfail_strict=true`).
**Живой read-only запуск Task 1:** код возврата 0 (вывод в SUMMARY не вставлен). Дополнительно проверен прогон с `--report` во временный каталог: коды 0, права файлов 0600, шаблонов e-mail и токена в файле состояния и отчёте нет.
**Рестарт `assistant-worker` не требуется:** изменены только `scripts/` и `tests/`, рантайм (`src/`) не затронут, сервисы не перезапускались и не останавливались.

## Task Commits

1. **Task 1: Read-only смоук ядра (tracer)** - `ea93a1a` (feat)
2. **Task 2: Задачи планировщика по ast и журналу, getMe по токену из .env** - `70dba2f` (feat)
3. **Task 3: Фазы без TTY, подтверждение владельца и markdown-отчёт** - `98a8472` (feat)

**Plan metadata:** следующий коммит docs(01-06).

## Files Created/Modified

- `scripts/deploy.py` - смоук: раннер и белый список команд, `redact`, разбор журнала, окно старта, проверки, ast-разбор задач, getMe, состояние, фазы `--await-help`/`--confirm-help`, отчёт, CLI
- `tests/test_deploy_script.py` - 122 теста на фейковом раннере, синтетическом журнале и поддельных `.env`/`main.py`

## Decisions Made

- Окно старта 60 с (см. выше), белого списка внешних ошибок нет: КРАСНЫЙ на живом сервисе возможен, решение о повторе принимает владелец по отчёту.
- Белый список команд вместо чёрного списка глаголов: безопаснее при будущих правках. План 01-07 расширит его для рестарта по флагу.
- Перед фазами подтверждения проверяется совпадение `InvocationID` с файлом состояния: иначе подтверждение относилось бы к уже перезапущенному сервису.
- Тело ответа `getMe` (имя бота) не разбирается и не печатается.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Сверка InvocationID перед `--await-help` и `--confirm-help`**
- **Found during:** Task 3
- **Issue:** план не требовал проверки, что файл состояния относится к текущему запуску сервиса; после рестарта между смоуком и подтверждением ответ владельца относился бы к другому запуску, а ожидание искало бы обновления в журнале мёртвой инвокации.
- **Fix:** `ensure_same_invocation` читает `systemctl show` (read-only) и прерывает фазу сообщением «сервис перезапущен или остановлен после смоука: повторите автоматическую часть», код 1; состояние не меняется.
- **Files modified:** scripts/deploy.py, tests/test_deploy_script.py (`test_await_help_refuses_state_of_previous_service_run`)
- **Committed in:** 98a8472

**2. [Процесс] RED-стадия подтверждена ошибкой сбора/атрибута, а не падением assertion**
- **Found during:** Tasks 1-3 (tdd="true")
- **Issue:** тесты писались до модуля, поэтому первый прогон Task 1 упал на `FileNotFoundError` при сборе (строго INVALID_RED по tdd.md); в Tasks 2 и 3 RED дали `AttributeError`/`TypeError` на ещё не существующих функциях (38 и 47 падений). `workflow.tdd_mode` не включён, план имеет `type: execute`, гейт RED-коммита не применялся.
- **Fix:** по одному коммиту на задачу, как требует план; отдельных `test(...)` коммитов нет.

---

**Total deviations:** 1 auto-fixed (Rule 2), 1 процессная заметка
**Impact on plan:** безопасность усилена, объём и интерфейс не изменились.

## Issues Encountered

- Два теста содержали собственные ошибки и были исправлены до коммита: проверка усечения использовала строку из символов `a`, которую `redact` справедливо принимает за hex-последовательность (заменена словами); проверка «нет Traceback» срабатывала на строке таблицы «ERROR/CRITICAL/Traceback» (уточнена до «Traceback (most recent»).
- Хеш `InvocationID` сервиса до и после живых прогонов не сравнивался побайтно: сравнение выполняет план 01-10 (по `<verification>` плана). Сервис не перезапускался.

## Known Stubs

None.

## Threat Flags

None. Новых сетевых точек у сервиса нет; скрипт обращается только к `api.telegram.org/getMe` (в плане, T-01-16). Меры T-01-16 ... T-01-20 реализованы: токен только по ключу `.env` и только класс исключения в выводе, `redact` до усечения, в коде нет `getUpdates` и обращений к сессиям, подпроцессы списком аргументов без shell и с белым списком, файлы состояния и отчёта с правами 0600.

## Next Phase Readiness

- План 01-07 добавляет к `scripts/deploy.py` резервную копию БД, рестарт по флагу и документацию; для рестарта нужно расширить белый список `ensure_read_only` отдельной проверенной командой и тестом.
- Процедуры VERIFICATION фаз 2-5 и 7-9 вызывают флаги `--await-help`, `--confirm-help`, `--report`, `--state-file` (стоимость переименования высокая, имена зафиксированы).
- Допущения плана остаются открытыми: внешний сбой (LMS, IMAP, `database is locked`) в окне старта законно краснит смоук; «Update id=N is handled» не содержит текста команды, поэтому ответ владельца остаётся авторитетным сигналом; при ротации журнала смоук красный с подсказкой.

## Self-Check: PASSED

- FOUND: scripts/deploy.py, tests/test_deploy_script.py
- FOUND коммиты: ea93a1a, 70dba2f, 98a8472 (предки HEAD)
- Полный прогон: 577 passed, 0 skipped/deselected/xfail
- Пре-коммит Security Shield зелёный на всех трёх коммитах; tests/test_hardcode_scanner.py зелёный

---
*Phase: 01-sobstvennyy-geyt-kachestva-assistant-core*
*Completed: 2026-10-09*
