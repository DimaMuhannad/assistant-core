# Phase 1: Собственный гейт качества assistant-core - Pattern Map

**Mapped:** 2026-10-09
**Files analyzed:** 22 (новые и изменяемые)
**Analogs found:** 20 / 22

Все analog-пути проверены `git ls-files` в своих репозиториях (tracked). Зеркал `.gsd/capabilities` нет.
Репозитории: core = `/opt/assistant-core`, shared = `/opt/assistant-shared` (отдельный git), chat = `/opt/chat-app` (read-only, кроме одной правки адаптера через `/gsd-quick`).

## File Classification

| Новый/изменяемый файл | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| core `scripts/gate.py` | utility (CLI-оркестратор) | batch (подпроцессы -> таблица) | chat `scripts/gate.py` | exact (порт) |
| core `scripts/deploy.py` | utility (CLI ops) | request-response + batch (systemd/journal/HTTP) | chat `scripts/gate.py` (`run_cmd`, `make_db_copy`, `CheckResult`, `render_report`) | role-match |
| core `tests/conftest.py` (+страж audit-hook) | test-config | event-driven (audit events) | core `tests/conftest.py` (структура) + RESEARCH Pattern 1 | partial |
| core `tests/test_live_db_guard.py` | test | transform | chat `backend/tests/test_gate.py` (стиль юнитов) | role-match |
| core `src/config.py` (захват override до `load_dotenv`) | config | transform | сам файл, строки 1-16 | exact (правка) |
| core `src/connectors/gdrive/client.py` (`create_server_backup_archive` + параметр каталога) | service | file-I/O | сам файл, строки 184-216 | exact (правка) |
| core `tests/test_gdrive_client.py` (правка теста) | test | file-I/O | сам файл | exact (правка) |
| core `tests/test_command_aliases.py` (стабилизация порогов) | test | transform | сам файл (строки 30, 181, 213) | exact (правка) |
| core `tests/test_gate.py` | test | transform | chat `backend/tests/test_gate.py` | exact (порт) |
| core `tests/test_gate_red_cases.py` | test | batch (подпроцесс pytest в tmp) | chat `backend/tests/test_gate.py` + `test_pre_commit_hook.py` (tmp-репозитории) | role-match |
| core `tests/test_deploy_script.py` | test | request-response (фейковый раннер) | chat `backend/tests/test_gate.py` (загрузка модуля из `scripts/`) | role-match |
| core `docs/OPS_DEPLOY.md` | doc | - | `docs/` (allowlist сканера хардкода) | no code analog |
| core `CLAUDE.md` §3, `.claude/CLAUDE.md`, `.planning/codebase/TESTING.md`, `.planning/config.json` | config/doc | - | текущие строки про общий гейт | exact (правка) |
| shared `.githooks/pre-commit` | hook | request-response | core `.githooks/pre-commit` | exact (копия) |
| shared `scripts/install_hooks.sh` | utility | file-I/O (git config) | core `scripts/install_hooks.sh` | exact (копия) |
| shared `scripts/security_shield.py` | utility (CLI-обёртка) | request-response | core `scripts/security_shield.py` | exact (копия) |
| shared `pyproject.toml` (+pytest-секция) | config | - | core `pytest.ini` | role-match |
| shared `tests/test_migrations.py` | test | CRUD (SQLite tmp) | chat `backend/tests/test_migrations.py` | exact (порт) |
| shared `tests/test_hitl_shared.py` | test | CRUD/async | chat `backend/tests/test_hitl_shared.py` | exact (порт, anyio -> asyncio) |
| shared `tests/test_security_shared.py`, `test_shield_regressions.py`, `test_shield_parity.py` | test | transform | одноимённые файлы chat `backend/tests/` | exact (порт) |
| shared `tests/test_pre_commit_hook.py` | test | file-I/O (tmp git repo) | chat `backend/tests/test_pre_commit_hook.py` | exact (порт) |
| chat `scripts/agy_cross_ai.sh` (блок gate, через `/gsd-quick`) | utility | batch | сам файл | exact (правка) |

