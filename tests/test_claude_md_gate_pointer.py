"""Страж правил: CLAUDE.md и .claude/CLAUDE.md указывают на собственный гейт (GATE-05, T-01-25).

После плана 01-05 гейт assistant-core живёт в scripts/gate.py. Если правила для агентов
вернутся к гейту chat-app, агенты получат ложный «ЗЕЛЁНЫЙ» от чужого набора проверок.

Ссылка на чужой гейт может быть записана по-разному (путь к скрипту, составная команда
с cd), поэтому проверка идёт регулярными выражениями, а не одной точной строкой (WR-13).
Шаблоны собраны из частей: сам тест не становится источником обратной ссылки
для проверок безопасности и хардкода.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_RULES = REPO_ROOT / "CLAUDE.md"
CLAUDE_DIR_RULES = REPO_ROOT / ".claude" / "CLAUDE.md"

OWN_GATE_COMMAND = "python3 scripts/gate.py"

# Путь к скрипту гейта chat-app: chat-app/gate.py или chat-app/scripts/gate.py
_CHAT_APP_GATE_PATH = re.compile("chat-app/" + "(?:scripts/)?" + "gate" + r"\.py")
# Составная команда: cd в каталог chat-app, затем интерпретатор с gate.py
_CHAT_APP_GATE_COMPOUND = re.compile(
    r"cd\s+\S*" + "chat-app" + r"\S*\s*(?:&&|;)?\s*python3?\s+\S*" + "gate" + r"\.py"
)
_LEGACY_GATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("путь к гейту chat-app", _CHAT_APP_GATE_PATH),
    ("составная команда cd + gate chat-app", _CHAT_APP_GATE_COMPOUND),
)

# Образцы для самопроверки шаблонов: каждый положительный образец должен сработать
# на свой шаблон, отрицательные не должны срабатывать ни на один из них.
_POSITIVE_PATH_SAMPLES = (
    "python " + "/opt/chat-app" + "/scripts/" + "gate.py",
    "python3 " + "/opt/chat-app" + "/" + "gate.py",
)
_POSITIVE_COMPOUND_SAMPLES = (
    "cd " + "/opt/chat-app" + " && python3 scripts/gate.py",
)
_NEGATIVE_SAMPLES = (
    "python3 scripts/gate.py",
    "cd /opt/assistant-core && python3 scripts/gate.py",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_root_claude_md_names_own_gate() -> None:
    text = _text(ROOT_RULES)
    assert OWN_GATE_COMMAND in text
    assert "scripts/gate.py" in _text(CLAUDE_DIR_RULES)


def test_rules_files_do_not_name_legacy_gate_command() -> None:
    # Сообщение называет только файл и вид ссылки, сам найденный фрагмент не печатается.
    for path in (ROOT_RULES, CLAUDE_DIR_RULES):
        text = _text(path)
        for label, pattern in _LEGACY_GATE_PATTERNS:
            assert pattern.search(text) is None, f"{path.name}: возврат к гейту chat-app ({label})"
        assert "until assistant-core has its own" not in text, f"{path.name}: устаревшая оговорка про гейт"


def test_legacy_gate_patterns_self_check() -> None:
    path_pattern = _CHAT_APP_GATE_PATH
    compound_pattern = _CHAT_APP_GATE_COMPOUND
    for sample in _POSITIVE_PATH_SAMPLES:
        assert path_pattern.search(sample), f"шаблон пути не сработал на образце {sample!r}"
    for sample in _POSITIVE_COMPOUND_SAMPLES:
        assert compound_pattern.search(sample), f"шаблон составной команды не сработал на образце {sample!r}"
    for sample in _NEGATIVE_SAMPLES:
        for label, pattern in _LEGACY_GATE_PATTERNS:
            assert pattern.search(sample) is None, f"ложное срабатывание ({label}) на {sample!r}"


def test_root_claude_md_mentions_ops_deploy_doc() -> None:
    text = _text(ROOT_RULES)
    assert "docs/OPS_DEPLOY.md" in text
    assert "scripts/deploy.py" in text
    assert "explicit owner permission" in text
