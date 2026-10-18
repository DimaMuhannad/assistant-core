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
| ISO-04 | gap | `src/main.py:651-652` (персона процесса) → `src/persona/current.py:17-40` (`_override`, `current_persona`, `use_persona`) → `src/brain/key_rotator.py:190-213` (пул ключей по `persona_id`) → `src/composition.py:21-146` (фабрики по персоне) → `/opt/assistant-shared/assistant_shared/hitl/store.py:24-75, 100-108` (подтверждения с `persona_id`); сбой записи подтверждения `database is locked` в `store.py:52` | `tests/test_concurrency_isolation.py:97-163` (`test_concurrent_confirmations_isolation`: 2 сбоя из 8 прогонов в связке с другими файлами, 0 из 20 при изолированном прогоне файла); `tests/test_concurrency_isolation.py:44-94`, `:166-190` и `tests/test_synthetic_persona.py` проходят | трасса+e2e |

## Доказательства

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

Итого: 2 сбоя из 8 прогонов в связке с другими файлами (прогоны 1–3 таблицы), 0 сбоев из 20 при изолированном прогоне файла. Сбой одинаковый в обоих случаях.

**Текст сбоя (без данных):** `sqlite3.OperationalError: database is locked`, стек: `tests/test_concurrency_isolation.py:128` (`asyncio.gather`) → `:118` (`create_synth_confirmations`) → `assistant_shared/hitl/store.py:52` (INSERT в `create_confirmation`). Подключения создаются на каждый вызов через `assistant_shared/db/connection.py:32-46` с `timeout=30.0` (`:39`) и `PRAGMA busy_timeout = 30000` (`:42`), поэтому блокировка возникла при уже заданном таймауте. Причина не установлена: в рамках фазы код не меняется (D-10). Гипотеза для планирования исправления, не проверена: `PRAGMA journal_mode = WAL` выполняется при каждом открытии подключения (`connection.py:45`), и конкурентное переключение режима может давать немедленный SQLITE_BUSY.

**Критерий стабильности:** по D-08 (аналогично DAT-03) любой сбой теста — это gap с частотой и текстом ошибки. Здесь: 2 из 8 прогонов в связке, текст выше. Тест не помечен skip/xfail/deselected, гейт при этом может быть красным на отдельных прогонах.

