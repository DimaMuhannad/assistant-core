"""Сканер хардкода профиля владельца (PER-08, D-16).

Ищет токены профиля (owner_tokens из данных персоны по умолчанию) в отслеживаемых git файлах
кода вне allowlist. Остаточный долг записан baseline-словарём {путь: {класс: число строк}}
(hardcode_baseline.py). Baseline не может расти: новая находка, новый файл и устаревшая запись
(число в baseline больше фактического или файл исчез) делают тест красным. Тексты токенов в
сообщения не попадают: только путь, класс и число строк.

Счёт - число строк файла, в которых есть хотя бы один токен класса: он устойчив к правкам
соседних слов в строке. Файл не зависит от репозитория: у него две одинаковые копии
(backend/tests/ в chat-app и tests/ в assistant-core), репозиторий определяется через git.
"""

import collections
import subprocess
from pathlib import Path

from .hardcode_baseline import HARDCODE_BASELINE
from .persona_tokens import owner_tokens, token_classes_in_line

REPO = Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=Path(__file__).resolve().parent,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
)

SCANNED_SUFFIXES = (
    ".py",
    ".html",
    ".js",
    ".css",
    ".sh",
    ".toml",
    ".ini",
    ".cfg",
    ".yaml",
    ".yml",
    ".json",
    ".jinja2",
)
# Классы, где значения владельца законны как данные: данные персоны и шаблоны, тесты и фикстуры,
# документация и планы. Фаза 6 ужесточает до пустого allowlist (FIN-01).
ALLOWLIST_PREFIXES = ("config/", "tests/", "backend/tests/", "docs/", ".planning/")
ALLOWLIST_SUFFIXES = (".md",)


def is_scanned(relpath: str) -> bool:
    """Файл кода вне allowlist."""
    if relpath.startswith(ALLOWLIST_PREFIXES) or relpath.endswith(ALLOWLIST_SUFFIXES):
        return False
    return relpath.endswith(SCANNED_SUFFIXES)


def scan_files(repo: Path, relpaths: list[str], tokens: dict[str, set[str]]) -> collections.Counter:
    """Счёт (путь, класс) -> число строк с токеном класса; allowlist и чужие расширения пропускаются."""
    found: collections.Counter = collections.Counter()
    for relpath in relpaths:
        if not is_scanned(relpath):
            continue
        path = repo / relpath
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            for cls in token_classes_in_line(line, tokens):
                found[(relpath, cls)] += 1
    return found


def scan_repo(repo: Path, tokens: dict[str, set[str]]) -> collections.Counter:
    """Сканирует отслеживаемые файлы репозитория (git ls-files; код возврата 0 обязателен)."""
    listing = subprocess.run(
        ["git", "ls-files", "-z"], cwd=repo, capture_output=True, check=True
    ).stdout.decode("utf-8")
    return scan_files(repo, [item for item in listing.split("\0") if item], tokens)


def compare(
    found: collections.Counter, allowed: dict[str, dict[str, int]]
) -> tuple[list[str], list[str]]:
    """(новые находки, устаревшие записи baseline); по образцу compare_shield_findings."""
    flat = {(path, cls): count for path, classes in allowed.items() for cls, count in classes.items()}
    new = [
        f"новая находка: {path} [{cls}] строк: {count} (в baseline {flat.get((path, cls), 0)})"
        for (path, cls), count in sorted(found.items())
        if count > flat.get((path, cls), 0)
    ]
    stale = [
        f"устаревшая запись (уменьшите или удалите в hardcode_baseline.py): "
        f"{path} [{cls}] в baseline {count}, найдено {found.get((path, cls), 0)}"
        for (path, cls), count in sorted(flat.items())
        if found.get((path, cls), 0) < count
    ]
    return new, stale


def render_baseline(found: collections.Counter) -> str:
    """Текст словаря HARDCODE_BASELINE для разовой генерации (с ручным просмотром)."""
    by_path: dict[str, dict[str, int]] = {}
    for (path, cls), count in sorted(found.items()):
        by_path.setdefault(path, {})[cls] = count
    lines = ["HARDCODE_BASELINE: dict[str, dict[str, int]] = {"]
    for path, classes in by_path.items():
        body = ", ".join(f'"{cls}": {count}' for cls, count in sorted(classes.items()))
        lines.append(f'    "{path}": {{{body}}},')
    lines.append("}")
    return "\n".join(lines) + "\n"


def test_scanner_counts_lines_and_respects_allowlist(tmp_path: Path) -> None:
    tokens = {"name": {"Иванов"}, "domain": {"corp.example"}}
    files = {
        "src/app.py": "x = 1\nowner = 'иванов'\nurl = 'https://corp.example/x', 'Иванов'\n",
        "src/page.html": "<p>corp.example</p>\n",
        "src/notes.txt": "Иванов\n",  # расширение вне списка
        "config/persona.yaml": "name: Иванов\n",  # allowlist
        "tests/test_x.py": "Иванов\n",
        "backend/tests/test_y.py": "Иванов\n",
        "docs/BASELINE.md": "Иванов\n",
        "README.md": "Иванов\n",
        ".planning/PLAN.json": '{"n": "Иванов"}\n',
    }
    for relpath, text in files.items():
        target = tmp_path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    found = scan_files(tmp_path, sorted(files) + ["src/missing.py"], tokens)

    assert dict(found) == {
        ("src/app.py", "name"): 2,  # строка с двумя вхождениями одного класса - одна строка
        ("src/app.py", "domain"): 1,
        ("src/page.html", "domain"): 1,
    }

    new, stale = compare(found, {"src/app.py": {"name": 2, "domain": 1}, "src/page.html": {"domain": 1}})
    assert new == [] and stale == []
    new, _ = compare(found, {"src/app.py": {"name": 1, "domain": 1}})
    assert len(new) == 2  # превышение счёта и новый файл
    _, stale = compare(found, {"src/app.py": {"name": 3}, "src/gone.py": {"name": 1}})
    assert len(stale) == 2  # запись больше фактического и исчезнувший файл
    assert all("Иванов" not in message for message in new + stale)


def test_no_new_hardcode_outside_baseline(default_persona_config: dict) -> None:
    found = scan_repo(REPO, owner_tokens(default_persona_config))
    new, _ = compare(found, HARDCODE_BASELINE)
    assert not new, "хардкод профиля вне baseline (перенесите значение в данные персоны):\n" + "\n".join(new)


def test_baseline_has_no_stale_entries(default_persona_config: dict) -> None:
    found = scan_repo(REPO, owner_tokens(default_persona_config))
    _, stale = compare(found, HARDCODE_BASELINE)
    assert not stale, "baseline больше фактического счёта, его нужно сократить:\n" + "\n".join(stale)
