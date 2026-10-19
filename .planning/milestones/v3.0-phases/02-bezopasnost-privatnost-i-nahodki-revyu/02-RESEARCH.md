# Phase 2: Безопасность, приватность и находки ревью - Research

**Researched:** 2026-10-10
**Domain:** Внутренняя безопасность платформы (библиотека `assistant_shared/security`, CLI-обёртка shield, HITL-защита диалога бота, уведомление о внешней обработке почты ИИ). Внешних библиотек и внешних API фаза не вводит, поэтому вся работа выполнена чтением кода и пробными прогонами тестов.
**Confidence:** HIGH (код прочитан целиком; влияние на chat-app подтверждено пробным прогоном его pytest против копии библиотеки в scratchpad)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Защита «очисти диалог» (SAFE-01)**
- **D-01:** Единственный путь очистки памяти — HITL-карточка `/clear` (`handle_cmd_clear_dialog` → `dlg:confirm_clear` / `dlg:cancel_clear` → кнопка «Восстановить»). `SecretaryDialogEngine` (`src/brain/secretary_dialog.py:611`) больше не вызывает `clear_dialog_history` сам.
- **D-02:** Текстовые фразы («очисти диалог», «забудь контекст», «сброс») и любое сообщение, смысл которого ведёт к очистке памяти (в том числе маршрут `clear_dialog` из intent_router), **ничего не очищают**. Бот отвечает по-русски предупреждением: очистка стирает память диалога, чтобы подтвердить её, нужно **вручную следующим сообщением** ввести команду со слэшем (`/clear`). Карточку из текста не показываем.
- **D-03:** Слэш-команды `/clear` и `/reset` идут через существующую HITL-карточку без изменения её поведения (в т.ч. «контекст уже пуст» без карточки).
- **D-04:** Поведение закреплено тестами: текстовое сообщение боту не меняет `bot_dialog_history`, выдаёт предупреждение; `/clear` показывает карточку; без подтверждения история остаётся.
- **D-05:** Ночной сброс 04:00 (`archive_dialog_history`) в фазу не входит. Предупреждение о ежесуточном сбросе памяти показывается при онбординге — это Phase 8 (см. Deferred).

**NDA-режим CLI-аудита из данных (SECF-01)**
- **D-06:** Источник правил — `workspaces` из `config/persona.yaml` (`clearance`, `forbidden_remote_substrings`, `forbidden_keywords`, remote/путь). Боевую БД аудит не открывает. Библиотека `assistant_shared/security` остаётся чистой от домена: `scripts/security_shield.py` (wrapper в assistant-core) загружает персону и передаёт правила в `audit_repository`; точный интерфейс выбирает планировщик.
- **D-07:** Репозиторий сопоставляется с пространством по полям пути/remote в данных. Подстрока `"tydex" in path` в `auditor.py:210` и литерал личного аккаунта в `auditor.py` удаляются.
- **D-08:** Fail-closed: данные workspaces недоступны или битые → красный итог (ошибка). Данные есть, но репозиторий не сопоставлен ни с одним пространством → публичная проверка с явным предупреждением в выводе. Для `restricted_nda` без правил remote — как сейчас, нарушение.
- **D-09:** `CORPORATE_NDA_KEYWORDS` в `patterns.py` удаляется. Ключевые слова NDA берутся только из `forbidden_keywords` пространства. Список ложных срабатываний shield может только сокращаться (не расти).
- **D-10:** Тест паритета NDA (`tests/test_nda_script_parity.py`) переписывается и не читает литерал из исходника. Новый тест проверяет, что в `assistant_shared/security` нет подстроки «tydex» и литерала личного аккаунта.

**Общая функция сканирования Web/CLI (SECF-02)**
- **D-11:** Общая функция `scan_file_content` живёт в `assistant_shared/security`. Построчное и многострочное сканирование (секреты, `forbidden_keywords`) в одном месте; `audit_path` (web) и CLI-путь оба вызывают её.
- **D-12:** `forbidden_keywords` едут внутри `NdaRemoteRule` (`nda_rule_for(ws)` читает их из того же словаря пространства, который chat-app уже передаёт из `db.py`). Исследователь проверяет, что правка chat-app не нужна; если нужна — только `/gsd-quick` в chat-app, pytest chat-app остаётся зелёным.
- **D-13:** Паритет проверяется синтетическими файлами во временном git-репозитории: чистый файл, файл с секретом, многострочный секрет (PEM), ключевое слово NDA, запрещённый файл (`.env`), пустой файл. `audit_repository` и `audit_path` дают одинаковый набор нарушений. Секреты в тесте собираются из частей, чтобы не срабатывал shield.

**Предупреждение об обработке почты ИИ (PRIV-01)**
- **D-14:** Текст предупреждения и список сервисов (Gemini и др.) — поле в `config/persona.yaml` (модель Pydantic `extra=forbid` в `src/persona/models.py`). В коде — нейтральный запасной текст по умолчанию на русском. В тексте: содержимое писем обрабатывается внешними ИИ-сервисами, разработчик не отвечает за утечку секретов и личной информации.
- **D-15:** Места показа: (1) блок внизу `/help` (`handle_cmd_help`, `src/notifier/bot_handler.py:426`); (2) старт сборщика почты — запись в журнале и одно сообщение в Telegram при первом успешном запуске `email_collector`, флаг «показано» хранится в БД (на временной БД в тестах); (3) `scripts/auth_google.py` и подсказки `.env.example`.
- **D-16:** Только информирование, без кнопки «принимаю» и блокировки сбора. Мастер подключения почты и согласие — Phase 8/9.

### Claude's Discretion
- Точное устройство интерфейса `audit_repository` и передачи правил из wrapper; имена функций и модулей.
- Как определять «смысл ведёт к очистке памяти» для D-02 (детерминированный список фраз и маршрут `clear_dialog` или LLM-намерение); достаточно покрыть существующие триггеры и маршрут `intent_router`.
- Имя поля в `persona.yaml` и схема хранения флага показа (в рамках существующих таблиц или миграции в assistant-shared — выбрать минимальное; боевая БД не трогается).
- Порядок и разбиение на планы.

### Deferred Ideas (OUT OF SCOPE)
- Предупреждение при онбординге о ежесуточном сбросе памяти диалога в 04:00 — Phase 8 (мастер первого запуска).
- Уведомление после ночного сброса с возможностью восстановить — новая возможность, в бэклог.
- Кнопка «прочитал и принимаю» для PRIV-01 — Phase 8/9 (онбординг, мастер почты).
- Мастер подключения почты — Phase 9.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SECF-01 | NDA-режим CLI-аудита из данных `workspaces`; нет подстроки пути «tydex» и литерала личного аккаунта в библиотеке; тест паритета NDA не читает литерал из исходника | Раздел «Паттерн A»: сопоставление репозитория с пространством по path/remote, правила из `WorkspaceConfig.model_dump()`, делегирующие обёртки; раздел «Влияние на три репозитория» (удаление `CORPORATE_NDA_KEYWORDS` ломает 13 тестов chat-app + 1 файл при сборе, доказано пробным прогоном) |
| SECF-02 | Общая функция сканирования файла для web и CLI; web проверяет `forbidden_keywords`; паритет на синтетических фикстурах, включая многострочные | Раздел «Паттерн B»: `scan_file_content` + структурные `Finding`, перечень реальных расхождений web/CLI, **уточнение D-12** (правка chat-app всё же нужна) |
| SAFE-01 | Решение по «очисти диалог» записано и закреплено тестом | Раздел «Паттерн C»: фактические пути очистки (3 места), список тестов к переписыванию |
| PRIV-01 | Предупреждение по-русски в `/help` и при подключении почты, текст из данных персоны | Раздел «Паттерн D»: поле `privacy` в `PersonaConfig`, функция `email_ai_notice`, хранение флага без миграции, три точки показа |
</phase_requirements>

## Summary

Фаза состоит из четырёх узких изменений, но два из них пересекают границы репозиториев. Библиотека безопасности `/opt/assistant-shared` подключена в виде editable-пакета и к venv assistant-core, и к venv chat-app (`assistant_shared.__file__` в обоих указывает на `/opt/assistant-shared/assistant_shared/__init__.py`), поэтому любая правка библиотеки мгновенно действует на тесты chat-app. Пробный прогон полного pytest chat-app против копии библиотеки без `CORPORATE_NDA_KEYWORDS` и без подстроки «tydex» дал `13 failed, 232 passed` и ещё одну ошибку сбора модуля `test_security_shared.py`. Без координированной правки chat-app через `/gsd-quick` критерий «pytest chat-app остаётся зелёным» невыполним.

Главный архитектурный вывод: **D-12 в исходной формулировке неполон.** Web-эндпоинты chat-app вызывают `audit_path(p_path, nda_rule=nda_rule_for(p))` по одному пространству, а `nda_rule_for` возвращает `None` для не-NDA пространств. Слова NDA нужно искать именно в ПУБЛИЧНЫХ репозиториях (в NDA-репозитории они законны, это закреплено chat-app тестом S05). Значит, слова NDA-пространства должны попасть в аудит других пространств, а этого нельзя достичь без правки двух строк в `security.py` chat-app. Правка chat-app нужна и по этой причине, и из-за тестов, и из-за обёртки `scripts/security_shield.py` chat-app, которая импортирует удаляемое имя.

