#!/usr/bin/env python3
"""Скрипт выкатки assistant-core: смоук сервиса, резервная копия БД, рестарт по флагу (OPS-01).

Запуск (из /opt/assistant-core):  python3 scripts/deploy.py

Без флагов выполняется только проверка текущего сервиса assistant-worker. Читает:
  - ``systemctl show`` (состояние юнита и InvocationID);
  - ``journalctl`` текущей инвокации (фильтр по InvocationID, а не по времени);
  - исходник ``src/main.py`` (разбор ast, без импорта);
  - из ``.env`` только ключ ``TELEGRAM_BOT_TOKEN``, его значение нигде не печатается.

Изменяющие действия возможны только по явным флагам (D-10, D-11):
  - ``--backup``: консистентная копия боевой БД через sqlite3 backup API, источник открыт в режиме
    ``mode=ro``, копия вне дерева git (D-11). Это единственное место, где скрипт открывает SQLite;
  - ``--restart``: рестарт assistant-worker с ожиданием готовности и тем же смоуком (D-10).
    Откат скрипт никогда не выполняет: при красном исходе он только печатает команды (D-12).

Чего скрипт не делает: не пишет в боевую БД, не импортирует ``src``, не запрашивает у Telegram
накопленные обновления бота, не открывает пользовательские сессии. Печатает только имена логгеров,
очищенные усечённые сообщения об ошибках и счётчики: сырые строки журнала, e-mail и токены в вывод
и в файлы не попадают.

Только стандартная библиотека.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shlex
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
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
GET_ME_TIMEOUT_S = 15
AWAIT_INTERVAL_S = 5
DEFAULT_AWAIT_TIMEOUT_S = 120
MAX_STORED_ERRORS = 50
# Единственный ключ .env, который читает скрипт; значение нигде не печатается и не сохраняется.
BOT_TOKEN_KEY = "TELEGRAM_BOT_TOKEN"
ENV_FILE_DEFAULT = CORE_DIR / ".env"
MAIN_PY_DEFAULT = CORE_DIR / "src" / "main.py"
# Резервные копии лежат вне дерева git (D-11). Каталог выбран планировщиком, меняется --backup-dir.
BACKUP_DIR_DEFAULT = Path("/var/backups/assistant-core")
LIVE_DB = CORE_DIR / "data" / "assistant.db"
# Рестарт: systemd может останавливать сервис до 90 с (TimeoutStopSec) перед SIGKILL, поэтому запас
# на сам restart и на ожидание готовности по 300 с (Pitfall 5). Шаг опроса - POLL_INTERVAL_S.
RESTART_TIMEOUT_S = 300
READY_TIMEOUT_S = 300
POLL_INTERVAL_S = 5
SHORT_HASH_LEN = 10
MAX_LISTED_PATHS = 20
POLLING_MARK = "Run polling for bot"

Runner = Callable[[list[str], int], subprocess.CompletedProcess]
Opener = Callable[..., object]

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
class ExpectedJob:
    func: str
    job_id: str
    conditional: bool


@dataclass(frozen=True)
class SmokeResult:
    """Итог автоматической части: строки таблицы и данные для следующих шагов."""

    rows: list[CheckResult]
    errors: list[Finding]
    warnings: list[Finding]
    invocation_id: str
    records: list[JournalRecord]


@dataclass(frozen=True)
class RestartResult:
    """Итог рестарта: сервис вернулся в рабочее состояние (новая инвокация, polling) или нет."""

    ok: bool
    detail: str
    old_invocation: str
    new_invocation: str


class CommandError(Exception):
    """Команда не выполнилась; текст пригоден для вывода (без сырого вывода команды)."""


class StateError(Exception):
    """Файл состояния смоука отсутствует или повреждён; текст пригоден для вывода."""


class BackupError(Exception):
    """Резервная копия не прошла проверку целостности; копия удалена."""


class BackupPathError(ValueError):
    """Каталог резервных копий внутри дерева git: копия БД с данными не должна попасть в репозиторий."""


# --------------------------------------------------------------------------- подпроцессы


def run_cmd(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Запуск подпроцесса: список аргументов, без shell, с таймаутом."""
    return subprocess.run(cmd, capture_output=True, text=True, shell=False, timeout=timeout)


_GIT_STATUS_TAIL = ["status", "--porcelain=v1", "-z", "--untracked-files=all"]
_READ_ONLY_GIT_TAILS = (["rev-parse", "HEAD"], ["rev-parse", "HEAD^"], _GIT_STATUS_TAIL)


def ensure_read_only(cmd: Sequence[str]) -> None:
    """Белый список команд: только чтение. Всё остальное (включая изменение сервиса) - ошибка.

    Команда рестарта сюда намеренно не входит: она формируется в одном месте (restart_service)
    и достижима только из ветки ``--restart``.
    """
    if not cmd:
        raise ValueError("пустая команда")
    program = cmd[0]
    if program == "systemctl" and len(cmd) >= 2 and cmd[1] == "show":
        return
    if program == "git" and len(cmd) >= 4 and cmd[1] == "-C" and list(cmd[3:]) in _READ_ONLY_GIT_TAILS:
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
    polling_ts = next((r.ts for r in records if POLLING_MARK in r.text), None)
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


