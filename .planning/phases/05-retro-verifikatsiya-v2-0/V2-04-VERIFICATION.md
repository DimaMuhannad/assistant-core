---
phase: 05-retro-verifikatsiya-v2-0
v2_phase: "04"
v2_source: /opt/chat-app/.planning/milestones/v2.0-phases/04-vladelets-shemy-bd-i-obschaya-biblioteka-bezopasnosti
verified: 2026-10-18T22:46:37Z
status: gaps_found
score: "3 из 6 требований passed (SEC-01, SEC-02, SEC-03); gap: DAT-02, DAT-03, DAT-04"
requirements: [DAT-02, DAT-03, DAT-04, SEC-01, SEC-02, SEC-03]
gaps: [DAT-02, DAT-03, DAT-04]
---

# V2-04: Общая библиотека безопасности и изоляция тестов chat-app (ретро-верификация фазы 04 v2.0)

## Источник (только чтение)

- Исходный каталог: `/opt/chat-app/.planning/milestones/v2.0-phases/04-vladelets-shemy-bd-i-obschaya-biblioteka-bezopasnosti/` (проверено `ls`, файлы не правились).
- Состав каталога (15 файлов): `04-01..04-04-PLAN.md` и `04-01..04-04-SUMMARY.md`, `04-CONTEXT.md`, `04-DISCUSSION-LOG.md`, `04-RESEARCH.md`, `04-REVIEW.md`, `04-REVIEW-FIX.md`, `04-REVIEWS.md`, `04-VALIDATION.md`. Собственного `04-VERIFICATION.md` в v2.0 нет.
- Требования, вынесенные в этот файл: SEC-01, SEC-02, SEC-03, DAT-04 (план 05-06) и DAT-02, DAT-03 (план 05-07).

## Вердикты

| Требование | Статус | Точка входа в рантайме (file:line) | Тест или команда проверки | Метка |
|---|---|---|---|---|
| SEC-01 | passed | chat-app: `backend/app/api/v1/security.py:10` (импорт), `:42` и `:86` (аудит через библиотеку); assistant-core: `scripts/security_shield.py:19`, `:75`; hook: `.githooks/pre-commit:19` | `tests/test_nda_script_parity.py` и `tests/test_security_shield_cli.py` (16 passed, код 0); chat-app `test_security_shared.py`, `test_nda_equivalence.py`, `test_shield_parity.py` (47 passed, код 0) | трасса+e2e |
| SEC-02 | passed | логика: `scripts/security_shield.py:75` (assistant-core, `audit_repository`); делегаторы: chat-app `scripts/security_shield.py:46`, assistant-shared `scripts/security_shield.py:49` | assistant-core: 16 passed (см. SEC-01); chat-app `backend/tests/test_shield_delegator.py` и `test_pre_commit_hook.py` (15 passed, код 0); assistant-shared `tests/test_security_shield_delegator.py` (14 passed, код 0) | трасса+e2e |
| SEC-03 | passed | `.githooks/pre-commit:19` запускает `scripts/security_shield.py` и `audit_repository`; установка `scripts/install_hooks.sh:40` (не запускался); проверка `scripts/gate.py:780` (`hook_installed_check`), вызовы `:908` (assistant-core) и `:922` (assistant-shared) | проба во временном репозитории: чистый коммит rc 0, коммит с синтетическим секретом rc 1 с названием шаблона «AWS Access Key ID» (см. «Доказательства», раздел SEC-03) | e2e |
| DAT-02 | gap | worker: `src/main.py:646-648` (`Database(config.SQLITE_DB_PATH)`, лог «Database initialized at»), путь: `src/config.py:16-24` (`DATABASE_URL`, от `BASE_DIR`); chat-app: `backend/app/core/config.py:20-22` (`SQLITE_DB_PATH`, алиас `DATABASE_PATH`), `backend/app/db.py:13` | сравнение `realpath -m` журнала воркера текущей инвокации и ответа владельца: пути не совпадают (см. `### DAT-02`); `test_db_config.py` не запускался (Ограничения, п. 9) | трасса |
| DAT-03 | gap | `/opt/assistant-shared/assistant_shared/db/connection.py:42-45` (async: `PRAGMA busy_timeout`, `journal_mode = WAL`), `:61-64` (sync); вызовы фабрики: `src/storage/db.py:48` (`Database.connection`), `backend/app/db.py:13` (chat-app), `assistant_shared/hitl/store.py:51` (`ConfirmationStore`) | `05-EVIDENCE-DAT03.md`, 60 последовательных прогонов: free 1/30, load 0/30, полных прогонов K=1, J=0; «Вердикт DAT-03: gap» | e2e |
| DAT-04 | gap | `backend/app/api/v1/security.py:42` (`asyncio.to_thread(audit_path, ...)` для пространства `/opt/assistant-core` из фикстуры персоны); обход дерева в `assistant_shared/security/auditor.py:156` (`rglob`); тесты-вызыватели `backend/tests/test_security_golden.py:79,104`, `backend/tests/test_nda_equivalence.py:360,413-415` | полный прогон `backend/tests` под `strace -f --seccomp-bpf -e trace=file`: 278 passed, 1 failed; положительный контроль: 1 попадание; обращения к данным и файлу БД: 9 строк | e2e |

