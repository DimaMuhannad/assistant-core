#!/usr/bin/env python3
"""Скрипт выкатки assistant-core: read-only смоук работающего сервиса (OPS-01).

Запуск (из /opt/assistant-core):  python3 scripts/deploy.py

Без флагов выполняется только проверка текущего сервиса assistant-worker. Читает:
  - ``systemctl show`` (состояние юнита и InvocationID);
  - ``journalctl`` текущей инвокации (фильтр по InvocationID, а не по времени);
  - исходник ``src/main.py`` (разбор ast, без импорта);
  - из ``.env`` только ключ ``TELEGRAM_BOT_TOKEN``, его значение нигде не печатается.

Чего скрипт не делает: не пишет в БД и не открывает её, не импортирует ``src``, не запрашивает у
Telegram накопленные обновления бота, не открывает пользовательские сессии, не перезапускает и не
останавливает сервис. Печатает только имена логгеров, очищенные усечённые сообщения об ошибках и
счётчики: сырые строки журнала, e-mail и токены в вывод и в файлы не попадают.

Только стандартная библиотека.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[1]
SERVICE_NAME = "assistant-worker"
# Окно ошибок старта: от начала инвокации до строки «Run polling for bot» плюс 60 секунд.
# Так в него попадают начальные циклы коллекторов, которые main() выполняет до запуска
# планировщика, и первые секунды работы, но не штатные сбои дальнейшей жизни сервиса
# (решение планировщика по D-08; белого списка «внешних» ошибок нет, решение владельца 2026-10-09).
STARTUP_TAIL_SECONDS = 60
SYSTEMCTL_TIMEOUT_S = 30
JOURNAL_TIMEOUT_S = 120
STATE_FILE_DEFAULT = Path("/var/tmp/assistant-core-smoke-state.json")
MESSAGE_LIMIT = 160
MAX_LISTED_FINDINGS = 10

Runner = Callable[[list[str], int], subprocess.CompletedProcess]

_INVOCATION_RE = re.compile(r"[0-9a-fA-F]{32}")


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class ServiceState:
    active_state: str
    sub_state: str
    main_pid: int
    invocation_id: str
    n_restarts: int


@dataclass(frozen=True)
class JournalRecord:
    ts: datetime
    level: str
    logger: str
    text: str


@dataclass(frozen=True)
class Finding:
    level: str
    logger: str
    message: str


@dataclass(frozen=True)
class SmokeResult:
    """Итог автоматической части: строки таблицы и данные для следующих шагов."""

    rows: list[CheckResult]
    errors: list[Finding]
    warnings: list[Finding]
    invocation_id: str
    records: list[JournalRecord]


class CommandError(Exception):
    """Команда не выполнилась; текст пригоден для вывода (без сырого вывода команды)."""


# --------------------------------------------------------------------------- подпроцессы


def run_cmd(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Запуск подпроцесса: список аргументов, без shell, с таймаутом."""
    return subprocess.run(cmd, capture_output=True, text=True, shell=False, timeout=timeout)


def ensure_read_only(cmd: Sequence[str]) -> None:
    """Белый список команд: только чтение. Всё остальное (включая изменение сервиса) - ошибка."""
    if not cmd:
        raise ValueError("пустая команда")
    program = cmd[0]
    if program == "systemctl" and len(cmd) >= 2 and cmd[1] == "show":
        return
    if program == "journalctl" and "--rotate" not in cmd and not any(
        part.startswith("--vacuum") or part == "--flush" for part in cmd
    ):
        return
    raise ValueError(f"команда не разрешена в режиме только чтения: {program}")


def _run(runner: Runner, cmd: list[str], timeout: int) -> str:
    """Выполнить разрешённую команду и вернуть stdout; сбои превращаются в CommandError."""
    ensure_read_only(cmd)
    program = cmd[0]
    try:
        proc = runner(cmd, timeout)
    except FileNotFoundError as exc:
        raise CommandError(f"команда {program} не найдена") from exc
    except subprocess.TimeoutExpired as exc:
        raise CommandError(f"{program}: таймаут {timeout} с") from exc
    except OSError as exc:
        raise CommandError(f"{program}: {type(exc).__name__}") from exc
    if proc.returncode != 0:
        reason = f"{program}: код возврата {proc.returncode}"
        stderr = redact(proc.stderr or "", limit=80)
        raise CommandError(f"{reason}: {stderr}" if stderr else reason)
    return proc.stdout or ""


