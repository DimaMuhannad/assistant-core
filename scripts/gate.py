#!/usr/bin/env python3
"""Локальный гейт качества assistant-core: одна команда -> честный итог «ЗЕЛЁНЫЙ» / «КРАСНЫЙ».

Запуск (из /opt/assistant-core):  python3 scripts/gate.py
Только стандартная библиотека Python, запускается любым python3.

Гейт не обрывается на первой ошибке: сбой шага превращается в красную строку,
остальные строки всё равно печатаются. Прогон с 0 собранных тестов, с
пропущенными, xfail/xpass или deselected тестами считается красным.
Гейт не читает .env, credentials.json, token.json, *.session и не трогает
systemd-сервисы на запись.

Образец: /opt/chat-app/scripts/gate.py (только для чтения). Этот файл от chat-app
не зависит.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[1]
SHARED_DIR = Path(os.environ.get("ASSISTANT_SHARED_DIR", "/opt/assistant-shared"))
CHAT_APP_DIR = Path(os.environ.get("ASSISTANT_CHAT_APP_DIR", "/opt/chat-app"))
LIVE_DB = CORE_DIR / "data" / "assistant.db"
CORE_VENV_BIN = CORE_DIR / ".venv" / "bin"
# Копии общих тестовых файлов в chat-app: только чтение, для сверки дрейфа (D-16).
CHAT_PERSONA = CHAT_APP_DIR / "backend" / "tests" / "synthetic_persona.py"
CORE_PERSONA = CORE_DIR / "tests" / "synthetic_persona.py"
CHAT_TOKENS = CHAT_APP_DIR / "backend" / "tests" / "persona_tokens.py"
CORE_TOKENS = CORE_DIR / "tests" / "persona_tokens.py"
PYTEST_TIMEOUT_S = 900
LINT_TIMEOUT_S = 300
SHIELD_TIMEOUT_S = 300
# Пауза между двумя замерами «тихого окна» при подозрении на запись живого сервиса (решение
# владельца 2026-10-09): константа, повтор один и без цикла.
REMEASURE_WAIT_S = 5

REPO_CORE = "assistant-core"
REPO_SHARED = "assistant-shared"

# Известные ложные срабатывания эвристик shield (решение D-17). Записи только удаляются:
# новая запись не добавляется, устаревшая запись (находки больше нет) краснит гейт, чтобы
# исключение не пережило причину. Ключ: (путь в posix, вид находки) -> число находок; без
# номеров строк и без текста ключевых слов. Для assistant-shared список пуст; chat-app
# в словаре нет: его shield гоняет собственный гейт.
KNOWN_SHIELD_FALSE_POSITIVES: dict[str, dict[tuple[str, str], int]] = {
    REPO_CORE: {
        ("config/persona.yaml", "nda-keyword"): 3,
    },
    REPO_SHARED: {},
}

_SUMMARY_WORDS = frozenset(
    {"failed", "error", "errors", "skipped", "deselected", "xfailed", "xpassed"}
)


@dataclass(frozen=True)
class CheckResult:
    repo: str
    name: str
    ok: bool
    detail: str = ""
    info: str = ""


def run_cmd(
    cmd: list[str],
    cwd: Path,
    env_extra: dict[str, str] | None = None,
    timeout: int = PYTEST_TIMEOUT_S,
) -> subprocess.CompletedProcess:
    """Запуск подпроцесса: список аргументов, без shell, с таймаутом."""
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        shell=False,
        timeout=timeout,
    )


def _exc_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def sha256_file(path: Path) -> str:
    """SHA-256 файла, чтение блоками."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def core_pytest_env(db_override: Path) -> dict[str, str]:
    """Окружение для pytest assistant-core: БД строго во временный файл, набор не сужается.

    ASSISTANT_DB_PATH_OVERRIDE читает src/config.py (до load_dotenv), поэтому тесты, которым
    нужна БД, не доберутся до боевой. Пустой PYTEST_ADDOPTS не даёт окружению сузить набор
    тестов. Путь на боевую БД, на корневой assistant.db (с sidecar-файлами) или внутрь
    каталога data отвергается (T-01-03).
    """
    resolved = db_override.resolve()
    data_dir = (CORE_DIR / "data").resolve()
    forbidden = {LIVE_DB.resolve(), (CORE_DIR / "assistant.db").resolve()}
    if resolved in forbidden or resolved == data_dir or data_dir in resolved.parents:
        raise ValueError(f"ASSISTANT_DB_PATH_OVERRIDE не может указывать на боевую БД: {db_override}")
    if resolved.parent == CORE_DIR.resolve() and resolved.name.startswith("assistant.db"):
        raise ValueError(f"ASSISTANT_DB_PATH_OVERRIDE не может указывать на боевую БД: {db_override}")
    return {"ASSISTANT_DB_PATH_OVERRIDE": str(db_override), "PYTEST_ADDOPTS": ""}


