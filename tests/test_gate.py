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
    monkeypatch.setattr(gate, "db_integrity_snapshot", lambda path: dict(_SNAP))
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
        "_safe_shield_step",
        lambda repo, repo_dir: events.append("shield") or CheckResult(repo, "shield", True),
    )
    monkeypatch.setattr(
        gate,
        "persona_drift_check",
        lambda a, b, name: events.append("drift") or CheckResult("assistant-core", name, True),
    )
    monkeypatch.setattr(
        gate,
        "_safe_hook_step",
        lambda repo, repo_dir: events.append("hook") or CheckResult(repo, "hook", True),
    )
    results = gate._run_all(None)
    assert events == [
        "hash", "pytest", "hash", "lint", "shield", "drift", "drift", "hook",
        "pytest", "shield", "hook",
    ]  # fmt: skip
    names = [r.name for r in results]
    assert names.index("боевая assistant.db не изменена") == names.index("pytest") + 1


def test_run_all_isolates_pytest_db_and_removes_temp_dir(monkeypatch):
    seen = {}
    monkeypatch.setattr(gate, "_sha_or_none", lambda path: "h")
    monkeypatch.setattr(gate, "db_integrity_snapshot", lambda path: dict(_SNAP))

    def fake_pytest(repo, **kw):
        if repo == gate.REPO_CORE:
            seen.update(kw)
        return CheckResult(repo, "pytest", True)

    monkeypatch.setattr(gate, "_safe_pytest_step", fake_pytest)
    monkeypatch.setattr(
        gate, "_safe_hook_step", lambda repo, repo_dir: CheckResult(repo, "hook", True)
    )
    monkeypatch.setattr(gate, "_safe_lint_step", lambda repo, **kw: CheckResult(repo, "lint", True))
    monkeypatch.setattr(
        gate, "_safe_shield_step", lambda repo, repo_dir: CheckResult(repo, "shield", True)
    )
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


# ============ Task 3: нормализация shield и замороженный список ложных срабатываний ============

import collections  # noqa: E402

# Тексты, которые не должны попасть в таблицу, собраны из частей: файл лежит в tests/,
# а shield сканирует отслеживаемые файлы целиком.
NDA_WORD = "".join(["tydex", "_internal", "_secret"])
AUTHOR_MAIL = "".join(["owner", "@", "example", ".org"])
REMOTE_URL = "".join(["https://", "git.example", "/synthetic/repo.git"])
ALERT = "\U0001F6A8"

_SYNTH_HEADER = (
    "\U0001F6E1 Running Security Shield on repository: {repo}\n"
    f"   • Origin Remote: {REMOTE_URL}\n"
    f"   • Author Email:  {AUTHOR_MAIL}\n"
    "   • Profile Mode:  PUBLIC / ACADEMIC\n"
    "   • Scanning 7 files...\n"
)


def _synthetic_shield_output(repo: Path) -> str:
    return (
        _SYNTH_HEADER.format(repo=repo)
        + "\n❌ SECURITY VIOLATIONS DETECTED:\n"
        + f"   {ALERT} {repo}/docs/a.md:3 - Found proprietary corporate keyword '{NDA_WORD}' in public repository!\n"
        + f"   {ALERT} {repo}/docs/a.md:9 - Found proprietary corporate keyword '{NDA_WORD}' in public repository!\n"
        + f"   {ALERT} {repo}/tests/t.py:12 - Found potential Generic Bearer Secret\n"
        + f"   {ALERT} something unexpected without a known shape\n"
        + "\nCommit or push blocked.\n"
    )


def test_parse_shield_findings_normalizes_and_drops_sensitive_text(tmp_path):
    found = gate.parse_shield_findings(_synthetic_shield_output(tmp_path), tmp_path)
    assert found == {
        ("docs/a.md", "nda-keyword"): 2,
        ("tests/t.py", "secret:Generic Bearer Secret"): 1,
        ("(нераспознано)", "unparsed"): 1,
    }
    flat = " ".join(f"{path} {kind} {count}" for (path, kind), count in found.items())
    assert NDA_WORD not in flat and AUTHOR_MAIL not in flat and REMOTE_URL not in flat
    assert "Origin" not in flat


def test_parse_shield_findings_special_kinds(tmp_path):
    output = (
        f"   {ALERT} Forbidden file pattern committed: credentials.json\n"
        f"   {ALERT} CRITICAL: synthetic remote problem\n"
        f"   {ALERT} {tmp_path}/x.bin - Read error: boom\n"
    )
    assert gate.parse_shield_findings(output, tmp_path) == {
        ("credentials.json", "forbidden-file"): 1,
        ("(remote)", "remote"): 1,
        ("x.bin", "read-error"): 1,
    }


def test_parse_shield_findings_ignores_header_only_output(tmp_path):
    assert not gate.parse_shield_findings(_SYNTH_HEADER.format(repo=tmp_path), tmp_path)


def test_parse_shield_findings_ignores_lines_without_alert_prefix(tmp_path):
    output = f"{tmp_path}/docs/a.md:3 - Found proprietary corporate keyword '{NDA_WORD}'\n"
    assert not gate.parse_shield_findings(output, tmp_path)


def test_parse_shield_findings_returns_counter_without_line_numbers(tmp_path):
    output = (
        f"   {ALERT} {tmp_path}/a.md:1 - Found proprietary corporate keyword 'x'\n"
        f"   {ALERT} {tmp_path}/a.md:99 - Found proprietary corporate keyword 'y'\n"
    )
    found = gate.parse_shield_findings(output, tmp_path)
    assert isinstance(found, collections.Counter)
    assert found == {("a.md", "nda-keyword"): 2}


