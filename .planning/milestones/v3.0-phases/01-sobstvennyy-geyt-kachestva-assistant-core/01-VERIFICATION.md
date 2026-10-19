---
phase: 01-sobstvennyy-geyt-kachestva-assistant-core
verified: 2026-10-10T06:00:00Z
status: passed
score: 5/5 must-haves verified
covered_files:
  - ".planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-01-PLAN.md"
  - ".planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-01-SUMMARY.md"
  - ".planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-02-PLAN.md"
  - ".planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-02-SUMMARY.md"
  - ".planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-03-PLAN.md"
  - ".planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-03-SUMMARY.md"
  - ".planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-04-PLAN.md"
  - ".planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-04-SUMMARY.md"
  - ".planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-05-PLAN.md"
  - ".planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-05-SUMMARY.md"
  - ".planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-06-PLAN.md"
  - ".planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-06-SUMMARY.md"
  - ".planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-07-PLAN.md"
  - ".planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-07-SUMMARY.md"
  - ".planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-08-PLAN.md"
  - ".planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-08-SUMMARY.md"
  - ".planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-09-PLAN.md"
  - ".planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-09-SUMMARY.md"
  - ".planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-10-PLAN.md"
  - ".planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-10-SUMMARY.md"
  - "CLAUDE.md"
  - "docs/OPS_DEPLOY.md"
  - "scripts/deploy.py"
  - "scripts/gate.py"
  - "src/config.py"
  - "tests/conftest.py"
  - "tests/live_db_guard.py"
  - "tests/test_deploy_script.py"
  - "tests/test_gate.py"
  - "tests/test_gate_red_cases.py"
covered_digest: "v3:sha256:5c6fd6ece14737ffa37315dc201222384ff9b3eb5cddcece88d48c9cfd961848"
behavior_unverified: 0
overrides_applied: 0
re_verification: false
gaps: []
deferred:
  - truth: "Закрытие 20 находок код-ревью фазы 01 (CR-01, WR-01..WR-13, IN-01..IN-06)"
    addressed_in: "Phase 2 (решение владельца, опрос 2026-10-10)"
    evidence: "01-REVIEW-DISPOSITION.md: open 0, total 20, все deferred; Phase 2 в ROADMAP.md — «Безопасность, приватность и находки ревью»"
  - truth: "Первая живая резервная копия `--backup` и первый живой `--restart` со смоуком"
    addressed_in: "Phase 2 (первый рестарт по разрешению владельца), Phase 3 (первый `--backup` перед миграцией 0003)"
    evidence: "01-VERIFICATION-EVIDENCE.md, раздел «Открытые пункты для следующих фаз»; docs/OPS_DEPLOY.md §7"
---

# Фаза 1: Собственный гейт качества assistant-core. Отчёт верификации

**Цель фазы:** Владелец проверяет assistant-core и assistant-shared одной командой в собственном репозитории, не завися от общего `gate.py` chat-app, и получает по-русски однозначный итог «ЗЕЛЁНЫЙ» или «КРАСНЫЙ». Описана и автоматизирована процедура выкатки, которой пользуются все последующие фазы.
**Проверено:** 2026-10-10
**Статус:** passed
**Повторная верификация:** нет, первичная

Принцип проверки: SUMMARY.md не принимался как доказательство. Код читался напрямую, гейт и read-only смоук запущены верификатором самостоятельно на живой системе (раздел «Достижимость из рантайма»).

## Достижимость из рантайма (правило CLAUDE.md §5)

Функция считается готовой, только если доступна владельцу из рантайма, а не только покрыта юнит-тестами.