def shared_pytest_env() -> dict[str, str]:
    """Окружение для pytest assistant-shared: набор не сужается, подмены БД нет.

    Тесты shared работают на временных БД и сами боевую БД не знают; пустой PYTEST_ADDOPTS
    не даёт окружению вызывающего сузить набор тестов (T-01-14).
    """
    return {"PYTEST_ADDOPTS": ""}


def _testsuites(junit_xml: Path) -> list[ET.Element]:
    root = ET.parse(junit_xml).getroot()
    if root.tag == "testsuite":
        return [root]
    suites = root.findall("testsuite")
    if not suites:
        raise ValueError("в junit XML нет элемента testsuite")
    return suites


def pytest_counts(junit_xml: Path) -> dict[str, int]:
    """Счётчики tests/failures/errors/skipped из junit XML (корень testsuites или testsuite)."""
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in _testsuites(junit_xml):
        for key in counts:
            counts[key] += int(suite.get(key, 0))
    return counts


def failed_test_ids(junit_xml: Path, limit: int = 10) -> list[str]:
    """«classname::name» первых упавших/ошибочных тестов."""
    ids: list[str] = []
    root = ET.parse(junit_xml).getroot()
    for case in root.iter("testcase"):
        if case.find("failure") is not None or case.find("error") is not None:
            ids.append(f"{case.get('classname', '')}::{case.get('name', '')}")
            if len(ids) >= limit:
                break
    return ids


def _last_summary_line(output: str) -> str:
    last = ""
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("=") and " in " in stripped:
            last = stripped
    return last


def pytest_summary_flags(output: str) -> list[str]:
    """Слова из итоговой строки pytest, которые означают «не чисто» (skip/xfail/deselect/ошибки)."""
    line = _last_summary_line(output)
    if not line:
        return []
    tokens = "".join(ch if ch.isalpha() else " " for ch in line).split()
    return sorted({t for t in tokens if t in _SUMMARY_WORDS})


def pytest_ok(returncode: int, counts: dict[str, int], flags: list[str]) -> bool:
    """Зелёный только при коде 0, ненулевом числе тестов и без failed/error/skipped/flags."""
    return (
        returncode == 0
        and counts.get("tests", 0) > 0
        and counts.get("failures", 0) == 0
        and counts.get("errors", 0) == 0
        and counts.get("skipped", 0) == 0
        and not flags
    )


def _git_head(cwd: Path) -> str:
    try:
        proc = run_cmd(["git", "-C", str(cwd), "rev-parse", "HEAD"], cwd, timeout=30)
    except Exception:
        return "неизвестен"
    head = proc.stdout.strip()
    return head if proc.returncode == 0 and head else "неизвестен"


def _write_snapshot(
    save_dir: Path,
    repo: str,
    cmd: list[str],
    env_extra: dict[str, str] | None,
    cwd: Path,
    tmp_dir: Path,
    stdout: str,
) -> None:
    """Снимок сырого вывода pytest -v (только pytest: вывод shield не сохраняется никогда)."""
    parts = [f"{key}={value}" for key, value in (env_extra or {}).items()] + cmd
    command = " ".join(parts).replace(str(tmp_dir), "временный каталог")
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    header = f"# Команда: {command}\n# Коммит: {_git_head(cwd)}\n# Дата: {stamp}\n"
    save_dir.mkdir(parents=True, exist_ok=True)
    (save_dir / f"pytest-{repo}.txt").write_text(header + stdout, encoding="utf-8")


