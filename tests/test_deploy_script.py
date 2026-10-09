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