# --------------------------------------------------------------------------- очистка текста

_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_RE_BOT_URL_TOKEN = re.compile(r"bot\d+:[^\s/'\"?&]+", re.IGNORECASE)
_RE_BOT_TOKEN = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b")
_RE_SECRET_PARAM = re.compile(
    r"\b([\w-]*(?:token|key|secret|password|passwd|auth)[\w-]*)=[^&\s'\"]+", re.IGNORECASE
)
_RE_HEX_LONG = re.compile(r"\b[0-9A-Fa-f]{32,}\b")
_RE_B64_LONG = re.compile(r"[A-Za-z0-9+/_-]{32,}={0,2}")


def _b64_replacement(match: re.Match[str]) -> str:
    value = match.group(0)
    # Пути вроде /opt/assistant-core/src/connectors не содержат цифр: их не трогаем.
    if any(ch.isdigit() for ch in value) and any(ch.isalpha() for ch in value):
        return "<скрыто>"
    return value


def redact(text: str, limit: int = MESSAGE_LIMIT) -> str:
    """Убрать e-mail, токены и секреты, схлопнуть пробелы, усечь до ``limit`` с многоточием.

    Очистка идёт до усечения: секрет на границе обрезки не может остаться половиной.
    """
    cleaned = _RE_EMAIL.sub("<email>", text)
    cleaned = _RE_BOT_URL_TOKEN.sub("bot<token>", cleaned)
    cleaned = _RE_BOT_TOKEN.sub("<token>", cleaned)
    cleaned = _RE_SECRET_PARAM.sub(r"\1=<скрыто>", cleaned)
    cleaned = _RE_HEX_LONG.sub("<скрыто>", cleaned)
    cleaned = _RE_B64_LONG.sub(_b64_replacement, cleaned)
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > limit:
        cleaned = cleaned[: max(limit - 1, 0)] + "…"
    return cleaned


# --------------------------------------------------------------------------- сервис и журнал


def get_service_state(runner: Runner = run_cmd) -> ServiceState:
    """Состояние юнита из ``systemctl show``; пустой InvocationID (юнит не запущен) допустим."""
    out = _run(
        runner,
        [
            "systemctl", "show", SERVICE_NAME,
            "-p", "ActiveState", "-p", "SubState", "-p", "MainPID",
            "-p", "InvocationID", "-p", "NRestarts",
        ],
        SYSTEMCTL_TIMEOUT_S,
    )
    values: dict[str, str] = {}
    for line in out.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip()] = value.strip()

    def _int(name: str) -> int:
        try:
            return int(values.get(name, "0") or 0)
        except ValueError:
            return 0

    return ServiceState(
        active_state=values.get("ActiveState", ""),
        sub_state=values.get("SubState", ""),
        main_pid=_int("MainPID"),
        invocation_id=values.get("InvocationID", ""),
        n_restarts=_int("NRestarts"),
    )


def read_invocation_journal(
    runner: Runner, invocation_id: str, since: datetime | None = None
) -> str:
    """Журнал одной инвокации. Фильтр по InvocationID: метки приложения смешаны UTC и MSK."""
    if not _INVOCATION_RE.fullmatch(invocation_id):
        raise ValueError("InvocationID имеет неожиданный формат")
    cmd = [
        "journalctl", "-u", SERVICE_NAME,
        f"_SYSTEMD_INVOCATION_ID={invocation_id}",
        "--no-pager", "-o", "short-iso",
    ]
    if since is not None:
        cmd += ["--since", since.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")]
    return _run(runner, cmd, JOURNAL_TIMEOUT_S)


_RE_JOURNAL_LINE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2}))"
    r"\s+\S+\s+[^\s\[:]+(?:\[\d+\])?:\s?(?P<msg>.*)$"
)
_RE_APP_LINE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \[(?P<level>[A-Z]+)\] "
    r"(?P<logger>[^\s:]+): (?P<text>.*)$"
)
_TRACEBACK_HEAD = "Traceback (most recent call last):"


