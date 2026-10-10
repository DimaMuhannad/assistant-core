"""Обёртка scripts/security_shield.py: правила NDA из данных персоны (SECF-01, D-06..D-08, D-21).

Все слова и адреса синтетические и собраны из частей; значения реальной персоны в файле не встречаются.
Обёртка запускается подпроцессом, как её запускают hook и гейты.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from .test_persona_loader import MINIMAL_TEMPLATE

SHIELD = Path(__file__).resolve().parents[1] / "scripts" / "security_shield.py"

# Синтетические слова NDA: собраны из частей, чтобы литерал не попадал в исходник целиком
WORD_A = "zq" + "vex" + "alpha"
WORD_B = "zq" + "vex" + "bravo"
WORD_C = "zq" + "vex" + "charlie"
FORBIDDEN_REMOTE = "git.synthetic" + ".example/" + "forbidden"
NDA_WORKSPACE_REMOTE = "https://git.synthetic" + ".example/" + "safe/repo.git"
SAFE_ORIGIN = "https://git.synthetic" + ".example/" + "safe/other.git"
BAD_ORIGIN = "https://git.synthetic" + ".example/" + "forbidden/repo.git"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, timeout=60
    )


def _make_repo(path: Path, files: dict[str, str], origin: str | None = None) -> Path:
    """Временный git-репозиторий с проиндексированными файлами."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "synthetic@synthetic.example")
    _git(path, "config", "user.name", "Synthetic")
    if origin:
        _git(path, "remote", "add", "origin", origin)
    for rel, text in files.items():
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _git(path, "add", "-A")
    return path.resolve()


def _workspaces_block(nda_path: Path, public_path: Path, words: tuple[str, ...] = (WORD_A,)) -> str:
    word_lines = "".join(f"        - {w}\n" for w in words)
    return (
        "  workspaces:\n"
        "    - id: pub-ws\n"
        "      label: Public workspace\n"
        f'      path: "{public_path}"\n'
        "      clearance: public\n"
        "    - id: nda-ws\n"
        "      label: NDA workspace\n"
        f'      path: "{nda_path}"\n'
        "      clearance: restricted_nda\n"
        f'      remote: "{NDA_WORKSPACE_REMOTE}"\n'
        "      forbidden_remote_substrings:\n"
        f"        - {FORBIDDEN_REMOTE}\n"
        "      forbidden_keywords:\n"
        f"{word_lines}"
    )


def _persona_text(nda_path: Path, public_path: Path, words: tuple[str, ...] = (WORD_A,)) -> str:
    extra = _workspaces_block(nda_path, public_path, words)
    return MINIMAL_TEMPLATE.format(persona_id="shield-cli", extra=extra)


def _write_persona(path: Path, nda_path: Path, public_path: Path, words: tuple[str, ...] = (WORD_A,)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_persona_text(nda_path, public_path, words), encoding="utf-8")
    return path


def _run_shield(persona_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PERSONA_CONFIG_PATH"] = str(persona_path)
    return subprocess.run(
        [sys.executable, str(SHIELD), *args],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )


def _setup(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Пути пространств и файл персоны: (каталог NDA, каталог публичного, файл персоны)."""
    nda_dir = (tmp_path / "ws_nda").resolve()
    pub_dir = (tmp_path / "ws_pub").resolve()
    nda_dir.mkdir()
    pub_dir.mkdir()
    persona = _write_persona(tmp_path / "persona_cfg" / "persona.yaml", nda_dir, pub_dir)
    return nda_dir, pub_dir, persona


# ---- Трассер: NDA по пути + запрещённый remote ----


def test_tracer_nda_repo_with_forbidden_origin_is_blocked(tmp_path):
    nda_dir, _pub, persona = _setup(tmp_path)
    repo = _make_repo(nda_dir / "project", {"a.txt": "ok\n"}, origin=BAD_ORIGIN)
    result = _run_shield(persona, str(repo), "--all")
    assert result.returncode == 1, result.stdout
    assert "RESTRICTED" in result.stdout
    assert "CRITICAL" in result.stdout


def test_tracer_nda_repo_with_safe_origin_passes(tmp_path):
    nda_dir, _pub, persona = _setup(tmp_path)
    repo = _make_repo(nda_dir / "project", {"a.txt": "ok\n"}, origin=SAFE_ORIGIN)
    result = _run_shield(persona, str(repo), "--all")
    assert result.returncode == 0, result.stdout
    assert "RESTRICTED" in result.stdout


# ---- Контракт обёртки ----


def test_unknown_flag_exits_with_code_2_before_persona_is_loaded(tmp_path):
    missing = tmp_path / "does_not_exist.yaml"
    result = _run_shield(missing, "--bogus-flag")
    assert result.returncode == 2
    assert "SECURITY SHIELD ERROR" not in result.stdout


def test_import_does_not_load_persona_or_print(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PERSONA_CONFIG_PATH", str(tmp_path / "does_not_exist.yaml"))
    spec = importlib.util.spec_from_file_location("security_shield_import_check", SHIELD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # не должно падать: персона при импорте не читается
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""
    assert callable(module.main)


def test_wrapper_has_no_nda_word_constants():
    spec = importlib.util.spec_from_file_location("security_shield_attr_check", SHIELD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    has_constant = hasattr(module, "CORPORATE_NDA_KEYWORDS")
    assert not has_constant, "обёртка не должна экспортировать константу слов NDA"
    source_has_name = "CORPORATE_NDA_KEYWORDS" in SHIELD.read_text(encoding="utf-8")
    assert not source_has_name