Строки DAT-02 и DAT-03 вынесены планом 05-07 (подразделы ниже).

## Доказательства

### DAT-02

**Путь воркера (журнал текущей инвокации):** `INV=$(systemctl show assistant-worker.service -p InvocationID --value)`, затем `journalctl -u assistant-worker.service _SYSTEMD_INVOCATION_ID="$INV"` и первая строка «Database initialized at». Найдена одна такая строка. Результат: `/opt/assistant-core/data/assistant.db`. Статика: `src/config.py:16-24` (путь из `DATABASE_URL`, по умолчанию `./data/assistant.db`, относительный путь приводится к `BASE_DIR`); `src/main.py:646-648`.

**Путь chat-app:** `/opt/chat-app/backend/data/assistant.db`. Это ответ владельца на одну команду (checkpoint:human-action, решение владельца 2026-10-18 №4), получен с третьей попытки. Команду выполнил владелец. Агенты `.env` chat-app не читали и настройки chat-app не импортировали. Статика: `backend/app/core/config.py:20-22`, `SQLITE_DB_PATH` по умолчанию `./data/assistant.db` относительно рабочего каталога; WorkingDirectory юнита chat-app — `/opt/chat-app/backend`, то есть путь тот же.

**Юниты (без вывода Environment):**

| Юнит | ActiveState | WorkingDirectory | Попаданий `SQLITE_DB_PATH` или `DATABASE_PATH` в Environment (grep -c) | EnvironmentFiles |
|---|---|---|---|---|
| chat-app.service | inactive | /opt/chat-app/backend | 0 | пусто |
| assistant-worker.service | active | /opt/assistant-core | 0 | пусто |

**Сравнение (`realpath -m`, строки путей, файлы не открывались и не хешировались):**

- воркер: `/opt/assistant-core/data/assistant.db`
- chat-app: `/opt/chat-app/backend/data/assistant.db`
- результат: **пути не совпадают**. Два процесса открывают разные файлы БД.

**Вердикт DAT-02: gap.** Класс D-09 «целостность данных», серьёзность high. Предложение: новое требование DAT-06 (chat-app и демон работают с одной БД), Phase 999.x; связано с записью бэклога Phase 999.2, где этот риск уже отмечен. Причина не исследовалась (D-10).

**Оговорка по букве требования.** Требование DAT-02 формулирует «путь берётся из настроек в обоих процессах». По букве это выполняют оба процесса. Протокол плана 05-07 сравнивает итоговые пути, и вердикт gap следует протоколу. Решение владельца: принять gap по протоколу или переформулировать DAT-02 в 05-08.

### DAT-03

**Протокол:** `05-EVIDENCE-DAT03.md`, тест `backend/tests/test_concurrent_write.py::test_concurrent_write_two_processes`, 60 последовательных целевых прогонов (30 в режиме free, 30 под нагрузкой) и полные прогоны набора (K=1). Тест в этом плане повторно не запускался (D-08, D-10).

