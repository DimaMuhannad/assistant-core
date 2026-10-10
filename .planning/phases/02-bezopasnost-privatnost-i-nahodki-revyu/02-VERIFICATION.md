---
phase: 02-bezopasnost-privatnost-i-nahodki-revyu
verified: 2026-10-10T20:30:00Z
status: human_needed
score: 5/5 must-haves verified
covered_files:
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-01-PLAN.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-01-SUMMARY.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-02-PLAN.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-02-SUMMARY.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-03-PLAN.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-03-SUMMARY.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-04-PLAN.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-04-SUMMARY.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-05-PLAN.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-05-SUMMARY.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-06-PLAN.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-06-SUMMARY.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-07-PLAN.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-07-SUMMARY.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-08-PLAN.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-08-SUMMARY.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-09-PLAN.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-09-SUMMARY.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-10-PLAN.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-10-SUMMARY.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-11-PLAN.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-11-SUMMARY.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-12-PLAN.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-12-SUMMARY.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-13-PLAN.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-13-SUMMARY.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-14-PLAN.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-14-SUMMARY.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-15-PLAN.md
  - .planning/phases/02-bezopasnost-privatnost-i-nahodki-revyu/02-15-SUMMARY.md
  - scripts/security_shield.py
  - src/brain/dialog_safety.py
  - src/main.py
  - src/notifier/bot_handler.py
  - src/persona/models.py
  - src/persona/notices.py
  - tests/test_phase2_reachability.py
covered_digest: "v3:sha256:12181fdd8d1e041ea930f8eed1debb70281f477cfb9a28b1ea65a6efbdcf9245"
behavior_unverified: 0
overrides_applied: 0
gaps: []
human_verification:
  - test: "Решение владельца по 6 предупреждениям ревью (WR-01..WR-06), все в 02-REVIEW-DISPOSITION.md со статусом open"
    expected: "По каждой записано: исправить (малая задача /gsd-quick либо ближайшая фаза), отложить или принять риск. Для WR-01 и WR-02 рекомендуется исправление до Phase 8 (мастер персоны), потому что мастер будет создавать пространства NDA из пользовательского ввода"
    why_human: "Disposition это решение владельца; верификатор его не принимает. WR-01 воспроизведён вручную (см. Gaps Summary)"
  - test: "Живой web-аудит после рестарта chat-app.service (заморожен, владелец решает)"
    expected: "Web-аудит chat-app показывает находки по запретным словам пространства в config/persona.yaml (3 известные) и замороженные находки; других нет"
    why_human: "Рестарт chat-app.service требует явного разрешения владельца; до рестарта запущенный web-процесс использует старый код библиотеки. Достижимость кода доказана ASGI-тестами chat-app (54 passed), но не живым вызовом"
---

# Phase 2: Безопасность, приватность и находки ревью. Отчёт верификации

**Цель фазы:** NDA-режим и аудит безопасности определяются данными рабочих пространств и одинаково работают в web и CLI, текстовая команда «очисти диалог» не стирает историю необратимо без защиты, а пользователь заранее предупреждён, что почта обрабатывается внешними ИИ-сервисами.
**Проверено:** 2026-10-10
**Статус:** human_needed (все 5 критериев ROADMAP подтверждены кодом и тестами; открыты два пункта для решения владельца, провалов нет)
**Повторная верификация:** нет, первичная

Три репозитория проверены по факту: `/opt/assistant-core` (main, база `f107209`), `/opt/assistant-shared` (master, база `74aa928`, 8 коммитов фазы), `/opt/chat-app` (master, база `4b73019`, 5 коммитов фазы `568ecf2`, `d4e4696`, `07a0b86`, `27886b3`, `f92d95f`). Утверждения SUMMARY не принимались на веру: код читался, тесты и гейт запускались заново. Боевая БД не открывалась, `.env` не читался, слова NDA, литерал личного аккаунта и значения `persona.yaml` в отчёт не попадают (только счётчики и имена).

