"""Юнит-тесты чистых функций локального гейта scripts/gate.py.

Здесь нет запуска полного гейта и подпроцессов pytest: гейт сам запускает
pytest assistant-core, и такой вызов из теста дал бы рекурсию. Боевая БД тестами
не открывается (страж tests/live_db_guard.py): временные файлы только в tmp_path.
"""

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_GATE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "gate.py"
_spec = importlib.util.spec_from_file_location("gate", _GATE_PATH)
gate = importlib.util.module_from_spec(_spec)
# dataclass в модуле с отложенными аннотациями ищет свой модуль в sys.modules
sys.modules["gate"] = gate
_spec.loader.exec_module(gate)

CheckResult = gate.CheckResult


# --- overall_green и render_report ---


def test_overall_green_empty_list_is_red():
    assert gate.overall_green([]) is False


def test_overall_green_single_green_is_green():
    assert gate.overall_green([CheckResult("assistant-core", "x", True)]) is True


def test_overall_green_one_red_among_green_is_red():
    results = [CheckResult("assistant-core", "a", True), CheckResult("assistant-core", "b", False)]
    assert gate.overall_green(results) is False


def test_render_report_all_green():
    report = gate.render_report([CheckResult("assistant-core", "import-linter", True)])
    lines = report.splitlines()
    assert lines[-1] == "ИТОГ: ЗЕЛЁНЫЙ"
    assert "✓" in report
    assert "Репозиторий" in report and "Проверка" in report and "Результат" in report


def test_render_report_one_red_shows_detail_and_red_verdict():
    report = gate.render_report(
        [
            CheckResult("assistant-core", "a", True),
            CheckResult("assistant-core", "b", False, "первая причина\nвторая причина"),
        ]
    )
    assert report.splitlines()[-1] == "ИТОГ: КРАСНЫЙ"
    assert "✗" in report
    assert "↳ первая причина" in report
    assert "↳ вторая причина" in report


def test_render_report_green_row_shows_info_with_dot_prefix():
    report = gate.render_report([CheckResult("assistant-core", "a", True, info="замер: 12")])
    assert "· замер: 12" in report
    assert "↳" not in report


def test_render_report_empty_list_is_red():
    assert gate.render_report([]).splitlines()[-1] == "ИТОГ: КРАСНЫЙ"


# --- import-linter ---


def test_lint_imports_step_missing_binary_is_red_without_exception(tmp_path):
    result = gate.run_lint_imports_step(
        "assistant-core", tmp_path / "нет" / "lint-imports", tmp_path, None
    )
    assert result.ok is False
    assert "requirements-dev.txt" in result.detail


def test_lint_imports_step_missing_repo_dir_is_red(tmp_path):
    fake_bin = tmp_path / "lint-imports"
    fake_bin.write_text("", encoding="utf-8")
    result = gate.run_lint_imports_step("assistant-core", fake_bin, tmp_path / "нет", None)
    assert result.ok is False
    assert "нет каталога" in result.detail


def test_lint_imports_step_timeout_is_red(tmp_path, monkeypatch):
    fake_bin = tmp_path / "lint-imports"
    fake_bin.write_text("", encoding="utf-8")

    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(gate, "run_cmd", boom)
    result = gate.run_lint_imports_step("assistant-core", fake_bin, tmp_path, None)
    assert result.ok is False
    assert "превышено время" in result.detail


def test_lint_imports_step_broken_contract_lists_arrows(tmp_path, monkeypatch):
    fake_bin = tmp_path / "lint-imports"
    fake_bin.write_text("", encoding="utf-8")
    out = "core-is-pure BROKEN\nsrc.core.a -> src.brain.b\nнезначимая строка\n"
    monkeypatch.setattr(
        gate, "run_cmd", lambda *a, **k: subprocess.CompletedProcess(a, 1, out, "")
    )
    result = gate.run_lint_imports_step("assistant-core", fake_bin, tmp_path, None)
    assert result.ok is False
    assert "BROKEN" in result.detail and "->" in result.detail
    assert "незначимая" not in result.detail


def test_lint_imports_step_green_on_zero_returncode(tmp_path, monkeypatch):
    fake_bin = tmp_path / "lint-imports"
    fake_bin.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        gate, "run_cmd", lambda *a, **k: subprocess.CompletedProcess(a, 0, "", "")
    )
    assert gate.run_lint_imports_step("assistant-core", fake_bin, tmp_path, None).ok is True


def test_safe_lint_step_turns_exception_into_red_row(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("синтетический сбой")

    monkeypatch.setattr(gate, "run_lint_imports_step", boom)
    result = gate._safe_lint_step("assistant-core")
    assert result.ok is False
    assert result.name == "import-linter"
    assert "сбой шага" in result.detail and "RuntimeError" in result.detail


# --- run_cmd, main ---


def test_run_cmd_passes_env_extra_and_captures_output(tmp_path):
    proc = gate.run_cmd(
        [sys.executable, "-c", "import os;print(os.environ['GATE_PROBE'])"],
        tmp_path,
        {"GATE_PROBE": "значение"},
        timeout=30,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "значение"


def test_main_returns_zero_for_green_results(monkeypatch, capsys):
    monkeypatch.setattr(gate, "_run_all", lambda save_dir: [CheckResult("assistant-core", "a", True)])
    assert gate.main([]) == 0
    assert "ИТОГ: ЗЕЛЁНЫЙ" in capsys.readouterr().out


def test_main_returns_one_for_red_results(monkeypatch, capsys):
    monkeypatch.setattr(gate, "_run_all", lambda save_dir: [CheckResult("assistant-core", "a", False, "x")])
    assert gate.main([]) == 1
    assert "ИТОГ: КРАСНЫЙ" in capsys.readouterr().out


def test_main_returns_one_for_empty_results(monkeypatch, capsys):
    monkeypatch.setattr(gate, "_run_all", lambda save_dir: [])
    assert gate.main([]) == 1
    assert "ИТОГ: КРАСНЫЙ" in capsys.readouterr().out


def test_main_turns_internal_exception_into_red_row(monkeypatch, capsys):
    def boom(save_dir):
        raise OSError("синтетический сбой")

    monkeypatch.setattr(gate, "_run_all", boom)
    assert gate.main([]) == 1
    out = capsys.readouterr().out
    assert "работа гейта" in out and "OSError" in out and "ИТОГ: КРАСНЫЙ" in out


def test_main_passes_save_dir_to_run_all(monkeypatch, tmp_path, capsys):
    seen = {}

    def fake(save_dir):
        seen["dir"] = save_dir
        return [CheckResult("assistant-core", "a", True)]

    monkeypatch.setattr(gate, "_run_all", fake)
    assert gate.main(["--save-pytest-output", str(tmp_path / "snap")]) == 0
    assert seen["dir"] == (tmp_path / "snap").resolve()


# --- свойства исходника ---


def _gate_tree() -> ast.Module:
    return ast.parse(_GATE_PATH.read_text(encoding="utf-8"))


def test_gate_imports_only_standard_library():
    stdlib = sys.stdlib_module_names
    modules = set()
    for node in ast.walk(_gate_tree()):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
    assert modules <= stdlib, f"не stdlib: {sorted(modules - stdlib)}"


def test_gate_never_uses_shell_true():
    for node in ast.walk(_gate_tree()):
        if isinstance(node, ast.keyword) and node.arg == "shell":
            assert isinstance(node.value, ast.Constant) and node.value.value is False