## Pattern Assignments

### core `scripts/gate.py` (utility, batch)

**Analog:** `/opt/chat-app/scripts/gate.py` (582 строки). Переносить почти построчно; заменить `CHAT_*`/`LIVE_DB` на `CORE_DIR`/`SHARED_DIR`, убрать строки chat-app, добавить строки shared и hook.

**Модульная шапка и константы** (chat gate.py:25-77): только stdlib; пути из env с дефолтом.
```python
from __future__ import annotations
import argparse, collections, hashlib, os, re, shutil, sqlite3, subprocess, sys, tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[1]          # в chat это CHAT_DIR
SHARED_DIR = Path(os.environ.get("ASSISTANT_SHARED_DIR", "/opt/assistant-shared"))
PYTEST_TIMEOUT_S = 900
KNOWN_SHIELD_FALSE_POSITIVES: dict[str, dict[tuple[str, str], int]] = {
    "assistant-core": {("config/persona.yaml", "nda-keyword"): 3},   # D-17, только удаляются
    "assistant-shared": {},                                           # D-17, начинается пустым
}
_SUMMARY_WORDS = frozenset({"failed","error","errors","skipped","deselected","xfailed","xpassed"})

@dataclass(frozen=True)
class CheckResult:
    repo: str
    name: str
    ok: bool
    detail: str = ""
```

**Запуск подпроцесса** (gate.py:116-134): список аргументов, `shell=False`, таймаут.
```python
def run_cmd(cmd, cwd, env_extra=None, timeout=PYTEST_TIMEOUT_S):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True,
                          shell=False, timeout=timeout)
```

**Строгий критерий pytest** (gate.py:159-207, `pytest_counts`, `_last_summary_line`, `pytest_summary_flags`, `pytest_ok`) переносить без изменений. Запуск обязательно с `-v` (строка итога с `=`), команда без `-k/-m/--deselect` (gate.py:247-250). Дополнить: очистить `PYTEST_ADDOPTS`, добавить `-o xfail_strict=true` [ASSUMED A2], передать `ASSISTANT_DB_PATH_OVERRIDE=<tmp>`.
```python
cmd = [str(pytest_bin), target, "-v", "-p", "no:cacheprovider",
       f"--junitxml={junit}", f"--basetemp={tmp_dir}/pytest-{repo}"]
def pytest_ok(returncode, counts, flags):
    return (returncode == 0 and counts.get("tests", 0) > 0 and counts.get("failures", 0) == 0
            and counts.get("errors", 0) == 0 and counts.get("skipped", 0) == 0 and not flags)
```

**Нормализация shield без утечки** (gate.py:302-406): `_SHIELD_LINE_RE`, `parse_shield_findings`, `compare_shield_findings`, `run_shield_step`. Переносить без изменений; `python_bin` брать из `CORE_DIR/.venv/bin/python` для обоих репозиториев (D-03). Для shared вызвать `run_shield_step("assistant-shared", SHARED_DIR)` отдельной строкой (D-05). Fail-closed ветки сохранить: rc не в (0,1); rc 1 без находок; 0 просканированных файлов.

**Дрейф персоны** (gate.py:426-443): `persona_drift_check(chat_copy, core_copy, name=...)`. Отсутствие файла = `ok=False` с названием причины (D-16). Вызывать дважды: `synthetic_persona.py` и `persona_tokens.py`; chat-копии `/opt/chat-app/backend/tests/{synthetic_persona,persona_tokens}.py`, только чтение. Путь chat вынести в константу (аналог `ASSISTANT_CORE_DIR` в chat gate.py:43), чтобы тест подменял через tmp.

**Хеш БД** (gate.py:466-488): `db_content_hash` (iterdump в одной транзакции, `?mode=ro`), `_sha_or_none`. Измерять "после" сразу после pytest core (Pitfall 3); при расхождении detail с диагностикой (`systemctl is-active`, mtime), вердикт КРАСНЫЙ. `make_db_copy` для гейта core НЕ нужен (тесты core БД не используют), но функция идёт в `deploy.py --backup`.