## Достижение цели

### Наблюдаемые истины (критерии успеха ROADMAP)

| # | Истина | Статус | Доказательства |
|---|--------|--------|----------------|
| 1 | CLI-аудит определяет NDA-режим по данным `workspaces`; в `assistant_shared/security` нет подстроки пути «tydex» и литерала личного аккаунта; тест паритета не читает литерал из исходника (SECF-01) | ✓ VERIFIED | `auditor.py:audit_repository(..., workspaces=...)` сопоставляет репозиторий через `match_workspace` (`rules.py`: реальный путь или нормализованный remote, подстрока пути не используется, строжайший допуск при нескольких кандидатах, неизвестный `clearance` считается строжайшим). `grep -ic tydex` по `assistant_shared/` и `scripts/` в assistant-shared: 0 вхождений; константы `CORPORATE_NDA_KEYWORDS` нет. Тест `tests/test_nda_script_parity.py::test_d10_library_sources_have_no_organization_or_account_tokens` берёт токены из `load_persona()` во время теста (названия организаций, первое слово аккаунта, хвост запрещённых подстрок remote) и сравнивает булево, литералов в файле теста нет. Прогон: 90 passed (4 файла core), 197 passed (assistant-shared). Fail-closed: `workspaces=None` или не итерируемое даёт rc=1; сбой git при чтении remote даёт нарушение; неизвестный уровень допуска даёт нарушение |
| 2 | Web- и CLI-аудит используют общую `scan_file_content`; web проверяет `forbidden_keywords` пространства; на общем наборе синтетических фикстур (включая многострочные) результат одинаков (SECF-02) | ✓ VERIFIED | `scanner.py:scan_file_content` единственная точка: и `check_file_content`/`check_index_content` (CLI), и `audit_path` (web) вызывают её. Chat-app `backend/app/api/v1/security.py` (строки 38-42 и 82-86) передаёт в `audit_path` `forbidden_keywords=collect_protected_keywords(workspaces)` и `nda_rule_for(p)`. Тесты: assistant-shared `test_scan_file_content.py`, `test_shield_parity.py`; chat-app `test_security_api.py`, `test_web_nda_keywords.py`, `test_shield_delegator.py`, `test_nda_equivalence.py`: 54 passed |
| 3 | «Очисти диалог» не стирает историю без защиты; решение принято, записано и закреплено тестом (SAFE-01) | ✓ VERIFIED | Решение: текст и голос дают предупреждение, очистка только через HITL-карточку `/clear`, после очистки есть «Восстановить контекст» (обратимый архив). Код: единственный вызов `Database.clear_dialog_history` находится в `cb_dlg_confirm_clear` (`bot_handler.py:1930`), `callback_data="dlg:confirm_clear"` создаёт только `handle_cmd_clear_dialog` (карточка). Остальные пути (быстрый роутер `intent_router.py:142`, движок `secretary_dialog.py:612`, текст `bot_handler.py:1434-1440`, голос `:2601`) заканчиваются `CLEAR_DIALOG_TEXT_WARNING`. Состояние «история не изменена» подтверждено поведенческим тестом (`tests/test_phase2_reachability.py::test_text_clear_phrase_through_router_text_handler_warns_and_keeps_history` и `tests/test_clear_dialog_text_guard.py`), прогон: passed. Это зависимая от поведения истина, поведенческий тест есть, значит PRESENT_BEHAVIOR_UNVERIFIED не применяется |
| 4 | При подключении почты и в `/help` пользователь видит предупреждение по-русски (Gemini и др., разработчик не отвечает за утечку); текст из данных персоны или интерфейса (PRIV-01) | ✓ VERIFIED | Схема `PrivacyConfig` в `src/persona/models.py` (пустой текст запрещён валидатором, лимит 1500 символов). `src/persona/notices.py:email_ai_notice(persona)` берёт текст из `persona.privacy`, нейтральный запасной текст без названий. Проверка загруженной персоны: длина 247, содержит «Gemini» и «Разработчик», фраза об ответственности есть. `/help` добавляет блок «Приватность почты» (`bot_handler.py:459`). Точка подключения почты: `src/main.py:_announce_email_ai_notice` вызывается из `run_email_collector_cycle`, зарегистрированного как `email_collector_job` (`main.py:795`); флаг `notice:email_ai` ставится только после успешной отправки. `scripts/auth_google.py` печатает то же предупреждение. Живые подтверждения владельца: см. R1-R2 |
| 5 | Достижимость из рантайма показана; security-логика только ужесточена (fail-closed); гейт ЗЕЛЁНЫЙ; рестарт только после разрешения владельца; смоук OPS-01 пройден | ✓ VERIFIED | Свежий прогон `python3 scripts/gate.py` (мной, в этой верификации): **ИТОГ: ЗЕЛЁНЫЙ**, 11 строк ✓, core 977 тестов, shared 197, SHA-256 боевой БД до/после совпали (`faf404a662e1`). `security_shield.py . --all`: ровно 3 находки, все в `config/persona.yaml:44`, rc=1 (как заморожено). Рестарт выполнил сам владелец по своему ответу в опросе (restart-with-backup), смоук `02-SMOKE-REPORT.md`: «ИТОГ СМОУКА: ЗЕЛЁНЫЙ»; InvocationID `40e9fe7a…` -> `25ff0740…`. Оговорка по «только ужесточена» см. Gaps Summary (WR-01..WR-03) |