Для SAFE-01 важная находка: **текстовая фраза «очисти диалог» в реальном боте уже ведёт на HITL-карточку** (маршрутизатор перехватывает точные фразы раньше диалога секретаря). Небезопасная прямая очистка в `secretary_dialog.py:611` достижима лишь в узких случаях, но D-01/D-02 всё равно требуют убрать её и заменить предупреждением на всех текстовых и голосовых путях. Это меняет поведение, поэтому часть существующих тестов нужно переписать.

**Primary recommendation:** Делить фазу на пять планов: (1) ядро сканирования в `assistant-shared` с новым API (волна 1); (2) задание `/gsd-quick` для chat-app, подготовленное заранее и проверенное против копии библиотеки (волна 2); (3) переключение обёртки assistant-core, удаление `CORPORATE_NDA_KEYWORDS` и переписанные тесты (волна 3, сразу после chat-app); (4) SAFE-01 и (5) PRIV-01 независимо от остальных (волна 1). Закрыть фазу VERIFICATION.md с достижимостью и рестартом только по разрешению владельца.

## Scope gap: находки код-ревью Phase 1 (требует решения до планирования)

**CONTEXT.md не упоминает 20 находок ревью Phase 1**, хотя название фазы содержит «находки ревью», STATE.md называет их «входом планирования Phase 2», а `01-REVIEW-DISPOSITION.md` фиксирует, что владелец отложил все 20 именно «to Phase 2 (security & review findings)». Четыре требования фазы (SECF-01/02, SAFE-01, PRIV-01) эти находки не покрывают. [VERIFIED: .planning/phases/01-sobstvennyy-geyt-kachestva-assistant-core/01-REVIEW-DISPOSITION.md:95-104, .planning/STATE.md:109-112]

Дополнительные задачи, которые STATE.md закрепляет за Phase 2 решениями владельца 2026-10-09: отказ адаптера cross-AI при подмене `scripts` симлинком (T-uo4-02, правка в chat-app через `/gsd-quick`) и `fastapi` в зависимостях `assistant-shared` (`hitl.decorators`, «Phase 2/3»). [VERIFIED: .planning/STATE.md:98-100]

Рекомендация планировщику и оркестратору: **не включать находки в основные четыре плана молча.** Спросить владельца через опрос (правило памяти: вопросы через AskUserQuestion), предложив: (а) включить только CR-01 как отдельный небольшой план (критическая находка: `sync_aadhk_from_drive` берёт имя файла из ответа Drive и пишет от root по `Path(f"/opt/chat-app/uploads/gdrive_{remote_name}")`, проверено чтением кода, `src/connectors/gdrive/client.py:118-135` и `:256-262`); (б) включить CR-01 плюс WR-05/WR-08/WR-09 и T-uo4-02 (безопасность выкатки и адаптера); (в) оставить всё в бэклоге с явной записью в ROADMAP. Моё предложение: вариант (а), потому что CR-01 это запись от root за пределы каталога и он соответствует «security-логика только ужесточается». Остальное в этом исследовании не разбирается.

## Architectural Responsibility Map

Приложение не веб-многоуровневое; ярусы заменены слоями проекта (`.claude/CLAUDE.md`, раздел Architecture).

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Сканирование файла на секреты и слова NDA (`scan_file_content`) | Общая библиотека `/opt/assistant-shared/assistant_shared/security` | — | Одна реализация для web и CLI (SEC-01); библиотека без домена |
| Загрузка правил NDA из `persona.yaml` | Обёртка `scripts/security_shield.py` assistant-core + `src/persona/loader.py` | — | D-06: домен приходит параметром; yaml не должен попасть в зависимости библиотеки |
| Сопоставление репозитория с пространством, режим NDA/публичный | Библиотека (`rules.py`), чистая функция над списком словарей | Обёртка передаёт данные | Одинаково для CLI и (по желанию) web; данные, не литералы |
| Web-аудит (`/security/overview`, `/security/audit`) | chat-app `backend/app/api/v1/security.py` (потребитель) | Библиотека | Передаёт слова NDA других пространств; правка только через `/gsd-quick` |
| Защита очистки диалога (текст -> предупреждение, `/clear` -> карточка) | `src/notifier/bot_handler.py` (интерфейс) | `src/brain/secretary_dialog.py`, `src/brain/intent_router.py` | HITL-карточка живёт в слое бота; движок диалога не должен менять память |
| Текст предупреждения PRIV-01 | `config/persona.yaml` + `src/persona/` (данные) | `bot_handler`, `main.py`, `scripts/auth_google.py` (показ) | Данные персоны, не хардкод (D-14) |
| Флаг «предупреждение показано» | `src/storage/db.py` (SQLite) | — | D-15: хранится в БД; боевая БД в тестах не трогается |

## Standard Stack

### Core
Новых зависимостей фаза не вводит. Правило проекта: «Новые зависимости — только с одобрения владельца» [VERIFIED: .claude/CLAUDE.md, раздел Constraints]. Всё нужное уже установлено.

| Библиотека | Версия | Назначение | Почему |
|------------|--------|------------|--------|
| Python | 3.12 (venv `/opt/assistant-core/.venv`) | Среда | Цель проекта |
| `assistant-shared` (editable) | 0.1.0 | Библиотека безопасности и миграции | Владелец схемы и безопасности (CLAUDE.md §5) |
| pydantic >= 2.7 | уже в requirements | Поле `privacy` в `PersonaConfig` (`extra=forbid`) | Существующая схема персоны |
| pyyaml >= 6.0 | уже в core | Загрузка persona.yaml в обёртке | Уже используется `src/persona/loader.py` |
| aiogram 3.31.0 | установлена | Хендлеры бота | Уже используется |
| pytest + pytest-asyncio | установлены | Тесты | `pytest.ini`, `asyncio_mode = auto` |

**Версия aiogram проверена запуском** `aiogram.__version__` -> `3.31.0` [VERIFIED: запуск в .venv assistant-core].

### Alternatives Considered
| Вместо | Можно | Компромисс |
|--------|-------|------------|
| Обёртка assistant-core грузит persona.yaml | Библиотека читает yaml сама | Нарушает D-06 (библиотека без домена) и требует `pyyaml` в зависимостях shared (нужно одобрение владельца); venv chat-app вообще не содержит `yaml` [VERIFIED: запуск `import yaml` в `/opt/chat-app/backend/.venv` -> `ModuleNotFoundError`] |
| Флаг PRIV-01 в новой таблице миграцией `0003` | Существующая таблица | Миграция `0003` занята планом Phase 3 (DAT-01), а первая миграция боевой БД потребует `--backup` раньше срока (см. Pitfall 9) |

**Installation:** не требуется.

**Version verification:** внешних пакетов нет; `npm view` / `pip index` не применимы.

## Package Legitimacy Audit

Фаза не устанавливает внешних пакетов. Проверка `package-legitimacy` не требуется.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| — | — | — | — | — | — | Новых пакетов нет |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                    ┌──────────────── config/persona.yaml (workspaces: clearance, path, remote,
                    │                  forbidden_remote_substrings, forbidden_keywords, message)
                    │                                   │ load_persona() (pydantic extra=forbid)
                    │                                   ▼
 git hook / gate ─► scripts/security_shield.py ──► workspaces = [ws.model_dump() ...]   ── ошибка загрузки ─► rc=1 (fail-closed)
 (staged / --all)   (assistant-core, тонкая)                   │
                                                               ▼
                                       assistant_shared.security.audit_repository(repo, staged_only, workspaces=...)
                                            │  1. repo -> git remote URLs (list_remote_urls)
                                            │  2. match_workspace(path, remotes, workspaces): путь -> remote -> строжайший clearance
                                            │  3. nda_rule_for(ws) / protected_keywords(workspaces)
                                            ▼
          файлы (индекс или рабочая копия) ──► scan_file_content(rel, text, keywords) ──► [Finding]
                                                                    ▲
 chat-app: /security/overview, /security/audit                      │ та же функция
  audit_path(p_path, nda_rule=nda_rule_for(p),                      │
             forbidden_keywords=collect_protected_keywords(ws)) ────┘
                    ▲
 chat-app БД (таблица workspaces, forbidden_keywords JSON)

 Telegram ─► EmailBotHandler.router
    │  Command("clear","reset") ─► handle_cmd_clear_dialog ─► HITL-карточка ─► dlg:confirm_clear ─► clear_dialog_history ─► «Восстановить»
    │  F.text ─► handle_user_text ─► FastIntentRouter ─ action=clear_dialog ─► НОВОЕ: предупреждение «введите /clear вручную» (не карточка)
    │  F.voice ─► handle_user_voice ─ action=clear_dialog ─► НОВОЕ: то же предупреждение
    └─ SecretaryDialogEngine.answer_user_message: фразы очистки ─► НОВОЕ: предупреждение, БД не меняется

 main.run_email_collector_cycle ─ sync_all_accounts ─ успешно подключён хотя бы один ящик? ─ флаг в БД не стоит? ─► журнал + одно сообщение Telegram ─► флаг
 /help ─► handle_cmd_help ─► … ─► блок email_ai_notice(current_persona())  (без обращения к self.db)