**Не обрывается на первой ошибке** (gate.py:495-513): обёртки `_safe_*_step` превращают исключение шага в красную строку.
```python
def _safe_shield_step(repo, repo_dir):
    try:
        return run_shield_step(repo, repo_dir)
    except Exception as exc:  # неожиданный сбой шага - красная строка, не трассировка
        return CheckResult(repo, "security_shield", False, f"сбой шага: {_exc_text(exc)}")
```

**Рендер и main** (gate.py:446-463, 565-582): `render_report` с колонками «Репозиторий | Проверка | Результат», `↳` деталями, `ИТОГ: ЗЕЛЁНЫЙ|КРАСНЫЙ`; пустой список = КРАСНЫЙ; `main` оборачивает `_run_all` в try/except и возвращает `0 if overall_green(results) else 1`; опция `--save-pytest-output DIR` сохраняется.

**Новые строки (нет в analog; писать по шаблону `CheckResult`):**
- pytest shared: `cwd=SHARED_DIR`, `pytest_bin=CORE_DIR/.venv/bin/pytest`, `target="tests"`.
- hook установлен (shared и опционально core): `git -C <repo> config --get core.hooksPath == ".githooks"` и `os.access(.githooks/pre-commit, os.X_OK)`; fail-closed.
- lint-imports core: `run_lint_imports_step` (gate.py:274-299) без изменений, `--no-logo --no-cache`.

**Порядок `_run_all`** (по образцу gate.py:516-562): hash_before -> pytest core -> hash_after -> lint -> shield core -> дрейф x2 -> pytest shared -> shield shared -> hook. `tempfile.mkdtemp(prefix="gate-")` + `shutil.rmtree` в `finally`.

---

### core `scripts/deploy.py` (utility, request-response/batch)

**Analog:** `/opt/chat-app/scripts/gate.py` для общих кирпичей; логики systemd/journal в кодовой базе нет (см. No Analog).

Копировать из gate.py: `run_cmd` (116-134) как внедряемый раннер (параметр `runner=run_cmd`, тест подставляет фейк и проверяет, что без `--restart` вызова `systemctl restart` нет); `CheckResult` + таблица (80-85, 450-463); `make_db_copy` для `--backup` (97-113):
```python
src = sqlite3.connect(live_db.resolve().as_uri() + "?mode=ro", uri=True)
out = sqlite3.connect(dst)
src.backup(out)
```
Для `--backup`: каталог вне git (`/var/backups/assistant-core` [ASSUMED A6]), каталог 0700, файл 0600.

Парсинг задач планировщика (RESEARCH, Code Examples): `ast`-разбор `src/main.py`, пары (функция, id), журнал содержит `Added job "<func>"`. Журнал фильтровать `journalctl -u assistant-worker _SYSTEMD_INVOCATION_ID=<id> --no-pager -o short-iso`. Не вызывать `getUpdates`, не открывать Telethon-сессию. Токен читать только по ключу `TELEGRAM_BOT_TOKEN`, не печатать; при ошибке `urllib` печатать класс и HTTP-код, не текст.

Ограничение сканера хардкода: в `scripts/*.py` не использовать токены профиля владельца (имя, организацию, аккаунт бота, ГУАП/tydex); пути `/opt/...` допустимы (`tests/test_hardcode_scanner.py`).

---

### core `tests/conftest.py` (страж боевой БД)

**Analog:** сам файл (docstring+импорты, строки 1-14) и RESEARCH Pattern 1. Страж ставится в самом начале файла, до `from src...`.

**Существующая шапка, перед которой вставлять страж:**
```python
import copy
import os

import pytest

from src.persona.loader import PERSONA_CONFIG_ENV, load_persona
from .synthetic_persona import SYNTHETIC_PERSONA
```
Сочетать с `os.environ.setdefault("ASSISTANT_DB_PATH_OVERRIDE", <tmp>)` до импорта `src`. Страж: `sys.addaudithook`, события `open` и `sqlite3.connect`, разбор `file:` URI через `urlsplit`, `realpath`, 4 суффикса (`""`, `-wal`, `-shm`, `-journal`), префильтр по basename, защита от рекурсии флагом `_busy`; закрыть оба пути `data/assistant.db` и корневой `assistant.db`. Полный эскиз в RESEARCH Pattern 1.

