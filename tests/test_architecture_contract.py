"""Тесты архитектурного контракта import-linter (FND-02, Фаза 1).

Реальный конфиг проверяет гейт (scripts/gate.py chat-app). Здесь доказывается, что
контракт не "молчит": падает на нарушении, не может быть пустым, долг ограничен сверху.
Все подпроцессы работают только на синтетических файлах и копиях кода в tmp_path.
"""

import configparser
import os
import shutil
import subprocess
import sys
from pathlib import Path

import grimp

# Без .resolve(): симлинк python в venv ведёт на системный интерпретатор, и каталог bin уже не venv.
LINT = Path(sys.executable).parent / "lint-imports"
REAL_CONFIG = Path(__file__).resolve().parents[1] / ".importlinter"
REAL_PACKAGE = Path(__file__).resolve().parents[1] / "src"

# Верхняя граница долга: Фаза 2 (PRT-04) опускает её до 0, увеличивать нельзя.
MAX_IGNORED_IMPORTS = 5

LINT_ARGS = ["--no-logo", "--no-cache"]

SYNTH_CONTRACT = """\
[importlinter]
root_package = synthpkg

[importlinter:contract:c]
name = brain not adapters
type = forbidden
source_modules =
    synthpkg.brain
forbidden_modules =
    synthpkg.connectors
"""


def _run_lint(cwd: Path, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    assert LINT.is_file(), "не установлен import-linter — см. requirements-dev.txt"
    env = {**os.environ, **env_extra} if env_extra else None
    return subprocess.run(
        [str(LINT), *LINT_ARGS],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _build_synth(root: Path, violate: bool) -> None:
    for sub in ("synthpkg", "synthpkg/brain", "synthpkg/connectors"):
        (root / sub).mkdir(parents=True, exist_ok=True)
        (root / sub / "__init__.py").write_text("", encoding="utf-8")
    (root / "synthpkg/connectors/gw.py").write_text("X = 1\n", encoding="utf-8")
    if violate:
        body = "def f():\n    from synthpkg.connectors.gw import X\n    return X\n"
    else:
        body = "def f():\n    return 1\n"
    (root / "synthpkg/brain/uc.py").write_text(body, encoding="utf-8")
    (root / ".importlinter").write_text(SYNTH_CONTRACT, encoding="utf-8")


def _lines(value: str) -> list[str]:
    """Многострочное значение конфига -> строки без пустых и без комментариев."""
    return [
        line.strip()
        for line in value.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _read_real_config() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(REAL_CONFIG, encoding="utf-8")
    return parser


def _contracts(parser: configparser.ConfigParser) -> list[configparser.SectionProxy]:
    return [parser[s] for s in parser.sections() if s.startswith("importlinter:contract:")]


def _ignored_pairs(contract: configparser.SectionProxy) -> list[tuple[str, str]]:
    pairs = []
    for entry in _lines(contract.get("ignore_imports", "")):
        source, _, target = entry.partition("->")
        pairs.append((source.strip(), target.strip()))
    return pairs


def test_contract_fails_on_intentional_violation(tmp_path):
    _build_synth(tmp_path, violate=True)
    result = _run_lint(tmp_path)
    assert result.returncode != 0, result.stdout
    assert "BROKEN" in result.stdout


def test_contract_passes_on_clean_package(tmp_path):
    _build_synth(tmp_path, violate=False)
    result = _run_lint(tmp_path)
    assert result.returncode == 0, result.stdout


def test_real_contract_modules_exist_in_graph():
    parser = _read_real_config()
    roots = _lines(parser["importlinter"]["root_packages"])
    external = parser["importlinter"].getboolean("include_external_packages", fallback=False)
    graph = grimp.build_graph(*roots, include_external_packages=external, cache_dir=None)
    top_packages = {root.split(".")[0] for root in roots}

    wanted: set[str] = set()
    for contract in _contracts(parser):
        wanted.update(_lines(contract.get("source_modules", "")))
        wanted.update(_lines(contract.get("forbidden_modules", "")))
        for source, target in _ignored_pairs(contract):
            wanted.update((source, target))
    assert wanted, "в реальном конфиге нет ни одного модуля контракта"

    missing = sorted(
        module
        for module in wanted
        if "*" not in module
        and module.split(".")[0] in top_packages
        and module not in graph.modules
    )
    assert not missing, f"модули контракта отсутствуют в графе grimp: {missing}"


def test_ignore_imports_debt_only_shrinks():
    parser = _read_real_config()
    total = sum(len(_ignored_pairs(contract)) for contract in _contracts(parser))
    assert total <= MAX_IGNORED_IMPORTS, (
        f"долг ignore_imports вырос: {total} > {MAX_IGNORED_IMPORTS}"
    )


def test_real_contract_fails_on_injected_violation(tmp_path):
    shutil.copytree(
        REAL_PACKAGE, tmp_path / "src", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copy(REAL_CONFIG, tmp_path / ".importlinter")
    injected = tmp_path / "src" / "brain" / "_injected_violation.py"
    injected.write_text("import src.collector\n", encoding="utf-8")

    result = _run_lint(tmp_path, {"PYTHONPATH": str(tmp_path)})
    assert result.returncode != 0, result.stdout
    assert "BROKEN" in result.stdout
    assert "src.brain._injected_violation" in result.stdout
