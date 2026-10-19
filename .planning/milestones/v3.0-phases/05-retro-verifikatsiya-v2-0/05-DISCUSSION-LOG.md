# Phase 5: Ретро-верификация v2.0 - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-18
**Phase:** 5-Ретро-верификация v2.0
**Areas discussed:** Доказательство достижимости, Раскладка VERIFICATION.md, Нестабильный тест DAT-03, Оформление gaps

---

## Доказательство достижимости

| Вопрос | Выбрано | Альтернативы |
|--------|---------|--------------|
| Метод | Трасса + прогон на врем. БД | только трасса; только тесты |
| Внешние API | Живые вызовы только чтение | только заглушки (рекомендовалось) |
| Смоук deploy.py | Да, read-only | Нет |
| Порог passed | passed (трасса) с пометкой | gap; по риску |

**Notes:** живые вызовы допускаются только без NDA-данных и без записи.

## Раскладка VERIFICATION.md
Папка фазы 5; таблица с доказательством.

## Нестабильный тест DAT-03
30 прогонов; 0 сбоев = stable, любой сбой = gap.

## Оформление gaps
По серьёзности; безопасность только записывать (без остановки); agy собирает, Claude выносит вердикт.

## Claude's Discretion
Разбиение на планы, порядок проверки, формат сводной таблицы.

## Deferred Ideas
None.
