---
phase: 05-retro-verifikatsiya-v2-0
plan: 08
verified: 2026-10-19T01:10:00Z
status: passed
score: "4/4 критериев успеха; цель фазы достигнута; требований passed 11 из 19, gap 8 (оформлены)"
covered_files:
  - .planning/phases/05-retro-verifikatsiya-v2-0/05-01-PLAN.md
  - .planning/phases/05-retro-verifikatsiya-v2-0/05-01-SUMMARY.md
  - .planning/phases/05-retro-verifikatsiya-v2-0/05-02-PLAN.md
  - .planning/phases/05-retro-verifikatsiya-v2-0/05-02-SUMMARY.md
  - .planning/phases/05-retro-verifikatsiya-v2-0/05-03-PLAN.md
  - .planning/phases/05-retro-verifikatsiya-v2-0/05-03-SUMMARY.md
  - .planning/phases/05-retro-verifikatsiya-v2-0/05-04-PLAN.md
  - .planning/phases/05-retro-verifikatsiya-v2-0/05-04-SUMMARY.md
  - .planning/phases/05-retro-verifikatsiya-v2-0/05-05-PLAN.md
  - .planning/phases/05-retro-verifikatsiya-v2-0/05-05-SUMMARY.md
  - .planning/phases/05-retro-verifikatsiya-v2-0/05-06-PLAN.md
  - .planning/phases/05-retro-verifikatsiya-v2-0/05-06-SUMMARY.md
  - .planning/phases/05-retro-verifikatsiya-v2-0/05-07-PLAN.md
  - .planning/phases/05-retro-verifikatsiya-v2-0/05-07-SUMMARY.md
  - .planning/phases/05-retro-verifikatsiya-v2-0/05-08-PLAN.md
  - .planning/phases/05-retro-verifikatsiya-v2-0/05-08-SUMMARY.md
  - .planning/phases/05-retro-verifikatsiya-v2-0/05-EVIDENCE-DAT03.md
  - .planning/phases/05-retro-verifikatsiya-v2-0/05-SUMMARY.md
covered_digest: "v3:sha256:e738b3fa6a2de2852d9cb573cdd42efb0200f5abc86348bb8fbe472f4c16a9ef"
behavior_unverified: 0
overrides_applied: 0
gaps: []
requirement_gaps: [DAT-02, DAT-03, DAT-04, ISO-02, ISO-04, ACT-03, UXQ-01, UXQ-04]
verifier: gsd-verifier (проверка достижения цели фазы, 2026-10-19)
---

# Фаза 5: Ретро-верификация v2.0 — сводка

Источники: шесть файлов `V2-04..V2-09-VERIFICATION.md` (исходные каталоги chat-app читались только на чтение), протокол `05-EVIDENCE-DAT03.md`. Вердикты V2-файлов перенесены без смягчения. Решения владельца: 2026-10-18 №1–7 (план 05-08) и сообщение 2026-10-19, пункты 1–4 (см. «Решения владельца» ниже).

## Решения владельца, учтённые в документе

- **2026-10-18 №1 (FIN-01):** passed формально (`HARDCODE_BASELINE` пуст в обоих репозиториях); непустой allowlist сканера — наблюдение; FIN-02 не создаётся.
- **2026-10-18 №2 (ACT-01, ACT-02):** формулировки обновлены по HITL-first; ACT-05 не создаётся.
- **2026-10-18 №3 (HIT-01):** passed по примитиву `ConfirmationStore` + `resume_action` + миграция 0002; обход в очистке диалога — HIT-05.
- **2026-10-18 №5 (ISO-02):** gap против текста v2.0, новое требование ISO-05.
- **2026-10-18 №6–7:** все gaps в бэклог Phase 999.3+, не в Phase 6 и не во вставленную фазу; 19 проверяемых требований плюс VER-01.
- **2026-10-19 пункт 1:** исправление gaps вне Phase 5 (D-10); каждый gap — требование или запись бэклога.
- **2026-10-19 пункт 2:** DAT-02 — gap, класс «целостность данных», серьёзность high, требование DAT-06, связано с Phase 999.2.
- **2026-10-19 пункт 3:** ISO-05 охватывает три пути `secretary_dialog.py` и вечерний дайджест `summarizer.py`.
- **2026-10-19 пункт 4:** зависание `tests/test_fast_intent_router.py` — запись бэклога 999.13 (дефект инфраструктуры тестов), новое требование не создаётся.

