---
phase: 02-bezopasnost-privatnost-i-nahodki-revyu
plan: 15
subsystem: rollout
tags: [ops-01, restart, smoke, live-checks, reachability, backup]
status: complete

requires:
  - phase: 02-bezopasnost-privatnost-i-nahodki-revyu
    provides: "планы 02-01..02-14: код фазы, гейт ЗЕЛЁНЫЙ, черновик evidence с перечнем R1-R5"
provides:
  - "02-SMOKE-REPORT.md: отчёт смоука после рестарта, ИТОГ СМОУКА ЗЕЛЁНЫЙ"
  - "02-VERIFICATION-EVIDENCE.md: разделы «Рестарт и смоук», «Живые проверки», R1-R5 со статусом passed"
  - "Изменения фазы 2 работают в живом процессе assistant-worker (новая инвокация)"
  - "Первая живая резервная копия боевой БД (процедура WR-08, WR-09 проверена вживую)"
affects: [02-VERIFICATION]

actuals:
  tokens: 9000
  tasks: 4
  commits: 1
plan_head_before: a115f334c6c963dab9092875bcae1d1748bca264
plan_head_after: 0d31b3712211f26c5cd9c1ab3ea3b59843f951a7

key-files:
  created:
    - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-SMOKE-REPORT.md
  modified:
    - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-VERIFICATION-EVIDENCE.md

key-decisions:
  - "Владелец выбрал рестарт с резервной копией (restart-with-backup); рестарт выполнил сам владелец, потому что запуск агентом был заблокирован правилами прав Claude Code; блокировку никто не обходил"
  - "Красного исхода не было, откат не печатался и не исполнялся"

requirements-completed: [SECF-01, SECF-02, SAFE-01, PRIV-01]
---

# Phase 2 Plan 15: рестарт assistant-worker, смоук OPS-01 и живые проверки Summary

Фаза 2 выкачена в рантайм по процедуре OPS-01 с разрешения владельца: смоук ЗЕЛЁНЫЙ, четыре живые проверки владельца пройдены, evidence для верификатора заполнено (R1-R5 passed).

## Выбор владельца (дословно)

- Рестарт: «Рестарт с резервной копией --backup (Рекомендуется)» (restart-with-backup).
- Ключ `ASSISTANT_DB_PATH_OVERRIDE` в живом `.env`: первый ответ «Не знаю»; затем владелец сам выполнил `grep -c ASSISTANT_DB_PATH_OVERRIDE /opt/assistant-core/.env` и получил `0` (ключа нет). `.env` исполнитель не читал.
- Запись: `/var/tmp/gsd-phase02-verify/restart-note.txt`.

## Что сделано

- **Task 1 (decision):** решение получено опросом в чате, записано в `restart-note.txt`.
- **Task 2 (tracer):** запуск `python3 scripts/deploy.py --restart --backup --report …/02-SMOKE-REPORT.md` агентом был заблокирован правилами прав Claude Code (причина отказа «Production Deploy»), блокировку никто не обходил. Команду выполнил владелец в этой сессии, код возврата 0, один рестарт.
  - InvocationID `40e9fe7aaf694e44974e2f7b55206f32` -> `25ff0740810d4783ae1ba7721b6f836c`; MainPID 295112 -> 893511; NRestarts 0; сервис active.
  - Автоматическая часть ЗЕЛЁНАЯ: 7 строк ✓ (рестарт, сервис active, журнал доступен, нет ERROR/CRITICAL/Traceback в окне старта, polling запущен, планировщик 10 из 10, `getMe` жив); ошибок и WARNING в окне старта нет.
  - После `--await-help` (обработанное обновление) и ответа владельца «Да, ответ пришёл, блок есть» выполнен `--confirm-help yes` с `--report`: **ИТОГ СМОУКА: ЗЕЛЁНЫЙ**.
  - Резервная копия: `/var/backups/assistant-core/assistant-20261010-172727.db`, 8695808 байт, права 0600, каталог 0700; содержимое не читалось.