def _parse_ts(raw: str) -> datetime | None:
    value = raw.replace(",", ".")
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    value = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", value)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_journal(text: str) -> list[JournalRecord]:
    """Разобрать вывод ``journalctl -o short-iso`` в записи приложения.

    Время записи берётся из префикса journald (однозначное). Строки без заголовка приложения
    дописываются к предыдущей записи; «Traceback» открывает отдельную запись TRACEBACK.
    """
    records: list[JournalRecord] = []
    for line in text.splitlines():
        match = _RE_JOURNAL_LINE.match(line)
        if not match:
            continue  # маркеры journalctl («-- No entries --») и пустые строки
        ts = _parse_ts(match.group("ts"))
        if ts is None:
            continue
        message = match.group("msg")
        app = _RE_APP_LINE.match(message)
        if app:
            records.append(JournalRecord(ts, app.group("level"), app.group("logger"), app.group("text")))
            continue
        if message.startswith(_TRACEBACK_HEAD):
            logger_name = records[-1].logger if records else ""
            records.append(JournalRecord(ts, "TRACEBACK", logger_name, message))
            continue
        if records:
            records[-1] = replace(records[-1], text=records[-1].text + "\n" + message)
    return records


def startup_window(
    records: Sequence[JournalRecord], tail_seconds: int = STARTUP_TAIL_SECONDS
) -> tuple[list[JournalRecord], datetime | None]:
    """Окно старта и метка запуска polling (None, если записи «Run polling for bot» нет)."""
    polling_ts = next((r.ts for r in records if "Run polling for bot" in r.text), None)
    if polling_ts is None:
        return list(records), None
    end = polling_ts + timedelta(seconds=tail_seconds)
    return [r for r in records if r.ts <= end], polling_ts


def _finding_message(record: JournalRecord) -> str:
    lines = [part for part in record.text.splitlines() if part.strip()]
    if not lines:
        return ""
    # У Traceback осмысленна последняя строка (тип и текст исключения), у остальных первая.
    chosen = lines[-1] if record.level == "TRACEBACK" else lines[0]
    return redact(chosen)


def scan_window(window: Sequence[JournalRecord]) -> tuple[list[Finding], list[Finding]]:
    """Ошибки (ERROR, CRITICAL, TRACEBACK) и предупреждения (WARNING) окна."""
    errors: list[Finding] = []
    warnings: list[Finding] = []
    for record in window:
        if record.level in {"ERROR", "CRITICAL", "TRACEBACK"}:
            errors.append(Finding(record.level, record.logger, _finding_message(record)))
        elif record.level == "WARNING":
            warnings.append(Finding(record.level, record.logger, _finding_message(record)))
    return errors, warnings


# --------------------------------------------------------------------------- проверки


def check_service_active(state: ServiceState) -> CheckResult:
    ok = state.active_state == "active"
    detail = f"ActiveState={state.active_state}, SubState={state.sub_state}, NRestarts={state.n_restarts}"
    return CheckResult("сервис active", ok, "" if ok else detail)


def check_journal_available(records: Sequence[JournalRecord]) -> CheckResult:
    if records:
        return CheckResult("журнал текущего запуска доступен", True)
    return CheckResult(
        "журнал текущего запуска доступен",
        False,
        "записей инвокации нет: возможна ротация журнала",
    )


def check_startup_errors(errors: Sequence[Finding]) -> CheckResult:
    name = "в окне старта нет ERROR/CRITICAL/Traceback"
    if not errors:
        return CheckResult(name, True)
    lines = [f"{f.logger}: {f.message}" for f in errors[:MAX_LISTED_FINDINGS]]
    rest = len(errors) - MAX_LISTED_FINDINGS
    if rest > 0:
        lines.append(f"… и ещё {rest}")
    return CheckResult(name, False, "\n".join(lines))