| Что | Как достигается владельцем | Проверено верификатором сам |
|---|---|---|
| Гейт | `cd /opt/assistant-core && python3 scripts/gate.py` | Да, 2026-10-10, одним запуском: rc 0, 10 строк ✓, «ИТОГ: ЗЕЛЁНЫЙ», 792 теста core, 91 тест shared, «SHA-256 до/после совпали: b17a71cf4524» |
| Смоук выкатки | `python3 scripts/deploy.py` (без флагов, только чтение) | Да, на живом `assistant-worker`: 6 проверок ✓, «АВТОМАТИЧЕСКАЯ ЧАСТЬ: ЗЕЛЁНАЯ», 10 из 10 задач планировщика; InvocationID `40e9fe7a…`, NRestarts 0, MainPID 295112 до и после — сервис не тронут |
| Подтверждение бота | `--await-help` и `--confirm-help yes` (фазы без TTY) | Не повторялось: требует действия владельца. Опирается на 01-SMOKE-REPORT.md (ответ владельца на /help «да») и на то, что InvocationID живого сервиса совпадает с зафиксированным в `/var/tmp/gsd-phase01-verify/series.txt` |
| Адаптер cross-AI | `/opt/chat-app/scripts/agy_cross_ai.sh --repo /opt/assistant-core` | Код выбора гейта прочитан (`agy_cross_ai.sh:311-318`: `$TOP/scripts/gate.py`, иначе гейт chat-app). Живой прогон не повторялся (токены агента, 271 с); независимые артефакты `/var/tmp/gsd-phase01-trial/` подтверждают: `rc.txt` = 0, в `gate-excerpt.txt` 10 строк и «ИТОГ: ЗЕЛЁНЫЙ» |

Дополнительно проверено ограничение «в chat-app ничего не менялось верификатором»: `git status` в `/opt/chat-app` чист; последние коммиты правки адаптера — `6b3b2ac` (код) и `4b73019` (документы quick-задачи).

Историческая серия (для контроля стабильности): `/var/tmp/gsd-phase01-verify/gate-run-1..3.txt`, все три rc 0, одинаковая таблица на одном HEAD `37e673d`, хеш БД внутри каждого прогона совпал.

## Достижение цели

### Проверяемые истины (критерии успеха ROADMAP)

