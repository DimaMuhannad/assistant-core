# Задание для /gsd-quick в chat-app: тесты миграций из каталога и покрытие таблиц бота (SCH-02, D-07..D-09)

Файл целиком передаётся `/gsd-quick` в сессии, открытой в `/opt/chat-app`. Сам план 03-01 репозиторий chat-app не меняет: он пишет это задание и проводит предпроверку. Правку выполняет оркестратор через `/gsd-quick` (чекпоинт Task 3 плана 03-01).

## 1. Заголовок и контекст

Общая библиотека `/opt/assistant-shared` установлена editable в виртуальных окружениях обоих сервисов. Миграция `0003_bot_commands_and_feedback.sql` перенесла схему трёх таблиц бота (`bot_command_settings`, `bot_custom_aliases`, `dialog_feedback_log`) под единое владение миграций.

В репозитории `chat-app` список миграций был зашит вручную в `backend/tests/test_migrations.py`. Появление файла `0003` в общем каталоге ломает тесты потребителя, пока они жестко ожидают только первые две версии. 

Требуется согласовать потребителя `chat-app` в рамках требований SCH-02 и решений D-07..D-09:
- динамически выводить `ALL_MIGRATIONS` и `LATEST_SCHEMA_VERSION` из каталога миграций `MIGRATIONS_DIR`;
- включить три таблицы бота в `EXPECTED_CORE_TABLES`;
- добавить тесты структуры колонок этих таблиц и статический запрет собственного DDL для них в `chat-app`.

Окно прохода: коммит `chat-app` выполняется ДО коммита `0003` в `assistant-shared`. В промежутке файл `0003` находится только в рабочем дереве `assistant-shared`.

## 2. Текущее поведение

- В `backend/tests/test_migrations.py` константы зашиты литералами:
  ```python
  LATEST_SCHEMA_VERSION = "0002_pending_confirmations"
  ALL_MIGRATIONS = ["0001_initial_schema", "0002_pending_confirmations"]
  ```
- Тесты проверяют строго `assert "0001_initial_schema" in applied` и `assert "0002_pending_confirmations" in applied`.
- В тесте `test_migrations_aiosqlite_in_memory_connection` проверка `assert row[0] == 2` ожидает ровно 2 примененные миграции.
- Список `EXPECTED_CORE_TABLES` не содержит таблиц `bot_command_settings`, `bot_custom_aliases`, `dialog_feedback_log`.
- Нет проверки структуры колонок таблиц бота и нет статического теста отсутствия собственного DDL для этих таблиц в `backend/app`.

## 3. Требуемое поведение

Один файл: `backend/tests/test_migrations.py`.

1. **Динамический список миграций из каталога:**
   - Импортировать `MIGRATIONS_DIR` из `assistant_shared.db.migrator`.
   - Вычислять список миграций динамически:
     ```python
     ALL_MIGRATIONS = sorted(p.stem for p in MIGRATIONS_DIR.glob("*.sql"))
     LATEST_SCHEMA_VERSION = ALL_MIGRATIONS[-1]
     ```
   - Заменить жесткие проверки на инвариантные: базовые версии `0001_initial_schema` и `0002_pending_confirmations` входят в `applied`.
   - В `test_migrations_aiosqlite_in_memory_connection` заменить проверку `row[0] == 2` на `row[0] == len(ALL_MIGRATIONS)`.

2. **Таблицы бота в составе ядра платформы:**
   - Дополнить `EXPECTED_CORE_TABLES` тремя таблицами: `bot_command_settings`, `bot_custom_aliases`, `dialog_feedback_log`.
   - Добавить тест проверки колонок таблиц бота после мигратора `test_bot_tables_schema_columns(tmp_path)`:
     - `bot_command_settings`: `['command_name', 'is_enabled', 'custom_description', 'updated_at']`
     - `bot_custom_aliases`: `['alias', 'canonical_command', 'created_at']`
     - `dialog_feedback_log`: `['id', 'message_id', 'user_id', 'feedback_type', 'created_at']`
     (проверка порядка и имен колонок по `PRAGMA table_info`).

3. **Статический запрет собственного DDL:**
   - Добавить статический тест `test_chat_app_does_not_create_shared_schema_tables()`:
     - Рекурсивно сканирует файлы `backend/app/**/*.py`.
     - Проверяет отсутствие операторов `CREATE TABLE` с именами `bot_command_settings`, `bot_custom_aliases`, `dialog_feedback_log` (регулярное выражение с `re.IGNORECASE` и поддержкой пробелов/переносов строк).
     - Включает самопроверку на синтетическом фрагменте и ассерт, что количество проверенных файлов больше нуля.

## 4. Предпроверка

Фактический запуск `backend/.venv/bin/pytest backend/tests -p no:cacheprovider -q -rf` в `/opt/chat-app` против модифицированной библиотеки зафиксировал:
- Итог: **6 failed, 271 passed, 3 warnings in 64.60s** (сохранено в `/var/tmp/gsd-phase03-precheck/chat-app-before.txt`).
- Список упавших файлов (`/var/tmp/gsd-phase03-precheck/failed-files.txt`):
  - `backend/tests/test_migrations.py` (все 6 падений относятся исключительно к этому файлу).
- Расхождений с допущением D-07 нет: падает ровно один файл `backend/tests/test_migrations.py`.

## 5. Файлы для изменения

Изменяется ровно один файл:
- `backend/tests/test_migrations.py`

## 6. Ограничения

- Файл `scripts/gate.py` репозитория chat-app НЕ менять.
- Другие тесты и механизмы безопасности не ослаблять.
- Запрещено вводить `skip`, `xfail`, `deselected`.
- Новых внешних зависимостей (pip/npm) не добавлять.
- Сервис `chat-app.service` НЕ перезапускать.
- Не создавать собственное DDL для трех таблиц в кодовой базе `chat-app`.

## 7. Проверка перед коммитом

1. Запустить полный тестовый набор `chat-app`:
   ```bash
   backend/.venv/bin/pytest backend/tests -p no:cacheprovider -q
   ```
   Должно быть 100% passed (277 passed или более, без failed/skipped/errors).
2. Запустить общий гейт `chat-app`:
   ```bash
   python3 scripts/gate.py
   ```
   Вердикт должен быть строго «ИТОГ: ЗЕЛЁНЫЙ».

## 8. Коммит

Атомарный коммит в `/opt/chat-app`:
```bash
git add backend/tests/test_migrations.py
git commit -m "test(migrations): derive migration list from shared catalog, cover bot tables (SCH-02)"
```

## 9. Что вернуть

По итогам выполнения `/gsd-quick` возвращает:
- Хеш коммита в `chat-app`.
- Итоговую строку полного pytest `chat-app`.
- Результат работы скрипта `python3 scripts/gate.py`.

## 10. Окно прохода

Коммит в `chat-app` должен предшествовать коммиту миграции `0003` в `assistant-shared`. В течение этого промежутка файл миграции `0003` находится в рабочем дереве `assistant-shared` в незакоммиченном виде.
