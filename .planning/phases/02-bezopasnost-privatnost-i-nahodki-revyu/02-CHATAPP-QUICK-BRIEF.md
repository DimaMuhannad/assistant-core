# Задание для /gsd-quick в chat-app: shield и web-аудит берут правила NDA из данных пространств (SECF-01, SECF-02, D-12, D-18)

Файл целиком передаётся `/gsd-quick` в сессии, открытой в `/opt/chat-app`. Сам план 02-07 репозиторий chat-app не меняет: он пишет это задание и проверяет его на копии библиотеки. Правку выполняет оркестратор через `/gsd-quick` (чекпоинт Task 3 плана 02-07). Однотипный перевод четырёх и более тестовых файлов допустимо отдать agy через `scripts/agy_task.sh` (CLAUDE.md §5); логика безопасности (`security.py`, делегатор) остаётся за Claude.

## 1. Заголовок и контекст

**Слова NDA других пространств ищет и web-аудит; обёртка shield становится делегатором; тесты потребителя больше не читают константу слов и не полагаются на имя каталога (SECF-01, SECF-02, D-12, D-18).**

Библиотека `/opt/assistant-shared` общая и установлена editable в venv обоих репозиториев: любое удаление имени в ней действует на chat-app мгновенно. Фаза 2 проекта assistant-core убирает из библиотеки константу слов NDA (`CORPORATE_NDA_KEYWORDS`), литерал личного аккаунта и режим NDA по подстроке имени каталога. Правило NDA теперь определяют ДАННЫЕ рабочих пространств персоны (`workspaces`: путь, remote, `forbidden_remote_substrings`, `forbidden_keywords`, `clearance`).

Что нужно от chat-app:

- SECF-02: web-аудит (`/api/v1/security/overview` и `/api/v1/security/audit`) обязан находить слова NDA других пространств в каталогах НЕ-NDA пространств. Сейчас он вызывает `audit_path` по одному пространству и слов не передаёт.
- SECF-01: обёртка `scripts/security_shield.py` не должна импортировать удаляемую константу; тесты не должны ссылаться на удаляемые имена.
- D-12 (уточнён исследованием): правка chat-app НУЖНА и делается только малой задачей `/gsd-quick` здесь, не из assistant-core. D-18: общую обёртку shield держит assistant-core, chat-app делегирует ей.

## 2. Текущее поведение

- `backend/app/api/v1/security.py`: функции `get_security_overview` и `run_security_audit` вызывают `audit_path(p_path, nda_rule=nda_rule_for(p))` для каждого пространства. Для публичного пространства `nda_rule_for` возвращает `None`, параметр `forbidden_keywords` не передаётся, поэтому слова NDA других пространств до публичного каталога не доходят. Слова доходят только через `collect_protected_keywords(workspaces)` в двух вызовах.
- `scripts/security_shield.py`: самостоятельная обёртка, которая импортирует из библиотеки `audit_repository` и `CORPORATE_NDA_KEYWORDS` и реэкспортирует их через `__all__`; запасной путь добавляет `/opt/assistant-shared` в `sys.path`.
- Тесты потребителя читают константу слов NDA (прямо или через обёртку) либо вызывают `audit_repository` без данных пространств и рассчитывают на режим NDA по подстроке имени каталога. Тест P03 сравнивает sha256 копий обёртки в двух репозиториях.
- Хук `.githooks/pre-commit` запускает `scripts/security_shield.py` с корнем репозитория аргументом; хук менять не нужно.

## 3. Требуемое поведение

### 3.1. `backend/app/api/v1/security.py`

- Импортировать `collect_protected_keywords` из `assistant_shared.security`.
- В `get_security_overview` и `run_security_audit` ОДИН раз на запрос вычислить `protected = collect_protected_keywords(workspaces)` по ВСЕМ пространствам персоны (в `run_security_audit` это значит по полному списку `workspaces`, а не по выбранному `target_projects`) и передать `forbidden_keywords=protected` в оба вызова `audit_path`.
- Ключи ответа и тексты ошибок (в том числе 503 без пространств и 404 для неизвестного проекта) не менять. Слова NDA в ответ не попадают: библиотека печатает только имя шаблона и файл.
- Вызов через `asyncio.to_thread` сохранить (тест `test_wr13_audit_runs_off_the_event_loop_thread` не должен краснеть; его подмена `audit_path` принимает произвольные аргументы, при необходимости привести сигнатуру подмены к `**kwargs`).

