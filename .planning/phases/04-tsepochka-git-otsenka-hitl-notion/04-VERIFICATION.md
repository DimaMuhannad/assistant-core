---
phase: 04-tsepochka-git-otsenka-hitl-notion
verified: 2026-10-18T13:02:18Z
status: human_needed
score: "5/5 критериев (4 подтверждены полностью, критерий 1 частично: отклонение принято владельцем, override)"
covered_files:
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-01-PLAN.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-01-SUMMARY.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-02-PLAN.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-02-SUMMARY.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-03-PLAN.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-03-SUMMARY.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-04-PLAN.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-04-SUMMARY.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-05-PLAN.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-05-SUMMARY.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-06-PLAN.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-06-SUMMARY.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-07-PLAN.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-07-SUMMARY.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-08-PLAN.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-08-SUMMARY.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-09-PLAN.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-09-SUMMARY.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-10-PLAN.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-10-SUMMARY.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-11-PLAN.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-11-SUMMARY.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-12-PLAN.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-12-SUMMARY.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-13-PLAN.md
  - .planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-13-SUMMARY.md
  - config/persona.yaml
  - docs/GIT_NOTION_SETUP.md
  - src/brain/git_evaluator.py
  - src/composition.py
  - src/connectors/git/provider.py
  - src/connectors/notion/client.py
  - src/core/exceptions.py
  - src/main.py
  - src/notifier/bot_handler.py
  - src/notifier/commands.py
  - src/security/airgap.py
  - tests/test_git_airgap_trap.py
  - tests/test_git_bot_commands.py
  - tests/test_git_chain.py
  - tests/test_git_chain_airgap.py
  - tests/test_git_connector.py
  - tests/test_notion_git_hitl.py
  - tests/test_phase4_chain_e2e.py
  - tests/test_phase4_git_read_failure.py
  - tests/test_phase4_hitl_security_fixes.py
  - tests/test_phase4_reachability.py
covered_digest: "v2:sha256:eccc64abd95420374452b5844bdf6f2b5558d93fd64b77a8ea559100f5fc77df"
behavior_unverified: 0
overrides_applied: 1
overrides:
  - must_have: "Репозитории подключаются только данными рабочего пространства (git: host, account, ssh_alias, remote): подключение через remote/ssh_alias персоны"
    reason: "fetch_remote работает через remote, настроенный в локальном клоне (git fetch --all --prune по .git/config); remote и ssh_alias персоны используются для фильтра допуска и статуса. Критерий 1 остаётся «частично», код не менялся."
    accepted_by: "владелец"
    accepted_at: "2026-10-15T00:00:00Z"
re_verification:
  previous_status: passed
  previous_score: "4/5 must-haves verified, 1 partial"
  gaps_closed: []
  gaps_remaining: []
  regressions: []
gaps: []
human_verification:
  - test: "Решить по открытым пунктам Air-Gap из ревью Argon (№3, №4, №5) в 04-REVIEW-ARGON / REVIEW-ARGON-20261018-1216.md"
    expected: "Решение владельца: ограничить fetch/log только remote из персоны, разворачивать симлинки и путь «/» в _norm_path, вызывать git_chain_workspaces на границе SshGitProvider; либо явно принять риск. До решения пункты числятся известными рисками."
    why_human: "Решение владельца о границах Air-Gap (связано с решением 2026-10-15 о fetch по remote локального клона); автоматикой не закрывается."
  - test: "Решить о рестарте assistant-worker для выкатки правок после последнего запуска сервиса"
    expected: "После рестарта по scripts/deploy.py --backup --restart смоук ЗЕЛЁНЫЙ, в живом ответе /git нет регрессий"
    why_human: "Рестарт только по явному разрешению владельца. Unit запущен 2026-10-15 20:52 UTC; коммиты 5765e53, 6341540, cf77525 (2026-10-16) и 9579db4 (2026-10-18) в запущенный процесс не вошли."
  - test: "Живая запись в Notion после подтверждения карточки на боевых ID"
    expected: "Страница активности создана ровно один раз; повторное нажатие не создаёт дубль"
    why_human: "Реальная запись в живую Notion не проверялась (тесты работают с подменой клиента); проверка меняет внешнее состояние."
