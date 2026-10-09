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


# ============ Task 2: строгий pytest, изоляция БД, хеш до/после, дрейф персоны ============

import hashlib  # noqa: E402
import sqlite3  # noqa: E402

JUNIT_SUITES = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<testsuites><testsuite name="pytest" errors="1" failures="2" skipped="3" tests="14">'
    '<testcase classname="tests.test_a" name="test_ok"/>'
    '<testcase classname="tests.test_a" name="test_bad"><failure message="x"/></testcase>'
    '<testcase classname="tests.test_b" name="test_err"><error message="y"/></testcase>'
    "</testsuite></testsuites>"
)
JUNIT_SUITE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="7"/>'
)
GOOD_COUNTS = {"tests": 14, "failures": 0, "errors": 0, "skipped": 0}


def _write(tmp_path, text, name="junit.xml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_pytest_counts_testsuites_root(tmp_path):
    counts = gate.pytest_counts(_write(tmp_path, JUNIT_SUITES))
    assert counts == {"tests": 14, "failures": 2, "errors": 1, "skipped": 3}


def test_pytest_counts_testsuite_root(tmp_path):
    counts = gate.pytest_counts(_write(tmp_path, JUNIT_SUITE))
    assert counts == {"tests": 7, "failures": 0, "errors": 0, "skipped": 0}


def test_pytest_counts_without_testsuite_element_raises(tmp_path):
    with pytest.raises(ValueError):
        gate.pytest_counts(_write(tmp_path, '<?xml version="1.0"?><testsuites/>'))


def test_failed_test_ids_lists_failures_and_errors(tmp_path):
    ids = gate.failed_test_ids(_write(tmp_path, JUNIT_SUITES))
    assert ids == ["tests.test_a::test_bad", "tests.test_b::test_err"]


def test_failed_test_ids_respects_limit(tmp_path):
    cases = "".join(
        f'<testcase classname="t" name="n{i}"><failure message="x"/></testcase>' for i in range(5)
    )
    xml = f'<testsuite name="pytest" tests="5" failures="5">{cases}</testsuite>'
    assert len(gate.failed_test_ids(_write(tmp_path, xml), limit=3)) == 3


def test_pytest_ok_green_case():
    assert gate.pytest_ok(0, GOOD_COUNTS, []) is True


def test_pytest_ok_adjacency_exactly_one_skipped_is_red():
    # граница adjacency: skipped == 1 при всех остальных зелёных
    assert gate.pytest_ok(0, {**GOOD_COUNTS, "skipped": 1}, []) is False


def test_pytest_ok_empty_zero_tests_is_red_for_rc_0_and_rc_5():
    # граница empty: ноль собранных тестов
    assert gate.pytest_ok(0, {**GOOD_COUNTS, "tests": 0}, []) is False
    assert gate.pytest_ok(5, {**GOOD_COUNTS, "tests": 0}, []) is False


@pytest.mark.parametrize(
    "returncode, counts, flags",
    [
        (1, GOOD_COUNTS, []),
        (0, {**GOOD_COUNTS, "failures": 1}, []),
        (0, {**GOOD_COUNTS, "errors": 1}, []),
        (0, GOOD_COUNTS, ["deselected"]),
        (0, GOOD_COUNTS, ["xfailed"]),
        (0, GOOD_COUNTS, ["xpassed"]),
        (0, GOOD_COUNTS, ["skipped"]),
    ],
)
def test_pytest_ok_other_red_cases(returncode, counts, flags):
    assert gate.pytest_ok(returncode, counts, flags) is False


def test_pytest_summary_flags_hidden_deselect_and_xfail():
    output = "...\n=== 10 passed, 2 deselected, 1 xfailed in 3.50s ===\n"
    assert gate.pytest_summary_flags(output) == ["deselected", "xfailed"]


def test_pytest_summary_flags_xpassed_error_and_skipped():
    output = "=== 9 passed, 1 xpassed, 1 skipped, 2 errors in 3.50s ===\n"
    assert gate.pytest_summary_flags(output) == ["errors", "skipped", "xpassed"]


def test_pytest_summary_flags_clean_run():
    assert gate.pytest_summary_flags("=== 14 passed in 2.10s ===\n") == []


def test_pytest_summary_flags_ignores_warnings_word():
    assert gate.pytest_summary_flags("=== 127 passed, 31 warnings in 45.00s ===\n") == []


def test_pytest_summary_flags_no_summary_line_gives_empty():
    assert gate.pytest_summary_flags("просто текст без итоговой строки") == []


# --- core_pytest_env ---


def test_core_pytest_env_normal_path_sets_override_and_clears_addopts(tmp_path):
    db = tmp_path / "gate-core-test.db"
    assert gate.core_pytest_env(db) == {
        "ASSISTANT_DB_PATH_OVERRIDE": str(db),
        "PYTEST_ADDOPTS": "",
    }


def test_core_pytest_env_refuses_live_db():
    with pytest.raises(ValueError):
        gate.core_pytest_env(gate.LIVE_DB)


def test_core_pytest_env_refuses_root_assistant_db():
    with pytest.raises(ValueError):
        gate.core_pytest_env(gate.CORE_DIR / "assistant.db")


def test_core_pytest_env_refuses_any_path_inside_data_dir():
    with pytest.raises(ValueError):
        gate.core_pytest_env(gate.CORE_DIR / "data" / "other-name.db")


def test_core_pytest_env_refuses_live_db_via_dotdot_path():
    sneaky = gate.CORE_DIR / "data" / ".." / "data" / "assistant.db"
    with pytest.raises(ValueError):
        gate.core_pytest_env(sneaky)


def test_core_pytest_env_refuses_wal_sidecar_of_root_db():
    with pytest.raises(ValueError):
        gate.core_pytest_env(gate.CORE_DIR / "assistant.db-wal")


# --- хеш боевой БД (на временной БД) ---


def test_db_content_hash_ignores_wal_checkpoint_but_sees_data_changes(tmp_path):
    db = tmp_path / "temp-copy.db"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT);")
    conn.execute("INSERT INTO t (v) VALUES ('a');")
    conn.commit()
    try:
        before = gate.db_content_hash(db)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        assert gate.db_content_hash(db) == before
        conn.execute("INSERT INTO t (v) VALUES ('b');")
        conn.commit()
        assert gate.db_content_hash(db) != before
    finally:
        conn.close()