## Критерии успеха (ROADMAP)

| # | Критерий | Статус | Доказательство |
|---|---|---|---|
| 1 | Для фаз 4–9 v2.0 в папке фазы лежит VERIFICATION.md со ссылками на исходные фазы chat-app | выполнен | `V2-04..V2-09-VERIFICATION.md` существуют, у каждого блок «Источник (только чтение)»; V2-07 — перекрёстная ссылка на `04-VERIFICATION.md` (требований фазы 07 в списке фазы 5 нет, решение №7) |
| 2 | Каждое из 19 требований получило passed или gap с доказательством из рантайма; FIN-01 подтверждено формально | выполнен | таблица «Сводная таблица 20 требований»: 19 строк passed/gap, у каждой точка входа file:line; `HARDCODE_BASELINE = {}` в `tests/hardcode_baseline.py` обоих репозиториев |
| 3 | `test_concurrent_write_two_processes` (DAT-03) прогнан повторно, результат записан честно | выполнен | `05-EVIDENCE-DAT03.md`: протокол 60 последовательных прогонов (свободная система 1 из 30 сбой, нагрузка 0 из 30, полных прогонов K=1, J=0); вердикт gap, оформлен как DAT-05 |
| 4 | Каждый gap стал требованием или записью бэклога; гейт ЗЕЛЁНЫЙ; боевая БД не затронута; рестарт не нужен | выполнен | реестр ниже: 10 gaps оформлены (требования HIT-05, ISO-05, DAT-05..08, HIT-06; бэклог 999.10–999.12); 999.13 без gap; гейт ЗЕЛЁНЫЙ на повторе (раздел «Результат гейта»); код не менялся, `assistant-worker` active, рестарт не выполнялся |

## Сводная таблица 20 требований

