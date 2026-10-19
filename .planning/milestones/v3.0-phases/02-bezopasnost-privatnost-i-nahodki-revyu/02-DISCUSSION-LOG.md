# Phase 2: Безопасность, приватность и находки ревью - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-10
**Phase:** 2-Безопасность, приватность и находки ревью
**Areas discussed:** SAFE-01, SECF-01, SECF-02, PRIV-01

---

## SAFE-01: защита «очисти диалог»

| Option | Selected |
|--------|----------|
| Единый путь через HITL-карточку | ✓ |
| Сразу архив + команда отмены | |
| Карточка, при пустой памяти ничего | |

**User's choice:** единый путь через HITL-карточку.
**Notes:** триггеры — если фраза ведёт к очистке памяти, бот выводит предупреждение, что человек должен вручную следующим сообщением ввести команду очистки со слэшем. Ночной сброс: вне фазы, но при онбординге предупредить о сбросе памяти за сутки.

## SECF-01: NDA-режим CLI-аудита

**Choices:** источник — `config/persona.yaml` по пути/remote; неизвестный репозиторий — строгий/предупреждение, данные недоступны — красный; ключевые слова — только `forbidden_keywords` из workspaces (CORPORATE_NDA_KEYWORDS удаляется).

## SECF-02: общая функция сканирования

**Choices:** `scan_file_content` в assistant-shared, `audit_path` её вызывает; keywords внутри `NdaRemoteRule`; фикстуры — синтетические файлы во временном git-репозитории.

## PRIV-01: предупреждение об ИИ-обработке почты

**Choices:** поле в `persona.yaml` + запасной текст; места — `/help`, старт сборщика почты (журнал + Telegram один раз), `auth_google.py`/`.env.example`; только информирование без «принимаю».

## Claude's Discretion

Интерфейс `audit_repository`, способ распознавания «смысл ведёт к очистке», имя поля и хранение флага показа, разбиение на планы.

## Deferred Ideas

Предупреждение о суточном сбросе при онбординге (Phase 8); уведомление после ночного сброса; кнопка согласия; мастер почты (Phase 9).
