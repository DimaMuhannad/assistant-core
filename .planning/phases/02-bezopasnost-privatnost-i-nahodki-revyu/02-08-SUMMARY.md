---
phase: 02-bezopasnost-privatnost-i-nahodki-revyu
plan: 08
subsystem: security
tags: [security-shield, nda, air-gap, persona, fail-closed, secf-01, pre-commit-hook]

requires:
  - phase: 02-bezopasnost-privatnost-i-nahodki-revyu
    provides: "02-06: audit_repository(workspaces=...), match_workspace; 02-07: chat-app переведён на данные и делегатор"
provides:
  - "scripts/security_shield.py: main(argv=None), правила NDA из workspaces персоны, без констант слов и допусков"
  - "tests/test_security_shield_cli.py: 12 интеграционных тестов обёртки (подпроцесс, как hook и гейты)"
  - "tests/test_nda_script_parity.py на данных персоны со строгой заглушкой audit_repository"
  - "tests/test_synthetic_persona.py::test_no_real_nda_keywords на данных персоны (файл байт-в-байт равен копии chat-app)"
affects: [02-09, 02-10, 02-11, chat-app, pre-commit-hook]

actuals:
  tokens: 6000
  tasks: 3
  commits: 2
plan_head_before: 62b7f24a882008f51426cddf801f55cf6da30709
plan_head_after: 7f91310d13902f73517ed2e08bf0b0fbfe779845

tech-stack:
  added: []
  patterns:
    - "Обёртка CLI грузит персону внутри main(), а не при импорте; любая ошибка загрузки даёт rc=1 и сообщение с именем класса исключения без значений"
    - "Тест паритета подменяет audit_repository заглушкой со строгой сигнатурой: лишний аргумент (допуск, смягчение) краснит тест"

key-files:
  created:
    - tests/test_security_shield_cli.py
  modified:
    - scripts/security_shield.py
    - tests/test_nda_script_parity.py
    - tests/test_synthetic_persona.py

key-decisions:
  - "D-21 выдержан: допуска слов нет ни в обёртке, ни в тестах; файл персоны даёт одинаковые находки в режиме фиксации и в --all"
  - "SECF-01 в REQUIREMENTS.md не отмечен: литералы слов остаются в библиотеке до плана 02-10 (как зафиксировано в 02-07)"

patterns-established:
  - "Синтетические слова и адреса в тестах собираются из частей; значения реальной персоны читаются во время теста и не печатаются"

requirements-completed: []
requirements-progress: [SECF-01]

coverage:
  - id: C1
    description: "Обёртка передаёт данные workspaces персоны в audit_repository тремя аргументами (repo, check_staged_only, workspaces); NDA по пути и по remote работает сквозным сценарием"
    requirement: SECF-01
    verification:
      - kind: integration
        ref: "tests/test_security_shield_cli.py (трассер: запрещённый origin rc=1 + RESTRICTED + CRITICAL; безопасный origin rc=0), tests/test_nda_script_parity.py"
        status: pass
    human_judgment: false
  - id: C2
    description: "Fail-closed: отсутствующий, не-YAML и невалидный по схеме файл персоны дают rc=1 и SECURITY SHIELD ERROR без значений из файла, в обоих режимах"
    requirement: SECF-01
    verification:
      - kind: integration
        ref: "tests/test_security_shield_cli.py::test_fail_closed_on_unavailable_persona_without_echoing_file_content"
        status: pass
    human_judgment: false
  - id: C3
    description: "Hook и shield не ослаблены (D-21): файл персоны с объявленными словами даёт одинаковое число находок в режиме фиксации и в --all; в обёртке нет слова allowance"
    requirement: SECF-01
    verification:
      - kind: integration
        ref: "test_persona_file_gives_findings_in_commit_mode_without_allowance, test_persona_file_gives_same_findings_in_full_audit; реальный запуск на копии config/ (3 и 3)"
        status: pass
    human_judgment: false
  - id: C4
    description: "Реальный shield --all на assistant-core: ровно три находки nda-keyword в config/persona.yaml, rc=1, как до фазы; оба гейта зелёные; потребитель chat-app зелёный"
    requirement: SECF-01
    verification:
      - kind: integration
        ref: "scripts/security_shield.py . --all (3 находки); python3 scripts/gate.py (assistant-core, 895+182): ИТОГ ЗЕЛЁНЫЙ; /opt/chat-app gate: ИТОГ ЗЕЛЁНЫЙ; pytest chat-app 261 passed; pytest shared 182 passed"
        status: pass
    human_judgment: false

duration: 45min
completed: 2026-10-10
status: complete
---

# Phase 2 Plan 08: Обёртка shield на данных персоны Summary

**`scripts/security_shield.py` (цель pre-commit hook и гейтов) теперь грузит `workspaces` из персоны и передаёт их в `audit_repository`; при любой проблеме с данными rc=1 без значений, а допусков слов нет ни в режиме фиксации, ни в `--all` (D-21).**

## Performance

- **Duration:** около 45 мин
- **Completed:** 2026-10-10
- **Tasks:** 3 (tracer, auto tdd, проверочная); коммитов 2 (Task 3 правок кода не потребовала)
- **Files:** 1 создан, 3 изменены

## Сигнатуры обёртки