| Требование | Статус | Точка входа в рантайме (file:line) | Тест или команда проверки | Метка | Файл V2 |
|---|---|---|---|---|---|
| VER-01 | passed | документальное требование, файлов рантайма нет: `V2-04..V2-09-VERIFICATION.md`, сводка и реестр в этом файле | шесть файлов V2 существуют; 20 строк сводки; все gaps оформлены; гейт (раздел «Результат гейта») | документ | все V2 |
| DAT-02 | gap | `src/main.py:646-648` (`Database(config.SQLITE_DB_PATH)`), `src/config.py:16-24`; chat-app `backend/app/core/config.py:20-22`, `backend/app/db.py:13` | сравнение путей журнала воркера и ответа владельца: демон `/opt/assistant-core/data/assistant.db`, chat-app `/opt/chat-app/backend/data/assistant.db` (расхождение) | трасса | V2-04 |
| DAT-03 | gap | `/opt/assistant-shared/assistant_shared/db/connection.py:42-45` (WAL, `busy_timeout`), `:61-64`; `src/storage/db.py:48` | `05-EVIDENCE-DAT03.md`: 60 последовательных прогонов, сбой `database is locked` 1 из 30 (свободная система), 0 из 30 (нагрузка), полных прогонов K=1, J=0 | e2e | V2-04 |
| DAT-04 | gap | `backend/app/api/v1/security.py:42` (`asyncio.to_thread(audit_path, ...)`), `/opt/assistant-shared/assistant_shared/security/auditor.py:156` (`rglob`) | полный прогон `backend/tests` под `strace -f -e trace=file`: 278 passed, 1 failed; 9 строк stat/lstat к `/opt/assistant-core/data` и `assistant.db`; положительный контроль: 1 попадание | e2e | V2-04 |
| SEC-01 | passed | chat-app `backend/app/api/v1/security.py:10, 42, 86`; assistant-core `scripts/security_shield.py:19, 75`; `.githooks/pre-commit:19` | `tests/test_nda_script_parity.py`, `tests/test_security_shield_cli.py`: 16 passed; chat-app `test_security_shared.py`, `test_nda_equivalence.py`, `test_shield_parity.py`: 47 passed | трасса+e2e | V2-04 |
| SEC-02 | passed | логика `scripts/security_shield.py:75` (`audit_repository`); делегаторы chat-app `scripts/security_shield.py:46`, assistant-shared `scripts/security_shield.py:49` | assistant-core: 16 passed; chat-app `test_shield_delegator.py`, `test_pre_commit_hook.py`: 15 passed; assistant-shared `test_security_shield_delegator.py`: 14 passed | трасса+e2e | V2-04 |
| SEC-03 | passed | `.githooks/pre-commit:19`; установка `scripts/install_hooks.sh:40`; проверка `scripts/gate.py:780` (`hook_installed_check`) | проба во временном репозитории: чистый коммит rc 0, коммит с синтетическим секретом rc 1 | e2e | V2-04 |
| HIT-01 | passed | `src/main.py:647` (`db.init_db()`, миграция 0002); `src/notifier/bot_handler.py:2078, 2401` (`resume_action`); `/opt/assistant-shared/assistant_shared/hitl/engine.py:28-62` | `tests/test_hitl_safety_guardrails.py`, `test_bot_hitl_parity.py`, `test_hitl_telegram_cards.py`: 18 passed (3 прогона из 3); assistant-shared: 211 passed | трасса+e2e | V2-05 |
| ISO-01 | passed | `src/main.py:687-699`; `src/brain/key_rotator.py:190-213` (пул по `persona_id`); присваивания `config.GEMINI_API_KEY` нет | `tests/test_key_rotator.py`: 9 passed (в т.ч. `test_key_rotator_persona_isolation`) | трасса | V2-06 |
| ISO-02 | gap | `src/security/airgap.py:132-157` (тело, snippet, вложения маскируются); `src/brain/secretary_dialog.py:169-176, 191-200, 773-806`; `src/brain/summarizer.py:343-347, 399` | `tests/test_airgap_trap.py`, `tests/test_nda_script_parity.py`: 12 passed (тело, snippet, вложения); метаданные не проверяются | трасса+e2e | V2-06 |
| ISO-03 | passed | `src/composition.py:37, 57, 78, 111, 144` (`MissingScopeError`); `src/main.py:673` (вызов вне `try`) | `tests/test_phase4_reachability.py`, `tests/test_ports_conformance.py`: 41 passed | трасса | V2-06 |
| ISO-04 | gap | `src/persona/current.py:17-40`; `/opt/assistant-shared/assistant_shared/hitl/store.py:52` (запись подтверждения) | `tests/test_concurrency_isolation.py::test_concurrent_confirmations_isolation`: `database is locked` в 2 из 9 прогонов в связке, 0 из 20 при изолированном прогоне | трасса+e2e | V2-06 |
| FIN-01 | passed | `tests/hardcode_baseline.py:14` (`HARDCODE_BASELINE = {}`) в обоих репозиториях | `tests/test_hardcode_scanner.py`: 3 passed (assistant-core и chat-app) | трасса | V2-06 |
| ACT-01 | passed | `src/notifier/bot_handler.py:1311`; `src/brain/secretary_dialog.py:595, 704, 816-821` (`_build_action_proposal`); `src/notifier/bot_handler.py:2401` (`resume_action`) | `tests/test_tool_calling_e2e.py` (3), `test_secretary_tools.py` (7), `test_hitl_telegram_cards.py` (9): в составе прогона 44 passed | трасса+e2e | V2-08 |
| ACT-02 | passed | `src/brain/secretary_dialog.py:702, 733`; `config/prompts/secretary_default.jinja2:27-31` | `tests/test_prompt_snapshot.py` (19), `test_secretary_tools.py` (7): в составе прогона 44 passed | трасса | V2-08 |
| ACT-03 | gap | HITL-путь `src/notifier/bot_handler.py:403-409, 2358, 2401`; обход `src/notifier/bot_handler.py:2499-2551` (`act:cal:retry` → `src/calendar/client.py:185` без `resume_action`) | наборы HITL и tool calling: 44 passed; обход тестами не покрыт | трасса+e2e | V2-08 |
| ACT-04 | passed | `src/notifier/bot_handler.py:1471`; `src/brain/intent_router.py:35, 121` | `tests/test_tool_calling_flow.py`: 6 passed; `tests/test_fast_intent_router.py`: 10 passed, процесс не завершается (см. Наблюдения 6) | трасса+e2e | V2-08 |
| UXQ-01 | gap | `src/notifier/bot_handler.py:911-939` (`setup_bot_commands`); `src/notifier/commands.py:206-248`; старт `src/main.py:700, 932` | `tests/test_bot_menu.py`, `tests/test_command_registry.py`: 20 passed; журнал старта: 2 «Successfully registered», 10 команд; разрыв: вызова при подключении и отключении коннекторов нет | трасса+e2e | V2-09 |
| UXQ-02 | passed | `src/notifier/bot_handler.py:432, 1354-1413`; `src/storage/db.py:2900, 2930, 2945`; `0003_bot_commands_and_feedback.sql:2-13` | `tests/test_phase3_reachability.py` (12), `tests/test_command_aliases.py`, `tests/test_no_inline_ddl.py`: 30 passed | трасса+e2e | V2-09 |
| UXQ-04 | gap | части 1–2 (passed): `src/notifier/bot_handler.py:423, 2698-2738`; `src/storage/db.py:2955`; часть 3 (gap): `send_connector_health_alert` `src/notifier/bot_handler.py:2660-2690`, вызовов в `src/` нет | `tests/test_command_aliases.py` (кэш, latency на моках), `tests/test_phase3_reachability.py`: 5 passed | трасса+e2e | V2-09 |

