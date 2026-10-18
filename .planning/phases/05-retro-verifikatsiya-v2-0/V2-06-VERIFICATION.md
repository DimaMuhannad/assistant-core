---
phase: 05-retro-verifikatsiya-v2-0
v2_phase: "06"
v2_source: /opt/chat-app/.planning/milestones/v2.0-phases/06-gotovnost-k-multitenantnosti
verified: 2026-10-18T21:46:41Z
status: in_progress
score: "0 из 5 требований вынесены"
requirements: [ISO-01, ISO-02, ISO-03, ISO-04, FIN-01]
gaps: []
---

# V2-06: Готовность к мультитенантности (ретро-верификация фазы 06 v2.0)

## Источник (только чтение)

- Исходный каталог фазы v2.0: `/opt/chat-app/.planning/milestones/v2.0-phases/06-gotovnost-k-multitenantnosti`.
- Состав каталога (16 файлов, проверено `ls`): `06-01-PLAN.md`, `06-01-SUMMARY.md`, `06-02-PLAN.md`, `06-02-SUMMARY.md`, `06-03-PLAN.md`, `06-03-SUMMARY.md`, `06-04-PLAN.md`, `06-04-SUMMARY.md`, `06-05-PLAN.md`, `06-05-SUMMARY.md`, `06-06-PLAN.md`, `06-06-SUMMARY.md`, `06-CONTEXT.md`, `06-DISCUSSION-LOG.md`, `06-RESEARCH.md`, `06-VALIDATION.md`. Файла `VERIFICATION.md` в исходной папке нет, поэтому ретро-верификация проведена по живому коду и тестам.
- Тексты требований v2.0 (только чтение): `/opt/chat-app/.planning/milestones/v2.0-REQUIREMENTS.md:83-87` (ISO-01, ISO-02, ISO-03, ISO-04, FIN-01).

## Вердикты

| Требование | Статус | Точка входа в рантайме (file:line) | Тест или команда проверки | Метка |
|---|---|---|---|---|
| ISO-01 | passed | `src/main.py:687-699` (`EmailBotHandler`, `dp.include_router`) → `src/notifier/bot_handler.py:432, 1311, 1416` → `src/brain/intent_router.py:381` и `src/brain/secretary_dialog.py:753, 813` → `src/brain/key_rotator.py:227, 219-220, 194-213` (прокси и `get_key_rotator`, пул по `persona_id`); `src/main.py:675` → `src/composition.py:161-167` → `src/main.py:904-913` → `src/brain/git_evaluator.py:305-311`; глобальных присваиваний `config.GEMINI_API_KEY` нет | `tests/test_key_rotator.py:111-125` (`test_key_rotator_no_global_config_mutation`), `:128-135`, `:138-170` (`test_key_rotator_persona_isolation`); `pytest tests/test_key_rotator.py -q` → код 0, `9 passed` | трасса |
| ISO-03 | passed | `src/composition.py:37, 57, 78, 111, 144` (`MissingScopeError` в пяти фабриках) ← `src/core/ports/connectors.py:34, 78, 146, 194` (`required_scopes`); `src/main.py:673` (`default_lms_client()` вне `try`) и `src/main.py:965` (`asyncio.run(main())` без перехвата): нехватка scope у `lms` останавливает старт (fail-closed); `/opt/chat-app/backend/app/core/config.py:6-33` (в `Settings` нет полей LMS) | `tests/test_phase4_reachability.py:91-120`, `tests/test_ports_conformance.py:284-295, 297-310`, `tests/test_concurrency_isolation.py:71`; `pytest tests/test_phase4_reachability.py tests/test_ports_conformance.py -q` → код 0, `41 passed`; `grep -rniE 'lms\|guap' /opt/chat-app/backend/app --include=*.py` → 0 совпадений | трасса |
| ISO-04 | gap | `src/main.py:651-652` (персона процесса) → `src/persona/current.py:17-40` (`_override`, `current_persona`, `use_persona`) → `src/brain/key_rotator.py:190-213` (пул ключей по `persona_id`) → `src/composition.py:21-146` (фабрики по персоне) → `/opt/assistant-shared/assistant_shared/hitl/store.py:24-75, 100-108` (подтверждения с `persona_id`); сбой записи подтверждения `database is locked` в `store.py:52` | `tests/test_concurrency_isolation.py:97-163` (`test_concurrent_confirmations_isolation`: 2 сбоя из 9 прогонов в связке с другими файлами, 0 из 20 при изолированном прогоне файла); `tests/test_concurrency_isolation.py:44-94`, `:166-190` и `tests/test_synthetic_persona.py` проходят | трасса+e2e |
| FIN-01 | passed | `tests/hardcode_baseline.py:14` (`HARDCODE_BASELINE = {}`), `tests/test_hardcode_scanner.py:149-158` (нет новых хардкодов вне baseline, нет устаревших записей); `/opt/chat-app/backend/tests/hardcode_baseline.py:14`, `/opt/chat-app/backend/tests/test_hardcode_scanner.py:149-158` | `tests/test_hardcode_scanner.py` (3 passed, код 0); `backend/tests/test_hardcode_scanner.py` (3 passed, код 0, git status chat-app не изменён) | трасса |

