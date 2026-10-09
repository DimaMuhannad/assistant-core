"""Страж правил: CLAUDE.md и .claude/CLAUDE.md указывают на собственный гейт (GATE-05, T-01-25).

После плана 01-05 гейт assistant-core живёт в scripts/gate.py. Если правила для агентов
вернутся к команде общего гейта chat-app, агенты получат ложный «ЗЕЛЁНЫЙ» от чужого набора проверок.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_RULES = REPO_ROOT / "CLAUDE.md"
CLAUDE_DIR_RULES = REPO_ROOT / ".claude" / "CLAUDE.md"

# Прежняя команда собрана из частей: сам тест не становится источником обратной ссылки.
LEGACY_GATE_COMMAND = "python3 " + "/opt/chat-app" + "/scripts/" + "gate.py"
OWN_GATE_COMMAND = "python3 scripts/gate.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_root_claude_md_names_own_gate() -> None:
    text = _text(ROOT_RULES)
    assert OWN_GATE_COMMAND in text
    assert "scripts/gate.py" in _text(CLAUDE_DIR_RULES)


def test_rules_files_do_not_name_legacy_gate_command() -> None:
    for path in (ROOT_RULES, CLAUDE_DIR_RULES):
        text = _text(path)
        assert LEGACY_GATE_COMMAND not in text, f"{path.name}: возврат к команде общего гейта chat-app"
        assert "until assistant-core has its own" not in text, f"{path.name}: устаревшая оговорка про гейт"


def test_root_claude_md_mentions_ops_deploy_doc() -> None:
    text = _text(ROOT_RULES)
    assert "docs/OPS_DEPLOY.md" in text
    assert "scripts/deploy.py" in text
    assert "explicit owner permission" in text