**Числа:** free 1 из 30 (free-27, rc 1); load 0 из 30; полных прогонов под нагрузкой K=1, из них J=0. Вердикт протокола: **gap**, так как D-08 требует 0 сбоев в каждом режиме и J=0.

**Первая строка ошибки (дословно из evidence):** `sqlite3.OperationalError: database is locked`. Сбой на `assistant_shared/db/connection.py:64` (`PRAGMA journal_mode = WAL`), при этом `busy_timeout` задан строкой выше.

**Трасса части «WAL и busy_timeout включены»:**

- `/opt/assistant-shared/assistant_shared/db/connection.py:42` `PRAGMA busy_timeout = 30000;` и `:45` `PRAGMA journal_mode = WAL;` (асинхронная фабрика `get_async_connection`, строка 32).
- `:61` `PRAGMA busy_timeout = 30000;` и `:64` `PRAGMA journal_mode = WAL;` (синхронная фабрика `get_sync_connection`, строка 50).
- Рантайм assistant-core: `src/storage/db.py:39-48` (`Database.connection` вызывает `get_async_connection(self.db_path)`).
- Рантайм chat-app: `backend/app/db.py:13` (`get_async_connection(settings.SQLITE_DB_PATH)`); `ConfirmationStore(settings.SQLITE_DB_PATH)` в `backend/app/api/v1/confirmations.py:11`, `reminders.py:58`, `projects.py:50`, `tasks.py:63`, `documents.py:49`. Сам `ConfirmationStore` (`assistant_shared/hitl/store.py:20`) открывает соединения через `get_async_connection` (строки 51 и далее).
- Тест `test_concurrent_write_two_processes` (`backend/tests/test_concurrent_write.py`): пул из двух процессов, каждый пишет 100 записей через `get_sync_connection` (строка 20), проверка в строке 69. Реальная фабрика, временная БД. Это часть e2e.

**Дополнительно (вне протокола D-08, в счёт 60 не входит):** полный прогон под strace в 05-06 дал один сбой того же теста из одного полного прогона (`1 failed, 278 passed`). См. «Наблюдения», п. 6.

**Замедленные прогоны из evidence:** free-21 (18.5 с) и free-26 (15.5 с). Причина не исследовалась.

### SEC-01

**Трасса по звеньям:**

1. chat-app: `backend/app/api/v1/security.py:10` импортирует `audit_path`, `collect_protected_keywords`, `nda_rule_for` из `assistant_shared.security`. Вызовы `audit_path` в `:42` (обзор) и `:86` (аудит).
2. assistant-core: `scripts/security_shield.py:19` импортирует `audit_repository` из `assistant_shared.security`; `:24` содержит запасной путь к `/opt/assistant-shared`; вызов `audit_repository` в `:75`.
3. assistant-shared (определения): `assistant_shared/security/patterns.py:9` (`SECRET_PATTERNS`), `assistant_shared/security/auditor.py:99` (`audit_path`), `:196` (`audit_repository`), экспорт в `assistant_shared/security/__init__.py`.
4. Рантайм-путь коммита: `.githooks/pre-commit:19` вызывает `scripts/security_shield.py`, тот вызывает `audit_repository`.
5. Гейт: `scripts/gate.py:901` запускает shield assistant-core, `:921` запускает shield assistant-shared.

**Импортёры** (`grep -rn "assistant_shared.security"` по `--include=*.py`):

- `/opt/chat-app/backend/app/api/v1/security.py:10`
- `/opt/assistant-core/scripts/security_shield.py:19` и `:24`
- `/opt/assistant-shared/scripts/` — импорта нет (делегатор не импортирует библиотеку, см. SEC-02).

**Локальные копии:** `grep -rln SECRET_PATTERNS` по `/opt/chat-app/backend/app`, `/opt/assistant-core/src` и `/opt/assistant-core/scripts` вернул пустой список. Определение шаблонов только в `assistant_shared/security/patterns.py:9`.

**Статус chat-app:** `systemctl show chat-app.service -p ActiveState` вернул `ActiveState=inactive`. Поэтому доказательство для chat-app статическое и тестовое. Рантайм-проверки chat-app в этой фазе нет.

