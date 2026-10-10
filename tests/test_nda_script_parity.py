"""P01 (PER-04, SECF-01, D-10, D-21): обёртка scripts/security_shield.py не хранит слова NDA и передаёт данные персоны.

Значения нигде не печатаются: сравнение выносится в булеву переменную, сообщения без значений.
Литерал из исходника библиотеки не читается. D-10 (план 02-10): в общей библиотеке безопасности нет ни
констант слов NDA, ни названий организаций и частей аккаунтов персоны; токены берутся из load_persona() во
время теста, в файле теста литералов нет.
"""

import importlib
import importlib.util
from pathlib import Path

import assistant_shared.security as security_package

from src.persona.loader import load_persona

SHIELD_PATH = Path(__file__).resolve().parents[1] / "scripts" / "security_shield.py"


def _shield_module():
    spec = importlib.util.spec_from_file_location("security_shield_under_test", SHIELD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p01_script_has_no_nda_word_constants():
    module = _shield_module()
    has_attribute = hasattr(module, "CORPORATE_NDA_KEYWORDS")
    assert not has_attribute, "обёртка не должна экспортировать слова NDA"
    in_source = "CORPORATE_NDA_KEYWORDS" in SHIELD_PATH.read_text(encoding="utf-8")
    assert not in_source, "обёртка не должна упоминать константу слов NDA"


def test_p01_script_passes_persona_workspaces_and_nothing_else(tmp_path, monkeypatch):
    monkeypatch.delenv("PERSONA_CONFIG_PATH", raising=False)
    expected = [ws.model_dump() for ws in load_persona().workspaces]
    assert expected, "в персоне по умолчанию ожидаются рабочие пространства"
    module = _shield_module()
    calls: list[tuple] = []

    def strict_stub(repo_path, check_staged_only, *, workspaces):
        # Любой лишний аргумент даёт TypeError: допусков и иных смягчений нет (D-21)
        calls.append((repo_path, check_staged_only, workspaces))
        return 0

    monkeypatch.setattr(module, "audit_repository", strict_stub)

    assert module.main(["--all", str(tmp_path)]) == 0
    assert module.main([str(tmp_path)]) == 0

    assert len(calls) == 2
    full_mode, commit_mode = calls
    assert full_mode[1] is False and commit_mode[1] is True
    same_data = full_mode[2] == expected and commit_mode[2] == expected
    assert same_data, "обёртка передала в библиотеку не данные рабочих пространств персоны"
    assert full_mode[0] == tmp_path.resolve() and commit_mode[0] == tmp_path.resolve()


# --- D-10 (SECF-01): в общей библиотеке безопасности нет доменных литералов ---

_MIN_TOKEN_LENGTH = 4
# Имена прежних констант собраны из частей, чтобы файл теста сам не содержал удалённого имени
_LEGACY_NAMES = (
    "CORPORATE" + "_NDA_" + "KEYWORDS",
    "_KW_" + "PREFIX",
    "_KW_" + "GOLAY",
    "_KW_" + "THZ",
)


def _security_modules():
    package_dir = Path(security_package.__file__).resolve().parent
    names = ["assistant_shared.security"] + [
        f"assistant_shared.security.{path.stem}"
        for path in sorted(package_dir.glob("*.py"))
        if path.stem != "__init__"
    ]
    return [importlib.import_module(name) for name in names]


def _persona_tokens() -> set[str]:
    """Названия и псевдонимы организаций, части аккаунтов и хвосты запрещённых подстрок remote (casefold)."""
    persona = load_persona()
    raw: list[str] = []
    for org in persona.organizations.values():
        raw.append(org.name)
        raw.extend(org.aliases)
    for ws in persona.workspaces:
        account_words = ws.account.split()
        if account_words:
            raw.append(account_words[0])
        for substring in ws.forbidden_remote_substrings:
            segments = [part for part in substring.replace("\\", "/").split("/") if part]
            if segments:
                raw.append(segments[-1])
    stripped = (item.strip() for item in raw)
    return {item.casefold() for item in stripped if len(item) >= _MIN_TOKEN_LENGTH}


def test_d10_library_has_no_nda_word_constants():
    found = [
        f"{module.__name__}: имя из набора прежних констант"
        for module in _security_modules()
        for legacy in _LEGACY_NAMES
        if hasattr(module, legacy)
    ]
    assert not found, found
    generic = [
        module.__name__
        for module in _security_modules()
        for attr in dir(module)
        if "NDA" in attr.upper() and "KEYWORD" in attr.upper()
    ]
    assert not generic, f"в модулях библиотеки найден атрибут со словами NDA: {generic}"


def test_d10_library_sources_have_no_organization_or_account_tokens():
    tokens = _persona_tokens()
    assert tokens, "данные персоны должны давать токены организаций и аккаунтов"
    package_dir = Path(security_package.__file__).resolve().parent
    sources = sorted(package_dir.glob("*.py"))
    assert sources, "исходники библиотеки безопасности не найдены"
    offenders = []
    for source in sources:
        text = source.read_text(encoding="utf-8").casefold()
        # Булево сравнение: значения токенов не печатаются
        if any(token in text for token in tokens):
            offenders.append(source.name)
    assert not offenders, f"в исходниках библиотеки найдены токены персоны (файлы: {offenders})"
