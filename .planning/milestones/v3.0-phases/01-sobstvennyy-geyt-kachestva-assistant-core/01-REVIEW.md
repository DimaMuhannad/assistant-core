---
phase: 01-sobstvennyy-geyt-kachestva-assistant-core
reviewed: 2026-10-09T22:45:00Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - scripts/gate.py
  - scripts/deploy.py
  - tests/live_db_guard.py
  - tests/conftest.py
  - src/config.py
  - src/connectors/gdrive/client.py
  - tests/test_gate.py
  - tests/test_gate_red_cases.py
  - tests/test_deploy_script.py
  - tests/test_live_db_guard.py
  - tests/test_gdrive_client.py
  - tests/test_command_aliases.py
  - tests/test_claude_md_gate_pointer.py
  - /opt/assistant-shared/.githooks/pre-commit
  - /opt/assistant-shared/scripts/install_hooks.sh
  - /opt/assistant-shared/scripts/security_shield.py
  - /opt/chat-app/scripts/agy_cross_ai.sh
findings:
  critical: 1
  warning: 13
  info: 6
  total: 20
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-10-09T22:45:00Z
**Depth:** standard
**Files Reviewed:** 17
**Status:** issues_found

## Summary

Просмотрены гейт качества (`scripts/gate.py`), скрипт выкатки (`scripts/deploy.py`), страж боевой БД, изменения `src/config.py` и `gdrive/client.py`, тесты к ним, хук и установщик в assistant-shared и изменённые хунки адаптера `agy_cross_ai.sh` (`git -C /opt/chat-app diff 279dc5a 6b3b2ac`).

Для evidence прогнан pytest по 7 тестовым файлам из области проверки: 386 passed, 0 skipped. Отдельно проверено на временной WAL-БД со схемой из миграций (включая FTS5): `db_content_hash` стабилен между вызовами и не ломается на виртуальных таблицах.

Сам каркас гейта сделан аккуратно (fail-closed на пустом наборе, skipped/xfail/deselected, нормализация вывода shield без утечки NDA-слов). Главные замечания такие:

- в `gdrive/client.py` есть реальная path traversal при записи файла на диск от root (код не новый, но файл входит в область);
- два смягчения гейта (повторный замер хеша БД, замороженный список shield по счётчику) снижают его способность обнаружить именно то, для чего они сделаны;
- защита адаптера `agy_cross_ai.sh` («гейту цели можно доверять, потому что `scripts/gate.py` в PROTECTED») неполна: гейт исполняет код, который патч менять может;
- в `deploy.py` есть паттерны записи от root в предсказуемый путь с переходом по symlink и `chmod` чужого каталога;
- ряд тестов недетерминирован или слаб.

Структурных находок (fallow) не передавалось. Внешних отчётов (`external_reviewer_evidence`) нет.

## Critical Issues

### CR-01: Path traversal при записи скачанного файла Google Drive (запись от root за пределы uploads)

**File:** `src/connectors/gdrive/client.py:256-262` (источник имени), `src/connectors/gdrive/client.py:118-135` (запись)
**Issue:** `sync_aadhk_from_drive` берёт `remote_name = backup_file["name"]` из ответа Drive и строит `Path(f"/opt/chat-app/uploads/gdrive_{remote_name}")`. Имя файла на Drive может содержать `/` и `..`. Префикс `gdrive_` приклеивается только к первому компоненту, а `download_file` делает `dest.parent.mkdir(parents=True)` и пишет файл. Проверено на временном каталоге: имя `aadhk/../../../../escaped/evil.db` создаёт `uploads/gdrive_aadhk`, а сам файл записывается на четыре уровня выше `uploads` (`escaped/evil.db`). Демон работает от root, так что можно записать файл в любое место (cron, systemd, `.githooks`, `src/`). Поиск `find_latest_aadhk_backup` идёт по всему Drive по подстроке имени (`aadhk`, `timetracker`, `.db`) и самым свежим `modifiedTime`, поэтому файл, которым с владельцем поделились, подходит под запрос. Содержимое затем разбирается как SQLite (`ingest_backup_file`). Код не появился в этой фазе, но файл входит в область проверки, а тест на `core_dir` его не покрывает.
**Fix:**
```python
UPLOADS_DIR = Path("/opt/chat-app/uploads")

safe_name = Path(remote_name).name  # только последний компонент, без / и ..
if not safe_name or safe_name in {".", ".."}:
    raise ValueError("недопустимое имя файла на Google Drive")
local_dest = (UPLOADS_DIR / f"gdrive_{safe_name}").resolve()
if UPLOADS_DIR.resolve() not in local_dest.parents:
    raise ValueError("путь загрузки вышел за пределы каталога uploads")
```
Лучше скачивать во временный каталог (`tempfile.TemporaryDirectory`) с фиксированным именем. Добавить тест с именем `../../x.db`.

