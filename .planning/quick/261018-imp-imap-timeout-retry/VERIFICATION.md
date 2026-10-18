---
status: passed
---
# Verification 261018-imp
3 новых теста + 42 теста почты/коллектора passed; `python3 scripts/gate.py` ЗЕЛЁНЫЙ. Рантайм: достижимо через `ingest_imap_account` (цикл `email_collector_job`, каждые 15 мин); проверка на живом сервисе после рестарта — по частоте строк «Failed to connect/ingest IMAP».
