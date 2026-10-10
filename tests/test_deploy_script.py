"""Тесты scripts/deploy.py: read-only смоук работающего сервиса (OPS-01).

Скрипт загружается по пути (как gate): это CLI, а не пакет. Подпроцессы подменяет фейковый раннер,
журнал синтетический (условные имена логгеров, без данных профиля владельца). Боевая БД, systemd и
сеть не затрагиваются: реальные команды systemctl и journalctl в тестах не запускаются.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

DEPLOY_PATH = Path(__file__).resolve().parents[1] / "scripts" / "deploy.py"


def _load_deploy():
    spec = importlib.util.spec_from_file_location("deploy_under_test", DEPLOY_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["deploy_under_test"] = module
    spec.loader.exec_module(module)
    return module


deploy = _load_deploy()

INVOCATION = "0123456789abcdef0123456789abcdef"
BASE = datetime(2026, 10, 8, 9, 30, 48, tzinfo=timezone.utc)
NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)


def _ts(offset_s: float, style: str = "colon") -> str:
    moment = BASE + timedelta(seconds=offset_s)
    text = moment.strftime("%Y-%m-%dT%H:%M:%S")
    return text + ("+00:00" if style == "colon" else "+0000")


def _app(offset_s: float, level: str, logger: str, text: str, style: str = "colon") -> str:
    """Строка журнала: префикс journald и формат приложения (время приложения смешанное)."""
    app_time = (BASE + timedelta(seconds=offset_s, hours=3)).strftime("%Y-%m-%d %H:%M:%S") + ",123"
    return f"{_ts(offset_s, style)} host python3[4242]: {app_time} [{level}] {logger}: {text}"


def _raw(offset_s: float, text: str) -> str:
    """Строка без заголовка приложения (продолжение, тело traceback)."""
    return f"{_ts(offset_s)} host python3[4242]: {text}"


def _journal(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def _show(active: str = "active", sub: str = "running", invocation: str = INVOCATION) -> str:
    return (
        f"MainPID=4242\nNRestarts=0\nInvocationID={invocation}\n"
        f"ActiveState={active}\nSubState={sub}\n"
    )


SYNTHETIC_MAIN = """
async def main():
    scheduler.add_job(run_a_cycle, "interval", hours=1, id="a_job", replace_existing=True)
    scheduler.add_job(run_b_cycle, "cron", hour=8, id="b_job")
    if feature_enabled:
        scheduler.add_job(run_c_cycle, "cron", hour=9, id="c_job")