## Warnings

### WR-01: Блокирующий сетевой и файловый ввод-вывод внутри async-методов (замораживает event loop демона)

**File:** `src/connectors/gdrive/client.py:224-262` (вызовы: `src/main.py:243`, `src/notifier/bot_handler.py:815,1771`)
**Issue:** `sync_aadhk_from_drive` и `backup_server_data_to_drive` объявлены `async`, но целиком синхронно вызывают `get_service`, `creds.refresh`, `files().list().execute()`, `MediaIoBaseDownload.next_chunk`, `upload_file`, `tarfile`. Демон работает на одном event loop (`.claude/CLAUDE.md`: heavy sync work must be offloaded; CLAUDE.md: async-first). Пока идёт скачивание и обновление токена, Telegram-бот и все APScheduler-задачи стоят.
**Fix:** `backup_file = await asyncio.to_thread(self.find_latest_aadhk_backup)`, `await asyncio.to_thread(self.download_file, file_id, local_dest)`, то же для `upload_file` и `create_server_backup_archive`.

### WR-02: Архив «серверного бэкапа» несогласован, небезопасен по правам и не используется

**File:** `src/connectors/gdrive/client.py:184-222`, `224-245`
**Issue:**
1. `tar.add` копирует основной файл `assistant.db` без `-wal`. БД работает в WAL (`assistant_shared/db/connection.py`), поэтому архив — это устаревший или несогласованный снимок. Для того же случая в `deploy.py` корректно использован sqlite3 backup API.
2. В архив кладутся `.env` (все ключи и пароли) и Telegram-сессия, файл создаётся с umask по умолчанию (обычно 0644) в `/opt/chat-app/uploads` — каталоге веб-сервиса chat-app, и потом уходит на Google Drive.
3. Параметр `include_uploads` не используется (мёртвый), метод `backup_server_data_to_drive` нигде не вызывается (`grep` по `src`, `scripts`).
**Fix:** если функция нужна, делать копию БД через `sqlite3.Connection.backup` во временный файл, создавать архив через `os.open(..., 0o600)` в приватном каталоге вне `uploads`, не включать `.env` по умолчанию. Если не нужна — удалить вместе с тестами.

### WR-03: Смягчение проверки «боевая БД не изменена» почти полностью отключает её

**File:** `scripts/gate.py:481-561`
**Issue:** условие «согласуется с записью сервиса» (`service_write_evidence`) — это «сервис active и mtime БД или `-wal` внутри окна прогона». Сервис работает 24/7 и пишет в БД постоянно, а любая запись (в том числе ошибочная запись теста) обновляет mtime внутри окна. Затем `quiet_remeasure` сравнивает два замера друг с другом, а не с `before`, то есть тест, который изменил БД, а потом наступила тишина на 5 с, проходит как зелёный. Различить запись сервиса и запись теста нельзя. Фактически строка краснеет только при неактивном сервисе или при записи в течение самой паузы. Решение владельца 2026-10-09 здесь понятно, но в `info` стоит честная пометка о том, что вердикт держится только на страже `tests/live_db_guard.py`, а страж (см. WR-07) закрывает не все пути.
**Fix:** усилить различение. Например, сравнивать не весь хеш, а набор таблиц, в которые пишет только тест (по дампу до/после выбрать «диффом» таблицы и сверить со списком таблиц, которые пишет сервис), либо фиксировать счётчик `PRAGMA data_version`/число строк в таблицах, не обновляемых сервисом. Минимум: записывать в `info` и в таблицу итогов, что сработало смягчение (это уже сделано), и считать красной строку при ≥2 срабатываниях подряд.