**Оценка:** 5/5 критериев подтверждены. Непроверенных поведенческих истин (`behavior_unverified`): 0.

### Охват требований (REQUIREMENTS.md)

| Требование | Планы | Описание | Статус | Доказательства |
|------------|-------|----------|--------|----------------|
| SECF-01 | 02-06, 02-07, 02-08, 02-10, 02-14, 02-15 | NDA-режим CLI из данных пространств, без «tydex» и личного литерала | ✓ SATISFIED | Критерий 1; таблица в REQUIREMENTS.md отмечена Complete |
| SECF-02 | 02-01, 02-06, 02-07, 02-14, 02-15 | Общая функция сканирования, web проверяет `forbidden_keywords`, паритет | ✓ SATISFIED | Критерий 2. Живой web-аудит не выполнен (рестарт chat-app.service заморожен), см. human_verification |
| SAFE-01 | 02-02, 02-14, 02-15 | «Очисти диалог» без стирания без защиты, решение закреплено тестом | ✓ SATISFIED | Критерий 3 |
| PRIV-01 | 02-11, 02-12, 02-14, 02-15 | Предупреждение при подключении почты и в `/help`, текст из данных | ✓ SATISFIED | Критерий 4 |

Сопоставление идентификаторов: все 4 ID фазы присутствуют в `requirements:` frontmatter планов; в REQUIREMENTS.md других ID, привязанных к Phase 2, нет, значит **ORPHANED нет**. Планы 02-03, 02-04, 02-05, 02-09, 02-13 имеют `requirements: []`: это закрытие находок ревью Phase 1 (CR-01, WR-01..WR-13, T-uo4-02), не требования v3.0.

### Достижимость из рантайма (R1-R5 из 02-VERIFICATION-EVIDENCE.md)