## Реестр gaps

| Gap | Требование-источник | Класс по D-09 | Новое требование или запись бэклога | Привязка Phase 999.N | Серьёзность |
|---|---|---|---|---|---|
| Очистка диалога мимо `resume_action` (`cb_dlg_confirm_clear`, fail-open; обход тестами закреплён в `tests/test_bot_hitl_parity.py:277-314`) | HIT-01 (кандидат HIT-05) | HITL | новое требование HIT-05 | Phase 999.3 | high |
| Метаданные NDA-почты (отправитель, тема, дата) уходят во внешний LLM на трёх путях диалога и в вечернем дайджесте | ISO-02 | NDA, безопасность | новое требование ISO-05 (связано с NDAM-01) | Phase 999.4 | high |
| Конкурентная запись двух процессов: сбои `database is locked` | DAT-03 | целостность данных | новое требование DAT-05 | Phase 999.5 | high |
| Демон и chat-app открывают разные файлы БД | DAT-02 | целостность данных | новое требование DAT-06 (связано с Phase 999.2, решение владельца 2026-10-19) | Phase 999.6 | high |
| Тесты chat-app обращаются к путям `/opt/assistant-core` (`data/`, `assistant.db`) через фикстуру персоны и обход аудита | DAT-04 (а) | целостность данных | новое требование DAT-07 | Phase 999.7 | critical |
| Нестабильная параллельная запись подтверждений двух персон (`database is locked`) | ISO-04 | целостность данных | новое требование DAT-08 | Phase 999.8 | средняя |
| Повтор синхронизации календаря (`act:cal:retry`) выполняет внешнюю запись мимо `resume_action` | ACT-03 | HITL и целостность данных | новое требование HIT-06 (серьёзность назначена по классу HITL) | Phase 999.9 | high |
| Меню команд не обновляется при подключении и отключении коннекторов | UXQ-01 | улучшение (функция не доставляется) | запись бэклога, нет нового требования (закрывается ONB-02, Phase 8) | Phase 999.10 | не задана (улучшение) |
| Проактивные алерты коннекторов не вызываются (`send_connector_health_alert`, 0 вызовов в `src/`) | UXQ-04 (часть 3) | улучшение (функция не доставляется) | запись бэклога, нет нового требования | Phase 999.11 | не задана (улучшение) |
| Тесты chat-app не герметичны: обращения к `.venv`, `config/`, `scripts/`, `src/` и корню assistant-core (701 путь) | DAT-04 (б) | улучшение (герметичность тестов) | запись бэклога, нет нового требования | Phase 999.12 | low |

**Бэклог без gap (решение владельца 2026-10-19, пункт 4):**

| Запись | Источник | Класс | Привязка |
|---|---|---|---|
| Зависание процесса `tests/test_fast_intent_router.py` (3 теста создают `EmailBotHandler` без `bot`/`notifier`, остаются потоки aiosqlite; код 124 при 10 passed) | наблюдения V2-08 п. 5, V2-09 п. 8, 05-01 | дефект инфраструктуры тестов (целостность гейта), не требование | Phase 999.13 |

## Наблюдения (не gaps)

