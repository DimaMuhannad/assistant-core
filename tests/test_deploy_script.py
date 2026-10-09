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


def test_script_does_not_import_src_and_does_not_open_database():
    source = "\n".join(_code_lines())
    assert not re.search(r"^\s*(from|import)\s+src\b", source, re.MULTILINE)
    assert "sqlite3" not in source and "aiosqlite" not in source


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
