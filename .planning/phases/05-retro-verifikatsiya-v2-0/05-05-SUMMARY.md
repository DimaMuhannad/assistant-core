---
phase: 05-retro-verifikatsiya-v2-0
plan: 05
subsystem: verification
tags: [DAT-03, sqlite, concurrency, evidence]
requires: [05-04]
provides: [DAT-03 evidence protocol and verdict]
affects: [05-07, 05-08]
requirements: [DAT-03]
key-files:
  created:
    - .planning/phases/05-retro-verifikatsiya-v2-0/05-EVIDENCE-DAT03.md
  modified: []
decisions:
  - "DAT-03 вынесен вердикт gap по критерию D-08: 1 сбой из 30 в режиме free (free-27, database is locked)"
  - "Причина сбоя не исследовалась и не чинилась (D-10); предложение DAT-05 передано плану 05-08"
metrics:
  duration: "~12 мин (22:08-22:16 UTC)"
  completed: 2026-10-18
  tasks: 3
status: complete
actuals:
  tokens: 3616
  tasks: 3
  commits: 1
---

# Phase 5 Plan 05: DAT-03 повторный прогон нестабильного теста — Summary

**60 последовательных прогонов test_concurrent_write_two_processes (30 свободно, 30 под нагрузкой): free 1/30 сбоев, load 0/30, вердикт DAT-03 — gap.**

## Результаты

| Режим | Прогонов | Сбоев | Секунды (мин / медиана / макс) |
|---|---|---|---|
| free | 30 | 1 (free-27: `sqlite3.OperationalError: database is locked`) | 1.4 / 1.8 / 18.5 |
| load | 30 | 0 | 1.2 / 1.8 / 34.1 |

- Полные прогоны набора chat-app под нагрузкой: K = 1, J = 0 (279 passed, 168 с, rc 0).
- Проба probe-00 (вне 60): OK.
- MemAvailable: старт 873 МБ, минимум за окно нагрузки 801 МБ; прерываний по памяти нет.
- assistant-worker до и после: ActiveState=active, NRestarts=0, ActiveEnterTimestamp не изменился.
- chat-app `git status --porcelain --ignored` до и после совпал.

## Deviations from Plan

None — план выполнен по протоколу. Единственное техническое уточнение: каталог проб `/var/tmp/gsd-phase05-probes/dat03/` создан `mkdir -m 0700` только для листового каталога; права выставлены на все каталоги вручную (0700).

## Known Stubs

None.

## Threat Flags

None.

## Self-Check

- Файл `05-EVIDENCE-DAT03.md` содержит 30 строк free-NN, 30 строк load-NN, строку probe-00, итоги, тексты ошибок, строку вердикта `gap`.
- Тест, код, миграции и REQUIREMENTS.md не менялись.

## Self-Check: PASSED
