# Phase 5 Plan 03: V2-05 (HIT-01) и V2-07 верификация Summary

**HIT-01 passed (трасса+e2e) по решению владельца №3; обход очистки диалога записан как gap HIT-05 (кандидат, бэклог 999.3); V2-07 создан со ссылкой на покрытие v3 (GIT-01..04, NTN-01..02), 246 reachability-тестов зелёные.**

---
phase: 05-retro-verifikatsiya-v2-0
plan: 03
subsystem: verification
tags: [retro-verification, v2.0, hitl, confirmation-store, resume-action, bypass, reachability]

requires:
  - phase: 03-vladenie-shemoy-bd
    provides: миграция 0002 pending_confirmations в assistant-shared (проверена на таблицу, колонки, индексы)
  - phase: 04-tsepochka-git-otsenka-hitl-notion
    provides: 04-VERIFICATION.md с покрытием GIT-01..04, NTN-01..02 (источник для V2-07)
provides:
  - V2-05-VERIFICATION.md с вердиктом HIT-01 (passed, трасса+e2e) и gap HIT-05 (обход в cb_dlg_confirm_clear)
  - V2-07-VERIFICATION.md (нет требований фазы 5, перекрёстная ссылка на покрытие v3)
affects: [05-08]

key-files:
  created:
    - .planning/phases/05-retro-verifikatsiya-v2-0/V2-05-VERIFICATION.md
    - .planning/phases/05-retro-verifikatsiya-v2-0/V2-07-VERIFICATION.md
    - .planning/phases/05-retro-verifikatsiya-v2-0/05-03-SUMMARY.md

key-decisions:
  - "HIT-01 passed (трасса+e2e): примитив ConfirmationStore + resume_action + миграция 0002 засчитан по решению владельца №3 (как указано в 05-03-PLAN.md); отсутствие декоратора @requires_confirmation записано как наблюдение, не gap"
  - "HIT-05 gap (кандидат, класс HITL, серьёзность high): cb_dlg_confirm_clear создаёт и подтверждает запись постфактум (bot_handler.py:1940-1948), при сбое хранилища очищает всё равно (:1949-1950, fail-open), очистку вызывает напрямую (:1952) без resume_action; записан только, не исправлен (D-10); привязка бэклог 999.3 через план 05-08"
  - "V2-07 без gap: у фазы 07 v2.0 нет требований фазы 5 (решение владельца №7); покрытие взято из 04-VERIFICATION.md дословно, GIT-01 остаётся PARTIAL (override)"
  - "Расхождение в 04-VERIFICATION.md: frontmatter status passed, тело human_needed; перенесено как наблюдение, статус v3 не переоценён"

patterns-established:
  - "Черновик внешнего агента (Argon) проверяется построчно: каждое file:line, имя функции, цитата и вердикт сверяются с кодом; выдуманные тесты и пути удаляются, список исправлений ведётся в «Ограничениях проверки»"
  - "Пробы «ПРОБА» из черновика выполняются самим исполнителем с кодом возврата и числом passed"

requirements-completed: []

duration: "не измерена (время старта не записано в начале плана)"
completed: 2026-10-18

actuals:
  tokens: 6254      # chars/4 над V2-05-VERIFICATION.md + V2-07-VERIFICATION.md (25016 символов); SUMMARY не учтён
  tasks: 3
  commits: 3        # измерено: git rev-list --count c513122..HEAD (до коммита SUMMARY)
plan_head_before: c513122ab8b5de28cb83b209c03268c4c4cb1efd
plan_head_after: ed1eb4c49e145dedc016156065af51bc7dfb8a94
---

# Phase 5 Plan 03: V2-05 (HIT-01) и V2-07 верификация

## Результат

