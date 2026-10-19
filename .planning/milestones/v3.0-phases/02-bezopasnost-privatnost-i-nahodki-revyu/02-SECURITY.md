---
phase: "02"
slug: "bezopasnost-privatnost-i-nahodki-revyu"
status: verified
# threats_open = число ОТКРЫТЫХ угроз уровня workflow.security_block_on (high) и выше
threats_open: 0
asvs_level: 1
block_on: high
created: "2026-10-10"
---

# Phase 02 — Безопасность

> Контракт безопасности фазы: реестр угроз, принятые риски, журнал аудита.
> Аудит выполнен агентом gsd-security-auditor на уровне ASVS 1 (меры найдены в коде, тестах или артефактах).
> Реестр построен из блоков `<threat_model>` 15 планов; значения слов NDA, литералы аккаунтов и содержимое `persona.yaml` в файл не вносились.

Обозначения путей: `core` = /opt/assistant-core, `shared` = /opt/assistant-shared, `chat` = /opt/chat-app.
Статус `closed*` = закрыто с остаточным риском (см. раздел «Остаточные риски»).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| B1 | Текст, голос и ответ LLM-роутера в Telegram -> бот -> память диалога (SQLite, очистка через архив) | Команды владельца, история диалога |
| B2 | Имя и содержимое файла Google Drive (в том числе расшаренного) -> запись на диск от root в uploads | Недоверенные имена файлов и данные |
| B3 | Данные персоны и пространств -> решение «NDA или публично» в shield (CLI, hook) и web-аудите | Правила NDA, remote, пути, слова |
| B4 | Делегирование hook, shared и chat-app -> обёртка assistant-core (`ASSISTANT_CORE_DIR`) | Единственный источник правил NDA |
| B5 | Скрипты и гейт -> общая ФС и боевая БД (deploy, live_db_guard, gate, рестарт сервиса) | Боевая БД, копии, состояние смоука |
| B6 | Патч агента Antigravity и документы фазы -> рабочее дерево, публичный репозиторий, гейт цели | Патчи, задания, SUMMARY, evidence |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation (evidence) | Status |
|-----------|----------|-----------|----------|-------------|-----------------------|--------|
| T-02-01 | Tampering | scan_file_content: единый поиск секретов | high | mitigate | shared security/scanner.py; test_scan_file_content.py | closed |
| T-02-02 | Info Disclosure | web-находка по слову NDA | medium | mitigate | format_web без слова; тесты scan_file_content | closed |
| T-02-03 | Elev. of Privilege | API слов как обход для файла | medium | mitigate | сигнатура закреплена inspect.signature, допуска нет | closed |
| T-02-04 | Tampering | фраза очистки (текст, голос, движок) | high | mitigate | единственный clear_dialog_history за карточкой /clear; test_clear_dialog_text_guard.py | closed |
| T-02-05 | Tampering | подмена /clear алиасом | medium | accept | protected={cancel,cansel,reset,clear,undo_clear} (bot_handler) | closed (accept, AR-02-01) |
| T-02-06 | Spoofing | неавторизованный пользователь | medium | mitigate | _is_authorized первым в предупреждении; тест | closed |
| T-02-07 | Elev. of Privilege | путь из имени файла Drive (root) | critical | mitigate | _safe_upload_path, whitelist, resolve-проверка; test_gdrive_client.py | closed* (WR-05) |
| T-02-08 | DoS | синхронный ввод-вывод в async | medium | mitigate | asyncio.to_thread; тест | closed |
| T-02-09 | Info Disclosure | архив .env и сессии на Drive | high | mitigate | методы удалены, grep по src и scripts: 0 | closed |
| T-02-10 | Tampering | запись по ссылке в каталоге загрузок | medium | mitigate | resolve() раскрывает ссылку, родитель вне UPLOADS_DIR -> отказ | closed* (WR-05) |
| T-02-11 | Tampering | _write_private и ссылка | high | mitigate | O_EXCL, O_NOFOLLOW, 0600, os.replace; test_deploy_script.py | closed |
| T-02-12 | Spoofing | подмена файла состояния смоука | high | mitigate | O_NOFOLLOW, fstat: файл, uid, mode&0o077==0 | closed |
| T-02-13 | Tampering | chmod существующего каталога копий | medium | mitigate | chmod только созданного, небезопасный существующий отвергается | closed |
| T-02-14 | Info Disclosure | копия БД в дереве чужого репозитория | high | mitigate | проверка .git у предков до создания каталога | closed |
| T-02-15 | Tampering | страж боевой БД: другой checkout, ссылка | high | mitigate | live_db_guard: абсолютные пути и realpath | closed |
| T-02-16 | Tampering | жёсткая ссылка на боевую БД | low | accept | сравнение по realpath, не inode (02-05-SUMMARY) | closed (accept, AR-02-02) |
| T-02-17 | Repudiation | обход стража правил вариантом команды | medium | mitigate | два регулярных выражения с самопроверкой | closed |
| T-02-18 | Spoofing | сопоставление по имени каталога | high | mitigate | shared rules.py: абсолютный resolve(), подстроки нет | closed |
| T-02-19 | Elev. of Privilege | пропажа данных ослабляет проверку | critical | mitigate | workspaces=None -> rc=1, сбой git и неизвестный допуск -> нарушение | closed* (WR-01, WR-02) |
| T-02-20 | Info Disclosure | вывод shield печатает слова или remote | medium | mitigate | новые сообщения без значений | closed* |
| T-02-21 | Tampering | пересекающиеся пространства | low | accept | побеждает строжайший допуск | closed (accept, AR-02-03) |
| T-02-22 | Tampering | перевод тестов chat-app ослабляет проверки | high | mitigate | нет skip/xfail; 251 -> 261 passed | closed |
| T-02-23 | Elev. of Privilege | делегатор молча пропускает проверку | critical | mitigate | нет каталога, обёртки или интерпретатора -> rc=1; тесты | closed |
| T-02-24 | Info Disclosure | слова NDA и адреса в задании и SUMMARY | high | mitigate | счётчики 0; test_nda_script_parity.py | closed |
| T-02-25 | Tampering | подмена ASSISTANT_CORE_DIR | low | accept | доверие задокументировано | closed (accept, AR-02-04) |
| T-02-26 | Elev. of Privilege | битая персона даёт «пройдено» | critical | mitigate | любое исключение -> rc=1 без отката к публичной проверке | closed |
| T-02-27 | Info Disclosure | ошибки печатают слова NDA | high | mitigate | только класс исключения и безопасный текст; include_input=False | closed |
| T-02-28 | Tampering | ослабление hook или shield ради персоны | medium | mitigate | допуска нет; 3 находки в обоих режимах | closed |
| T-02-29 | Tampering | подмена PERSONA_CONFIG_PATH | medium | accept | схема отвергает restricted_nda без правил | closed (accept, AR-02-05; WR-01) |
| T-02-30 | Tampering | патч агента меняет окружение гейта | high | mitigate | восемь новых PROTECTED; test_agy_cross_ai.py | closed* (WR-06) |
| T-02-31 | Tampering | подмена scripts/gate.py ссылкой | high | mitigate | gate_path_symlink до агента и перед гейтом | closed |
| T-02-32 | Repudiation | «гейт зелёный» для цели без гейта | medium | mitigate | GATE_KIND и предупреждение в stderr и SUMMARY | closed* (IN-04) |
| T-02-33 | Tampering | правка ослабляет прежние защиты | high | mitigate | PROTECTED надмножество прежнего (11 -> 19) | closed |
| T-02-34 | DoS | красный pytest chat-app после удаления имён | high | mitigate | предпроверка на копии, итог трёх репозиториев | closed |
| T-02-35 | Elev. of Privilege | делегатор shared молча пропускает | critical | mitigate | rc=1 при отсутствии цели; тесты | closed |
| T-02-36 | Info Disclosure | литералы организации и аккаунта в библиотеке | high | mitigate | grep по shared: 0; тесты D-10 | closed |
| T-02-37 | Tampering | подмена ASSISTANT_CORE_DIR (shared) | low | accept | доверие задокументировано | closed (accept, AR-02-04) |
| T-02-38 | Info Disclosure | предупреждение молча отключается данными | medium | mitigate | пустой и более 1500 символов отвергается, запасной текст | closed |
| T-02-39 | Tampering | обход hook при коммите персоны | high | mitigate | один --no-verify --only (95812d1), согласие владельца, sha256 | closed |
| T-02-40 | Info Disclosure | слова NDA и организации в новых файлах | high | mitigate | в добавленных строках слов NDA 0 | closed |
| T-02-41 | Tampering | ящик определён неверно | medium | mitigate | _has_connected_mailbox; тесты | closed* (IN-01) |
| T-02-42 | DoS | сбой показа ломает цикл почты | medium | mitigate | флаг после успешной отправки, свой try/except | closed |
| T-02-43 | Tampering | ключ флага пересекается с daily_primed_context | low | mitigate | префикс notice:, иначе ValueError | closed |
| T-02-44 | Tampering | смягчение прячет порчу боевой БД | high | mitigate | снимок mode=ro, сравнение с исходным | closed* (WR-04) |
| T-02-45 | Tampering | правки тестом при совместимых снимках | medium | accept | основной барьер live_db_guard | closed (accept, AR-02-06) |
| T-02-46 | Tampering | подмена ложных срабатываний при равном счётчике | high | mitigate | line_fingerprint (sha256 пути и строки) | closed |
| T-02-47 | Repudiation | находка fixed без теста | high | mitigate | 14 fixed и 6 deferred; 119 тестов | closed* |
| T-02-48 | Info Disclosure | сырые данные журнала в evidence | high | mitigate | e-mail, секретов, слов NDA: 0 | closed |
| T-02-49 | Elev. of Privilege | рестарт или backup во время проверки | high | mitigate | InvocationID, NRestarts, MainPID совпали с базой | closed |
| T-02-50 | Elev. of Privilege | рестарт без разрешения владельца | critical | mitigate | blocking-human; рестарт выполнил владелец | closed |
| T-02-51 | Tampering | ключ переопределения пути БД | high | mitigate | владелец: grep -c = 0; ключ читается до load_dotenv | closed |
| T-02-52 | Info Disclosure | сырые строки журнала в отчёте | high | mitigate | отчёт без InvocationID и сырых строк | closed |
| T-02-53 | Repudiation | красный смоук смягчён или скрыт | high | mitigate | любая красная строка -> КРАСНЫЙ; откат только печатается | closed |
| T-02-54 | Info Disclosure | вывод shield --all со словами NDA | high | mitigate | в фазовых документах слов NDA 0 | closed |
| T-02-SC | Tampering | установка пакетов pip (15 планов) | high | mitigate | requirements, pyproject, Dockerfile не менялись | closed |