def check_polling_started(polling_ts: datetime | None) -> CheckResult:
    name = "polling бота запущен (запись в журнале)"
    if polling_ts is not None:
        return CheckResult(name, True)
    return CheckResult(
        name,
        False,
        "записи «Run polling for bot» нет: запуск не завершён или возможна ротация журнала",
    )


def auto_ok(rows: Sequence[CheckResult]) -> bool:
    return bool(rows) and all(row.ok for row in rows)


def _warning_summary(warnings: Sequence[Finding]) -> str:
    counts = Counter(f.logger or "?" for f in warnings)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    loggers = ", ".join(f"{name}×{count}" for name, count in ordered[:MAX_LISTED_FINDINGS])
    return f"WARNING в окне старта: {len(warnings)} (логгеры: {loggers}), вердикт не меняют"


def render_table(rows: Sequence[CheckResult], warnings: Sequence[Finding] = ()) -> str:
    """Русская таблица «Проверка | Результат», сводка WARNING и итог автоматической части."""
    header = "Проверка"
    width = max([len(header), *(len(row.name) for row in rows)])
    lines = [f"{header.ljust(width)} | Результат", f"{'-' * width}-+-{'-' * 9}"]
    for row in rows:
        lines.append(f"{row.name.ljust(width)} | {'✓' if row.ok else '✗'}")
        for detail_line in row.detail.splitlines():
            lines.append(f"  ↳ {detail_line}")
    if warnings:
        lines.append(_warning_summary(warnings))
    lines.append(f"АВТОМАТИЧЕСКАЯ ЧАСТЬ: {'ЗЕЛЁНАЯ' if auto_ok(rows) else 'КРАСНАЯ'}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- состояние смоука


def save_state(path: Path, data: dict) -> None:
    """Записать JSON с правами 0600 (каталог вне репозитория, секретов в данных нет)."""
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------- автоматическая часть


def run_smoke(runner: Runner) -> SmokeResult:
    """Read-only автоматическая часть: сервис, журнал инвокации, окно ошибок, polling."""
    rows: list[CheckResult] = []
    try:
        state = get_service_state(runner)
    except CommandError as exc:
        rows.append(CheckResult("сервис active", False, str(exc)))
        return SmokeResult(rows, [], [], "", [])

    rows.append(check_service_active(state))
    if state.active_state != "active" or not state.invocation_id:
        if state.active_state == "active":
            rows.append(CheckResult("журнал текущего запуска доступен", False, "InvocationID пуст"))
        return SmokeResult(rows, [], [], state.invocation_id, [])

    try:
        text = read_invocation_journal(runner, state.invocation_id)
    except CommandError as exc:
        rows.append(CheckResult("журнал текущего запуска доступен", False, str(exc)))
        return SmokeResult(rows, [], [], state.invocation_id, [])

    records = parse_journal(text)
    rows.append(check_journal_available(records))
    window, polling_ts = startup_window(records)
    errors, warnings = scan_window(window)
    rows.append(check_startup_errors(errors))
    rows.append(check_polling_started(polling_ts))
    return SmokeResult(rows, errors, warnings, state.invocation_id, records)


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deploy.py",
        description="Read-only смоук сервиса assistant-worker (без флагов сервис не меняется).",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=STATE_FILE_DEFAULT,
        help=f"файл состояния смоука вне репозитория (по умолчанию {STATE_FILE_DEFAULT})",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    runner: Runner = run_cmd,
    now: Callable[[], datetime] | None = None,
) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    clock = now or (lambda: datetime.now(timezone.utc))

    result = run_smoke(runner)
    print(render_table(result.rows, result.warnings))

    state = {
        "created_utc": clock().astimezone(timezone.utc).isoformat(timespec="seconds"),
        "invocation_id": result.invocation_id,
        "checks": [asdict(row) for row in result.rows],
    }
    try:
        save_state(args.state_file, state)
    except OSError as exc:
        print(f"Не удалось сохранить файл состояния: {type(exc).__name__}", file=sys.stderr)
        return 2
    return 0 if auto_ok(result.rows) else 1


if __name__ == "__main__":
    sys.exit(main())