## Доказательства

### ISO-01: `key_rotator.py` не мутирует глобальный `config.GEMINI_API_KEY`; ключи принадлежат контексту персоны

**Формулировка требования (`/opt/chat-app/.planning/milestones/v2.0-REQUIREMENTS.md:83`):** «`key_rotator.py` не мутирует глобальный `config.GEMINI_API_KEY`; ключи принадлежат контексту персоны (явная передача или `contextvars`); `test_key_rotator.py` проходит.»

**Вердикт:** `passed` (метка `трасса`: доказано трассой, без e2e-теста, D-04). Присваиваний `config.GEMINI_API_KEY` или `GEMINI_API_KEYS` в `src/` и `scripts/` нет (поиск по `config\.GEMINI_API_KEYS?\s*=`, 0 совпадений). Ротатор кэшируется по `persona_id`.

**Трасса (`файл:строка`):**
1. Вход: `src/main.py:687-698` создаёт `EmailBotHandler`, `src/main.py:699` подключает его роутер; `src/notifier/bot_handler.py:432` регистрирует `handle_user_text` (`:1311`).
2. Вызовы из рантайма: `bot_handler.py:1416` → `src/brain/intent_router.py:381` (`key_rotator.execute_with_failover`); `bot_handler.py:1472` → `_handle_secretary_dialog` (`:2569`) → `:2576` → `src/brain/secretary_dialog.py:753, 813`; клиент берётся через `key_rotator.get_client()` (`intent_router.py:119`, `secretary_dialog.py:70`).
3. Планировщик: `src/main.py:675` → `src/composition.py:161-167` (`use_key_rotator=True`) → cron-задача `git_progress_job` (`src/main.py:904-913`) → `run_git_progress_cycle` (`:604-611`) → `src/brain/git_evaluator.py:305-311`.
4. Прокси и фабрика: `src/brain/key_rotator.py:227` (`key_rotator = _KeyRotatorProxy()`), `:219-220` (`__getattr__` → `get_key_rotator()`), `:194-213` (ключ кэша `p_id` из `current_persona()`, ключи `persona.gemini_keys` (`src/persona/models.py:310`), кэш `_rotator_cache` (`:191`, `:210-211`), `env_path=None` (`:211`)).
5. Персона: `src/persona/current.py:17` (`_override`), `:21-30` (`current_persona`), `:34-40` (`use_persona`).
6. Мутация состояния: `mark_exhausted` (`key_rotator.py:87-118`) меняет `self.cooldowns[key]` (`:90`) и `self.active_index` (`:103`, `:114`) только у своего экземпляра.