*Status: open · closed · closed* = с остаточным риском · closed (accept) = принятый риск с записью в журнале ниже*
*Severity: critical > high > medium > low; в threats_open входят только открытые угрозы уровня high и выше*

Итого: 55 угроз, закрыто 55 (48 mitigate, 7 accept), открыто 0, открыто на уровне high и выше 0. По severity: critical 6, high 28, medium 16, low 5.

---

## Остаточные риски (closed*)

Угрозы закрыты по коду на уровне L1, остаток вызван находками ревью WR-01..WR-06 и IN-01..IN-05. Эти находки принял как отложенные риск владелец 2026-10-10 (ответ «Принять риски, идти дальше», `02-REVIEW-DISPOSITION.md`). Принятие само по себе ничего не закрывает.

| Находка | Угрозы | Вывод |
|---------|--------|-------|
| WR-01 (слова из пробелов отключают защиту слов, воспроизведено) | T-02-19 (critical), T-02-29 | Остаток на L1. На L2 кандидат в OPEN. Исправить до Phase 8 |
| WR-02 (относительный путь NDA не сопоставляется, воспроизведено) | T-02-19, T-02-18 | То же. Все пути живой персоны абсолютные |
| WR-03 (слова других NDA-пространств не ищутся в NDA-репозитории) | T-02-21 | Не открывает угрозу: одно NDA-пространство в живой персоне |
| WR-04 (смягчение гейта принимает INSERT/UPDATE и DELETE в 10 таблицах) | T-02-44, T-02-45 | Расширяет принятый остаток; основной барьер live_db_guard |
| WR-05 (проверка пути и open() разнесены, нет лимита размера) | T-02-07, T-02-10 | Заявленный вектор закрыт; остаются гонка и ссылка внутри UPLOADS_DIR |
| WR-06 (PROTECTED не покрывает корневой conftest.py, tests/**/conftest.py, sitecustomize.py) | T-02-30 | На L2 кандидат в OPEN; патч не коммитится и проверяется Claude |
| IN-01..IN-05 | T-02-41, 42, 38, 32, 23, 25, 35, 37 | Информационные, безопасная сторона или принятое доверие |

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-02-01 | T-02-05 | Алиас не может переопределить /clear, /reset, /cancel, /undo_clear; защита существовала до фазы | план 02-02 (disposition accept) | 2026-10-10 |
| AR-02-02 | T-02-16 | Жёсткая ссылка на боевую БД не распознаётся (realpath, не inode); нужна запись в каталог тестов | план 02-05 | 2026-10-10 |
| AR-02-03 | T-02-21 | При пересечении пространств побеждает строжайший допуск; дефект данных владельца | план 02-06 | 2026-10-10 |
| AR-02-04 | T-02-25, T-02-37 (IN-05) | ASSISTANT_CORE_DIR принадлежит доверенному окружению процесса | планы 02-07, 02-10 | 2026-10-10 |
| AR-02-05 | T-02-29 | PERSONA_CONFIG_PATH в доверенном окружении; схема отвергает restricted_nda без списков | план 02-08 | 2026-10-10 |
| AR-02-06 | T-02-45, WR-04 | Тест может изменить боевую БД при совместимых снимках; основной барьер live_db_guard | план 02-13 | 2026-10-10 |
| AR-02-07 | WR-01 -> T-02-19 | forbidden_keywords из пробелов у restricted_nda; исправить до Phase 8 | владелец (deferred) | 2026-10-10 |
| AR-02-08 | WR-02 -> T-02-19, T-02-18 | Относительный путь или ~ у NDA-пространства даёт публичный профиль; исправить до Phase 8 | владелец (deferred) | 2026-10-10 |
| AR-02-09 | WR-03 -> T-02-21 | Слова других NDA-пространств не ищутся в NDA-репозитории | владелец (deferred) | 2026-10-10 |
| AR-02-10 | WR-05 -> T-02-07, T-02-10 | Гонка между проверкой и open(), ссылка внутри UPLOADS_DIR, нет лимита размера | владелец (deferred) | 2026-10-10 |
| AR-02-11 | WR-06 -> T-02-30 | conftest.py и sitecustomize.py не защищены; патч не коммитится и проверяется Claude | владелец (deferred) | 2026-10-10 |
| AR-02-12 | IN-01..IN-05 | Информационные замечания ревью | владелец (deferred) | 2026-10-10 |
| AR-02-13 | T-02-28, T-02-39 | 3 находки слов NDA в config/persona.yaml (данные владельца); замороженный список гейта покрывает их по отпечатку; единственный --no-verify (95812d1) по согласию владельца; решение отнесено к Phase 8 | владелец (D-21) | 2026-10-10 |

---

## Наблюдения вне реестра (не блокируют)

- **U-1 (предупреждение).** В `02-RESEARCH.md` по счётчикам: названия организаций ~20, хвост запретной подстроки remote 2, фрагменты литерала личного аккаунта 3; в `02-DISCUSSION-LOG.md` один производный токен. Это документы планирования вне охвата T-02-24, T-02-48, T-02-52; shield их не ловит. Решение (отредактировать или принять) за владельцем.
- **U-2 (информационно).** `_is_authorized` в bot_handler возвращает True, если `allowed_user_id` не задан (поведение до фазы); значение берётся из `config.TELEGRAM_USER_ID`, настройка не проверялась (`.env` не читался).
- Живой web-аудит chat-app не выполнялся (рестарт chat-app.service заморожен); достижимость доказана ASGI-тестами.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-10 | 55 | 55 | 0 | gsd-security-auditor (ASVS 1, block_on high) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-10
