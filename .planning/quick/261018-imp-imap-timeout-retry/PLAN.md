# Quick 261018-imp: IMAP-таймауты почты университета
Диагноз (read-only): сервер доступен, 27 таймаутов из 272 подключений за 3 дня (~10%); `IMAPClient(timeout=15)` в `ingest_imap_account` без повтора, красный смоук после рестарта.
Правка: `open_imap_client` (timeout 45 с, до 2 попыток подключения+логина, повтор только для TimeoutError/OSError); используется в `ingest_imap_account`.
Тест: `tests/test_imap_connect_retry.py` (3 теста, падают без правки).
