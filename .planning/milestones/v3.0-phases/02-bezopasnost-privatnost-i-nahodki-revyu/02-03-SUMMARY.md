---
phase: 02-bezopasnost-privatnost-i-nahodki-revyu
plan: 03
subsystem: security
tags: [google-drive, path-traversal, asyncio, to-thread, cr-01, wr-01, wr-02, wr-12]

requires:
  - phase: 01-sobstvennyy-geyt-kachestva-assistant-core
    provides: "01-REVIEW.md с находками CR-01, WR-01, WR-02, WR-12; собственный гейт качества"
provides:
  - "src/connectors/gdrive/client.py: UPLOADS_DIR, _safe_upload_path (безопасный путь записи), to_thread-вызовы Drive в sync_aadhk_from_drive"
  - "Удалены create_server_backup_archive и backup_server_data_to_drive (архив .env и сессии Telegram)"
  - "tests/test_gdrive_client.py: 22 теста (враждебные имена, символьные ссылки, поток выполнения, ветки поиска, download_file, отсутствие архива)"
affects: [02-14, 02-15]

actuals:
  tokens: 5700
  tasks: 3
  commits: 3
plan_head_before: 318682e720518b9a9635c932efef0ad5d8ac1ea7
plan_head_after: f4ffdaaf77799580096e132fd3545762ef6f3554

tech-stack:
  added: []
  patterns:
    - "Недоверенное имя из внешнего ответа: отказ по разделителям и нулевому байту, whitelist символов, проверка родителя назначения после resolve()"
    - "Блокирующий Google API внутри async-метода: asyncio.to_thread, тест сравнивает идентификатор потока с потоком цикла"

key-files:
  created: []
  modified:
    - src/connectors/gdrive/client.py
    - tests/test_gdrive_client.py

key-decisions:
  - "Имя файла с Drive, содержащее «/», «\\» или нулевой байт, отвергается целиком, а не обрезается до последнего компонента: иначе «aadhk/../../../../escaped/evil.db» и «../../x.db» превратились бы в безопасное «evil.db» и «x.db», а must_have плана требует для них отказ (безопасность только ужесточается)"
  - "Назначение остаётся в /opt/chat-app/uploads с именем gdrive_<безопасное имя>; защита держится на проверке родителя после resolve() (символьная ссылка наружу даёт отказ)"
  - "create_server_backup_archive и backup_server_data_to_drive удалены, а не починены: нигде не вызывались, архивировали .env и сессию Telegram"

patterns-established:
  - "Тесты записи на диск подменяют UPLOADS_DIR через monkeypatch на каталог в tmp_path и сравнивают снимок дерева до и после"

requirements-completed: []

coverage:
  - id: D1
    description: "CR-01: враждебное имя файла с Drive не выводит запись за каталог загрузок; download_file не вызывается, ответ status=error с русским message"
    verification:
      - kind: integration
        ref: "tests/test_gdrive_client.py::test_sync_rejects_hostile_remote_names (7 имён), ::test_sync_rejects_symlink_pointing_outside_uploads (каталог и файл), ::test_sync_safe_name_is_downloaded_into_uploads, ::test_sync_replaces_unsafe_characters_in_remote_name"
        status: pass
    human_judgment: false
  - id: D2
    description: "WR-01: find_latest_aadhk_backup и download_file выполняются вне потока event loop"
    verification:
      - kind: unit
        ref: "tests/test_gdrive_client.py::test_sync_runs_blocking_drive_calls_off_event_loop (локальный откат to_thread: тест падает, 1 failed 23 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "WR-02: небезопасный серверный бэкап удалён, регрессия зафиксирована"
    verification:
      - kind: unit
        ref: "tests/test_gdrive_client.py::test_server_backup_archive_methods_are_removed (нет атрибутов, AST не импортирует tarfile)"
        status: pass
    human_judgment: false
  - id: D4
    description: "WR-12: тесты Drive различают ветки поиска и покрывают download_file"
    verification:
      - kind: unit
        ref: "tests/test_gdrive_client.py::test_find_backup_prefers_dedicated_folder, ::test_find_backup_general_search_when_no_folder, ::test_find_backup_general_search_when_folder_is_empty, ::test_find_backup_general_search_skips_folders, ::test_find_backup_returns_none_when_nothing_found, ::test_download_file_writes_collected_bytes, ::test_sync_returns_not_found_when_drive_has_no_backup"
        status: pass
    human_judgment: false
  - id: D5
    description: "Контракт и архитектура не нарушены, гейт зелёный"
    verification:
      - kind: integration
        ref: "tests/test_ports_conformance.py, tests/test_composition_di.py, tests/test_live_db_guard.py (104 passed вместе с gdrive); tests/test_architecture_contract.py (5 passed); python3 scripts/gate.py: ИТОГ ЗЕЛЁНЫЙ (854 + 145 тестов, SHA-256 боевой БД до и после совпали)"
        status: pass
    human_judgment: false