```

### Recommended Project Structure
```
/opt/assistant-shared/assistant_shared/security/
├── scanner.py      # НОВЫЙ: Finding, scan_file_content (чистая функция, без файлового ввода-вывода)
├── rules.py        # NdaRemoteRule(+forbidden_keywords), nda_rule_for, match_workspace, collect_protected_keywords
├── auditor.py      # audit_path / audit_repository / check_file_content: чтение файлов + форматирование
├── patterns.py     # без CORPORATE_NDA_KEYWORDS
└── runner.py       # без изменений
/opt/assistant-core/
├── scripts/security_shield.py   # реальная обёртка: load_persona -> workspaces -> audit_repository
├── src/persona/models.py        # + PrivacyConfig, PersonaConfig.privacy
├── src/persona/notices.py       # НОВЫЙ: email_ai_notice(persona) -> str (запасной текст по умолчанию)
├── src/brain/dialog_safety.py   # НОВЫЙ: CLEAR_DIALOG_TRIGGERS, CLEAR_DIALOG_TEXT_WARNING
└── tests/ …                     # см. Validation Architecture
```
Каталог `src/persona` не импортирует `src.config` (docstring пакета), поэтому `notices.py` можно вызывать из `scripts/auth_google.py` без загрузки `.env` [VERIFIED: src/persona/__init__.py:1-4].

### Паттерн A: NDA-режим из данных (SECF-01)

**Что:** `audit_repository(repo_path, check_staged_only=True, *, workspaces)` получает список словарей той же формы, которую уже используют `nda_rule_for` и chat-app (`id, path, remote, clearance, forbidden_remote_substrings, forbidden_keywords, remote_violation_message`). Обёртка строит его из `WorkspaceConfig.model_dump()`.

**Проверенные факты (дословно):**
- `auditor.py:210`: `is_tydex_repo = "tydex" in str(repo_path).lower()`; `:224`: `if "github.com/dimamuhannad" in origin_norm:`; `:213` печатает `'🔒 RESTRICTED (Tydex NDA)'`; `:225` содержит `"CRITICAL: Tydex private project remote points to personal public account (DimaMuhannad)!"`. [VERIFIED: /opt/assistant-shared/assistant_shared/security/auditor.py:210-225] Литералы есть не только в проверке, но и в двух строках вывода.
- `patterns.py:35`: `_KW_PREFIX = "tydex_"` и `patterns.py:38`: `CORPORATE_NDA_KEYWORDS: list[str] = [`. Подстрока «tydex» присутствует и здесь, поэтому удалять нужно весь блок констант (`patterns.py:32-42`). [VERIFIED: patterns.py:32-42]
- `rules.py`: `nda_rule_for` возвращает правило только при `ws.get("clearance") != "restricted_nda"` -> `None`; `NdaRemoteRule` имеет два поля (`forbidden_remote_substrings`, `violation_message`). [VERIFIED: rules.py:11-30]
- `WorkspaceConfig` (pydantic, `extra="forbid"`) содержит `path`, `remote`, `clearance: Literal["public", "internal", "restricted_nda"]`, `forbidden_remote_substrings`, `forbidden_keywords`, `remote_violation_message`; валидатор `_nda_requires_rules` требует для `restricted_nda` непустые оба списка. [VERIFIED: src/persona/models.py:49-76]
- В данных persona.yaml у NDA-пространства стоит `forbidden_remote_substrings: ["github.com/DimaMuhannad"]`, `clearance: restricted_nda`, `path: /opt/work-tydex`, `remote: "git@tydex-vps:tydex/optics-firmware.git"`; `forbidden_keywords` содержит три слова (значения здесь намеренно не приводятся: они срабатывают на shield). [VERIFIED: config/persona.yaml:33-45]

**Сопоставление репозитория с пространством (D-07), рекомендуемый алгоритм:**
1. `repo = repo_path.resolve()`; кандидат, если `repo == Path(ws.path).resolve()` либо `repo` лежит внутри `ws.path`.
2. Иначе кандидат, если любой URL из `list_remote_urls(repo)` после `normalize_remote` равен `normalize_remote(ws.remote)`.
3. Несколько кандидатов -> берётся самый строгий clearance (`restricted_nda` > `internal` > `public`). Это fail-closed: спорное считается более защищаемым.
4. Нет кандидатов, данные есть -> публичная проверка и строка-предупреждение `   ⚠️ …` в выводе.
5. `workspaces is None` -> `rc=1` (данные недоступны, D-08 буквально). Явный пустой список `()` означает «данные есть, пространств нет» и допустим для тестов.

**Режим NDA:** для сопоставленного `restricted_nda` берутся `nda_rule_for(ws)`: все remote и push-URL проверяются на `forbidden_remote_substrings` (как сейчас в `audit_path`, CR-05), сбой git -> нарушение, пустые подстроки -> нарушение `CRITICAL` (как `audit_path:133-135`). Слова NDA в таком репозитории не ищутся. Для остальных режимов слова ищутся (см. паттерн B).

**Вывод, который нельзя ломать (контракты потребителей):**
- Гейт разбирает только строки находок вида «пробелы, значок 🚨, пробел, тело», заголовок и предупреждения не разбираются: `_SHIELD_LINE_RE = re.compile(r"^\s+\U0001F6A8 (?P<body>.*)$")` [VERIFIED: scripts/gate.py:310]. Поэтому **предупреждение о несопоставленном репозитории печатать с `⚠️`, не с 🚨**, иначе гейт увидит «(нераспознано)» и покраснеет.
- Тела находок сохраняют прежние префиксы, которые разбирает гейт: `Forbidden file pattern committed:`, `CRITICAL`, `<путь>:<строка> - Found potential <имя>`, `<путь>:<строка> - Found proprietary corporate keyword`, `… - Read error` [VERIFIED: scripts/gate.py:337-356].
- В заголовке должны остаться слова `RESTRICTED` и `PUBLIC` (chat-app тест S01 их ищет) [VERIFIED: /opt/chat-app/backend/tests/test_nda_equivalence.py:217-229]; текст ошибки remote берётся из `violation_message` данных (в persona.yaml он начинается с `CRITICAL:`), запасной `DEFAULT_REMOTE_VIOLATION` тоже начинается с `CRITICAL:` [VERIFIED: rules.py:6].

**Замороженный список гейта:** `KNOWN_SHIELD_FALSE_POSITIVES` держит `("config/persona.yaml", "nda-keyword"): 3` [VERIFIED: scripts/gate.py:60-65]. После перехода на данные `forbidden_keywords` в этой же строке persona.yaml по-прежнему даёт ровно три находки (одна строка, три слова), то есть список не растёт и не устаревает. Любой новый файл со словами NDA (в том числе этот документ, план, SUMMARY) покрасит гейт, **слова нельзя печатать ни в .planning, ни в тестах**.

### Паттерн B: общая функция сканирования (SECF-02)

**Сигнатура (рекомендация):**
```python
# assistant_shared/security/scanner.py  (чистая функция: текст на входе, находки на выходе)
@dataclass(frozen=True)
class Finding:
    kind: str    # "secret" | "keyword" | "forbidden_file" | "read_error"
    name: str    # имя шаблона секрета, слово или имя файла
    line: int    # 0 для forbidden_file / read_error

def scan_file_content(rel_path: str, text: str, *, keywords: Sequence[str] = ()) -> list[Finding]: ...
def format_cli(display_path: str, f: Finding) -> str   # «{path}:{line} - Found potential {name}» и т.д. (формат сохраняется)
def format_web(rel_path: str, f: Finding) -> str       # «{rel}: Обнаружен потенциальный секрет ({name})» и т.д. (формат сохраняется)
```

**Реальные расхождения web и CLI (прочитано в `auditor.py`), которые общая функция обязана устранить:**

| # | CLI (`check_file_content`/`check_index_content`) | Web (`audit_path`) | Решение |
|---|----|----|----|
| 1 | Запрещённое имя файла -> одна находка, содержимое НЕ сканируется (`auditor.py:70-72`) | Запрещённое имя -> находка И дальше сканирует содержимое (`:174-185`) | Единое правило «короткое замыкание». Его закрепляют тесты chat-app S07 (`.env` с токеном -> ровно 1 находка) и N06 |
| 2 | Построчно, одна находка на пару (строка, шаблон) | Весь файл целиком, одна находка на пару (файл, шаблон) | Один проход по всему тексту через `pattern.finditer`, номер строки по смещению, дедупликация по (строка, шаблон). Это надмножество построчного поиска (в шаблоне Generic Bearer есть `\s*`, он может пересекать строки) |
| 3 | Слова NDA ищутся, если репозиторий не NDA (`is_public_repo`) | Слова NDA не ищутся совсем (подтверждено: в `audit_path` нет обращения к `CORPORATE_NDA_KEYWORDS`) | Ищутся по правилу «не NDA-репозиторий» |
| 4 | Читает версию из git-индекса при staged-режиме (CR-03) | Рабочая копия по `git ls-files` | Источник текста остаётся разным (это чтение, не сканирование), результат сканирования функции тот же |
| 5 | Лимита числа файлов нет | `max_files=5000`, усечение = нарушение | Не относится к функции сканирования; оставить как есть |
| 6 | Ошибка чтения -> `… - Read error: …` | `… ошибка чтения (…)` | Оставить два форматтера |

**Важно для chat-app:** тест S09 подменяет `open` в пространстве имён модуля `assistant_shared.security.auditor` (`monkeypatch.setattr(shared_auditor, "open", boom, raising=False)`) и ожидает ровно одну находку `Read error` [VERIFIED: /opt/chat-app/backend/tests/test_nda_equivalence.py:266-279]. Поэтому **чтение файла (`open`) должно остаться в `auditor.py`**, а `scanner.py` не должен читать файлы. Если читать в другом модуле, S09 перестанет проверять то, что проверяет.

**Слова NDA и уточнение D-12 (главный вывод):**
- Правило «слова NDA запрещены в публичных репозиториях, а в NDA-репозитории разрешены» закреплено тестами S04 (каждое слово даёт ровно одну находку при `is_public_repo=True`) и S05 (ноль находок при `is_public_repo=False`) [VERIFIED: test_nda_equivalence.py:248-272].
- Chat-app вызывает аудит по одному пространству: `res = await asyncio.to_thread(audit_path, p_path, nda_rule=nda_rule_for(p))` (две точки: `security.py:39` и `security.py:81`), а для публичного `p` `nda_rule_for(p)` равно `None` [VERIFIED: /opt/chat-app/backend/app/api/v1/security.py:39,81; rules.py:19-21].
- Поэтому если слова NDA «ехать» только внутри `NdaRemoteRule` (D-12 буквально), то правило получает лишь NDA-пространство, а слова нужно искать в ДРУГИХ пространствах: web-аудит публичных пространств слов так и не увидит. **Требуемая правка:** `NdaRemoteRule` получает необязательное поле `forbidden_keywords: tuple[str, ...] = ()` (значение по умолчанию сохраняет конструктор `NdaRemoteRule(forbidden_remote_substrings=..., violation_message=...)` из chat-app теста `test_shield_regressions.py:167`), библиотека даёт `collect_protected_keywords(workspaces) -> tuple[str, ...]` (объединение слов из всех NDA-правил), `audit_path(..., forbidden_keywords=())` ищет их при `nda_rule is None` и игнорирует при NDA. В chat-app меняются две строки вызова на `audit_path(p_path, nda_rule=nda_rule_for(p), forbidden_keywords=collect_protected_keywords(workspaces))`. Таблица `workspaces` chat-app уже хранит и отдаёт `forbidden_keywords` (`db.py:58,69`), то есть данных достаточно, миграция не нужна [VERIFIED: /opt/chat-app/backend/app/db.py:56-70].
- Рекомендация (в рамках усиления): сравнение слов без учёта регистра (`casefold` с обеих сторон). Это только добавляет находки, существующие тесты (точные слова) не затрагивает.

### Паттерн C: защита «очисти диалог» (SAFE-01)

**Фактические пути очистки памяти (прочитаны, не по документации):**
1. Slash: `self.router.message(Command("clear", "reset"))(self.handle_cmd_clear_dialog)` [VERIFIED: src/notifier/bot_handler.py:411] -> карточка с `dlg:confirm_clear` / `dlg:cancel_clear` (`:1882-1883`).
2. Текст: `handle_user_text` -> `intent_router.route` -> `elif route_res.action == "clear_dialog": await self.handle_cmd_clear_dialog(message)` [VERIFIED: bot_handler.py:1430-1431]. Здесь «очисти диалог» сегодня показывает карточку (то есть защита фактически есть).
3. Голос: тот же маршрут в `handle_user_voice` [VERIFIED: bot_handler.py:2583-2584]; у голосового сообщения `message.text` пуст.
4. Движок диалога: `if cleaned_text.lower() in ("/clear", "/reset", "очисти диалог", "забудь контекст", "сброс"):` затем `await self.db.clear_dialog_history(user_id)` и ответ «Контекст диалога успешно очищен» [VERIFIED: src/brain/secretary_dialog.py:610-613]. Единственный вызов `answer_user_message` в рантайме: `bot_handler.py:2365`; ещё один в `scripts/test_secretary_simulation.py:221` (не тест pytest).
5. Триггеры маршрутизатора: `if lower in ("/clear", "сброс", "очисти диалог", "забудь контекст", "/reset"):` -> `action="clear_dialog"` [VERIFIED: src/brain/intent_router.py:141-143]. LLM-маршрут тоже способен вернуть `clear_dialog` (оно входит в `VALID_ACTIONS`, `intent_router.py:41`), то есть для произвольной формулировки («очисти, пожалуйста, диалог») карточка сегодня тоже показывается.
6. Инструментов function calling для очистки нет (поиск `clear|forget|wipe|delete_memory` по `src/brain/tools_schema.py` ничего не дал).

**Рекомендуемая реализация:**
- Новый модуль `src/brain/dialog_safety.py` с константами `CLEAR_DIALOG_TRIGGERS` (единый список для маршрутизатора и движка) и `CLEAR_DIALOG_TEXT_WARNING` (русский текст: очистка стирает память диалога, чтобы подтвердить, введите вручную следующим сообщением `/clear`). Модуль лежит в `src/brain` и не импортирует адаптеры (контракт `brain-no-adapters`).
- `secretary_dialog.py`: ветку заменить на возврат предупреждения без обращения к БД; это покрывает и `/clear`, `/reset` при прямом вызове движка.
- `bot_handler.py` в двух ветках `clear_dialog` (текст и голос): вызвать новый метод `_warn_clear_requires_slash(message)` вместо `handle_cmd_clear_dialog`. Исключение: если текст сообщения сам начинается с `/` (защитная ветка для `/clear@бот`), оставить карточку по D-03. Слэш-обработчик `Command("clear","reset")` и колбэки не менять.
- Маршрут `clear_dialog` в `FastIntentRouter` не удалять: `tests/test_fast_intent_router.py:19-32` проверяет его и запись аудита.

**Тесты, которые нужно переписать или добавить:**
- `tests/test_secretary_dialog.py::test_secretary_dialog_clear_command` (строка 44) сегодня утверждает обратное: ответ содержит «очищен» и `len(hist) == 0` для `/clear`. Переписать: история сохраняется, ответ содержит `/clear` как инструкцию. [VERIFIED: tests/test_secretary_dialog.py:44-60]
- Остальные HITL-тесты (`test_hitl_safety_guardrails.py`, `test_bot_hitl_parity.py`) трогают только карточку и колбэки и не меняются [VERIFIED: tests/test_hitl_safety_guardrails.py:42-135].
- Добавить `tests/test_clear_dialog_text_guard.py` (D-04): текст «очисти диалог» через `handler.handle_user_text(msg)` на временной БД с реальным `FastIntentRouter` -> `get_active_dialog_count` не изменился, `msg.answer`/`notifier.send_message` получил предупреждение, карточки (`InlineKeyboardMarkup`) нет; та же проверка для «забудь контекст», «сброс», голосового пути (мок `voice_processor.transcribe`), прямого вызова движка со всеми пятью фразами; `/clear` через `handle_cmd_clear_dialog` по-прежнему показывает карточку, без нажатия «Да» история на месте. Паттерн готовых моков: `MagicMock()` для `bot`/`msg`, `AsyncMock()` для `answer`, `EmailBotHandler(bot=MagicMock(), db=db, allowed_user_id=user_id)` [VERIFIED: tests/test_hitl_safety_guardrails.py:42-66].
- Тест достижимости: в `handler.router.message.handlers` присутствует обработчик `handle_user_text` под `F.text` и `handle_cmd_clear_dialog` под `Command("clear","reset")`.

### Паттерн D: предупреждение PRIV-01

**Поле в персоне.** Добавить в `src/persona/models.py` модель `PrivacyConfig` (`extra="forbid"`, `frozen=True`) и поле `privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)` в `PersonaConfig` (по образцу `ui: UiConfig = Field(default_factory=UiConfig)` на `models.py:261`). Предлагаемые поля: `email_ai_notice: str | None` (полный текст, переопределяет шаблон) и `external_ai_services: list[str]` (список, подставляется в шаблон). Поле необязательное, значит `tests/synthetic_persona.py` (копия, дрейф которой проверяет гейт) менять не нужно. Chat-app читает персону выборочно (`persona.py:32` берёт `persona["ui"]["texts"]`), новый ключ в `config_json` ему не мешает [VERIFIED: grep по /opt/chat-app/backend/app/api/v1/persona.py].

**Функция текста.** `src/persona/notices.py::email_ai_notice(persona) -> str`: если `persona.privacy.email_ai_notice` задан, возвращает его; иначе нейтральный запасной текст по-русски, куда подставлен список сервисов («…внешними ИИ-сервисами (Gemini и др.)…»). В коде не должно быть токенов владельца (организации, имена): `tests/test_hardcode_scanner.py` ищет токены профиля в отслеживаемом коде вне allowlist, baseline не может расти [VERIFIED: tests/test_hardcode_scanner.py:1-12]. Слова «Gemini» в запасном тексте допустимо держать только если они берутся из `external_ai_services`; в самом коде -- нейтральная формулировка.

**Точки показа и ограничения:**
1. `/help`: `handle_cmd_help` (`bot_handler.py:426`) уже собирает текст из `current_persona()` через `_get_univ_name()` и т.п. Блок добавить в конец. **Ограничение, которое уже закреплено тестом:** `tests/test_deploy_script.py::test_help_handler_does_not_touch_db` разбирает AST и краснеет, если `handle_cmd_help` обращается к `self.db`/`self.database`, `Database`, `sqlite3`, `aiosqlite` [VERIFIED: tests/test_deploy_script.py:1356-1373]. Текст брать только из персоны, без БД.
2. Сборщик почты: `run_email_collector_cycle(db, email_collector, notifier)` (`src/main.py:199-230`). После успешного `sync_all_accounts` проверить флаг; если не стоит и подключён хотя бы один ящик, записать в журнал, отправить `notifier.send_message(text)` и поставить флаг. Критерий «подключён»: результат аккаунта — словарь, у которого `status` не начинается с `skipped` (пропуск без учётных данных возвращает `{"account": account_id, "status": "skipped_no_creds"}`, у Gmail `skipped_no_token`) [VERIFIED: src/collector/email_collector.py, grep `skipped_no_creds`, `skipped_no_token`]. Существующий тест `test_run_email_collector_cycle_deduplication` вызывает цикл с `AsyncMock` уведомителем и результатом `{"mailru": {"inserted": 1}}`; он считает только `send_actionable_email_card`, поэтому новое сообщение его не ломает [VERIFIED: tests/test_email_reply_workflow.py:336-380].
3. `scripts/auth_google.py` и `.env.example`: в скрипте добавить вывод текста перед запуском OAuth (скрипт автономный, использует абсолютные пути; для импорта `src.persona.notices` нужно добавить корень репозитория в `sys.path`); в `.env.example` сейчас нет блока почты, добавить закомментированный блок с русским предупреждением рядом с переменными ящиков (`MAILRU_EMAIL`, `GMAIL_EMAIL` объявлены в `src/config.py:67,75`).

**Хранение флага без миграции (Claude's Discretion).** Общей таблицы «ключ-значение» в схеме нет: в `0001_initial_schema.sql` и `0002_pending_confirmations.sql` отсутствуют `settings`/`kv`-таблицы [VERIFIED: grep `CREATE TABLE` по двум миграциям]. Варианты:

| Вариант | За | Против |
|---------|----|----|
| A. Миграция в assistant-shared | Чистая схема | Номер `0003` закреплён за DAT-01 Phase 3; миграция боевой БД при рестарте тянет `--backup` раньше Phase 3, а проверки WR-08/WR-09 (права, `/var/tmp`) ещё отложены [VERIFIED: .planning/STATE.md:111-114] |
| B. Строка в `daily_primed_context` с зарезервированным ключом `notice:email_ai` | Нулевое изменение схемы; таблица читается только по ключу (`db.py:2717,2728`) | Таблица предназначена для дат; решение временное |
| C. Флаг только в памяти процесса | Просто | Нарушает D-15 (после каждого рестарта сообщение повторяется) |

**Рекомендация:** B, спрятанный за двумя методами `Database.has_notice_shown(key)` / `Database.mark_notice_shown(key)`, чтобы Phase 3 могла перенести флаг в настоящую таблицу одной правкой. Отметить как [ASSUMED] для подтверждения владельцем (A1 в журнале допущений).

### Anti-Patterns to Avoid
- **Печатать предупреждения о несопоставленном репозитории с 🚨:** гейт разбирает такие строки как находки и краснеет.
- **Тест, содержащий литерал аккаунта или слова NDA:** shield и сканер хардкода сработают; значения брать из данных персоны во время теста.
- **Сопоставление по подстроке пути:** это та же ошибка, что `"tydex" in path`; сравнивать `resolve()`-пути целиком (защита от симлинков и совпадений в чужих именах).
- **Тихий откат к публичному режиму при битой персоне:** D-08 требует красный итог.
- **Обращение к `self.db` из `handle_cmd_help`:** ломает `test_help_handler_does_not_touch_db`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Нормализация remote | Своё сравнение URL | `normalize_remote`, `list_remote_urls` из shared | Уже обрабатывают `ssh://`, scp-форму, порт, алиасы `ssh.github.com`, регистр (CR-05, WR-07) |
| Загрузка и валидация персоны | Разбор yaml в обёртке | `src.persona.loader.load_persona` | `extra=forbid`, понятные ошибки без значений (в файле бывают NDA-слова) |
| Правило NDA пространства | Повторная проверка `clearance` | `nda_rule_for(ws)` | Единственная точка с fail-closed |
| HITL-карточка очистки | Новая карточка для текста | Существующая `/clear` + `restore_dialog_history` | D-01/D-03: единый путь |
| Список русских формулировок очистки | Свои регулярные выражения по разным файлам | Один `CLEAR_DIALOG_TRIGGERS` | Сейчас два расходящихся кортежа в `intent_router.py:141` и `secretary_dialog.py:611` |
| Шифрование/хеш отпечатков | — | Не требуется | Криптография в фазе не нужна |