"""

BOT_TOKEN = "123456789" + ":" + "AAH" + "q" * 32


def _job_lines(offset_s: float = 10, functions=("run_a_cycle", "run_b_cycle")) -> list[str]:
    lines = [
        _app(offset_s, "INFO", "apscheduler.scheduler", f'Added job "{name}" to job store "default"')
        for name in functions
    ]
    lines.append(_app(offset_s + 1, "INFO", "apscheduler.scheduler", "Scheduler started"))
    return lines


GREEN_JOURNAL = _journal(
    _app(0, "INFO", "assistant-worker", "Assistant Worker starting up..."),
    _app(5, "WARNING", "src.collector.mail", "slow response"),
    *_job_lines(10),
    _app(30, "INFO", "aiogram.dispatcher", "Run polling for bot id=1 - 'name'"),
)


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


class FakeOpener:
    """Подмена urlopen: записывает URL и отдаёт ответ или бросает исключение."""

    def __init__(self, body: bytes = b'{"ok": true, "result": {}}', raises=None) -> None:
        self.body = body
        self.raises = raises
        self.urls: list[str] = []

    def __call__(self, url, timeout=15):
        self.urls.append(url)
        if self.raises is not None:
            raise self.raises
        return FakeResponse(self.body)


class FakeRunner:
    """Записывает вызовы и отдаёт заготовленные ответы по первому слову команды."""

    def __init__(
        self,
        show: str | None = None,
        journal: str = GREEN_JOURNAL,
        raises: Exception | None = None,
        rc: int = 0,
        stderr: str = "",
    ) -> None:
        self.show = _show() if show is None else show
        self.journal = journal
        self.raises = raises
        self.rc = rc
        self.stderr = stderr
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], timeout: int):
        self.calls.append(list(cmd))
        if self.raises is not None:
            raise self.raises
        if cmd[0] == "systemctl":
            out = self.show
        elif cmd[0] == "journalctl":
            out = self.journal
        else:
            out = ""
        return subprocess.CompletedProcess(cmd, self.rc, stdout=out, stderr=self.stderr)


def _run_main(
    tmp_path: Path,
    runner: FakeRunner,
    *extra: str,
    opener: FakeOpener | None = None,
    env_text: str | None = None,
) -> int:
    state = tmp_path / "state.json"
    env_path = tmp_path / ".env.test"
    env_path.write_text(
        f"TELEGRAM_BOT_TOKEN={BOT_TOKEN}\n" if env_text is None else env_text, encoding="utf-8"
    )
    main_py = tmp_path / "main_synthetic.py"
    main_py.write_text(SYNTHETIC_MAIN, encoding="utf-8")
    return deploy.main(
        ["--state-file", str(state), *extra],
        runner=runner,
        now=lambda: NOW,
        opener=opener or FakeOpener(),
        env_path=env_path,
        main_py_path=main_py,
    )


# ---------------------------------------------------------------- состояние сервиса


def test_get_service_state_parses_show_output():
    runner = FakeRunner()
    state = deploy.get_service_state(runner)
    assert state.active_state == "active"
    assert state.sub_state == "running"
    assert state.main_pid == 4242
    assert state.invocation_id == INVOCATION
    assert state.n_restarts == 0


def test_get_service_state_accepts_empty_invocation_id_of_stopped_unit():
    runner = FakeRunner(show=_show(active="inactive", sub="dead", invocation=""))
    state = deploy.get_service_state(runner)
    assert state.active_state == "inactive"
    assert state.invocation_id == ""


def test_get_service_state_uses_only_systemctl_show():
    runner = FakeRunner()
    deploy.get_service_state(runner)
    assert len(runner.calls) == 1
    assert runner.calls[0][:3] == ["systemctl", "show", "assistant-worker"]


# ---------------------------------------------------------------- разбор журнала


def test_parse_journal_app_line_fields():
    records = deploy.parse_journal(_journal(_app(0, "ERROR", "src.collector.mail", "boom")))
    assert len(records) == 1
    record = records[0]
    assert record.level == "ERROR"
    assert record.logger == "src.collector.mail"
    assert record.text == "boom"
    assert record.ts == BASE


def test_parse_journal_supports_numeric_offset_without_colon():
    records = deploy.parse_journal(_journal(_app(7, "INFO", "x.y", "ok", style="compact")))
    assert records[0].ts == BASE + timedelta(seconds=7)


def test_parse_journal_continuation_line_is_appended_to_previous_record():
    records = deploy.parse_journal(
        _journal(_app(0, "INFO", "x.y", "first"), _raw(0, "  second part"))
    )
    assert len(records) == 1
    assert "first" in records[0].text and "second part" in records[0].text


def test_parse_journal_traceback_creates_record_with_previous_logger():
    records = deploy.parse_journal(
        _journal(
            _app(0, "ERROR", "src.connectors.lms", "login failed"),
            _raw(0, "Traceback (most recent call last):"),
            _raw(0, '  File "x.py", line 1, in f'),
            _raw(0, "ValueError: bad value"),
            _app(1, "INFO", "x.y", "next"),
        )
    )
    assert [r.level for r in records] == ["ERROR", "TRACEBACK", "INFO"]
    assert records[1].logger == "src.connectors.lms"
    assert "ValueError: bad value" in records[1].text


def test_parse_journal_ignores_service_markers_and_blank_lines():
    text = "-- No entries --\n\n" + _app(0, "INFO", "x.y", "ok") + "\n"
    records = deploy.parse_journal(text)
    assert len(records) == 1


# ---------------------------------------------------------------- окно старта


def _window_records():
    return deploy.parse_journal(
        _journal(
            _app(0, "INFO", "assistant-worker", "start"),
            _app(10, "ERROR", "src.collector.mail", "initial cycle failed"),
            _app(40, "INFO", "aiogram.dispatcher", "Run polling for bot id=1 - 'n'"),
            _app(70, "ERROR", "src.collector.lms", "inside tail"),
            _app(101, "ERROR", "src.collector.late", "after tail"),
        )
    )


def test_startup_window_ends_at_polling_plus_tail():
    window, polling = deploy.startup_window(_window_records(), tail_seconds=60)
    assert polling == BASE + timedelta(seconds=40)
    loggers = [r.logger for r in window]
    assert "src.collector.lms" in loggers
    assert "src.collector.late" not in loggers
    assert loggers[0] == "assistant-worker"


def test_startup_window_without_polling_covers_all_records():
    records = deploy.parse_journal(_journal(_app(0, "INFO", "a", "x"), _app(500, "ERROR", "b", "y")))
    window, polling = deploy.startup_window(records)
    assert polling is None
    assert len(window) == 2


def test_startup_tail_constant_is_sixty_seconds():
    assert deploy.STARTUP_TAIL_SECONDS == 60


def test_scan_window_splits_errors_and_warnings():
    records = deploy.parse_journal(
        _journal(
            _app(0, "WARNING", "src.a", "slow"),
            _app(1, "ERROR", "src.b", "failed"),
            _app(2, "CRITICAL", "src.c", "dead"),
            _app(3, "INFO", "src.d", "fine"),
        )
    )
    errors, warnings = deploy.scan_window(records)
    assert [(f.level, f.logger) for f in errors] == [("ERROR", "src.b"), ("CRITICAL", "src.c")]
    assert [(f.level, f.logger) for f in warnings] == [("WARNING", "src.a")]


def test_scan_window_traceback_counts_as_error_with_exception_line():
    records = deploy.parse_journal(
        _journal(
            _app(0, "INFO", "src.x", "begin"),
            _raw(0, "Traceback (most recent call last):"),
            _raw(0, "KeyError: 'missing'"),
        )
    )
    errors, _ = deploy.scan_window(records)
    assert len(errors) == 1
    assert errors[0].level == "TRACEBACK"
    assert errors[0].logger == "src.x"
    assert "KeyError" in errors[0].message


def test_scan_window_message_is_redacted_and_truncated():
    mail = "owner" + "@" + "example.org"
    records = deploy.parse_journal(
        _journal(_app(0, "ERROR", "src.mail", f"login {mail} failed " + "z" * 400))
    )
    errors, _ = deploy.scan_window(records)
    assert mail not in errors[0].message
    assert len(errors[0].message) <= deploy.MESSAGE_LIMIT


# ---------------------------------------------------------------- redact


def test_redact_removes_email():
    mail = "someone" + "@" + "example.org"
    assert mail not in deploy.redact(f"user {mail} here")


def test_redact_removes_bot_token_by_format():
    token = "123456789" + ":" + "AAH" + "x" * 32
    assert token not in deploy.redact(f"token {token} leaked")


def test_redact_removes_bot_token_inside_url():
    token = "123456789" + ":" + "short_secret"
    url = f"https://api.telegram.org/bot{token}/getMe"
    cleaned = deploy.redact(f"HTTPSConnectionPool: {url}")
    assert token not in cleaned
    assert "short_secret" not in cleaned


def test_redact_removes_secret_query_parameters():
    text = "GET /x?token=abcdef&key=hello&Secret=s3&password=p&auth=a&page=2"
    cleaned = deploy.redact(text)
    for leaked in ("abcdef", "hello", "s3", "=p&", "=a&"):
        assert leaked not in cleaned
    assert "page=2" in cleaned


def test_redact_removes_long_hex_and_base64_like_sequences():
    hex_value = "ab12" * 10
    b64_value = "Zm9vYmFy" * 5
    cleaned = deploy.redact(f"h={hex_value} b={b64_value}")
    assert hex_value not in cleaned
    assert b64_value not in cleaned


def test_redact_keeps_short_words_and_paths():
    assert deploy.redact("path /opt/assistant-core/src/main.py ok") == (
        "path /opt/assistant-core/src/main.py ok"
    )


def test_redact_truncates_with_ellipsis_after_cleaning():
    cleaned = deploy.redact("слово " * 100, limit=50)
    assert len(cleaned) == 50
    assert cleaned.endswith("…")


def test_redact_collapses_whitespace_and_newlines():
    assert deploy.redact("a\n  b\t c") == "a b c"


# ---------------------------------------------------------------- проверки


def test_check_service_active_green_and_red():
    ok = deploy.check_service_active(deploy.ServiceState("active", "running", 1, INVOCATION, 0))
    bad = deploy.check_service_active(deploy.ServiceState("failed", "failed", 0, "", 3))
    assert ok.ok and ok.name == "сервис active"
    assert not bad.ok and "failed" in bad.detail


def test_check_journal_available_red_on_empty_with_rotation_hint():
    assert deploy.check_journal_available([deploy.parse_journal(GREEN_JOURNAL)[0]]).ok
    empty = deploy.check_journal_available([])
    assert not empty.ok and "ротация" in empty.detail


def test_check_startup_errors_lists_ten_and_counts_rest():
    findings = [deploy.Finding("ERROR", f"src.l{i}", f"m{i}") for i in range(13)]
    result = deploy.check_startup_errors(findings)
    assert not result.ok
    assert result.detail.count("src.l") == 10
    assert "3" in result.detail.splitlines()[-1]
    assert deploy.check_startup_errors([]).ok


def test_check_polling_started():
    assert deploy.check_polling_started(BASE).ok
    missing = deploy.check_polling_started(None)
    assert not missing.ok and "ротация" in missing.detail


def test_render_table_green_has_summary_and_warning_line():
    rows = [deploy.CheckResult("сервис active", True), deploy.CheckResult("второй", True, "деталь")]
    warnings = [
        deploy.Finding("WARNING", "src.a", "x"),
        deploy.Finding("WARNING", "src.a", "y"),
        deploy.Finding("WARNING", "src.b", "z"),
    ]
    text = deploy.render_table(rows, warnings)
    assert "Проверка" in text and "Результат" in text
    assert "↳ деталь" in text
    assert "WARNING в окне старта: 3" in text and "src.a×2" in text and "src.b×1" in text
    assert text.rstrip().endswith("АВТОМАТИЧЕСКАЯ ЧАСТЬ: ЗЕЛЁНАЯ")


def test_render_table_red_when_any_row_failed():
    rows = [deploy.CheckResult("a", True), deploy.CheckResult("b", False, "причина")]
    assert deploy.render_table(rows).rstrip().endswith("АВТОМАТИЧЕСКАЯ ЧАСТЬ: КРАСНАЯ")


# ---------------------------------------------------------------- main: сквозной путь


def test_main_green_returns_zero_and_prints_verdict(tmp_path, capsys):
    rc = _run_main(tmp_path, FakeRunner())
    out = capsys.readouterr().out
    assert rc == 0
    assert "АВТОМАТИЧЕСКАЯ ЧАСТЬ: ЗЕЛЁНАЯ" in out
    assert "WARNING в окне старта: 1" in out


def test_main_error_in_startup_window_is_red_without_allowlist(tmp_path, capsys):
    journal = _journal(
        _app(0, "INFO", "assistant-worker", "start"),
        _app(5, "ERROR", "src.collector.mail", "IMAP timed out"),
        *_job_lines(10),
        _app(30, "INFO", "aiogram.dispatcher", "Run polling for bot id=1 - 'n'"),
    )
    rc = _run_main(tmp_path, FakeRunner(journal=journal))
    out = capsys.readouterr().out
    assert rc == 1
    assert "src.collector.mail: IMAP timed out" in out
    assert "АВТОМАТИЧЕСКАЯ ЧАСТЬ: КРАСНАЯ" in out


def test_main_error_after_tail_does_not_redden(tmp_path):
    journal = _journal(
        _app(0, "INFO", "assistant-worker", "start"),
        *_job_lines(10),
        _app(30, "INFO", "aiogram.dispatcher", "Run polling for bot id=1 - 'n'"),
        _app(500, "ERROR", "src.collector.mail", "late failure"),
    )
    assert _run_main(tmp_path, FakeRunner(journal=journal)) == 0


def test_main_stopped_service_is_red_and_journal_not_read(tmp_path, capsys):
    runner = FakeRunner(show=_show(active="inactive", sub="dead", invocation=""))
    rc = _run_main(tmp_path, runner)
    assert rc == 1
    assert all(call[0] != "journalctl" for call in runner.calls)
    assert "АВТОМАТИЧЕСКАЯ ЧАСТЬ: КРАСНАЯ" in capsys.readouterr().out


def test_main_journal_filter_is_by_invocation_id(tmp_path):
    runner = FakeRunner()
    _run_main(tmp_path, runner)
    journal_calls = [c for c in runner.calls if c[0] == "journalctl"]
    assert len(journal_calls) == 1
    assert f"_SYSTEMD_INVOCATION_ID={INVOCATION}" in journal_calls[0]
    assert "--no-pager" in journal_calls[0]


def test_main_runner_sees_only_read_only_commands(tmp_path):
    runner = FakeRunner()
    _run_main(tmp_path, runner)
    forbidden = {
        "restart", "stop", "start", "kill", "reload", "enable", "disable", "daemon-reload",
        "try-restart", "reload-or-restart", "mask", "unmask",
    }
    assert runner.calls
    for call in runner.calls:
        assert call[0] in {"systemctl", "journalctl"}
        if call[0] == "systemctl":
            assert call[1] == "show"
        assert not (forbidden & set(call))


def test_main_missing_binary_gives_red_row_not_traceback(tmp_path, capsys):
    rc = _run_main(tmp_path, FakeRunner(raises=FileNotFoundError("systemctl")))
    out = capsys.readouterr().out
    assert rc == 1
    assert "не найдена" in out
    assert "Traceback (most recent" not in out


def test_main_timeout_gives_red_row(tmp_path, capsys):
    rc = _run_main(tmp_path, FakeRunner(raises=subprocess.TimeoutExpired("systemctl", 30)))
    assert rc == 1
    assert "таймаут" in capsys.readouterr().out


def test_main_nonzero_return_code_gives_red_row(tmp_path, capsys):
    rc = _run_main(tmp_path, FakeRunner(rc=3, stderr="Failed to connect to bus"))
    out = capsys.readouterr().out
    assert rc == 1
    assert "код возврата 3" in out


def test_main_usage_error_returns_two(tmp_path):
    assert deploy.main(["--no-such-flag"], runner=FakeRunner(), now=lambda: NOW) == 2


def test_main_saves_state_file_outside_repo_with_owner_only_mode(tmp_path):
    runner = FakeRunner()
    state = tmp_path / "state.json"
    _run_main(tmp_path, runner)
    assert state.exists()
    assert (state.stat().st_mode & 0o777) == 0o600
    data = state.read_text(encoding="utf-8")
    assert INVOCATION in data
    assert "Run polling" not in data  # сырые строки журнала в состояние не попадают


# ---------------------------------------------------------------- защита от изменяющих команд


def test_ensure_read_only_rejects_state_changing_commands():
    for cmd in (
        ["systemctl", "restart", "assistant-worker"],
        ["systemctl", "stop", "assistant-worker"],
        ["systemctl", "daemon-reload"],
        ["rm", "-rf", "/"],
        ["journalctl", "--rotate"],
    ):
        with pytest.raises(ValueError):
            deploy.ensure_read_only(cmd)


def test_ensure_read_only_allows_show_and_journal_reads():
    deploy.ensure_read_only(["systemctl", "show", "assistant-worker", "-p", "ActiveState"])
    deploy.ensure_read_only(["journalctl", "-u", "assistant-worker", "--no-pager", "-o", "short-iso"])


def test_read_invocation_journal_rejects_malformed_invocation_id():
    with pytest.raises(ValueError):
        deploy.read_invocation_journal(FakeRunner(), "--vacuum-size=1M")


# ---------------------------------------------------------------- статические свойства файла


def _code_lines() -> list[str]:
    return [
        line
        for line in DEPLOY_PATH.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]


def test_script_does_not_import_src_and_opens_sqlite_only_in_make_db_copy():
    """Скрипт не импортирует src; соединения SQLite открывает только make_db_copy (по --backup, D-11)."""
    source = "\n".join(_code_lines())
    assert not re.search(r"^\s*(from|import)\s+src\b", source, re.MULTILINE)
    assert "aiosqlite" not in source
    tree = ast.parse(DEPLOY_PATH.read_text(encoding="utf-8"))
    owners: set[str] = set()
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(func):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "connect"
                and isinstance(node.value, ast.Name)
                and node.value.id == "sqlite3"
            ):
                owners.add(func.name)
    assert owners == {"make_db_copy"}
    assert 1 <= source.count("sqlite3.connect") <= 2


def test_script_is_executable_python3_with_shebang():
    first = DEPLOY_PATH.read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith("#!") and "python3" in first


# ================================================================ Task 2: планировщик и getMe

import urllib.error  # noqa: E402

REAL_MAIN_PY = Path(__file__).resolve().parents[1] / "src" / "main.py"

KNOWN_JOBS = {
    ("run_sentinel_cycle", "schedule_sentinel_job"),
    ("run_telegram_collector_cycle", "telegram_collector_job"),
    ("run_email_collector_cycle", "email_collector_job"),
    ("run_lms_monitor_cycle", "lms_monitor_job"),
    ("run_morning_brief_cycle", "morning_brief_job"),
    ("run_evening_digest_cycle", "evening_digest_job"),
    ("run_aadhk_gdrive_sync_cycle", "aadhk_gdrive_sync_job"),
    ("run_nightly_reset_and_priming_cycle", "nightly_reset_and_priming_job"),
    ("run_weekly_memory_review_cycle", "weekly_memory_review_job"),
    ("run_live_ticker_refresh_cycle", "live_ticker_refresh_job"),
}


def test_expected_jobs_on_real_main_contains_ten_known_pairs():
    jobs = deploy.expected_jobs(REAL_MAIN_PY.read_text(encoding="utf-8"))
    pairs = {(job.func, job.job_id) for job in jobs}
    assert KNOWN_JOBS <= pairs


def test_expected_jobs_marks_conditional_calls_under_if():
    jobs = {job.job_id: job for job in deploy.expected_jobs(SYNTHETIC_MAIN)}
    assert jobs["a_job"].conditional is False
    assert jobs["b_job"].conditional is False
    assert jobs["c_job"].conditional is True
    assert jobs["c_job"].func == "run_c_cycle"


def test_expected_jobs_ignores_calls_without_function_name_argument():
    source = (
        "scheduler.add_job('text', id='x')\n"
        "scheduler.add_job(obj.method, id='y')\n"
        "scheduler.add_job(real_fn, id='z')\n"
        "other.run(real_fn, id='w')\n"
    )
    assert [(j.func, j.job_id) for j in deploy.expected_jobs(source)] == [("real_fn", "z")]


def test_load_expected_jobs_reads_file(tmp_path):
    path = tmp_path / "m.py"
    path.write_text(SYNTHETIC_MAIN, encoding="utf-8")
    assert {j.job_id for j in deploy.load_expected_jobs(path)} == {"a_job", "b_job", "c_job"}


def test_parse_added_jobs_extracts_function_names_and_started_flag():
    records = deploy.parse_journal(_journal(*_job_lines(0, ("run_a_cycle", "run_b_cycle"))))
    added, started = deploy.parse_added_jobs(records)
    assert added == {"run_a_cycle", "run_b_cycle"}
    assert started is True


def test_parse_added_jobs_ignores_other_loggers_and_missing_start():
    records = deploy.parse_journal(
        _journal(
            _app(0, "INFO", "src.other", 'Added job "run_a_cycle" to job store "default"'),
            _app(1, "INFO", "src.other", "Scheduler started"),
        )
    )
    assert deploy.parse_added_jobs(records) == (set(), False)


def _expected():
    return deploy.expected_jobs(SYNTHETIC_MAIN)


def test_check_scheduler_jobs_green_when_all_unconditional_registered():
    result = deploy.check_scheduler_jobs(_expected(), {"run_a_cycle", "run_b_cycle"}, True)
    assert result.ok
    assert "2 из 2" in result.name
    assert "условная" in result.detail and "c_job" in result.detail


def test_check_scheduler_jobs_conditional_job_does_not_redden():
    result = deploy.check_scheduler_jobs(
        _expected(), {"run_a_cycle", "run_b_cycle", "run_c_cycle"}, True
    )
    assert result.ok


def test_check_scheduler_jobs_red_lists_missing_ids_with_rotation_hint():
    result = deploy.check_scheduler_jobs(_expected(), {"run_a_cycle"}, True)
    assert not result.ok
    assert "b_job" in result.detail and "a_job" not in result.detail.split("не зарегистрированы")[-1]
    assert "ротация" in result.detail
    assert "1 из 2" in result.name


def test_check_scheduler_jobs_red_when_scheduler_not_started():
    result = deploy.check_scheduler_jobs(_expected(), {"run_a_cycle", "run_b_cycle"}, False)
    assert not result.ok
    assert "Scheduler started" in result.detail


def test_check_scheduler_jobs_red_when_nothing_expected():
    assert not deploy.check_scheduler_jobs([], set(), True).ok


def test_read_env_key_handles_quotes_comments_and_export(tmp_path):
    env = tmp_path / "e"
    env.write_text(
        "# comment\n\nOTHER=1\nexport TELEGRAM_BOT_TOKEN='quoted-value'  \nTAIL=2\n",
        encoding="utf-8",
    )
    assert deploy.read_env_key(env, "TELEGRAM_BOT_TOKEN") == "quoted-value"
    env.write_text('TELEGRAM_BOT_TOKEN="dq-value"\n', encoding="utf-8")
    assert deploy.read_env_key(env, "TELEGRAM_BOT_TOKEN") == "dq-value"
    env.write_text("TELEGRAM_BOT_TOKEN=plain # trailing comment\n", encoding="utf-8")
    assert deploy.read_env_key(env, "TELEGRAM_BOT_TOKEN") == "plain"


def test_read_env_key_missing_key_or_file_gives_none(tmp_path):
    env = tmp_path / "e"
    env.write_text("OTHER=1\n#TELEGRAM_BOT_TOKEN=commented\n", encoding="utf-8")
    assert deploy.read_env_key(env, "TELEGRAM_BOT_TOKEN") is None
    assert deploy.read_env_key(tmp_path / "absent", "TELEGRAM_BOT_TOKEN") is None


def test_read_env_key_empty_value_gives_none(tmp_path):
    env = tmp_path / "e"
    env.write_text("TELEGRAM_BOT_TOKEN=\n", encoding="utf-8")
    assert deploy.read_env_key(env, "TELEGRAM_BOT_TOKEN") is None


def test_telegram_get_me_ok_true():
    opener = FakeOpener()
    ok, detail = deploy.telegram_get_me(BOT_TOKEN, opener)
    assert ok is True and detail == "getMe: токен жив"
    assert opener.urls == [f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"]


def test_telegram_get_me_ok_false_in_json():
    ok, detail = deploy.telegram_get_me(BOT_TOKEN, FakeOpener(body=b'{"ok": false}'))
    assert ok is False and BOT_TOKEN not in detail


def test_telegram_get_me_http_error_reports_code_only():
    err = urllib.error.HTTPError(f"https://x/bot{BOT_TOKEN}/getMe", 401, "Unauthorized", {}, None)
    ok, detail = deploy.telegram_get_me(BOT_TOKEN, FakeOpener(raises=err))
    assert (ok, detail) == (False, "getMe: HTTP 401")


def test_telegram_get_me_other_exception_reports_class_only_without_token():
    boom = RuntimeError(f"failed https://api.telegram.org/bot{BOT_TOKEN}/getMe")
    ok, detail = deploy.telegram_get_me(BOT_TOKEN, FakeOpener(raises=boom))
    assert (ok, detail) == (False, "getMe: RuntimeError")
    assert BOT_TOKEN not in detail


def test_telegram_get_me_invalid_json_reports_class_only():
    ok, detail = deploy.telegram_get_me(BOT_TOKEN, FakeOpener(body=b"not json"))
    assert ok is False and BOT_TOKEN not in detail


def test_check_get_me_missing_token_names_key_without_value(tmp_path):
    env = tmp_path / "e"
    env.write_text("OTHER=1\n", encoding="utf-8")
    result = deploy.check_get_me(env, FakeOpener())
    assert not result.ok
    assert result.name == "getMe: токен бота жив"
    assert "TELEGRAM_BOT_TOKEN" in result.detail


def test_check_get_me_never_leaks_token_through_exception(tmp_path):
    env = tmp_path / "e"
    env.write_text(f"TELEGRAM_BOT_TOKEN={BOT_TOKEN}\n", encoding="utf-8")
    boom = urllib.error.URLError(f"cannot reach bot{BOT_TOKEN}")
    result = deploy.check_get_me(env, FakeOpener(raises=boom))
    assert not result.ok
    assert BOT_TOKEN not in result.name + result.detail
    assert BOT_TOKEN.split(":")[0] not in result.detail


def test_main_prints_scheduler_and_get_me_rows_in_order(tmp_path, capsys):
    rc = _run_main(tmp_path, FakeRunner())
    out = capsys.readouterr().out
    assert rc == 0
    names = [
        "сервис active",
        "журнал текущего запуска доступен",
        "в окне старта нет ERROR/CRITICAL/Traceback",
        "polling бота запущен (запись в журнале)",
        "планировщик: задачи зарегистрированы (2 из 2)",
        "getMe: токен бота жив",
    ]
    positions = [out.index(name) for name in names]
    assert positions == sorted(positions)


def test_main_red_when_job_missing_in_journal(tmp_path, capsys):
    journal = _journal(
        _app(0, "INFO", "assistant-worker", "start"),
        *_job_lines(10, ("run_a_cycle",)),
        _app(30, "INFO", "aiogram.dispatcher", "Run polling for bot id=1 - 'n'"),
    )
    rc = _run_main(tmp_path, FakeRunner(journal=journal))
    out = capsys.readouterr().out
    assert rc == 1
    assert "b_job" in out


def test_main_get_me_failure_is_red_and_token_never_printed(tmp_path, capsys):
    opener = FakeOpener(raises=RuntimeError(f"bad bot{BOT_TOKEN}"))
    rc = _run_main(tmp_path, FakeRunner(), opener=opener)
    captured = capsys.readouterr()
    assert rc == 1
    assert "getMe: RuntimeError" in captured.out
    assert BOT_TOKEN not in captured.out + captured.err
    assert BOT_TOKEN not in (tmp_path / "state.json").read_text(encoding="utf-8")


def test_main_missing_token_is_red(tmp_path, capsys):
    rc = _run_main(tmp_path, FakeRunner(), env_text="OTHER=1\n")
    assert rc == 1
    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().out


def test_main_unreadable_main_py_gives_red_row(tmp_path, capsys):
    state = tmp_path / "s.json"
    rc = deploy.main(
        ["--state-file", str(state)],
        runner=FakeRunner(),
        now=lambda: NOW,
        opener=FakeOpener(),
        env_path=tmp_path / "absent.env",
        main_py_path=tmp_path / "no_such_main.py",
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert "планировщик" in out and "Traceback (most recent" not in out


def test_main_does_not_call_network_when_service_is_down(tmp_path):
    opener = FakeOpener()
    runner = FakeRunner(show=_show(active="inactive", sub="dead", invocation=""))
    assert _run_main(tmp_path, runner, opener=opener) == 1
    assert opener.urls == []


def test_script_has_no_get_updates_or_user_session_access():
    source = DEPLOY_PATH.read_text(encoding="utf-8")
    assert "getUpdates" not in source
    code = "\n".join(_code_lines()).lower()
    assert "telethon" not in code and ".session" not in code


def test_read_env_key_is_called_only_with_bot_token_key():
    code = "\n".join(line for line in _code_lines() if not line.lstrip().startswith("def "))
    keys = re.findall(r"read_env_key\([^,()]+,\s*([^)]+)\)", code)
    assert keys and all(key.strip() in {"BOT_TOKEN_KEY", '"TELEGRAM_BOT_TOKEN"'} for key in keys)
    assert deploy.BOT_TOKEN_KEY == "TELEGRAM_BOT_TOKEN"


# ================================================================ Task 3: фазы без TTY и отчёт

import ast  # noqa: E402
import json  # noqa: E402

BOT_HANDLER_PATH = Path(__file__).resolve().parents[1] / "src" / "notifier" / "bot_handler.py"
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
BOT_TOKEN_RE = re.compile(r"\d{6,}:[A-Za-z0-9_-]{20,}")


def _line_at(moment: datetime, level: str, logger: str, text: str) -> str:
    """Строка журнала с явным временем (для обновлений после метки смоука)."""
    stamp = moment.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    app_time = moment.strftime("%Y-%m-%d %H:%M:%S") + ",001"
    return f"{stamp} host python3[4242]: {app_time} [{level}] {logger}: {text}"


def _handled(moment: datetime, update_id: int = 7) -> str:
    return _line_at(
        moment, "INFO", "aiogram.event", f"Update id={update_id} is handled. Duration 182 ms by bot id=1"
    )


class Clock:
    """Часы и sleep для ожидания без реальных пауз."""

    def __init__(self, start: datetime = NOW) -> None:
        self.current = start
        self.slept: list[float] = []

    def now(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.current += timedelta(seconds=seconds)


class SeqRunner(FakeRunner):
    """Журнал меняется от вызова к вызову: последний элемент повторяется."""

    def __init__(self, journals: list[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self.journals = list(journals)
        self.journal_calls = 0

    def __call__(self, cmd, timeout):
        if cmd[0] == "journalctl":
            index = min(self.journal_calls, len(self.journals) - 1)
            self.journal_calls += 1
            self.journal = self.journals[index]
        if cmd[0] == "git":
            self.calls.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, stdout="a" * 40 + "\n", stderr="")
        return super().__call__(cmd, timeout)


def _handled_journal(offset_s: float = 5) -> str:
    return GREEN_JOURNAL + _journal(_handled(NOW + timedelta(seconds=offset_s)))


def _make_state(tmp_path: Path) -> Path:
    assert _run_main(tmp_path, FakeRunner()) == 0
    return tmp_path / "state.json"


def _phase(tmp_path: Path, runner, *flags: str, clock: Clock | None = None) -> int:
    clock = clock or Clock()
    return deploy.main(
        ["--state-file", str(tmp_path / "state.json"), *flags],
        runner=runner,
        now=clock.now,
        sleep=clock.sleep,
    )


def _state(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- счёт обновлений


def test_count_handled_updates_counts_only_handled_after_marker():
    marker = NOW
    records = deploy.parse_journal(
        _journal(
            _handled(NOW - timedelta(seconds=30), 1),
            _handled(NOW + timedelta(seconds=1), 2),
            _line_at(NOW + timedelta(seconds=2), "INFO", "aiogram.event", "Update id=3 is not handled."),
            _line_at(NOW + timedelta(seconds=3), "INFO", "other.logger", "Update id=4 is handled."),
            _handled(NOW, 5),
        )
    )
    assert deploy.count_handled_updates(records, marker) == 2


# ---------------------------------------------------------------- ожидание /help


def _state_dict(**over) -> dict:
    data = {
        "created_utc": NOW.isoformat(),
        "invocation_id": INVOCATION,
        "checks": [{"name": "сервис active", "ok": True, "detail": ""}],
        "errors": [],
        "warnings": {},
        "help_marker_utc": NOW.isoformat(timespec="seconds"),
        "help_handled": None,
        "owner_confirmed": None,
    }
    data.update(over)
    return data


def test_await_help_returns_true_when_update_appears_later():
    clock = Clock()
    runner = SeqRunner([GREEN_JOURNAL, GREEN_JOURNAL, _handled_journal()])
    handled = deploy.await_help(_state_dict(), runner, clock.sleep, clock.now, timeout=120)
    assert handled is True
    assert clock.slept == [5, 5]


def test_await_help_times_out_without_real_waiting():
    clock = Clock()
    runner = SeqRunner([GREEN_JOURNAL])
    handled = deploy.await_help(_state_dict(), runner, clock.sleep, clock.now, timeout=30)
    assert handled is False
    assert sum(clock.slept) >= 30
    assert all(step == 5 for step in clock.slept)


def test_await_help_journal_query_filters_by_invocation_and_marker():
    clock = Clock()
    runner = SeqRunner([_handled_journal()])
    deploy.await_help(_state_dict(), runner, clock.sleep, clock.now, timeout=10)
    call = next(c for c in runner.calls if c[0] == "journalctl")
    assert f"_SYSTEMD_INVOCATION_ID={INVOCATION}" in call
    assert "--since" in call
    assert call[call.index("--since") + 1] == "2026-10-09 12:00:00 UTC"


# ---------------------------------------------------------------- вердикт


@pytest.mark.parametrize(
    "over, expected",
    [
        ({"help_handled": True, "owner_confirmed": True}, "ЗЕЛЁНЫЙ"),
        ({"help_handled": True, "owner_confirmed": False}, "КРАСНЫЙ"),
        ({"help_handled": False, "owner_confirmed": True}, "КРАСНЫЙ"),
        ({"help_handled": False}, "КРАСНЫЙ"),
        ({"help_handled": True, "owner_confirmed": None}, "ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ"),
        ({}, "ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ"),
        (
            {"checks": [{"name": "x", "ok": False, "detail": ""}], "help_handled": True,
             "owner_confirmed": True},
            "КРАСНЫЙ",
        ),
        ({"checks": [], "help_handled": True, "owner_confirmed": True}, "КРАСНЫЙ"),
    ],
)
def test_final_verdict_rules(over, expected):
    assert deploy.final_verdict(_state_dict(**over)) == expected


def test_verdict_reasons_explain_yes_without_handled_update():
    reasons = deploy.verdict_reasons(_state_dict(help_handled=False, owner_confirmed=True))
    assert any("журнал" in reason for reason in reasons)


# ---------------------------------------------------------------- confirm_help


def test_confirm_help_checks_journal_once_without_waiting():
    runner = SeqRunner([_handled_journal()])
    state = deploy.confirm_help(_state_dict(), "yes", runner)
    assert state["owner_confirmed"] is True
    assert state["help_handled"] is True
    assert runner.journal_calls == 1


def test_confirm_help_yes_without_update_is_recorded_as_not_handled():
    runner = SeqRunner([GREEN_JOURNAL])
    state = deploy.confirm_help(_state_dict(), "yes", runner)
    assert state["help_handled"] is False
    assert deploy.final_verdict(state) == "КРАСНЫЙ"


def test_confirm_help_keeps_known_handled_flag_without_journal_query():
    runner = SeqRunner([GREEN_JOURNAL])
    state = deploy.confirm_help(_state_dict(help_handled=True), "no", runner)
    assert runner.journal_calls == 0
    assert state["owner_confirmed"] is False


# ---------------------------------------------------------------- main: обычный запуск


def test_main_green_prints_three_step_instruction(tmp_path, capsys):
    assert _run_main(tmp_path, FakeRunner()) == 0
    out = capsys.readouterr().out
    assert "/help" in out
    assert "--await-help" in out and "--confirm-help" in out
    assert "опросом" in out
    assert "ИТОГ СМОУКА: ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ" in out


def test_main_red_does_not_print_instruction(tmp_path, capsys):
    journal = _journal(_app(0, "ERROR", "src.x", "boom"))
    assert _run_main(tmp_path, FakeRunner(journal=journal)) == 1
    out = capsys.readouterr().out
    assert "--await-help" not in out
    assert "ИТОГ СМОУКА: КРАСНЫЙ" in out


def test_main_state_has_marker_checks_and_unknown_help(tmp_path):
    path = _make_state(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["help_marker_utc"] == "2026-10-09T12:00:00+00:00"
    assert data["invocation_id"] == INVOCATION
    assert len(data["checks"]) == 6
    assert data["help_handled"] is None and data["owner_confirmed"] is None
    assert "host python3[" not in path.read_text(encoding="utf-8")


def test_main_state_stores_redacted_errors_without_raw_lines(tmp_path):
    mail = "owner" + "@" + "example.org"
    journal = _journal(
        _app(0, "ERROR", "src.mail", f"login {mail} failed"),
        *_job_lines(10),
        _app(30, "INFO", "aiogram.dispatcher", "Run polling for bot id=1 - 'n'"),
    )
    _run_main(tmp_path, FakeRunner(journal=journal))
    text = (tmp_path / "state.json").read_text(encoding="utf-8")
    assert mail not in text and "host python3[" not in text
    assert json.loads(text)["errors"][0]["logger"] == "src.mail"


# ---------------------------------------------------------------- main: --await-help


def test_await_help_without_state_file_returns_two(tmp_path, capsys):
    rc = _phase(tmp_path, SeqRunner([GREEN_JOURNAL]), "--await-help")
    assert rc == 2
    captured = capsys.readouterr()
    assert "состояния" in captured.out + captured.err


def test_await_help_handled_updates_state_and_returns_zero(tmp_path, capsys):
    _make_state(tmp_path)
    rc = _phase(tmp_path, SeqRunner([_handled_journal()]), "--await-help")
    assert rc == 0
    assert _state(tmp_path)["help_handled"] is True
    assert ((tmp_path / "state.json").stat().st_mode & 0o777) == 0o600
    assert "обработано" in capsys.readouterr().out


def test_await_help_timeout_returns_one_and_marks_not_handled(tmp_path):
    _make_state(tmp_path)
    clock = Clock()
    rc = _phase(tmp_path, SeqRunner([GREEN_JOURNAL]), "--await-help", "--await-timeout", "15", clock=clock)
    assert rc == 1
    assert _state(tmp_path)["help_handled"] is False
    assert sum(clock.slept) >= 15


def test_await_help_refuses_state_of_previous_service_run(tmp_path, capsys):
    _make_state(tmp_path)
    other = "f" * 32
    runner = SeqRunner([_handled_journal()], show=_show(invocation=other))
    rc = _phase(tmp_path, runner, "--await-help")
    assert rc == 1
    assert "перезапущен" in capsys.readouterr().out
    assert _state(tmp_path)["help_handled"] is None


def test_await_help_corrupt_state_file_returns_two(tmp_path):
    (tmp_path / "state.json").write_text("{not json", encoding="utf-8")
    assert _phase(tmp_path, SeqRunner([GREEN_JOURNAL]), "--await-help") == 2


def test_await_timeout_must_be_non_negative_integer(tmp_path):
    assert _phase(tmp_path, FakeRunner(), "--await-help", "--await-timeout", "abc") == 2
    assert _phase(tmp_path, FakeRunner(), "--await-help", "--await-timeout", "-5") == 2


# ---------------------------------------------------------------- main: --confirm-help


def test_confirm_help_yes_after_handled_update_is_green(tmp_path, capsys):
    _make_state(tmp_path)
    assert _phase(tmp_path, SeqRunner([_handled_journal()]), "--await-help") == 0
    rc = _phase(tmp_path, SeqRunner([GREEN_JOURNAL]), "--confirm-help", "yes")
    assert rc == 0
    assert "ИТОГ СМОУКА: ЗЕЛЁНЫЙ" in capsys.readouterr().out
    assert _state(tmp_path)["owner_confirmed"] is True


def test_confirm_help_no_is_red(tmp_path, capsys):
    _make_state(tmp_path)
    assert _phase(tmp_path, SeqRunner([_handled_journal()]), "--await-help") == 0
    rc = _phase(tmp_path, SeqRunner([GREEN_JOURNAL]), "--confirm-help", "no")
    assert rc == 1
    assert "ИТОГ СМОУКА: КРАСНЫЙ" in capsys.readouterr().out


def test_confirm_help_yes_without_handled_update_is_red_with_explanation(tmp_path, capsys):
    _make_state(tmp_path)
    rc = _phase(tmp_path, SeqRunner([GREEN_JOURNAL]), "--confirm-help", "yes")
    out = capsys.readouterr().out
    assert rc == 1
    assert "ИТОГ СМОУКА: КРАСНЫЙ" in out
    assert "журнал" in out


def test_confirm_help_does_not_wait(tmp_path):
    _make_state(tmp_path)
    clock = Clock()
    _phase(tmp_path, SeqRunner([GREEN_JOURNAL]), "--confirm-help", "yes", clock=clock)
    assert clock.slept == []


def test_confirm_help_rejects_unknown_answer(tmp_path):
    _make_state(tmp_path)
    assert _phase(tmp_path, SeqRunner([GREEN_JOURNAL]), "--confirm-help", "maybe") == 2


def test_await_and_confirm_are_mutually_exclusive(tmp_path):
    _make_state(tmp_path)
    assert _phase(tmp_path, SeqRunner([GREEN_JOURNAL]), "--await-help", "--confirm-help", "yes") == 2


# ---------------------------------------------------------------- отчёт


def _dirty_state() -> dict:
    mail = "owner" + "@" + "example.org"
    token = "123456789" + ":" + "AAH" + "z" * 32
    return _state_dict(
        errors=[
            {"level": "ERROR", "logger": "src.collector.mail", "message": f"login {mail} failed"},
            {"level": "TRACEBACK", "logger": "src.x", "message": f"bad {token} | `tick`"},
        ],
        warnings={"src.a": 2, "src.b": 1},
        checks=[
            {"name": "сервис active", "ok": True, "detail": ""},
            {"name": "getMe: токен бота жив", "ok": False, "detail": f"url bot{token}/getMe {mail}"},
        ],
        help_handled=True,
        owner_confirmed=True,
    )


def test_render_report_md_has_required_sections():
    report = deploy.render_report_md(_dirty_state(), "a" * 40, NOW)
    for fragment in (
        "2026-10-09",
        "a" * 40,
        "| Проверка |",
        "Ошибки в окне старта",
        "src.collector.mail",
        "WARNING",
        "src.a",
        "Подтверждение бота",
        "ИТОГ СМОУКА:",
    ):
        assert fragment in report


def test_render_report_md_contains_no_emails_tokens_or_raw_lines():
    report = deploy.render_report_md(_dirty_state(), "a" * 40, NOW)
    assert not EMAIL_RE.search(report)
    assert not BOT_TOKEN_RE.search(report)
    assert "host python3[" not in report


def test_render_report_md_unknown_head_is_marked():
    report = deploy.render_report_md(_state_dict(), None, NOW)
    assert "неизвестен" in report


def test_render_report_md_verdict_matches_final_verdict():
    green = deploy.render_report_md(_state_dict(help_handled=True, owner_confirmed=True), "b" * 40, NOW)
    assert "ИТОГ СМОУКА: ЗЕЛЁНЫЙ" in green
    pending = deploy.render_report_md(_state_dict(), "b" * 40, NOW)
    assert "ИТОГ СМОУКА: ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ" in pending


def test_main_report_flag_writes_file_with_head_from_git(tmp_path):
    report = tmp_path / "smoke.md"
    runner = SeqRunner([GREEN_JOURNAL])
    rc = _phase(tmp_path, runner, "--report", str(report))
    assert rc in (0, 1)
    text = report.read_text(encoding="utf-8")
    assert "a" * 40 in text
    git_calls = [c for c in runner.calls if c[0] == "git"]
    assert git_calls == [["git", "-C", str(deploy.CORE_DIR), "rev-parse", "HEAD"]]


def test_main_report_overwrites_existing_file(tmp_path):
    report = tmp_path / "smoke.md"
    report.write_text("старое содержимое", encoding="utf-8")
    _phase(tmp_path, SeqRunner([GREEN_JOURNAL]), "--report", str(report))
    assert "старое содержимое" not in report.read_text(encoding="utf-8")


def test_main_report_after_confirm_reflects_final_verdict(tmp_path):
    _make_state(tmp_path)
    _phase(tmp_path, SeqRunner([_handled_journal()]), "--await-help")
    report = tmp_path / "smoke.md"
    rc = _phase(tmp_path, SeqRunner([GREEN_JOURNAL]), "--confirm-help", "yes", "--report", str(report))
    assert rc == 0
    assert "ИТОГ СМОУКА: ЗЕЛЁНЫЙ" in report.read_text(encoding="utf-8")


def test_validate_report_path_requires_existing_parent(tmp_path):
    with pytest.raises(ValueError):
        deploy.validate_report_path(tmp_path / "no_dir" / "r.md")


def test_validate_report_path_rejects_git_directory(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    with pytest.raises(ValueError):
        deploy.validate_report_path(git_dir / "r.md")


def test_validate_report_path_accepts_existing_file_and_new_file(tmp_path):
    existing = tmp_path / "r.md"
    existing.write_text("x", encoding="utf-8")
    assert deploy.validate_report_path(existing) == existing.resolve()
    assert deploy.validate_report_path(tmp_path / "new.md") == (tmp_path / "new.md").resolve()


def test_main_invalid_report_path_returns_two_before_any_command(tmp_path):
    runner = FakeRunner()
    rc = _phase(tmp_path, runner, "--report", str(tmp_path / "missing" / "r.md"))
    assert rc == 2
    assert runner.calls == []


# ---------------------------------------------------------------- read-only во всех режимах


def test_all_modes_pass_only_whitelisted_commands(tmp_path):
    _make_state(tmp_path)
    runners = []
    for flags in (
        ("--await-help",),
        ("--confirm-help", "yes"),
        ("--report", str(tmp_path / "r.md")),
    ):
        runner = SeqRunner([_handled_journal()])
        _phase(tmp_path, runner, *flags)
        runners.append(runner)
    forbidden = {"restart", "stop", "start", "kill", "reload", "enable", "disable", "daemon-reload"}
    for runner in runners:
        assert runner.calls
        for call in runner.calls:
            deploy.ensure_read_only(call)
            assert call[0] in {"systemctl", "journalctl", "git"}
            assert not (forbidden & set(call))


def test_ensure_read_only_git_only_rev_parse_head():
    deploy.ensure_read_only(["git", "-C", "/opt/assistant-core", "rev-parse", "HEAD"])
    for cmd in (
        ["git", "-C", "/x", "push"],
        ["git", "-C", "/x", "rev-parse", "HEAD", "--", "extra"],
        ["git", "commit", "-m", "x"],
    ):
        with pytest.raises(ValueError):
            deploy.ensure_read_only(cmd)


# ---------------------------------------------------------------- состояние: загрузка


def test_load_state_roundtrip_and_validation(tmp_path):
    path = tmp_path / "s.json"
    deploy.save_state(path, _state_dict())
    assert deploy.load_state(path)["invocation_id"] == INVOCATION
    with pytest.raises(deploy.StateError):
        deploy.load_state(tmp_path / "absent.json")
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(deploy.StateError):
        deploy.load_state(path)
    path.write_text('{"invocation_id": "x"}', encoding="utf-8")
    with pytest.raises(deploy.StateError):
        deploy.load_state(path)


def test_save_state_tightens_mode_of_existing_file(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{}", encoding="utf-8")
    path.chmod(0o644)
    deploy.save_state(path, _state_dict())
    assert (path.stat().st_mode & 0o777) == 0o600


# ---------------------------------------------------------------- D-07 и CLI


def test_help_handler_does_not_touch_db():
    """D-07: /help не пишет в БД. Если справка начнёт обращаться к self.db, тест краснеет.

    Предупреждение PRIV-01 в тексте справки допустимо: оно не использует БД. Запись в БД из
    справки возвращает вопрос владельцу.
    """
    tree = ast.parse(BOT_HANDLER_PATH.read_text(encoding="utf-8"))
    handlers = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == "handle_cmd_help"
    ]
    assert len(handlers) == 1, "обработчик handle_cmd_help не найден: тест не может быть пустым"
    for node in ast.walk(handlers[0]):
        if isinstance(node, ast.Attribute) and node.attr in {"db", "database"}:
            owner = node.value
            assert not (isinstance(owner, ast.Name) and owner.id == "self"), "handle_cmd_help обращается к БД"
        if isinstance(node, ast.Name):
            assert node.id not in {"Database", "sqlite3", "aiosqlite"}


def test_cli_help_lists_all_five_options():
    proc = subprocess.run(
        [sys.executable, str(DEPLOY_PATH), "--help"], capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0
    for option in ("--state-file", "--report", "--await-help", "--await-timeout", "--confirm-help"):
        assert option in proc.stdout


# ================================================================ Task 1 (план 01-07): резервная копия --backup

import hashlib  # noqa: E402
import os  # noqa: E402
import sqlite3  # noqa: E402
import stat  # noqa: E402


def _make_wal_db(path: Path, rows: int = 5) -> sqlite3.Connection:
    """Временная WAL-БД; соединение остаётся открытым, чтобы sidecar-файлы WAL существовали."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)")
    conn.executemany("INSERT INTO notes (body) VALUES (?)", [(f"row-{i}",) for i in range(rows)])
    conn.commit()
    return conn