### 3.2. `scripts/security_shield.py` - тонкий делегатор

- Каталог assistant-core берётся из переменной окружения `ASSISTANT_CORE_DIR`, иначе `/opt/assistant-core`.
- Запускается интерпретатор `<каталог>/.venv/bin/python` с файлом `<каталог>/scripts/security_shield.py`.
- Все аргументы командной строки пробрасываются без изменений (`sys.argv[1:]`), код возврата наследуется, рабочий каталог, stdout и stderr не меняются (потомок наследует потоки; перехватывать и пересобирать вывод не нужно).
- Fail-closed: если каталог, обёртка в нём или интерпретатор отсутствуют, вывести в stderr строку «❌ SECURITY SHIELD ERROR: <причина по-русски>» и завершиться кодом 1. Молчаливого прохода нет.
- В файле НЕТ импортов `assistant_shared`, нет реэкспорта `audit_repository`, нет констант слов NDA. Запасной путь через `sys.path` удалить вместе со всем остальным.
- Зависимость chat-app от каталога assistant-core разрешена решением владельца D-18. Подмена `ASSISTANT_CORE_DIR` окружением принимается как доверенная (так же, как `PERSONA_CONFIG_PATH`); поведение зафиксировать в docstring.
- Рекомендуемая реализация: `os.execv` либо `subprocess.run(..., check=False)` и `sys.exit(returncode)`; выбрать то, что проще проверить тестом, и сохранить код возврата 2 при неизвестном флаге (argparse в обёртке assistant-core).

## Предпроверка

Предпроверка выполнена планом 02-07 ДО этой правки и не меняла настоящие репозитории. Копия библиотеки `/var/tmp/gsd-phase02-precheck/shared-final` смоделировала ИТОГОВОЕ состояние библиотеки после плана 02-10: константа слов NDA и её экспорт удалены, `check_file_content` и `check_index_content` при `custom_keywords=None` ищут «слов нет», прежняя ветка `audit_repository` и приватный маркер умолчания удалены, у `audit_repository` умолчание `workspaces=None` (rc=1, D-20).

Полный `backend/tests` chat-app прогнан из `/opt/chat-app` с `PYTHONPATH=/var/tmp/gsd-phase02-precheck/shared-final` (результат в `/var/tmp/gsd-phase02-precheck/before.txt`; из-за ошибки сбора модуля пришлось добавить `--continue-on-collection-errors`, иначе pytest прерывается на первом модуле):

- итог: **19 упало, 226 прошло, 1 ошибка сбора модуля** (`19 failed, 226 passed, 3 warnings, 1 error`);
- ошибка сбора: `test_security_shared.py` (импорт удалённой константы);
- файлы упавших тестов (`/var/tmp/gsd-phase02-precheck/failed-files.txt`):
  - `test_nda_equivalence.py` - 5 тестов (S01-S05)
  - `test_persona_api.py` - 1 тест
  - `test_pre_commit_hook.py` - 5 тестов
  - `test_security_shared.py` - ошибка сбора
  - `test_shield_parity.py` - 1 тест
  - `test_shield_regressions.py` - 6 тестов
  - `test_synthetic_persona.py` - 1 тест

Причины по группам:

1. Импорт или чтение удалённой константы (через обёртку или напрямую): `test_security_shared.py`, `test_nda_equivalence.py::test_s04`, `test_s05`, `test_persona_api.py`, `test_synthetic_persona.py`.
2. Вызов `audit_repository` без `workspaces=` теперь даёт rc=1 «данные рабочих пространств недоступны» (D-20): `test_shield_parity.py`, `test_shield_regressions.py` (CR-01 два теста, CR-03 два теста, CR-05 CLI), `test_nda_equivalence.py::test_s01`-`test_s03`.
3. Запуск обёртки как подпроцесса, которая падает на импорте удалённой константы: `test_pre_commit_hook.py` (пять тестов), `test_shield_regressions.py::test_cr02_flag_first_is_not_treated_as_path`.