### WR-04: Замороженный список ложных срабатываний shield позволяет подменить находку

**File:** `scripts/gate.py:55-65`, `362-376`
**Issue:** ключ списка — `(путь, вид)` и счётчик. Текст найденного слова и номера строк намеренно не сравниваются (T-01-09). Значит, три «ложных» NDA-срабатывания в `config/persona.yaml` можно заменить тремя настоящими утечками (или перенести утечку на место одного из ложных), и гейт останется зелёным. Для шифрованного по смыслу правила «безопасность только ужесточается» это дыра: исключение держится на счётчике, а не на конкретной строке.
**Fix:** хранить в замороженном списке не только счётчик, но и стабильный отпечаток находки: `sha256(путь + "\0" + строка файла)` для каждой разрешённой строки (хеш в репозитории не раскрывает слово), и сравнивать отпечатки. Для этого `parse_shield_findings` нужно получать номер строки и читать строку из файла (в самом гейте, без печати).

### WR-05: Защита адаптера агента неполна: гейт цели исполняет код, который патч менять может

**File:** `/opt/chat-app/scripts/agy_cross_ai.sh:22-26` (комментарий), `82-83` (`PROTECTED`), `312-319` (выбор гейта)
**Issue:** новое правило «берём `scripts/gate.py` цели, ему можно доверять, потому что он в `PROTECTED`» верно только для самого файла. Гейт после применения патча запускает `tests/` цели, `tests/conftest.py`, `tests/live_db_guard.py`, `pytest.ini` и `src/config.py`, а они в `PROTECTED` не входят. Патч агента может изменить `tests/live_db_guard.py` (отключить стража боевой БД), `tests/conftest.py` (хук `pytest_collection_modifyitems` убирает тесты без события `deselected`, `pytest_sessionfinish` меняет код возврата), `pytest.ini` (`--ignore`, `-p`), `src/config.py` (путь БД). Строка гейта «боевая БД не изменена» после WR-03 уже слабая. Тесты также исполняются от root вне jail агента.
**Fix:** расширить `PROTECTED` для репозиториев с собственным гейтом: `tests/conftest.py`, `tests/live_db_guard.py`, `pytest.ini`, `scripts/deploy.py`, `src/config.py`, `requirements*.txt`; либо запускать гейт на патче только после ручного осмотра diff. Обновить комментарий («trusted» относится только к самому файлу гейта).

### WR-06: Для репозитория без своего гейта адаптер молча запускает гейт chat-app и сообщает «гейт цели зелёный»

**File:** `/opt/chat-app/scripts/agy_cross_ai.sh:312-319`, `383`
**Issue:** при отсутствии `scripts/gate.py` у цели выполняется `python3 $SCRIPT_DIR/gate.py` в chat-app, то есть проверяется chat-app, а не изменённая цель. Итог в отчёте всегда формулируется как «Гейт качества целевого репозитория завершился с кодом 0» — это неверно для ветки (3) и воспроизводит именно ту «ложную зелень от чужого набора проверок», против которой направлен `test_claude_md_gate_pointer.py`.
**Fix:** для ветки (3) завершать с отдельным кодом («у цели нет гейта») либо формулировать отчёт по ветке: `GATE_KIND=target|adapter-own|test`, и в отчёте писать «ВНИМАНИЕ: гейт chat-app, цель им не проверена».

### WR-07: Страж боевой БД не закрывает часть путей