---

### core `src/config.py` (config, правка 4 строк)

**Analog:** сам файл, строки 8-16 (текущий код):
```python
load_dotenv(BASE_DIR / ".env", override=True)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/assistant.db")
SQLITE_DB_PATH = DATABASE_URL.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
if not os.path.isabs(SQLITE_DB_PATH):
    SQLITE_DB_PATH = str(BASE_DIR / SQLITE_DB_PATH)
```
Правка: `_DB_OVERRIDE = os.environ.get("ASSISTANT_DB_PATH_OVERRIDE")` до `load_dotenv`; после вычисления `SQLITE_DB_PATH` при непустом override присвоить его. Без переменной поведение прежнее. Тест (в `test_live_db_guard.py`): подмена `dotenv.load_dotenv` фейком, эмулирующим override, `importlib.reload(src.config)`, в `finally` вернуть исходное состояние. Не читать `.env`.

---

### core `src/connectors/gdrive/client.py` + `tests/test_gdrive_client.py`

**Analog:** сам файл, строки 184-216. Сигнатура сейчас:
```python
@staticmethod
def create_server_backup_archive(dest_dir="/opt/chat-app/uploads", include_db=True,
                                 include_env=True, include_uploads=False) -> Path:
    ...
    db_path = "/opt/assistant-core/data/assistant.db"
    session_path = "/opt/assistant-core/data/assistant_worker.session"
    env_core = "/opt/assistant-core/.env"
```
Добавить параметр `core_dir: str | Path = "/opt/assistant-core"` и строить три пути от него; вызов без аргументов (client.py:224) остаётся прежним (рестарт не нужен, отметить в SUMMARY). Тест передаёт `tmp_path` с поддельными `data/assistant.db`, `.env`, `data/assistant_worker.session`.

---

### core `tests/test_command_aliases.py` (стабилизация)

**Analog:** сам файл. Строка 30 `latency_ms < 50.0`, строки 181 и 213 `< 250.0`. Заменить одиночный замер на `min()` из N замеров или `time.process_time()`; не использовать skip/xfail. Затем три подряд зелёных полных прогона гейта.

---

### core `tests/test_gate.py`, `tests/test_gate_red_cases.py`, `tests/test_deploy_script.py` (test)

**Analog:** `/opt/chat-app/backend/tests/test_gate.py` (загрузка модуля скрипта, junit-фикстуры, `_write`). Переносить стиль и ~35 юнитов, менять только имена констант и пути.

**Загрузка скрипта как модуля** (test_gate.py:13-19):
```python
_GATE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "gate.py"   # у core parents[1]
_spec = importlib.util.spec_from_file_location("gate", _GATE_PATH)
gate = importlib.util.module_from_spec(_spec)
sys.modules["gate"] = gate      # dataclass с отложенными аннотациями ищет модуль в sys.modules
_spec.loader.exec_module(gate)
CheckResult = gate.CheckResult
```
Фикстуры JUNIT_SUITES / JUNIT_SUITE / GOOD_COUNTS и хелпер `_write(tmp_path, text)` (test_gate.py:21-45) копировать. Правило: не запускать полный гейт из теста (рекурсия); красные случаи (сломанный, skip, xfail, xpass, deselected через `addopts -k`, 0 тестов) проверять на мини-проектах в `tmp_path`. Для `test_deploy_script.py` загрузка модуля та же, `deploy` вместо `gate`; фейковый раннер записывает вызовы. Литералы секретов собирать из частей (`tests/` вне allowlist shield).

---

### shared `.githooks/pre-commit`, `scripts/install_hooks.sh`, `scripts/security_shield.py` (hook/utility)

**Analog:** `/opt/assistant-core/.githooks/pre-commit`, `scripts/install_hooks.sh`, `scripts/security_shield.py` (копия, D-04, тот же порядок поиска Python).