def _logical_dump_hash(path: Path) -> str:
    conn = sqlite3.connect(path)
    try:
        digest = hashlib.sha256()
        for line in conn.iterdump():
            digest.update(line.encode("utf-8"))
        return digest.hexdigest()
    finally:
        conn.close()


class ForbiddenRunner:
    """Раннер, который не должен вызываться вообще (ветка --backup не трогает systemd и журнал)."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, cmd, timeout):
        self.calls.append(list(cmd))
        raise AssertionError(f"раннер не должен вызываться: {cmd}")


def test_build_parser_has_all_flags():
    parser = deploy.build_parser()
    flags = {opt for action in parser._actions for opt in action.option_strings if opt.startswith("--")}
    assert {
        "--state-file", "--report", "--await-help", "--await-timeout", "--confirm-help",
        "--backup", "--backup-dir",
    } <= flags


def test_build_parser_backup_defaults():
    args = deploy.build_parser().parse_args([])
    assert args.backup is False
    assert args.backup_dir == deploy.BACKUP_DIR_DEFAULT


def test_backup_dir_default_is_outside_git_tree():
    assert deploy.BACKUP_DIR_DEFAULT == Path("/var/backups/assistant-core")
    resolved = deploy.BACKUP_DIR_DEFAULT.resolve()
    assert deploy.CORE_DIR != resolved and deploy.CORE_DIR not in resolved.parents


def test_backup_creates_checked_copy_with_private_modes(tmp_path):
    live = tmp_path / "live.db"
    writer = _make_wal_db(live)
    try:
        dst_dir = tmp_path / "backups"
        copy = deploy.make_db_copy(live, dst_dir, NOW)
    finally:
        writer.close()
    assert copy.parent == dst_dir
    assert copy.name == "assistant-20261009-120000.db"
    assert stat.S_IMODE(copy.stat().st_mode) == 0o600
    assert stat.S_IMODE(dst_dir.stat().st_mode) == 0o700
    conn = sqlite3.connect(copy)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert conn.execute("SELECT count(*) FROM notes").fetchone() == (5,)
    finally:
        conn.close()
    assert sorted(os.listdir(dst_dir)) == [copy.name]  # без sidecar-файлов: копия самодостаточна


def test_backup_includes_rows_still_in_wal(tmp_path):
    live = tmp_path / "live.db"
    writer = _make_wal_db(live, rows=3)
    try:
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("INSERT INTO notes (body) VALUES ('tail')")
        writer.commit()
        copy = deploy.make_db_copy(live, tmp_path / "backups", NOW)
    finally:
        writer.close()
    conn = sqlite3.connect(copy)
    try:
        assert conn.execute("SELECT count(*) FROM notes").fetchone() == (4,)
    finally:
        conn.close()


def test_backup_does_not_change_source_database(tmp_path):
    live = tmp_path / "live.db"
    writer = _make_wal_db(live)
    try:
        before_hash = _logical_dump_hash(live)
        before_files = sorted(os.listdir(tmp_path))
        deploy.make_db_copy(live, tmp_path / "backups", NOW)
        after_files = sorted(p for p in os.listdir(tmp_path) if p != "backups")
        after_hash = _logical_dump_hash(live)
    finally:
        writer.close()
    assert after_hash == before_hash
    assert after_files == before_files  # в каталоге источника не появилось лишних файлов


def test_backup_opens_source_read_only(tmp_path, monkeypatch):
    live = tmp_path / "live.db"
    writer = _make_wal_db(live)
    seen: list[tuple] = []
    real_connect = sqlite3.connect

    def spy(*args, **kwargs):
        seen.append((args, kwargs))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", spy)
    try:
        deploy.make_db_copy(live, tmp_path / "backups", NOW)
    finally:
        monkeypatch.undo()
        writer.close()
    uri_calls = [(a, k) for a, k in seen if str(a[0]).startswith("file:")]
    assert len(uri_calls) == 1
    assert uri_calls[0][0][0].endswith("?mode=ro")
    assert uri_calls[0][1].get("uri") is True
    assert len(seen) == 2  # источник и приёмник, других соединений нет


def test_backup_refuses_existing_directory_with_wide_mode_and_keeps_its_mode(tmp_path):
    live = tmp_path / "live.db"
    writer = _make_wal_db(live)
    dst_dir = tmp_path / "wide"
    dst_dir.mkdir()
    dst_dir.chmod(0o755)
    try:
        with pytest.raises(deploy.BackupPathError):
            deploy.make_db_copy(live, dst_dir, NOW)
    finally:
        writer.close()
    assert stat.S_IMODE(dst_dir.stat().st_mode) == 0o755
    assert os.listdir(dst_dir) == []


def test_backup_accepts_own_private_directory_and_does_not_chmod_it(tmp_path, monkeypatch):
    live = tmp_path / "live.db"
    writer = _make_wal_db(live)
    dst_dir = tmp_path / "private"
    dst_dir.mkdir()
    dst_dir.chmod(0o700)
    chmod_calls: list[Path] = []
    real_chmod = os.chmod

    def spy_chmod(path, mode, *args, **kwargs):
        chmod_calls.append(Path(path))
        return real_chmod(path, mode, *args, **kwargs)

    monkeypatch.setattr(deploy.os, "chmod", spy_chmod)
    try:
        copy = deploy.make_db_copy(live, dst_dir, NOW)
    finally:
        writer.close()
    assert copy.parent == dst_dir.resolve()
    assert dst_dir.resolve() not in chmod_calls
    assert stat.S_IMODE(dst_dir.stat().st_mode) == 0o700


def test_backup_chmods_only_the_directory_it_created(tmp_path, monkeypatch):
    live = tmp_path / "live.db"
    writer = _make_wal_db(live)
    dst_dir = tmp_path / "parent" / "backups"
    chmod_calls: list[Path] = []
    real_chmod = os.chmod

    def spy_chmod(path, mode, *args, **kwargs):
        chmod_calls.append(Path(path))
        return real_chmod(path, mode, *args, **kwargs)

    monkeypatch.setattr(deploy.os, "chmod", spy_chmod)
    try:
        deploy.make_db_copy(live, dst_dir, NOW)
    finally:
        writer.close()
    assert chmod_calls == [dst_dir.resolve()]
    assert stat.S_IMODE(dst_dir.stat().st_mode) == 0o700


def test_backup_refuses_existing_directory_of_other_owner_without_changes(tmp_path, monkeypatch):
    live = tmp_path / "live.db"
    writer = _make_wal_db(live)
    dst_dir = tmp_path / "foreign"
    dst_dir.mkdir()
    dst_dir.chmod(0o700)
    monkeypatch.setattr(deploy.os, "geteuid", lambda: dst_dir.stat().st_uid + 1)
    try:
        with pytest.raises(deploy.BackupPathError):
            deploy.make_db_copy(live, dst_dir, NOW)
    finally:
        writer.close()
    assert stat.S_IMODE(dst_dir.stat().st_mode) == 0o700
    assert os.listdir(dst_dir) == []


def test_backup_rejects_directory_under_foreign_git_repository_before_creating_it(tmp_path, monkeypatch):
    fake_core = tmp_path / "core"
    fake_core.mkdir()
    monkeypatch.setattr(deploy, "CORE_DIR", fake_core.resolve())
    foreign = tmp_path / "chat-app"
    (foreign / ".git").mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    live = tmp_path / "live.db"
    writer = _make_wal_db(live)
    try:
        for inside in (foreign / "uploads", foreign / "uploads" / "deep" / "x", worktree / "b"):
            with pytest.raises(deploy.BackupPathError):
                deploy.make_db_copy(live, inside, NOW)
        assert not (foreign / "uploads").exists()
        assert not (worktree / "b").exists()
        link = tmp_path / "link"
        link.symlink_to(foreign)
        with pytest.raises(deploy.BackupPathError):
            deploy.make_db_copy(live, link / "uploads", NOW)
        assert not (foreign / "uploads").exists()
    finally:
        writer.close()


def test_backup_rejects_directory_inside_repo_before_creating_it(tmp_path, monkeypatch):
    fake_core = tmp_path / "repo"
    fake_core.mkdir()
    monkeypatch.setattr(deploy, "CORE_DIR", fake_core.resolve())
    live = tmp_path / "live.db"
    writer = _make_wal_db(live)
    try:
        for inside in (fake_core / "backups", fake_core / "a" / "b", fake_core):
            with pytest.raises(ValueError):
                deploy.make_db_copy(live, inside, NOW)
            assert not (fake_core / "backups").exists()
            assert not (fake_core / "a").exists()
        # путь через символическую ссылку тоже внутри репозитория
        link = tmp_path / "link"
        link.symlink_to(fake_core)
        with pytest.raises(ValueError):
            deploy.make_db_copy(live, link / "backups", NOW)
        assert not (fake_core / "backups").exists()
    finally:
        writer.close()
    assert os.listdir(fake_core) == []


def test_backup_removes_copy_and_raises_when_integrity_check_fails(tmp_path, monkeypatch):
    live = tmp_path / "live.db"
    writer = _make_wal_db(live)
    monkeypatch.setattr(deploy, "_integrity_ok", lambda conn: False)
    try:
        with pytest.raises(deploy.BackupError):
            deploy.make_db_copy(live, tmp_path / "backups", NOW)
    finally:
        writer.close()
    assert os.listdir(tmp_path / "backups") == []


def test_backup_removes_partial_file_when_source_is_missing(tmp_path):
    with pytest.raises(Exception):
        deploy.make_db_copy(tmp_path / "absent.db", tmp_path / "backups", NOW)
    assert not (tmp_path / "absent.db").exists()  # источник не создаётся режимом mode=ro
    assert os.listdir(tmp_path / "backups") == []


def test_backup_refuses_to_overwrite_existing_copy(tmp_path):
    live = tmp_path / "live.db"
    writer = _make_wal_db(live)
    try:
        first = deploy.make_db_copy(live, tmp_path / "backups", NOW)
        before = first.read_bytes()
        with pytest.raises(FileExistsError):
            deploy.make_db_copy(live, tmp_path / "backups", NOW)
    finally:
        writer.close()
    assert first.read_bytes() == before


def test_main_backup_creates_copy_prints_path_and_size_and_never_calls_runner(tmp_path, capsys):
    live = tmp_path / "live.db"
    writer = _make_wal_db(live)
    runner = ForbiddenRunner()
    dst_dir = tmp_path / "backups"
    try:
        rc = deploy.main(
            ["--backup", "--backup-dir", str(dst_dir), "--state-file", str(tmp_path / "state.json")],
            runner=runner,
            now=lambda: NOW,
            live_db=live,
        )
    finally:
        writer.close()
    out = capsys.readouterr().out
    assert rc == 0
    assert runner.calls == []
    copy = dst_dir / "assistant-20261009-120000.db"
    assert copy.is_file()
    assert str(copy) in out
    assert str(copy.stat().st_size) in out
    assert "содержимое не печатается" in out
    assert "row-" not in out
    assert not (tmp_path / "state.json").exists()  # смоук не запускался


def test_main_backup_failure_prints_only_exception_class_and_returns_one(tmp_path, capsys):
    runner = ForbiddenRunner()
    rc = deploy.main(
        ["--backup", "--backup-dir", str(tmp_path / "backups")],
        runner=runner,
        now=lambda: NOW,
        live_db=tmp_path / "absent.db",
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert runner.calls == []
    text = captured.out + captured.err
    assert "OperationalError" in text
    assert str(tmp_path / "absent.db") not in text  # текст исключения (с путём) не печатается


def test_main_backup_dir_inside_repo_returns_one_and_creates_nothing(tmp_path, monkeypatch, capsys):
    fake_core = tmp_path / "repo"
    fake_core.mkdir()
    monkeypatch.setattr(deploy, "CORE_DIR", fake_core.resolve())
    live = tmp_path / "live.db"
    writer = _make_wal_db(live)
    try:
        rc = deploy.main(
            ["--backup", "--backup-dir", str(fake_core / "backups")],
            runner=ForbiddenRunner(),
            now=lambda: NOW,
            live_db=live,
        )
    finally:
        writer.close()
    assert rc == 1
    assert "BackupPathError" in capsys.readouterr().out
    assert os.listdir(fake_core) == []


def test_main_backup_dir_without_backup_flag_is_usage_error(tmp_path, capsys):
    runner = ForbiddenRunner()
    rc = deploy.main(["--backup-dir", str(tmp_path / "b")], runner=runner, now=lambda: NOW)
    assert rc == 2
    assert runner.calls == []
    assert "--backup" in capsys.readouterr().err


def test_main_backup_cannot_be_combined_with_phase_flags(tmp_path, capsys):
    runner = ForbiddenRunner()
    for phase in (["--await-help"], ["--confirm-help", "yes"]):
        rc = deploy.main(["--backup", *phase], runner=runner, now=lambda: NOW, live_db=tmp_path / "x.db")
        assert rc == 2
    assert runner.calls == []
    assert "--backup" in capsys.readouterr().err


# ================================================================ Task 2 (план 01-07): --restart и откат без автоотката

HEAD_FULL = "c" * 40
PARENT_FULL = "d" * 40
NEW_INVOCATION = "fedcba9876543210fedcba9876543210"
STARTING_JOURNAL = _journal(_app(0, "INFO", "assistant-worker", "Assistant Worker starting up..."))
MUTATING_VERBS = {"restart", "stop", "start", "kill", "reload", "enable", "disable", "daemon-reload"}
ROLLBACK_MARK = "ОТЧЁТ О СБОЕ ВЫКАТКИ"
NO_AUTOROLLBACK = "Автоотката нет: откат требует нового разрешения владельца"


class RestartRunner:
    """Сценарный раннер: git, systemctl show/restart и журнал нового запуска; всё записывается."""

    def __init__(
        self,
        *,
        status: str = "",
        head: str | None = HEAD_FULL,
        parent: str | None = PARENT_FULL,
        show_polls_before_new: int = 0,
        journal_polls_before_polling: int = 0,
        journal: str = GREEN_JOURNAL,
        restart_rc: int = 0,
        restart_raises: Exception | None = None,
        invocation_never_changes: bool = False,
        on_restart=None,
    ) -> None:
        self.status = status
        self.head = head
        self.parent = parent
        self.show_polls_before_new = show_polls_before_new
        self.journal_polls_before_polling = journal_polls_before_polling
        self.journal = journal
        self.restart_rc = restart_rc
        self.restart_raises = restart_raises
        self.invocation_never_changes = invocation_never_changes
        self.on_restart = on_restart
        self.calls: list[list[str]] = []
        self.timeouts: list[int] = []
        self.restarted = False
        self.show_after_restart = 0
        self.journal_calls = 0

    def restart_calls(self) -> list[list[str]]:
        return [c for c in self.calls if c[:2] == ["systemctl", "restart"]]

    def __call__(self, cmd, timeout):
        self.calls.append(list(cmd))
        self.timeouts.append(timeout)
        prog = cmd[0]

        def done(out: str = "", rc: int = 0):
            return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr="")

        if prog == "git":
            sub = list(cmd[3:])
            if sub and sub[0] == "status":
                return done(self.status)
            if sub == ["rev-parse", "HEAD"]:
                return done(f"{self.head}\n") if self.head else done("", 128)
            if sub == ["rev-parse", "HEAD^"]:
                return done(f"{self.parent}\n") if self.parent else done("", 128)
        if prog == "systemctl" and cmd[1] == "restart":
            if self.on_restart is not None:
                self.on_restart()
            if self.restart_raises is not None:
                raise self.restart_raises
            self.restarted = True
            return done("", self.restart_rc)
        if prog == "systemctl" and cmd[1] == "show":
            if not self.restarted or self.invocation_never_changes:
                return done(_show())
            self.show_after_restart += 1
            if self.show_after_restart <= self.show_polls_before_new:
                return done(_show(active="activating", sub="start"))
            return done(_show(invocation=NEW_INVOCATION))
        if prog == "journalctl":
            self.journal_calls += 1
            if self.journal_calls <= self.journal_polls_before_polling:
                return done(STARTING_JOURNAL)
            return done(self.journal)
        raise AssertionError(f"неожиданная команда раннеру: {cmd}")


def _restart_main(
    tmp_path: Path,
    runner,
    *flags: str,
    clock: Clock | None = None,
    live_db: Path | None = None,
    opener: FakeOpener | None = None,
) -> int:
    clock = clock or Clock()
    env_path = tmp_path / ".env.test"
    env_path.write_text(f"TELEGRAM_BOT_TOKEN={BOT_TOKEN}\n", encoding="utf-8")
    main_py = tmp_path / "main_synthetic.py"
    main_py.write_text(SYNTHETIC_MAIN, encoding="utf-8")
    return deploy.main(
        ["--state-file", str(tmp_path / "state.json"), *flags],
        runner=runner,
        now=clock.now,
        sleep=clock.sleep,
        opener=opener or FakeOpener(),
        env_path=env_path,
        main_py_path=main_py,
        live_db=live_db,
    )


def _tokens(runner) -> set[str]:
    return {part for call in runner.calls for part in call}


# ---------------------------------------------------------------- CLI и разбор git status


def test_build_parser_restart_flag_defaults_to_false():
    parser = deploy.build_parser()
    assert parser.parse_args([]).restart is False
    assert parser.parse_args(["--restart"]).restart is True


def test_restart_cannot_be_combined_with_phase_flags(tmp_path, capsys):
    runner = RestartRunner()
    for phase in (["--await-help"], ["--confirm-help", "yes"]):
        assert _restart_main(tmp_path, runner, "--restart", *phase) == 2
    assert runner.calls == []
    assert "--restart" in capsys.readouterr().err


def test_git_dirty_paths_ignores_clean_tree_and_planning_only_changes():
    runner = RestartRunner(status=" M .planning/config.json\0?? .planning/state.json\0A  .planning/x/y.md\0")
    assert deploy.git_dirty_paths(runner) == []


def test_git_dirty_paths_lists_modified_and_untracked_outside_planning():
    runner = RestartRunner(status=" M src/a.py\0?? scripts/new.py\0 M .planning/config.json\0D  docs/old.md\0")
    assert deploy.git_dirty_paths(runner) == ["src/a.py", "scripts/new.py", "docs/old.md"]


def test_git_dirty_paths_handles_renames_and_copies():
    runner = RestartRunner(
        status="R  docs/new.md\0.planning/old.md\0C  src/copy.py\0src/orig.py\0 M .planning/p.md\0"
    )
    assert deploy.git_dirty_paths(runner) == ["docs/new.md", "src/copy.py", "src/orig.py"]


def test_git_dirty_paths_uses_porcelain_z_with_all_untracked_files():
    runner = RestartRunner()
    deploy.git_dirty_paths(runner)
    assert runner.calls == [
        ["git", "-C", str(deploy.CORE_DIR), "status", "--porcelain=v1", "-z", "--untracked-files=all"]
    ]


def test_git_dirty_paths_raises_command_error_when_git_fails():
    class Failing(RestartRunner):
        def __call__(self, cmd, timeout):
            self.calls.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="fatal: not a git repository")

    with pytest.raises(deploy.CommandError):
        deploy.git_dirty_paths(Failing())


def test_ensure_read_only_allows_git_status_and_parent_lookup_only_in_exact_form():
    core = str(deploy.CORE_DIR)
    deploy.ensure_read_only(["git", "-C", core, "status", "--porcelain=v1", "-z", "--untracked-files=all"])
    deploy.ensure_read_only(["git", "-C", core, "rev-parse", "HEAD^"])
    for cmd in (
        ["git", "-C", core, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignored"],
        ["git", "-C", core, "status"],
        ["git", "-C", core, "rev-parse", "HEAD^^"],
        ["git", "-C", core, "revert", "--no-edit", "HEAD"],
        ["git", "-C", core, "checkout", "--", "."],
    ):
        with pytest.raises(ValueError):
            deploy.ensure_read_only(cmd)


def test_ensure_read_only_still_rejects_restart_command():
    with pytest.raises(ValueError):
        deploy.ensure_read_only(["systemctl", "restart", deploy.SERVICE_NAME])


# ---------------------------------------------------------------- без флага рестарт недостижим


def test_without_restart_flag_runner_never_sees_restart(tmp_path):
    for flags in ((), ("--report", str(tmp_path / "r.md"))):
        runner = RestartRunner(invocation_never_changes=True)
        assert _restart_main(tmp_path, runner, *flags) == 0
        assert runner.calls
        assert not (MUTATING_VERBS & _tokens(runner))
        assert runner.restart_calls() == []


def test_backup_flag_alone_never_reaches_runner_or_restart(tmp_path):
    live = tmp_path / "live.db"
    writer = _make_wal_db(live)
    runner = RestartRunner()
    try:
        rc = _restart_main(tmp_path, runner, "--backup", "--backup-dir", str(tmp_path / "b"), live_db=live)
    finally:
        writer.close()
    assert rc == 0
    assert runner.calls == []


# ---------------------------------------------------------------- отказ при грязном дереве


def test_restart_refused_on_dirty_tree(tmp_path, capsys):
    runner = RestartRunner(status=" M src/a.py\0?? scripts/new.py\0 M .planning/config.json\0")
    rc = _restart_main(tmp_path, runner, "--restart")
    out = capsys.readouterr().out
    assert rc == 2
    assert "src/a.py" in out and "scripts/new.py" in out
    assert ".planning/config.json" not in out
    assert [c[0] for c in runner.calls] == ["git"]  # ни одного вызова systemctl
    assert not (tmp_path / "state.json").exists()


def test_restart_refused_when_git_status_fails(tmp_path, capsys):
    class Failing(RestartRunner):
        def __call__(self, cmd, timeout):
            self.calls.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="")

    runner = Failing()
    assert _restart_main(tmp_path, runner, "--restart") == 2
    assert all(c[0] == "git" for c in runner.calls)
    assert "дерево git" in capsys.readouterr().out


def test_restart_refused_when_head_is_unknown(tmp_path):
    runner = RestartRunner(head=None)
    assert _restart_main(tmp_path, runner, "--restart") == 2
    assert all(c[0] == "git" for c in runner.calls)


def test_restart_dirty_tree_with_backup_makes_no_copy(tmp_path):
    live = tmp_path / "live.db"
    writer = _make_wal_db(live)
    runner = RestartRunner(status=" M src/a.py\0")
    dst = tmp_path / "b"
    try:
        rc = _restart_main(tmp_path, runner, "--restart", "--backup", "--backup-dir", str(dst), live_db=live)
    finally:
        writer.close()
    assert rc == 2
    assert not dst.exists()


# ---------------------------------------------------------------- порядок и ожидание готовности


def test_restart_sequence_and_ready_wait(tmp_path, capsys):
    live = tmp_path / "live.db"
    writer = _make_wal_db(live)
    dst = tmp_path / "backups"
    seen_at_restart: dict[str, list[str]] = {}
    runner = RestartRunner(
        show_polls_before_new=2,
        journal_polls_before_polling=1,
        on_restart=lambda: seen_at_restart.setdefault("files", sorted(os.listdir(dst))),
    )
    clock = Clock()
    try:
        rc = _restart_main(
            tmp_path, runner, "--restart", "--backup", "--backup-dir", str(dst), clock=clock, live_db=live
        )
    finally:
        writer.close()
    out = capsys.readouterr().out
    assert rc == 0

    kinds = []
    for call in runner.calls:
        if call[0] == "git":
            kinds.append("git:" + call[3] + (":" + call[4] if call[3] == "rev-parse" else ""))
        else:
            kinds.append(f"{call[0]}:{call[1]}")
    # git: status, rev-parse HEAD, rev-parse HEAD^; затем прежнее состояние, restart, опрос.
    assert kinds[:3] == ["git:status", "git:rev-parse:HEAD", "git:rev-parse:HEAD^"]
    assert kinds[3] == "systemctl:show"
    assert kinds[4] == "systemctl:restart"
    restart_index = 4
    assert runner.calls[restart_index] == ["systemctl", "restart", deploy.SERVICE_NAME]
    assert runner.timeouts[restart_index] >= deploy.RESTART_TIMEOUT_S
    assert len(runner.restart_calls()) == 1
    # копия готова до рестарта
    assert len(seen_at_restart["files"]) == 1 and seen_at_restart["files"][0].startswith("assistant-")
    # опрос: два «activating», новая инвокация без polling в журнале, затем polling; потом тот же смоук
    assert kinds[5:] == (
        ["systemctl:show"] * 3
        + ["journalctl:-u", "systemctl:show", "journalctl:-u"]
        + ["systemctl:show", "journalctl:-u"]
    )
    assert runner.journal_calls == 3
    # паузы: шаг опроса и затем окно старта до смоука
    assert deploy.POLL_INTERVAL_S in clock.slept
    assert clock.slept[-1] == deploy.STARTUP_TAIL_SECONDS
    # состояние и вывод относятся к новой инвокации
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["invocation_id"] == NEW_INVOCATION
    assert "АВТОМАТИЧЕСКАЯ ЧАСТЬ: ЗЕЛЁНАЯ" in out
    assert "--await-help" in out and "--confirm-help" in out
    assert ROLLBACK_MARK not in out


def test_restart_service_returns_result_with_old_and_new_invocation():
    runner = RestartRunner(show_polls_before_new=1, journal_polls_before_polling=1)
    clock = Clock()
    result = deploy.restart_service(runner, clock.sleep, clock.now)
    assert isinstance(result, deploy.RestartResult)
    assert result.ok is True
    assert result.old_invocation == INVOCATION
    assert result.new_invocation == NEW_INVOCATION


def test_restart_without_backup_does_not_create_copy(tmp_path):
    runner = RestartRunner()
    assert _restart_main(tmp_path, runner, "--restart", "--backup-dir", str(tmp_path / "b")) == 2
    runner = RestartRunner()
    assert _restart_main(tmp_path, runner, "--restart") == 0
    assert not (tmp_path / "b").exists()


def test_restart_backup_failure_stops_before_any_systemctl(tmp_path, capsys):
    runner = RestartRunner()
    rc = _restart_main(
        tmp_path, runner, "--restart", "--backup", "--backup-dir", str(tmp_path / "b"),
        live_db=tmp_path / "absent.db",
    )
    assert rc == 1
    assert all(c[0] == "git" for c in runner.calls)
    assert "Резервная копия не создана" in capsys.readouterr().out


def test_restart_ready_timeout_when_invocation_never_changes(tmp_path, capsys):
    runner = RestartRunner(invocation_never_changes=True)
    clock = Clock()
    rc = _restart_main(tmp_path, runner, "--restart", clock=clock)
    out = capsys.readouterr().out
    assert rc == 1
    assert sum(clock.slept) >= deploy.READY_TIMEOUT_S
    assert len(runner.restart_calls()) == 1
    assert runner.journal_calls == 0  # смоук не запускался
    assert ROLLBACK_MARK in out and NO_AUTOROLLBACK in out
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert deploy.final_verdict(state) == "КРАСНЫЙ"


def test_restart_ready_timeout_when_polling_never_appears(tmp_path, capsys):
    runner = RestartRunner(journal_polls_before_polling=10**6)
    clock = Clock()
    rc = _restart_main(tmp_path, runner, "--restart", clock=clock)
    out = capsys.readouterr().out
    assert rc == 1
    assert sum(clock.slept) >= deploy.READY_TIMEOUT_S
    assert "Run polling for bot" in out
    assert ROLLBACK_MARK in out
    assert len(runner.restart_calls()) == 1


def test_restart_command_nonzero_exit_is_red_without_waiting(tmp_path, capsys):
    runner = RestartRunner(restart_rc=1)
    clock = Clock()
    rc = _restart_main(tmp_path, runner, "--restart", clock=clock)
    assert rc == 1
    assert clock.slept == []
    assert ROLLBACK_MARK in capsys.readouterr().out


def test_restart_command_timeout_is_red_without_second_attempt(tmp_path, capsys):
    runner = RestartRunner(restart_raises=subprocess.TimeoutExpired(["systemctl"], 300))
    rc = _restart_main(tmp_path, runner, "--restart")
    assert rc == 1
    assert len(runner.restart_calls()) == 1
    assert ROLLBACK_MARK in capsys.readouterr().out


def test_restart_report_is_written_for_green_and_red_outcomes(tmp_path):
    green = tmp_path / "green.md"
    assert _restart_main(tmp_path, RestartRunner(), "--restart", "--report", str(green)) == 0
    assert "c" * 40 in green.read_text(encoding="utf-8")
    red_journal = GREEN_JOURNAL + _journal(_app(20, "ERROR", "src.collector.mail", "boom"))
    red = tmp_path / "red.md"
    rc = _restart_main(tmp_path, RestartRunner(journal=red_journal), "--restart", "--report", str(red))
    assert rc == 1
    assert "КРАСНЫЙ" in red.read_text(encoding="utf-8")


# ---------------------------------------------------------------- красный смоук: отчёт без автоотката


RED_JOURNAL = GREEN_JOURNAL + _journal(_app(20, "ERROR", "src.collector.mail", "boom while polling"))


def test_red_smoke_after_restart_prints_rollback_and_runs_nothing(tmp_path, capsys, monkeypatch):
    live = tmp_path / "live.db"
    writer = _make_wal_db(live)
    dst = tmp_path / "backups"
    events: list[tuple[str, object]] = []
    real_print = print

    def spy_print(*args, **kwargs):
        events.append(("print", " ".join(str(a) for a in args)))
        real_print(*args, **kwargs)

    class Recording(RestartRunner):
        def __call__(self, cmd, timeout):
            events.append(("call", list(cmd)))
            return super().__call__(cmd, timeout)

    monkeypatch.setattr(deploy, "print", spy_print, raising=False)
    runner = Recording(journal=RED_JOURNAL)
    try:
        rc = _restart_main(
            tmp_path, runner, "--restart", "--backup", "--backup-dir", str(dst),
            "--report", str(tmp_path / "r.md"), live_db=live,
        )
    finally:
        writer.close()
    out = capsys.readouterr().out
    assert rc == 1
    backup_file = next(dst.iterdir())

    # отчёт и команды отката напечатаны
    assert ROLLBACK_MARK in out
    assert "src.collector.mail" in out and "boom while polling" in out
    assert "git -C" in out and "revert --no-edit " + HEAD_FULL[:10] in out
    assert str(backup_file) in out and str(deploy.LIVE_DB) in out
    assert NO_AUTOROLLBACK in out
    assert "затрёт" in out  # предупреждение про данные после выкатки

    # раннер после отчёта не получает ни одной команды
    report_index = max(i for i, (kind, value) in enumerate(events) if kind == "print" and ROLLBACK_MARK in value)
    assert not [e for e in events[report_index:] if e[0] == "call"]

    # за всё время: ни revert, ни checkout, ни cp, ни stop/start, ни второго restart
    tokens = _tokens(runner)
    assert not ({"revert", "checkout", "cp", "stop", "start", "reset", "kill"} & tokens)
    assert len(runner.restart_calls()) == 1
    # отчёт --report записан и при красном исходе, состояние красное
    assert "КРАСНЫЙ" in (tmp_path / "r.md").read_text(encoding="utf-8")
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert deploy.final_verdict(state) == "КРАСНЫЙ"


def test_red_smoke_without_backup_has_no_restore_commands(tmp_path, capsys):
    runner = RestartRunner(journal=RED_JOURNAL)
    assert _restart_main(tmp_path, runner, "--restart") == 1
    out = capsys.readouterr().out
    assert ROLLBACK_MARK in out and "revert --no-edit" in out
    assert "cp " not in out and "systemctl stop" not in out
    assert "резервной копии не было" in out


def test_build_rollback_report_uses_short_hashes_and_numbers_commands():
    rows = [deploy.CheckResult("в окне старта нет ERROR/CRITICAL/Traceback", False, "src.x: boom")]
    text = deploy.build_rollback_report(HEAD_FULL, PARENT_FULL, Path("/var/backups/x/assistant-1.db"), rows)
    assert HEAD_FULL not in text and PARENT_FULL not in text
    assert HEAD_FULL[:10] in text and PARENT_FULL[:10] in text
    assert "в окне старта нет ERROR/CRITICAL/Traceback" in text and "src.x: boom" in text
    numbered = [line for line in text.splitlines() if line.strip()[:2] in {f"{i}." for i in range(1, 10)}]
    assert len(numbered) >= 5
    assert "/var/backups/x/assistant-1.db" in text
    assert NO_AUTOROLLBACK in text


def test_build_rollback_report_handles_unknown_parent_and_missing_backup():
    text = deploy.build_rollback_report(HEAD_FULL, None, None, [deploy.CheckResult("сервис active", False)])
    assert HEAD_FULL[:10] in text
    assert "родитель" in text and "неизвестен" in text
    assert "systemctl stop" not in text


def test_build_rollback_report_redacts_secrets_in_failed_rows():
    rows = [deploy.CheckResult("проверка", False, f"token {BOT_TOKEN} user@example.org")]
    text = deploy.build_rollback_report(HEAD_FULL, PARENT_FULL, None, rows)
    assert BOT_TOKEN not in text and "user@example.org" not in text


# ---------------------------------------------------------------- статические свойства (T-01-21, T-01-22)


def test_restart_command_is_built_in_exactly_one_place():
    code = _code_lines()
    assert sum(line.count('"restart"') for line in code) == 1
    tree = ast.parse(DEPLOY_PATH.read_text(encoding="utf-8"))
    for func in ast.walk(tree):
        if isinstance(func, ast.FunctionDef) and any(
            isinstance(n, ast.Constant) and n.value == "restart" for n in ast.walk(func)
        ):
            assert func.name == "restart_service"


def test_restart_service_is_called_only_from_the_restart_branch():
    tree = ast.parse(DEPLOY_PATH.read_text(encoding="utf-8"))
    callers: set[str] = set()
    for func in ast.walk(tree):
        if not isinstance(func, ast.FunctionDef):
            continue
        for node in ast.walk(func):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "restart_service":
                callers.add(func.name)
    assert callers == {"_run_restart"}
    main_src = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "main"
    )
    guarded = [
        n for n in ast.walk(main_src)
        if isinstance(n, ast.If) and "args.restart" in ast.unparse(n.test)
        and any(isinstance(c, ast.Name) and c.id == "_run_restart" for sub in n.body for c in ast.walk(sub))
    ]
    assert guarded, "_run_restart должна вызываться из main только под условием args.restart"


def test_rollback_commands_are_never_executed_by_the_script():
    code = "\n".join(_code_lines())
    assert 'runner(["git", "revert"' not in code
    assert 'runner(["git", "checkout"' not in code
    assert not re.search(r'\[\s*"git",\s*"-C",[^\]]*"(revert|checkout|reset)"', code)
    assert not re.search(r'\[\s*"cp"', code)
    assert not re.search(r'"systemctl",\s*"(stop|start)"', code)


def test_cli_help_lists_backup_and_restart_options():
    proc = subprocess.run(
        [sys.executable, str(DEPLOY_PATH), "--help"], capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0
    for option in ("--backup", "--backup-dir", "--restart"):
        assert option in proc.stdout


# ================================================================ Task 3 (план 01-07): docs/OPS_DEPLOY.md

DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "OPS_DEPLOY.md"


def _cli_long_flags() -> list[str]:
    parser = deploy.build_parser()
    flags = [
        opt
        for action in parser._actions
        for opt in action.option_strings
        if opt.startswith("--") and opt != "--help"
    ]
    assert flags, "парсер не отдал ни одного флага: тест не может быть пустым"
    return sorted(flags)


def _missing_flags(text: str) -> list[str]:
    return [flag for flag in _cli_long_flags() if flag not in text]


def test_docs_cover_all_cli_flags():
    assert DOC_PATH.is_file()
    assert _missing_flags(DOC_PATH.read_text(encoding="utf-8")) == []


def test_docs_flag_check_detects_a_missing_flag():
    text = DOC_PATH.read_text(encoding="utf-8").replace("--confirm-help", "--x-confirm")
    assert _missing_flags(text) == ["--confirm-help"]


def test_docs_have_all_numbered_sections_in_order():
    text = DOC_PATH.read_text(encoding="utf-8")
    headers = re.findall(r"^## (\d+)\. (.+)$", text, re.MULTILINE)
    assert [int(number) for number, _ in headers] == list(range(1, 13))
    titles = {number: title for number, title in headers}
    for number, word in {
        "1": "Назначение", "2": "Правила", "3": "Команды", "4": "смоук", "5": "Окно ошибок",
        "6": "Фазы без TTY", "7": "Резервная копия", "8": "Рестарт", "9": "Откат",
        "10": "Отчёт", "11": "не делает", "12": "ограничения",
    }.items():
        assert word.lower() in titles[number].lower(), (number, titles[number])


def test_docs_is_long_enough_and_in_russian():
    text = DOC_PATH.read_text(encoding="utf-8")
    assert len(text.splitlines()) >= 80
    assert len(re.findall(r"[а-яёА-ЯЁ]", text)) > 2000


def test_docs_phase3_backup_duty_before_migration_0003_in_one_paragraph():
    paragraphs = re.split(r"\n\s*\n", DOC_PATH.read_text(encoding="utf-8"))
    assert any("Phase 3" in p and "--backup" in p and "0003" in p for p in paragraphs)


def test_docs_contain_no_emails_tokens_or_secret_values():
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "@" not in text
    assert not re.search(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b", text)
    assert not re.search(r"\b[0-9a-fA-F]{32,}\b", text)
    assert not re.search(r"(?i)(password|passwd|secret)\s*[=:]\s*\S+", text)
    assert not re.search(r"(?i)\b(TELEGRAM_BOT_TOKEN|GEMINI_API_KEYS?)\s*=\s*\S+", text)


def test_docs_numbers_match_script_constants():
    text = DOC_PATH.read_text(encoding="utf-8")
    assert str(deploy.BACKUP_DIR_DEFAULT) in text
    assert str(deploy.STATE_FILE_DEFAULT) in text
    assert f"{deploy.RESTART_TIMEOUT_S} секунд" in text
    assert f"{deploy.READY_TIMEOUT_S} секунд" in text
    assert f"{deploy.STARTUP_TAIL_SECONDS} секунд" in text
    assert str(deploy.DEFAULT_AWAIT_TIMEOUT_S) in text
    assert f"{deploy.POLL_INTERVAL_S} секунд" in text


def test_docs_state_that_rollback_is_never_automatic_and_restart_needs_owner_yes():
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "Автоотката нет" in text
    assert "ТОЛЬКО печатаются" in text
    assert "только после ответа «да» владельца" in text