**File:** `tests/live_db_guard.py:19-25`, `62-67`
**Issue:**
1. `CORE_DIR` вычисляется от расположения файла. Если тесты запущены из другого checkout (копия, worktree, jail), страж охраняет `<checkout>/data/assistant.db`, а боевую `/opt/assistant-core/data/assistant.db` — нет. Код с абсолютным путём (например, `create_server_backup_archive(core_dir="/opt/assistant-core")` по умолчанию, `src/persona/seed.py:LIVE_DB_PATH` относительно файла) тогда достанет боевую БД.
2. Префильтр `text.endswith(_BASENAMES)` пропускает любой путь с другим именем: симлинк `x.db -> .../data/assistant.db` не блокируется, хотя `realpath` его разрешил бы.
3. `Database()` по умолчанию использует относительный `./data/assistant.db` (`src/storage/db.py:24`), то есть изоляция через `config.SQLITE_DB_PATH` его не охватывает, держится только на стороже.
**Fix:** добавить в `LIVE_DB_PATHS` абсолютный `Path("/opt/assistant-core/data/assistant.db")` (и обновить `test_live_db_paths_constant_lists_both_live_files`); для префильтра использовать `os.path.realpath` для любых путей с `assistant`, либо сравнивать `os.path.samefile` по inode боевых файлов, когда они существуют.

### WR-08: `deploy.py` пишет от root в предсказуемый путь в `/var/tmp` с переходом по symlink

**File:** `scripts/deploy.py:55`, `596-614`, `1203`, `752-760`
**Issue:** `_write_private` открывает файл через `os.open(path, O_WRONLY|O_CREAT|O_TRUNC, 0o600)` без `O_NOFOLLOW`, затем делает `os.fchmod`. Путь состояния по умолчанию — `/var/tmp/assistant-core-smoke-state.json` в каталоге со sticky-битом, доступном всем. Любой локальный пользователь может заранее поставить symlink на нужный файл, после чего root обнулит и перепишет его и сузит права до 0600. `--report PATH` аналогично усекает любой существующий файл (`validate_report_path` запрещает лишь `.git` и каталог). Сейчас на VPS нет непривилегированных учётных записей и все сервисы под root, поэтому это hardening, но состояние смоука ещё и определяет вердикт `final_verdict` (его можно подделать, подложив файл).
**Fix:** `os.O_NOFOLLOW | os.O_CREAT | os.O_EXCL` с записью во временный файл и `os.replace`; путь состояния по умолчанию перенести в `/var/lib/assistant-core/` (создаётся с 0700); в `validate_report_path` отказывать, если путь существует и это не обычный файл или symlink.

### WR-09: `make_db_copy` меняет права произвольного существующего каталога и проверяет только «внутри core»

**File:** `scripts/deploy.py:937-955`
**Issue:**
1. `os.chmod(target_dir, 0o700)` выполняется всегда. Для `--backup-dir /var/backups` или `/srv/data` это молча меняет права на существующем общем каталоге (docstring допускает «выделенный каталог», но код этого не проверяет).
2. `BackupPathError` ("внутри дерева git") проверяет только `CORE_DIR`; `--backup-dir /opt/chat-app/uploads` или `/opt/assistant-shared/x` проходит, и полная копия боевой БД ложится в рабочее дерево другого репозитория.
**Fix:** применять `chmod` только к каталогу, созданному этим вызовом, а к существующему — отказ, если его владелец или права не соответствуют (`st_mode & 0o077`); для проверки «внутри git» подниматься по родителям и искать `.git` (или вызывать `git rev-parse --show-toplevel` с `cwd=target_dir`).

### WR-10: Тесты `db_unchanged_check` недетерминированы: запускают реальный `systemctl` и делают `stat` боевой БД