Тесты, которые против копии проходят по правильной причине (`test_cr01_git_failure_is_fail_closed` и последняя проверка `test_cr02_unknown_flag_and_missing_path_fail`: проверка «не git-репозиторий» стоит в библиотеке раньше проверки данных пространств), тоже получают явный `workspaces=()` для единообразия вызовов.

## 4. Итоговый контракт библиотеки (на что можно опираться)

- `audit_repository(path, check_staged_only, *, workspaces)` - `workspaces` только именованный; `None` даёт rc=1 без сканирования, `()` означает «пространств нет» (репозиторий проверяется как публичный с предупреждением), кортеж словарей - данные пространств.
- `check_file_content(path, is_public_repo, custom_keywords)` - слова задаются списком; `custom_keywords=None` означает «слов нет».
- `audit_path(path, nda_rule, is_public_repo, max_files, forbidden_keywords)` - слова ищутся только в НЕ-NDA каталоге (`nda_rule is None`) и только при `is_public_repo`.
- `collect_protected_keywords(workspaces)`, `nda_rule_for(ws)`, `match_workspace(repo_path, remote_urls, workspaces)`, `scan_file_content(rel_path, text, *, keywords)`.
- Сопоставление репозитория с пространством идёт по реальному пути (`resolve()`, сам путь или вложенный) и по нормализованному remote, равному полю `remote` пространства; при нескольких кандидатах побеждает строжайший допуск. Имя каталога режим NDA не включает и не выключает. В тестовых данных пространств полю `remote` давать синтетическое значение `https://git.example.org/ws/data.git`, чтобы случайное совпадение по remote не меняло результат.
- Параметров допуска вхождений слов в API нет и не будет (решение владельца D-21: shield не ослабляется ни для одного файла); код и тесты chat-app таких параметров не ожидают.
- Константа слов NDA и прежняя ветка по подстроке пути УДАЛЯЮТСЯ планом 02-10 (до тех пор остаются). Код и тесты chat-app не должны ссылаться на удаляемые имена. Слов по умолчанию в `check_file_content` в итоговом состоянии нет.

Подробности перевода тестов, по файлам из списка предпроверки:

- `test_security_shared.py`: убрать `CORPORATE_NDA_KEYWORDS` из импорта (иначе остаётся ошибка сбора). Тест `test_check_file_content_corporate_keywords` брать слово из данных: `_owner_nda_workspace()["forbidden_keywords"][0]` (хелпер лежит в `test_nda_equivalence.py`; вынести в общий модуль тестов, например `backend/tests/nda_helpers.py`, или продублировать чтение из копии БД), передавать `custom_keywords=[слово]`; в публичном режиме ожидается одно нарушение, в NDA-режиме (`is_public_repo=False`) ноль.
- `test_nda_equivalence.py`: `_load_shield()` возвращает модуль библиотеки; S01-S03 передают `workspaces=` явно. S01 (режим NDA определяется данными): пространство - копия `_owner_nda_workspace()` с `path` во временном каталоге (`tmp_path / "ws-a"`) и синтетическим `remote`; репозиторий внутри этого пути с запрещённым remote даёт rc=1 и в выводе «RESTRICTED» и «CRITICAL»; репозиторий вне пути даёт rc=0 и «PUBLIC». Имена каталогов в тестах нейтральные (`ws-a`, `plain`), не несущие смысла: имя режим больше не определяет. S02: репозиторий внутри пути NDA-пространства с запрещённым remote - rc=1 и «CRITICAL». S03: репозиторий вне путей пространств с тем же remote - rc=0. S04/S05: слова брать из данных пространства (`forbidden_keywords`), передавать `custom_keywords=` в `check_file_content`; S04 в публичном режиме ждёт по одному нарушению на слово, S05 в NDA-режиме ноль. Тест P03 (равенство sha256 копий) заменить тестом делегирования (см. 3.3). Docstring модуля о «известном расхождении» (web не проверял слова NDA) привести в соответствие: расхождение закрыто, оба пути ищут слова NDA других пространств.
- `test_persona_api.py`: функцию `_shield_nda_words()` заменить чтением `forbidden_keywords` у пространств персоны из `DatabaseService.list_workspaces(settings.PERSONA_ID)` (без запуска обёртки); смысл теста не ослаблять: `nda_words` непусты, в ответ `/api/v1/persona/current` они не попадают.
- `test_synthetic_persona.py`: `test_no_real_nda_keywords` брать слова из данных пространства персоны по умолчанию (копия БД, `forbidden_keywords`) вместо обёртки; проверка «ни одна строка синтетической персоны не содержит реальных слов» остаётся. Функция `_load_shield()` в этом файле больше не нужна.
- `test_shield_regressions.py`: все вызовы `audit_repository(...)` получают `workspaces=` явно (пустое значение допустимо: `workspaces=()`). `test_cr05_cli_checks_all_remotes_and_aliases` описывает NDA-репозиторий по имени каталога: перевести на пространство из данных (`{**_owner_nda_workspace(), "path": str(nda_root)}` с `forbidden_remote_substrings` из данных; `nda_root` во временном каталоге) и заменить литерал запрещённого remote на `https://` + подстрока из `_owner_nda_workspace()["forbidden_remote_substrings"][0]`, чтобы литерал аккаунта в файле не хранился. `test_cr02_flag_first_is_not_treated_as_path` запускает обёртку подпроцессом и после перевода идёт через делегатор.
- `test_shield_parity.py`: `audit_repository(repo, check_staged_only=False, workspaces=())`; ожидание паритета с web-аудитом не менять.
- `test_pre_commit_hook.py`: изменений в самих тестах, как правило, не нужно: тесты копируют `scripts/security_shield.py` (теперь делегатор) в временный репозиторий, а делегатор находит assistant-core по умолчанию; проверить, что пять тестов зелёные против НАСТОЯЩЕЙ библиотеки.

### 3.3. Новые тесты

- Web-эндпоинт `/api/v1/security/audit` (ASGI-клиент `ASGITransport`, как в соседних тестах `test_persona_api.py` и `test_nda_equivalence.py`): подменить `DatabaseService.list_workspaces` синтетическим набором из двух пространств с каталогами во временной папке - публичное (`clearance: public`, без слов) и NDA (`clearance: restricted_nda`, `forbidden_keywords` из данных копии БД, `forbidden_remote_substrings` синтетическое значение с `example.org`). В каталог публичного пространства положить tracked-файл со словом NDA (слово собрать в рантайме из данных, не писать литералом); ответ содержит нарушение для публичного пространства и НЕ содержит его для NDA-пространства. Булевы проверки, без печати слов в сообщения assert. Дополнительно: запрос с `project_id` публичного пространства всё равно ищет слова, взятые по ВСЕМ пространствам (а не только выбранному).
- Тест делегирования (замена P03): (а) файл `scripts/security_shield.py` не содержит текста `assistant_shared`; (б) сквозной запуск `sys.executable scripts/security_shield.py --all <временный git-репозиторий>` даёт rc=1 при секрете (строку собрать из частей) и rc=0 при чистом содержимом; (в) с `ASSISTANT_CORE_DIR`, указывающим на несуществующий каталог, код возврата 1 и в stderr «SECURITY SHIELD ERROR» (fail-closed); (г) с `ASSISTANT_CORE_DIR` на каталог без `.venv/bin/python` код возврата 1. Тест не пропускается при наличии assistant-core (никаких `skip`/`xfail`).

## 5. Файлы для изменения

- `backend/app/api/v1/security.py`
- `scripts/security_shield.py` (делегатор)
- `backend/tests/test_nda_equivalence.py`
- `backend/tests/test_security_shared.py`
- `backend/tests/test_shield_regressions.py`
- `backend/tests/test_shield_parity.py`
- `backend/tests/test_persona_api.py`
- `backend/tests/test_synthetic_persona.py`
- `backend/tests/test_pre_commit_hook.py` (только если после проверки потребуется)
- новый общий модуль тестовых хелперов (по желанию) и новый файл тестов web-аудита слов NDA и делегирования

