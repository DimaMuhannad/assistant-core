# Phase 5 Plan 04: V2-09 верификация (UXQ-01, UXQ-02, UXQ-04) Summary

**V2-09-VERIFICATION.md по фазе 09 v2.0: UXQ-02 passed (трасса+e2e), UXQ-01 gap и UXQ-04 gap с привязкой к бэклогу; доказано из рантайма журналом старта и read-only смоуком deploy.py.**

---
phase: 05-retro-verifikatsiya-v2-0
plan: 04
subsystem: verification
tags: [retro-verification, v2.0, telegram-bot, bot-menu, aliases, feedback, edge-cache, connector-alerts]

requires:
  - phase: 03-vladenie-shemoy-bd
    provides: миграция 0003 (bot_command_settings, bot_custom_aliases, dialog_feedback_log)
provides:
  - V2-09-VERIFICATION.md с вердиктами UXQ-01 (gap), UXQ-02 (passed), UXQ-04 (gap), трассой file:line и доказательствами
  - строка журнала «Successfully registered» текущей инвокации assistant-worker и смоук deploy.py без флагов
affects: [05-08]

key-files:
  created:
    - .planning/phases/05-retro-verifikatsiya-v2-0/V2-09-VERIFICATION.md
    - .planning/phases/05-retro-verifikatsiya-v2-0/05-04-SUMMARY.md

key-decisions:
  - "UXQ-02 passed по критерию плана (хранение 0003, четыре операции, обновление меню по трассе); литеральная фраза «переименуй» и скрытие только фиксированного набора слов записаны как наблюдения для решения владельца"
  - "UXQ-01 gap: при подключении и отключении коннекторов вызова setup_bot_commands нет, диалоговое подключение относится к ONB-02 (Phase 8); запись бэклога 999.x"
  - "UXQ-04 gap: часть 3 (проактивные алерты коннекторов) не доставляется, send_connector_health_alert имеет 0 вызовов в src/, задачи проверки здоровья в планировщике нет; класс D-09 «улучшение / функция не доставляется», запись бэклога 999.x"
  - "Допущение RESEARCH A3 опровергнуто: замер latency есть (test_edge_caching_latency_sub_250ms), но тест не доказывает попадание в кэш; попадание подтверждено трассой"
  - "Исходный текст UXQ взят из chat-app BACKLOG.md (Инициатива 5), а не из v2.0-REQUIREMENTS.md, где нет ни одного UXQ"

patterns-established:
  - "Черновик внешнего агента проверяется построчно по коду; неверные ссылки и несуществующие тесты перечисляются в ограничениях"

requirements-completed: [UXQ-02]

duration: "не измерена (время старта не записано в начале плана)"
completed: 2026-10-18

actuals:
  tokens: 7716      # chars/4 над V2-09-VERIFICATION.md (30864 символа); SUMMARY не учтён
  tasks: 3
  commits: 3        # измерено: git rev-list --count 7b49d32..HEAD (до коммита SUMMARY)
plan_head_before: 7b49d323982f159e9cbd6d161f7411934c29c9c7
plan_head_after: 41eb224a61c5614bb34540c71ab1581b6931a187
---

# Phase 5 Plan 04: V2-09 верификация Summary

## Результат

| Требование | Статус | Основание |
|---|---|---|
| UXQ-02 | passed (трасса+e2e) | Миграция 0003, четыре операции из чата через `handle_user_text` на временной БД (`test_phase3_reachability.py:192`), обновление меню по трассе |
| UXQ-01 | gap | Меню строится из коннекторов персоны и обновляется при старте (журнал: 2 строки «Successfully registered», 10 команд); при подключении и отключении обновления нет |
| UXQ-04 | gap | Части 1 (👍/👎) и 2 (edge cache) passed; часть 3 (проактивные алерты коннекторов) не доставляется |

Итог: 1 из 3 требований passed. Gaps: UXQ-01 (ONB-02, Phase 8), UXQ-04 (часть 3). Gaps классифицированы по D-09 и переданы плану 05-08 как записи бэклога 999.x. Новые требования не созданы. Код не менялся.

## Смоук и рантайм

