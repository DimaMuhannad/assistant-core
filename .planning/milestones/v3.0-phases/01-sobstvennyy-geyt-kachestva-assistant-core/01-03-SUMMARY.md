---
phase: 01-sobstvennyy-geyt-kachestva-assistant-core
plan: 03
subsystem: testing
tags: [pre-commit, git-hooks, security-shield, assistant-shared, core.hooksPath]

requires:
  - phase: 01-sobstvennyy-geyt-kachestva-assistant-core
    provides: "01-02: собственные тесты shared и pytest-конфигурация (83 теста)"
provides:
  - "/opt/assistant-shared/.githooks/pre-commit: hook запускает только security_shield по индексированным файлам"
  - "/opt/assistant-shared/scripts/install_hooks.sh: воспроизводимая идемпотентная установка через core.hooksPath"
  - "/opt/assistant-shared/scripts/security_shield.py: CLI-обёртка над audit_repository (копия обёртки assistant-core)"
  - "tests/test_pre_commit_hook.py: 8 интеграционных тестов hook и установщика на временных репозиториях"
  - "Hook установлен в самом репозитории shared (core.hooksPath = .githooks)"
affects: [01-05, gate]

actuals:
  tokens: 3500
  tasks: 2
  commits: 2
plan_head_before: 725639982139996a2a174aeaa001366ac1c98825
plan_head_after: 74aa9286406631f8cba13f55e5a1d337acecdaf7

tech-stack:
  added: []
  patterns:
    - "Hook репозитория: фиксированный порядок поиска Python (VIRTUAL_ENV, .venv репозитория, /opt/assistant-core/.venv, python3)"
    - "Установка hook через локальный core.hooksPath; свежий клон требует повторного запуска установщика (fail-closed для гейта)"

key-files:
  created:
    - /opt/assistant-shared/.githooks/pre-commit
    - /opt/assistant-shared/scripts/install_hooks.sh
    - /opt/assistant-shared/scripts/security_shield.py
    - /opt/assistant-shared/tests/test_pre_commit_hook.py
  modified:
    - /opt/assistant-shared/README.md

key-decisions:
  - "scripts/security_shield.py в shared это небольшая копия обёртки assistant-core (OQ5); дрейф копий не проверяется. Единственное отличие: запасной путь sys.path вычисляется от Path(__file__).resolve().parents[1], а не литералом /opt/assistant-shared"
  - "Из порядка поиска Python убраны кандидаты chat-app; в hook нет вызовов pytest (D-04)"

patterns-established:
  - "Коммиты плана делаются в репозиторий shared (ветка master) командой git -C /opt/assistant-shared; SUMMARY и STATE/ROADMAP в assistant-core"

requirements-completed: [GATE-03]

coverage:
  - id: D1
    description: "Pre-commit hook в shared блокирует синтетический секрет и файл .env, пропускает чистый коммит; тест на временном репозитории"
    requirement: GATE-03
    verification:
      - kind: integration
        ref: "cd /opt/assistant-shared && /opt/assistant-core/.venv/bin/pytest tests/test_pre_commit_hook.py (8 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Установщик воспроизводим: работает в worktree, отказывает без файла hook, предупреждает о чужом core.hooksPath, повторный запуск безопасен"
    requirement: GATE-03
    verification:
      - kind: integration
        ref: "tests/test_pre_commit_hook.py#test_wr09_installer_works_in_git_worktree"
        status: pass
      - kind: integration
        ref: "tests/test_pre_commit_hook.py#test_wr09_installer_fails_cleanly_without_hook_file"
        status: pass
      - kind: integration
        ref: "tests/test_pre_commit_hook.py#test_wr09_installer_warns_about_existing_hooks_path"
        status: pass
    human_judgment: false
  - id: D3
    description: "Hook реально установлен в репозитории shared, коммит README прошёл через него, скан shared --all даёт rc 0"
    requirement: GATE-03
    verification:
      - kind: other
        ref: "git -C /opt/assistant-shared config --get core.hooksPath (.githooks); коммит 74aa928 содержит баннер Pre-Commit Hook"
        status: pass
      - kind: other
        ref: "/opt/assistant-core/.venv/bin/python /opt/assistant-shared/scripts/security_shield.py /opt/assistant-shared --all (rc 0)"
        status: pass
    human_judgment: false

duration: 2min
completed: 2026-10-09
status: complete
---

# Phase 1 Plan 03: Pre-commit hook для assistant-shared Summary

**В /opt/assistant-shared установлен pre-commit hook (core.hooksPath = .githooks), который запускает тот же security_shield, что и assistant-core, и блокирует синтетический секрет и файл .env; доказано 8 интеграционными тестами на временных репозиториях.**

## Performance

- **Duration:** 2 мин
- **Started:** 2026-10-09T18:04:16Z
- **Completed:** 2026-10-09T18:05:46Z
- **Tasks:** 2
- **Files modified:** 5 в репозитории shared (4 новых, `README.md`)

