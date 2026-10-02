"""Загрузчик персоны (PER-01, D-01): подмена файла, строгая схема, безопасный YAML."""

from pathlib import Path

import pytest

from src.persona.loader import (
    DEFAULT_PERSONA_PATH,
    PERSONA_CONFIG_ENV,
    load_persona,
    resolve_persona_path,
)
from src.persona.models import PersonaConfigError

MINIMAL_TEMPLATE = """\
persona:
  id: {persona_id}
  display_name: Тестовая Персона
  short_name: Тестова П.
  title: тестировщик
  organizations:
    university:
      name: Университет-А
      aliases: []
  default_area: Область-А
{extra}"""


def _write_persona(path: Path, persona_id: str = "tmp-persona", extra: str = "") -> Path:
    path.write_text(MINIMAL_TEMPLATE.format(persona_id=persona_id, extra=extra), encoding="utf-8")
    return path


def test_default_persona_loads_without_env(monkeypatch):
    monkeypatch.delenv(PERSONA_CONFIG_ENV, raising=False)
    persona = load_persona()
    assert persona.id == "popov-da-default"
    assert persona.source_path == DEFAULT_PERSONA_PATH
    assert persona.base_dir == DEFAULT_PERSONA_PATH.parent


def test_env_path_overrides_default(monkeypatch, tmp_path):
    other = _write_persona(tmp_path / "other.yaml", "env-persona")
    monkeypatch.setenv(PERSONA_CONFIG_ENV, str(other))
    persona = load_persona()
    assert persona.id == "env-persona"
    assert persona.source_path == other


def test_explicit_path_beats_env_and_empty_env_is_ignored(monkeypatch, tmp_path):
    from_env = _write_persona(tmp_path / "env.yaml", "env-persona")
    explicit = _write_persona(tmp_path / "explicit.yaml", "explicit-persona")
    monkeypatch.setenv(PERSONA_CONFIG_ENV, str(from_env))
    assert load_persona(explicit).id == "explicit-persona"

    monkeypatch.setenv(PERSONA_CONFIG_ENV, "")
    assert resolve_persona_path() == DEFAULT_PERSONA_PATH
    assert load_persona().id == "popov-da-default"


def test_unknown_key_rejected_without_echoing_value(tmp_path):
    marker = "znachenie-marker-123"
    bad = _write_persona(tmp_path / "bad.yaml", extra=f"  neizvestnoe_pole: {marker}\n")
    with pytest.raises(PersonaConfigError) as excinfo:
        load_persona(bad)
    text = str(excinfo.value)
    assert "neizvestnoe_pole" in text
    assert marker not in text
    assert str(bad) in text


def test_unsafe_yaml_tag_rejected(tmp_path):
    evil = tmp_path / "evil.yaml"
    evil.write_text(
        "persona: !!python/object/apply:os.system ['echo unsafe']\n", encoding="utf-8"
    )
    with pytest.raises(PersonaConfigError):
        load_persona(evil)


def test_missing_root_key_rejected(tmp_path):
    no_root = tmp_path / "no-root.yaml"
    no_root.write_text("id: tmp-persona\ndisplay_name: X\n", encoding="utf-8")
    with pytest.raises(PersonaConfigError):
        load_persona(no_root)
