---
phase: 02-bezopasnost-privatnost-i-nahodki-revyu
plan: 01
subsystem: security
tags: [assistant-shared, security-scanner, nda, air-gap, secf-02, scan_file_content]

requires:
  - phase: 01-sobstvennyy-geyt-kachestva-assistant-core
    provides: "01-02/01-03: собственные тесты shared (91) и pre-commit hook в shared"
provides:
  - "/opt/assistant-shared/assistant_shared/security/scanner.py: Finding, scan_file_content, is_forbidden_name, format_cli, format_web"
  - "NdaRemoteRule.forbidden_keywords и collect_protected_keywords(workspaces) в rules.py"
  - "audit_path(forbidden_keywords=...): слова NDA других пространств ищутся в публичном каталоге"
  - "check_file_content и check_index_content работают через scan_file_content; _scan_lines удалён"
  - "tests/test_scan_file_content.py: 54 теста на синтетических словах"
affects: [02-06, 02-10, 02-11, security_shield, chat-app]

actuals:
  tokens: 9600
  tasks: 2
  commits: 2
plan_head_before: 74aa9286406631f8cba13f55e5a1d337acecdaf7
plan_head_after: c09124879d92354538cf747cff1ea5c531b06ddf

tech-stack:
  added: []
  patterns:
    - "Один сканер текста для web и CLI: чистая функция (путь, текст) -> список Finding, форматирование отдельными функциями, чтение с диска остаётся в auditor.py"
    - "Слова NDA едут внутри NdaRemoteRule; web-сообщение о слове не печатает само слово"

key-files:
  created:
    - /opt/assistant-shared/assistant_shared/security/scanner.py
    - /opt/assistant-shared/tests/test_scan_file_content.py
  modified:
    - /opt/assistant-shared/assistant_shared/security/auditor.py
    - /opt/assistant-shared/assistant_shared/security/rules.py
    - /opt/assistant-shared/assistant_shared/security/__init__.py

key-decisions:
  - "D-21 закреплён кодом и тестами: у scan_file_content, check_file_content, check_index_content нет параметров допуска; сигнатуры проверяются inspect.signature, в каталоге библиотеки нет слова allowance, слово в config/persona.yaml даёт находку как в любом файле"
  - "check_index_content приводит CRLF и одиночный CR к LF перед сканированием (как текстовое чтение рабочей копии), чтобы номера строк из индекса и из файла совпадали"
  - "Запрещённое имя в check_file_content проверяется до открытия файла по полному пути (как раньше), в web и check_index_content по относительному пути"

patterns-established:
  - "Коммиты плана в /opt/assistant-shared (ветка master), SUMMARY и STATE/ROADMAP в assistant-core"

requirements-completed: [SECF-02]

coverage:
  - id: D1
    description: "scan_file_content единая для web и CLI: запрещённое имя даёт одну находку без разбора содержимого, секреты по всему тексту (PEM, многострочный Generic Bearer), слова NDA без учёта регистра, пустой текст даёт ноль"
    requirement: SECF-02
    verification:
      - kind: unit
        ref: "tests/test_scan_file_content.py (все девять шаблонов SECRET_PATTERNS, PEM на строке 3, Bearer через перевод строки, регистр, пустой текст)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Web-путь audit_path ищет forbidden_keywords только в не-NDA каталоге при is_public_repo, ответ без текста слова, прежние тексты и гранулярность"
    requirement: SECF-02
    verification:
      - kind: integration
        ref: "tests/test_scan_file_content.py#test_audit_path_keyword_in_public_dir_is_one_violation_without_the_word и соседние три теста (NDA-каталог, is_public_repo=False, без аргумента)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Паритет web и CLI: один текст даёт одинаковые множества находок; Read error остаётся одной находкой при подмене auditor.open; индекс против рабочей копии; сигнатуры без параметров допуска"
    requirement: SECF-02
    verification:
      - kind: integration
        ref: "tests/test_scan_file_content.py#test_web_and_cli_give_the_same_findings_for_the_same_text, #test_read_error_gives_exactly_one_read_error_finding, #test_check_index_content_reads_the_index_version_not_the_working_copy, #test_cli_check_signatures_have_no_tolerance_parameter"
        status: pass
    human_judgment: false
  - id: D4
    description: "Потребители не сломаны: полный pytest chat-app, тест потребителя assistant-core и аудит shield с тремя известными находками"
    requirement: SECF-02
    verification:
      - kind: integration
        ref: "cd /opt/chat-app && backend/.venv/bin/pytest backend/tests (251 passed); cd /opt/assistant-core && .venv/bin/pytest tests/test_nda_script_parity.py (2 passed)"
        status: pass
      - kind: other
        ref: "security_shield.py . --all в assistant-core: ровно 3 находки, все 3 в persona.yaml (сравнивались только счётчики)"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-10-10
status: complete
---

# Phase 2 Plan 01: Общая функция сканирования файла Summary

**Web-аудит и CLI-проверки в assistant-shared сведены к одной чистой функции `scan_file_content`; web-путь научен искать слова NDA других пространств через `NdaRemoteRule.forbidden_keywords`, механизма допуска слов нет ни для одного файла (D-21).**

## Performance

- **Duration:** около 25 мин (продолжение после остановки предыдущего исполнителя; код `scanner.py`, `rules.py`, `__init__.py` и `audit_path` были в рабочей копии, проверены по плану и закоммичены вместе с тестами)
- **Completed:** 2026-10-10
- **Tasks:** 2
- **Files:** 5 в репозитории shared (2 новых, 3 изменённых)

## Accomplishments