Файлы вне списка не менять.

## 6. Ограничения (обязательные)

- `scripts/gate.py` chat-app НЕ менять (D-15): гейт chat-app остаётся гейтом потребителя.
- Защиты и тесты потребителя не ослаблять и не удалять без замены; число тестов в итоге не должно уменьшиться (допустимо равенство при замене P03 тестом делегирования; записать число до и после).
- Пропусков (`skip`), `xfail`, `deselected` не вводить; тест делегирования не пропускается при наличии assistant-core.
- Новых зависимостей не добавлять.
- Сервис `chat-app.service` не перезапускать (заморожен, решение владельца).
- Секреты, слова NDA, личные литералы аккаунтов и адреса правил remote в тексты кода, тестов и сообщения коммита не вставлять. Синтетические значения только на `example.org`; слова собирать в рантайме из данных или из частей.
- Живую БД assistant-core не открывать; тесты chat-app работают с копией БД, как сейчас.

## 7. Проверка перед коммитом

1. Полный `cd /opt/chat-app && backend/.venv/bin/pytest backend/tests -p no:cacheprovider -q` зелёный против НАСТОЯЩЕЙ библиотеки (с текущим состоянием: аддитивные имена уже есть, прежняя константа ещё есть).
2. Тот же полный набор зелёный против копии итогового состояния: `PYTHONPATH=/var/tmp/gsd-phase02-precheck/shared-final backend/.venv/bin/pytest backend/tests -p no:cacheprovider -q` ПОСЛЕ правок, с ОДНИМ допустимым исключением, которое нужно перечислить в ответе по имени: тесты, запускающие обёртку assistant-core через делегатор (пять тестов `test_pre_commit_hook.py`, `test_cr02_flag_first_is_not_treated_as_path`, сквозная часть теста делегирования) могут краснеть против копии, пока в assistant-core не заменена обёртка (план 02-08). Любое другое падение против копии - дефект правки.
3. `cd /opt/chat-app && python3 scripts/gate.py` даёт «ИТОГ: ЗЕЛЁНЫЙ».
4. `grep -c "assistant_shared" scripts/security_shield.py` равно 0; `git diff --stat` не содержит `scripts/gate.py`.
5. Дерево чистое после коммита, кроме файла `.watchdog_disabled`, который лежит в chat-app до начала работ и правкой не создаётся и не удаляется.

## 8. Коммит

Атомарный, через `/gsd-quick`, прямо в `main` chat-app. Сообщение вида: `fix(security): shield rules come from workspace data, web audit checks NDA keywords (SECF-01, SECF-02)`.

## 9. Что вернуть

- хеш коммита chat-app;
- строки итогов полного pytest против настоящей библиотеки и против копии (с перечнем исключения из раздела 7, пункт 2); число тестов до и после правки;
- итог общего гейта chat-app;
- подтверждение, что `chat-app.service` не перезапускался;
- если при выполнении обнаружится отклонение от описанного (например, дополнительный упавший тест, не попавший в раздел «Предпроверка»), остановиться и задать вопрос владельцу опросом (AskUserQuestion), решение приложить к ответу.

## Известное последствие

После рестарта `chat-app.service` (он заморожен и этой правкой не перезапускается) web-аудит публичного пространства assistant-core покажет находки по слову NDA в `config/persona.yaml`: файл объявляет слова и лежит в публичном репозитории. Это верная находка о публичном репозитории, а не дефект правки; решение (убрать слова из публичного репозитория) относится к Phase 8.

Решение владельца D-21 это последствие не меняет и не усиливает: допуска слов для файла персоны нет ни в web, ни в CLI; hook и shield не ослаблены; три известные находки режима `--all` остаются, замороженные списки обоих гейтов (гейт chat-app не меняется, D-15 Phase 1) остаются верными и не растут. Коммиты `config/persona.yaml` в фазе проходят разовым обходом хука по согласию владельца (план 02-11).