| # | Истина | Статус | Доказательство |
|---|---|---|---|
| 1 | `python3 scripts/gate.py` печатает по-русски таблицу «проверка → ✓/✗» и «ИТОГ: ЗЕЛЁНЫЙ» (rc 0) на чистом дереве; сломанный тест, skip, xfail, xpass, deselected и ноль тестов дают КРАСНЫЙ; гейт не обрывается на первой ошибке (GATE-01) | ✓ VERIFIED | Живой запуск верификатора: ЗЕЛЁНЫЙ, rc 0. Код `scripts/gate.py`: `pytest_ok` требует rc 0, tests > 0, failures/errors/skipped = 0 и пустых флагов итоговой строки (`failed/error/skipped/deselected/xfailed/xpassed`); команда pytest с `-o xfail_strict=true` и пустым `PYTEST_ADDOPTS` (набор не сужается); `overall_green([])` = False; каждый шаг обёрнут в `_safe_*` и превращает исключение в красную строку, `_run_all` не прерывается. Независимая проверка: на мини-проекте с одним skip `run_pytest_step` вернул `ok=False`, отчёт закончился «ИТОГ: КРАСНЫЙ». Красные кейсы закреплены `tests/test_gate_red_cases.py` (fail, skip, xfail, xpass, deselected через addopts, ноль тестов, подмена PYTEST_ADDOPTS, нет бинарника, таймаут) и `tests/test_gate.py`; все входят в 792 зелёных теста |
| 2 | Тесты не открывают боевую БД; `load_dotenv(override=True)` её не перебивает (доказано тестом); гейт сверяет SHA-256 до/после и печатает совпадение (GATE-02) | ✓ VERIFIED | `src/config.py:9` захватывает `ASSISTANT_DB_PATH_OVERRIDE` ДО `load_dotenv` (строка 12), затем применяет его после вычисления `DATABASE_URL` (строки 22-24). `tests/live_db_guard.py` ставит `sys.addaudithook` на `open` и `sqlite3.connect` (нормализация URI, относительных путей, sidecar `-wal/-shm/-journal`, bytes/PathLike), устанавливается в `tests/conftest.py:19` до импорта `src`. Тесты: `test_db_path_override_survives_load_dotenv_override`, `test_test_process_uses_isolated_db_path`, `test_aiosqlite_connect_to_live_path_is_blocked` и др. `core_pytest_env` отвергает путь на боевую БД. В гейте: строка «боевая assistant.db не изменена», в выводе «SHA-256 до/после совпали: …». Боевую БД верификатор не открывал |
| 3 | У assistant-shared свои pytest-тесты (мигратор, HITL, безопасность) и воспроизводимо установленный pre-commit hook, блокирующий синтетический секрет; гейт показывает их отдельными строками (GATE-03) | ✓ VERIFIED | В `/opt/assistant-shared/tests/`: `test_migrations.py`, `test_hitl_shared.py`, `test_security_shared.py`, `test_shield_parity.py`, `test_shield_regressions.py`, `test_pre_commit_hook.py`; гейт собирает 91 тест. `.githooks/pre-commit` (исполняемый), `scripts/install_hooks.sh`, `git config core.hooksPath` = `.githooks` в обоих репозиториях. `test_blocked_on_synthetic_secret` и `test_blocked_on_forbidden_env_file` в тестах hook. В живом прогоне три строки assistant-shared: pytest 91, security_shield, hook установлен. Коммиты shared: `4fd0239`, `3438904`, `7256399`, `aec78bc`, `74aa928` |
| 4 | Гейт не слабее общего гейта chat-app по части assistant-core: дрейф `synthetic_persona.py` и `persona_tokens.py` с копиями chat-app (только чтение) и замороженный список ложных срабатываний shield (записи только удаляются); пробный прогон адаптера и правила CLAUDE.md используют новый гейт и дают ЗЕЛЁНЫЙ (GATE-04, GATE-05) | ✓ VERIFIED | Строки «синтетическая персона (дрейф SHA-256)» и «токены персоны (дрейф SHA-256)» в живом прогоне ✓; `persona_drift_check` читает копию chat-app только на чтение (`test_persona_drift_check_never_modifies_chat_copy`). `KNOWN_SHIELD_FALSE_POSITIVES` = одна запись `config/persona.yaml / nda-keyword: 3`, для shared пусто; устаревшая запись краснит гейт (`test_run_shield_step_core_stale_frozen_entry_is_red`), новая находка краснит (`..._one_extra_finding_is_red`), `test_known_shield_false_positives_frozen_list_is_exact`. `CLAUDE.md` и `.claude/CLAUDE.md` указывают на `python3 scripts/gate.py`; устаревшая оговорка «until assistant-core has its own» удалена; страж `tests/test_claude_md_gate_pointer.py`. Адаптер: `/opt/chat-app/scripts/agy_cross_ai.sh` выбирает `$TOP/scripts/gate.py`; пробный прогон `rc.txt` = 0, «ИТОГ: ЗЕЛЁНЫЙ» (артефакты `/var/tmp/gsd-phase01-trial/`). Ограничение: живой прогон адаптера верификатор не повторял |
| 5 | Процедура выкатки описана и автоматизирована скриптом: рестарт только по разрешению владельца, затем смоук (сервис active, нет ошибок в журнале старта, планировщик зарегистрировал задачи, бот отвечает); смоук не пишет в боевую БД; read-only часть запущена на текущем сервисе без рестарта, результат записан (OPS-01) | ✓ VERIFIED | `docs/OPS_DEPLOY.md` (12 разделов: правила, флаги, проверки смоука, окно ошибок, фазы без TTY, `--backup`, `--restart`, откат, отчёт, ограничения). `scripts/deploy.py`: единственный вызов `systemctl restart` собран в одном месте (строка 1029) и достижим только при `args.restart`; из `systemctl` без флага используется только `show`; БД открывается только в `make_db_copy` через `file:…?mode=ro` (строка 965) и только при `--backup`; откат только печатается (команды `systemctl stop/start/restart` лежат в тексте отчёта, строки 1086-1098). `python3 scripts/deploy.py --help` подтверждает флаги. 173 теста в `tests/test_deploy_script.py` (в составе 792 зелёных). Живой read-only смоук верификатора: 6 проверок ✓ на сервисе без рестарта. Результат владельца по боту — `01-SMOKE-REPORT.md`: «ИТОГ СМОУКА: ЗЕЛЁНЫЙ», ответ владельца на /help «да» |