- `scanner.py`: `Finding(kind, name, line)`, `scan_file_content(rel_path, text, *, keywords=())`, `is_forbidden_name(rel_path)`, `format_cli(display_path, finding)`, `format_web(rel_path, finding)`. Модуль чистый, без обращений к диску. Порядок: запрещённое имя (одна находка, текст не разбирается), секреты по всему тексту с номером строки по смещению совпадения, слова NDA построчно через `casefold`, сортировка по строке (секреты раньше слов).
- `rules.py`: `NdaRemoteRule.forbidden_keywords=()` (двухаргументный конструктор chat-app работает), `nda_rule_for` принимает `Mapping` и заполняет слова, `collect_protected_keywords` берёт слова только из `restricted_nda` и схлопывает дубликаты по `casefold`.
- `auditor.py`: `audit_path(forbidden_keywords=...)` ищет слова только при `nda_rule is None` и `is_public_repo`; запрещённое имя больше не вызывает чтения содержимого; web-находки схлопываются по паре (файл, шаблон), слово NDA в ответ не попадает. `check_file_content` и `check_index_content` вызывают общую функцию, `_scan_lines` и `_forbidden_name_violation` удалены, сигнатуры прежние.
- Тесты: 54 теста в `tests/test_scan_file_content.py` (460 строк), все слова и секреты собраны из частей, реальных слов NDA и аккаунтов нет.

## Сигнатуры

- `scan_file_content(rel_path: str, text: str, *, keywords: Iterable[str] = ()) -> list[Finding]`
- `is_forbidden_name(rel_path: str) -> bool`
- `format_cli(display_path: object, finding: Finding) -> str`, `format_web(rel_path: str, finding: Finding) -> str`
- `collect_protected_keywords(workspaces: Iterable[Mapping[str, Any]]) -> tuple[str, ...]`
- `audit_path(target_path, nda_rule=None, is_public_repo=True, max_files=5000, forbidden_keywords=())`
- `check_file_content(file_path, is_public_repo=True, custom_keywords=None)` и `check_index_content(repo_path, rel_path, is_public_repo=True, custom_keywords=None)` без изменений

## Проверки

| Проверка | До | После |
|---|---|---|
| pytest shared | 91 passed | 145 passed (91 + 54 новых) |
| полный pytest chat-app (потребитель) | - | 251 passed, `git -C /opt/chat-app status --short` пуст |
| `tests/test_nda_script_parity.py` (assistant-core) | - | 2 passed |
| shield `. --all` в assistant-core | 3 находки | 3 находки, все 3 в `config/persona.yaml` |
| grep allowance в `assistant_shared/security` | - | 0 вхождений |

## Task Commits

Коммиты сделаны в `/opt/assistant-shared` (ветка `master`):

1. **Task 1 (tracer): scan_file_content, слова NDA в правиле и web-аудите** - `7374893` (feat)
2. **Task 2: check_file_content и check_index_content на общей функции** - `c091248` (refactor)

**Plan metadata:** коммит docs(02-01) в assistant-core (SUMMARY, STATE, ROADMAP, REQUIREMENTS).

## Decisions Made

См. frontmatter. Главное: допуска слов нет (D-21); индекс нормализует переводы строки как рабочая копия.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Запрещённое имя в check_file_content проверялось бы после чтения файла**
- **Found during:** Task 2
- **Issue:** первая версия переписанной `check_file_content` открывала файл раньше, чем проверялось запрещённое имя: `.env` без права чтения дал бы «Read error» вместо находки, а содержимое секретного файла читалось без нужды (прежний код проверял имя до открытия).
- **Fix:** проверка `is_forbidden_name(str(file_path))` вынесена перед `open`.
- **Files modified:** `assistant_shared/security/auditor.py`
- **Commit:** `c091248`

**2. [Rule 1 - Bug] Расхождение нумерации строк между индексом и рабочей копией**
- **Found during:** Task 2
- **Issue:** `splitlines` прежней версии делил индекс по CRLF/CR, а новая `split("\n")` по декодированным байтам оставила бы CRLF одной строкой при одиночном CR.
- **Fix:** текст из индекса приводится к LF (`\r\n` и `\r` в `\n`), как делает текстовое чтение; тест `test_check_index_content_crlf_lines_are_counted_like_working_copy`.
- **Commit:** `c091248`

### Процессные заметки

- Тесты Task 1 и Task 2 написаны после кода (код Task 1 перешёл из предыдущего запуска), красной фазы RED для `tdd="true"` Task 2 не было; поведение закреплено характеризационными тестами, `tdd_mode` не включён.
- Тест паритета web/CLI сравнивает нормализованные множества (имя файла, вид, шаблон), как требует план.
- `check_index_content` не экспортируется пакетом (план этого не требует), тесты импортируют его из `assistant_shared.security.auditor`.
- Авторская идентичность в `/opt/assistant-shared` не настроена (git выдаёт предупреждение о автоматическом имени); конфигурация не менялась.

## Known Stubs

None.

## Threat Flags

None. Новых сетевых точек, путей аутентификации и обращений к файлам нет; поверхность сузилась (запрещённое имя больше не приводит к чтению содержимого).

## Issues Encountered

Предыдущий запуск остановился на записи тестового файла в `/opt/assistant-shared`; после добавления каталога в рабочие директории записи прошли без обходов.

## Next Phase Readiness

План 02-06 может передавать слова NDA из персоны в `audit_path` через `collect_protected_keywords`; `CORPORATE_NDA_KEYWORDS` остаётся значением по умолчанию до плана 02-10. Коммит `config/persona.yaml` (план 02-11) потребует разового `--no-verify` по согласию владельца: слово NDA в файле персоны по-прежнему даёт находку (три известные в shield).

## Self-Check: PASSED

- scanner.py: найден; tests/test_scan_file_content.py: найден
- коммиты `7374893` и `c091248` являются предками HEAD в `/opt/assistant-shared`