---

# Phase 4: Цепочка Git → оценка → HITL → Notion. Отчёт верификации

**Цель фазы:** Владелец получает по-русски оценку хода проектов по git-репозиториям своих рабочих пространств и вносит её в Notion только после подтверждения в Telegram. Цепочка достижима из планировщика и из команды бота, а пространства `restricted_nda` исключены из неё полностью.
**Проверено:** 2026-10-18
**Статус:** human_needed (код и тесты подтверждают цель; остаются решения владельца: открытые пункты Air-Gap, рестарт для выкатки последних правок, живая запись в Notion)
**Повторная верификация:** да, после ревизии 2026-10-15 и quick-задач 261015-kuf, 261016-p4r, 261016-t4l, 261018-arg. Предыдущий отчёт (2026-10-12, доработан 2026-10-15) был устаревшим: исходники изменились после его написания.

Проверка выполнена от цели к коду: утверждения SUMMARY не принимались как доказательство, ключевые узлы прочитаны в исходниках, тесты и гейт запущены заново. Боевая БД и `.env` не открывались; `src/` и `tests/` не менялись.

---

## 1. Достижение цели

### Наблюдаемые истины (критерии успеха ROADMAP)

| # | Истина | Статус | Доказательства (по коду) |
|---|--------|--------|--------------------------|
| 1 | Репозитории подключаются данными рабочего пространства (`git: host, account, ssh_alias, remote`) через `default_git_source_provider` и `SshGitProvider` (только чтение, scope `git.read`). Пространства без remote или каталога пропускаются, статус виден в рантайме (GIT-01, GIT-02). | ◐ PARTIAL (override: отклонение принято владельцем 2026-10-15) | Реализовано: `default_git_source_provider` (`src/composition.py:95`) проверяет привязку `git_source` и scopes, `SshGitProvider.required_scopes = ("git.read",)` (`src/connectors/git/provider.py:43`); `evaluate()` даёт статусы `NO_REMOTE`, `NO_DIR`, `NOT_GIT`, `FETCH_FAILED`, `READ_FAILED` (`src/brain/git_evaluator.py:334-440`). Не реализовано по формулировке критерия: `fetch_remote` запускает `git fetch --all --prune` по локальному `.git/config` (`provider.py:98`), `remote`/`ssh_alias`/`host`/`account` персоны для самого подключения не используются, они служат фильтром допуска и условием «есть что опрашивать». Решение владельца 2026-10-15: так и оставить, критерий «частично», код не менять. |
| 2 | `GitProgressEvaluator` создаётся в планировщике `src/main.py` (периодичность — данные персоны) и по команде бота; владелец получает по-русски оценку для public- и internal-репозиториев (GIT-03). | ✓ VERIFIED | Рантайм-путь: `main()` создаёт `default_git_evaluator(db)` (`src/main.py:675`) до `EmailBotHandler(..., git_evaluator=git_evaluator)` (`:697`); задача `git_progress_job` добавляется безусловно с расписанием из `git_source_settings()` (`:902-911`, персона: `sun 20:00`, порог застоя 7 дней); команда `/git` зарегистрирована (`bot_handler.py:426`, `commands.py:173`) и вызывает `evaluator.evaluate()` (`bot_handler.py:2166`). Фабрика собирает `GitProgressEvaluator` (`composition.py:149-169`). Текст сводки и статусы по-русски, запасной шаблон при отказе LLM. Тесты: `tests/test_phase4_reachability.py` (13 тестов, включая AST-проверки порядка и регистрации задачи). |
| 3 | `restricted_nda` и неопределённый допуск исключены из цепочки (fail-closed): нет обращений к git, LLM, Notion; нет оценки и карточки; в ответе одна строка «NDA: исключено из оценки» (GIT-04). | ✓ VERIFIED (с известными рисками, см. раздел 5) | `git_chain_workspaces(persona)` вызывается первой операцией `evaluate()` (`git_evaluator.py:344`) и повторно в обработчике записи (`:687`); `persona is None` или любая ошибка → `unresolved=True`, ничего не допускается (`src/security/airgap.py:367-411`); допущенные пространства, пересекающиеся с исключёнными по `path`/`remote`/`ssh_alias`, тоже исключаются; защита в глубину: `fetch_remote` и `get_commits_since` бросают `AirGapViolationError` для недопущенного `clearance` (`provider.py:85,137`); коммиты проходят `sanitize_git_commits_for_llm` до промпта (`git_evaluator.py:450`). Ловушки `TrapGitProvider`/`TrapLlm`/`TrapNotion` на рантайм-путях `handle_cmd_git` и `run_git_progress_cycle` — `tests/test_git_chain_airgap.py`. |
| 4 | `notion_project_sync` зарегистрирован в рантайме, связь «пространство → проект Notion» из персоны. Запись только после подтверждения HITL в Telegram: отклонение ничего не пишет, повтор без дублей, сбой SSH/Notion не роняет демон и виден в статусе (NTN-01, NTN-02). | ✓ VERIFIED (живая запись в Notion не проверялась, см. раздел 6) | `register_action_handler(NOTION_ACTION_TYPE, self._handle_notion_sync)` в `GitProgressEvaluator.__init__` (`git_evaluator.py:209`); `notion_project` берётся из персоны (4 валидных ID в `config/persona.yaml`, строки 23, 32, 42, 54), валидность проверяется `is_valid_notion_id`. Единственный вызов записи — `_handle_notion_sync` после `resume_action` (`bot_handler.py:2242+`); перед записью повторная проверка допуска, валидация ID, проверка готовности клиента и поиск существующей страницы (`find_project_activity`) для дедупликации (`git_evaluator.py:681-756`). Карточка идемпотентна по ключу «пространство|дата» (`propose_card`, `:522`, под `asyncio.Lock`). При сбое: `NotionSyncError`/`LookupError`/любое исключение → `reopen_action`, ответ «Не записано в Notion, повторите» (`bot_handler.py:2275-2293`). `cb_ntn_reject` не трогает подтверждённую запись (`:2319`). Авторизация fail-closed (quick 261015-kuf). Тесты: `test_notion_git_hitl.py`, `test_git_bot_commands.py`, `test_phase4_hitl_security_fixes.py` (в т.ч. возврат в pending при сбое Notion, ноль обращений к Notion до подтверждения), `test_phase4_chain_e2e.py`. |
| 5 | VERIFICATION.md доказывает достижимость из рантайма: задача планировщика видна при старте, команда бота запускает оценку, цепочка «команда → оценка → HITL-карточка → запись» проходит на временной БД с подменёнными SSH и Notion; рестарт только с разрешения владельца, смоук OPS-01 пройден. | ✓ VERIFIED | Достижимость по коду — см. строки 2 и 4 (главный путь: `main.py` → `default_git_evaluator` → `EmailBotHandler` → `/git` → `ntn:req` → `ntn:conf` → `_handle_notion_sync` → `NotionAsyncClient.log_project_activity`; планировщик: `run_git_progress_cycle` → `evaluate` → `propose_cards` → карточка в Telegram). Сквозные тесты `tests/test_phase4_chain_e2e.py` на временной БД. Рестарт 2026-10-12 с разрешением владельца и бэкапом, смоук ЗЕЛЁНЫЙ, 11 из 11 задач планировщика, включая `git_progress_job` (`04-SMOKE-REPORT.md`); живые ответы `/help` и `/git` подтверждены владельцем. Оговорка: запущенный процесс старше последних четырёх коммитов, см. раздел 6. |