def test_sha_or_none_returns_none_for_missing_file(tmp_path):
    assert gate._sha_or_none(tmp_path / "missing.db") is None


def test_sha256_file_matches_hashlib(tmp_path):
    path = tmp_path / "blob.bin"
    path.write_bytes(b"gate" * 1000)
    assert gate.sha256_file(path) == hashlib.sha256(b"gate" * 1000).hexdigest()


# --- db_unchanged_check и диагностика ---


def test_db_unchanged_check_equal_hash_is_green_with_prefix_info():
    digest = "abcdef0123456789" * 4
    result = gate.db_unchanged_check(digest, digest)
    assert result.ok is True
    assert result.repo == "assistant-core"
    assert result.name == "боевая assistant.db не изменена"
    assert result.info == "SHA-256 до/после совпали: abcdef012345"


def test_db_unchanged_check_none_on_either_side_is_red():
    assert gate.db_unchanged_check(None, "x").ok is False
    assert gate.db_unchanged_check("x", None).ok is False
    assert "не удалось вычислить хеш" in gate.db_unchanged_check(None, None).detail


def test_db_unchanged_check_mismatch_is_red_with_diagnostics_and_retry_hint():
    result = gate.db_unchanged_check("a", "b", diagnostics_fn=lambda: "ДИАГНОСТИКА-ПРОБА")
    assert result.ok is False
    assert "хеш боевой БД изменился во время pytest assistant-core" in result.detail
    assert "ДИАГНОСТИКА-ПРОБА" in result.detail
    assert "повторите прогон" in result.detail
    assert "tests/live_db_guard.py" in result.detail


def test_db_unchanged_check_mismatch_uses_db_diagnostics_by_default(monkeypatch):
    monkeypatch.setattr(gate, "_db_diagnostics", lambda: "ПОДМЕНА-ДИАГНОСТИКИ")
    assert "ПОДМЕНА-ДИАГНОСТИКИ" in gate.db_unchanged_check("a", "b").detail


def test_db_unchanged_check_mismatch_stays_red_when_diagnostics_crash():
    def boom():
        raise RuntimeError("нет доступа")

    result = gate.db_unchanged_check("a", "b", diagnostics_fn=boom)
    assert result.ok is False
    assert "диагностика недоступна" in result.detail


