---
phase: 05-retro-verifikatsiya-v2-0
plan: 07
subsystem: verification
tags: [DAT-02, DAT-03, db-path, wal, busy_timeout, retro-verification, V2-04]
requires: [05-05, 05-06]
provides: [V2-04-VERIFICATION.md verdicts DAT-02, DAT-03; frontmatter total for V2-04]
affects: [05-08]
requirements: [VER-01, DAT-02, DAT-03]
key-files:
  created:
    - .planning/phases/05-retro-verifikatsiya-v2-0/05-07-SUMMARY.md
  modified:
    - .planning/phases/05-retro-verifikatsiya-v2-0/V2-04-VERIFICATION.md
decisions:
  - "DAT-03 gap по протоколу 60 прогонов (free 1/30, load 0/30, K=1 J=0), класс целостность данных, предложение DAT-05 передано 05-08; тест не перепрогонялся"
  - "DAT-02 gap: журнал воркера /opt/assistant-core/data/assistant.db не совпадает с путём chat-app /opt/chat-app/backend/data/assistant.db (ответ владельца), класс целостность данных, предложение DAT-06 передано 05-08"
  - "V2-04 итог: status gaps_found, 3 из 6 требований passed (SEC-01, SEC-02, SEC-03); gap: DAT-02, DAT-03, DAT-04"
  - "test_db_config.py не запускался: импорт app/core/config.py читает .env chat-app; проверка выполнена по источнику"
metrics:
  duration: "~25 мин (22:17-22:47 UTC, включая паузу на ответ владельца)"
  completed: 2026-10-18
  tasks: 3
  files: 2
status: complete
commits: 0
plan_head_before: 67aedc72120a3da55f133cce68ce981027399322
plan_head_after: 67aedc72120a3da55f133cce68ce981027399322
actuals:
  tokens: 8117
  tasks: 3
  commits: 0
---

# Phase 5 Plan 07: V2-04 вердикты DAT-02 и DAT-03, итог V2-04 — Summary

**DAT-03 вынесен gap по протоколу 60 прогонов (free 1 из 30). DAT-02 вынесен gap: журнал воркера и путь chat-app указывают на разные файлы БД. V2-04 завершён со статусом gaps_found, 3 из 6 требований passed.**

## Результаты

| Требование | Статус | Метка | Основание |
|---|---|---|---|
| DAT-02 | gap | трасса | `realpath -m`: `/opt/assistant-core/data/assistant.db` (журнал воркера, текущая инвокация) против `/opt/chat-app/backend/data/assistant.db` (ответ владельца) |
| DAT-03 | gap | e2e | `05-EVIDENCE-DAT03.md`: free 1/30 (free-27, `database is locked` в `connection.py:64`), load 0/30, K=1 J=0 |
| DAT-04 | gap | e2e | без изменений, из 05-06 |
| SEC-01 | passed | трасса+e2e | без изменений, из 05-06 |
| SEC-02 | passed | трасса+e2e | без изменений, из 05-06 |
| SEC-03 | passed | e2e | без изменений, из 05-06 |

Итог frontmatter V2-04: `status: gaps_found`, `score: "3 из 6 требований passed"`, `gaps: [DAT-02, DAT-03, DAT-04]`.

## Ответ владельца (только путь)

Путь chat-app получен одним ответом владельца на команду из checkpoint Task 2 (решение владельца 2026-10-18 №4). Записан только путь: `/opt/chat-app/backend/data/assistant.db`. Агенты `.env` chat-app не читали и настройки chat-app не импортировали. Ответ получен с третьей попытки, первые две не выполнены по причинам запуска команды.

## Deviations from Plan

### Не выполнено по запрету

**1. `backend/tests/test_db_config.py` не запускался (Task 3, шаг verify).**
- **Найдено при:** чтении `app/core/config.py` перед запуском.
- **Причина:** модуль создаёт `settings = Settings()` на уровне модуля с `env_file=".env"`. Импорт из теста читает `.env` chat-app, что запрещено (T-05-19, требование оркестратора «не импортировать настройки chat-app»).
- **Замена:** проверка по источнику. `app/core/config.py:20-22` содержит `./data/assistant.db` по умолчанию и не содержит хардкода `/opt/assistant-core`. Результат записан в «Ограничения проверки», п. 9.
- **Влияние:** автоматический шаг verify Task 3 с pytest не выполнен. Вердикт DAT-02 опирается на сравнение путей и статику, а не на тест.

### Вне отклонений

- Вердикт DAT-02 по протоколу плана дан как gap. Требование DAT-02 по букве («путь берётся из настроек в обоих процессах») выполняют оба процесса. Оговорка записана в `### DAT-02` и требует решения владельца (см. ниже).
- Полный прогон под strace из 05-06 дал второй сбой `test_concurrent_write_two_processes` (1 из 1 полного прогона). Это наблюдение вне протокола D-08, в вердикт DAT-03 не входит.

## Known Stubs

None.

## Threat Flags

None. Новых поверхностей не найдено; T-05-19, T-05-20, T-05-21 закрыты по плану (путь получен от владельца, `Environment` не выведен, посторонний `assistant.db` описан только `ls -l`).

## Gaps, переданные плану 05-08

| Gap | Класс D-09 | Серьёзность | Предложение |
|---|---|---|---|
| DAT-02 | целостность данных | high | новое требование DAT-06 (chat-app и демон работают с одной БД), Phase 999.x |
| DAT-03 | целостность данных | high | новое требование DAT-05 (стабильная конкурентная запись двух процессов), Phase 999.x |
| DAT-04 (а) | целостность данных | critical | DAT-07 (из 05-06, без изменений) |
| DAT-04 (б) | улучшение | low | бэклог 999.x (из 05-06, без изменений) |

## Решения владельца, нужные до закрытия фазы

1. DAT-02: принять gap по протоколу сравнения путей либо переформулировать требование («путь обоих процессов один и тот же»).
2. DAT-03 и DAT-02: подтвердить запись в бэклог Phase 999.x или выбрать другой порядок (решение за 05-08).

## Self-Check

- Строки DAT-02, DAT-03, DAT-04, SEC-01, SEC-02, SEC-03 присутствуют в V2-04-VERIFICATION.md, каждая с `passed` или `gap` (проверено grep).
- Статус DAT-03 согласован с вердиктом `05-EVIDENCE-DAT03.md` (`**Вердикт DAT-03:** gap`); строка DAT-03 содержит gap и упоминание DAT-05.
- Строка DAT-02 gap содержит предложение DAT-06.
- Адресов e-mail в V2-04-VERIFICATION.md нет (grep: 0).
- Вне `.planning/` изменений нет (`git status`).
- `scripts/gate.py` не запускался, код и тесты не менялись, миграций нет, `REQUIREMENTS.md` статусы не менялись, `.planning/config.json`, `state.json`, `milestone.lock` не стейджены.

## Self-Check: PASSED