## Accomplishments

- Созданы `.githooks/pre-commit`, `scripts/install_hooks.sh`, `scripts/security_shield.py` (все три в git с режимом 100755) и `tests/test_pre_commit_hook.py`. Hook запускает только shield (в файле нет упоминаний pytest, D-04).
- Тест переносит 8 случаев из chat-app: чистый коммит, блокировка секрета, блокировка `.env`, коммит после очистки индекса, установщик в worktree, отказ без файла hook, предупреждение о чужом `core.hooksPath`, поиск Python без `VIRTUAL_ENV` и с урезанным `PATH`. Литералы секретов собраны из частей (`grep` на полный ключ Gemini печатает 0).
- Установщик выполнен в самом shared дважды (идемпотентность подтверждена, в локальной конфигурации одно значение `core.hooksPath`). Коммит README прошёл через установленный hook: баннер Pre-Commit Hook и «Security Shield passed» в выводе коммита.
- README дополнен разделом «Тесты и pre-commit hook» по-русски (запуск тестов, установка hook, скан `--all`, пояснение про D-04 и D-05).
- Полный прогон тестов shared: 91 passed (83 из плана 01-02 и 8 новых), без skip/xfail/deselect. Скан `security_shield.py /opt/assistant-shared --all`: rc 0.

**Копия обёртки shield (OQ5):** `/opt/assistant-shared/scripts/security_shield.py` это небольшая копия `/opt/assistant-core/scripts/security_shield.py`. Дрейф между копиями не проверяется. Различие одно: запасной путь добавления в `sys.path` берётся из `Path(__file__).resolve().parents[1]`.

**Результат установки hook:** `git -C /opt/assistant-shared config --get core.hooksPath` печатает `.githooks`; последний коммит плана (`74aa928`) прошёл через hook.

## Task Commits

Коммиты сделаны в репозитории `/opt/assistant-shared` (ветка `master`), не в assistant-core:

1. **Task 1: hook, установщик, обёртка shield, тест блокировки (tracer)** - `aec78bc` (feat)
2. **Task 2: установка hook в shared, README, коммит через hook** - `74aa928` (docs)

**Plan metadata:** коммит docs(01-03) в assistant-core.

## Files Created/Modified

- `/opt/assistant-shared/.githooks/pre-commit` - hook запускает shield по индексированным файлам
- `/opt/assistant-shared/scripts/install_hooks.sh` - установка через `core.hooksPath`
- `/opt/assistant-shared/scripts/security_shield.py` - CLI-обёртка над `audit_repository` (argparse, неизвестный флаг даёт rc 2)
- `/opt/assistant-shared/tests/test_pre_commit_hook.py` - 8 интеграционных тестов
- `/opt/assistant-shared/README.md` - раздел «Тесты и pre-commit hook»

## Decisions Made

- Следовал плану: порядок поиска Python сокращён до `VIRTUAL_ENV`, `.venv` репозитория, `/opt/assistant-core/.venv`, `python3`.
- Трейсер (Task 1): после коммита `<verify>` перезапущен, 8 passed, расширение продолжено.

## Deviations from Plan

None - plan executed exactly as written.

Процессная заметка: тесты характеризационные (поведение hook перенесено из chat-app), поэтому красной RED-фазы не было; задачи закоммичены по одному коммиту, как требует план (`tdd_mode` не включён).

## Issues Encountered

None.

## Known Stubs

None.

## Threat Flags

None. Новых сетевых точек, путей аутентификации и схемных изменений нет. T-01-07: установщик воспроизводим, строка гейта в плане 01-05 краснит итог, пока hook не установлен. T-01-SC: пакеты не устанавливались, зависимости не менялись.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- План 01-05 (гейт) может проверять `core.hooksPath == .githooks`, исполняемость `.githooks/pre-commit` и запускать `scripts/security_shield.py <shared> --all` и `pytest tests` (91 passed, около 17 с) по shared отдельными строками.
- Свежий клон shared остаётся без hook до запуска `bash scripts/install_hooks.sh`: поведение желательное (fail-closed). Открытый дефект из 01-02 (fastapi не в зависимостях shared) не затронут.

## Self-Check: PASSED

- FOUND: `.githooks/pre-commit`, `scripts/install_hooks.sh`, `scripts/security_shield.py`, `tests/test_pre_commit_hook.py` в `/opt/assistant-shared`; режим 100755 у трёх скриптов
- FOUND коммиты: `aec78bc`, `74aa928` (в репозитории shared)
- `git -C /opt/assistant-shared status --short` пуст, `git -C /opt/chat-app status --short` пуст
- Полный прогон shared: 91 passed; скан rc 0

---
*Phase: 01-sobstvennyy-geyt-kachestva-assistant-core*
*Completed: 2026-10-09*