Hook (core .githooks/pre-commit:5-20): перебор кандидатов Python (`VIRTUAL_ENV`, `${REPO_ROOT}/.venv`, `/opt/assistant-core/.venv/bin/python`), затем
```bash
exec "${PYTHON_BIN}" "${REPO_ROOT}/scripts/security_shield.py" "${REPO_ROOT}"
```
Установщик (install_hooks.sh:5-38): проверка git-репо через `rev-parse --git-dir`, проверка `import assistant_shared.security`, `chmod +x`, предупреждение при чужом `core.hooksPath`, `git config core.hooksPath .githooks`. Для shared список кандидатов Python начать с `/opt/assistant-core/.venv/bin/python`.

Shield-обёртка (security_shield.py целиком, 15 строк): `argparse` с `path` и `--all`, `sys.exit(audit_repository(Path(args.path).resolve(), check_staged_only=not args.all))`; неизвестные флаги дают rc 2 (fail-closed). Рекомендация RESEARCH OQ5: копия обёртки, дрейф не проверять, отметить в SUMMARY.

В shared сейчас нет `scripts/`, `tests/`, `.githooks/` (ls-files: только `assistant_shared/**`, `pyproject.toml`, `README.md`, `.gitignore`). Файлы нужно `git add` до первого гейта (Pitfall 8).

---

### shared `pyproject.toml` (pytest-секция)

**Analog:** core `pytest.ini` (`asyncio_mode = auto`, `testpaths = tests`, `pythonpath = .`). В shared добавить `[tool.pytest.ini_options]` с теми же ключами; `pythonpath = .`. Опционально `[project.optional-dependencies] dev` без установки.

---

### shared `tests/test_migrations.py`, `test_hitl_shared.py`, `test_security_shared.py`, `test_shield_regressions.py`, `test_shield_parity.py`, `test_pre_commit_hook.py`

**Analog:** одноимённые файлы в `/opt/chat-app/backend/tests/` (все tracked). Источник пути hook/shield в `test_pre_commit_hook.py:11-12` меняется на `parents[1]` shared:
```python
HOOK_SOURCE = Path(__file__).resolve().parents[1] / ".githooks" / "pre-commit"
SHIELD_SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "security_shield.py"
```
Фикстура `git_repo` (test_pre_commit_hook.py:15-48): `git init`, копия hook и shield, `core.hooksPath .githooks`, начальный коммит; `_run_git_commit` передаёт `VIRTUAL_ENV`. Тесты: чистый коммит проходит, синтетический секрет и `.env` блокируются, 3 теста установщика (worktree, нет файла, чужой hooksPath).

Правки при переносе:
- `test_migrations.py:48-49` жёсткие `LATEST_SCHEMA_VERSION`/`ALL_MIGRATIONS` заменить списком из `assistant_shared/db/migrations/*.sql` + проверка префикса `[:2] == [0001, 0002]`; `EXPECTED_CORE_TABLES` как подмножество (Pitfall 9, Phase 3 добавит `0003`).
- `test_hitl_shared.py` строки ~54, 85, 112, 150: `@pytest.mark.anyio` -> режим asyncio (`asyncio_mode=auto`) (Pitfall 10).
- Тесты `app.*` (WR-13 в `test_shield_regressions.py`) и web-HITL/dashboard/конфиг БД chat-app не переносить (D-01).
- `test_cr05_cli_checks_all_remotes_and_aliases` использует `tmp_path / "tydex-work"` (завязка на подстроку, которую Phase 2 SECF-01 уберёт): решить при переносе, записать пометку для Phase 2 (OQ6).
- Секреты и NDA-слова в литералах собирать из частей (shield по `git ls-files`).

---

### chat `scripts/agy_cross_ai.sh` (GATE-05, только через `/gsd-quick` в chat-app)