| Пункт | Автоматическое доказательство (проверено мной) | Живое доказательство (владелец, источник: опрос и `02-SMOKE-REPORT.md`) | Статус |
|-------|-----------------------------------------------|----------------------------------------------------------------------|--------|
| R1. `/help` с блоком приватности | `handle_cmd_help` добавляет `email_ai_notice(current_persona())` (`bot_handler.py:459`); тесты reachability: passed | `/help` в Telegram: блок «Приватность почты» есть | ✓ passed |
| R2. Точка подключения почты | `email_collector_job` -> `run_email_collector_cycle` -> `_announce_email_ai_notice`; флаг после успешной отправки | Ровно одно сообщение; записей `PRIV-01:` в журнале инвокации: 1 | ✓ passed |
| R3. Текст «очисти диалог» | Сквозной тест через роутер: ответ равен предупреждению с `/clear`, карточки нет, история не меняется | Ответ владельца: «Предупреждение с /clear, карточки нет» | ✓ passed |
| R4. Аудит через `scripts/security_shield.py` | Обёртка передаёт в `audit_repository` только `repo`, `check_staged_only`, `workspaces`; `--all` дал 3 находки в данных персоны (запущено мной); гейт ЗЕЛЁНЫЙ | Hook и обёртка не входят в службу; живой шаг не нужен | ✓ passed |
| R5. Рестарт и смоук OPS-01 | Гейт ЗЕЛЁНЫЙ | Рестарт по разрешению владельца, смоук ЗЕЛЁНЫЙ, ошибок в журнале старта 0 | ✓ passed |

Живые ответы владельца приняты как внешнее свидетельство (журнал службы я не читал; соответствие `InvocationID` отчёту смоука сверено по `02-SMOKE-REPORT.md` и evidence).

### Поведенческие проверки

| Поведение | Команда | Результат | Статус |
|-----------|---------|-----------|--------|
| Набор фазы core | `.venv/bin/pytest tests/test_phase2_reachability.py tests/test_nda_script_parity.py tests/test_clear_dialog_text_guard.py tests/test_privacy_notice.py` | 90 passed | ✓ PASS |
| Весь assistant-shared | `pytest tests` в `/opt/assistant-shared` | 197 passed | ✓ PASS |
| Потребитель chat-app | `test_security_api, test_web_nda_keywords, test_shield_delegator, test_nda_equivalence` | 54 passed | ✓ PASS |
| Гейт | `python3 scripts/gate.py` | ИТОГ: ЗЕЛЁНЫЙ, rc=0, 977 + 197 тестов | ✓ PASS |
| Shield по дереву | `security_shield.py . --all` | 3 находки, все `config/persona.yaml:44`, rc=1 | ✓ PASS (как заморожено) |

Зонды (`probe-*.sh`) фаза не объявляла: шаг 7c неприменим.

### Антипаттерны

Маркеры долга `TBD/FIXME/XXX` в файлах, изменённых фазой, блокирующих не выявлены в просмотренных областях; значимые находки сведены в ревью (0 critical, 6 warning, 5 info), рассмотренные ниже. Заглушек в путях PRIV-01 и SAFE-01 нет: данные текут из персоны и из обработчиков роутера.

## Предупреждения ревью: влияют ли на критерии успеха

Каждое предупреждение из `02-REVIEW.md` оценено относительно критериев ROADMAP, а не только по названию.

