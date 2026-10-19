# Phase 5: Ретро-верификация v2.0 - Context

**Gathered:** 2026-10-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Фаза только проверяет, код не правит. Для 20 требований, перенесённых из v2.0 без проверки (DAT-02..04, SEC-01..03, HIT-01, ISO-01..04, FIN-01, ACT-01..04, UXQ-01, UXQ-02, UXQ-04), выдаётся честный вердикт `passed` или `gap` с доказательством достижимости из рантайма (`src/main.py` или команда бота), а не только зелёным юнит-тестом. Результат: 6 файлов VERIFICATION.md (по фазам 4–9 v2.0), сводка по 20 требованиям, повторный прогон нестабильного теста DAT-03, каждый gap оформлен. Исправление gaps в фазу не входит. Рантайм не меняется, рестарт не нужен.

</domain>

<decisions>
## Implementation Decisions

### Доказательство достижимости
- **D-01:** Метод: статическая трасса вызовов от `src/main.py` или хэндлера бота до функции плюс тест, который входит через реальный вход (хэндлер бота) на временной БД с заглушками внешних API. Одного юнит-теста недостаточно.
- **D-02:** Внешние сервисы: разрешены живые вызовы только для чтения (например `getMe`, чтение календаря). Запрет остаётся жёстким: содержимое NDA-пространств не уходит ни в какую внешнюю LLM, записи во внешние системы запрещены.
- **D-03:** Read-only смоук `python3 scripts/deploy.py` на работающем `assistant-worker` включается как доказательство (меню команд UXQ-01, задачи планировщика). Без `--restart` и `--backup`, без записи в боевую БД.
- **D-04:** Порог passed: если требование достижимо, но покрыто только трассой без теста с реальным входом, ставится `passed` с пометкой «доказано трассой, без e2e-теста». Слабое покрытие уходит в бэклог как улучшение, а не как gap.

### Раскладка и формат VERIFICATION.md
- **D-05:** 6 файлов лежат в папке фазы 5: `V2-04-VERIFICATION.md` … `V2-09-VERIFICATION.md`, плюс итоговая сводная таблица 20 требований. Каждый файл ссылается на исходную фазу chat-app (`/opt/chat-app/.planning/milestones/v2.0-phases/0N-*`, только чтение).
- **D-06:** Запись требования — таблица: требование → статус → точка входа в рантайме (file:line) → тест или команда проверки → пометка «трасса/e2e».

### Нестабильный тест DAT-03
- **D-07:** `test_concurrent_write_two_processes` прогоняется 30 раз подряд в двух режимах: на свободной системе и под нагрузкой (вместе с полным pytest). Учитывать VPS 2 ГБ RAM.
- **D-08:** Критерий: 0 сбоев из 30 = stable. Любой сбой = gap с частотой и текстом ошибки. skip/xfail запрещены гейтом, тест не скрывать.

### Оформление gaps
- **D-09:** Gap по серьёзности: безопасность, HITL, NDA, целостность данных → новое требование с ID в REQUIREMENTS.md, привязка к будущей фазе. Улучшения и косметика → запись бэклога 999.x.
- **D-10:** Если gap касается безопасности (HITL, Air-Gap), в этой фазе он только записывается, без остановки и без внеочередного исправления. Владелец увидит его в итоговой сводке.

### Исполнитель
- **D-11:** agy (flash, только через `/opt/chat-app/scripts/agy_task.sh run --repo /opt/assistant-core --mode read`) собирает инвентаризацию точек входа по требованиям. Claude выносит вердикты, прогоняет тесты (в jail нет `.venv`, БД, git), пишет VERIFICATION.md и запускает гейт.

### Claude's Discretion
- Разбиение на планы и волны, порядок проверки фаз v2.0, формат сводной таблицы.
- FIN-01 подтверждается формально: `HARDCODE_BASELINE` пуст в обоих репозиториях.
- UXQ-02 проверяется на хранении, перенесённом в `0003` (Phase 3).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Проект и требования
- `.planning/ROADMAP.md` §Phase 5 — цель, критерии успеха, заметки планирования
- `.planning/REQUIREMENTS.md` — тексты VER-01 и 20 проверяемых требований
- `.planning/PROJECT.md` — ограничения (боевая БД, сервисы заморожены, Air-Gap)
- `CLAUDE.md` и `.claude/CLAUDE.md` — гейт, маршрутизация agy, HITL, Air-Gap

### История v2.0 (chat-app, только чтение)
- `/opt/chat-app/.planning/milestones/v2.0-MILESTONE-AUDIT.md` — аудит: «сиротские» цепочки
- `/opt/chat-app/.planning/milestones/v2.0-REQUIREMENTS.md`, `v2.0-ROADMAP.md`
- `/opt/chat-app/.planning/milestones/v2.0-phases/04-…` … `09-…` — исходные фазы 4–9

### Процедуры
- `docs/OPS_DEPLOY.md` и `scripts/deploy.py` — read-only смоук
- `scripts/gate.py` — гейт качества
- `.planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-CONTEXT.md` — образец VERIFICATION с проверкой достижимости

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/deploy.py` (read-only смоук): готовая проверка задач планировщика, `getMe`, меню команд
- `scripts/gate.py`: итог ЗЕЛЁНЫЙ/КРАСНЫЙ, хеш боевой БД до/после
- Тесты `tests/test_ports_conformance.py`, `tests/test_hitl_safety_guardrails.py`, `tests/test_airgap_trap.py`, `tests/test_hardcode_scanner.py` — база для доказательств

### Established Patterns
- Адаптеры подключаются через `src/composition.py`; хэндлеры бота и `brain` не импортируют адаптеры напрямую
- Задачи планировщика регистрируются в `src/main.py`

### Integration Points
- `src/main.py` (APScheduler), `src/notifier/bot_handler.py` (команды), `src/brain/intent_router.py` и `secretary_dialog.py` (ACT-01..04)

</code_context>

<specifics>
## Specific Ideas

Пример доказательства для ACT-01: цепочка сообщение в Telegram → `intent_router` → `SecretaryDialogEngine` → бэкенд календаря. Обрыв на любом звене = gap.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. Исправление найденных gaps планируется отдельно.

</deferred>

---

*Phase: 5-Ретро-верификация v2.0*
*Context gathered: 2026-10-18*
