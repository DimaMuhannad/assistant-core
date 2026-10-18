---
status: complete
---
# Summary 261018-imp
`src/collector/email_collector.py`: `open_imap_client`, `IMAP_TIMEOUT_SEC=45`, `IMAP_CONNECT_ATTEMPTS=2`. Тесты: 3 новых, без правки падают. Gate ЗЕЛЁНЫЙ. Требуется рестарт `assistant-worker` (только с разрешения владельца), чтобы правка вошла в рантайм.