**Выполненные команды:**

- assistant-core: `cd /opt/assistant-core && PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider tests/test_nda_script_parity.py tests/test_security_shield_cli.py -q` — код 0, `16 passed in 11.02s`.
- chat-app (только чтение): `cd /opt/chat-app && PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/pytest -p no:cacheprovider backend/tests/test_security_shared.py backend/tests/test_nda_equivalence.py backend/tests/test_shield_parity.py -q` — код 0, `47 passed in 34.46s`.
- `git status --porcelain --ignored` chat-app до и после запусков совпал.

### SEC-02

| Репозиторий | Файл | Строк | Что делает | Fail-closed |
|---|---|---|---|---|
| assistant-core | `scripts/security_shield.py` | 79 | загружает правила пространств из персоны и вызывает `audit_repository` (`:75`) | да: ошибка данных пространств даёт rc 1; неизвестный флаг даёт rc 2 |
| chat-app | `scripts/security_shield.py` | 55 | запускает обёртку assistant-core подпроцессом (`:46`) тем же интерпретатором, код возврата наследуется | да: нет каталога, обёртки или интерпретатора дают «SECURITY SHIELD ERROR» и rc 1 |
| assistant-shared | `scripts/security_shield.py` | 58 | то же, подпроцессом (`:49`) | да, как выше; завершение сигналом даёт rc 1 |

**Дрейфа нет.** В делегаторах нет констант правил и нет импорта библиотеки (проверено `grep`). Логика сканирования одна: `audit_repository` в библиотеке. Единственная обёртка с логикой — assistant-core. Регрессию стиля «копия логики» закрывают `tests/test_nda_script_parity.py` (`test_p01_script_passes_persona_workspaces_and_nothing_else`, `test_d10_library_has_no_nda_word_constants`) и `backend/tests/test_shield_parity.py` (паритет веб-аудита и CLI).

**Выполненные команды и коды:**

- assistant-core: см. SEC-01, 16 passed, код 0.
- chat-app: `backend/tests/test_shield_delegator.py` (включая `test_delegator_does_not_import_the_shared_library` и `test_delegator_end_to_end_blocks_secret_and_passes_clean`) вместе с `test_pre_commit_hook.py` — код 0, `15 passed`. Команда: `cd /opt/chat-app && PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/pytest -p no:cacheprovider backend/tests/test_shield_delegator.py backend/tests/test_pre_commit_hook.py -q`.
- assistant-shared: `cd /opt/assistant-shared && PYTHONDONTWRITEBYTECODE=1 /opt/assistant-core/.venv/bin/pytest -p no:cacheprovider tests/test_security_shield_delegator.py -q` — код 0, `14 passed in 6.50s`. Дерево assistant-shared до и после совпало.

### SEC-03

**Установка (проверка без запуска установщика):**

- `git config --get core.hooksPath`: assistant-core `.githooks`, chat-app `.githooks`, assistant-shared `.githooks`.
- `test -x .githooks/pre-commit`: исполняемый во всех трёх репозиториях (`-rwxr-xr-x`).
- `scripts/install_hooks.sh` прочитан, не запускался: проверка `import assistant_shared.security` (`:29`), `chmod +x` (`:34`), предупреждение при другом значении `core.hooksPath` (`:36-38`), запись `core.hooksPath = .githooks` (`:40`). Установка воспроизводима: при повторном запуске с тем же значением результат не меняется.
- `scripts/gate.py` `hook_installed_check` (`:780`) вызывается для assistant-core (`:908`) и assistant-shared (`:922`). Для chat-app проверки в гейте нет.

**Проба e2e (временный репозиторий вне боевых путей):**

- Каталог: `/var/tmp/gsd-phase05-probes/sec03/` (права 0700). Репозиторий создан `mktemp -d`, после проверки удалён (остатков нет).
- Настройка: `git init`, синтетические `user.name` и `user.email` только в этом репозитории, копия `.githooks/pre-commit` из assistant-core, `core.hooksPath = .githooks`, симлинк `scripts/security_shield.py` на обёртку assistant-core (в индекс не добавлялся). Коммиты с `VIRTUAL_ENV=/opt/assistant-core/.venv`, чтобы hook выбрал интерпретатор assistant-core.

