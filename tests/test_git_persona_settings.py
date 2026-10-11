"""Тесты схемы git_source, настроек, домена и конфигурации Notion (план 04-03, GIT-02, GIT-03, NTN-01)."""

import json
from pathlib import Path

import pytest

from src.core.domain.entities import Persona, Workspace, WorkspaceClearance
from src.persona.loader import load_persona
from src.persona.models import PersonaConfigError

from .synthetic_persona import SYNTHETIC_PERSONA, synthetic_to_config


def _load_modified_persona(tmp_path: Path, modifier) -> any:
    data = synthetic_to_config(SYNTHETIC_PERSONA)
    modifier(data)
    path = tmp_path / "persona.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return load_persona(path)


def test_git_source_settings_default(tmp_path: Path) -> None:
    from src.persona.bindings import GitSourceSettings, git_source_settings
    from src.persona.models import GitSourceParams

    # Персона по умолчанию: привязка git_source есть, config пуст
    persona = _load_modified_persona(tmp_path, lambda d: None)
    settings = git_source_settings(persona)

    schema_defaults = GitSourceParams()
    assert settings == GitSourceSettings(
        stagnation_days=schema_defaults.stagnation_days,
        day_of_week=schema_defaults.day_of_week,
        hour=schema_defaults.hour,
        minute=schema_defaults.minute,
    )
    assert (settings.stagnation_days, settings.day_of_week, settings.hour, settings.minute) == (7, "sun", 20, 0)


def test_git_source_settings_without_binding(tmp_path: Path) -> None:
    from src.persona.bindings import GitSourceSettings, git_source_settings

    # 1. Персона без привязки git_source (список пуст)
    def remove_git_source(d: dict) -> None:
        d["persona"]["connectors"]["git_source"] = []

    persona_empty_git = _load_modified_persona(tmp_path, remove_git_source)
    settings = git_source_settings(persona_empty_git)
    assert (settings.stagnation_days, settings.day_of_week, settings.hour, settings.minute) == (7, "sun", 20, 0)

    # 2. Объект без атрибута connectors (например, доменный Persona)
    domain_persona = Persona(id="p", name="n")
    domain_settings = git_source_settings(domain_persona)
    assert (
        domain_settings.stagnation_days,
        domain_settings.day_of_week,
        domain_settings.hour,
        domain_settings.minute,
    ) == (7, "sun", 20, 0)


def test_git_source_settings_explicit(tmp_path: Path) -> None:
    from src.persona.bindings import git_source_settings

    def set_explicit(d: dict) -> None:
        d["persona"]["connectors"]["git_source"][0]["config"] = {
            "stagnation_days": 3,
            "day_of_week": "fri",
            "hour": 18,
            "minute": 30,
        }

    persona = _load_modified_persona(tmp_path, set_explicit)
    settings = git_source_settings(persona)

    assert settings.stagnation_days == 3
    assert settings.day_of_week == "fri"
    assert settings.hour == 18
    assert settings.minute == 30


@pytest.mark.parametrize(
    "bad_config",
    [
        {"stagnation_days": 0},
        {"stagnation_days": 366},
        {"hour": 24},
        {"hour": -1},
        {"minute": 60},
        {"minute": -1},
        {"day_of_week": "xyz"},
        {"unknown_key": "val"},
    ],
)
def test_git_source_params_reject_invalid(tmp_path: Path, bad_config: dict) -> None:
    def set_bad(d: dict) -> None:
        d["persona"]["connectors"]["git_source"][0]["config"] = bad_config

    with pytest.raises(PersonaConfigError) as exc_info:
        _load_modified_persona(tmp_path, set_bad)

    err_msg = str(exc_info.value)
    assert "git_source" in err_msg
    # Значения конфигурации не должны печататься в ошибке
    for val in bad_config.values():
        assert str(val) not in err_msg or len(str(val)) <= 2  # исключаем случайные совпадения цифр


def test_to_domain_carries_git_host_and_account(tmp_path: Path) -> None:
    # Workspace без этих полей создаётся как раньше
    ws_plain = Workspace(id="w", name="W", clearance=WorkspaceClearance.PUBLIC, path="/p")
    assert ws_plain.git_host is None
    assert ws_plain.account == ""

    # to_domain передаёт git_host и account
    def set_ws_git(d: dict) -> None:
        ws0 = d["persona"]["workspaces"][0]
        ws0["git_host"] = "git.example.com"
        ws0["account"] = "owner-acc"

    persona = _load_modified_persona(tmp_path, set_ws_git)
    domain_persona = persona.to_domain()
    ws_domain = domain_persona.workspaces[0]

    assert ws_domain.git_host == "git.example.com"
    assert ws_domain.account == "owner-acc"


def test_notion_activity_db_id_in_config() -> None:
    import src.config as config

    assert hasattr(config, "NOTION_ACTIVITY_DB_ID")
    assert isinstance(config.NOTION_ACTIVITY_DB_ID, str)


def test_env_example_has_commented_notion_activity_and_api_key() -> None:
    from assistant_shared.security import SECRET_PATTERNS

    repo_root = Path(__file__).resolve().parent.parent
    env_example_path = repo_root / ".env.example"
    lines = env_example_path.read_text(encoding="utf-8").splitlines()

    # Проверяем точное наличие строк без значений
    assert "# NOTION_API_KEY=" in lines
    assert "# NOTION_ACTIVITY_DB_ID=" in lines

    # Проверяем, что ни одна строка не содержит секрет
    for line in lines:
        for name, pattern in SECRET_PATTERNS:
            assert not pattern.search(line), f"Line '{line}' matched secret pattern {name}"