- `main(argv: list[str] | None = None) -> int`: разбор аргументов (`path` по умолчанию «.», `--all`; неизвестный флаг даёт rc=2 до загрузки персоны), затем загрузка правил, затем `audit_repository(repo, check_staged_only=not args.all, workspaces=workspaces)` ровно с этими тремя аргументами.
- `_load_workspaces() -> tuple[list[dict], PersonaConfig]`: вставляет корень assistant-core в `sys.path`, импортирует `src.persona.loader.load_persona`, возвращает `[ws.model_dump() ...]` и персону. Вызывается из `main`, при импорте модуля персона не читается.
- `_report_unavailable(exc)`: печатает «❌ SECURITY SHIELD ERROR: данные рабочих пространств недоступны (ИмяКласса) …»; для `PersonaConfigError` добавляет его безопасный текст. Возврат 1.
- Экспортируется `["audit_repository", "main"]`; константы слов NDA и её экспорта нет.

## Сценарии CLI-тестов (12)

| Сценарий | Результат |
|---|---|
| Трассер: репозиторий в пути NDA-пространства, запрещённый origin | rc=1, RESTRICTED, CRITICAL |
| Трассер: тот же путь, безопасный origin | rc=0, RESTRICTED |
| Неизвестный флаг при отсутствующем файле персоны | rc=2, персона не грузилась |
| Импорт модуля при отсутствующем файле персоны | не падает, ничего не печатает |
| В модуле и исходнике нет константы слов NDA | подтверждено |
| Несопоставленный репозиторий | rc=0, есть «⚠️», нет 🚨 |
| Публичный репозиторий со словом NDA в другом регистре / NDA-репозиторий с тем же файлом | rc=1 с «Found proprietary corporate keyword» / rc=0 |
| Файл персоны отсутствует, не YAML, не проходит схему (оба режима) | rc=1, SECURITY SHIELD ERROR, маркер из файла в выводе не появляется |
| Сопоставление только по remote | RESTRICTED, слова не ищутся, rc=0 |
| Файл персоны в индексе, режим фиксации (D-21) | rc=1, 3 находки |
| Тот же репозиторий, `--all` (D-21) | rc=1, 3 находки, число равно режиму фиксации |
| Персона вне репозитория, слов в репозитории нет, оба режима | rc=0 |

`tests/test_nda_script_parity.py`: два теста (нет констант слов; строгая заглушка `(repo_path, check_staged_only, *, workspaces)` получает `workspaces` равные `[ws.model_dump() ...]` персоны по умолчанию в обоих режимах). `test_no_real_nda_keywords` берёт слова из фикстуры `default_persona_config`, `_load_shield` удалён.

## Проверки (только счётчики, значения не печатались)

| Проверка | Результат |
|---|---|
| `security_shield.py . --all` в assistant-core | rc=1, находок слов NDA ровно 3, все в `config/persona.yaml`, других нарушений нет |
| Режим фиксации на копии `config/` во временном git-репозитории | rc=1, 3 находки |
| Режим `--all` на той же копии | rc=1, 3 находки (равно режиму фиксации) |
| pytest целевых файлов плана (CLI, parity, synthetic, loader, hardcode) | 56 passed |
| pytest shared | 182 passed |
| pytest chat-app (делегатор вызывает новую обёртку) | 261 passed |
| гейт assistant-core | ИТОГ: ЗЕЛЁНЫЙ (895 core, 182 shared, дрейф синтетической персоны и токенов зелёный, живая БД не менялась) |
| общий гейт chat-app | ИТОГ: ЗЕЛЁНЫЙ (261 chat-app, 895 assistant-core) |
| `grep -ci allowance scripts/security_shield.py` | 0 |
| `git -C /opt/chat-app status --short` | только `?? .watchdog_disabled` (существовал до фазы, см. 02-07); `scripts/gate.py` chat-app не менялся |

## Deviations from Plan

### Auto-fixed Issues

None - plan executed as written, с двумя уточнениями без отклонения от замысла:

- Task 3, шаг (2): копия одного `config/persona.yaml` во временном каталоге давала `PersonaConfigError` (шаблоны `persona.prompts` лежат рядом в `config/prompts`), то есть fail-closed rc=1 без находок. Проверка повторена с копией всего каталога `config/`: 3 находки в обоих режимах. Это ожидаемое поведение загрузчика, правок кода не потребовалось.
- `tests/test_synthetic_persona.py` приведён к байт-в-байт равному виду с копией chat-app (неиспользуемые импорты `importlib.util` и `Path` убраны вместе с `_load_shield`).

## Auth gates

None.

## Known Stubs

None.

## Threat Flags

None. Новых сетевых точек, путей аутентификации и обращений к файлам на границах доверия нет. T-02-26 (битая персона), T-02-27 (значения в сообщениях) и T-02-28 (ослабление hook) закрыты тестами; T-02-29 принят (PERSONA_CONFIG_PATH в доверенном окружении).

## Для следующих планов

- Известное следствие D-21: pre-commit hook блокирует любой коммит, затрагивающий `config/persona.yaml` (три находки). Коммит файла персоны в фазе делается только разовым `--no-verify` по явному согласию владельца (чекпоинт плана 02-11); в этом плане файл персоны не менялся и не коммитился.
- SECF-01 не отмечен выполненным: литералы слов NDA остаются в библиотеке до плана 02-10, который удаляет прежние имена и добавляет проверку отсутствия литералов. Предпроверка 02-07 предполагает, что после этого плана красных тестов chat-app против копии итоговой библиотеки не остаётся.
- Остаточный долг из 02-07 (старый литерал аккаунта в `backend/tests/test_security_shared.py` chat-app) по-прежнему учесть в плане 02-10.

## Self-Check: PASSED

- `scripts/security_shield.py`, `tests/test_security_shield_cli.py`, `tests/test_nda_script_parity.py`, `tests/test_synthetic_persona.py` найдены
- коммиты `3fb4885` и `7f91310` существуют в `main`