| Шаг | Результат |
|---|---|
| коммит чистого файла (контроль «чисто») | код 0; в логе есть баннер hook |
| коммит файла с синтетическим секретом (ключ собран из частей при выполнении, в файл целиком не записывался) | код 1; в выводе hook: `secret.txt:1 - Found potential AWS Access Key ID` |
| число коммитов во временном репозитории | 1 (только чистый) |
| удаление временного репозитория | выполнено |

- Литерал ключа в логе пробы не найден (0 совпадений). Логи лежат только в `/var/tmp/gsd-phase05-probes/sec03/` и в документ не вносятся.
- Коммитов в assistant-core не делалось. `git -C /opt/assistant-core rev-parse HEAD` и `git config --list --local` до и после пробы совпали.

### DAT-04

**Статическая часть:**

- `backend/tests/conftest.py:1-5` (docstring): «Каталог /opt/assistant-core во время тестов недоступен и не используется». Это утверждение пробой ниже опровергнуто (см. gap).
- `backend/tests/test_database_isolated.py:14` проверяет только путь БД тестов (не содержит `/opt/assistant-core`). Обход рабочих пространств этим тестом не проверяется.
- `backend/tests/test_security_golden.py:29` содержит фикстуру пространства с путём `/opt/assistant-core` (строка данных, не обращение к файлу).
- `backend/app/api/v1/security.py:42` и `:86` запускают `audit_path` для пути пространства в `asyncio.to_thread`. `assistant_shared/security/auditor.py:156` обходит дерево через `rglob("*")`. Так пространство `assistant-core` из фикстуры персоны обходит реальный каталог `/opt/assistant-core`.

**Положительный контроль (проба действительна):** `strace -f --seccomp-bpf -e trace=file` на `python3 -c "import os; os.stat('/opt/assistant-core/pytest.ini')"`. Результат: `total=162 chatapp=0 shared=0 hits=1`, в `control.hits` строка `newfstatat(AT_FDCWD, "/opt/assistant-core/pytest.ini", ...) = 0`. Попадание есть.

**Основной прогон:**

- Команда: `cd /opt/chat-app && strace -f --seccomp-bpf -e trace=file -o '|awk -v out=<probe>/real -f <probe>/filter.awk' env PYTHONDONTWRITEBYTECODE=1 /opt/chat-app/backend/.venv/bin/pytest -p no:cacheprovider -q --basetemp=<probe>/tmp backend/tests`. Запуск один, в фоне, параллельно ничего не выполнялось.
- Итог pytest: код 1, `1 failed, 278 passed, 3 warnings in 143.01s`. Упал `backend/tests/test_concurrent_write.py::test_concurrent_write_two_processes` (`sqlite3.OperationalError: database is locked`). Это наблюдение для DAT-03, см. «Наблюдения».
- Счётчики фильтра (`real.counts`): `total=330932 chatapp=16905 shared=1739 hits=14814`.
- Обращения к `/opt/assistant-core` (14814 строк, 703 различных пути, 186 потоков и процессов):
  - **Класс «целостность данных»:** 2 различных пути, `/opt/assistant-core/data` и `/opt/assistant-core/data/assistant.db`, всего 9 строк. Все 9 строк — `newfstatat` (stat и lstat). `openat`, чтения и записи в трассе по этим путям нет. Все 9 строк принадлежат одному потоку (tid 1370946), который выполнял обход аудита Security Tile.
  - **Класс «улучшение (герметичность тестов)»:** остальные 701 путь: корень `/opt/assistant-core` (обход аудита), `CLAUDE.md`, `docs/`, `Dockerfile`, `config/persona.yaml`, `config/prompts/*.jinja2`, `src/persona/*.py`, `scripts/security_shield.py`, `.venv/` (интерпретатор и site-packages). Источники: 20 запусков интерпретатора assistant-core (обёртка, аргументы — временные каталоги тестов делегаторов), 12 `chdir` в `/opt/assistant-core` и обход аудита.
  - Файлы `.env`, `token.json`, `credentials.json`, `*.session` в трассе не встречаются. `.env.example` встречается 8 раз (только имя примера).