**Оценка:** 5/5 истин проверены. Истин, которые «присутствуют, но поведение не проверено» (PRESENT_BEHAVIOR_UNVERIFIED), нет: поведенческие инварианты (только по флагу `--restart`, только печать отката, красный при skip/xfail/0 тестов, страж БД) закреплены выполняющимися тестами, а красный путь гейта дополнительно проверен вручную на мини-проекте.

### Обязательные артефакты

| Артефакт | Назначение | Статус | Детали |
|---|---|---|---|
| `scripts/gate.py` | Гейт, 754 строки, только stdlib | ✓ VERIFIED | Существует, содержателен, запускается; данные текут (реальные pytest/shield/хеш) |
| `scripts/deploy.py` | Смоук, backup, restart, откат, 1430 строк | ✓ VERIFIED | Существует; `--help` работает; живой смоук выполнен |
| `docs/OPS_DEPLOY.md` | Процедура выкатки, 193 строки | ✓ VERIFIED | Описания флагов сверены с `--help` тестом дрейфа документа и CLI (план 01-07) |
| `tests/live_db_guard.py`, `tests/conftest.py` | Страж боевой БД | ✓ VERIFIED | Подключён в conftest до импорта `src` |
| `src/config.py` | Приоритет изолированного пути БД | ✓ VERIFIED | Захват до `load_dotenv`, применение после |
| `/opt/assistant-shared/tests/*`, `.githooks/pre-commit`, `scripts/install_hooks.sh` | Тесты и hook shared | ✓ VERIFIED | Подключены к гейту отдельными строками |
| `CLAUDE.md`, `.claude/CLAUDE.md` | Правила на собственный гейт | ✓ VERIFIED | Страж-тест зелёный |
| `/opt/chat-app/scripts/agy_cross_ai.sh` | Адаптер выбирает гейт целевого репозитория | ✓ VERIFIED | Код прочитан; chat-app `scripts/gate.py` не изменён (D-15) |

### Проверка ключевых связей

| От | К | Через | Статус |
|---|---|---|---|
| `scripts/gate.py::_run_all` | `tests/conftest.py` → `src/config.py` | `ASSISTANT_DB_PATH_OVERRIDE` в env подпроцесса pytest | ✓ WIRED (путь до выполнения тестов подменяется; хеш боевой БД до/после совпал) |
| `scripts/gate.py` | `/opt/assistant-shared` | `SHARED_DIR`, pytest интерпретатором core `.venv`, shield, hook | ✓ WIRED (3 строки в живом прогоне) |
| `scripts/gate.py` | chat-app копии персоны | `persona_drift_check`, чтение `rb` | ✓ WIRED |
| `CLAUDE.md` | `scripts/gate.py`, `docs/OPS_DEPLOY.md` | текстовая команда + страж-тест | ✓ WIRED |
| `agy_cross_ai.sh` | `/opt/assistant-core/scripts/gate.py` | выбор `$TOP/scripts/gate.py` | ✓ WIRED |
| `scripts/deploy.py` | `assistant-worker.service`, журнал, Telegram getMe | `systemctl show`, журнал по InvocationID, HTTP getMe | ✓ WIRED (живой смоук ✓) |
| `docs/OPS_DEPLOY.md` | флаги `deploy.py` | тест дрейфа документа и CLI | ✓ WIRED |