# --------------------------------------------------------------------------- планировщик (D-14)

_RE_ADDED_JOB = re.compile(r'^Added job "(?P<func>[^"]+)" to job store')
SCHEDULER_LOGGER = "apscheduler.scheduler"


class _JobVisitor(ast.NodeVisitor):
    """Собирает вызовы ``<что-то>.add_job(функция, ..., id="...")`` с признаком «под if»."""

    def __init__(self) -> None:
        self.jobs: list[ExpectedJob] = []
        self._if_depth = 0

    def visit_If(self, node: ast.If) -> None:
        self._if_depth += 1
        self.generic_visit(node)
        self._if_depth -= 1

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_job"
            and node.args
            and isinstance(node.args[0], ast.Name)
        ):
            job_id = next(
                (
                    kw.value.value
                    for kw in node.keywords
                    if kw.arg == "id"
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                ),
                "",
            )
            self.jobs.append(ExpectedJob(node.args[0].id, job_id, self._if_depth > 0))
        self.generic_visit(node)


def expected_jobs(main_py_text: str) -> list[ExpectedJob]:
    """Ожидаемые задачи планировщика из текста src/main.py (ast, без импорта и запуска)."""
    visitor = _JobVisitor()
    visitor.visit(ast.parse(main_py_text))
    return visitor.jobs


def load_expected_jobs(path: Path = MAIN_PY_DEFAULT) -> list[ExpectedJob]:
    return expected_jobs(Path(path).read_text(encoding="utf-8"))


def parse_added_jobs(records: Sequence[JournalRecord]) -> tuple[set[str], bool]:
    """Имена функций из «Added job» и признак «Scheduler started» (по всему журналу инвокации)."""
    added: set[str] = set()
    started = False
    for record in records:
        if record.logger != SCHEDULER_LOGGER:
            continue
        first_line = record.text.splitlines()[0] if record.text else ""
        match = _RE_ADDED_JOB.match(first_line)
        if match:
            added.add(match.group("func"))
        elif first_line.strip() == "Scheduler started":
            started = True
    return added, started


def check_scheduler_jobs(
    expected: Sequence[ExpectedJob], added: set[str], started: bool
) -> CheckResult:
    required = [job for job in expected if not job.conditional]
    registered = [job for job in required if job.func in added]
    name = f"планировщик: задачи зарегистрированы ({len(registered)} из {len(required)})"
    missing = [job.job_id or job.func for job in required if job.func not in added]
    lines: list[str] = []
    if not required:
        lines.append("в src/main.py не найдено ни одного вызова add_job")
    if not started:
        lines.append("планировщик не стартовал: записи «Scheduler started» нет")
    if missing:
        lines.append("не зарегистрированы: " + ", ".join(missing))
    if (missing or not started) and required:
        lines.append("возможна ротация журнала")
    for job in expected:
        if job.conditional:
            state = "зарегистрирована" if job.func in added else "не зарегистрирована"
            lines.append(f"условная: {job.job_id or job.func} ({state})")
    ok = bool(required) and started and not missing
    return CheckResult(name, ok, "\n".join(lines))


# --------------------------------------------------------------------------- бот: getMe (D-06)