def test_compare_shield_findings_equal_sets_no_problems():
    found = collections.Counter({("docs/a.md", "nda-keyword"): 2})
    assert gate.compare_shield_findings(found, {("docs/a.md", "nda-keyword"): 2}) == ([], [])


def test_compare_shield_findings_extra_finding_is_new():
    found = collections.Counter({("docs/a.md", "nda-keyword"): 3})
    new, stale = gate.compare_shield_findings(found, {("docs/a.md", "nda-keyword"): 2})
    assert new and not stale
    assert "docs/a.md" in new[0]


def test_compare_shield_findings_missing_finding_is_stale():
    found = collections.Counter({("docs/a.md", "nda-keyword"): 1})
    new, stale = gate.compare_shield_findings(found, {("docs/a.md", "nda-keyword"): 2})
    assert stale and not new


def test_compare_shield_findings_results_are_sorted_by_path_and_kind():
    found = collections.Counter(
        {("z.md", "nda-keyword"): 1, ("a.md", "nda-keyword"): 1, ("a.md", "forbidden-file"): 1}
    )
    allowed = {("y.md", "nda-keyword"): 1, ("b.md", "nda-keyword"): 1}
    new, stale = gate.compare_shield_findings(found, allowed)
    assert [line.split(": ", 1)[1].split(" [")[0] for line in new] == ["a.md", "a.md", "z.md"]
    assert "[forbidden-file]" in new[0] and "[nda-keyword]" in new[1]
    assert [line.split(": ", 1)[1].split(" [")[0] for line in stale] == ["b.md", "y.md"]


def test_known_shield_false_positives_frozen_list_is_exact():
    assert gate.KNOWN_SHIELD_FALSE_POSITIVES == {
        gate.REPO_CORE: {("config/persona.yaml", "nda-keyword"): 3},
        gate.REPO_SHARED: {},
    }


def test_known_shield_false_positives_has_no_chat_app_key():
    assert "chat-app" not in gate.KNOWN_SHIELD_FALSE_POSITIVES


def _fake_repo(tmp_path, script_body="print('stub')\n"):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "security_shield.py").write_text(script_body, encoding="utf-8")
    return tmp_path


def _shield_proc(stdout, returncode=1):
    def fake(cmd, cwd, env_extra=None, timeout=0):
        return subprocess.CompletedProcess(cmd, returncode, stdout, "")

    return fake


def test_run_shield_step_missing_script_is_red(tmp_path):
    result = gate.run_shield_step(gate.REPO_CORE, tmp_path)
    assert result.ok is False
    assert "security_shield.py" in result.detail


def test_run_shield_step_timeout_is_red(tmp_path, monkeypatch):
    repo = _fake_repo(tmp_path)

    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(gate, "run_cmd", boom)
    result = gate.run_shield_step(gate.REPO_CORE, repo)
    assert result.ok is False and "превышено время" in result.detail


@pytest.mark.parametrize("code", [2, 3, 127, -9])
def test_run_shield_step_unexpected_returncode_is_red(tmp_path, monkeypatch, code):
    repo = _fake_repo(tmp_path)
    monkeypatch.setattr(gate, "run_cmd", _shield_proc("   • Scanning 3 files...\n", code))
    result = gate.run_shield_step(gate.REPO_CORE, repo)
    assert result.ok is False
    assert "сбой" in result.detail


def test_run_shield_step_code_one_without_findings_is_red(tmp_path, monkeypatch):
    repo = _fake_repo(tmp_path)
    monkeypatch.setattr(gate, "run_cmd", _shield_proc("   • Scanning 3 files...\n", 1))
    result = gate.run_shield_step(gate.REPO_CORE, repo)
    assert result.ok is False
    assert "без распознанных находок" in result.detail


def test_run_shield_step_scanning_zero_files_is_red(tmp_path, monkeypatch):
    repo = _fake_repo(tmp_path)
    monkeypatch.setattr(gate, "run_cmd", _shield_proc("   • Scanning 0 files...\n", 0))
    result = gate.run_shield_step(gate.REPO_CORE, repo)
    assert result.ok is False
    assert "ничего не просканировал" in result.detail


def test_run_shield_step_no_scanning_line_is_red(tmp_path, monkeypatch):
    repo = _fake_repo(tmp_path)
    monkeypatch.setattr(
        gate, "run_cmd", _shield_proc("   • No staged or modified files found to scan.\n", 0)
    )
    result = gate.run_shield_step(gate.REPO_CORE, repo)
    assert result.ok is False
    assert "ничего не просканировал" in result.detail


def test_run_shield_step_clean_scan_is_green_for_shared_with_empty_list(tmp_path, monkeypatch):
    repo = _fake_repo(tmp_path)
    monkeypatch.setattr(gate, "run_cmd", _shield_proc("   • Scanning 4 files...\n", 0))
    assert gate.run_shield_step(gate.REPO_SHARED, repo).ok is True


def test_run_shield_step_runs_all_mode_with_list_args_and_core_python(tmp_path, monkeypatch):
    repo = _fake_repo(tmp_path)
    seen = {}

    def spy(cmd, cwd, env_extra=None, timeout=0):
        seen.update(cmd=cmd, cwd=cwd, timeout=timeout)
        return subprocess.CompletedProcess(cmd, 0, "   • Scanning 4 files...\n", "")

    monkeypatch.setattr(gate, "run_cmd", spy)
    gate.run_shield_step(gate.REPO_SHARED, repo)
    assert seen["cmd"][1].endswith("security_shield.py") and seen["cmd"][-1] == "--all"
    assert seen["cmd"][0] == str(gate.CORE_VENV_BIN / "python")
    assert seen["cwd"] == repo and seen["timeout"] == gate.SHIELD_TIMEOUT_S