**Key insight:** вся логика уже есть в виде кусков, но размазана и продублирована (два списка фраз, два пути сканирования, литералы в библиотеке). Задача фазы — свести к одной реализации и вынести литералы в данные, а не писать новое.

## Влияние на три репозитория (кросс-репозиторная матрица)

Библиотека подключена к обоим venv как один и тот же каталог, поэтому любая правка действует на chat-app сразу. Проверено пробным прогоном (копия `/opt/assistant-shared` в scratchpad, из неё убраны `CORPORATE_NDA_KEYWORDS` и условие «tydex», запуск через `PYTHONPATH`, ничего в репозиториях не изменено; `git status` chat-app пуст). Базовая линия на настоящей библиотеке: 117 passed на семи файлах с безопасностью. Итог на копии: **13 failed, 232 passed + ошибка сбора `test_security_shared.py`**.

| Тест chat-app (`/opt/chat-app/backend/tests/`) | Почему падает | Что менять в `/gsd-quick` |
|---|---|---|
| `test_security_shared.py` (весь файл, ImportError) | `from assistant_shared.security import CORPORATE_NDA_KEYWORDS` | Убрать импорт; три теста слов NDA перевести на `custom_keywords` с синтетическим словом |
| `test_nda_equivalence.py::test_s01`, `::test_s02` | NDA-режим по подстроке «Tydex-X» / «tydex-work» в пути | Передавать `workspaces=` с синтетическим NDA-пространством, путь в данных |
| `test_nda_equivalence.py::test_s04`, `::test_s05` | `shield.CORPORATE_NDA_KEYWORDS` | Брать слова из `_owner_nda_workspace()["forbidden_keywords"]` (данные копии БД) |
| `test_shield_regressions.py::test_cr02_flag_first_is_not_treated_as_path` | Запускает `scripts/security_shield.py` chat-app, тот импортирует удалённое имя | Обновить обёртку (см. ниже) |
| `test_shield_regressions.py::test_cr05_cli_checks_all_remotes_and_aliases` | Каталог «tydex-work» больше не NDA | Данные пространства вместо имени каталога |
| `test_persona_api.py::test_persona_current_whitelist_only` | Обёртка отдаёт `CORPORATE_NDA_KEYWORDS` | Брать слова из данных персоны |
| `test_synthetic_persona.py::test_no_real_nda_keywords` | Обёртка отдаёт `CORPORATE_NDA_KEYWORDS` | То же |
| `test_pre_commit_hook.py` (5 тестов) | Хук запускает обёртку, она падает на импорте | Работающая обёртка (делегатор) |
| `test_nda_equivalence.py::test_p03_shield_copies_identical` | Сравнивает sha256 обёрток chat-app и assistant-core; пройдёт сейчас, но упадёт после любой правки одной из них | Заменить проверкой, что обёртка chat-app делегирует в обёртку assistant-core |