def read_env_key(env_path: Path, key: str) -> str | None:
    """Значение одного ключа из .env (кавычки, ``export``, комментарии) или None."""
    try:
        text = Path(env_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        name, sep, value = line.partition("=")
        if not sep or name.strip() != key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        return value or None
    return None


def telegram_get_me(
    token: str, opener: Opener = urllib.request.urlopen, timeout: int = GET_ME_TIMEOUT_S
) -> tuple[bool, str]:
    """GET getMe. Тело ответа (имя бота) и текст исключений не печатаются: токен есть в URL."""
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with opener(url, timeout=timeout) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return False, f"getMe: HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - граница ввода-вывода: наружу только имя класса
        return False, f"getMe: {type(exc).__name__}"
    if isinstance(payload, dict) and payload.get("ok") is True:
        return True, "getMe: токен жив"
    return False, "getMe: ответ без ok=true"


def check_get_me(env_path: Path, opener: Opener = urllib.request.urlopen) -> CheckResult:
    name = "getMe: токен бота жив"
    token = read_env_key(env_path, BOT_TOKEN_KEY)
    if token is None:
        return CheckResult(name, False, f"токен не найден (ключ {BOT_TOKEN_KEY} в .env)")
    ok, detail = telegram_get_me(token, opener)
    return CheckResult(name, ok, "" if ok else detail)


# --------------------------------------------------------------------------- состояние смоука

_STATE_REQUIRED_KEYS = ("invocation_id", "help_marker_utc", "checks")


def _write_private(path: Path, text: str) -> None:
    """Записать файл с правами 0600 (в том числе сузить права существующего файла)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def save_state(path: Path, data: dict) -> None:
    """Записать JSON состояния с правами 0600 (каталог вне репозитория, секретов нет)."""
    _write_private(path, json.dumps(data, ensure_ascii=False, indent=2))


def load_state(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StateError(
            "файл состояния не найден: сначала запустите смоук без флагов (python3 scripts/deploy.py)"
        ) from exc
    except (OSError, ValueError) as exc:
        raise StateError(f"файл состояния повреждён ({type(exc).__name__}): повторите смоук") from exc
    if not isinstance(data, dict) or any(key not in data for key in _STATE_REQUIRED_KEYS):
        raise StateError("файл состояния имеет неожиданный формат: повторите смоук")
    return data


def build_state(result: SmokeResult, moment: datetime) -> dict:
    """Состояние смоука из очищенных данных: сырые строки журнала сюда не попадают."""
    stamp = moment.astimezone(timezone.utc).isoformat(timespec="seconds")
    return {
        "created_utc": stamp,
        "invocation_id": result.invocation_id,
        "checks": [asdict(row) for row in result.rows],
        "errors": [asdict(f) for f in result.errors[:MAX_STORED_ERRORS]],
        "errors_total": len(result.errors),
        "warnings": dict(Counter(f.logger or "?" for f in result.warnings)),
        "help_marker_utc": stamp,
        "help_handled": None,
        "owner_confirmed": None,
    }


# --------------------------------------------------------------------------- фазы без TTY (D-09)

_RE_HANDLED = re.compile(r"^Update id=\d+ is handled\b")
UPDATES_LOGGER = "aiogram.event"


def count_handled_updates(records: Sequence[JournalRecord], since: datetime) -> int:
    """Число обработанных ботом обновлений («Update id=N is handled») не раньше метки."""
    return sum(
        1
        for record in records
        if record.logger == UPDATES_LOGGER
        and record.ts >= since
        and _RE_HANDLED.match(record.text.splitlines()[0] if record.text else "")
    )


def _marker(state: dict) -> datetime:
    marker = _parse_ts(str(state.get("help_marker_utc", "")))
    if marker is None:
        raise StateError("в файле состояния нет метки времени: повторите смоук")
    return marker


def _handled_since_marker(state: dict, runner: Runner) -> bool:
    marker = _marker(state)
    text = read_invocation_journal(runner, str(state["invocation_id"]), since=marker)
    return count_handled_updates(parse_journal(text), marker) > 0


def ensure_same_invocation(state: dict, runner: Runner) -> None:
    """Состояние смоука относится к текущему запуску сервиса, иначе подтверждать нечего."""
    current = get_service_state(runner)
    if current.invocation_id != state.get("invocation_id"):
        raise CommandError(
            "сервис перезапущен или остановлен после смоука: повторите автоматическую часть"
        )


def await_help(
    state: dict,
    runner: Runner,
    sleep: Callable[[float], None],
    now: Callable[[], datetime],
    timeout: int = DEFAULT_AWAIT_TIMEOUT_S,
    interval: int = AWAIT_INTERVAL_S,
) -> bool:
    """Ждать в журнале обработанное обновление после метки; опрос с шагом ``interval``."""
    deadline = now() + timedelta(seconds=timeout)
    while True:
        if _handled_since_marker(state, runner):
            return True
        if now() >= deadline:
            return False
        sleep(interval)


def confirm_help(state: dict, answer: str, runner: Runner) -> dict:
    """Записать ответ владельца; если обновление ещё не проверялось, один раз глянуть журнал."""
    updated = dict(state)
    updated["owner_confirmed"] = answer == "yes"
    if updated.get("help_handled") is None:
        updated["help_handled"] = _handled_since_marker(updated, runner)
    return updated


def final_verdict(state: dict) -> str:
    """ЗЕЛЁНЫЙ только при зелёной автоматической части, обработанном обновлении и «да» владельца."""
    checks = state.get("checks") or []
    if not checks or not all(item.get("ok") for item in checks):
        return "КРАСНЫЙ"
    if state.get("owner_confirmed") is False or state.get("help_handled") is False:
        return "КРАСНЫЙ"
    if state.get("owner_confirmed") is True and state.get("help_handled") is True:
        return "ЗЕЛЁНЫЙ"
    return "ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ"


def verdict_reasons(state: dict) -> list[str]:
    """Пояснения к вердикту по-русски (без секретов: имена проверок и флаги)."""
    reasons: list[str] = []
    checks = state.get("checks") or []
    failed = [str(item.get("name", "?")) for item in checks if not item.get("ok")]
    if not checks:
        reasons.append("автоматическая часть не выполнялась")
    if failed:
        reasons.append("красные проверки автоматической части: " + "; ".join(failed))
    if state.get("help_handled") is False:
        if state.get("owner_confirmed") is True:
            reasons.append(
                "ответ владельца «да», но в журнале нет обработанного обновления после метки"
            )
        else:
            reasons.append("в журнале нет обработанного обновления после метки")
    if state.get("owner_confirmed") is False:
        reasons.append("владелец ответил «нет»")
    if state.get("help_handled") is None:
        reasons.append("не выполнен --await-help")
    if state.get("owner_confirmed") is None:
        reasons.append("не выполнен --confirm-help")
    return reasons


# --------------------------------------------------------------------------- отчёт (D-13)


def validate_report_path(path: Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if ".git" in resolved.parts:
        raise ValueError("отчёт нельзя писать внутрь каталога .git")
    if resolved.is_dir():
        raise ValueError("путь отчёта указывает на каталог")
    if not resolved.parent.is_dir():
        raise ValueError(f"каталог отчёта не существует: {resolved.parent}")
    return resolved


def _git_commit(runner: Runner, rev: str) -> str | None:
    """Полный хеш коммита через ``git rev-parse`` или None, если определить не удалось."""
    try:
        out = _run(runner, ["git", "-C", str(CORE_DIR), "rev-parse", rev], SYSTEMCTL_TIMEOUT_S)
    except CommandError:
        return None
    value = out.strip()
    return value if re.fullmatch(r"[0-9a-f]{40}", value) else None


def get_head(runner: Runner) -> str | None:
    """Хеш HEAD репозитория."""
    return _git_commit(runner, "HEAD")


def get_parent_head(runner: Runner) -> str | None:
    """Хеш родителя HEAD (None у первого коммита или при сбое)."""
    return _git_commit(runner, "HEAD^")


def git_dirty_paths(runner: Runner) -> list[str]:
    """Пути с изменениями вне ``.planning/`` (изменённые, добавленные, неотслеживаемые, переименованные).

    Разбор ``git status --porcelain=v1 -z``: записи разделены NUL, у переименования и копирования
    следом идёт запись с исходным путём. Содержимое файлов не читается и не возвращается.
    """
    out = _run(runner, ["git", "-C", str(CORE_DIR), *_GIT_STATUS_TAIL], SYSTEMCTL_TIMEOUT_S)
    entries = out.split("\0")
    paths: list[str] = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        paths.append(path)
        if ("R" in status or "C" in status) and index < len(entries) and entries[index]:
            paths.append(entries[index])
            index += 1
    return [path for path in paths if path != ".planning" and not path.startswith(".planning/")]


def _md(text: object) -> str:
    """Очистка и экранирование для markdown-таблиц и списков."""
    return redact(str(text)).replace("|", "\\|").replace("`", "'")


def _yes_no(value: object, unknown: str) -> str:
    return unknown if value is None else ("да" if value else "нет")


def render_report_md(state: dict, head: str | None, now: datetime) -> str:
    """Markdown-отчёт смоука только из состояния и очищенных данных (повторная очистка внутри)."""
    stamp = now.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# Отчёт смоука assistant-worker",
        "",
        f"- Дата: {stamp}",
        f"- Коммит HEAD: {('`' + head + '`') if head else 'неизвестен'}",
        f"- InvocationID: `{_md(state.get('invocation_id', ''))}`",
        "",
        "## Проверки",
        "",
        "| Проверка | Результат |",
        "|---|---|",
    ]
    details: list[str] = []
    for item in state.get("checks") or []:
        lines.append(f"| {_md(item.get('name', '?'))} | {'✓' if item.get('ok') else '✗'} |")
        for detail_line in str(item.get("detail", "")).splitlines():
            details.append(f"- {_md(item.get('name', '?'))} ↳ {_md(detail_line)}")
    if details:
        lines += ["", *details]

    errors = state.get("errors") or []
    total = int(state.get("errors_total", len(errors)) or 0)
    lines += ["", f"## Ошибки в окне старта ({total})", ""]
    if errors:
        lines += [
            f"- [{_md(e.get('level', '?'))}] `{_md(e.get('logger', '?'))}`: {_md(e.get('message', ''))}"
            for e in errors
        ]
        if total > len(errors):
            lines.append(f"- … показано {len(errors)} из {total}")
    else:
        lines.append("Нет.")

    warnings = state.get("warnings") or {}
    lines += ["", "## WARNING в окне старта", ""]
    if warnings:
        ordered = sorted(warnings.items(), key=lambda item: (-int(item[1]), str(item[0])))
        lines += [f"- `{_md(name)}`: {int(count)}" for name, count in ordered]
        lines.append("Вердикт WARNING не меняют.")
    else:
        lines.append("Нет.")

    lines += [
        "",
        "## Подтверждение бота",
        "",
        f"- Обработанное обновление после метки {_md(state.get('help_marker_utc', '?'))}: "
        f"{_yes_no(state.get('help_handled'), 'не проверялось')}",
        f"- Ответ владельца на /help: {_yes_no(state.get('owner_confirmed'), 'не получен')}",
    ]
    verdict = final_verdict(state)
    if verdict != "ЗЕЛЁНЫЙ":
        lines += ["", *[f"- {_md(reason)}" for reason in verdict_reasons(state)]]
    lines += ["", f"**ИТОГ СМОУКА: {verdict}**", ""]
    return "\n".join(lines)


# --------------------------------------------------------------------------- автоматическая часть


def run_smoke(
    runner: Runner,
    opener: Opener = urllib.request.urlopen,
    env_path: Path = ENV_FILE_DEFAULT,
    main_py_path: Path = MAIN_PY_DEFAULT,
) -> SmokeResult:
    """Read-only автоматическая часть: сервис, журнал, окно ошибок, polling, задачи, getMe."""
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

    try:
        expected = load_expected_jobs(main_py_path)
    except (OSError, SyntaxError, ValueError) as exc:
        rows.append(
            CheckResult(
                "планировщик: задачи зарегистрированы",
                False,
                f"не удалось разобрать src/main.py: {type(exc).__name__}",
            )
        )
    else:
        added, started = parse_added_jobs(records)
        rows.append(check_scheduler_jobs(expected, added, started))
    rows.append(check_get_me(env_path, opener))
    return SmokeResult(rows, errors, warnings, state.invocation_id, records)


# --------------------------------------------------------------------------- резервная копия (D-11)

_DB_SIDECARS = ("-wal", "-shm", "-journal")


def _integrity_ok(conn: sqlite3.Connection) -> bool:
    return conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]


def _inside_core(path: Path) -> bool:
    core = CORE_DIR.resolve()
    return path == core or core in path.parents


def make_db_copy(live_db: Path, dst_dir: Path, now: datetime) -> Path:
    """Консистентная копия БД через sqlite3 backup API (источник только на чтение, D-11).

    Единственное место, где скрипт открывает SQLite. Каталог ``dst_dir`` должен быть выделенным
    под копии: его права сужаются до 0700. Копия создаётся с правами 0600 и не перезаписывает
    существующий файл. Проверка целостности (``PRAGMA integrity_check``) идёт на копии; при
    любом сбое неполная копия удаляется.
    """
    target_dir = Path(dst_dir).expanduser().resolve()
    if _inside_core(target_dir):
        raise BackupPathError("каталог резервных копий внутри дерева git")
    os.makedirs(target_dir, mode=0o700, exist_ok=True)
    os.chmod(target_dir, 0o700)
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")
    copy_path = target_dir / f"assistant-{stamp}.db"
    fd = os.open(copy_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    src: sqlite3.Connection | None = None
    out: sqlite3.Connection | None = None
    try:
        src = sqlite3.connect(Path(live_db).resolve().as_uri() + "?mode=ro", uri=True)
        out = sqlite3.connect(copy_path)
        src.backup(out)
        # Копия самодостаточна: без WAL и sidecar-файлов её можно восстановить одним cp.
        out.execute("PRAGMA journal_mode=DELETE").fetchall()
        if not _integrity_ok(out):
            raise BackupError("копия не прошла PRAGMA integrity_check")
    except BaseException:
        for conn in (out, src):
            if conn is not None:
                conn.close()
        out = src = None
        for suffix in ("", *_DB_SIDECARS):
            try:
                os.unlink(str(copy_path) + suffix)
            except FileNotFoundError:
                pass
        raise
    finally:
        for conn in (out, src):
            if conn is not None:
                conn.close()
    return copy_path


# --------------------------------------------------------------------------- рестарт (D-10, D-12)


def _poll_ready(runner: Runner, old_invocation: str) -> tuple[str, str]:
    """Один опрос готовности: (новая инвокация, причина ожидания); пустая причина - готово."""
    try:
        state = get_service_state(runner)
    except CommandError as exc:
        return "", f"состояние сервиса недоступно ({exc})"
    if not state.invocation_id or state.invocation_id == old_invocation:
        return "", "новая инвокация сервиса не появилась"
    if state.active_state != "active":
        return state.invocation_id, f"ActiveState={state.active_state}"
    try:
        records = parse_journal(read_invocation_journal(runner, state.invocation_id))
    except CommandError as exc:
        return state.invocation_id, f"журнал новой инвокации недоступен ({exc})"
    if not any(POLLING_MARK in record.text for record in records):
        return state.invocation_id, f"в журнале новой инвокации нет записи «{POLLING_MARK}»"
    return state.invocation_id, ""


def restart_service(
    runner: Runner,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] | None = None,
) -> RestartResult:
    """Перезапустить assistant-worker и дождаться новой инвокации и запуска polling.

    Единственное место, где формируется команда рестарта; вызывается только из ветки ``--restart``.
    Ничего не откатывает и не повторяет: любой сбой возвращается красным результатом.
    """
    clock = now or (lambda: datetime.now(timezone.utc))
    try:
        before = get_service_state(runner)
    except CommandError as exc:
        return RestartResult(False, f"не удалось прочитать состояние сервиса до рестарта: {exc}", "", "")
    old = before.invocation_id

    command = ["systemctl", "restart", SERVICE_NAME]
    try:
        proc = runner(command, RESTART_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return RestartResult(False, f"systemctl: таймаут рестарта {RESTART_TIMEOUT_S} с", old, "")
    except OSError as exc:
        return RestartResult(False, f"systemctl: {type(exc).__name__}", old, "")
    if proc.returncode != 0:
        reason = f"systemctl: код возврата рестарта {proc.returncode}"
        stderr = redact(proc.stderr or "", limit=80)
        return RestartResult(False, f"{reason}: {stderr}" if stderr else reason, old, "")

    deadline = clock() + timedelta(seconds=READY_TIMEOUT_S)
    while True:
        new, reason = _poll_ready(runner, old)
        if not reason:
            return RestartResult(True, "", old, new)
        if clock() >= deadline:
            detail = f"сервис не вернулся в рабочее состояние за {READY_TIMEOUT_S} с: {reason}"
            return RestartResult(False, detail, old, new)
        sleep(POLL_INTERVAL_S)


def _short(commit: str) -> str:
    return commit[:SHORT_HASH_LEN]


def build_rollback_report(
    head: str,
    previous_head: str | None,
    backup_path: Path | None,
    failed_rows: Sequence[CheckResult],
) -> str:
    """Отчёт о сбое выкатки и команды отката. Команды только печатаются, скрипт их не исполняет (D-12)."""
    core = shlex.quote(str(CORE_DIR))
    db = shlex.quote(str(LIVE_DB))
    previous = _short(previous_head) if previous_head else "неизвестен"
    lines = ["ОТЧЁТ О СБОЕ ВЫКАТКИ", "", "Что упало:"]
    for row in failed_rows:
        lines.append(f"  - {redact(row.name)}")
        lines += [f"      {redact(detail_line)}" for detail_line in row.detail.splitlines()]
    lines += [
        "",
        f"Выкатывался коммит {_short(head)}; родитель этого коммита: {previous}.",
        "",
        "Команды отката (скрипт их НЕ выполняет; каждая требует разрешения владельца):",
    ]
    steps: list[tuple[str, str]] = [
        (
            f"git -C {core} revert --no-edit {_short(head)}",
            f"откат кода новым коммитом; если выкатка включала несколько коммитов, укажите диапазон сами "
            f"(родитель: {previous})",
        )
    ]
    if backup_path is not None:
        backup = shlex.quote(str(backup_path))
        steps += [
            (f"systemctl stop {SERVICE_NAME}", "остановить сервис перед заменой БД"),
            (
                f"cp -p {backup} {db}",
                "ВНИМАНИЕ: восстановление из копии затрёт данные, появившиеся после выкатки",
            ),
            (
                f"rm -f {db}-wal {db}-shm",
                "убрать sidecar-файлы прежней БД, если остались (копия самодостаточна)",
            ),
            (f"systemctl start {SERVICE_NAME}", "запустить сервис на откаченном коде и восстановленной БД"),
        ]
    else:
        steps.append((f"systemctl restart {SERVICE_NAME}", "применить откаченный код"))
    for number, (command, note) in enumerate(steps, start=1):
        lines += [f"  {number}. {command}", f"       {note}"]
    if backup_path is None:
        lines += ["", "Откат БД невозможен: резервной копии не было (выкатка без --backup)."]
    lines += ["", "Автоотката нет: откат требует нового разрешения владельца."]
    return "\n".join(lines)


# --------------------------------------------------------------------------- CLI


def _nonneg_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("нужно целое число секунд") from exc
    if number < 0:
        raise argparse.ArgumentTypeError("число секунд не может быть отрицательным")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deploy.py",
        description=(
            "Смоук сервиса assistant-worker. Без флагов выполняется только чтение: автоматическая часть, "
            "сервис не меняется; фазы подтверждения /help работают по файлу состояния. "
            "Изменяющие действия только по флагам --backup и --restart."
        ),
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=STATE_FILE_DEFAULT,
        help=f"файл состояния смоука вне репозитория (по умолчанию {STATE_FILE_DEFAULT})",
    )
    parser.add_argument(
        "--report",
        type=Path,
        metavar="PATH",
        help="записать markdown-отчёт в PATH (каталог должен существовать, не внутри .git)",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help=(
            "сделать резервную копию боевой БД (backup API, источник mode=ro) вне дерева git, "
            "права 0600 в каталоге 0700; без других флагов больше ничего не делает"
        ),
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help=(
            "перезапустить assistant-worker, дождаться новой инвокации и polling, повторить смоук; "
            "только по разрешению владельца; при красном исходе откат лишь печатается"
        ),
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=BACKUP_DIR_DEFAULT,
        metavar="PATH",
        help=f"каталог резервных копий, только с --backup (по умолчанию {BACKUP_DIR_DEFAULT})",
    )
    phase = parser.add_mutually_exclusive_group()
    phase.add_argument(
        "--await-help",
        action="store_true",
        help="ждать в журнале обработанное обновление после метки смоука (отправьте боту /help)",
    )
    phase.add_argument(
        "--confirm-help",
        choices=("yes", "no"),
        help="записать ответ владельца на /help (ответ Claude получает опросом в чате)",
    )
    parser.add_argument(
        "--await-timeout",
        type=_nonneg_int,
        default=DEFAULT_AWAIT_TIMEOUT_S,
        metavar="SECONDS",
        help=f"дедлайн для --await-help (по умолчанию {DEFAULT_AWAIT_TIMEOUT_S} с)",
    )
    return parser


def _instruction(state_file: Path) -> str:
    suffix = "" if state_file == STATE_FILE_DEFAULT else f" --state-file {shlex.quote(str(state_file))}"
    return "\n".join(
        [
            "Автоматическая часть зелёная. Дальше фазы без TTY (D-09):",
            "  1. Отправьте боту команду /help.",
            f"  2. Выполните: python3 scripts/deploy.py --await-help{suffix}",
            "  3. Claude спросит владельца в чате опросом, пришёл ли ответ, и выполнит:",
            f"     python3 scripts/deploy.py --confirm-help yes{suffix}   (или no)",
            "Подтверждение «ответ пришёл?» Claude получает опросом в чате, а не вводом в терминале.",
        ]
    )


def _write_report(
    path: Path, state: dict, runner: Runner, clock: Callable[[], datetime]
) -> int:
    try:
        _write_private(path, render_report_md(state, get_head(runner), clock()))
    except OSError as exc:
        print(f"Не удалось записать отчёт: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(f"Отчёт записан: {path}")
    return 0


def _run_phase(
    args: argparse.Namespace,
    runner: Runner,
    clock: Callable[[], datetime],
    sleep: Callable[[float], None],
    report_path: Path | None,
) -> int:
    try:
        state = load_state(args.state_file)
        ensure_same_invocation(state, runner)
        if args.await_help:
            handled = await_help(state, runner, sleep, clock, args.await_timeout)
            state["help_handled"] = handled
            if handled:
                print("Обновление после метки смоука: обработано ботом.")
            else:
                print(f"Обновление после метки смоука не получено за {args.await_timeout} с.")
        else:
            state = confirm_help(state, args.confirm_help, runner)
    except StateError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except CommandError as exc:
        print(f"Смоук прерван: {exc}")
        return 1
    try:
        save_state(args.state_file, state)
    except OSError as exc:
        print(f"Не удалось сохранить файл состояния: {type(exc).__name__}", file=sys.stderr)
        return 2

    verdict = final_verdict(state)
    if args.confirm_help:
        print(f"ИТОГ СМОУКА: {verdict}")
        if verdict != "ЗЕЛЁНЫЙ":
            for reason in verdict_reasons(state):
                print(f"  ↳ {reason}")
    elif state["help_handled"]:
        print("Дальше Claude спросит владельца, пришёл ли ответ, и выполнит --confirm-help.")
    rc = 0
    if report_path is not None:
        rc = _write_report(report_path, state, runner, clock)
    if rc:
        return rc
    if args.await_help:
        return 0 if state["help_handled"] else 1
    return 0 if verdict == "ЗЕЛЁНЫЙ" else 1


def _make_backup(args: argparse.Namespace, clock: Callable[[], datetime], live_db: Path) -> Path | None:
    """Резервная копия по --backup. Печатает путь и размер, но не содержимое; None при сбое."""
    try:
        copy_path = make_db_copy(live_db, args.backup_dir, clock())
        size = copy_path.stat().st_size
    except Exception as exc:  # noqa: BLE001 - граница ввода-вывода: наружу только имя класса
        print(f"Резервная копия не создана: {type(exc).__name__}")
        return None
    print(f"Резервная копия создана: {copy_path} ({size} байт); содержимое не печатается.")
    return copy_path


def _run_backup(args: argparse.Namespace, clock: Callable[[], datetime], live_db: Path) -> int:
    """Режим «только копия»: раннер, systemd и журнал не используются."""
    return 0 if _make_backup(args, clock, live_db) is not None else 1


def _run_restart(
    args: argparse.Namespace,
    runner: Runner,
    clock: Callable[[], datetime],
    sleep: Callable[[float], None],
    opener: Opener,
    env_path: Path,
    main_py_path: Path,
    report_path: Path | None,
    live_db: Path,
) -> int:
    """Выкатка по ``--restart``: дерево, [копия], рестарт, ожидание, смоук; при красном - отчёт.

    Порядок фиксирован (D-10, D-11, D-12). Откат здесь не выполняется никогда: после отчёта
    раннер не получает ни одной команды.
    """
    try:
        dirty = git_dirty_paths(runner)
    except CommandError as exc:
        print(f"Рестарт отменён: не удалось проверить дерево git ({exc}). Сервис не тронут.")
        return 2
    if dirty:
        print("Рестарт отменён: дерево git не чистое вне .planning/. Сервис не тронут.")
        print("Пути с изменениями (содержимое не печатается):")
        for path in dirty[:MAX_LISTED_PATHS]:
            print(f"  - {path}")
        if len(dirty) > MAX_LISTED_PATHS:
            print(f"  … и ещё {len(dirty) - MAX_LISTED_PATHS}")
        return 2
    head = get_head(runner)
    if head is None:
        print("Рестарт отменён: не удалось определить HEAD (git rev-parse HEAD). Сервис не тронут.")
        return 2
    previous_head = get_parent_head(runner)

    backup_path: Path | None = None
    if args.backup:
        backup_path = _make_backup(args, clock, live_db)
        if backup_path is None:
            print("Выкатка остановлена до рестарта: сервис не тронут.")
            return 1

    result = restart_service(runner, sleep, clock)
    if result.ok:
        print(f"Сервис перезапущен. Ожидание окна старта {STARTUP_TAIL_SECONDS} с перед смоуком.")
        sleep(STARTUP_TAIL_SECONDS)
        smoke = run_smoke(runner, opener=opener, env_path=env_path, main_py_path=main_py_path)
        restart_row = CheckResult("рестарт: новая инвокация active, polling запущен", True)
        smoke = replace(smoke, rows=[restart_row, *smoke.rows])
    else:
        failed = CheckResult("рестарт: сервис вернулся в рабочее состояние", False, result.detail)
        smoke = SmokeResult([failed], [], [], result.new_invocation, [])

    print(render_table(smoke.rows, smoke.warnings))
    state = build_state(smoke, clock())
    try:
        save_state(args.state_file, state)
    except OSError as exc:
        print(f"Не удалось сохранить файл состояния: {type(exc).__name__}", file=sys.stderr)
        return 2
    green = auto_ok(smoke.rows)
    if green:
        print(_instruction(args.state_file))
    print(f"ИТОГ СМОУКА: {final_verdict(state)}")
    # Отчёт --report пишется ДО печати отчёта об откате: после него раннер молчит.
    report_failed = report_path is not None and _write_report(report_path, state, runner, clock) != 0
    if green:
        return 2 if report_failed else 0
    failed_rows = [row for row in smoke.rows if not row.ok]
    print()
    print(build_rollback_report(head, previous_head, backup_path, failed_rows))
    return 1


def main(
    argv: Sequence[str] | None = None,
    runner: Runner = run_cmd,
    now: Callable[[], datetime] | None = None,
    opener: Opener | None = None,
    env_path: Path | None = None,
    main_py_path: Path | None = None,
    sleep: Callable[[float], None] | None = None,
    live_db: Path | None = None,
) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    clock = now or (lambda: datetime.now(timezone.utc))
    sleep_fn = sleep or time.sleep

    if args.backup_dir != BACKUP_DIR_DEFAULT and not args.backup:
        print("--backup-dir имеет смысл только вместе с --backup", file=sys.stderr)
        return 2

    if (args.await_help or args.confirm_help) and (args.backup or args.restart):
        print(
            "--backup и --restart нельзя сочетать с фазами --await-help и --confirm-help",
            file=sys.stderr,
        )
        return 2

    report_path: Path | None = None
    if args.report is not None:
        try:
            report_path = validate_report_path(args.report)
        except ValueError as exc:
            print(f"Отчёт: {exc}", file=sys.stderr)
            return 2

    if args.await_help or args.confirm_help:
        return _run_phase(args, runner, clock, sleep_fn, report_path)

    if args.restart:
        return _run_restart(
            args,
            runner,
            clock,
            sleep_fn,
            opener or urllib.request.urlopen,
            env_path or ENV_FILE_DEFAULT,
            main_py_path or MAIN_PY_DEFAULT,
            report_path,
            live_db or LIVE_DB,
        )

    if args.backup:
        return _run_backup(args, clock, live_db or LIVE_DB)

    result = run_smoke(
        runner,
        opener=opener or urllib.request.urlopen,
        env_path=env_path or ENV_FILE_DEFAULT,
        main_py_path=main_py_path or MAIN_PY_DEFAULT,
    )
    print(render_table(result.rows, result.warnings))
    state = build_state(result, clock())
    try:
        save_state(args.state_file, state)
    except OSError as exc:
        print(f"Не удалось сохранить файл состояния: {type(exc).__name__}", file=sys.stderr)
        return 2
    green = auto_ok(result.rows)
    if green:
        print(_instruction(args.state_file))
    print(f"ИТОГ СМОУКА: {final_verdict(state)}")
    if report_path is not None and _write_report(report_path, state, runner, clock):
        return 2
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