- **HIT-01: passed (трасса+e2e).** Трасса от колбэков бота до `resume_action` подтверждена чтением: `hitl:confirm:` → `cb_hitl_confirm` (`src/notifier/bot_handler.py:2051`, `resume_action` `:2078`); `act:*:conf:` → `_handle_hitl_action_callback` (`:2358`, `resume_action` `:2401`); `engine.py:28-62` → `store.py:116-139`. Миграция `0002_pending_confirmations.sql` применяется при старте (`src/main.py:647` → `db.py:73-75` → `migrator.py`). Тесты: 18 passed ×3 прогона, 211 passed (shared), коды возврата 0.
- **Gap HIT-05 (кандидат):** обход единой точки в очистке диалога. Записан по коду с точными ссылками, в фазе не исправлен (D-10).
- **V2-07:** требований фазы 5 нет, покрытие v3 переписано из `04-VERIFICATION.md` (GIT-01 PARTIAL override; GIT-02..04, NTN-01..02 SATISFIED). Свежий прогон четырёх reachability-файлов: 246 passed, код 0.
- Код, тесты и миграции не менялись. Изменения только в `.planning/phases/05-retro-verifikatsiya-v2-0/`.

## Коммиты

- `83c744d` docs(05-03): V2-05 HIT-01 verdict with trace from bot callbacks to resume_action
- `211866c` docs(05-03): V2-05 gap HIT-05 for direct clear bypass in cb_dlg_confirm_clear
- `ed1eb4c` docs(05-03): V2-07 cross-reference to v3 phase 4 coverage; finalize V2-05 (gaps_found)

## Argon-черновик (вход)

Черновик `/tmp/claude-0/-opt-assistant-core/e2ca4d81-1caf-44dc-8ab4-f93627813d7b/scratchpad/argon/05-03-ARGON-DRAFT.md` использован как входной. Исправлено **24 пункта**, добавлено **1** (подробный список в разделе «Ограничения проверки» V2-05-VERIFICATION.md). Главное:

- выдуманные тесты: «слэш-защита /clear» (`test_hitl_telegram_cards.py`), «asyncio.gather» (`test_hitl_shared.py`), «повторное нажатие» (`test_bot_hitl_parity.py`);
- выдуманные пути в V2-07: `src/integrations/git_source.py`, `src/integrations/notion_project_sync.py`;
- неверный статус GIT-01 («passed» вместо «PARTIAL (override)»);
- неверная сигнатура `handler(conf.target_id, conf.payload)` (реально `handler(conf)`), неверная таблица журнала (`bot_dialog_history.is_archived`);
- привязка gap к «Фазе 6» и плану 05-04 (верно: бэклог 999.3, план 05-08);
- пробы «ПРОБА» не выполнялись (выполнены здесь);
- ссылки на `file:///var/tmp/argon-p5...` (чужой клон) заменены путями репозиториев.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Исправлены ошибки черновика Argon в обоих файлах**
- **Found during:** Задачи 1-3
- **Issue:** черновик содержал неверные номера строк, выдуманные тесты и пути, неверный формат таблицы (ID в обратных кавычках, HIT-05 в таблице вердиктов)
- **Fix:** каждый пункт сверён с кодом и исправлен; формат приведён к D-06 и образцу V2-06
- **Files modified:** V2-05-VERIFICATION.md, V2-07-VERIFICATION.md
- **Commit:** 83c744d, 211866c, ed1eb4c

### Deliberate departures

- `requirements.mark-complete` не выполнен: план перечисляет `VER-01, HIT-01`, но `REQUIREMENTS.md` по инструкции владельца ведётся планом 05-08. Статусы не менялись.
- Длительность не записана: время старта в начале плана не фиксировалось. В `actuals` указаны `tasks` и `commits`.

Иначе план выполнен как написан.

## Auth Gates

Нет.

## Known Stubs

Нет (документы верификации, без кода).

## Threat Flags

Нет новых поверхностей. Обход в cb_dlg_confirm_clear уже описан как T-05-07 и записан как gap.

## Self-Check: PASSED

Файлы V2-05, V2-07 и SUMMARY существуют. Коммиты 83c744d, 211866c, ed1eb4c есть в истории. Вне `.planning/` изменений нет. `/opt/assistant-shared` не изменён: `git status --porcelain --ignored` совпал до и после прогона.

## Открытые вопросы владельца

1. Подтвердить решение №3 записью в владельческом источнике: в `05-CONTEXT.md` нумерованных решений нет, номер цитирует только план.
2. Подтвердить бэклог Phase 999.3 для HIT-05 (план 05-08 создаст запись).
3. Решить, оставить ли текст HIT-01 с декоратором `@requires_confirmation` (буква требования) или заменить на `ConfirmationStore + resume_action`.
4. Решить по расхождению в `04-VERIFICATION.md` (frontmatter `passed`, тело `human_needed`): переоценить или оставить.