Тесты assistant-core, которые придётся менять: `tests/test_nda_script_parity.py` (оба теста, D-10), `tests/test_synthetic_persona.py::test_no_real_nda_keywords` (строка 191, `_load_shield().CORPORATE_NDA_KEYWORDS`).
Тесты `assistant-shared`: `test_security_shared.py` (импорт и три теста слов, комментарий «закреплено до Phase 2 / SECF-01» на строке 33), `test_shield_regressions.py::test_cr05_cli_checks_all_remotes_and_aliases` (комментарий на строке 220, литерал аккаунта в строке 226).

**Обёртки CLI.** Реальная обёртка живёт в assistant-core (D-06, загружает персону, `sys.path` дополняется корнем репозитория, чтобы импортировался `src.persona.loader`). Копии в `/opt/assistant-shared/scripts/` и `/opt/chat-app/scripts/` нельзя сделать такими же: в venv chat-app нет `yaml`, а библиотека не должна читать yaml. Рекомендация: эти две копии становятся тонкими **делегаторами**, которые запускают `<ASSISTANT_CORE_DIR или /opt/assistant-core>/.venv/bin/python <core>/scripts/security_shield.py <те же аргументы>` и возвращают его код возврата; если файла нет — `rc=1` с сообщением (fail-closed). Единственный источник правил — `persona.yaml`; ослабления проверки для chat-app нет (сегодня его обёртка сканирует слова NDA, делегатор сохраняет это).