- Контроль «боевая БД не открыта»: в трассе нет `openat` и других операций открытия для `data/assistant.db`.

**Вердикт:** gap (по правилу плана: любое обращение к `/opt/assistant-core/data/` или к файлу БД — класс «целостность данных»; любое иное обращение — класс «улучшение»). Оба класса зафиксированы в разделе «Gaps».

**Различные пути (первые 20 из 703; полный список в пробе, только пути):**

```
/opt/assistant-core
/opt/assistant-core/.claude/CLAUDE.md
/opt/assistant-core/CLAUDE.md
/opt/assistant-core/config
/opt/assistant-core/config/persona.yaml
/opt/assistant-core/config/prompts
/opt/assistant-core/config/prompts/debrief_default.jinja2
/opt/assistant-core/config/prompts/evening_digest_default.jinja2
/opt/assistant-core/config/prompts/git_progress_default.jinja2
/opt/assistant-core/config/prompts/intent_router_default.jinja2
/opt/assistant-core/config/prompts/methodist_default.jinja2
/opt/assistant-core/config/prompts/methodist_scope_check_default.jinja2
/opt/assistant-core/config/prompts/morning_brief_default.jinja2
/opt/assistant-core/config/prompts/reply_generator_default.jinja2
/opt/assistant-core/config/prompts/secretary_default.jinja2
/opt/assistant-core/data
/opt/assistant-core/data/assistant.db
/opt/assistant-core/docker-compose.yml
/opt/assistant-core/Dockerfile
/opt/assistant-core/docs/baseline/reconcile_report.json
```

Путь `/opt/assistant-core/data/assistant.db` входит в класс «целостность данных».

## Наблюдения (не gaps)

1. **SEC-02, оговорка (дословно, по плану).** «В chat-app и assistant-shared это делегаторы, а не обёртки над библиотекой, как говорит буква требования». Gap не создан: логика единая, дрейфа нет. Владелец извещается в итоговой сводке.
2. **SEC-01, доказательство chat-app статическое.** `chat-app.service` неактивен (`ActiveState=inactive`), рантайм chat-app в проверке не участвовал.
3. **Гейт и установленные hook.** `hook_installed_check` в `scripts/gate.py` проверяет assistant-core и assistant-shared. Hook chat-app гейтом не проверяется.
4. **Долг DEBT-03 IN-05.** Hook assistant-shared через делегатор зависит от пути `/opt/assistant-core`. Это известный долг, в gap не переносится.
5. **Расхождение документа и поведения.** Docstring `backend/tests/conftest.py:1-5` утверждает, что `/opt/assistant-core` во время тестов не используется. Трасса это опровергает (см. DAT-04). Исправление docstring — часть предложения по DAT-07 (план 05-08).
6. **Наблюдение для DAT-03 (вне протокола D-08).** В полном прогоне под strace (05-06) упал `test_concurrent_write_two_processes` с `sqlite3.OperationalError: database is locked`. Полный прогон под strace: 1 сбой из 1. Счёт по D-08 ведёт `05-EVIDENCE-DAT03.md` (план 05-05), вердикт DAT-03 вынесен в `### DAT-03`.
7. **Итог полного прогона chat-app под strace:** `1 failed, 278 passed` (код pytest 1). Ни один тест не пропущен через skip, xfail или deselected.
8. **Разные файлы БД у воркера и chat-app (DAT-02).** Воркер открывает `/opt/assistant-core/data/assistant.db`, chat-app по своей конфигурации открывает `/opt/chat-app/backend/data/assistant.db`. Класс риска тот же, что отмечен в бэклоге Phase 999.2. Передано в DAT-06 (план 05-08).
9. **Посторонний файл `/opt/assistant-core/assistant.db` (A8, только метаданные).** `ls -l`: размер 544768 байт, время изменения 8 окт. 06:30, владелец root. Файл не открывался и не хешировался. Происхождение не исследовалось (допущение RESEARCH A8).