def test_run_shield_step_falls_back_to_current_interpreter_without_core_venv(tmp_path, monkeypatch):
    repo = _fake_repo(tmp_path)
    monkeypatch.setattr(gate, "CORE_VENV_BIN", tmp_path / "нет-venv")
    seen = {}

    def spy(cmd, cwd, env_extra=None, timeout=0):
        seen["python"] = cmd[0]
        return subprocess.CompletedProcess(cmd, 0, "   • Scanning 4 files...\n", "")

    monkeypatch.setattr(gate, "run_cmd", spy)
    gate.run_shield_step(gate.REPO_SHARED, repo)
    assert seen["python"] == sys.executable


def _core_persona_output(repo: Path, count: int) -> str:
    lines = "".join(
        f"   {ALERT} {repo}/config/persona.yaml:{40 + i} - Found proprietary corporate keyword '{NDA_WORD}{i}' in public repository!\n"
        for i in range(count)
    )
    return "   • Scanning 9 files...\n\n❌ SECURITY VIOLATIONS DETECTED:\n" + lines


def test_run_shield_step_core_frozen_entry_matches_exactly_is_green(tmp_path, monkeypatch):
    repo = _fake_repo(tmp_path)
    monkeypatch.setattr(gate, "run_cmd", _shield_proc(_core_persona_output(repo, 3), 1))
    assert gate.run_shield_step(gate.REPO_CORE, repo).ok is True


def test_run_shield_step_core_one_extra_finding_is_red(tmp_path, monkeypatch):
    repo = _fake_repo(tmp_path)
    monkeypatch.setattr(gate, "run_cmd", _shield_proc(_core_persona_output(repo, 4), 1))
    result = gate.run_shield_step(gate.REPO_CORE, repo)
    assert result.ok is False and "новая находка" in result.detail


def test_run_shield_step_core_stale_frozen_entry_is_red(tmp_path, monkeypatch):
    repo = _fake_repo(tmp_path)
    monkeypatch.setattr(gate, "run_cmd", _shield_proc(_core_persona_output(repo, 2), 1))
    result = gate.run_shield_step(gate.REPO_CORE, repo)
    assert result.ok is False and "устаревшая запись" in result.detail


def test_run_shield_step_core_clean_run_makes_frozen_entry_stale(tmp_path, monkeypatch):
    repo = _fake_repo(tmp_path)
    monkeypatch.setattr(gate, "run_cmd", _shield_proc("   • Scanning 9 files...\n", 0))
    result = gate.run_shield_step(gate.REPO_CORE, repo)
    assert result.ok is False and "устаревшая запись" in result.detail


def test_run_shield_step_shared_has_no_allowance_for_any_finding(tmp_path, monkeypatch):
    repo = _fake_repo(tmp_path)
    monkeypatch.setattr(gate, "run_cmd", _shield_proc(_core_persona_output(repo, 3), 1))
    result = gate.run_shield_step(gate.REPO_SHARED, repo)
    assert result.ok is False and "новая находка" in result.detail


def test_run_shield_step_does_not_leak_nda_word_email_or_remote(tmp_path, monkeypatch):
    repo = _fake_repo(tmp_path)
    monkeypatch.setattr(gate, "run_cmd", _shield_proc(_synthetic_shield_output(repo), 1))
    result = gate.run_shield_step(gate.REPO_SHARED, repo)
    assert result.ok is False and "новая находка" in result.detail
    leaked = [s for s in (NDA_WORD, AUTHOR_MAIL, REMOTE_URL, "Origin Remote") if s in result.detail]
    assert not leaked
    report = gate.render_report([result])
    assert NDA_WORD not in report and AUTHOR_MAIL not in report and REMOTE_URL not in report


def test_run_shield_step_failure_detail_never_contains_raw_output(tmp_path, monkeypatch):
    repo = _fake_repo(tmp_path)
    raw = _synthetic_shield_output(repo)
    monkeypatch.setattr(gate, "run_cmd", _shield_proc(raw, 2))
    result = gate.run_shield_step(gate.REPO_SHARED, repo)
    assert NDA_WORD not in result.detail and AUTHOR_MAIL not in result.detail


def test_run_shield_step_limits_detail_lines(tmp_path, monkeypatch):
    repo = _fake_repo(tmp_path)
    lines = "".join(
        f"   {ALERT} {repo}/f{i}.md:1 - Found proprietary corporate keyword 'k'\n" for i in range(40)
    )
    monkeypatch.setattr(gate, "run_cmd", _shield_proc("   • Scanning 40 files...\n" + lines, 1))
    result = gate.run_shield_step(gate.REPO_SHARED, repo)
    assert len(result.detail.splitlines()) == gate._SHIELD_MAX_DETAIL


def test_safe_shield_step_turns_exception_into_red_row(monkeypatch):
    def boom(repo, repo_dir):
        raise RuntimeError("синтетический сбой")

    monkeypatch.setattr(gate, "run_shield_step", boom)
    result = gate._safe_shield_step(gate.REPO_CORE, gate.CORE_DIR)
    assert result.ok is False and "сбой шага" in result.detail


def test_gate_source_never_prints_or_stores_raw_shield_stdout():
    tree = _gate_tree()
    func = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run_shield_step"
    )
    uses = [
        n
        for n in ast.walk(func)
        if isinstance(n, ast.Attribute) and n.attr in ("stdout", "stderr")
    ]
    # stdout допустим только как вход parse_shield_findings и поиск строки «Scanning N files»
    sources = {ast.unparse(n) for n in uses}
    assert sources <= {"proc.stdout"}
    for node in ast.walk(func):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "CheckResult":
            assert "proc.stdout" not in ast.unparse(node)