duration: 45min
completed: 2026-10-10
status: complete
---

# Phase 2 Plan 03: Безопасность клиента Google Drive Summary

**Закрыты CR-01 (path traversal при записи от root), WR-01 (блокирующий ввод-вывод в async), WR-02 (архив .env и сессии Telegram) и WR-12 (слабые тесты Drive): имя файла с Drive теперь проверяется до записи, вызовы Google API идут через asyncio.to_thread, опасный архив бэкапа удалён.**

## Находка -> изменение -> тест

| Находка | Изменение | Тест |
|---|---|---|
| CR-01 (T-02-07, T-02-10) | `UPLOADS_DIR` и `_safe_upload_path` в `client.py`: отказ для «/», «\\», нулевого байта, «», «.», «..»; whitelist `[\w.-]`, прочее заменяется на «_»; родитель назначения после `resolve()` равен `UPLOADS_DIR.resolve()`; `sync_aadhk_from_drive` при отказе возвращает `status=error` и русский `message`, `download_file` не вызывается | `test_sync_rejects_hostile_remote_names` (7 имён), `test_sync_rejects_symlink_pointing_outside_uploads` (ссылка на каталог и на файл вне загрузок), `test_sync_safe_name_is_downloaded_into_uploads`, `test_sync_replaces_unsafe_characters_in_remote_name` |
| WR-01 (T-02-08) | `await asyncio.to_thread(self.find_latest_aadhk_backup)` и `await asyncio.to_thread(self.download_file, ...)` | `test_sync_runs_blocking_drive_calls_off_event_loop` |
| WR-02 (T-02-09) | удалены `create_server_backup_archive`, `backup_server_data_to_drive` и импорты `os`, `tarfile`, `datetime`; три теста архива удалены | `test_server_backup_archive_methods_are_removed` |
| WR-12 | единый `return_value` заменён на `side_effect`; ветка папки `com.aadhk.time`, общий поиск, пустая папка, пропуск папок в выдаче, ничего не найдено, `download_file` через подмену `MediaIoBaseDownload`, `not_found` | `test_find_backup_*` (5), `test_download_file_writes_collected_bytes`, `test_sync_returns_not_found_when_drive_has_no_backup` |

## Предусловие Task 3

`git grep -n "create_server_backup_archive\|backup_server_data_to_drive" -- src scripts tests docs` нашёл упоминания только в `src/connectors/gdrive/client.py` и `tests/test_gdrive_client.py`. Условие выполнено, вызовов вне этих файлов нет; порт `src/core/ports/clients.py` удаляемых методов не требует.

## Accomplishments

- Запись скачанного с Drive файла за пределы каталога загрузок невозможна, в том числе через символьную ссылку; новых путей записи нет, один небезопасный путь удалён.
- Telegram-бот и планировщик не замораживаются сетевым вводом-выводом Drive.
- Контракт ответа для `main.py` и `bot_handler.py` сохранён: успех возвращает `file_name`, `modified_time`, `ingestion_result`; любой `status != success` обрабатывается через `message` (вызывающий код не менялся).

## Проверки

| Проверка | Результат |
|---|---|
| tracer (после Task 1): `pytest tests/test_gdrive_client.py` | 16 passed (сквозной тест враждебных имён зелёный, расширение продолжено) |
| `pytest tests/test_gdrive_client.py tests/test_composition_di.py tests/test_ports_conformance.py` (Task 2) | 74 passed |
| локальный откат `to_thread` | `test_sync_runs_blocking_drive_calls_off_event_loop` падает (1 failed, 23 passed на тот момент), код восстановлен |
| `pytest ... tests/test_live_db_guard.py` (Task 3) | 104 passed |
| `pytest tests/test_architecture_contract.py` | 5 passed |
| `python3 scripts/gate.py` | ИТОГ ЗЕЛЁНЫЙ: assistant-core 854 теста, assistant-shared 145, SHA-256 боевой БД до и после совпали |