## Gaps

| Требование | Класс по D-09 | Предложение оформления | Привязка |
|---|---|---|---|
| DAT-02 | целостность данных, серьёзность high | новое требование DAT-06: chat-app и демон работают с одной БД (общий путь или явная конфигурация), Phase 999.x | план 05-08 (REQUIREMENTS.md, DAT-06); бэклог Phase 999.x, связано с 999.2 |
| DAT-03 | целостность данных, серьёзность high | новое требование DAT-05: стабильная конкурентная запись двух процессов (WAL, busy_timeout), Phase 999.x; полный текст ошибки в `05-EVIDENCE-DAT03.md` | план 05-08 (REQUIREMENTS.md, DAT-05); Phase 999.x |
| DAT-04 (а): обращения к `/opt/assistant-core/data/` и файлу `assistant.db` (9 строк stat/lstat, один поток обхода аудита Security Tile) | целостность данных, серьёзность critical | новое требование DAT-07: тесты chat-app не обходят пространства по путям assistant-core; фикстура персоны указывает на временный каталог | план 05-08 (REQUIREMENTS.md, DAT-07), будущая фаза Phase 999.x |
| DAT-04 (б): обращения к `.venv`, `config/`, `scripts/`, `src/` и корню assistant-core (701 путь из делегаторов и обхода аудита) | улучшение (герметичность тестов), серьёзность low | запись бэклога Phase 999.x: герметичность тестов chat-app | план 05-08 (ROADMAP.md, бэклог 999.x) |

Gap DAT-04 (а) оценён по правилу плана: обращение stat-only считается обращением. Владелец может решить иначе (см. «Ограничения проверки», пункт 3).

## Ограничения проверки

1. `chat-app.service` неактивен. Для SEC-01 доказательство статическое и тестовое. Для SEC-03 и DAT-04 проба проводилась на уровне git и ОС, не на рантайме chat-app.
2. strace фиксирует только файловые системные вызовы (`trace=file`) в режиме `-f`. Обращения, не выполненные через файловые вызовы, трассой не видны. Сырой вывод strace не сохранялся целиком: в `/var/tmp/gsd-phase05-probes/dat04/` лежат отфильтрованные строки (`real.hits`) и счётчики.
3. Классификация stat-only обращения как «обращения» взята из правила плана без отдельного решения владельца.
4. Проба SEC-03 выполнена однократно. Чистый коммит и коммит с секретом прошли в одном временном репозитории, который удалён.
5. Боевая БД `/opt/assistant-core/data/assistant.db` не открывалась (в трассе нет открытия). Файлы `.env` не читались. Сервисы не перезапускались. Установка пакетов не выполнялась. agy не использовался.
6. `scripts/gate.py` в этом плане не запускался.
7. Код и тесты репозиториев не изменялись (D-10). Миграций нет.
8. **Путь chat-app получен от владельца одной командой.** Ответ принят с третьей попытки: первые две не выполнены по причинам запуска команды, не по существу. Записан только путь, без других значений. Исполнитель команду не запускал и `.env` не читал.
9. **`backend/tests/test_db_config.py` не запускался.** Модуль `app/core/config.py` создаёт `settings = Settings()` на уровне модуля с `env_file=".env"`, и импорт читает `.env` chat-app, что запрещено. Проверка выполнена по источнику: `app/core/config.py:20-22` содержит `./data/assistant.db` и не содержит хардкода `/opt/assistant-core`. Шаг pytest плана 05-07 поэтому не выполнен (отклонение зафиксировано в SUMMARY).
10. **Проба DAT-02 не рантаймовая для chat-app.** `chat-app.service` неактивен, путь chat-app вычислен конфигурацией в рабочем каталоге, а не процессом. Вердикт опирается на ответ владельца и статику.
11. **Вердикт DAT-03 не перепрогонялся.** Evidence-файл `05-EVIDENCE-DAT03.md` не менялся, `scripts/gate.py` не запускался, agy не использовался.
12. **Оговорка к DAT-02 по букве требования** (см. `### DAT-02`): решение владельца, принять gap по протоколу или переформулировать требование.
