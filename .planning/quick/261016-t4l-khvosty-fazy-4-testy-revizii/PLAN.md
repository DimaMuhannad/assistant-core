# Quick 261016-t4l: хвосты фазы 4 (04-REVISION.md, разделы 1, 2, 5)

Сверка с кодом перед работой: раздел 1 пп. 1–3 (VERIFICATION.md) и п. 4 (статус сбоя), раздел 2 пп. 3, 4 уже закрыты в `04-VERIFICATION.md`, `f7b3700` и существующих тестах (`REPO_ROOT = Path(__file__).resolve().parents[1]`, `test_handler_rejects_when_clearance_unknown`, `..._persona_is_none`). Документы фазы не меняются.

Остаётся дописать тесты в `tests/test_phase4_hitl_security_fixes.py`:
1. сбой Notion при подтверждении возвращает карточку в pending (раздел 2 п. 1), мутация: удаление `reopen_action` роняет тест;
2. ноль обращений к Notion между карточкой и подтверждением (п. 5);
3. confirm после reject ничего не пишет (п. 6; reject после confirm уже покрыт).

Вне объёма: пп. 2 и 7 раздела 2, раздел 3, решение по ssh_alias.