**File:** `tests/test_gate.py:1327-1355` (`test_db_retry_not_attempted_without_window`, `test_db_retry_none_in_quiet_remeasure_is_red`, `test_db_retry_not_attempted_when_service_not_active_or_mtime_outside_window`, `test_db_retry_crash_in_remeasure_or_evidence_is_red`)
**Issue:** эти тесты не передают `diagnostics_fn`, и красная ветка вызывает настоящую `_db_diagnostics()`: реальный подпроцесс `systemctl is-active assistant-worker` и `LIVE_DB.stat()` (docstring модуля обещает, что тесты не трогают боевую БД; `stat` страж не блокирует, но это всё равно обращение к боевому файлу). Результат зависит от окружения (нет systemctl, права). Фикстуру нужно сделать герметичной.
**Fix:** autouse-фикстура в модуле: `monkeypatch.setattr(gate, "_db_diagnostics", lambda: "диагностика")` и `monkeypatch.setattr(gate, "_service_state", lambda: "inactive")`.

### WR-11: Тест `test_menu_command_rendering` ничего не проверяет про «отрисовку меню»

**File:** `tests/test_command_aliases.py:92-110`
**Issue:** переменная `catalog = registry._build_default_catalog(...)` вычисляется и нигде не используется, утверждения касаются только записи в БД (`get_command_settings`, `get_custom_aliases`). Название и docstring обещают проверку форматирования меню, которой нет, тест проходит при любом содержимом каталога.
**Fix:** добавить `assert any(c.command == "lms" for c in catalog)` и проверку, что скрытая команда помечена в тексте меню (или переименовать тест).

### WR-12: Тест Drive проходит через ветку «папка», а не через общий поиск; пути `download`/`sync` не покрыты

**File:** `tests/test_gdrive_client.py:82-119`
**Issue:** один и тот же `mock_service.files().list().execute.return_value` отдаёт и «папку», и «файлы». `find_latest_aadhk_backup` возвращает `folder_files[0]` из ветки «папка com.aadhk.time», а четыре запроса общего поиска не выполняются; проверка `"aadhk" in latest_file["name"]` проходит случайно. Ни `download_file`, ни `sync_aadhk_from_drive` (с CR-01) не тестируются.
**Fix:** использовать `side_effect` с разными ответами для запроса папки и файлов; добавить тест на `sync_aadhk_from_drive` с враждебным именем файла.

### WR-13: Защитный тест на «возврат к чужому гейту» ловит только точную строку

**File:** `tests/test_claude_md_gate_pointer.py:16-34`
**Issue:** `LEGACY_GATE_COMMAND = "python3 /opt/chat-app/scripts/gate.py"` ищется как подстрока. Варианты `python /opt/chat-app/scripts/gate.py`, `cd /opt/chat-app && python3 scripts/gate.py` или команда с флагами обходят тест; к тому же третий тест требует буквальных фраз `explicit owner permission`, `docs/OPS_DEPLOY.md`, что делает его хрупким к редактуре текста.
**Fix:** искать регулярным выражением `chat-app/(scripts/)?gate\.py` (ссылка на гейт chat-app в правилах недопустима при любом способе запуска).

## Info

### IN-01: `ASSISTANT_DB_PATH_OVERRIDE` в боевом рантайме не логируется и не нормализуется

**File:** `src/config.py:9`, `22-24`
**Issue:** переменная, случайно попавшая в окружение systemd, молча перенаправит демон на другую БД (миграции создадут пустую, сервис «здоров», но без данных). Относительный путь не привязывается к `BASE_DIR`, в отличие от `DATABASE_URL`.
**Fix:** `logging.getLogger(__name__).warning("DB path overridden: %s", ...)` при непустом значении и `os.path.abspath` для нормализации.

### IN-02: `os.environ.setdefault` не заменяет пустую строку

**File:** `tests/conftest.py:22`
**Issue:** если окружение уже содержит `ASSISTANT_DB_PATH_OVERRIDE=""`, `setdefault` оставит пустое значение, `config.py` посчитает его «не задано» и пойдёт по `DATABASE_URL` из `.env`, то есть к боевому пути (спасает только страж, весь набор тестов упадёт).
**Fix:** `if not os.environ.get("ASSISTANT_DB_PATH_OVERRIDE"): os.environ[...] = ...`.