**Службы.** Процесс `chat-app.service` загружает библиотеку при старте. Реальный эффект правок на живом web-аудите появится только после рестарта chat-app.service, который заморожен до разрешения владельца. Достижимость web-аудита в VERIFICATION.md доказывать тестовым клиентом chat-app (ASGI), а живую проверку делать только после явного разрешения.

**Порядок (рекомендация).** Написать задание `/gsd-quick` для chat-app заранее по образцу `01-CHATAPP-QUICK-BRIEF.md` и проверить его набор тестов против копии новой библиотеки в scratchpad тем же способом (`PYTHONPATH=<копия>`), до того как менять настоящую библиотеку. Затем один скоординированный переход: коммит библиотеки + assistant-core, сразу `/gsd-quick` в chat-app, полный pytest chat-app. Допускается короткое «красное окно» между коммитами; итоговая проверка обязательна.

## Common Pitfalls

### Pitfall 1: Гейт краснеет от предупреждения или слов NDA в документах
**What goes wrong:** строка с 🚨 разбирается как находка; слова NDA в любом отслеживаемом файле — новая находка.
**Why it happens:** гейт берёт только строки находок и сверяет число с замороженным словарём [VERIFIED: scripts/gate.py:55-65, 324-359].
**How to avoid:** предупреждение с `⚠️`; слова NDA и литерал аккаунта нигде не печатать (RESEARCH, PLAN, SUMMARY, тесты); синтетические слова в тестах.
**Warning signs:** гейт пишет «новая находка: … [nda-keyword]» или «(нераспознано)».

### Pitfall 2: Удаление `CORPORATE_NDA_KEYWORDS` ломает потребителей по цепочке
**What goes wrong:** ImportError в обёртках, тестах и git-хуках двух репозиториев.
**How to avoid:** см. кросс-репозиторную матрицу; сначала задание chat-app и проверка на копии библиотеки.
**Warning signs:** `ImportError: cannot import name 'CORPORATE_NDA_KEYWORDS'`.

### Pitfall 3: `monkeypatch` тестов chat-app привязан к модулю `auditor`
**What goes wrong:** перенос чтения файла в `scanner.py` оставляет S09 зелёным по ложной причине или красным.
**How to avoid:** `open(...)` остаётся в `auditor.py` (см. паттерн B).

### Pitfall 4: Хук assistant-core блокирует коммиты при битой персоне
**What goes wrong:** после перехода на данные любая ошибка в `persona.yaml` даёт красный shield и блокирует любой коммит (fail-closed по D-08).
**How to avoid:** это желаемое поведение; сообщение об ошибке должно быть понятным по-русски и не печатать значения (использовать `PersonaConfigError`, как делает loader). Не добавлять обходов.

### Pitfall 5: Несопоставленный репозиторий (assistant-shared, временные репозитории тестов)
**What goes wrong:** `/opt/assistant-shared` нет среди `workspaces` персоны, значит он всегда «публичный с предупреждением»; слова NDA ищутся (это строже, чем «не искать»), удалённый запрет на личный аккаунт для него не действует.
**How to avoid:** принять как решение D-08; отразить в VERIFICATION.md. Не добавлять пространство shared в persona.yaml в этой фазе (расширение данных владельца).

### Pitfall 6: Сканер хардкода профиля и новые тексты
**What goes wrong:** `tests/test_hardcode_scanner.py` ищет токены владельца (организации, имена) в отслеживаемом коде; новый код или тест с такими словами покраснит baseline, который не может расти.
**How to avoid:** тексты нейтральные, значения из персоны; существующий приём разбиения литерала на части (`"ГУ" + "АП"`) использовать только для данных, которым нет замены.

### Pitfall 7: Тестовый токен бота и shield
**What goes wrong:** aiogram проверяет токен (`left.isdigit()` и непустое `right`) [VERIFIED: `validate_token` в aiogram 3.31.0], а shield ловит `\b[0-9]{8,10}:[a-zA-Z0-9_-]{35}\b`.
**How to avoid:** в тестах не создавать настоящий `Bot`; использовать `MagicMock()` как в существующих тестах. Если нужен `Dispatcher.feed_update`, собирать токен с коротким числовым префиксом (до 7 цифр).

### Pitfall 8: Изменение поведения голосового пути
**What goes wrong:** у голосового сообщения `message.text` равен `None`; проверка «текст начинается с /» упадёт на `None.startswith`.
**How to avoid:** `(message.text or "").lstrip().startswith("/")`.

### Pitfall 9: Первый рестарт после фазы пишет в боевую БД
**What goes wrong:** первый успешный цикл почты после рестарта ставит флаг PRIV-01 (запись демона в боевую БД) и отправляет владельцу сообщение.
**How to avoid:** это штатная запись демона, а не смоука; смоук OPS-01 остаётся read-only (`--restart` вызывает его по процедуре). Описать в VERIFICATION.md и предупредить владельца о одном сообщении Telegram после рестарта. Рестарт только по разрешению (CLAUDE.md §3).

### Pitfall 10: Общая функция сканирования и цены регулярных выражений
**What goes wrong:** `finditer` по всему тексту больших файлов дороже построчного `search`.
**How to avoid:** шаблоны простые, `max_files` и ограничения web сохраняются; при необходимости пропускать бинарные данные (в коде уже `errors="ignore"`). Отдельных мер сверх этого не требуется [ASSUMED: оценка нагрузки не измерялась].

## Code Examples

### Сопоставление пространства и выбор набора слов (эскиз для планировщика)
```python
# assistant_shared/security/rules.py  (эскиз; имена на усмотрение планировщика)
_ORDER = {"public": 0, "internal": 1, "restricted_nda": 2}

def match_workspace(repo: Path, remote_urls: Sequence[str], workspaces: Sequence[Mapping[str, Any]]):
    real = repo.resolve()
    hits = []
    for ws in workspaces:
        by_path = False
        try:
            root = Path(ws["path"]).resolve()
            by_path = real == root or root in real.parents
        except (KeyError, OSError):
            pass
        remote = ws.get("remote")
        by_remote = bool(remote) and any(normalize_remote(u) == normalize_remote(remote) for u in remote_urls)
        if by_path or by_remote:
            hits.append(ws)
    return max(hits, key=lambda w: _ORDER.get(w.get("clearance"), 2), default=None)  # неизвестный clearance = строжайший
```
Источник дискретных значений (`clearance`, `path`, `remote`): `src/persona/models.py:49-76` и `config/persona.yaml:33-45`, см. выше.

### Обёртка assistant-core (эскиз)
```python
def _load_workspaces() -> list[dict]:
    try:
        from src.persona.loader import load_persona
        return [ws.model_dump() for ws in load_persona().workspaces]
    except Exception as exc:                      # любой сбой данных = красный итог (D-08)
        print(f"\n❌ SECURITY SHIELD ERROR: данные рабочих пространств недоступны: {type(exc).__name__}\n")
        sys.exit(1)
```
`load_persona()` учитывает `PERSONA_CONFIG_PATH`, значения в сообщениях об ошибках не печатает [VERIFIED: src/persona/loader.py:17-30, 41-62]. Корень репозитория нужно добавить в `sys.path` до импорта (`scripts/` каталог скрипта в `sys.path` по умолчанию, корня там нет).

### Предупреждение вместо очистки (эскиз)
```python
# src/brain/dialog_safety.py
CLEAR_DIALOG_TRIGGERS = ("/clear", "/reset", "очисти диалог", "забудь контекст", "сброс")
CLEAR_DIALOG_TEXT_WARNING = (
    "⚠️ Очистка стирает память диалога. Из обычного сообщения я её не выполняю. "
    "Чтобы подтвердить, введите вручную следующим сообщением команду /clear."
)
```
Значения кортежа — дословно из `intent_router.py:141` и `secretary_dialog.py:611` (порядок и состав совпадают с кортежем движка).

### Паритет web и CLI на синтетических фикстурах (форма теста)
```python
# секреты из частей, чтобы не срабатывал shield; PEM-заголовок собирается как в существующем test_shield_parity.py
pem = "-----BEGIN " + "RSA PRIVATE KEY-----\nbody\n-----END " + "RSA PRIVATE KEY-----\n"
# фикстуры: clean.py, secret.py (Generic Bearer из частей), key.pem.txt (многострочный), kw.txt (синтетическое слово
# из аргумента forbidden_keywords), .env, empty.txt
# сравнивать нормализованные множества (путь, вид, имя) из двух форматов; не сравнивать сырые строки
```
Образец сборки секретов из частей: `tests/test_shield_parity.py` в assistant-shared (строки `"api" + "_key = 'super_secret_token_12345'\n"` и `"-----BEGIN " + "RSA PRIVATE KEY-----"`) [VERIFIED: /opt/assistant-shared/tests/test_shield_parity.py:28-33].

