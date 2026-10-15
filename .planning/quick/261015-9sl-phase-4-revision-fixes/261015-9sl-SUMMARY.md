# Quick 261015-9sl: доработка фазы 4 по 04-REVISION.md. Итог

**Статус: задачи 1-3 выполнены, гейт КРАСНЫЙ по причине вне объёма плана (см. «Гейт»).**

Источник: `.planning/phases/04-tsepochka-git-otsenka-hitl-notion/04-REVISION.md`, разделы 1, 2 и 5.
Код в `src/` не менялся (`git diff 2a375a9 HEAD -- src` пусто). Решение по `ssh_alias`/`remote` в `fetch_remote` не принималось и не реализовано (за владельцем).

## Коммиты

| Коммит | Задача | Содержание |
|---|---|---|
| f50a876 | 1 | `tests/test_phase4_chain_e2e.py`: 6 новых тестов, `marker_commit` реально попадает в коммит NDA-репозитория |
| 0bf4e75 | 2 | `tests/test_notion_git_hitl.py`: 5 fail-closed тестов; `tests/test_git_chain.py`, `tests/test_git_airgap_trap.py`: пути от `Path(__file__).resolve().parents[1]` |
| 6897134 | 3 | `04-VERIFICATION.md`, `04-VERIFICATION-EVIDENCE.md`: критерий 1 частично, число тестов, фраза про ID, раздел 6 |

## Числа тестов

| Файл | До | После |
|---|---|---|
| tests/test_phase4_chain_e2e.py | 17 | 23 |
| tests/test_notion_git_hitl.py | 19 | 24 |
| tests/test_git_chain.py | 20 | 20 |
| tests/test_git_airgap_trap.py | 6 | 6 |
| Итого по четырём файлам | 62 | 73 |

Все четыре файла проходят без skipped, xfailed и deselected. Перед коммитом задачи 1 и 2 — pytest файла: 23 passed и 50 passed (три файла). Путевые тесты проверены из посторонней текущей директории: 3 passed.

## Гейт

`python3 scripts/gate.py` вернул код 1, итог **КРАСНЫЙ**. Девять строк из десяти зелёные. Красная строка: `tests.test_hardcode_scanner::test_no_new_hardcode_outside_baseline`, полный pytest assistant-core 1159 passed и 1 failed из 1160.

Причина: `scripts/agy_argon_review.sh`, строка 32, содержит проверку `grep -qiE 'nda|tydex|corporate|restricted'`. Сканер считает `tydex` токеном профиля владельца и находит одну новую строку класса `organization`, которой нет в baseline. Файл пришёл в коммитах 5ea9519 и 61fda77, в этом плане он не менялся. Мои изменения лежат в `tests/` и `.planning/`, оба пути в allowlist сканера, поэтому новой находки они дать не могли. Входы сканера (`scripts/`, `config/`, `tests/hardcode_baseline.py`, `tests/persona_tokens.py`, `tests/test_hardcode_scanner.py`) с базы 2a375a9 не менялись.

Почему не чинил: исправление означает либо правку строки 32 в скрипте, который отсекает NDA и корпоративные репозитории (это контур безопасности, Air-Gap), либо рост baseline, что сканер запрещает по замыслу. План требует при красном гейте по иной причине остановиться. Решение за владельцем.

Прочие гейт-строки зелёные: SHA-256 боевой БД совпал до и после pytest, import-linter, security_shield, дрейф персоны, pre-commit хук, assistant-shared (211 passed и shield).

## Документы

- Критерий 1 и GIT-01 отмечены «частично». Основание: `SshGitProvider.fetch_remote` (`src/connectors/git/provider.py`, строка 97) запускает `git fetch --all --prune` по локальному `.git/config`, поля `remote`, `ssh_alias`, `host`, `account` не используются.
- В тексте документов нет ни одного ID Notion (проверено по префиксам из `config/persona.yaml`), только номера строк 23, 32, 42, 54.
- Фраза «до ввода боевых ID» и «до выдачи ID» удалены. Статус `passed` в frontmatter не менялся, как и требует план.

## Отклонения от плана

1. Номер строки `fetch_remote` в плане: 98. Фактически `git fetch --all --prune` на строке 97; в документах указана 97.
2. В `test_notion_git_hitl.py` общая проверка вынесена в хелпер `_assert_fail_closed_notion_sync`. Проверки те же, что в плане.
3. В `04-VERIFICATION.md` строка 5 таблицы содержала «17 passed» для e2e; добавлено «на момент приёмки, 23 после доработки» (план явно не требовал, но без этого документ противоречил бы разделу 6).
4. Зонд мутации (тест 2) реализован как подмена `reopen_action` в тесте. Реальной мутации `src/` не делалось (запрет). Проверка «без reopen карточка остаётся confirmed» выполнена через этот зонд.
5. `STATE.md` не обновлялся: план этого не требует.

## Открыто

- Гейт: решение по строке 32 `scripts/agy_argon_review.sh` (владелец или отдельная задача).
- Подключение по `ssh_alias`/`remote` в `fetch_remote`: решение владельца (04-REVISION.md, раздел 5, п. 2).
- Пункты 04-REVISION.md вне этого плана: раздел 2 пп. 2 и 7, раздел 3, раздел 4, раздел 1 п. 4.
- Известное поведение: `cb_ntn_reject` не проверяет статус и после confirm отвечает «Отклонено». Данные не портятся (зафиксировано тестом).
