---
phase: 01
review: 01-REVIEW.md
titles: json
findings:
  - id: CR-01
    severity: critical
    disposition: open
    title: "Path traversal при записи скачанного файла Google Drive (запись от root за пределы uploads)"
  - id: WR-01
    severity: warning
    disposition: open
    title: "Блокирующий сетевой и файловый ввод-вывод внутри async-методов (замораживает event loop демона)"
  - id: WR-02
    severity: warning
    disposition: open
    title: "Архив «серверного бэкапа» несогласован, небезопасен по правам и не используется"
  - id: WR-03
    severity: warning
    disposition: open
    title: "Смягчение проверки «боевая БД не изменена» почти полностью отключает её"
  - id: WR-04
    severity: warning
    disposition: open
    title: "Замороженный список ложных срабатываний shield позволяет подменить находку"
  - id: WR-05
    severity: warning
    disposition: open
    title: "Защита адаптера агента неполна: гейт цели исполняет код, который патч менять может"
  - id: WR-06
    severity: warning
    disposition: open
    title: "Для репозитория без своего гейта адаптер молча запускает гейт chat-app и сообщает «гейт цели зелёный»"
  - id: WR-07
    severity: warning
    disposition: open
    title: "Страж боевой БД не закрывает часть путей"
  - id: WR-08
    severity: warning
    disposition: open
    title: "`deploy.py` пишет от root в предсказуемый путь в `/var/tmp` с переходом по symlink"
  - id: WR-09
    severity: warning
    disposition: open
    title: "`make_db_copy` меняет права произвольного существующего каталога и проверяет только «внутри core»"
  - id: WR-10
    severity: warning
    disposition: open
    title: "Тесты `db_unchanged_check` недетерминированы: запускают реальный `systemctl` и делают `stat` боевой БД"
  - id: WR-11
    severity: warning
    disposition: open
    title: "Тест `test_menu_command_rendering` ничего не проверяет про «отрисовку меню»"
  - id: WR-12
    severity: warning
    disposition: open
    title: "Тест Drive проходит через ветку «папка», а не через общий поиск; пути `download`/`sync` не покрыты"
  - id: WR-13
    severity: warning
    disposition: open
    title: "Защитный тест на «возврат к чужому гейту» ловит только точную строку"
  - id: IN-01
    severity: info
    disposition: open
    title: "`ASSISTANT_DB_PATH_OVERRIDE` в боевом рантайме не логируется и не нормализуется"
  - id: IN-02
    severity: info
    disposition: open
    title: "`os.environ.setdefault` не заменяет пустую строку"
  - id: IN-03
    severity: info
    disposition: open
    title: "Мелочи в `deploy.py`"
  - id: IN-04
    severity: info
    disposition: open
    title: "Неточности в `gate.py`"
  - id: IN-05
    severity: info
    disposition: open
    title: "Хук и установщик assistant-shared зависят от пути assistant-core и проверяют не то, что исполняется"
  - id: IN-06
    severity: info
    disposition: open
    title: "Мёртвые/слабые места `gdrive/client.py`"
open: 20
total: 20
recorded: 2026-10-09T23:13:02.883Z
---

# Phase 01: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| CR-01 | critical | open | - |
| WR-01 | warning | open | - |
| WR-02 | warning | open | - |
| WR-03 | warning | open | - |
| WR-04 | warning | open | - |
| WR-05 | warning | open | - |
| WR-06 | warning | open | - |
| WR-07 | warning | open | - |
| WR-08 | warning | open | - |
| WR-09 | warning | open | - |
| WR-10 | warning | open | - |
| WR-11 | warning | open | - |
| WR-12 | warning | open | - |
| WR-13 | warning | open | - |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |
| IN-05 | info | open | - |
| IN-06 | info | open | - |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
