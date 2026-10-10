# Отложенные находки фазы 02

## 02-14: плавающий тест `test_concurrent_confirmations_isolation` ("database is locked")

- **Что:** `tests/test_concurrency_isolation.py::test_concurrent_confirmations_isolation` (ISO-04, Phase 06 v2.0) иногда падает с `sqlite3.OperationalError: database is locked` в `ConfirmationStore.create_confirmation` (`/opt/assistant-shared/assistant_shared/hitl/store.py`, одиночный INSERT) при параллельном создании подтверждений двумя корутинами на свежей временной БД.
- **Как проявилось:** в плане 02-14 один прогон общего гейта chat-app (`/opt/chat-app/scripts/gate.py`) дал строку assistant-core pytest красной именно из-за этого теста (1 failed, 976 passed); собственный гейт assistant-core в тот же час зелёный (977 passed). Отдельно тест на 10 прогонов подряд упал 1 раз (≈10%), в первом прогоне серии из 5 тоже упал 1 раз и шёл 23 секунды.
- **Связь с планом:** изменений в затронутых тестом файлах (`assistant-shared/hitl`, `db/connection.py`, сам тест) план не вносил; регрессия фазы 2 не доказана и маловероятна.
- **Предположение (не проверено):** гонка первого открытия временной БД, когда соединения одновременно выставляют `PRAGMA journal_mode = WAL` (`get_async_connection`), а `busy_timeout` до такой ошибки не ждёт. Для боевой БД, уже находящейся в режиме WAL, риск, вероятно, ниже; подтверждения нет.
- **Почему не исправлено:** вне области плана; `assistant-shared` в этом плане read-only. Нужен разбор причины, затем исправление в `assistant-shared` (повтор на `SQLITE_BUSY` или иной порядок PRAGMA) и стабилизация теста.
- **Решение владельцу:** завести малую задачу (кандидат в Phase 3 «Владение схемой БД», затрагивает `assistant-shared`) или отдельный `/gsd-quick`. Пока плавающий тест может кратко делать общий гейт chat-app красным; повторный прогон обычно зелёный.