**Оценка:** критерии 2–5 подтверждены полностью, критерий 1 выполнен частично по зафиксированному решению владельца. Непроверенных поведенческих истин (`behavior_unverified`): 0 — поведенческие инварианты критерия 4 (возврат карточки в pending, ноль записей до подтверждения, confirm/reject) покрыты тестами, часть из них проверена мутацией (quick 261016-t4l: без `reopen_action` падает `test_ntn_confirm_notion_failure_returns_card_to_pending`).

---

## 2. Охват требований (REQUIREMENTS.md)

Все шесть ID фазы заявлены в `requirements:` планов (04-01, 04-12 и 04-13 заявляют все шесть) и сопоставлены с REQUIREMENTS.md. Осиротевших требований нет: другие ID за Phase 4 в REQUIREMENTS.md не закреплены.

| Требование | Планы | Статус | Доказательства |
|------------|-------|--------|----------------|
| GIT-01 | 04-01, 04-05, 04-08, 04-12, 04-13 | ◐ PARTIAL (override) | Порт и `SshGitProvider` (read-only, scope `git.read`) вызываются из рантайма через `default_git_source_provider`. Оговорка: подключение по `remote`/`ssh_alias` не реализовано, `fetch_remote` идёт через локальный клон, решение владельца 2026-10-15. Отметка `[x]` в REQUIREMENTS.md относится к вызову провайдера из рантайма. |
| GIT-02 | 04-01, 04-03, 04-05, 04-06, 04-10, 04-12, 04-13 | ✓ SATISFIED | Статусы пропуска `NO_REMOTE`/`NO_DIR`/`NOT_GIT`, сбои `FETCH_FAILED`/`READ_FAILED` в `evaluate()`; видны в ответе `/git` (`format_run_text`). Сбой чтения коммитов больше не выдаётся за «Застой» (quick 261015-kuf). |
| GIT-03 | 04-01, 04-03, 04-06, 04-08, 04-09, 04-11, 04-12, 04-13 | ✓ SATISFIED | `GitProgressEvaluator`, `git_progress_job`, `/git`, русский текст и запасной шаблон, порог застоя из персоны. |
| GIT-04 | 04-01, 04-05, 04-10, 04-12, 04-13 | ✓ SATISFIED (риски в разделе 5) | Шлюз `git_chain_workspaces` первой операцией, защита в глубину в провайдере, ловушки на рантайм-пути. |
| NTN-01 | 04-01, 04-03, 04-04, 04-07, 04-08, 04-12, 04-13 | ✓ SATISFIED | `NotionAsyncClient` (scopes `notion.read`, `notion.write`), `default_notion_client`, регистрация `notion_project_sync`, `notion_project` из персоны. |
| NTN-02 | 04-01, 04-02, 04-04, 04-07, 04-09, 04-10, 04-12, 04-13 | ✓ SATISFIED | HITL-карточки `ntn:req`/`ntn:conf`/`ntn:rej`, идемпотентный ключ, `reopen_action` в assistant-shared (04-02), дедупликация через `find_project_activity`. |

