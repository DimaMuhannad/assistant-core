# Quick 261016-p4r: остаточные дефекты фазы 4 (04-REVISION.md, раздел 4)

Ограничения: ssh_alias/remote в fetch не менять; документы фазы не трогать; тесты не ослаблять.

| # | Дефект | Правка | Тест (падает без правки) |
|---|--------|--------|--------------------------|
| 1 | нет обрезки card_text до 4096 | `GitProgressEvaluator.format_card_text` режет до 4096 | `test_card_text_truncated_to_telegram_limit` |
| 2 | regex «скрой/покажи команду» без git/гит/коммиты | `bot_handler.py`, обе regex | `test_bot_hide_show_git_command_aliases[git, гит, коммиты]` |
| 3 | наивный `datetime.now()` в `_parse_git_log` (находится в `src/connectors/git/provider.py`, не в git_evaluator.py) | `datetime.now(timezone.utc)` | `test_parse_git_log_bad_date_fallback_is_timezone_aware` |
| 4 | UTC-фолбэк даты в `_handle_notion_sync` | общий `_local_date_iso` (config.TZ), как в `collect` | `test_notion_sync_date_fallback_uses_local_timezone` |

Коммиты: 5765e53 (п.2), 6341540 (п.3), cf77525 (п.1 и 4: один файл, общий хелпер).