1. **FIN-01, непустой allowlist сканера.** `ALLOWLIST_PREFIXES` и `ALLOWLIST_SUFFIXES` в `tests/test_hardcode_scanner.py:47-48` обоих репозиториев пропускают `config/`, `tests/`, `docs/`, `.planning/` и `.md`. Буква v2.0 про «пустой allowlist» не выполнена; формальный критерий решения №1 выполнен, FIN-02 не создаётся.
2. **SEC-02, делегаторы.** Обёртки chat-app и assistant-shared зависят от пути `/opt/assistant-core`; известный долг DEBT-03 (IN-05). Оговорка, не gap.
3. **HIT-01, декоратор.** `@requires_confirmation` в коде не реализован; вердикт опирается на решение №3. Аннотация в REQUIREMENTS.md сохранена (см. открытые вопросы).
4. **ISO-03, доказательство по коду.** Отсутствие переменных `GUAP_*`/`LMS_*` в `.env` и окружении процесса не проверялось (`.env` не читался); для части chat-app теста нет.
5. **UXQ-04, кэш.** RESEARCH A3 опровергнуто: замер latency есть (`test_edge_caching_latency_sub_250ms`), попадание в кэш доказано трассой, но не тестом.
6. **Зависание `test_fast_intent_router.py`.** Отдельный запуск не завершается (код 124); в полном наборе из шести файлов код 0 (55 passed). Записано в бэклог 999.13, не gap.
7. **DAT-03 вне протокола D-08.** В полном прогоне под strace упал `test_concurrent_write_two_processes` (1 из 1); счёт ведёт `05-EVIDENCE-DAT03.md`.
8. **Посторонний файл `/opt/assistant-core/assistant.db`.** Только метаданные (544768 байт, root, 8 октября); не открывался и не хешировался; происхождение не исследовано (RESEARCH A8).
9. **Мёртвый путь алертов и кнопка проверки.** Callback `chk:<название службы>` с кириллицей может превысить 64 байта Telegram; предположение, вызова нет.

## Открытые вопросы владельцу

1. **UXQ-02, переименование как алиас.** Принят ли алиас «называй <новое> как <команда>» как закрытие пункта «переименование» (план 05-08 предписывает так; в статусе passed). Нужен ответ владельца через опрос.
2. **ISO-03, нет теста chat-app.** Оставить passed по коду или перевести в gap (текст v2.0 требует «проверяемый тест»).
3. **HIT-01, аннотация.** Текст требования упоминает `@requires_confirmation`; аннотация «засчитано по решению №3» добавлена. Владелец вправе убрать или переписать текст.
4. **04-VERIFICATION.md (v3, фаза 4).** Во frontmatter `passed`, в теле `human_needed`. Какой статус считать итоговым (расхождение записано, документ не переписан).
5. **Смоук `/help` не выполнен** в этой фазе.
6. **Меню «mail» всегда активно** (наблюдение UXQ-02): видимость не зависит от подключения почты.
7. **DAT-04 (а), stat-only обращение.** По правилу плана stat/lstat считается обращением; владелец может решить иначе (снизить до «улучшения»).

## Результат гейта

Гейт `python3 scripts/gate.py` запущен из `/opt/assistant-core` в фоне, без параллельных pytest и strace. Вывод вне репозитория: `/var/tmp/gsd-phase05-probes/gate-1.txt` и `gate-2.txt`.

- **Попытка 1:** `ИТОГ: КРАСНЫЙ`, rc 1. Единственная красная строка: «боевая assistant.db не изменена» (хеш изменился во время pytest assistant-core; `assistant-worker` active; mtime БД 2026-10-19T00:30:35+00:00, то есть внутри окна измерения). Остальные строки ✓: pytest assistant-core 1182 тестов, import-linter, security_shield, дрейф персон (2), pre-commit hook; assistant-shared pytest 211, security_shield, pre-commit hook.
- **Попытка 2** (повтор ровно один раз через 30 секунд, по протоколу плана 05-08 и решению 2026-10-09): `ИТОГ: ЗЕЛЁНЫЙ`, rc 0. Все 11 строк ✓; SHA-256 боевой БД до и после совпали (`a90d8fb6c11c`, проверил сам гейт, БД планом не открывалась).

Итог: зелёный на повторе; красная попытка 1 записана, не скрыта. Код не менялся, рестарт не нужен.

