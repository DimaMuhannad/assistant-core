"""Загрузчик персоны (PER-01, D-01): подмена файла, строгая схема, безопасный YAML."""

import json
from pathlib import Path

import pytest
import yaml

from src.persona.loader import (
    DEFAULT_PERSONA_PATH,
    PERSONA_CONFIG_ENV,
    load_persona,
    resolve_persona_path,
)
from src.persona.models import PersonaConfigError

from .synthetic_persona import SYNTHETIC_PERSONA, SYNTHETIC_TELEGRAM_ENV, synthetic_to_config

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
  task_areas:
    - {{value: Область-А, label: Область А}}
  methodist:
    raw_dir: /tmp/raw
    kb_dir: /tmp/kb
    scope_rules: {{out_of_scope_reason: вне темы}}
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


def _nda_workspace(extra: str = "") -> str:
    return (
        "  workspaces:\n"
        "    - id: corp\n"
        "      label: Корп\n"
        "      path: /tmp/corp\n"
        "      clearance: restricted_nda\n"
        f"{extra}"
    )


@pytest.mark.parametrize(
    "extra",
    [
        "",
        '      forbidden_remote_substrings: ["example.invalid/x"]\n',
        '      forbidden_keywords: ["marker-x"]\n',
        '      forbidden_remote_substrings: []\n      forbidden_keywords: ["marker-x"]\n',
    ],
)
def test_restricted_nda_requires_rules(tmp_path, extra):
    bad = _write_persona(tmp_path / "bad.yaml", extra=_nda_workspace(extra))
    with pytest.raises(PersonaConfigError) as excinfo:
        load_persona(bad)
    text = str(excinfo.value)
    assert "без правил NDA" in text
    assert "marker-x" not in text


def test_restricted_nda_with_both_rule_lists_is_accepted_and_public_needs_none(tmp_path):
    rules = (
        '      forbidden_remote_substrings: ["example.invalid/x"]\n'
        '      forbidden_keywords: ["marker-x"]\n'
        "    - id: open\n"
        "      label: Открытое\n"
        "      path: /tmp/open\n"
        "      clearance: public\n"
    )
    ok = _write_persona(tmp_path / "ok.yaml", extra=_nda_workspace(rules))
    assert [w.clearance for w in load_persona(ok).workspaces] == ["restricted_nda", "public"]


def test_workspace_ids_unique(tmp_path):
    twice = (
        "  workspaces:\n"
        "    - {id: same, label: A, path: /tmp/a, clearance: public}\n"
        "    - {id: same, label: B, path: /tmp/b, clearance: internal}\n"
    )
    with pytest.raises(PersonaConfigError):
        load_persona(_write_persona(tmp_path / "dup.yaml", extra=twice))


def test_clearance_values_match_domain_enum():
    from typing import get_args

    from src.core.domain.entities import WorkspaceClearance
    from src.persona.models import WorkspaceConfig

    literal = set(get_args(WorkspaceConfig.model_fields["clearance"].annotation))
    assert literal == {c.value for c in WorkspaceClearance}


def _persona_from(tmp_path, **sections: str) -> Path:
    return _write_persona(tmp_path / "p.yaml", extra="".join(sections.values()))


def test_telegram_ids_must_be_env_placeholders(tmp_path):
    literal = "100000777"
    bad = _persona_from(tmp_path, t=f"  telegram:\n    authorized_user_ids: ['{literal}']\n")
    with pytest.raises(PersonaConfigError) as excinfo:
        load_persona(bad)
    assert literal not in str(excinfo.value)

    ok = _persona_from(tmp_path, t='  telegram:\n    authorized_user_ids: ["${TELEGRAM_USER_ID}"]\n')
    assert load_persona(ok).telegram.authorized_user_ids == ["${TELEGRAM_USER_ID}"]


def test_resolve_authorized_user_ids_never_returns_empty_string(tmp_path):
    persona = load_persona(
        _persona_from(tmp_path, t='  telegram:\n    authorized_user_ids: ["${TELEGRAM_USER_ID}"]\n')
    )
    assert persona.resolve_authorized_user_ids(env={}) == ()
    assert persona.unresolved_env_vars(env={}) == ("TELEGRAM_USER_ID",)
    assert persona.resolve_authorized_user_ids(env={"TELEGRAM_USER_ID": ""}) == ()
    assert persona.resolve_authorized_user_ids(env={"TELEGRAM_USER_ID": "  "}) == ()
    assert persona.unresolved_env_vars(env={"TELEGRAM_USER_ID": ""}) == ("TELEGRAM_USER_ID",)
    env = {"TELEGRAM_USER_ID": "100000777"}
    assert persona.resolve_authorized_user_ids(env=env) == (100000777,)
    assert persona.unresolved_env_vars(env=env) == ()
    with pytest.raises(PersonaConfigError) as excinfo:
        persona.resolve_authorized_user_ids(env={"TELEGRAM_USER_ID": "abc"})
    assert "TELEGRAM_USER_ID" in str(excinfo.value) and "abc" not in str(excinfo.value)
    with pytest.raises(PersonaConfigError) as excinfo:
        persona.resolve_authorized_user_ids(env={}, strict=True)
    assert "TELEGRAM_USER_ID" in str(excinfo.value)


def test_resolve_reads_environment_at_call_time(tmp_path, monkeypatch):
    persona = load_persona(
        _persona_from(tmp_path, t='  telegram:\n    authorized_user_ids: ["${TELEGRAM_USER_ID}"]\n')
    )
    monkeypatch.delenv("TELEGRAM_USER_ID", raising=False)
    assert persona.resolve_authorized_user_ids() == ()
    monkeypatch.setenv("TELEGRAM_USER_ID", "100000555")
    assert persona.resolve_authorized_user_ids() == (100000555,)