---

## 3. Поведенческие проверки и гейты качества

| Набор | Команда | Результат | Статус |
|-------|---------|-----------|--------|
| Тесты фазы 4 (10 файлов) | `.venv/bin/pytest tests/test_phase4_reachability.py tests/test_phase4_chain_e2e.py tests/test_git_chain_airgap.py tests/test_notion_git_hitl.py tests/test_git_bot_commands.py tests/test_git_connector.py tests/test_git_chain.py tests/test_phase4_hitl_security_fixes.py tests/test_phase4_git_read_failure.py tests/test_git_airgap_trap.py` | 152 passed | ✓ PASS |
| Гейт качества, прогон 1 | `python3 scripts/gate.py` | pytest 1179 ✓; строка «боевая assistant.db не изменена» ✗: хеш изменился, пока сервис `assistant-worker` активен и пишет в БД; остальные строки ✓ → ИТОГ КРАСНЫЙ | ⚠ ложный красный из-за живой записи сервиса |
| Гейт качества, прогон 2 | `python3 scripts/gate.py` | pytest assistant-core 1179 ✓, assistant-shared 211 ✓, SHA-256 БД до/после совпал, import-linter ✓, security_shield ✓, дрейф персоны ✓, hook ✓ → ИТОГ ЗЕЛЁНЫЙ | ✓ PASS |

Пояснение к прогону 1: гейт сам рекомендует повторить прогон при записи живого сервиса; тесты в обоих прогонах прошли, во втором неизменность БД подтверждена. Страж `tests/live_db_guard.py` остаётся основной защитой.

---

## 4. Антипаттерны