## State of the Art

| Старый подход | Текущий | Когда | Влияние |
|---------------|---------|-------|---------|
| Режим NDA по подстроке пути и литералу аккаунта | Правила из данных пространства | Эта фаза | Универсализация (CLAUDE.md §2) |
| Два независимых сканера (web целиком, CLI построчно) | Одна `scan_file_content` | Эта фаза | Паритет и меньше мест для расхождений |
| Очистка памяти из движка диалога | Только `/clear` с карточкой | Эта фаза | Нет необратимых действий без подтверждения |

**Deprecated/outdated:** `CORPORATE_NDA_KEYWORDS`, `is_tydex_repo`, ветка очистки в `SecretaryDialogEngine`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Флаг PRIV-01 хранить строкой `daily_primed_context` с зарезервированным ключом, без миграции | Паттерн D | Владелец может предпочесть чистую таблицу; цена — перенос в Phase 3 |
| A2 | Для `workspaces=None` библиотека возвращает `rc=1` (строгая трактовка D-08), а `()` означает «данных нет, пространств нет» | Паттерн A | Если нужна мягкая трактовка, придётся меньше править тестов, но слабее fail-closed |
| A3 | Копии обёртки в shared и chat-app становятся делегаторами в обёртку assistant-core | Матрица | Если владелец хочет автономный chat-app, потребуется другой источник правил (БД chat-app) |
| A4 | Слова NDA сравнивать без учёта регистра | Паттерн B | Возможны новые находки в существующих файлах (маловероятно: слова нижнего регистра) |
| A5 | Находки ревью Phase 1 не входят в четыре плана без решения владельца; предложен CR-01 | Scope gap | Если владелец ждёт все 20, фаза сильно растёт |
| A6 | Нагрузка `finditer` по всему тексту приемлема | Pitfall 10 | Замедление аудита больших репозиториев; проверяется временем гейта |
| A7 | Критерий «ящик подключён» = результат аккаунта со `status`, не начинающимся с `skipped` | Паттерн D | Возможен показ предупреждения без реального ящика или пропуск; проверяется тестом |

## Open Questions

1. **Включать ли находки ревью Phase 1 в фазу?**
   - Известно: все 20 отложены владельцем в Phase 2; CONTEXT.md молчит; требования их не содержат.
   - Неясно: объём.
   - Рекомендация: опрос владельца до планирования (см. Scope gap), по умолчанию только CR-01 отдельным планом.
2. **Что делать с обёрткой chat-app?**
   - Известно: в её venv нет `yaml`; её хук и пять тестов хука зависят от импорта; сейчас она сканирует слова NDA.
   - Неясно: допустима ли зависимость chat-app от каталога `/opt/assistant-core`.
   - Рекомендация: делегатор с `ASSISTANT_CORE_DIR` (по умолчанию `/opt/assistant-core`), fail-closed; решение подтвердить в задании chat-app.
3. **Строгая или мягкая трактовка `workspaces=None`?**
   - Рекомендация: строгая (`rc=1`), для тестов явный `workspaces=()`.
4. **Нужно ли добавить `assistant-shared` как пространство персоны?**
   - Сейчас он не входит в `workspaces`, всегда «публичный с предупреждением».
   - Рекомендация: нет в этой фазе (данные владельца), записать в бэклог.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python venv assistant-core | все тесты, обёртка | да | 3.12 | — |
| `git` | аудит, тесты во временных репозиториях | да | используется тестами (91 тест shared проходит) | — |
| pytest + pytest-asyncio | тесты | да | работают | — |
| pyyaml в venv assistant-core | загрузка persona.yaml | да | используется loader | — |
| pyyaml в venv chat-app | обёртка chat-app | **нет** | `ModuleNotFoundError` | делегатор через venv assistant-core |
| chat-app pytest (только запуск) | проверка потребителя | да | 117 passed на безопасных файлах | — |
| import-linter | гейт | да (Phase 1) | — | — |
| Сеть/внешние API | не нужны | — | — | — |

**Missing dependencies with no fallback:** нет.
**Missing dependencies with fallback:** `yaml` в venv chat-app (делегатор).

## Validation Architecture

> `workflow.nyquist_validation` включён [VERIFIED: .planning/config.json, `"nyquist_validation": true`].

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8 + pytest-asyncio (`asyncio_mode = auto`) |
| Config file | `/opt/assistant-core/pytest.ini`; для shared — `[tool.pytest.ini_options]` в `/opt/assistant-shared/pyproject.toml` |
| Quick run command | `cd /opt/assistant-core && .venv/bin/pytest <файл> -p no:cacheprovider -v` |
| Shared suite | `cd /opt/assistant-shared && /opt/assistant-core/.venv/bin/pytest tests -p no:cacheprovider -q` (базовая линия: 91 passed) |
| Consumer check (только чтение chat-app) | `cd /opt/chat-app && backend/.venv/bin/pytest backend/tests -p no:cacheprovider -q` |
| Full suite / gate | `cd /opt/assistant-core && python3 scripts/gate.py` (ожидается «ИТОГ: ЗЕЛЁНЫЙ») |

Базовая линия, снятая в этой сессии: assistant-core, девять файлов, затрагиваемых фазой (`test_nda_script_parity`, `test_hitl_safety_guardrails`, `test_secretary_dialog`, `test_fast_intent_router`, `test_bot_hitl_parity`, `test_email_reply_workflow`, `test_synthetic_persona`, `test_hardcode_scanner`, `test_persona_config`): **56 passed**; chat-app, семь файлов с безопасностью: **117 passed**.

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SECF-01 | В `assistant_shared/security` нет «tydex» и литерала аккаунта; значения берутся из данных персоны во время теста, в файле теста литералов нет; `CORPORATE_NDA_KEYWORDS` отсутствует | unit | `.venv/bin/pytest tests/test_nda_script_parity.py -p no:cacheprovider -v` | переписать |
| SECF-01 | CLI определяет NDA по данным: сопоставление по пути, по remote, спор -> строжайший, не найден -> публичный + `⚠️`, `None` -> rc 1, битая персона -> rc 1 | unit (shared) | `cd /opt/assistant-shared && /opt/assistant-core/.venv/bin/pytest tests/test_workspace_matching.py -p no:cacheprovider -v` | Wave 0 |
| SECF-01 | Обёртка assistant-core: временная персона (`PERSONA_CONFIG_PATH`), NDA-репозиторий с запрещённым remote -> rc 1, слова NDA в публичном репозитории -> rc 1, битый файл персоны -> rc 1 | integration (subprocess) | `.venv/bin/pytest tests/test_security_shield_cli.py -p no:cacheprovider -v` | Wave 0 |
| SECF-02 | Паритет `audit_path` и `audit_repository` на фикстурах: чистый, секрет, многострочный PEM, слово NDA, `.env`, пустой | integration (shared) | `cd /opt/assistant-shared && /opt/assistant-core/.venv/bin/pytest tests/test_shield_parity.py -p no:cacheprovider -v` | расширить |
| SECF-02 | `scan_file_content`: построчно, многострочно, дедупликация, короткое замыкание по имени файла, `casefold` слов | unit (shared) | `cd /opt/assistant-shared && /opt/assistant-core/.venv/bin/pytest tests/test_scan_file_content.py -p no:cacheprovider -v` | Wave 0 |
| SECF-02 | Web-эндпоинт chat-app ищет слова NDA в публичном пространстве (ASGI-клиент, синтетическая персона) | integration (chat-app, через /gsd-quick) | `cd /opt/chat-app && backend/.venv/bin/pytest backend/tests/test_nda_equivalence.py backend/tests/test_security_api.py -p no:cacheprovider -q` | в задании chat-app |
| SECF-01/02 | Потребитель остаётся зелёным | regression (read-only) | `cd /opt/chat-app && backend/.venv/bin/pytest backend/tests -p no:cacheprovider -q` | существует |
| SAFE-01 | Текст/голос/движок: история не меняется, предупреждение содержит `/clear`, карточки нет | unit | `.venv/bin/pytest tests/test_clear_dialog_text_guard.py -p no:cacheprovider -v` | Wave 0 |
| SAFE-01 | `/clear` показывает карточку; без подтверждения история на месте; подтверждение, отмена, восстановление | unit | `.venv/bin/pytest tests/test_hitl_safety_guardrails.py tests/test_bot_hitl_parity.py tests/test_secretary_dialog.py -p no:cacheprovider -v` | существует, `test_secretary_dialog_clear_command` переписать |
| SAFE-01 | Единый список триггеров (маршрутизатор и движок используют одну константу) | unit | `.venv/bin/pytest tests/test_fast_intent_router.py -p no:cacheprovider -v` | существует |
| PRIV-01 | `/help` содержит текст из персоны; по умолчанию запасной текст; `handle_cmd_help` не трогает БД | unit | `.venv/bin/pytest tests/test_privacy_notice.py tests/test_deploy_script.py::test_help_handler_does_not_touch_db -p no:cacheprovider -v` | Wave 0 + существует |
| PRIV-01 | Цикл почты: первое успешное подключение -> журнал + одно сообщение + флаг; второй цикл молчит; все ящики `skipped_*` -> без сообщения; временная БД | unit/integration | `.venv/bin/pytest tests/test_privacy_notice.py tests/test_email_reply_workflow.py -p no:cacheprovider -v` | Wave 0 + существует |
| PRIV-01 | `PersonaConfig` принимает `privacy`, отвергает лишние ключи; `auth_google.py` и `.env.example` содержат предупреждение | unit | `.venv/bin/pytest tests/test_persona_config.py tests/test_privacy_notice.py -p no:cacheprovider -v` | существует + Wave 0 |
| все | Архитектура и границы импортов | lint | `python3 scripts/gate.py` (строка lint-imports) | существует |
| все | Гейт ЗЕЛЁНЫЙ, число находок shield не выросло | gate | `python3 scripts/gate.py` | существует |
| достижимость | `/help`, точка почты, текстовое «очисти диалог», `scripts/security_shield.py` | VERIFICATION.md | команды выше плюс `python3 scripts/security_shield.py --all` и `python3 scripts/deploy.py` (read-only смоук) | вручную в VERIFICATION |