## Task Commits

1. **Task 1 (tracer): безопасный путь загрузки (CR-01)** - `458ca4a` (fix)
2. **Task 2: to_thread и тесты веток поиска (WR-01, WR-12)** - `067b792` (fix)
3. **Task 3: удаление серверного бэкапа (WR-02)** - `f4ffdaa` (fix)

**Plan metadata:** коммит docs(02-03) (SUMMARY, STATE, ROADMAP).

## Decisions Made

См. frontmatter. Главное: при расхождении между действием («берётся `Path(name).name`») и must_have («имена с `..` и `/` дают отказ») выбрана строгая трактовка must_have.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Отказ по разделителям пути вместо обрезки до последнего компонента**
- **Found during:** Task 1
- **Issue:** действие плана предписывало брать `Path(name).name`, но тогда имена «aadhk/../../../../escaped/evil.db» и «../../x.db» из must_have и критериев приёмки стали бы допустимыми («evil.db», «x.db»). Нулевой байт после whitelist-замены тоже превратился бы в «_» и не дал отказа.
- **Fix:** до обрезки отвергаются имена с «/», «\\» и «\x00»; `Path(name).name` оставлен как второй рубеж, затем «», «.», «..», whitelist и проверка родителя после `resolve()`.
- **Files modified:** `src/connectors/gdrive/client.py`, `tests/test_gdrive_client.py`
- **Commit:** `458ca4a`

**2. [Rule 3 - Blocking] Устаревший ledger коммитов плана**
- **Found during:** старт плана
- **Issue:** `.git/gsd-plan-head-before-02-03` указывал на `7410deb` от прежнего этапа, `commits:` дало бы неверное число.
- **Fix:** файл перезаписан реальной базой `318682e` (вне истории git); `commits: 3` измерен `git rev-list --count`.

### Процессные заметки

- Имена с Drive, содержащие «/», теперь отклоняются целиком (Drive такие имена допускает, но для файла бэкапа AADHk это не встречается); при отказе пользователь видит русское сообщение.
- Гейт при первом прогоне упал на `tests/test_command_aliases.py::test_fast_intent_router_aliases`: тест проверяет задержку роутера `< 50 мс` и зависит от нагрузки VPS (в изолированных прогонах один вызов занимал 18 с при активной фоновой нагрузке). Файл к плану не относится, повторный прогон гейта зелёный, изолированные прогоны проходят. Нестабильность по времени стоит учесть отдельным заданием (предложение: ослабить порог или измерять в тихом окне), в этом плане не исправлялась.
- Неиспользуемый импорт `from src import config` в `client.py` существовал до плана и не тронут (вне находок плана); IN-06 не затронут.
- `tdd="true"` у Task 2 не оформлялся отдельными RED/GREEN-коммитами (по плану один коммит на задачу); тест потока проверен локальным откатом.
- `actuals.tokens` оценено как chars/4 по диффу `src` и `tests` (около 22,7 тыс. символов).

## Known Stubs

None.

## Threat Flags

None. Новых сетевых точек, путей аутентификации и обращений к файлам нет; поверхность сузилась. Модель угроз: T-02-07 и T-02-10 закрыты тестами враждебных имён и символьных ссылок, T-02-08 закрыт тестом потока, T-02-09 закрыт удалением методов и регрессионным тестом, T-02-SC не затронут (пакеты не ставились).

## Issues Encountered

Первый прогон полного гейта упал на времязависимом тесте задержки роутера (см. выше), второй прошёл зелёным.

## Next Phase Readiness

Фаза рантаймовая: изменения вступят в силу после рестарта `assistant-worker.service`, который не выполнялся (только по явному разрешению владельца). Disposition находок CR-01, WR-01, WR-02, WR-12 в `01-REVIEW-DISPOSITION.md` обновляет план 02-14 по перечисленным тестам.

## Self-Check: PASSED

- `src/connectors/gdrive/client.py`, `tests/test_gdrive_client.py`: найдены
- коммиты `458ca4a`, `067b792`, `f4ffdaa` являются предками HEAD