- Маркеры `TBD`, `FIXME`, `XXX`, `TODO`, `HACK` в изменённых файлах `src/` фазы отсутствуют; пропусков/xfail в тестах фазы нет.
- `sanitize_notion_payload_for_airgap` (`src/security/airgap.py:228`) нигде в `src/` не вызывается: мёртвый код, защищён только тестом. ⚠ Предупреждение (запись остаётся из ревизии, не блокирует: запись в Notion идёт только из `_handle_notion_sync` с повторной проверкой допуска и данными, собранными из уже санированных коммитов).
- Закрыты с тестами: fail-closed `_is_authorized`, `cb_ntn_reject` проверяет `CONFIRMED`, сбой обновления сообщения не откатывает запись (261015-kuf); `GitStatus.READ_FAILED` вместо ложного «Застой», `latest_commit_date` по максимуму (261015-kuf); regex «скрой/покажи команду», UTC-фолбэк даты, обрезка `card_text` до 4096, фолбэк даты коммита (261016-p4r); пропуск коммита с нечитаемой датой, скрытие `user:token@` в stderr git, исправление двух тестов (261018-arg, Argon №11, №13, №17, №18).

---

## 5. Известные риски (не верифицированы, ждут решения владельца)

Источник: `.planning/REVIEW-ARGON-20261018-1216.md`, раздел «Вердикты Claude». Эти пункты не считаются подтверждёнными; кода не менял никто.

| Пункт Argon | Суть | Состояние по коду |
|-------------|------|-------------------|
| №3 (Air-Gap) | `git fetch --all` и `git log --branches --remotes` читают все remote из локального `.git/config`, а не только `remote` персоны | Механика подтверждена чтением `provider.py:98,163`; упирается в решение владельца 2026-10-15. **Открыто.** |
| №4 (Air-Gap) | `_norm_path` не разворачивает симлинки; путь `/` превращается в `None` и не пересекается ни с чем | Механика подтверждена чтением `airgap.py:280-287`; на реальных путях персоны проблема не воспроизводилась. **Открыто.** |
| №5 (Air-Gap) | Провайдер на своей границе проверяет только `clearance` (`is_git_chain_eligible`), а не пересечения с NDA-пространствами; пересечения отсекает шлюз в `evaluate()` | Подтверждено чтением; основной рантайм-путь идёт через шлюз. **Открыто.** |
| №7 | Нажатие «Отклонить» во время долгой записи в Notion отвечает «Уже подтверждено», после сбоя запись возвращается в pending | Не проверено по коду. |
| №8, №10, №12, №14 | Дубли карточек на стыке суток; `%aI` против даты коммитера; UTC в промпте против `Europe/Moscow` в карточке; повторное сообщение с кнопками при повторном нажатии | №14 подтверждается чтением `cb_ntn_request` (сообщение шлётся каждый раз); остальные не проверены. |
| №9 | Обработчик `notion_project_sync` регистрируется только в `GitProgressEvaluator.__init__`; если оценщик не создан, старые pending-карточки не обработаются | Подтверждено чтением; поведение безопасное (запись не происходит, пользователь видит «Не записано в Notion, повторите»). |
| №2, №6, №16 | Нормализация remote без разбора URL; скрипт `agy_argon_review.sh` | Не проверено; №1 завышен, №15 ложный (по вердиктам). |

---

## 6. Что требует решения или проверки человеком

1. **Air-Gap №3–5** — решение владельца (см. раздел 5).
2. **Выкатка последних правок.** `assistant-worker` активен с 2026-10-15 20:52 UTC (`systemctl show`). Коммиты 5765e53, 6341540, cf77525 (2026-10-16) и 9579db4 (2026-10-18) изменяют `src/` и в запущенный процесс не вошли. Рестарт — только по разрешению владельца: `python3 scripts/deploy.py --backup --restart`.
3. **Живая запись в Notion.** Тесты используют подменённый клиент; страница в боевой Notion не создавалась в рамках верификации.

---

## 7. Итог

Цепочка «git → оценка → HITL-карточка → Notion» достижима из рантайма (планировщик и команда `/git`), запись в Notion происходит только после подтверждения, `restricted_nda` и неопределённый допуск отсекаются fail-closed на шлюзе и на границе провайдера. Критерий 1 выполнен частично по осознанному решению владельца (подключение через remote локального клона). Статус `human_needed`: остаются решение по Air-Gap №3–5, рестарт для выкатки четырёх последних коммитов и живая проверка записи в Notion.

---

_Проверено: 2026-10-18_
_Верификатор: Claude (gsd-verifier)_
