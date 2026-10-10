---
phase: 02
review: 02-REVIEW.md
titles: json
findings:
  - id: WR-01
    severity: warning
    disposition: open
    title: "Пространство restricted_nda с пустыми словами (forbidden_keywords: [\"\"]) молча отключает защиту слов NDA"
  - id: WR-02
    severity: warning
    disposition: open
    title: "Путь пространства NDA относительный или с ~ не сопоставляется: репозиторий получает публичный профиль, проверка remote пропускается"
  - id: WR-03
    severity: warning
    disposition: open
    title: "Репозиторий, сопоставленный с пространством NDA, не проверяется на слова других пространств NDA (CLI и web)"
  - id: WR-04
    severity: warning
    disposition: open
    title: "Смягчение проверки БД в gate.py принимает любые INSERT/UPDATE и DELETE в 10 таблицах рантайма"
  - id: WR-05
    severity: warning
    disposition: open
    title: "Скачивание Google Drive: путь проверяется, затем открывается обычным open() от root; возможна подмена ссылкой, нет лимита размера"
  - id: WR-06
    severity: warning
    disposition: open
    title: "PROTECTED адаптера cross-AI не покрывает корневой conftest.py, вложенные tests/**/conftest.py и sitecustomize.py"
  - id: IN-01
    severity: info
    disposition: open
    title: "_has_connected_mailbox определяет ящик исключением известных ключей, а не по ключу account"
  - id: IN-02
    severity: info
    disposition: open
    title: "Если mark_notice_shown падает после успешной отправки, предупреждение повторяется каждые 15 минут"
  - id: IN-03
    severity: info
    disposition: open
    title: "scripts/auth_google.py импортирует src.persona.notices вне запасного try"
  - id: IN-04
    severity: info
    disposition: open
    title: "Запасной гейт адаптера cross-AI завершается кодом 0 для непроверенного репозитория"
  - id: IN-05
    severity: info
    disposition: open
    title: "Делегаторы shield в shared и chat-app исполняют то, на что указывает ASSISTANT_CORE_DIR (принятое доверие)"
---

# Phase 02 — disposition находок ревью

Записано оркестратором после `02-REVIEW.md` (0 критических, 6 предупреждений, 5 информационных).
Все находки пока `open`: ни одна не исправлена и ни одна не отложена решением владельца.
Решение по каждой (исправить, отложить, принять риск) принимает владелец; кандидаты на ближайшую фазу
или малые задачи `/gsd-quick` перечислены в итоговом сообщении оркестратора.
