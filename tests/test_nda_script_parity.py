"""P01 (PER-04, D-15): правила scripts/security_shield.py совпадают с данными персоны.

NDA-слова нигде не печатаются: сравнение выносится в булеву переменную, сообщения без значений.
"""

import importlib.util
import re
from pathlib import Path

from src.persona.loader import load_persona

SHIELD_PATH = Path(__file__).resolve().parents[1] / "scripts" / "security_shield.py"


def _shield_module():
    spec = importlib.util.spec_from_file_location("security_shield_under_test", SHIELD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _nda_workspace():
    nda = [ws for ws in load_persona().workspaces if ws.clearance == "restricted_nda"]
    assert len(nda) == 1, "в персоне по умолчанию ожидается ровно одно restricted_nda-пространство"
    return nda[0]


def test_p01_script_keywords_match_persona_data():
    ws = _nda_workspace()
    same = set(_shield_module().CORPORATE_NDA_KEYWORDS) == set(ws.forbidden_keywords)
    assert same, "NDA-слова скрипта и данных персоны расходятся"


def test_p01_script_remote_rule_matches_persona_data():
    ws = _nda_workspace()
    source = SHIELD_PATH.read_text(encoding="utf-8")
    found = tuple(re.findall(r'"([^"]+)" in origin_url', source))
    same = found == tuple(ws.forbidden_remote_substrings)
    assert same, "подстрока remote скрипта и данных персоны расходятся"