def run_pytest_step(
    repo: str,
    pytest_bin: Path,
    target: str,
    cwd: Path,
    env_extra: dict[str, str] | None,
    tmp_dir: Path,
    save_dir: Path | None,
) -> CheckResult:
    """Один запуск pytest -> CheckResult. Команда без фильтров набора тестов: набор не сужается."""
    name = "pytest — тестов: 0"
    if not pytest_bin.is_file():
        return CheckResult(repo, name, False, f"не найден pytest: {pytest_bin}")
    if not cwd.is_dir():
        return CheckResult(repo, name, False, f"нет каталога репозитория: {cwd}")
    junit = tmp_dir / f"junit-{repo}.xml"
    cmd = [
        str(pytest_bin),
        target,
        "-v",
        "-p",
        "no:cacheprovider",
        "-o",
        "xfail_strict=true",
        f"--junitxml={junit}",
        f"--basetemp={tmp_dir}/pytest-{repo}",
    ]
    try:
        proc = run_cmd(cmd, cwd, env_extra)
    except subprocess.TimeoutExpired:
        return CheckResult(repo, name, False, "превышено время выполнения pytest")
    if save_dir is not None:
        _write_snapshot(save_dir, repo, cmd, env_extra, cwd, tmp_dir, proc.stdout)
    try:
        counts = pytest_counts(junit)
        failed = failed_test_ids(junit)
    except (OSError, ET.ParseError, ValueError):
        counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
        failed = []
    flags = pytest_summary_flags(proc.stdout)
    name = f"pytest — тестов: {counts['tests']}"
    if pytest_ok(proc.returncode, counts, flags):
        return CheckResult(repo, name, True)
    lines = [_last_summary_line(proc.stdout) or f"код возврата pytest: {proc.returncode}"]
    if counts["tests"] == 0:
        lines.append("не собрано ни одного теста")
    lines.extend(f"упал: {test_id}" for test_id in failed)
    return CheckResult(repo, name, False, "\n".join(lines))


def run_lint_imports_step(
    repo: str,
    lint_bin: Path,
    cwd: Path,
    env_extra: dict[str, str] | None,
) -> CheckResult:
    """Один запуск lint-imports (контракт .importlinter репозитория) -> CheckResult.

    --no-cache: кэш import-linter не должен появляться в дереве репозитория.
    """
    name = "import-linter"
    if not lint_bin.is_file():
        return CheckResult(repo, name, False, "не установлен import-linter — см. requirements-dev.txt")
    if not cwd.is_dir():
        return CheckResult(repo, name, False, f"нет каталога репозитория: {cwd}")
    try:
        proc = run_cmd(
            [str(lint_bin), "--no-logo", "--no-cache"], cwd, env_extra, timeout=LINT_TIMEOUT_S
        )
    except subprocess.TimeoutExpired:
        return CheckResult(repo, name, False, "превышено время выполнения lint-imports")
    if proc.returncode == 0:
        return CheckResult(repo, name, True)
    output = proc.stdout + "\n" + proc.stderr
    lines = [line.strip() for line in output.splitlines() if "BROKEN" in line or "->" in line]
    if not lines:
        lines = [f"код возврата lint-imports: {proc.returncode}"]
    return CheckResult(repo, name, False, "\n".join(lines[:10]))


_SHIELD_LINE_RE = re.compile(r"^\s+\U0001F6A8 (?P<body>.*)$")
_SHIELD_AT_LINE_RE = re.compile(r"^(?P<path>.+?):(?P<line>\d+) - (?P<msg>.*)$")
_SHIELD_SCANNED_RE = re.compile(r"Scanning (?P<n>\d+) files")
_SHIELD_MAX_DETAIL = 15


def _relative_posix(raw_path: str, repo_dir: Path) -> str:
    """Путь относительно repo_dir в posix; вне репозитория остаётся как есть."""
    try:
        return Path(raw_path).relative_to(repo_dir).as_posix()
    except ValueError:
        return raw_path


def parse_shield_findings(output: str, repo_dir: Path) -> collections.Counter:
    """Нормализует вывод shield в Counter {(путь, вид): число}.

    Рассматриваются ТОЛЬКО строки находок («пробелы, значок, пробел, тело»). Заголовок shield
    (адрес remote, e-mail автора), текст NDA-слов и номера строк отбрасываются и не попадают
    в результат: гейт ничего из этого не печатает и не сохраняет (T-01-09).
    """
    found: collections.Counter = collections.Counter()
    for line in output.splitlines():
        match = _SHIELD_LINE_RE.match(line)
        if not match:
            continue
        body = match.group("body").strip()
        if body.startswith("Forbidden file pattern committed:"):
            name = body.split(":", 1)[1].strip()
            found[(name, "forbidden-file")] += 1
            continue
        if body.startswith("CRITICAL"):
            found[("(remote)", "remote")] += 1
            continue
        at_line = _SHIELD_AT_LINE_RE.match(body)
        if at_line:
            path = _relative_posix(at_line.group("path"), repo_dir)
            msg = at_line.group("msg")
            if msg.startswith("Found potential "):
                found[(path, "secret:" + msg[len("Found potential ") :].strip())] += 1
                continue
            if msg.startswith("Found proprietary corporate keyword"):
                found[(path, "nda-keyword")] += 1
                continue
        read_error = body.split(" - Read error", 1)
        if len(read_error) == 2:
            found[(_relative_posix(read_error[0].strip(), repo_dir), "read-error")] += 1
            continue
        found[("(нераспознано)", "unparsed")] += 1
    return found


