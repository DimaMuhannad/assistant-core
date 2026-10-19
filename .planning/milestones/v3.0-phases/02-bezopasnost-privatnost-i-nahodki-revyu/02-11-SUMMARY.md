---
phase: 02-bezopasnost-privatnost-i-nahodki-revyu
plan: 11
subsystem: privacy
tags: [privacy, persona, help, priv-01, d-14, d-15, d-16, d-21]
status: complete

requires:
  - phase: 02-bezopasnost-privatnost-i-nahodki-revyu
    provides: "02-02, 02-08, 02-10: схема персоны, обёртка shield на данных персоны, библиотека безопасности без слов NDA"
provides:
  - "PrivacyConfig (extra=forbid, frozen) и PersonaConfig.privacy (по умолчанию пустой блок)"
  - "src/persona/notices.py: email_ai_notice(persona), нейтральный запасной текст, EMAIL_AI_NOTICE_FLAG_KEY = notice:email_ai"
  - "Блок «Приватность почты» в конце /help из current_persona(), без обращения к БД"
  - "Текст предупреждения владельца в config/persona.yaml (блок privacy)"
affects: [02-12]

actuals:
  tokens: 14000
  tasks: 4
  commits: 3
plan_head_before: a96945f0b194a10e210380395695d37a4405d99b
plan_head_after: 6b3189f420c83fde9aecd9d3c44c271f66b00c91

key-files:
  created:
    - src/persona/notices.py
    - tests/test_privacy_notice.py
  modified:
    - src/persona/models.py
    - src/notifier/bot_handler.py
    - config/persona.yaml

key-decisions:
  - "Пустое или длиннее 1500 символов email_ai_notice отвергается схемой (EMAIL_AI_NOTICE_MAX_LEN в models.py), поле не задают вовсе, чтобы взять запасной текст (T-02-38)"
  - "Запасной текст нейтрален: без названий сервисов; сервисы из external_ai_services добавляются со словами «и др.»"
  - "Только информирование (D-16): без кнопки согласия и блокировки сбора"

requirements-completed: []
---

# Phase 2 Plan 11: предупреждение о приватности почты в /help Summary

**Предупреждение о передаче содержимого писем внешним ИИ-сервисам (Gemini и др.) показывается в конце `/help`; текст принадлежит данным персоны, в коде только нейтральный запасной текст.**

## Что сделано

- **Схема:** `PrivacyConfig` с полями `email_ai_notice` (после `strip` непустой, до 1500 символов) и `external_ai_services` (непустые названия); `PersonaConfig.privacy` по умолчанию пустой, поэтому `tests/synthetic_persona.py` и его копия в chat-app не менялись, дрейф не возник.
- **Функция:** `email_ai_notice(persona)` в `src/persona/notices.py` (модуль-лист, контракт persona-is-leaf соблюдён). Ключ флага показа для плана 02-12: `EMAIL_AI_NOTICE_FLAG_KEY = "notice:email_ai"`.
- **Справка:** `handle_cmd_help` добавляет блок без обращения к БД (`test_help_handler_does_not_touch_db` зелёный). Длина итогового текста справки с текстом владельца: 1822 символа (лимит Telegram 4096; с максимальным текстом в 1500 символов тест подтверждает длину меньше лимита).
- **Данные владельца:** в `config/persona.yaml` добавлены 2 строки (блок `privacy`), слова NDA не добавлялись.
- **Тесты:** `tests/test_privacy_notice.py` (схема, функция, `/help`, данные владельца, синтетическая персона без блока).

## Разовый обход hook (D-21)

- **Ответ владельца (дословно):** «Разрешаю один раз (Рекомендуется)». Источник: опрос AskUserQuestion владельцу в чате этой сессии, получен через оркестратора. Исполнитель сначала остановился на чекпоинте, потому что согласие пришло только как сообщение агента, и продолжил после подтверждения ответа владельца и записи consent.txt.
- **Коммит с обходом hook:** `95812d1dd748aed1a8700ec68b2fba3d6e357436`. Обход hook был один; коммит выполнен оркестратором по ответу владельца, исполнитель `--no-verify` не использовал.
- **Форма команды:** `git commit --no-verify --only -m ... -- config/persona.yaml` (запись `commit_pathspec=config/persona.yaml` в result.txt).
- **Файлы коммита:** только `config/persona.yaml` (2 вставленные строки).
- **Находки `scripts/security_shield.py . --all`:** перед коммитом 3 (все в `config/persona.yaml`), после него 3, новых нет. Вывод shield не сохранялся.
- **sha256 закоммиченного файла** равен значению в consent.txt (`53a82b70...`).
- Остальные коммиты плана (`f28f4ab`, `6b3189f`) прошли штатный hook без обхода. `.githooks/pre-commit`, `scripts/security_shield.py`, `scripts/gate.py` не менялись.

## Коммиты

| Коммит | Назначение |
|--------|-----------|
| f28f4ab | схема privacy, `email_ai_notice`, блок в `/help`, тесты (Task 1) |
| 95812d1 | текст предупреждения в `config/persona.yaml` (обход hook, D-21) |
| 6b3189f | расширенные тесты данных владельца (Task 2/4, штатный hook) |

## Проверки

- `tests/test_privacy_notice.py`, `test_persona_config`, `test_persona_loader`, `test_hardcode_scanner`, `test_nda_script_parity`: 65 passed; контракты import-linter и сканер хардкода без правки baseline.
- `python3 scripts/gate.py`: ИТОГ: ЗЕЛЁНЫЙ (assistant-core 914 тестов, assistant-shared 197). В окне прогона активный `assistant-worker` писал в боевую БД; гейт сам перемерил в тихом окне, два замера совпали (проверка хеша прошла).
- Автоматические проверки Task 4 (хеш коммита, одно-путь, 3 находки, чистое дерево): пройдены.

## Deviations from Plan

None по коду. Организационно: Task 3 (чекпоинт) сначала вернул управление оркестратору; коммит персоны с `--no-verify` выполнил оркестратор по ответу владельца, а не исполнитель.

## Known Stubs

Нет.

## Threat Flags

Нет новой поверхности атаки.

## Примечание о требованиях

PRIV-01 не отмечен выполненным: требование объявляют также 02-12 (показ при старте сборщика и в `auth_google.py`); этот план закрывает часть `/help`.

## Self-Check: PASSED

Файлы `src/persona/notices.py`, `tests/test_privacy_notice.py` найдены; коммиты `f28f4ab`, `95812d1`, `6b3189f` в истории.
