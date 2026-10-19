---
phase: 02
review: 02-REVIEW.md
titles: json
findings:
  - id: WR-01
    severity: warning
    disposition: deferred
    title: "Пространство restricted_nda с пустыми словами (forbidden_keywords: [\"\"]) молча отключает защиту слов NDA"
  - id: WR-02
    severity: warning
    disposition: deferred
    title: "Путь пространства NDA относительный или с ~ не сопоставляется: репозиторий получает публичный профиль, проверка remote пропускается"
  - id: WR-03
    severity: warning
    disposition: deferred
    title: "Репозиторий, сопоставленный с пространством NDA, не проверяется на слова других пространств NDA (CLI и web)"
  - id: WR-04
    severity: warning
    disposition: deferred
    title: "Смягчение проверки БД в gate.py принимает любые INSERT/UPDATE и DELETE в 10 таблицах рантайма"
  - id: WR-05
    severity: warning
    disposition: deferred
    title: "Скачивание Google Drive: путь проверяется, затем открывается обычным open() от root; возможна подмена ссылкой, нет лимита размера"
  - id: WR-06
    severity: warning
    disposition: deferred
    title: "PROTECTED адаптера cross-AI не покрывает корневой conftest.py, вложенные tests/**/conftest.py и sitecustomize.py"
  - id: IN-01
    severity: info
    disposition: deferred
    title: "_has_connected_mailbox определяет ящик исключением известных ключей, а не по ключу account"
  - id: IN-02
    severity: info
    disposition: deferred
    title: "Если mark_notice_shown падает после успешной отправки, предупреждение повторяется каждые 15 минут"
  - id: IN-03
    severity: info
    disposition: deferred
    title: "scripts/auth_google.py импортирует src.persona.notices вне запасного try"
  - id: IN-04
    severity: info
    disposition: deferred
    title: "Запасной гейт адаптера cross-AI завершается кодом 0 для непроверенного репозитория"
  - id: IN-05
    severity: info
    disposition: deferred
    title: "Делегаторы shield в shared и chat-app исполняют то, на что указывает ASSISTANT_CORE_DIR (принятое доверие)"
---

# Phase 02 — disposition находок ревью

Решение владельца 2026-10-10 (ответ в чате после отчёта верификатора): «Принять риски, идти дальше».
Все 11 находок (WR-01..WR-06, IN-01..IN-05) получают статус `deferred`: риск принят, исправления не делаются в этой фазе.

Заметки для будущих фаз и малых задач `/gsd-quick`:
- WR-01 и WR-02 (пустые слова и относительный путь NDA-пространства в данных персоны) верификатор рекомендует исправить до Phase 8,
  когда мастер персоны начнёт создавать такие данные из пользовательского ввода.
- WR-03 закреплён сознательно (T-02-21): в живой персоне одно NDA-пространство.
- WR-04, WR-05, WR-06 касаются закрытия находок Phase 1 (gate.py, скачивание Google Drive, адаптер cross-AI в chat-app).
- Плавающий тест `test_concurrent_confirmations_isolation` (HITL-хранилище shared) записан в `deferred-items.md`.
