"""Красные кейсы гейта на мини-проектах во временном каталоге (GATE-01, T-01-13, T-01-14).

Каждый тест строит крошечный проект в ``tmp_path`` и гонит через него настоящий
``gate.run_pytest_step`` (настоящий подпроцесс pytest). Красные кейсы утверждают
``ok is False``, зелёный контроль утверждает ``ok is True``: так видно, что гейт
не «всегда красный». Сам ``scripts/gate.py`` целиком здесь не запускается (рекурсия),
боевая БД не открывается.

Модуль ``gate`` грузится по пути к ``scripts/gate.py`` под собственным именем в
``sys.modules``, независимо от ``tests/test_gate.py``.

Литералы пометок пропуска и xfail встречаются только как строки содержимого мини-проектов.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

_GATE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "gate.py"
_spec = importlib.util.spec_from_file_location("gate_for_red_cases", _GATE_PATH)
gate = importlib.util.module_from_spec(_spec)
# dataclass в модуле с отложенными аннотациями ищет свой модуль в sys.modules
sys.modules["gate_for_red_cases"] = gate
_spec.loader.exec_module(gate)

# Путь к pytest берётся от интерпретатора теста без resolve() (правило .planning/codebase/TESTING.md)
PYTEST_BIN = Path(sys.executable).parent / "pytest"

PASSING_TWO = {
    "test_a.py": "def test_one():\n    assert 1 + 1 == 2\n\n\ndef test_two():\n    assert 'a' in 'abc'\n",
}


def _project(tmp_path, files, ini=None):
    """Мини-проект: каталог tests/ с переданными файлами и, при необходимости, pytest.ini."""
    project = tmp_path / "mini"
    tests_dir = project / "tests"
    tests_dir.mkdir(parents=True)
    for name, body in files.items():
        (tests_dir / name).write_text(body, encoding="utf-8")
    if ini is not None:
        (project / "pytest.ini").write_text(ini, encoding="utf-8")
    return project


def _step(project, tmp_path, env_extra=None):
    """Один настоящий запуск шага pytest гейта на мини-проекте."""
    work = tmp_path / "gate-work"
    work.mkdir(exist_ok=True)
    return gate.run_pytest_step(
        "mini",
        pytest_bin=PYTEST_BIN,
        target="tests",
        cwd=project,
        env_extra=env_extra,
        tmp_dir=work,
        save_dir=None,
    )


def test_green_control_project(tmp_path):
    result = _step(_project(tmp_path, PASSING_TWO), tmp_path, gate.shared_pytest_env())
    assert result.ok is True
    assert result.name == "pytest — тестов: 2"


def test_failing_test_is_red(tmp_path):
    files = {"test_a.py": "def test_broken():\n    assert 1 == 2\n"}
    result = _step(_project(tmp_path, files), tmp_path, gate.shared_pytest_env())
    assert result.ok is False
    assert "test_broken" in result.detail


def test_skipped_test_is_red(tmp_path):
    body = "import pytest\n\n\n@pytest.mark.skip(reason='r')\ndef test_s():\n    assert True\n"
    result = _step(_project(tmp_path, {"test_a.py": body}), tmp_path, gate.shared_pytest_env())
    assert result.ok is False


def test_xfail_is_red(tmp_path):
    body = "import pytest\n\n\n@pytest.mark.xfail\ndef test_x():\n    assert False\n"
    result = _step(_project(tmp_path, {"test_a.py": body}), tmp_path, gate.shared_pytest_env())
    assert result.ok is False


def test_xpass_is_red(tmp_path):
    body = "import pytest\n\n\n@pytest.mark.xfail\ndef test_x():\n    assert True\n"
    result = _step(_project(tmp_path, {"test_a.py": body}), tmp_path, gate.shared_pytest_env())
    assert result.ok is False


def test_deselected_by_addopts_is_red(tmp_path):
    project = _project(tmp_path, PASSING_TWO, ini="[pytest]\naddopts = -k test_one\n")
    result = _step(project, tmp_path, gate.shared_pytest_env())
    assert result.ok is False
    assert "deselected" in result.detail


def test_zero_tests_is_red(tmp_path):
    result = _step(_project(tmp_path, {}), tmp_path, gate.shared_pytest_env())
    assert result.ok is False
    assert "не собрано ни одного теста" in result.detail


def test_pytest_addopts_env_does_not_narrow_the_suite(tmp_path, monkeypatch):
    # Фильтр, которому ничего не соответствует: без очистки PYTEST_ADDOPTS набор опустел бы.
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k нет_такого_теста")
    project = _project(tmp_path, PASSING_TWO)
    shared = _step(project, tmp_path, gate.shared_pytest_env())
    core = _step(project, tmp_path, gate.core_pytest_env(tmp_path / "core-test.db"))
    assert shared.ok is True and shared.name == "pytest — тестов: 2"
    assert core.ok is True and core.name == "pytest — тестов: 2"
    # контроль: без env_extra тот же фильтр действительно сужает набор, то есть тест не пустой
    unprotected = _step(project, tmp_path, None)
    assert unprotected.ok is False


def test_missing_pytest_binary_is_red(tmp_path):
    result = gate.run_pytest_step(
        "mini",
        pytest_bin=tmp_path / "нет" / "pytest",
        target="tests",
        cwd=_project(tmp_path, PASSING_TWO),
        env_extra=None,
        tmp_dir=tmp_path,
        save_dir=None,
    )
    assert result.ok is False
    assert "не найден pytest" in result.detail


def test_timeout_is_red(tmp_path, monkeypatch):
    def slow(cmd, *args, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(gate, "run_cmd", slow)
    result = _step(_project(tmp_path, PASSING_TWO), tmp_path, gate.shared_pytest_env())
    assert result.ok is False
    assert "превышено время выполнения pytest" in result.detail