| Находка | Нарушает критерий? | Вывод и обоснование |
|---------|-------------------|---------------------|
| WR-01: у `restricted_nda` пространства `forbidden_keywords: [""]` проходит валидатор | Нет для текущих данных; **gap-risk, значимый** | **Воспроизведено мной** на `WorkspaceConfig`: значения `[""]` и `["  "]` принимаются, `collect_protected_keywords` возвращает `()`, то есть защита слов NDA молча выключается в CLI и в web. В живой персоне ключей NDA 3, непустые (shield даёт ровно 3 находки), так что критерии 1-2 на реальных данных выполнены. Но комментарий валидатора обещает «пустые данные не должны молча выключить NDA», а критерий 5 говорит «только ужесточена, fail-closed». Для введённой фазой модели данных это дыра в обещанном свойстве, не откат прежнего поведения (раньше слова были константами). Мастер персоны Phase 8 создаёт такие данные из ввода, поэтому исправить нужно до него |
| WR-02: относительный или `~` путь NDA-пространства не сопоставляется | Нет для текущих данных; gap-risk | Подтверждено чтением `_matches_by_path` (относительный путь даёт False, без диагностики) и `audit_repository` (не сопоставлен: публичный профиль и предупреждение, проверка remote пропускается). Все 4 пути живой персоны абсолютные (проверено по `startswith("/")`). Дыра достижима только некорректным данными владельца |
| WR-03: репозиторий NDA-пространства не проверяется на слова других NDA-пространств | Нет | Подтверждено кодом (`keywords = [] if is_nda ...`, `audit_path` не ищет слова при `nda_rule is not None`). Критерий 2 и тексты SECF-02 требуют слова «рабочего пространства» в web-аудите, что выполнено для не-NDA каталогов. В живой персоне одно NDA-пространство, межклиентской утечки быть не может. Закреплено осознанно (T-02-21 в evidence). Усиление на будущее |
| WR-04: смягчение проверки БД в `gate.py` принимает INSERT/UPDATE | Нет | Вне критериев 1-5; страж `tests/live_db_guard.py` остаётся основным барьером, гейт сверил SHA-256 (совпал). Принятый остаточный риск T-02-45 |
| WR-05: Drive `open(...,"wb")` после проверки пути | Нет | Относится к закрытию CR-01 Phase 1 (план 02-03), не к критериям Phase 2. Основной обход (path traversal) закрыт тестами, остаётся гонка проверки и открытия при записи в общий каталог |
| WR-06: `PROTECTED` адаптера cross-AI без `conftest.py` и `sitecustomize.py` | Нет | Относится к закрытию WR-05 Phase 1 (chat-app `27886b3`), не к критериям Phase 2 |

IN-01..IN-05 информационные, на критерии не влияют (IN-01: `_has_connected_mailbox` определяет ящик исключением, в реальных результатах `sync_all_accounts` сработало, R2 подтвердил один показ).

**Расхождение для внимания.** `02-VERIFICATION-EVIDENCE.md` пишет «Находок со статусом open нет»; это верно для `01-REVIEW-DISPOSITION.md` (14 строк fixed, 6 info в deferred). Для `02-REVIEW-DISPOSITION.md` все 11 строк `open`: решение владельца ещё не принято. Это не провал критерия, но фаза «закрыта» с неразрешёнными находками собственного ревью.

## Остаточные риски (из evidence, подтверждены)

- Плавающий тест `test_concurrent_confirmations_isolation` (`database is locked`) вне фазы, записан в `deferred-items.md`; в этой верификации собственный гейт прошёл с первого раза.
- Три находки shield `--all` в `config/persona.yaml` (слова NDA как данные, публичный репозиторий): решение отнесено к Phase 8. Единственный обход hook (`--no-verify`, коммит `95812d1`, по разрешению владельца, D-21) задокументирован; новых находок он не добавил.
- Неотслеживаемый `.watchdog_disabled` в chat-app.

## Нужна проверка человеком

1. **Решения по предупреждениям ревью WR-01..WR-06** (disposition все open). Ожидается: для каждой записано исправить, отложить или принять риск; WR-01 и WR-02 лучше закрыть малой задачей `/gsd-quick` до Phase 8.
2. **Живой web-аудит** после рестарта `chat-app.service` (заморожен). Ожидается: 3 известные находки по запретным словам пространства плюс замороженные, других нет. Почему не автоматически: рестарт сервиса только по разрешению владельца; код проверен ASGI-тестами.

## Резюме пробелов

Критерии успеха не провалены: провальных истин, отсутствующих артефактов и неподключённых связей нет. Остаются два риска, которые стоит закрыть: WR-01 (валидатор схемы не защищает от пробельных слов NDA, воспроизведено) и WR-02 (непригодный путь NDA-пространства даёт публичный профиль). Оба срабатывают только на ошибочных данных владельца и не затрагивают текущую персону, поэтому записаны как gap-risk, а не как невыполненный критерий. Статус `human_needed` выставлен из-за двух пунктов выше, а не из-за найденного дефекта цели.

---

_Проверено: 2026-10-10_
_Верификатор: Claude (gsd-verifier)_