### Sampling Rate
- **Per task commit:** `.venv/bin/pytest <изменённые файлы> -p no:cacheprovider -v`
- **Per wave merge:** `cd /opt/assistant-shared && /opt/assistant-core/.venv/bin/pytest tests -p no:cacheprovider -q`, затем консумерный прогон chat-app (read-only), затем `python3 scripts/gate.py`
- **Phase gate:** `python3 scripts/gate.py` = «ИТОГ: ЗЕЛЁНЫЙ» и полный pytest chat-app зелёный до `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `/opt/assistant-shared/tests/test_scan_file_content.py` — SECF-02
- [ ] `/opt/assistant-shared/tests/test_workspace_matching.py` — SECF-01
- [ ] `/opt/assistant-core/tests/test_security_shield_cli.py` — SECF-01 (временная персона; образцы фикстур персоны: `tests/conftest.py::default_persona_config`, `tests/synthetic_persona.py`)
- [ ] `/opt/assistant-core/tests/test_clear_dialog_text_guard.py` — SAFE-01
- [ ] `/opt/assistant-core/tests/test_privacy_notice.py` — PRIV-01
- [ ] Предпроверка задания chat-app: прогон полного pytest chat-app против копии библиотеки через `PYTHONPATH` (способ показан в этом исследовании); новых каркасов тестов не нужно, фреймворк установлен

## Security Domain

> `security_enforcement` включён, `security_asvs_level: 1`, `security_block_on: high` [VERIFIED: .planning/config.json].

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | нет | — (бот уже проверяет `allowed_user_id`) |
| V3 Session Management | нет | — |
| V4 Access Control | да | `_is_authorized` в `handle_cmd_clear_dialog` и в `handle_user_text`; остаётся без изменений |
| V5 Input Validation | да | pydantic `extra=forbid` для персоны и `WorkspaceConfig`; сравнение путей через `resolve()` |
| V7 Error Handling and Logging | да | fail-closed: битая персона, сбой git, пустые правила NDA = нарушение; сообщения об ошибках без значений |
| V8 Data Protection | да | слова NDA и remote не печатаются в гейте, документах и тестах; предупреждение PRIV-01 информирует о внешней обработке |
| V6 Cryptography | нет | — |

### Known Threat Patterns for Python/SQLite/Telegram-бот

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Подмена режима NDA именем каталога или симлинком | Spoofing / Tampering | Сопоставление по `resolve()`-пути и нормализованному remote, спорное = строжайший clearance |
| Ослабление проверки при пропаже данных | Elevation of Privilege | `workspaces=None` и ошибка загрузки персоны = rc 1; пустые правила NDA = нарушение |
| Утечка слов NDA через вывод shield | Information Disclosure | Гейт не печатает слова; предупреждения без значений; слова только из данных |
| Обход проверки слов регистром | Tampering | `casefold` с обеих сторон |
| Необратимая очистка памяти текстовой командой | Tampering / DoS | Предупреждение вместо очистки; единственный путь — `/clear` с карточкой и архивом (`is_archived`), обратимо `restore_dialog_history` |
| Подмена `/clear` пользовательским алиасом | Tampering | Уже закрыто: `protected = {"cancel", "cansel", "reset", "clear", "undo_clear"}` [VERIFIED: bot_handler.py:1367] |
| Запись от root по имени файла из внешнего источника (CR-01, если включат в фазу) | Tampering / Elevation | `Path(remote_name).name` + проверка `resolve()` внутри каталога загрузок |
| Подмена правил через `PERSONA_CONFIG_PATH` | Tampering | Переменная окружения процесса; хук/гейт запускаются под владельцем; в VERIFICATION отметить доверие окружению |

## Project Constraints (from CLAUDE.md)

Из `/opt/assistant-core/CLAUDE.md` и `/opt/assistant-core/.claude/CLAUDE.md` (обязательны, как locked decisions):
- Боевую БД `/opt/assistant-core/data/assistant.db` не открывать и не менять при разработке и тестах.
- `assistant-worker.service` и `chat-app.service` заморожены; рестарт assistant-worker только по явному разрешению владельца через `python3 scripts/deploy.py --restart` и затем смоук-проверка; рестарт chat-app.service — тоже только с разрешения.
- Качество: тесты 100%; пропуски, xfail, deselected делают гейт красным; проверять `python3 scripts/gate.py`, не общий гейт chat-app.
- Безопасность: HITL для необратимых действий; Air-Gap NDA; security-проверки только ужесточаются, fail-closed.
- Стек: Python 3.12, async-first; новые зависимости только с одобрения владельца.
- Всё, что видит пользователь, по-русски; код и коммиты по-английски или по-русски.
- Профильные значения из `config/persona.yaml`, не из кода (`tests/test_hardcode_scanner.py`).
- Правки chat-app только мелкими задачами `/gsd-quick`; `/opt/assistant-shared` — владелец схемы и библиотеки безопасности (assistant-core на стороне владельца).
- Границы импортов (`.importlinter`): `src.brain` не импортирует адаптеры; `bot_handler` и `live_ticker` не импортируют адаптеры напрямую; `src.core` чист.
- Логи: `%s`-форматирование, не f-строки, секреты не логировать; новых `print` в `src/` не добавлять.
- Фаза закрывается только с SUMMARY.md и VERIFICATION.md, проверяющим достижимость из рантайма.
- Делегирование Antigravity-агентам только через `/opt/chat-app/scripts/agy_task.sh`; исследование, архитектура, логика безопасности/NDA/HITL, ревью, проверка — всегда Claude; однотипные правки 4+ файлов и черновики тестов — кандидаты для agy.

## Sources

### Primary (HIGH confidence)
- Код, прочитанный в этой сессии: `/opt/assistant-shared/assistant_shared/security/{auditor,rules,patterns,runner,__init__}.py`, `/opt/assistant-shared/tests/{test_shield_parity,test_security_shared,test_shield_regressions}.py`, `/opt/assistant-shared/scripts/security_shield.py`, `/opt/assistant-core/scripts/{security_shield,gate,auth_google}.py`, `/opt/assistant-core/src/{notifier/bot_handler,brain/secretary_dialog,brain/intent_router,persona/models,persona/loader,main,collector/email_collector,storage/db}.py`, `config/persona.yaml`, `.env.example`, `.importlinter`, тесты assistant-core, перечисленные в тексте.
- Код chat-app (только чтение): `backend/app/api/v1/security.py`, `backend/app/db.py`, `backend/tests/{test_nda_equivalence,test_security_shared,test_shield_regressions,test_persona_api,test_synthetic_persona,conftest}.py`, `scripts/security_shield.py`.
- Запуски в этой сессии: pytest assistant-shared (91 passed), набор assistant-core (56 passed), набор chat-app (117 passed), прогон chat-app против копии библиотеки в scratchpad (13 failed, 232 passed + ошибка сбора), `aiogram.__version__`, проверка `import yaml` в venv chat-app.
- `.planning/{REQUIREMENTS,STATE,config.json}`, `phases/02-…/02-CONTEXT.md`, `phases/01-…/{01-REVIEW,01-REVIEW-DISPOSITION,01-CHATAPP-QUICK-BRIEF}.md`.

### Secondary (MEDIUM confidence)
- Нет (внешние источники не использовались: фаза внутренняя).

### Tertiary (LOW confidence)
- Оценка производительности `finditer` (A6), критерий «ящик подключён» (A7).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — новых зависимостей нет, всё установлено и проверено запуском.
- Architecture: HIGH для SECF/SAFE (код прочитан, влияние на chat-app измерено), MEDIUM для PRIV-01 (выбор хранилища флага — рекомендация, ждёт подтверждения).
- Pitfalls: HIGH — большинство подтверждены чтением кода или прогоном.

**Research date:** 2026-10-10
**Valid until:** 2026-11-10 (стабильный внутренний код; пересмотреть, если до планирования меняются `/opt/assistant-shared` или `bot_handler.py`)