## Ограничения проверки

1. Боевая БД `/opt/assistant-core/data/assistant.db` и файл `/opt/assistant-core/assistant.db` не открывались (проверяет гейт, read-only по mode=ro). `.env` не читался ни в одном из файлов.
2. `chat-app.service` неактивен; проверки DAT-04 и SEC-03 выполнены на уровне git, ОС и тестов, не живого рантайма chat-app.
3. Живых вызовов LLM и внешних API не было, кроме read-only `getMe` внутри `scripts/deploy.py` (D-02). `assistant-worker` не перезапускался.
4. Новых тестов и изменений кода в репозиториях нет (D-10). chat-app и assistant-shared не менялись.
5. agy не использовался (STATE A-6). Черновики Argon (acc2) использовались как недоверенный ввод и перепроверены по коду; счётчики исправлений по SUMMARY: 05-01 — 10, 05-02 — 36, 05-03 — 24, 05-04 — 21.
6. strace фиксирует только файловые вызовы; обращения без файловых системных вызовов трассой не видны.

## Проверка достижения цели фазы (gsd-verifier)

**Дата:** 2026-10-19. **Вердикт по цели фазы: passed.** Цель фазы: каждое требование v2.0, перенесённое без проверки, получает честный статус по факту, каждый разрыв становится явной записью. Требования-gaps, корректно оформленные и разнесённые по бэклогу, не являются gaps фазы.

### Проверка по критериям ROADMAP

| # | Критерий | Результат | Что проверено независимо |
|---|---|---|---|
| 1 | VERIFICATION.md для фаз 4–9 v2.0 со ссылками на источник | VERIFIED | шесть файлов `V2-04..V2-09-VERIFICATION.md` существуют; во frontmatter у каждого `v2_source` с путём в `/opt/chat-app/.planning/milestones/v2.0-phases/…`, есть блок «Источник» |
| 2 | 19 требований: passed или gap с доказательством из рантайма; FIN-01 формально | VERIFIED | таблица сводки: 11 passed + 8 gap = 19, у каждой строки file:line; `HARDCODE_BASELINE: dict[str, dict[str, int]] = {}` в `tests/hardcode_baseline.py:14` |
| 3 | DAT-03 прогнан повторно, результат честный | VERIFIED | `05-EVIDENCE-DAT03.md`: 1 из 30 (свободная система, free-27 `database is locked`), 0 из 30 под нагрузкой, вердикт gap; сбой не скрыт; каталог проб `/var/tmp/gsd-phase05-probes/dat03` существует |
| 4 | Каждый gap — требование или бэклог; гейт ЗЕЛЁНЫЙ; БД не тронута; рестарт не нужен | VERIFIED | см. ниже |

### Покрытие ID требований

Объединение `requirements` из PLAN 05-01..05-08: VER-01, ACT-01..04, ISO-01..04, FIN-01, HIT-01, UXQ-01, UXQ-02, UXQ-04, DAT-03, SEC-01..03, DAT-04, DAT-02 = 20 ID. Совпадает со строкой Requirements фазы 5 в ROADMAP.md (20 ID). Все 20 есть в таблице сводки; осиротевших ID нет.

### Сверка статусов REQUIREMENTS.md и 05-VERIFICATION.md

- Passed (11): SEC-01, SEC-02, SEC-03, HIT-01, ISO-01, ISO-03, FIN-01, ACT-01, ACT-02, ACT-04, UXQ-02 — в REQUIREMENTS.md `[x]` и «Complete». VER-01 `[x]`, «Complete».
- Gap (8): DAT-02, DAT-03, DAT-04, ISO-02, ISO-04, ACT-03, UXQ-01, UXQ-04 — `[ ]`, в таблице трассировки «Gap → …» с привязкой.
- UXQ-02, отмеченное Complete ещё планом 05-04 (коммит `9fd2bac`): совпадает с итоговым вердиктом passed, расхождения нет.
- Новые требования HIT-05, ISO-05, DAT-05..08, HIT-06 присутствуют (`[ ]`, «Pending», Phase 999.3–999.9); счёт покрытия 51 согласуется с 44 + 7.

### Соответствие gap → требование/бэклог