# ============ Plan 01-05 Task 1: строки assistant-shared и проверка hook ============

HOOK_NAME = "pre-commit hook установлен"


def _git_repo(tmp_path, hooks_path=".githooks", hook_mode=0o755, hook_exists=True):
    """Временный git-репозиторий с настраиваемым core.hooksPath и файлом hook."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    if hooks_path is not None:
        subprocess.run(
            ["git", "-C", str(repo), "config", "core.hooksPath", hooks_path], check=True
        )
    if hook_exists:
        hook = repo / ".githooks" / "pre-commit"
        hook.parent.mkdir()
        hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        hook.chmod(hook_mode)
    return repo


def test_shared_pytest_env_clears_addopts_and_has_no_db_override():
    env = gate.shared_pytest_env()
    assert env == {"PYTEST_ADDOPTS": ""}
    assert "ASSISTANT_DB_PATH_OVERRIDE" not in env


def test_hook_installed_check_green_with_hookspath_and_executable_hook(tmp_path):
    result = gate.hook_installed_check("assistant-shared", _git_repo(tmp_path))
    assert result.ok is True
    assert result.repo == "assistant-shared"
    assert result.name == HOOK_NAME


def test_hook_installed_check_red_without_hookspath_mentions_installer(tmp_path):
    result = gate.hook_installed_check("assistant-core", _git_repo(tmp_path, hooks_path=None))
    assert result.ok is False
    assert result.name == HOOK_NAME
    assert "scripts/install_hooks.sh" in result.detail


def test_hook_installed_check_red_with_other_hookspath(tmp_path):
    result = gate.hook_installed_check("assistant-core", _git_repo(tmp_path, hooks_path="hooks"))
    assert result.ok is False
    assert "scripts/install_hooks.sh" in result.detail


def test_hook_installed_check_red_for_non_executable_hook(tmp_path):
    result = gate.hook_installed_check("assistant-core", _git_repo(tmp_path, hook_mode=0o644))
    assert result.ok is False
    assert "scripts/install_hooks.sh" in result.detail


def test_hook_installed_check_red_for_missing_hook_file(tmp_path):
    result = gate.hook_installed_check("assistant-core", _git_repo(tmp_path, hook_exists=False))
    assert result.ok is False
    assert "scripts/install_hooks.sh" in result.detail


def test_hook_installed_check_red_for_missing_directory(tmp_path):
    result = gate.hook_installed_check("assistant-shared", tmp_path / "нет")
    assert result.ok is False
    assert "scripts/install_hooks.sh" in result.detail or "нет каталога" in result.detail


def test_hook_installed_check_without_git_is_red_not_exception(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path)

    def boom(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(gate, "run_cmd", boom)
    result = gate.hook_installed_check("assistant-core", repo)
    assert result.ok is False and "scripts/install_hooks.sh" in result.detail


def test_hook_installed_check_timeout_is_red_not_exception(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path)

    def slow(cmd, *args, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 30)

    monkeypatch.setattr(gate, "run_cmd", slow)
    assert gate.hook_installed_check("assistant-core", repo).ok is False


def test_safe_hook_step_turns_exception_into_red_row(monkeypatch):
    def boom(repo, repo_dir):
        raise RuntimeError("синтетический сбой")

    monkeypatch.setattr(gate, "hook_installed_check", boom)
    result = gate._safe_hook_step(gate.REPO_SHARED, gate.SHARED_DIR)
    assert result.ok is False and "сбой шага" in result.detail
    assert result.repo == gate.REPO_SHARED and result.name == HOOK_NAME


EXPECTED_ROW_ORDER = [
    ("assistant-core", "pytest"),
    ("assistant-core", "боевая assistant.db не изменена"),
    ("assistant-core", "import-linter"),
    ("assistant-core", "security_shield (--all)"),
    ("assistant-core", "синтетическая персона (дрейф SHA-256)"),
    ("assistant-core", "токены персоны (дрейф SHA-256)"),
    ("assistant-core", HOOK_NAME),
    ("assistant-shared", "pytest"),
    ("assistant-shared", "security_shield (--all)"),
    ("assistant-shared", HOOK_NAME),
]


def _stub_all_steps(monkeypatch, calls=None):
    """Заглушки всех шагов: узнаваемые имена; под стражем БД реальный хеш из теста запрещён."""
    calls = calls if calls is not None else []
    monkeypatch.setattr(gate, "_sha_or_none", lambda path: "h")
    monkeypatch.setattr(gate, "db_integrity_snapshot", lambda path: dict(_SNAP))

    def pytest_step(repo, **kw):
        calls.append(("pytest", repo, kw))
        return CheckResult(repo, "pytest", True)

    def lint_step(repo, **kw):
        calls.append(("lint", repo, kw))
        return CheckResult(repo, "import-linter", True)

    def shield_step(repo, repo_dir):
        calls.append(("shield", repo, repo_dir))
        return CheckResult(repo, "security_shield (--all)", True)

    def hook_step(repo, repo_dir):
        calls.append(("hook", repo, repo_dir))
        return CheckResult(repo, HOOK_NAME, True)

    monkeypatch.setattr(gate, "_safe_pytest_step", pytest_step)
    monkeypatch.setattr(gate, "_safe_lint_step", lint_step)
    monkeypatch.setattr(gate, "_safe_shield_step", shield_step)
    monkeypatch.setattr(gate, "_safe_hook_step", hook_step)
    monkeypatch.setattr(
        gate, "persona_drift_check", lambda a, b, name: CheckResult("assistant-core", name, True)
    )
    return calls


def test_run_all_row_order(monkeypatch):
    _stub_all_steps(monkeypatch)
    results = gate._run_all(None)
    assert [(r.repo, r.name) for r in results] == EXPECTED_ROW_ORDER


def test_shared_rows_are_separate(monkeypatch):
    calls = _stub_all_steps(monkeypatch)
    results = gate._run_all(None)
    shared_names = [r.name for r in results if r.repo == gate.REPO_SHARED]
    assert shared_names == ["pytest", "security_shield (--all)", HOOK_NAME]
    assert len(set(shared_names)) == 3
    kinds = [c[0] for c in calls if c[1] == gate.REPO_SHARED]
    assert kinds == ["pytest", "shield", "hook"]


def test_shared_pytest_row_uses_core_venv_and_shared_cwd(monkeypatch):
    calls = _stub_all_steps(monkeypatch)
    gate._run_all(None)
    shared_pytest = next(c for c in calls if c[0] == "pytest" and c[1] == gate.REPO_SHARED)
    kw = shared_pytest[2]
    assert kw["pytest_bin"] == gate.CORE_VENV_BIN / "pytest"
    assert kw["cwd"] == gate.SHARED_DIR
    assert kw["target"] == "tests"
    assert kw["env_extra"] == {"PYTEST_ADDOPTS": ""}
    shield = next(c for c in calls if c[0] == "shield" and c[1] == gate.REPO_SHARED)
    assert shield[2] == gate.SHARED_DIR
    hooks = {c[1]: c[2] for c in calls if c[0] == "hook"}
    assert hooks == {gate.REPO_CORE: gate.CORE_DIR, gate.REPO_SHARED: gate.SHARED_DIR}


def test_run_all_never_aborts_on_step_exception(monkeypatch):
    """Исключение одного из run_*_step даёт красную строку «сбой шага», остальные 9 печатаются."""
    monkeypatch.setattr(gate, "_sha_or_none", lambda path: "h")
    monkeypatch.setattr(gate, "db_integrity_snapshot", lambda path: dict(_SNAP))
    monkeypatch.setattr(
        gate, "run_pytest_step", lambda repo, **kw: CheckResult(repo, "pytest", True)
    )

    def lint_boom(repo, **kw):
        raise RuntimeError("синтетический сбой import-linter")

    monkeypatch.setattr(gate, "run_lint_imports_step", lint_boom)
    monkeypatch.setattr(
        gate, "run_shield_step", lambda repo, d: CheckResult(repo, "security_shield (--all)", True)
    )
    monkeypatch.setattr(
        gate, "hook_installed_check", lambda repo, d: CheckResult(repo, HOOK_NAME, True)
    )
    monkeypatch.setattr(
        gate, "persona_drift_check", lambda a, b, name: CheckResult("assistant-core", name, True)
    )
    results = gate._run_all(None)
    assert len(results) == 10
    red = [r for r in results if not r.ok]
    assert len(red) == 1 and "сбой шага" in red[0].detail
    assert gate.overall_green(results) is False
    report = gate.render_report(results)
    assert report.splitlines()[-1] == "ИТОГ: КРАСНЫЙ"
    for repo, name in [row for row in EXPECTED_ROW_ORDER if row[1] != "pytest"]:
        assert name in report


# ============ Решение владельца 2026-10-09: один повтор при записи живого сервиса ============

import os  # noqa: E402
import time  # noqa: E402

WINDOW = (1000.0, 2000.0)
# Совместимые снимки целостности (WR-03): та же схема, строки не убыли.
_SNAP = {"schema": "s" * 64, "objects": {"t": "o" * 64}, "rows": {"t": 5}}
COMPAT = (_SNAP, {**_SNAP, "rows": {"t": 6}})


def _spy_remeasure(result):
    calls = []

    def fn():
        calls.append(1)
        return result

    return fn, calls


def test_db_retry_service_write_then_quiet_remeasure_match_is_green_with_explicit_note():
    remeasure, calls = _spy_remeasure(("c" * 64, "c" * 64))
    result = gate.db_unchanged_check(
        "a" * 64,
        "b" * 64,
        window=WINDOW,
        evidence_fn=lambda window: (True, "сервис assistant-worker: active; время изменения БД: T"),
        remeasure_fn=remeasure,
        snapshots=COMPAT,
    )
    assert result.ok is True
    assert len(calls) == 1
    assert "снимки целостности" in result.info
    assert "запись сервиса assistant-worker" in result.info
    assert "повторное измерение" in result.info
    assert "cccccccccccc" in result.info
    assert "SHA-256 до/после совпали" not in result.info  # честно: до/после НЕ совпали


def test_db_retry_quiet_remeasure_also_differs_is_red_with_guard_phrase():
    remeasure, calls = _spy_remeasure(("c" * 64, "d" * 64))
    result = gate.db_unchanged_check(
        "a",
        "b",
        diagnostics_fn=lambda: "ДИАГНОСТИКА",
        window=WINDOW,
        evidence_fn=lambda window: (True, "E"),
        remeasure_fn=remeasure,
        snapshots=COMPAT,
    )
    assert result.ok is False
    assert len(calls) == 1  # один повтор, не цикл
    assert "tests/live_db_guard.py" in result.detail
    assert "повторное измерение" in result.detail
    assert "ДИАГНОСТИКА" in result.detail


def test_db_retry_not_attempted_when_service_not_active_or_mtime_outside_window():
    remeasure, calls = _spy_remeasure(("c", "c"))
    result = gate.db_unchanged_check(
        "a",
        "b",
        window=WINDOW,
        evidence_fn=lambda window: (False, "сервис assistant-worker: inactive"),
        remeasure_fn=remeasure,
    )
    assert result.ok is False and calls == []
    assert "tests/live_db_guard.py" in result.detail


def test_db_retry_not_attempted_without_window():
    remeasure, calls = _spy_remeasure(("c", "c"))
    result = gate.db_unchanged_check(
        "a", "b", evidence_fn=lambda window: (True, "E"), remeasure_fn=remeasure
    )
    assert result.ok is False and calls == []


def test_db_retry_not_attempted_when_a_hash_is_none():
    remeasure, calls = _spy_remeasure(("c", "c"))
    for before, after in ((None, "b"), ("a", None), (None, None)):
        result = gate.db_unchanged_check(
            before,
            after,
            window=WINDOW,
            evidence_fn=lambda window: (True, "E"),
            remeasure_fn=remeasure,
        )
        assert result.ok is False
    assert calls == []


def test_db_retry_none_in_quiet_remeasure_is_red():
    for pair in ((None, "c"), ("c", None), (None, None)):
        remeasure, calls = _spy_remeasure(pair)
        result = gate.db_unchanged_check(
            "a",
            "b",
            window=WINDOW,
            evidence_fn=lambda window: (True, "E"),
            remeasure_fn=remeasure,
            snapshots=COMPAT,
        )
        assert result.ok is False and len(calls) == 1


def test_db_retry_crash_in_remeasure_or_evidence_is_red():
    def boom(*args):
        raise RuntimeError("сбой")

    r1 = gate.db_unchanged_check(
        "a",
        "b",
        window=WINDOW,
        evidence_fn=lambda window: (True, "E"),
        remeasure_fn=boom,
        snapshots=COMPAT,
    )
    r2 = gate.db_unchanged_check(
        "a", "b", window=WINDOW, evidence_fn=boom, remeasure_fn=lambda: ("c", "c"), snapshots=COMPAT
    )
    assert r1.ok is False and r2.ok is False


def test_db_unchanged_check_equal_hash_never_triggers_evidence_or_remeasure():
    remeasure, calls = _spy_remeasure(("c", "c"))

    def evidence(window):
        raise AssertionError("не должно вызываться")

    result = gate.db_unchanged_check(
        "a", "a", window=WINDOW, evidence_fn=evidence, remeasure_fn=remeasure
    )
    assert result.ok is True and calls == []


def test_db_unchanged_check_has_no_loop_so_retry_is_single():
    tree = _gate_tree()
    func = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "db_unchanged_check"
    )
    assert not [n for n in ast.walk(func) if isinstance(n, (ast.While, ast.For, ast.AsyncFor))]


def _fake_service(monkeypatch, state):
    monkeypatch.setattr(
        gate, "run_cmd", lambda *a, **k: subprocess.CompletedProcess(a, 0, state + "\n", "")
    )


def test_service_write_evidence_active_and_mtime_inside_window(tmp_path, monkeypatch):
    fake_db = tmp_path / "stand-in.db"
    fake_db.write_bytes(b"x")
    os.utime(fake_db, (1500.0, 1500.0))
    monkeypatch.setattr(gate, "LIVE_DB", fake_db)
    _fake_service(monkeypatch, "active")
    consistent, text = gate.service_write_evidence(WINDOW)
    assert consistent is True
    assert "active" in text and "UTC" in text


def test_service_write_evidence_mtime_outside_window_is_not_consistent(tmp_path, monkeypatch):
    fake_db = tmp_path / "stand-in.db"
    fake_db.write_bytes(b"x")
    monkeypatch.setattr(gate, "LIVE_DB", fake_db)
    _fake_service(monkeypatch, "active")
    for stamp in (999.0, 2001.0):
        os.utime(fake_db, (stamp, stamp))
        assert gate.service_write_evidence(WINDOW)[0] is False


def test_service_write_evidence_idle_service_is_not_consistent(tmp_path, monkeypatch):
    fake_db = tmp_path / "stand-in.db"
    fake_db.write_bytes(b"x")
    os.utime(fake_db, (1500.0, 1500.0))
    monkeypatch.setattr(gate, "LIVE_DB", fake_db)
    for state in ("inactive", "failed", "unknown", ""):
        _fake_service(monkeypatch, state)
        assert gate.service_write_evidence(WINDOW)[0] is False


def test_service_write_evidence_unknown_state_or_missing_db_is_not_consistent(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(gate, "LIVE_DB", tmp_path / "нет.db")
    _fake_service(monkeypatch, "active")
    assert gate.service_write_evidence(WINDOW)[0] is False

    def boom(*args, **kwargs):
        raise FileNotFoundError("systemctl")

    fake_db = tmp_path / "stand-in.db"
    fake_db.write_bytes(b"x")
    os.utime(fake_db, (1500.0, 1500.0))
    monkeypatch.setattr(gate, "LIVE_DB", fake_db)
    monkeypatch.setattr(gate, "run_cmd", boom)
    assert gate.service_write_evidence(WINDOW)[0] is False


def test_service_write_evidence_counts_wal_sidecar_mtime(tmp_path, monkeypatch):
    fake_db = tmp_path / "stand-in.db"
    fake_db.write_bytes(b"x")
    os.utime(fake_db, (10.0, 10.0))
    wal = tmp_path / "stand-in.db-wal"
    wal.write_bytes(b"w")
    os.utime(wal, (1500.0, 1500.0))
    monkeypatch.setattr(gate, "LIVE_DB", fake_db)
    _fake_service(monkeypatch, "active")
    assert gate.service_write_evidence(WINDOW)[0] is True


def test_service_write_evidence_is_read_only_systemctl(tmp_path, monkeypatch):
    calls = []
    fake_db = tmp_path / "stand-in.db"
    fake_db.write_bytes(b"x")
    monkeypatch.setattr(gate, "LIVE_DB", fake_db)

    def spy(cmd, *args, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "active", "")

    monkeypatch.setattr(gate, "run_cmd", spy)
    gate.service_write_evidence(WINDOW)
    assert calls and all(cmd[:2] == ["systemctl", "is-active"] for cmd in calls)


def test_quiet_remeasure_takes_hash_waits_constant_then_takes_hash_again(monkeypatch):
    events = []
    hashes = iter(["h1", "h2"])
    monkeypatch.setattr(gate, "_sha_or_none", lambda path: events.append("hash") or next(hashes))
    monkeypatch.setattr(gate.time, "sleep", lambda s: events.append(("sleep", s)))
    assert gate.quiet_remeasure() == ("h1", "h2")
    assert events == ["hash", ("sleep", gate.REMEASURE_WAIT_S), "hash"]
    assert isinstance(gate.REMEASURE_WAIT_S, (int, float)) and 0 < gate.REMEASURE_WAIT_S <= 30


def test_run_all_passes_measurement_window_to_db_check(monkeypatch):
    _stub_all_steps(monkeypatch)
    seen = {}

    def fake_check(before, after, **kw):
        seen.update(kw)
        return CheckResult("assistant-core", "боевая assistant.db не изменена", True)

    monkeypatch.setattr(gate, "db_unchanged_check", fake_check)
    t0 = time.time()
    gate._run_all(None)
    t1 = time.time()
    start, end = seen["window"]
    assert t0 <= start <= end <= t1


def test_run_all_service_write_is_remeasured_and_row_is_green_with_note(monkeypatch):
    _stub_all_steps(monkeypatch)
    hashes = iter(["before", "after"])
    monkeypatch.setattr(gate, "_sha_or_none", lambda path: next(hashes))
    snaps = iter(COMPAT)
    monkeypatch.setattr(gate, "db_integrity_snapshot", lambda path: next(snaps))
    monkeypatch.setattr(gate, "service_write_evidence", lambda window: (True, "сервис active"))
    monkeypatch.setattr(gate, "quiet_remeasure", lambda: ("quiet-hash-1", "quiet-hash-1"))
    results = gate._run_all(None)
    row = next(r for r in results if r.name == "боевая assistant.db не изменена")
    assert row.ok is True and "запись сервиса" in row.info
    assert gate.overall_green(results) is True


def test_run_all_write_with_idle_service_stays_red(monkeypatch):
    _stub_all_steps(monkeypatch)
    hashes = iter(["before", "after"])
    monkeypatch.setattr(gate, "_sha_or_none", lambda path: next(hashes))
    monkeypatch.setattr(gate, "service_write_evidence", lambda window: (False, "сервис inactive"))

    def must_not_run():
        raise AssertionError("повтор не должен запускаться")

    monkeypatch.setattr(gate, "quiet_remeasure", must_not_run)
    results = gate._run_all(None)
    row = next(r for r in results if r.name == "боевая assistant.db не изменена")
    assert row.ok is False
    assert gate.overall_green(results) is False


# ============ WR-03 (D-17): снимок целостности БД и условие смягчения ============


def _make_db(path, tables=None, fts=False):
    """Временная SQLite: таблицы {имя: число строк}; при fts - FTS5 с триггером-копией."""
    conn = sqlite3.connect(path)
    try:
        for name, count in (tables or {"items": 3}).items():
            conn.execute(f"CREATE TABLE {name} (id INTEGER PRIMARY KEY, v TEXT)")
            conn.executemany(f"INSERT INTO {name} (v) VALUES (?)", [("x",)] * count)
        if fts:
            conn.execute("CREATE VIRTUAL TABLE docs_fts USING fts5(body)")
            conn.executemany("INSERT INTO docs_fts (body) VALUES (?)", [("слово",)] * 4)
        conn.commit()
    finally:
        conn.close()
    return path


def test_integrity_snapshot_contains_schema_and_row_counts(tmp_path):
    snap = gate.db_integrity_snapshot(_make_db(tmp_path / "a.db", {"alpha": 2, "beta": 0}))
    assert snap["rows"] == {"alpha": 2, "beta": 0}
    assert len(snap["schema"]) == 64 and set(snap["objects"]) >= {"alpha", "beta"}


def test_integrity_snapshot_excludes_fts_virtual_and_shadow_tables(tmp_path):
    snap = gate.db_integrity_snapshot(_make_db(tmp_path / "a.db", {"items": 1}, fts=True))
    assert snap["rows"] == {"items": 1}


def test_integrity_snapshot_schema_changes_with_ddl_not_with_rows(tmp_path):
    db = _make_db(tmp_path / "a.db", {"items": 1})
    first = gate.db_integrity_snapshot(db)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO items (v) VALUES ('y')")
    conn.commit()
    same_schema = gate.db_integrity_snapshot(db)
    conn.execute("ALTER TABLE items ADD COLUMN extra TEXT")
    conn.commit()
    conn.close()
    changed = gate.db_integrity_snapshot(db)
    assert same_schema["schema"] == first["schema"] and same_schema["rows"] == {"items": 2}
    assert changed["schema"] != first["schema"]


def test_integrity_snapshot_unreadable_or_missing_file_gives_none(tmp_path):
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"not a database " * 100)
    assert gate.db_integrity_snapshot(junk) is None
    assert gate.db_integrity_snapshot(tmp_path / "нет.db") is None


def test_integrity_snapshot_opens_only_read_only_uri(tmp_path, monkeypatch):
    db = _make_db(tmp_path / "a.db")
    seen = []
    real_connect = sqlite3.connect

    def spy(target, *args, **kwargs):
        seen.append((target, kwargs))
        return real_connect(target, *args, **kwargs)

    monkeypatch.setattr(gate.sqlite3, "connect", spy)
    assert gate.db_integrity_snapshot(db) is not None
    assert len(seen) == 1
    target, kwargs = seen[0]
    assert target.startswith("file:") and target.endswith("?mode=ro") and kwargs.get("uri") is True


def _snap(schema="s", rows=None, objects=None):
    return {"schema": schema, "objects": objects or {}, "rows": rows or {"t": 5}}


def test_compare_integrity_growth_is_compatible():
    ok, text = gate.compare_integrity(_snap(rows={"t": 5}), _snap(rows={"t": 9, "new": 1}))
    assert ok is True and text


def test_compare_integrity_schema_change_is_incompatible_and_names_object_only():
    before = _snap("a", objects={"t": "1", "u": "2"})
    after = _snap("b", objects={"t": "1", "u": "3"})
    ok, text = gate.compare_integrity(before, after)
    assert ok is False and "u" in text and "схема" in text


def test_compare_integrity_shrink_outside_runtime_tables_is_incompatible():
    ok, text = gate.compare_integrity(
        _snap(rows={"email_messages": 10, "tasks": 4}), _snap(rows={"email_messages": 9, "tasks": 4})
    )
    assert ok is False and "email_messages" in text and "tasks" not in text


def test_compare_integrity_shrink_in_runtime_delete_table_is_compatible():
    assert "tasks" in gate.RUNTIME_DELETES_FROM
    ok, _ = gate.compare_integrity(_snap(rows={"tasks": 4}), _snap(rows={"tasks": 1}))
    assert ok is True


def test_compare_integrity_missing_table_counts_as_shrink_even_with_same_schema_digest():
    ok, text = gate.compare_integrity(_snap(rows={"memory_facts": 3}), _snap(rows={}))
    assert ok is False and "memory_facts" in text


def test_compare_integrity_none_snapshot_is_incompatible():
    assert gate.compare_integrity(None, _snap())[0] is False
    assert gate.compare_integrity(_snap(), None)[0] is False
    assert gate.compare_integrity(None, None)[0] is False
    assert gate.compare_integrity({"schema": "x"}, _snap())[0] is False


def test_runtime_deletes_from_matches_delete_statements_in_storage_layer():
    import re

    source = (Path(_GATE_PATH).parents[1] / "src" / "storage" / "db.py").read_text(encoding="utf-8")
    found = set(re.findall(r"DELETE FROM ([a-z_]+)\b", source))
    assert found <= gate.RUNTIME_DELETES_FROM, sorted(found - gate.RUNTIME_DELETES_FROM)


def _hash_pair_check(snapshots, **kw):
    remeasure, calls = _spy_remeasure(("c" * 64, "c" * 64))
    result = gate.db_unchanged_check(
        "a" * 64,
        "b" * 64,
        diagnostics_fn=lambda: "ДИАГНОСТИКА",
        window=WINDOW,
        evidence_fn=lambda window: (True, "сервис assistant-worker: active"),
        remeasure_fn=remeasure,
        snapshots=snapshots,
        **kw,
    )
    return result, calls


def test_db_unchanged_check_mitigation_with_compatible_snapshots_is_green():
    result, calls = _hash_pair_check(COMPAT)
    assert result.ok is True and len(calls) == 1
    assert "снимки целостности" in result.info


def test_db_unchanged_check_mitigation_with_changed_schema_is_red():
    after = {**_SNAP, "schema": "z" * 64, "objects": {"t": "q" * 64}}
    result, calls = _hash_pair_check((_SNAP, after))
    assert result.ok is False and calls == []
    assert "смягчение не применено" in result.detail and "ДИАГНОСТИКА" in result.detail
    assert "схема" in result.detail


def test_db_unchanged_check_mitigation_without_snapshots_is_red():
    result, calls = _hash_pair_check(None)
    assert result.ok is False and calls == []
    assert "смягчение не применено" in result.detail


def test_db_unchanged_check_mitigation_with_none_snapshot_is_red():
    for pair in ((None, _SNAP), (_SNAP, None), (None, None)):
        result, calls = _hash_pair_check(pair)
        assert result.ok is False and calls == []


def test_db_unchanged_check_mitigation_with_shrinking_rows_is_red_and_names_only_tables():
    after = {**_SNAP, "rows": {"t": 1}}
    result, calls = _hash_pair_check((_SNAP, after))
    assert result.ok is False and calls == []
    assert "число строк уменьшилось в таблицах: t" in result.detail


def test_db_unchanged_check_malformed_snapshots_are_red():
    result, calls = _hash_pair_check("не кортеж")
    assert result.ok is False and calls == []


def test_db_unchanged_check_equal_hashes_ignore_snapshots():
    assert gate.db_unchanged_check("h", "h", snapshots=None).ok is True


def test_run_all_passes_snapshots_from_before_and_after_to_db_check(monkeypatch):
    _stub_all_steps(monkeypatch)
    order = iter([{"schema": "before"}, {"schema": "after"}])
    monkeypatch.setattr(gate, "db_integrity_snapshot", lambda path: next(order))
    seen = {}

    def fake_check(before, after, **kw):
        seen.update(kw)
        return CheckResult("assistant-core", "боевая assistant.db не изменена", True)

    monkeypatch.setattr(gate, "db_unchanged_check", fake_check)
    results = gate._run_all(None)
    assert seen["snapshots"] == ({"schema": "before"}, {"schema": "after"})
    assert len(results) == 10


def test_run_all_source_passes_snapshots_keyword_to_db_unchanged_check():
    func = next(
        n for n in ast.walk(_gate_tree()) if isinstance(n, ast.FunctionDef) and n.name == "_run_all"
    )
    calls = [
        n
        for n in ast.walk(func)
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "db_unchanged_check"
    ]
    assert len(calls) == 1 and "snapshots" in {kw.arg for kw in calls[0].keywords}
