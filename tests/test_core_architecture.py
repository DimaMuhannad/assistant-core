"""Тесты чистоты ядра src.core (D-01, D-02): контракт, рантайм-страж, полнота запретов.

Хелперы берутся из tests.test_architecture_contract (сам файл не меняется).
"""

import subprocess
import sys
from pathlib import Path

from tests.test_architecture_contract import _contracts, _ignored_pairs, _lines, _read_real_config

REPO = Path(__file__).resolve().parents[1]

PROFILE_TOKENS = ("тидекс", "tydex", "гуап", "guap")

_RUNTIME_PROBE = """
import importlib, pkgutil, sys
before = set(sys.modules)
import src.core
for m in pkgutil.walk_packages(src.core.__path__, "src.core."):
    importlib.import_module(m.name)
bad = sorted(
    n for n in set(sys.modules) - before
    if n.split(".")[0] not in sys.stdlib_module_names
    and n != "src"
    and not n.startswith("src.core")
)
if bad:
    print("\\n".join(bad))
    sys.exit(1)
"""


def _contract(name: str):
    parser = _read_real_config()
    return parser[f"importlinter:contract:{name}"]


def test_core_imports_only_stdlib_and_core():
    result = subprocess.run(
        [sys.executable, "-c", _RUNTIME_PROBE],
        cwd=str(REPO),
        timeout=60,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"ядро подгрузило лишнее:\n{result.stdout}{result.stderr}"


def test_core_is_pure_forbids_every_other_src_module():
    children: set[str] = set()
    for entry in (REPO / "src").iterdir():
        if entry.is_dir():
            if entry.name in {"__pycache__", "core"} or entry.name.startswith("."):
                continue
            children.add(f"src.{entry.name}")
        elif entry.suffix == ".py" and entry.name != "__init__.py":
            children.add(f"src.{entry.stem}")

    forbidden = set(_lines(_contract("core-is-pure")["forbidden_modules"]))
    missing = children - forbidden
    assert not missing, f"core-is-pure не запрещает: {sorted(missing)}"


def test_core_has_no_profile_tokens():
    offenders = []
    for path in (REPO / "src" / "core").rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        offenders += [f"{path.name}: {t}" for t in PROFILE_TOKENS if t in text]
    assert not offenders, offenders


def test_use_case_contracts_not_weakened():
    assert _contracts(_read_real_config()), "в конфиге нет контрактов"

    brain = set(_lines(_contract("brain-no-adapters")["forbidden_modules"]))
    handler = set(_lines(_contract("bot-handler-no-adapters")["forbidden_modules"]))
    ticker = set(_lines(_contract("live-ticker-no-adapters")["forbidden_modules"]))
    assert brain >= {
        "src.connectors", "src.calendar", "src.parser",
        "src.sender", "src.collector", "src.notifier",
    }
    assert handler >= {
        "src.connectors", "src.calendar", "src.parser",
        "src.sender", "src.collector",
    }
    assert ticker >= {
        "src.connectors", "src.calendar", "src.parser",
        "src.sender", "src.collector",
    }


def test_ignore_imports_debt_is_zero():
    """D-15: ни один контракт реального конфига не прячет импорты в ignore_imports."""
    contracts = _contracts(_read_real_config())
    assert contracts, "в конфиге нет контрактов"
    debt = {c.name: _ignored_pairs(c) for c in contracts if _ignored_pairs(c)}
    assert not debt, f"осталась запись ignore_imports: {debt}"
