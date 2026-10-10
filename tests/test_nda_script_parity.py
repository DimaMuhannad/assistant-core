"""P01 (PER-04, SECF-01, D-10, D-21): обёртка scripts/security_shield.py не хранит слова NDA и передаёт данные персоны.

Значения нигде не печатаются: сравнение выносится в булеву переменную, сообщения без значений.
Литерал из исходника библиотеки не читается: проверку отсутствия литералов в библиотеке добавляет план 02-10.
"""

import importlib.util
from pathlib import Path

from src.persona.loader import load_persona

SHIELD_PATH = Path(__file__).resolve().parents[1] / "scripts" / "security_shield.py"


def _shield_module():
    spec = importlib.util.spec_from_file_location("security_shield_under_test", SHIELD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p01_script_has_no_nda_word_constants():
    module = _shield_module()
    has_attribute = hasattr(module, "CORPORATE_NDA_KEYWORDS")
    assert not has_attribute, "обёртка не должна экспортировать слова NDA"
    in_source = "CORPORATE_NDA_KEYWORDS" in SHIELD_PATH.read_text(encoding="utf-8")
    assert not in_source, "обёртка не должна упоминать константу слов NDA"


def test_p01_script_passes_persona_workspaces_and_nothing_else(tmp_path, monkeypatch):
    monkeypatch.delenv("PERSONA_CONFIG_PATH", raising=False)
    expected = [ws.model_dump() for ws in load_persona().workspaces]
    assert expected, "в персоне по умолчанию ожидаются рабочие пространства"
    module = _shield_module()
    calls: list[tuple] = []

    def strict_stub(repo_path, check_staged_only, *, workspaces):
        # Любой лишний аргумент даёт TypeError: допусков и иных смягчений нет (D-21)
        calls.append((repo_path, check_staged_only, workspaces))
        return 0

    monkeypatch.setattr(module, "audit_repository", strict_stub)

    assert module.main(["--all", str(tmp_path)]) == 0
    assert module.main([str(tmp_path)]) == 0

    assert len(calls) == 2
    full_mode, commit_mode = calls
    assert full_mode[1] is False and commit_mode[1] is True
    same_data = full_mode[2] == expected and commit_mode[2] == expected
    assert same_data, "обёртка передала в библиотеку не данные рабочих пространств персоны"
    assert full_mode[0] == tmp_path.resolve() and commit_mode[0] == tmp_path.resolve()
