# Phase 1: Собственный гейт качества assistant-core - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-09
**Phase:** 01-sobstvennyy-geyt-kachestva-assistant-core
**Areas discussed:** Тесты assistant-shared, Смоук «бот отвечает», Скрипт выкатки, Общий gate.py chat-app

---

## Тесты assistant-shared

| Вопрос | Варианты | Выбрано |
|--------|----------|---------|
| Источник тестов | Перенести из chat-app / Написать новые / На усмотрение Claude | Перенести из chat-app |
| Копии в chat-app | Оставить / Удалить через /gsd-quick | Оставить |
| Окружение | .venv assistant-core / Свой .venv | .venv assistant-core |
| Pre-commit hook | Тот же shield / Shield + тесты | Тот же shield |
| Shield по assistant-shared в гейте | Да, отдельной строкой / Только pytest | Да, отдельной строкой |

## Смоук «бот отвечает»

| Вопрос | Варианты | Выбрано |
|--------|----------|---------|
| Способ | Авто + владелец шлёт команду / Только авто (getMe, polling) / Telethon автоматически | Авто + владелец шлёт команду |
| Команда | /help / /status / Новая /ping | /help |
| Ошибка в журнале | ERROR/Traceback красный, warning показать / Любой warning красный | ERROR/Traceback красный, warning показать |

## Скрипт выкатки

| Вопрос | Варианты | Выбрано |
|--------|----------|---------|
| Разрешение на рестарт | Опрос в чате + флаг / Только вручную в терминале | Опрос в чате + флаг |
| Резервная копия БД | Всегда с ротацией / Только по флагу | Только по флагу |
| Красный смоук | Отчёт + инструкция отката / Автооткат | Отчёт + инструкция отката |
| Отчёт | Файл + VERIFICATION.md / Только терминал | Файл + VERIFICATION.md |

**Notes:** резервная копия выбрана «только по флагу». Claude зафиксировал (D-11), что Phase 3 обязана использовать этот флаг перед миграцией 0003.

## Общий gate.py chat-app

| Вопрос | Варианты | Выбрано |
|--------|----------|---------|
| Часть assistant-core в общем гейте | Не трогать / Убрать / Общий вызывает новый | Не трогать |
| Нет копии chat-app для дрейфа | КРАСНЫЙ / «не проверено» | КРАСНЫЙ |

## Claude's Discretion

- Механизм изоляции БД тестов от `load_dotenv(override=True)` (GATE-02)
- Устройство и формат `scripts/gate.py`, имена флагов скрипта выкатки, таймауты, окно журнала

## Deferred Ideas

- Удаление дублей тестов из chat-app; удаление части assistant-core из общего гейта — отклонено владельцем