**Analog:** сам файл, блок `# ---------- gate ----------`. Правка из RESEARCH Code Examples:
```bash
if [ -n "${AGY_GATE_CMD:-}" ]; then GATE=("$AGY_GATE_CMD"); GATE_DIR="$SCRIPT_DIR/.."
elif [ -f "$TOP/scripts/gate.py" ]; then GATE=(python3 "$TOP/scripts/gate.py"); GATE_DIR="$TOP"
else GATE=(python3 "$SCRIPT_DIR/gate.py"); GATE_DIR="$SCRIPT_DIR/.."; fi
( cd "$GATE_DIR" && exec "${GATE[@]}" ) < /dev/null > "$GATE_LOG" 2>&1 &
```
Тест выбора гейта добавить в `backend/tests/test_agy_cross_ai.py` (tracked); `scripts/gate.py` целевого репозитория уже в PROTECTED. Пробный прогон на `--repo /opt/assistant-core` делать последним, после коммита всех правок (OQ7).

---

## Shared Patterns

### Fail-closed и «не обрывается на первой ошибке»
**Source:** `/opt/chat-app/scripts/gate.py:495-513, 371-406`
**Apply to:** `scripts/gate.py`, `scripts/deploy.py`. Отсутствие файла/бинарника/каталога, 0 тестов, rc shield не из (0,1), rc 1 без находок, нет chat-копии персоны = `CheckResult(ok=False)` с причиной. Сбой шага превращается в красную строку, не в traceback.

### Подпроцессы
**Source:** `gate.py:116-134`
**Apply to:** `gate.py`, `deploy.py`, тесты hook. Список аргументов, `shell=False`, `timeout`, `capture_output=True`. Для `systemctl restart` в deploy таймаут >= 180-300 с (Pitfall 5).

### Нет утечки в вывод
**Source:** `gate.py:316-368` (shield), RESEARCH Security Domain
**Apply to:** `gate.py`, `deploy.py`, отчёты. Печатать только (путь, вид, число) и классы исключений; не печатать сырой вывод shield/journald, URL с токеном, e-mail; не читать `.env`/`*.session`/`credentials.json`/`token.json` (deploy читает только ключ `TELEGRAM_BOT_TOKEN`, gate не читает вовсе).

### Язык и логирование
**Source:** `.claude/CLAUDE.md` Conventions
**Apply to:** все новые файлы. Пользовательский вывод по-русски; `from __future__ import annotations`; PEP 604; CLI-скрипты могут `print`, в `src/` только `logger = logging.getLogger(__name__)` с `%s`.

### Ограничения тестов и скриптов
**Apply to:** все. Боевую `data/assistant.db` не открывать; `scripts/` сканируется `tests/test_hardcode_scanner.py` (baseline пуст); `tests/` вне allowlist shield (секреты из частей); пропуски/xfail/deselected = красный.

### Защита от правок агентом
`scripts/gate.py`, `.githooks/`, `scripts/security_shield.py`, `.importlinter` правит только Claude, `cross_ai: true` в планах на них недопустим.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| core `scripts/deploy.py` (части: systemd, journalctl по `_SYSTEMD_INVOCATION_ID`, `getMe`, ожидание `Update id=N is handled`, фазы без TTY, markdown-отчёт) | utility | request-response | В кодовой базе нет скриптов эксплуатации systemd/journal; использовать RESEARCH Pattern 4 и раздел «Фазы смоука без TTY» |
| core audit-hook страж в `tests/conftest.py` | test-config | event-driven | Аналога нет; эскиз RESEARCH Pattern 1 (проверен экспериментом) |
| core `docs/OPS_DEPLOY.md` | doc | - | Нет аналога процедуры выкатки |

## Metadata

**Analog search scope:** `/opt/chat-app/scripts`, `/opt/chat-app/backend/tests`, `/opt/assistant-core/{scripts,.githooks,tests,src/config.py,src/connectors/gdrive}`, `/opt/assistant-shared`
**Files scanned/read:** chat gate.py (целиком), test_gate.py/test_pre_commit_hook.py/test_migrations.py (фрагменты), core hook/installer/shield (целиком), config.py, conftest.py, gdrive client.py (фрагмент)
**Pattern extraction date:** 2026-10-09