- **Task 3 (checkpoint):** живые проверки владельца опросами в чате (дословно): `/help`: «Да, ответ пришёл, блок есть»; «очисти диалог»: «Предупреждение с /clear, карточки нет»; сообщение о почте: «Да, ровно одно». Записей `PRIV-01:` в журнале текущей инвокации: **1**; ERROR/CRITICAL/Traceback: 0.
- **Task 4 (auto), коммит `0d31b37`:** разделы «Рестарт и смоук» и «Живые проверки», столбец живых доказательств и статусы R1-R5 (все passed), указание верификатору, обновлены «Открытые пункты». Автоматические проверки задачи (разделы, R1-R5, нет заготовок, нет e-mail, токенов и запретных слов персоны) зелёные.
- **Гейт после рестарта:** `python3 scripts/gate.py` **ИТОГ: ЗЕЛЁНЫЙ** (11 строк ✓, assistant-core 977 тестов, assistant-shared 197, «SHA-256 до/после совпали»); повтор не понадобился. Вывод: `/var/tmp/gsd-phase02-verify/gate-run-after-restart.txt`.

## Пункты критерия успеха 5

| Пункт | Статус | Источник |
|---|---|---|
| R1 `/help` с блоком приватности | passed | ответ владельца, отчёт смоука |
| R2 сообщение «Приватность почты» и 1 запись PRIV-01 | passed | ответ владельца, счёт по журналу инвокации |
| R3 «очисти диалог» даёт предупреждение с `/clear` | passed | ответ владельца, тесты 02-02 и 02-14 |
| R4 `scripts/security_shield.py` как точка входа аудита | passed | тесты достижимости 02-14, гейт ЗЕЛЁНЫЙ |
| R5 рестарт по разрешению владельца, смоук OPS-01 | passed | `02-SMOKE-REPORT.md`, `restart-note.txt` |

## Deviations from Plan

**1. [Организационное] Рестарт выполнил владелец, не агент.** Запуск `deploy.py --restart --backup` агентом отклонён классификатором прав; по правилам задачи обхода не было, оркестратор сообщил владельцу, команда выполнена им самим (OPS_DEPLOY.md, раздел 2а это допускает). Смоук и отчёт те же, что при запуске агентом. Правок кода нет.

Иных отклонений нет.

## Auth gates

Нет.

## Known Stubs

Нет.

## Threat Flags

Нет новой поверхности.

## Заметки и открытые пункты

- `chat-app.service` не перезапускался (вне плана). После будущего рестарта web-аудит chat-app покажет находки по запретным словам пространства в `config/persona.yaml` (три известные) и замороженные; решение владельца, сохранение этих слов в публичном файле относится к Phase 8.
- Плавающий тест `test_concurrent_confirmations_isolation` (`database is locked`, примерно 1 прогон из 10) остаётся в `deferred-items.md` как решение владельца.
- Первая живая резервная копия сделана сейчас; перед миграцией `0003` в Phase 3 нужна новая копия с отдельным разрешением владельца.
- Побочные записи демона после рестарта: флаг `notice:email_ai` в боевой БД и одно сообщение «Приватность почты» (штатно, не смоук).
- **`02-VERIFICATION.md` пишет верификатор GSD по перечню R1-R5 из `02-VERIFICATION-EVIDENCE.md`; этот план его не создаёт, SUMMARY его не заменяет.** Фаза не закрыта до появления этого файла.

## Self-Check: PASSED

- FOUND: `02-SMOKE-REPORT.md`, `02-VERIFICATION-EVIDENCE.md`, `/var/tmp/gsd-phase02-verify/restart-note.txt`, `/var/tmp/gsd-phase02-verify/live-checks.txt`
- FOUND commit `0d31b37` (предок HEAD)
- Сервис active, InvocationID `25ff0740…` отличается от базовой линии