def test_db_diagnostics_reports_service_state_and_mtime(tmp_path, monkeypatch):
    fake_db = tmp_path / "live-stand-in.db"
    fake_db.write_bytes(b"x")
    monkeypatch.setattr(gate, "LIVE_DB", fake_db)
    monkeypatch.setattr(
        gate, "run_cmd", lambda *a, **k: subprocess.CompletedProcess(a, 0, "active\n", "")
    )
    text = gate._db_diagnostics()
    assert "active" in text and "UTC" in text


def test_db_diagnostics_without_systemctl_says_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "LIVE_DB", tmp_path / "нет.db")

    def boom(*args, **kwargs):
        raise FileNotFoundError("systemctl")

    monkeypatch.setattr(gate, "run_cmd", boom)
    assert "неизвестно" in gate._db_diagnostics()


def test_db_diagnostics_never_calls_a_mutating_systemctl_verb(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(gate, "LIVE_DB", tmp_path / "нет.db")

    def spy(cmd, *args, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "active", "")

    monkeypatch.setattr(gate, "run_cmd", spy)
    gate._db_diagnostics()
    assert calls and all(cmd[:2] == ["systemctl", "is-active"] for cmd in calls)


# --- дрейф персоны ---


def test_persona_drift_check_identical_copies_is_green(tmp_path):
    a = _write(tmp_path, "SYNTHETIC_PERSONA = {}\n", "a.py")
    b = _write(tmp_path, "SYNTHETIC_PERSONA = {}\n", "b.py")
    result = gate.persona_drift_check(a, b, "синтетическая персона (дрейф SHA-256)")
    assert result.ok is True
    assert result.repo == "assistant-core"
    assert result.name == "синтетическая персона (дрейф SHA-256)"


def test_persona_drift_check_different_copies_is_red_with_sync_hint(tmp_path):
    a = _write(tmp_path, "SYNTHETIC_PERSONA = {}\n", "a.py")
    b = _write(tmp_path, "SYNTHETIC_PERSONA = {'x': 1}\n", "b.py")
    result = gate.persona_drift_check(a, b, "n")
    assert result.ok is False
    assert "синхронизируйте" in result.detail


def test_persona_drift_check_missing_chat_copy_is_red_with_reason(tmp_path):
    core_copy = _write(tmp_path, "x", "core.py")
    result = gate.persona_drift_check(tmp_path / "нет-в-chat-app.py", core_copy, "n")
    assert result.ok is False
    assert "нет файла" in result.detail


def test_persona_drift_check_missing_core_copy_is_red_with_reason(tmp_path):
    chat_copy = _write(tmp_path, "x", "chat.py")
    result = gate.persona_drift_check(chat_copy, tmp_path / "нет-в-core.py", "n")
    assert result.ok is False
    assert "нет файла" in result.detail


def test_persona_drift_check_never_modifies_chat_copy(tmp_path):
    chat_copy = _write(tmp_path, "one", "chat.py")
    core_copy = _write(tmp_path, "two", "core.py")
    before = (chat_copy.read_bytes(), chat_copy.stat().st_mtime_ns)
    gate.persona_drift_check(chat_copy, core_copy, "n")
    assert (chat_copy.read_bytes(), chat_copy.stat().st_mtime_ns) == before


def test_gate_pairs_cover_synthetic_persona_and_persona_tokens():
    assert gate.CHAT_PERSONA == gate.CHAT_APP_DIR / "backend" / "tests" / "synthetic_persona.py"
    assert gate.CORE_PERSONA == gate.CORE_DIR / "tests" / "synthetic_persona.py"
    assert gate.CHAT_TOKENS == gate.CHAT_APP_DIR / "backend" / "tests" / "persona_tokens.py"
    assert gate.CORE_TOKENS == gate.CORE_DIR / "tests" / "persona_tokens.py"


def test_chat_app_dir_and_shared_dir_come_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSISTANT_CHAT_APP_DIR", str(tmp_path / "chat"))
    monkeypatch.setenv("ASSISTANT_SHARED_DIR", str(tmp_path / "shared"))
    spec = importlib.util.spec_from_file_location("gate_envprobe", _GATE_PATH)
    probe = importlib.util.module_from_spec(spec)
    sys.modules["gate_envprobe"] = probe
    try:
        spec.loader.exec_module(probe)
    finally:
        del sys.modules["gate_envprobe"]
    assert probe.CHAT_APP_DIR == tmp_path / "chat"
    assert probe.SHARED_DIR == tmp_path / "shared"
    assert probe.CHAT_PERSONA == tmp_path / "chat" / "backend" / "tests" / "synthetic_persona.py"


# --- run_pytest_step ---


def _fake_pytest_run(junit_xml, stdout, returncode=0, captured=None):
    """Подмена run_cmd: кладёт junit XML туда, куда просит команда, и возвращает вывод."""

    def fake(cmd, cwd, env_extra=None, timeout=0):
        if captured is not None:
            captured.update(cmd=cmd, cwd=cwd, env_extra=env_extra, timeout=timeout)
        junit_arg = next(a for a in cmd if a.startswith("--junitxml="))
        Path(junit_arg.split("=", 1)[1]).write_text(junit_xml, encoding="utf-8")
        return subprocess.CompletedProcess(cmd, returncode, stdout, "")

    return fake


def _fake_pytest_bin(tmp_path):
    return _write(tmp_path, "", "pytest")


def test_run_pytest_step_missing_binary_is_red(tmp_path):
    result = gate.run_pytest_step(
        "assistant-core", tmp_path / "нет-pytest", "tests", tmp_path, None, tmp_path, None
    )
    assert result.ok is False
    assert "не найден pytest" in result.detail
    assert result.name == "pytest — тестов: 0"


def test_run_pytest_step_missing_cwd_is_red(tmp_path):
    result = gate.run_pytest_step(
        "assistant-core", _fake_pytest_bin(tmp_path), "tests", tmp_path / "нет", None, tmp_path, None
    )
    assert result.ok is False
    assert "нет каталога" in result.detail


def test_run_pytest_step_timeout_is_red(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(gate, "run_cmd", boom)
    result = gate.run_pytest_step(
        "assistant-core", _fake_pytest_bin(tmp_path), "tests", tmp_path, None, tmp_path, None
    )
    assert result.ok is False
    assert "превышено время" in result.detail


def test_run_pytest_step_command_is_strict_and_unfiltered(tmp_path, monkeypatch):
    captured = {}
    xml = '<testsuite tests="3" failures="0" errors="0" skipped="0"/>'
    monkeypatch.setattr(
        gate, "run_cmd", _fake_pytest_run(xml, "=== 3 passed in 1.0s ===\n", captured=captured)
    )
    env = {"ASSISTANT_DB_PATH_OVERRIDE": str(tmp_path / "t.db"), "PYTEST_ADDOPTS": ""}
    result = gate.run_pytest_step(
        "assistant-core", _fake_pytest_bin(tmp_path), "tests", tmp_path, env, tmp_path, None
    )
    cmd = captured["cmd"]
    assert result.ok is True and result.name == "pytest — тестов: 3"
    assert cmd[1] == "tests" and "-v" in cmd and "-p" in cmd and "no:cacheprovider" in cmd
    assert "-o" in cmd and "xfail_strict=true" in cmd
    assert any(a.startswith("--junitxml=") for a in cmd)
    assert any(a.startswith("--basetemp=") for a in cmd)
    assert not {"-k", "-m", "--deselect"} & set(cmd)
    assert captured["env_extra"] == env


def test_run_pytest_step_zero_tests_is_red_with_reason(tmp_path, monkeypatch):
    xml = '<testsuite tests="0" failures="0" errors="0" skipped="0"/>'
    monkeypatch.setattr(gate, "run_cmd", _fake_pytest_run(xml, "=== no tests ran in 0.1s ===\n"))
    result = gate.run_pytest_step(
        "assistant-core", _fake_pytest_bin(tmp_path), "tests", tmp_path, None, tmp_path, None
    )
    assert result.ok is False
    assert "не собрано ни одного теста" in result.detail


def test_run_pytest_step_single_skip_is_red(tmp_path, monkeypatch):
    xml = '<testsuite tests="5" failures="0" errors="0" skipped="1"/>'
    monkeypatch.setattr(
        gate, "run_cmd", _fake_pytest_run(xml, "=== 4 passed, 1 skipped in 1.0s ===\n")
    )
    result = gate.run_pytest_step(
        "assistant-core", _fake_pytest_bin(tmp_path), "tests", tmp_path, None, tmp_path, None
    )
    assert result.ok is False
    assert "1 skipped" in result.detail


def test_run_pytest_step_failures_listed_with_summary_line(tmp_path, monkeypatch):
    monkeypatch.setattr(
        gate,
        "run_cmd",
        _fake_pytest_run(JUNIT_SUITES, "=== 2 failed, 1 passed in 1.0s ===\n", returncode=1),
    )
    result = gate.run_pytest_step(
        "assistant-core", _fake_pytest_bin(tmp_path), "tests", tmp_path, None, tmp_path, None
    )
    assert result.ok is False
    assert "=== 2 failed, 1 passed in 1.0s ===" in result.detail
    assert "упал: tests.test_a::test_bad" in result.detail


def test_run_pytest_step_missing_junit_is_red(tmp_path, monkeypatch):
    monkeypatch.setattr(
        gate, "run_cmd", lambda *a, **k: subprocess.CompletedProcess(a, 0, "=== 3 passed in 1s ===", "")
    )
    result = gate.run_pytest_step(
        "assistant-core", _fake_pytest_bin(tmp_path), "tests", tmp_path, None, tmp_path, None
    )
    assert result.ok is False


def test_run_pytest_step_saves_raw_pytest_output_snapshot(tmp_path, monkeypatch):
    xml = '<testsuite tests="3" failures="0" errors="0" skipped="0"/>'
    monkeypatch.setattr(gate, "run_cmd", _fake_pytest_run(xml, "=== 3 passed in 1.0s ===\n"))
    save_dir = tmp_path / "snap"
    env = {"ASSISTANT_DB_PATH_OVERRIDE": str(tmp_path / "t.db")}
    gate.run_pytest_step(
        "assistant-core", _fake_pytest_bin(tmp_path), "tests", tmp_path, env, tmp_path, save_dir
    )
    text = (save_dir / "pytest-assistant-core.txt").read_text(encoding="utf-8")
    assert "=== 3 passed in 1.0s ===" in text
    assert "# Команда:" in text and "# Дата:" in text
    assert str(tmp_path) not in text.split("=== 3 passed")[0].replace("временный каталог", "")


def test_safe_pytest_step_turns_exception_into_red_row(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("синтетический сбой")

    monkeypatch.setattr(gate, "run_pytest_step", boom)
    result = gate._safe_pytest_step("assistant-core")
    assert result.ok is False
    assert "сбой шага" in result.detail


def test_gate_source_has_no_test_filters_and_pins_xfail_strict():
    source = _GATE_PATH.read_text(encoding="utf-8")
    assert "xfail_strict=true" in source
    for forbidden in ('"-k"', '"-m"', "--deselect"):
        assert forbidden not in source


# --- порядок шагов в _run_all (хеш «после» сразу после pytest core) ---


def test_run_all_measures_hash_after_pytest_core_and_before_other_rows(monkeypatch):
    events = []
    monkeypatch.setattr(gate, "_sha_or_none", lambda path: events.append("hash") or "h")
    monkeypatch.setattr(
        gate,
        "_safe_pytest_step",
        lambda repo, **kw: events.append("pytest") or CheckResult(repo, "pytest", True),
    )
    monkeypatch.setattr(
        gate, "_safe_lint_step", lambda repo, **kw: events.append("lint") or CheckResult(repo, "lint", True)
    )
    monkeypatch.setattr(
        gate,
        "persona_drift_check",
        lambda a, b, name: events.append("drift") or CheckResult("assistant-core", name, True),
    )
    results = gate._run_all(None)
    assert events[:4] == ["hash", "pytest", "hash", "lint"]
    assert events[4:] == ["drift", "drift"]
    names = [r.name for r in results]
    assert names.index("боевая assistant.db не изменена") == names.index("pytest") + 1


def test_run_all_isolates_pytest_db_and_removes_temp_dir(monkeypatch):
    seen = {}
    monkeypatch.setattr(gate, "_sha_or_none", lambda path: "h")

    def fake_pytest(repo, **kw):
        seen.update(kw)
        return CheckResult(repo, "pytest", True)

    monkeypatch.setattr(gate, "_safe_pytest_step", fake_pytest)
    monkeypatch.setattr(gate, "_safe_lint_step", lambda repo, **kw: CheckResult(repo, "lint", True))
    monkeypatch.setattr(
        gate, "persona_drift_check", lambda a, b, name: CheckResult("assistant-core", name, True)
    )
    gate._run_all(None)
    override = Path(seen["env_extra"]["ASSISTANT_DB_PATH_OVERRIDE"])
    assert override.name == "gate-core-test.db"
    assert gate.CORE_DIR / "data" not in override.parents
    assert not seen["tmp_dir"].exists()
    assert seen["env_extra"]["PYTEST_ADDOPTS"] == ""
    assert seen["target"] == "tests" and seen["cwd"] == gate.CORE_DIR