**Тесты и прогон:**
- `tests/test_key_rotator.py`: 9 тестов (определения на строках `:27, 33, 52, 69, 80, 100, 111, 128, 138`). `test_key_rotator_no_global_config_mutation` (`:111-125`) сверяет `config.GEMINI_API_KEY` до и после `mark_exhausted`, и проверяет, что временный `.env` переписан (там `env_path` задан явно, `:124-125`). `test_key_rotator_default_env_path_is_none` (`:128-135`): при `env_path=None` `sync_active_key_to_env` возвращает `False`. `test_key_rotator_persona_isolation` (`:138-170`): подмена `_current_rotator` (тестовый путь) и переключение `use_persona` между двумя персонами с независимыми пулами и cooldown.
- Команда: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider tests/test_key_rotator.py -q` → код 0, `9 passed in 3.00s`.

### ISO-03: Zero-Trust scopes; ядро не поднимает коннектор без scope; chat-app не держит учётные данные LMS

**Формулировка требования (`/opt/chat-app/.planning/milestones/v2.0-REQUIREMENTS.md:85`):** «Zero-Trust scopes: коннектор объявляет `required_scopes`, персона выдаёт `scopes`; ядро отказывается поднимать коннектор без выданного scope; процесс chat-app не держит учётные данные LMS (проверяемый тест).»

**Вердикт:** `passed` (метка `трасса`, без e2e-теста, D-04). Часть assistant-core доказана трассой по всем пяти фабрикам и пробой. Часть про chat-app: в формулировке указан «проверяемый тест», а отдельного теста в chat-app нет. Подтверждение только статическим поиском по коду и полям настроек. Это записано как предел вывода (A6) и вынесено владельцу на решение.

**Трасса assistant-core (`файл:строка`):**
- Декларации `required_scopes`: `src/core/ports/connectors.py:34` (timesheet), `:78` (schedule), `:146` (lms), `:194` (git); `src/connectors/aadhk/provider.py:17`, `src/connectors/guap_lms/client.py:20`, `src/connectors/git/provider.py:43`, `src/connectors/notion/client.py:23`.
- Проверки в фабриках `src/composition.py`: `schedule_site_url` (`:34-37`, raise на `:37`), `default_timesheet_service` (`:54-57`, `:57`), `default_lms_client` (`:75-78`, `:78`), `default_git_source_provider` (`:108-111`, `:111`), `default_notion_client` (`:141-144`, `:144`). Каждая сравнивает `required_scopes` с `binding(role).scopes` (`src/persona/bindings.py:67-79`, читает `current_persona()`).
- Вызовы при старте: `src/main.py:673` — `default_lms_client()` вне `try`; исключение не перехватывается и доходит до `src/main.py:965` (`asyncio.run(main())`), процесс завершается (fail-closed). `src/main.py:674-678` — `default_git_evaluator` в `try/except`, цепочка git отключается с записью в лог. `src/main.py:703` — `schedule_site_url()` вне `try`.
- Прочие вызовы: `src/notifier/bot_handler.py:152` (lms), `:305` (timesheet), `src/brain/secretary_dialog.py:138`, `src/notifier/live_ticker.py:146`.
- Проба в памяти (без записи в файлы, `python -c` с `use_persona`): привязка `lms` со `scopes=["lms.read"]` → `default_lms_client()` поднимает `MissingScopeError` (сообщение содержит «lms»); исходная персона не изменена (`lms.read`, `lms.write`).

**Тесты assistant-core:**
- `tests/test_phase4_reachability.py:91-120` — `test_composition_default_git_evaluator_missing_scope_raises`: notion (`:107`) и git_source (`:120`) без нужных scope.
- `tests/test_ports_conformance.py:284-295` — `test_connectors_declare_required_scopes`; `:297-310` — `test_composition_missing_scope_error`: timesheet без `timesheet.write`.
- `tests/test_concurrency_isolation.py:71` — синтетическая персона: `MissingScopeError` при `default_timesheet_service`.
- Прямого теста на нехватку scope для `default_lms_client` и `schedule_site_url` нет. Их покрытие: трасса и проба. (Черновик Argon ссылался на несуществующий тест `test_scope_enforcement_lms_missing_write`; исправлено.)
- Команды: `pytest tests/test_phase4_reachability.py tests/test_ports_conformance.py -q` → код 0, `41 passed in 18.47s`; `-k "scope or required_scopes"` → код 0, `3 passed, 38 deselected` (в черновике ожидалось 11).

**Часть chat-app (`/opt/chat-app/backend`, только чтение):**
- `grep -rniE 'lms|guap' /opt/chat-app/backend/app --include=*.py` → 0 совпадений.
- `app/core/config.py:6-33`: класс `Settings` объявляет 10 полей: `PROJECT_NAME` (`:7`), `VERSION` (`:8`), `API_V1_STR` (`:9`), `HOST` (`:12`), `PORT` (`:13`), `DEBUG` (`:14`), `CORS_ORIGINS` (`:17`), `SQLITE_DB_PATH` (`:20`), `WORKSPACE_ROOT` (`:24`), `PERSONA_ID` (`:27`). Полей учётных данных LMS нет. Параметры `env_file=".env"` (`:30`) и `extra="ignore"` (`:32`).
- Предел вывода (A6): это доказывает отсутствие LMS-кода и полей в chat-app, но не доказывает отсутствие переменных `GUAP_*` или `LMS_*` в файле `.env` или в окружении процесса. Файл `.env` не читался. `chat-app.service` неактивен (`systemctl is-active` → `inactive`, только чтение статуса).

### ISO-04: Параллельный запуск персоны по умолчанию и синтетической персоны без cross-talk (ключи, кэши, рабочие пространства, привязки коннекторов, подтверждения)

**Формулировка требования (`/opt/chat-app/.planning/milestones/v2.0-REQUIREMENTS.md:86`):** «Интеграционный тест одновременно инстанцирует персону по умолчанию и вторую синтетическую персону и подтверждает отсутствие cross-talk (ключи, кэши, рабочие пространства, привязки коннекторов, подтверждения).»

**Вердикт:** `gap` (метка `трасса+e2e`). Изоляция состояния (cross-talk) в прогонах, где тест завершился, подтверждена. Gap относится к надёжности параллельной записи подтверждений: в связке с другими тестами тест `test_concurrent_confirmations_isolation` дважды завершился ошибкой `sqlite3.OperationalError: database is locked`, то есть параллельный запуск двух персон не проходит стабильно. Требование «подтверждает отсутствие cross-talk» по букве одним прогоном не закрывается, поэтому статус не `passed`.

**Трасса (`файл:строка` на каждом звене):**
1. Старт процесса: `src/main.py:651-652` — `persona = current_persona()` и `seed_persona(db, persona)`.
2. Текущая персона процесса: `src/persona/current.py:17` — `_override: ContextVar[PersonaConfig | None]`; `:21-30` — `current_persona()` (сначала `_override`, затем загрузка из `config/persona.yaml` с кэшем по пути); `:34-40` — `use_persona()` с `ContextVar.set/reset`.
3. Пул ключей Gemini: `src/brain/key_rotator.py:191` (`_rotator_cache: dict[str, GeminiKeyRotator]`), `:194-213` (`get_key_rotator()` берёт `persona.id` и `persona.gemini_keys`, строит ротатор по ключу `p_id`), `:211` (`env_path=None`). Отдельного ContextVar для ключей в рантайме нет: `_current_rotator` (`:190`) нигде в `src/` не выставляется, его использует только тест `tests/test_key_rotator.py:141`. Изоляция ключей идёт через персону из `current_persona()`.
4. Фабрики композиции: `src/composition.py:21-146` вызывают `binding()` и `has_binding()` (`src/persona/bindings.py:67-79`), которые читают `current_persona()`, поэтому привязки и `scopes` разрешаются для персоны текущей корутины.
5. Подтверждения: `/opt/assistant-shared/assistant_shared/hitl/store.py:24-75` — `create_confirmation` пишет `persona_id` (INSERT в `store.py:52-66`); `:100-108` — `list_pending(persona_id)` фильтрует `WHERE status = 'pending' AND persona_id = ?`.
6. Число персон в рантайме: одна. `use_persona(` вызывается в `src/` только в определении (`src/persona/current.py:34`); демон работает с персоной `popov-da-default` из `config/persona.yaml`. Синтетическая персона `synthetic-test-persona` (`tests/synthetic_persona.py:39-40`, `SYNTHETIC_PERSONA`, `"id"`) существует только в тестах. Метка: пометка «в рантайме одна персона» действует.

**Что именно проверяют тесты (`tests/test_concurrency_isolation.py`, 3 теста):**
- `test_multi_persona_concurrency_isolation` (`:44-94`): два воркера через `use_persona(...)` параллельно по 25 итераций. Проверяются: `persona_id` (`popov-da-default` и `synthetic-test-persona`), число рабочих пространств (4 и 3), активный ключ из своего пула (`MOCK_DEFAULT_KEYS` и `MOCK_SYNTH_KEYS`, `:29-30`), и для синтетической персоны `MissingScopeError` при `default_timesheet_service(None)` (`:71-72`). Ротация ключей в тесте не выполняется.
- `test_concurrent_confirmations_isolation` (`:97-163`): по 10 подтверждений на каждую персону через `asyncio.gather` в одной SQLite-базе из `tmp_path`. Это место сбоя (см. ниже).
- `test_high_concurrency_persona_switching` (`:166-190`): 20 корутин (по 10 на персону) со случайными задержками, проверка `current_persona().id`, `display_name` и активного ключа.
- `tests/test_synthetic_persona.py`: 7 тестов (`:58, 69, 81, 123, 156, 162, 176`) — независимость и отсутствие пересечения с персоной по умолчанию.

**Выполненные команды (`PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider ... -q`, каждая под `timeout 300`):**

| № | Команда | Код возврата | Итог pytest |
|---|---|---|---|
| 1 | `tests/test_concurrency_isolation.py tests/test_synthetic_persona.py` (команда Task 1) | 0 | `10 passed in 4.26s` |
| 2 | то же, 6 повторов подряд | 0, 0, **1**, 0, 0, 0 | 5 раз `10 passed`; 1 раз `1 failed, 9 passed` |
| 3 | `tests/test_phase4_reachability.py tests/test_ports_conformance.py tests/test_concurrency_isolation.py` (ISO-03, общий прогон) | **1** | `1 failed, 43 passed in 39.66s` |
| 4 | `tests/test_concurrency_isolation.py`, 20 повторов подряд | 0 во всех 20 | `3 passed` в каждом; один прогон занял 47.5 с (вероятное ожидание блокировки) |
| 5 | `tests/test_key_rotator.py` (ISO-01, для справки) | 0 | `9 passed` |
| 6 | `tests/test_key_rotator.py tests/test_phase4_reachability.py tests/test_ports_conformance.py tests/test_concurrency_isolation.py tests/test_hardcode_scanner.py` (общий прогон Task 2) | 0 | `56 passed in 15.85s` (тот же тест прошёл) |

Итого: 2 сбоя из 9 прогонов в связке с другими файлами (прогоны 1–3 и 6 таблицы), 0 сбоев из 20 при изолированном прогоне файла. Сбой одинаковый в обоих случаях.

**Текст сбоя (без данных):** `sqlite3.OperationalError: database is locked`, стек: `tests/test_concurrency_isolation.py:128` (`asyncio.gather`) → `:118` (`create_synth_confirmations`) → `assistant_shared/hitl/store.py:52` (INSERT в `create_confirmation`). Подключения создаются на каждый вызов через `assistant_shared/db/connection.py:32-46` с `timeout=30.0` (`:39`) и `PRAGMA busy_timeout = 30000` (`:42`), поэтому блокировка возникла при уже заданном таймауте. Причина не установлена: в рамках фазы код не меняется (D-10). Гипотеза для планирования исправления, не проверена: `PRAGMA journal_mode = WAL` выполняется при каждом открытии подключения (`connection.py:45`), и конкурентное переключение режима может давать немедленный SQLITE_BUSY.

**Критерий стабильности:** по D-08 (аналогично DAT-03) любой сбой теста — это gap с частотой и текстом ошибки. Здесь: 2 из 9 прогонов в связке, текст выше. Тест не помечен skip/xfail/deselected, гейт при этом может быть красным на отдельных прогонах.

### FIN-01: Сканер хардкода работает с пустым `HARDCODE_BASELINE` в обоих репозиториях

**Формулировка требования (`/opt/chat-app/.planning/milestones/v2.0-REQUIREMENTS.md:87`):** «Метрика завершения подтверждена: сканер хардкода (PER-08) работает с пустым allowlist — в коде обоих репозиториев нет ГУАП, Тидекс, ФИО, персональных путей и аккаунтов вне данных персоны; персона по умолчанию ведёт себя как раньше; 100% pytest.»

**Вердикт:** `passed` формально (метка `трасса`), по решению владельца от 2026-10-18 №1: `HARDCODE_BASELINE` пуст в обоих репозиториях, тесты сканера зелёные. Буква текста v2.0 требует пустой allowlist; он не пуст (см. «Наблюдения»). По решению владельца это записано как наблюдение, не как gap. Новое требование FIN-02 не создаётся.

**Трасса (`файл:строка`):**
- `tests/hardcode_baseline.py:14` — `HARDCODE_BASELINE: dict[str, dict[str, int]] = {}`.
- `/opt/chat-app/backend/tests/hardcode_baseline.py:14` — то же.
- `tests/test_hardcode_scanner.py:149-153` — `test_no_new_hardcode_outside_baseline`: разница «найдено минус baseline» обязана быть пустой; `:155-158` — `test_baseline_has_no_stale_entries`. В chat-app те же тесты на строках `backend/tests/test_hardcode_scanner.py:149-158`.
- Итог: при пустом baseline тест требует нулевого числа совпадений вне allowlist. Отдельного теста «baseline пуст» нет: пустота проверяется косвенно (см. «Наблюдения»).

**Прогоны:**
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider tests/test_hardcode_scanner.py -q` (assistant-core) → код 0, `3 passed in 1.56s`.
- `PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/pytest -p no:cacheprovider backend/tests/test_hardcode_scanner.py -q` (из `/opt/chat-app`) → код 0, `3 passed in 18.14s`. Вывод `git -C /opt/chat-app status --porcelain --ignored | sort` до и после прогона совпал (изменений нет).

## Наблюдения (не gaps)

1. **ISO-01, `sync_active_key_to_env` (`src/brain/key_rotator.py:120-142`).** Функция переписывает строку `GEMINI_API_KEY=` в файле `env_path` через временный файл и `os.replace` (`:134-136`). Её вызывает `mark_exhausted` (`:107`, `:115`). В рантайме `env_path` всегда `None`: единственный конструктор в рантайме — `get_key_rotator` с `env_path=None` (`:211`); при `None` функция возвращает `False` (`:122-123`). Ненулевой `env_path` задаётся только тестами на временных файлах. В этой фазе функция не запускалась, `.env` не открывался. Если появится конструктор с `env_path`, ротация начнёт переписывать `.env`; это наблюдение для будущих фаз.
2. **ISO-01, `_current_rotator` (`key_rotator.py:190`).** ContextVar ключей в `src/` не выставляется, его использует только `tests/test_key_rotator.py:141`. Рантайм-изоляция держится на ContextVar персоны (`src/persona/current.py:17`) и кэше `_rotator_cache` по `persona_id`.
3. **FIN-01, непустой allowlist сканера (наблюдение по решению владельца №1, не gap, FIN-02 не создан).** В обоих сканерах: `ALLOWLIST_PREFIXES = ("config/", "tests/", "backend/tests/", "docs/", ".planning/")` и `ALLOWLIST_SUFFIXES = (".md",)` (`tests/test_hardcode_scanner.py:47-48`, `/opt/chat-app/backend/tests/test_hardcode_scanner.py:47-48`). Функция `is_scanned` (`:51-55`) пропускает эти пути. Буква v2.0 («работает с пустым allowlist») по этому пункту не выполнена; формальный критерий решения №1 выполнен.
4. **FIN-01, отсутствие теста на пустоту baseline.** Пустота `HARDCODE_BASELINE` не проверяется отдельным тестом. Вместо этого `test_no_new_hardcode_outside_baseline` (`:149-153`) при пустом baseline требует нулевого числа совпадений вне allowlist. Это сильнее проверки пустоты, но если однажды в baseline появятся записи, покрытие станет неявным.
5. **ISO-03, момент проверки.** `required_scopes` проверяется при сборке фабрики (`src/composition.py`), а не при каждом вызове коннектора. Текущая персона (`config/persona.yaml`, привязка `lms` со `scopes: lms.read, lms.write`) проходит проверку.
6. **ISO-04, персоны в рантайме.** В процессе работает одна персона; параллельный запуск двух персон проверяется только тестами (см. Gap ISO-04).

## Gaps

| Требование | Класс по D-09 | Предложение оформления | Привязка |
|---|---|---|---|
| ISO-04 | Целостность данных (подтверждения HITL): параллельная запись двух персон не проходит стабильно, `database is locked` в 2 из 9 прогонов в связке | Класс D-09 «целостность данных» → новое требование с ID в REQUIREMENTS.md через план 05-08 после решения владельца, либо запись бэклога 999.x; исправление вне фазы (D-10). Серьёзность: средняя (cross-talk не наблюдался, сбой — отказ записи) | `tests/test_concurrency_isolation.py:97-163`, `/opt/assistant-shared/assistant_shared/hitl/store.py:52` |