### Покрытие требований

Все ID из frontmatter PLAN сверены с `.planning/REQUIREMENTS.md`. Осиротевших требований нет: REQUIREMENTS.md отображает на Phase 1 ровно GATE-01..05 и OPS-01, и все они заявлены в планах.

| Требование | Планы | Статус | Доказательство |
|---|---|---|---|
| GATE-01 | 01-01, 01-04, 01-05, 01-10 | ✓ SATISFIED | Истина 1 |
| GATE-02 | 01-01, 01-04, 01-05, 01-10 | ✓ SATISFIED | Истина 2 |
| GATE-03 | 01-02, 01-03, 01-05 | ✓ SATISFIED | Истина 3 |
| GATE-04 | 01-04, 01-05 | ✓ SATISFIED | Истина 4 |
| GATE-05 | 01-08, 01-09 | ✓ SATISFIED | Истина 4 (живой прогон адаптера не повторялся, см. оговорку) |
| OPS-01 | 01-06, 01-07, 01-10 | ✓ SATISFIED | Истина 5 |

В REQUIREMENTS.md все шесть отмечены `[x]` и «Complete». Для GATE-06 (вне этой фазы) в таблице нет отображения на Phase 1; это ожидаемо.

### Поведенческие проверки (Step 7b)

| Поведение | Команда | Результат | Статус |
|---|---|---|---|
| Полный гейт на чистом дереве | `python3 scripts/gate.py` | rc 0, 10 строк ✓, «ИТОГ: ЗЕЛЁНЫЙ» | ✓ PASS |
| Красный при skip (независимый мини-проект) | `run_pytest_step` на проекте с одним `@pytest.mark.skip` + `render_report` | `ok=False`, «ИТОГ: КРАСНЫЙ» | ✓ PASS |
| Read-only смоук живого сервиса | `python3 scripts/deploy.py --state-file <scratch> --report <scratch>` | 6 проверок ✓, rc 0, InvocationID/NRestarts/MainPID не изменились | ✓ PASS |
| Справка CLI выкатки | `python3 scripts/deploy.py --help` | флаги `--backup/--restart/--report/--await-help/--confirm-help…` совпадают с OPS_DEPLOY.md | ✓ PASS |

Полный pytest запускался один раз (внутри гейта), без повторных фильтрованных прогонов.

### Выполнение probe (Step 7c)

Probe-скриптов `scripts/*/tests/probe-*.sh` в фазе нет и ни один не заявлен в PLAN: шаг не применим.

### Анти-паттерны

Поиск маркеров долга `TBD/FIXME/XXX` в изменённых файлах фазы (`scripts/gate.py`, `scripts/deploy.py`, `src/config.py`, `tests/live_db_guard.py`, `docs/OPS_DEPLOY.md`) выполнялся вместе с чтением кода; блокирующих заглушек, пустых реализаций и необработанных долговых маркеров не обнаружено. Слабые места, найденные код-ревью, перечислены ниже как отложенные.

## Отложенные пункты (не пробелы цели фазы)

### Находки код-ревью (20, все deferred в Phase 2 решением владельца, опрос 2026-10-10)

Источник: `01-REVIEW.md`, `01-REVIEW-DISPOSITION.md` (open 0, total 20). Ни одна находка не опровергает обязательную истину фазы: каждая относится к усилению защиты или к качеству кода, а заявленное поведение (GATE-01..05, OPS-01) подтверждено исполнением. Заслуживают внимания при планировании Phase 2, потому что ослабляют устойчивость гейта:

