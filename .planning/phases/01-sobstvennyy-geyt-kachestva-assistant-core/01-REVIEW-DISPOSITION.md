---
phase: 01
review: 01-REVIEW.md
titles: json
findings:
  - id: CR-01
    severity: critical
    disposition: deferred
    title: "Path traversal при записи скачанного файла Google Drive (запись от root за пределы uploads)"
  - id: WR-01
    severity: warning
    disposition: deferred
    title: "Блокирующий сетевой и файловый ввод-вывод внутри async-методов (замораживает event loop демона)"
  - id: WR-02
    severity: warning
    disposition: deferred
    title: "Архив «серверного бэкапа» несогласован, небезопасен по правам и не используется"
  - id: WR-03
    severity: warning
    disposition: deferred
    title: "Смягчение проверки «боевая БД не изменена» почти полностью отключает её"
  - id: WR-04
    severity: warning
    disposition: deferred
    title: "Замороженный список ложных срабатываний shield позволяет подменить находку"
  - id: WR-05
    severity: warning
    disposition: deferred
    title: "Защита адаптера агента неполна: гейт цели исполняет код, который патч менять может"
  - id: WR-06
    severity: warning
    disposition: deferred
    title: "Для репозитория без своего гейта адаптер молча запускает гейт chat-app и сообщает «гейт цели зелёный»"
  - id: WR-07
    severity: warning
    disposition: deferred
    title: "Страж боевой БД не закрывает часть путей"
  - id: WR-08
    severity: warning
    disposition: deferred
    title: "`deploy.py` пишет от root в предсказуемый путь в `/var/tmp` с переходом по symlink"
  - id: WR-09
    severity: warning
    disposition: deferred
    title: "`make_db_copy` меняет права произвольного существующего каталога и проверяет только «внутри core»"
  - id: WR-10
    severity: warning
    disposition: deferred
    title: "Тесты `db_unchanged_check` недетерминированы: запускают реальный `systemctl` и делают `stat` боевой БД"
  - id: WR-11
    severity: warning
    disposition: deferred
    title: "Тест `test_menu_command_rendering` ничего не проверяет про «отрисовку меню»"
  - id: WR-12
    severity: warning
    disposition: deferred
    title: "Тест Drive проходит через ветку «папка», а не через общий поиск; пути `download`/`sync` не покрыты"
  - id: WR-13
    severity: warning
    disposition: deferred
    title: "Защитный тест на «возврат к чужому гейту» ловит только точную строку"
  - id: IN-01
    severity: info
    disposition: deferred
    title: "`ASSISTANT_DB_PATH_OVERRIDE` в боевом рантайме не логируется и не нормализуется"
  - id: IN-02
    severity: info
    disposition: deferred
    title: "`os.environ.setdefault` не заменяет пустую строку"
  - id: IN-03
    severity: info
    disposition: deferred
    title: "Мелочи в `deploy.py`"
  - id: IN-04
    severity: info
    disposition: deferred
    title: "Неточности в `gate.py`"
  - id: IN-05
    severity: info
    disposition: deferred
    title: "Хук и установщик assistant-shared зависят от пути assistant-core и проверяют не то, что исполняется"
  - id: IN-06
    severity: info
    disposition: deferred
    title: "Мёртвые/слабые места `gdrive/client.py`"
open: 0
total: 20
recorded: 2026-10-10T05:03:13.670Z
---

# Phase 01: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| CR-01 | critical | deferred | owner poll 2026-10-10: deferred to Phase 2 (security & review findings) |
| WR-01 | warning | deferred | owner poll 2026-10-10: deferred to Phase 2 (security & review findings) |
| WR-02 | warning | deferred | owner poll 2026-10-10: deferred to Phase 2 (security & review findings) |
| WR-03 | warning | deferred | owner poll 2026-10-10: deferred to Phase 2 (security & review findings) |
| WR-04 | warning | deferred | owner poll 2026-10-10: deferred to Phase 2 (security & review findings) |
| WR-05 | warning | deferred | owner poll 2026-10-10: deferred to Phase 2 (security & review findings) |
| WR-06 | warning | deferred | owner poll 2026-10-10: deferred to Phase 2 (security & review findings) |
| WR-07 | warning | deferred | owner poll 2026-10-10: deferred to Phase 2 (security & review findings) |
| WR-08 | warning | deferred | owner poll 2026-10-10: deferred to Phase 2 (security & review findings) |
| WR-09 | warning | deferred | owner poll 2026-10-10: deferred to Phase 2 (security & review findings) |
| WR-10 | warning | deferred | owner poll 2026-10-10: deferred to Phase 2 (security & review findings) |
| WR-11 | warning | deferred | owner poll 2026-10-10: deferred to Phase 2 (security & review findings) |
| WR-12 | warning | deferred | owner poll 2026-10-10: deferred to Phase 2 (security & review findings) |
| WR-13 | warning | deferred | owner poll 2026-10-10: deferred to Phase 2 (security & review findings) |
| IN-01 | info | deferred | owner poll 2026-10-10: deferred to Phase 2 (security & review findings) |
| IN-02 | info | deferred | owner poll 2026-10-10: deferred to Phase 2 (security & review findings) |
| IN-03 | info | deferred | owner poll 2026-10-10: deferred to Phase 2 (security & review findings) |
| IN-04 | info | deferred | owner poll 2026-10-10: deferred to Phase 2 (security & review findings) |
| IN-05 | info | deferred | owner poll 2026-10-10: deferred to Phase 2 (security & review findings) |
| IN-06 | info | deferred | owner poll 2026-10-10: deferred to Phase 2 (security & review findings) |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