- `python3 scripts/deploy.py` без флагов: код возврата 0. Автоматическая часть ЗЕЛЁНАЯ (6 проверок ✓, планировщик 11 из 11, getMe ✓). Итог «ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ»: фаза `/help` по D-03 не запускалась.
- Журнал текущей инвокации `assistant-worker` (старт 17:14:12 UTC, активна): две строки «Successfully registered 10 Telegram bot menu commands», ошибок регистрации меню 0. Чаты в документе скрыты.
- Единственный живой внешний вызов — getMe (D-02). Перезапуска не было.

## Допущение A3 (RESEARCH)

Допущение «латентность 250 мс не измерена нигде» (`05-RESEARCH.md:557`) опровергнуто: `tests/test_command_aliases.py:171` замеряет `time.perf_counter()` для `/today` и `/timesheet`. Замер слабый: минимум из 5 вызовов на моках, без проверки попадания в кэш. Вердикт по кэшу — passed с трассой, наблюдение записано.

## Решения, нужные владельцу

1. UXQ-02: принять алиас «называй <новое> как <команда>» как закрытие «переименования» (план так и предписывает) или перевести литеральную фразу «переименуй команду … в …» и расширение списка скрываемых команд в gap-улучшение.
2. Итог смоука: разрешить ли фазу `/help` (`--await-help` / `--confirm-help`), чтобы получить «ЗЕЛЁНЫЙ». Сейчас не запускалась по D-03.
3. Подтвердить запись бэклога 999.x для UXQ-01 (ссылка на ONB-02) и UXQ-04 (мёртвый путь алертов).

## Argon-черновик

Использован черновик agy/Argon (acc2, gemini-4-argon-high) как недоверенный ввод. Вердикты черновика совпали с итоговыми (UXQ-01 gap, UXQ-02 passed, UXQ-04 gap). Доказательная часть содержала ошибки: исправлено 21 пункт. Список — в разделе «Ограничения проверки» файла V2-09-VERIFICATION.md. Главные: неверный источник UXQ, неверный unit журнала (assistant-core вместо assistant-worker), выдуманный состав смоука (9 проверок вместо 6) и итоговая строка, функции `_resolve_cmd_target` и `_build_today_Quick_actions_kb`, которых нет в коде, и неверный список тестов в пробе.

## Отклонения от плана

- Журнал коммита (`.git/gsd-plan-head-before-05-04`) создан после первого коммита, а не до него. Базовый коммит восстановлен по `git log` (родитель первого коммита плана: `7b49d32`, он же HEAD на старте сессии). Число коммитов измерено от этой базы.
- Время старта не записано, поэтому `duration` не измерена.
- Зависание `tests/test_fast_intent_router.py` при отдельном запуске (код 124 после `10 passed`) наблюдалось один раз. В наборе из 6 файлов тот же файл завершился с кодом 0 (`55 passed`). Записано как наблюдение, не как красный гейт.

## Проверки

- `tests/test_command_aliases.py tests/test_command_registry.py tests/test_no_inline_ddl.py`: 30 passed, код 0.
- `tests/test_bot_menu.py tests/test_command_registry.py tests/test_command_aliases.py`: 20 passed, код 0.
- `tests/test_phase3_reachability.py`: 12 passed, код 0.
- `tests/test_tool_calling_flow.py tests/test_prompt_snapshot.py`: 25 passed, код 0.
- Набор Task 3 из 6 файлов: 55 passed, код 0. Отдельный `test_fast_intent_router.py`: см. выше.
- `-k "edge_caching or feedback or connector_health"` в test_command_aliases: 5 passed.
- Гейт `scripts/gate.py` агентом не запускался (запускает оркестратор).

## Known Stubs

Нет. Документ не содержит заглушек в коде; ссылка на бэклог — это запись плана 05-08.

## Threat Flags

Нет. Новых сетевых точек, путей аутентификации и изменений схемы не добавлено.

## Self-Check

Проверено после записи:
- `V2-09-VERIFICATION.md` существует, `status: gaps_found`, строки UXQ-01/UXQ-02/UXQ-04 имеют статусы `gap`/`passed`.
- Коммиты `9997644`, `145f360`, `41eb224` есть в истории `main`.
- Вне `.planning/` изменений нет.
- В документе нет адресов e-mail, идентификаторов чатов и шаблонов токена.