Все 10 строк реестра имеют цель: HIT-05 → 999.3, ISO-05 → 999.4, DAT-05 → 999.5, DAT-06 → 999.6, DAT-07 → 999.7, DAT-08 → 999.8, HIT-06 → 999.9, UXQ-01 → 999.10, UXQ-04 (часть 3) → 999.11, DAT-04 (б) → 999.12; запись 999.13 (зависание `test_fast_intent_router.py`) без gap, по решению владельца. Все разделы 999.3–999.13 найдены в ROADMAP.md с Source phase, Class и Follow-ups.

### Выборочная проверка file:line по коду (не по SUMMARY)

| Утверждение | Результат |
|---|---|
| `src/main.py:646-648` `Database(config.SQLITE_DB_PATH)` + `init_db()` (DAT-02, HIT-01); `:673` `default_lms_client()` до `try`; `:700, 932` `setup_bot_commands()` | подтверждено |
| `bot_handler.py:2499-2551` `act:cal:retry` → `create_event_from_dict` (`src/calendar/client.py:185`) без `resume_action` (`resume_action` только на `:2078, 2274, 2401`) — gap ACT-03 | подтверждено |
| `bot_handler.py:1932` `cb_dlg_confirm_clear`: `create_confirmation` + немедленный `confirm_action`, `except Exception` лишь логирует, затем `clear_dialog_history` выполняется (fail-open) — gap HIT-05; тест `test_bot_hitl_parity.py:277` закрепляет обход | подтверждено |
| `airgap.py:132-157` маскирует body/snippet/attachments, но не sender/subject/date; `secretary_dialog.py:169-176, 191-200, 773-806` и `summarizer.py:343-347` подставляют отправителя, тему, дату — gap ISO-02 | подтверждено |
| `send_connector_health_alert` определён в `bot_handler.py:2660`, вызовов в `src/` нет — gap UXQ-04 (часть 3) | подтверждено |
| `bot_handler.py:911-939` `setup_bot_commands` вызывается только на старте (`main.py:700, 932`) — gap UXQ-01 | подтверждено |
| `assistant_shared/db/connection.py:42-45, 61-64` WAL и `busy_timeout = 30000`; `hitl/store.py:52` запись в `pending_confirmations` | подтверждено |
| `key_rotator.py:190-213` пул ротаторов по `persona_id` (ISO-01); `composition.py:37, 57, 78, 111, 144` `MissingScopeError` (ISO-03); `scripts/gate.py:780` `hook_installed_check` | подтверждено |

Расхождений между утверждениями V2-файлов (включая выводы, выросшие из черновиков Argon) и кодом не найдено.

### Гейт и неизменность кода

- `gate-1.txt`: КРАСНЫЙ (rc 1), единственная красная строка «боевая assistant.db не изменена» (assistant-worker active, БД изменена воркером в окне измерения); остальные 10 строк ✓. `gate-2.txt`: ЗЕЛЁНЫЙ (rc 0), все 11 строк ✓, SHA-256 до/после совпали (`a90d8fb6c11c`). Красная попытка записана в документе, не скрыта; повтор один раз соответствует протоколу. Сам верификатор гейт не запускал (по заданию оркестратора), опираясь на сохранённые выводы.
- `git diff --name-only 252970d..HEAD` вне `.planning/`: 0 файлов. В рабочем дереве вне `.planning` изменений нет. Код и тесты не менялись, рестарт не требовался (D-10).
- Боевая БД и `.env` верификатором не открывались.

### Замечания (не блокируют)

1. Открытые вопросы владельцу 1–7 (раздел выше) остаются без ответа: UXQ-02 (алиас вместо переименования), ISO-03 (нет теста chat-app), HIT-01 (аннотация `@requires_confirmation`), статус `04-VERIFICATION.md` v3. Это решения о формулировках, а не недостающие доказательства; текущие вердикты честно помечены.
2. Статус `passed` относится к цели фазы (честные вердикты и оформление gaps). Продукт при этом содержит 8 открытых требований-gaps, из них высокой серьёзности HIT-05, ISO-05, DAT-05, DAT-06, HIT-06 и критической DAT-07; их исправление запланировано вне Phase 5 (бэклог 999.3–999.9).
3. Нерешённый риск среды: гейт зависит от того, что воркер не пишет в БД во время pytest (гейт-1 красный из-за этого); защита тестов — `tests/live_db_guard.py`.