| Находка | Серьёзность | Суть | Влияние на цель фазы |
|---|---|---|---|
| CR-01 | critical | Path traversal при записи файла Google Drive (`src/connectors/gdrive/client.py`), запись от root за пределы uploads | Вне цели фазы (код рантайма, не гейт и не выкатка). Критическая, поэтому в Phase 2 первой |
| WR-03 | warning | Смягчение проверки «боевая БД не изменена» (`gate.py:481-561`) при записи сервиса фактически отключает сравнение; вердикт держится на страже тестов | Истина 2 держится: сравнение хешей есть, в трёх исторических прогонах и в живом прогоне верификатора хеши совпали, страж доказан тестами. Усилить в Phase 2 |
| WR-04 | warning | Замороженный список shield сравнивает (путь, вид, счётчик), а не конкретную строку: три ложные находки можно подменить тремя настоящими | Истина 4 держится: список на месте и работает как заявлено; усиление отпечатками строк — Phase 2 |
| WR-05, WR-06 | warning | Адаптер: гейт цели исполняет код, который патч может менять; для репозитория без `scripts/gate.py` молча берётся гейт chat-app | Для `--repo /opt/assistant-core` адаптер корректно использует новый гейт (проверено кодом и артефактом пробного прогона) |
| WR-07 | warning | Страж боевой БД не закрывает часть путей | Закрывает пути, заявленные планом и тестами; остаточные пути — Phase 2 |
| WR-08, WR-09 | warning | `deploy.py`: запись от root в предсказуемый путь `/var/tmp` с переходом по symlink; `make_db_copy` меняет права существующего каталога | Затрагивает только ветки с записью; read-only смоук не затронут. Проверить до первого живого `--backup` |
| WR-01, WR-02, WR-10..WR-13, IN-01..IN-06 | warning/info | Блокирующий I/O в async, архив бэкапа, недетерминированные тесты, слабые тесты, мелочи в `gate.py`/`deploy.py`/hook/gdrive | Вне must-have |

### Прочие открытые пункты на следующие фазы

- Первый живой `--restart` assistant-worker со смоуком: по явному разрешению владельца (Phase 2). До него подтвердить допущение A1: в боевом `.env` нет ключа `ASSISTANT_DB_PATH_OVERRIDE` (в 01-SECURITY.md T-01-03 закрыт: переменная читается из окружения процесса до `load_dotenv`, поэтому ключ в `.env` безвреден по построению; в юните нет `Environment=`/`EnvironmentFile`).
- Первый живой `--backup` перед миграцией `0003` (Phase 3), проверка прав каталога копий (A6); решение про пустые sidecar-файлы WAL в `data/` (`deferred-items.md`).
- Нестабильный тест chat-app `test_concurrent_write_two_processes` (DAT-03, Phase 6).
- Статусные чекбоксы «Phase 1» и планов в `ROADMAP.md` остаются `[ ]`, хотя `Plans: 10/10`: обновляет оркестратор при закрытии фазы (не гейт цели).

## Согласованность с уже принятыми решениями

- `01-SECURITY.md`: status secured, threats_open 0. Принято без пересмотра.
- `01-VALIDATION.md`: status validated, nyquist_compliant true. Принято без пересмотра.
- `01-REVIEW.md` + `01-REVIEW-DISPOSITION.md`: 20 находок deferred, см. выше.

## Резюме

Пробелов нет. Цель фазы достигнута и достижима из рантайма: владелец одной командой `python3 scripts/gate.py` в `/opt/assistant-core` получает таблицу по-русски и «ИТОГ: ЗЕЛЁНЫЙ» / «ИТОГ: КРАСНЫЙ» (проверено живым запуском верификатора и красным контролем на мини-проекте); процедура выкатки описана в `docs/OPS_DEPLOY.md`, автоматизирована `scripts/deploy.py`, её read-only часть выполнена на живом сервисе без рестарта и без записи в боевую БД. Оговорки, не меняющие статус: ветки `--restart` и `--backup` проверены только юнит-тестами (сервисы заморожены по ограничению проекта), живой прогон адаптера cross-AI верификатором не повторялся (подтверждён кодом и артефактами `/var/tmp/gsd-phase01-trial/`), подтверждение бота владельцем взято из `01-SMOKE-REPORT.md`.

---

_Проверено: 2026-10-10_
_Верификатор: Claude (gsd-verifier)_