def compare_shield_findings(
    found: collections.Counter, allowed: dict[tuple[str, str], int]
) -> tuple[list[str], list[str]]:
    """(новые находки, устаревшие записи замороженного списка), оба списка отсортированы."""
    new = [
        f"новая находка: {path} [{kind}] ×{count}"
        for (path, kind), count in sorted(found.items())
        if count > allowed.get((path, kind), 0)
    ]
    stale = [
        f"устаревшая запись (удалите из KNOWN_SHIELD_FALSE_POSITIVES): {path} [{kind}]"
        for (path, kind), count in sorted(allowed.items())
        if found.get((path, kind), 0) < count
    ]
    return new, stale


def run_shield_step(repo: str, repo_dir: Path) -> CheckResult:
    """Один запуск scripts/security_shield.py репозитория (режим --all) -> CheckResult.

    detail содержит только строки «новая находка»/«устаревшая запись» или причину сбоя,
    никогда сырой вывод shield. Интерпретатор для обоих репозиториев берётся из .venv core
    (D-03), при его отсутствии используется текущий.
    """
    name = "security_shield (--all)"
    script = repo_dir / "scripts" / "security_shield.py"
    if not script.is_file():
        return CheckResult(repo, name, False, f"не найден scripts/security_shield.py: {script}")
    if not repo_dir.is_dir():
        return CheckResult(repo, name, False, f"нет каталога репозитория: {repo_dir}")
    python_bin = CORE_VENV_BIN / "python"
    if not python_bin.is_file():
        python_bin = Path(sys.executable)
    cmd = [str(python_bin), str(script), str(repo_dir), "--all"]
    try:
        proc = run_cmd(cmd, repo_dir, timeout=SHIELD_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return CheckResult(repo, name, False, "превышено время выполнения security_shield")
    if proc.returncode not in (0, 1):
        return CheckResult(
            repo, name, False, f"сбой security_shield: код возврата {proc.returncode}"
        )
    found = parse_shield_findings(proc.stdout, repo_dir)
    if proc.returncode == 1 and not found:
        return CheckResult(repo, name, False, "сбой security_shield: код 1 без распознанных находок")
    scanned = _SHIELD_SCANNED_RE.search(proc.stdout)
    if not scanned or int(scanned.group("n")) == 0:
        return CheckResult(repo, name, False, "security_shield ничего не просканировал")
    new, stale = compare_shield_findings(found, KNOWN_SHIELD_FALSE_POSITIVES.get(repo, {}))
    problems = new + stale
    if problems:
        return CheckResult(repo, name, False, "\n".join(problems[:_SHIELD_MAX_DETAIL]))
    return CheckResult(repo, name, True)


def db_content_hash(db: Path) -> str:
    """SHA-256 логического содержимого БД (дамп схемы и данных, соединение только на чтение).

    Хеш файла ненадёжен в режиме WAL: записи лежат в -wal, а checkpoint меняет основной файл
    без изменения данных. Дамп в одной транзакции от этого не зависит. Единственное обращение
    гейта к боевой БД: чтение для хеша, запись исключена режимом mode=ro.
    """
    conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    try:
        conn.execute("BEGIN")
        digest = hashlib.sha256()
        for line in conn.iterdump():
            digest.update(line.encode("utf-8", "surrogatepass"))
            digest.update(b"\n")
        return digest.hexdigest()
    finally:
        conn.close()


def _sha_or_none(path: Path) -> str | None:
    try:
        return db_content_hash(path)
    except (OSError, sqlite3.Error):
        return None


def _service_state() -> str:
    """Состояние assistant-worker: только чтение (``systemctl is-active``), сервис не меняется."""
    try:
        proc = run_cmd(["systemctl", "is-active", "assistant-worker"], CORE_DIR, timeout=10)
        return proc.stdout.strip() or "неизвестно"
    except Exception:
        return "неизвестно"


def _iso_utc(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).replace(microsecond=0).isoformat()


def _db_diagnostics() -> str:
    """Короткая диагностика при расхождении хеша: состояние сервиса и время изменения БД.

    Вердикт диагностика не смягчает, она лишь помогает отличить запись живого сервиса от
    ошибки теста.
    """
    state = _service_state()
    try:
        mtime = _iso_utc(LIVE_DB.stat().st_mtime)
    except OSError:
        mtime = "неизвестно"
    return f"сервис assistant-worker: {state}; время изменения БД (UTC): {mtime}"


def _db_latest_mtime() -> float | None:
    """Самое позднее время изменения файла БД или её -wal (запись в WAL не трогает основной файл)."""
    stamps = []
    for path in (LIVE_DB, LIVE_DB.with_name(LIVE_DB.name + "-wal")):
        try:
            stamps.append(path.stat().st_mtime)
        except OSError:
            continue
    return max(stamps) if stamps else None


def service_write_evidence(window: tuple[float, float]) -> tuple[bool, str]:
    """Согласуется ли расхождение хеша с записью живого сервиса: (да/нет, пояснение).

    «Да» только если assistant-worker активен И время изменения БД лежит внутри окна измерения
    [начало «до»; конец «после»]. Любая неизвестность («неизвестно», нет файла) означает «нет».
    """
    state = _service_state()
    mtime = _db_latest_mtime()
    start, end = window
    inside = mtime is not None and start <= mtime <= end
    stamp = _iso_utc(mtime) if mtime is not None else "неизвестно"
    text = (
        f"сервис assistant-worker: {state}; время изменения БД (UTC): {stamp}; "
        f"окно измерения (UTC): {_iso_utc(start)} .. {_iso_utc(end)}"
    )
    return state == "active" and inside, text


def quiet_remeasure() -> tuple[str | None, str | None]:
    """Два замера хеша боевой БД через постоянную паузу REMEASURE_WAIT_S (тихое окно)."""
    first = _sha_or_none(LIVE_DB)
    time.sleep(REMEASURE_WAIT_S)
    second = _sha_or_none(LIVE_DB)
    return first, second


def db_unchanged_check(
    before: str | None,
    after: str | None,
    diagnostics_fn=None,
    window: tuple[float, float] | None = None,
    evidence_fn=None,
    remeasure_fn=None,
) -> CheckResult:
    """Хеш боевой БД до и сразу после pytest core: расхождение краснит итог.

    Единственное смягчение (решение владельца 2026-10-09): если хеши различаются, а
    ``service_write_evidence`` говорит, что живой assistant-worker активен и писал в БД внутри
    окна измерения, делается ОДИН повторный замер в тихом окне (две пробы через
    REMEASURE_WAIT_S). Совпали обе - строка зелёная с явной пометкой в info. Не совпали,
    сервис не активен, время изменения вне окна, окна нет или любой хеш None - КРАСНЫЙ, как
    раньше. Основная защита от записи тестов в боевую БД - страж tests/live_db_guard.py.
    """
    name = "боевая assistant.db не изменена"
    if before is None or after is None:
        return CheckResult(REPO_CORE, name, False, "не удалось вычислить хеш боевой БД")
    if before == after:
        return CheckResult(REPO_CORE, name, True, info=f"SHA-256 до/после совпали: {before[:12]}")
    retry_note = ""
    if window is not None:
        try:
            consistent, evidence = (evidence_fn or service_write_evidence)(window)
        except Exception:
            consistent, evidence = False, "диагностика недоступна"
        if consistent:
            try:
                first, second = (remeasure_fn or quiet_remeasure)()
            except Exception:
                first = second = None
            if first is not None and first == second:
                info = (
                    f"обнаружена запись сервиса assistant-worker в окне прогона ({evidence})\n"
                    "SHA-256 до/после не совпали; повторное измерение в тихом окне "
                    f"({REMEASURE_WAIT_S} с) дало совпадение двух замеров: {first[:12]}"
                )
                return CheckResult(REPO_CORE, name, True, info=info)
            retry_note = (
                "повторное измерение в тихом окне тоже не подтвердило неизменность "
                f"(пауза {REMEASURE_WAIT_S} с)\n"
            )
    try:
        diagnostics = (diagnostics_fn or _db_diagnostics)()
    except Exception:
        diagnostics = "диагностика недоступна"
    detail = (
        "хеш боевой БД изменился во время pytest assistant-core\n"
        f"{diagnostics}\n"
        f"{retry_note}"
        "повторите прогон; основная защита тестов это страж tests/live_db_guard.py"
    )
    return CheckResult(REPO_CORE, name, False, detail)


def _rel_to(path: Path, base: Path) -> str:
    """Путь относительно корня; вне него - как есть."""
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def persona_drift_check(chat_copy: Path, core_copy: Path, name: str) -> CheckResult:
    """Две копии общего тестового файла (chat-app и assistant-core) совпадают побайтно.

    Копия chat-app только читается. Отсутствие любого файла - красный (D-16, fail-closed).
    """
    for path in (chat_copy, core_copy):
        if not path.is_file():
            return CheckResult(REPO_CORE, name, False, f"нет файла: {path}")
    try:
        same = sha256_file(chat_copy) == sha256_file(core_copy)
    except OSError as exc:
        return CheckResult(REPO_CORE, name, False, f"не удалось прочитать копии: {_exc_text(exc)}")
    if not same:
        return CheckResult(
            REPO_CORE,
            name,
            False,
            f"копии различаются — синхронизируйте {_rel_to(chat_copy, CHAT_APP_DIR)} "
            f"в chat-app и {_rel_to(core_copy, CORE_DIR)} в assistant-core",
        )
    return CheckResult(REPO_CORE, name, True)


def hook_installed_check(repo: str, repo_dir: Path) -> CheckResult:
    """pre-commit hook репозитория установлен: core.hooksPath = .githooks и файл исполняемый (D-04).

    Любой сбой (нет каталога, нет git, таймаут) даёт красную строку, а не исключение.
    """
    name = "pre-commit hook установлен"
    advice = "выполните scripts/install_hooks.sh в репозитории"
    try:
        if not repo_dir.is_dir():
            return CheckResult(repo, name, False, f"нет каталога репозитория: {repo_dir}\n{advice}")
        proc = run_cmd(
            ["git", "-C", str(repo_dir), "config", "--get", "core.hooksPath"], repo_dir, timeout=30
        )
        configured = proc.stdout.strip()
        if proc.returncode != 0 or not configured:
            return CheckResult(repo, name, False, f"core.hooksPath не задан\n{advice}")
        if configured != ".githooks":
            return CheckResult(
                repo, name, False, f"core.hooksPath = {configured}, ожидается .githooks\n{advice}"
            )
        hook = repo_dir / ".githooks" / "pre-commit"
        if not hook.is_file():
            return CheckResult(repo, name, False, f"нет файла .githooks/pre-commit\n{advice}")
        if not os.access(hook, os.X_OK):
            return CheckResult(repo, name, False, f".githooks/pre-commit не исполняемый\n{advice}")
    except Exception as exc:  # нет git, таймаут, ошибка ОС - красная строка (fail-closed)
        return CheckResult(
            repo, name, False, f"не удалось проверить hook: {_exc_text(exc)}\n{advice}"
        )
    return CheckResult(repo, name, True)


def overall_green(results: list[CheckResult]) -> bool:
    """Пустой список результатов - красный: гейт без проверок ничего не доказывает."""
    return bool(results) and all(result.ok for result in results)


def render_report(results: list[CheckResult]) -> str:
    """Таблица «Репозиторий | Проверка | Результат» с деталями и итоговой строкой."""
    rows = [("Репозиторий", "Проверка", "Результат")]
    rows += [(r.repo, r.name, "✓" if r.ok else "✗") for r in results]
    w_repo = max(len(row[0]) for row in rows) + 2
    w_name = max(len(row[1]) for row in rows) + 2
    lines = ["Гейт качества assistant-core и assistant-shared", ""]
    for index, row in enumerate(rows):
        lines.append(f"{row[0].ljust(w_repo)}{row[1].ljust(w_name)}{row[2]}")
        if index == 0:
            continue
        result = results[index - 1]
        if not result.ok:
            lines.extend(f"  ↳ {line}" for line in result.detail.splitlines())
        else:
            lines.extend(f"  · {line}" for line in result.info.splitlines())
    lines.append("")
    lines.append("ИТОГ: ЗЕЛЁНЫЙ" if overall_green(results) else "ИТОГ: КРАСНЫЙ")
    return "\n".join(lines)


def _safe_pytest_step(repo: str, **kwargs) -> CheckResult:
    try:
        return run_pytest_step(repo=repo, **kwargs)
    except Exception as exc:  # неожиданный сбой шага - красная строка, не трассировка
        return CheckResult(repo, "pytest — тестов: 0", False, f"сбой шага: {_exc_text(exc)}")


def _safe_shield_step(repo: str, repo_dir: Path) -> CheckResult:
    try:
        return run_shield_step(repo, repo_dir)
    except Exception as exc:  # неожиданный сбой шага - красная строка, не трассировка
        return CheckResult(repo, "security_shield (--all)", False, f"сбой шага: {_exc_text(exc)}")


def _safe_hook_step(repo: str, repo_dir: Path) -> CheckResult:
    try:
        return hook_installed_check(repo, repo_dir)
    except Exception as exc:  # неожиданный сбой шага - красная строка, не трассировка
        return CheckResult(repo, "pre-commit hook установлен", False, f"сбой шага: {_exc_text(exc)}")


def _safe_lint_step(repo: str, **kwargs) -> CheckResult:
    try:
        return run_lint_imports_step(repo=repo, **kwargs)
    except Exception as exc:  # неожиданный сбой шага - красная строка, не трассировка
        return CheckResult(repo, "import-linter", False, f"сбой шага: {_exc_text(exc)}")


def _run_all(save_dir: Path | None) -> list[CheckResult]:
    results: list[CheckResult] = []
    window_start = time.time()
    before = _sha_or_none(LIVE_DB)
    tmp_dir = Path(tempfile.mkdtemp(prefix="gate-"))
    try:
        results.append(
            _safe_pytest_step(
                REPO_CORE,
                pytest_bin=CORE_VENV_BIN / "pytest",
                target="tests",
                cwd=CORE_DIR,
                env_extra=core_pytest_env(tmp_dir / "gate-core-test.db"),
                tmp_dir=tmp_dir,
                save_dir=save_dir,
            )
        )
        # «После» измеряется СРАЗУ за pytest core: окно для записи живого сервиса минимально.
        after = _sha_or_none(LIVE_DB)
        window_end = time.time()
        results.append(db_unchanged_check(before, after, window=(window_start, window_end)))
        results.append(
            _safe_lint_step(
                REPO_CORE, lint_bin=CORE_VENV_BIN / "lint-imports", cwd=CORE_DIR, env_extra=None
            )
        )
        results.append(_safe_shield_step(REPO_CORE, CORE_DIR))
        results.append(
            persona_drift_check(CHAT_PERSONA, CORE_PERSONA, "синтетическая персона (дрейф SHA-256)")
        )
        results.append(
            persona_drift_check(CHAT_TOKENS, CORE_TOKENS, "токены персоны (дрейф SHA-256)")
        )
        results.append(_safe_hook_step(REPO_CORE, CORE_DIR))
        # assistant-shared: тесты интерпретатором core .venv (D-03), shield отдельной строкой (D-05)
        results.append(
            _safe_pytest_step(
                REPO_SHARED,
                pytest_bin=CORE_VENV_BIN / "pytest",
                target="tests",
                cwd=SHARED_DIR,
                env_extra=shared_pytest_env(),
                tmp_dir=tmp_dir,
                save_dir=save_dir,
            )
        )
        results.append(_safe_shield_step(REPO_SHARED, SHARED_DIR))
        results.append(_safe_hook_step(REPO_SHARED, SHARED_DIR))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Локальный гейт качества assistant-core.")
    parser.add_argument(
        "--save-pytest-output",
        metavar="DIR",
        help="сохранить сырой вывод pytest -v в DIR (снимок baseline; вывод shield не сохраняется)",
    )
    args = parser.parse_args(argv)
    save_dir = Path(args.save_pytest_output).resolve() if args.save_pytest_output else None
    try:
        results = _run_all(save_dir)
    except Exception as exc:
        results = [
            CheckResult(REPO_CORE, "работа гейта", False, f"внутренняя ошибка: {_exc_text(exc)}")
        ]
    print(render_report(results))
    return 0 if overall_green(results) else 1


if __name__ == "__main__":
    sys.exit(main())