def test_connector_roles_match_domain_enum_and_binding_ids_unique(tmp_path):
    from src.core.domain.entities import ConnectorRole
    from src.persona.models import ConnectorsConfig

    assert set(ConnectorsConfig.model_fields) == {role.value for role in ConnectorRole}
    assert len(ConnectorsConfig.model_fields) == 6

    twice = (
        "  connectors:\n"
        "    lms:\n"
        "      - {id: main, provider: lms_portal, scopes: [lms.read]}\n"
        "      - {id: main, provider: lms_portal, scopes: [lms.read]}\n"
    )
    with pytest.raises(PersonaConfigError):
        load_persona(_persona_from(tmp_path, c=twice))

    two_ids = (
        "  connectors:\n"
        "    lms:\n"
        "      - {id: main, provider: lms_portal, scopes: [lms.read]}\n"
        "      - {id: second, provider: lms_portal, scopes: [lms.read]}\n"
    )
    persona = load_persona(_persona_from(tmp_path, c=two_ids))
    assert [b.id for b in persona.connectors.lms] == ["main", "second"]


def test_default_area_must_be_among_task_areas(tmp_path):
    text = MINIMAL_TEMPLATE.format(persona_id="p", extra="").replace(
        "default_area: Область-А", "default_area: Нет-такой"
    )
    bad = tmp_path / "bad.yaml"
    bad.write_text(text, encoding="utf-8")
    with pytest.raises(PersonaConfigError):
        load_persona(bad)


def test_default_persona_data_is_complete():
    persona = load_persona()
    assert len(persona.workspaces) == 4
    assert len(persona.task_areas) == 6
    assert [a.value for a in persona.task_areas if not a.show_in_filter] == ["Финансы"]
    assert persona.default_area in {a.value for a in persona.task_areas}
    assert len(persona.ui.texts) == 7
    assert len(persona.methodist.file_catalog) == 7
    assert persona.connectors.git_source == [] and persona.connectors.notion == []
    assert persona.connectors.timesheet[0].config["daily_norm_hours"] == 8.5
    assert persona.telegram.authorized_user_ids == ["${TELEGRAM_USER_ID}"]
    assert persona.to_domain().workspaces[2].clearance.value == "restricted_nda"


def test_current_persona_and_use_persona_override(tmp_path, monkeypatch):
    from src.persona.current import current_persona, reset_persona_cache, use_persona

    monkeypatch.delenv(PERSONA_CONFIG_ENV, raising=False)
    reset_persona_cache()
    default = current_persona()
    assert default.id == "popov-da-default"
    assert current_persona() is default  # кэш по пути

    other = load_persona(_write_persona(tmp_path / "o.yaml", "other-persona", extra=""))
    with use_persona(other):
        assert current_persona().id == "other-persona"
    assert current_persona().id == "popov-da-default"

    # путь вычисляется при каждом вызове: смена переменной окружения видна без перезапуска
    monkeypatch.setenv(PERSONA_CONFIG_ENV, str(tmp_path / "o.yaml"))
    assert current_persona().id == "other-persona"
    monkeypatch.delenv(PERSONA_CONFIG_ENV)
    reset_persona_cache()
    assert current_persona() is not default  # файл перечитан
    assert current_persona().id == "popov-da-default"


def test_synthetic_persona_loads_from_yaml_via_env(monkeypatch, tmp_path):
    path = tmp_path / "synthetic.yaml"
    path.write_text(
        yaml.safe_dump(synthetic_to_config(SYNTHETIC_PERSONA), allow_unicode=True),
        encoding="utf-8",
    )
    monkeypatch.setenv(PERSONA_CONFIG_ENV, str(path))
    monkeypatch.delenv(SYNTHETIC_TELEGRAM_ENV, raising=False)
    persona = load_persona()
    assert persona.id == "synthetic-test-persona"
    assert persona.display_name == SYNTHETIC_PERSONA["display_name"]
    assert persona.display_name != load_persona(DEFAULT_PERSONA_PATH).display_name
    assert [(w.id, w.clearance) for w in persona.workspaces] == [
        (w["id"], w["clearance"]) for w in SYNTHETIC_PERSONA["workspaces"]
    ]
    nda = next(w for w in persona.workspaces if w.clearance == "restricted_nda")
    source = next(w for w in SYNTHETIC_PERSONA["workspaces"] if w["id"] == nda.id)
    assert nda.forbidden_keywords == source["forbidden_keywords"]
    assert nda.forbidden_remote_substrings == source["forbidden_remote_substrings"]
    slots = persona.connectors.schedule_source[0].config["lesson_slots"]
    assert slots == [{"number": 1, "start": "08:15", "end": "09:45"}]
    assert persona.default_area == SYNTHETIC_PERSONA["default_area"]
    # плейсхолдер разворачивается из окружения в момент вызова; без переменной - пусто
    assert persona.resolve_authorized_user_ids({SYNTHETIC_TELEGRAM_ENV: "100000001"}) == (
        SYNTHETIC_PERSONA["telegram"]["authorized_user_id"],
    )
    assert persona.resolve_authorized_user_ids({}) == ()
    assert persona.unresolved_env_vars({}) == (SYNTHETIC_TELEGRAM_ENV,)


def test_synthetic_persona_loads_from_json(tmp_path):
    config = synthetic_to_config(SYNTHETIC_PERSONA)
    yaml_path = tmp_path / "synthetic.yaml"
    yaml_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    json_path = tmp_path / "synthetic.json"
    json_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    from_json = load_persona(json_path)
    from_yaml = load_persona(yaml_path)
    assert from_json.model_dump() == from_yaml.model_dump()
    assert from_json.id == SYNTHETIC_PERSONA["id"]