### IN-03: Мелочи в `deploy.py`

**File:** `scripts/deploy.py:184-187`, `1004`, `598-608`, `1405`, `301-346`
**Issue:**
- `ensure_read_only` для `journalctl` — чёрный список (`--rotate`, `--vacuum*`, `--flush`); не покрыты `--sync`, `--relinquish-var`, `--smart-relinquish-var`, `--setup-keys`, `--update-catalog`. Команды формируются только внутри скрипта, но слово «белый список» в docstring не соответствует действительности.
- `_poll_ready` не ловит `ValueError` от `read_invocation_journal` (неожиданный формат InvocationID): исключение вылетит из `restart_service` уже после рестарта и без отчёта об откате.
- В `_write_private` после выхода из `with` handle повторно вызывается `os.close(fd)`; возможен двойной close (закрытие чужого дескриптора).
- `--backup` без `--restart` молча игнорирует `--report`.
- Traceback, залогированный через `logger.exception`, считается дважды: как ERROR и как TRACEBACK.
- Резервные копии не ротируются; имя копии с точностью до секунды (`FileExistsError` при двух вызовах в одну секунду, сообщение в `_make_backup` скромное).
**Fix:** белый список флагов journalctl; `except (CommandError, ValueError)` в `_poll_ready`; `fdopen` вынести в отдельный try; предупреждать о неиспользуемом `--report`.

### IN-04: Неточности в `gate.py`

**File:** `scripts/gate.py:8-10`, `36`, `684`
**Issue:**
- Docstring «Гейт не читает .env…» верен для самого гейта, но дочерний pytest через `src.config` читает `.env` с `override=True` (реальные токены попадают в процесс тестов).
- `SHARED_DIR` из окружения не проходит через `.resolve()`; если задан symlink, shield печатает разрешённый путь, `_relative_posix` не сможет сократить его, и находки получат абсолютные ключи.
- Если боевой БД нет (чистая машина, клон), строка «хеш не вычислен» вечно красная: это fail-closed, но стоит зафиксировать в документации для запуска гейта вне VPS.
**Fix:** `SHARED_DIR = Path(os.environ.get(...)).resolve()`; уточнить docstring.

### IN-05: Хук и установщик assistant-shared зависят от пути assistant-core и проверяют не то, что исполняется

**File:** `/opt/assistant-shared/.githooks/pre-commit:8`, `/opt/assistant-shared/scripts/install_hooks.sh:20,29`
**Issue:** запасной интерпретатор жёстко прописан как `/opt/assistant-core/.venv/bin/python` (решение D-03, но shared становится нерабочим вне этого VPS). Установщик проверяет `python -c "import assistant_shared.security"`: `-c` кладёт текущий каталог в `sys.path`, поэтому из `/opt/assistant-shared` проверка проходит даже без установки пакета; тогда как хук запускает `scripts/security_shield.py`, где `sys.path[0]` — это `scripts/`, а при `ImportError` включается запасной путь, то есть реально хук работает, но проверка установщика ничего не доказывает.
**Fix:** в установщике использовать `python -I -c ...` либо запускать `security_shield.py --help` тем же способом, что и хук.

### IN-06: Мёртвые/слабые места `gdrive/client.py`

**File:** `src/connectors/gdrive/client.py:50`, `143`, `160-164`
**Issue:** `is_configured` проверяет подстроку `"drive"` (подойдёт `drive.readonly`, а загрузка потребует `drive`); `get_or_create_folder` подставляет `folder_name` в запрос Drive без экранирования `'`; параметр `include_uploads` не используется; `except Exception: pass` при удалении архива скрывает ошибку.
**Fix:** сравнивать со списком точных scope, экранировать `'` и `\` в `folder_name`, удалить `include_uploads`, писать `logger.warning` при сбое `unlink`.

---

_Reviewed: 2026-10-09T22:45:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
