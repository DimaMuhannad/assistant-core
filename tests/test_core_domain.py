"""Тесты доменных сущностей ядра (PRT-01, D-03, D-05)."""

import dataclasses
from datetime import date, datetime

import pytest

from src.core.domain.entities import (
    AcademicSubmission,
    EmailMessage,
    Persona,
    ScheduleEvent,
    Task,
    WorkRecord,
    Workspace,
    WorkspaceClearance,
)

NOW = datetime(2026, 3, 2, 9, 0)

WORKSPACE = Workspace(id="w", name="W", clearance=WorkspaceClearance.PUBLIC, path="/p")

# (экземпляр, имя поля для попытки присваивания)
SAMPLES = [
    (ScheduleEvent(external_id="e", title="t", starts_at=NOW, ends_at=NOW), "title"),
    (WorkRecord(shift_date=date(2026, 3, 2), hours=8.5, project_tag="tag"), "hours"),
    (AcademicSubmission(submission_id="s", title="t", deadline=None, is_public=False), "title"),
    (Task(title="t", area="a", status="open"), "status"),
    (EmailMessage(message_id="m", subject="s", sender="x", received_at=NOW), "subject"),
    (WORKSPACE, "name"),
    (Persona(id="p", name="n"), "name"),
]
IDS = [type(s).__name__ for s, _ in SAMPLES]


def test_workspace_clearance_has_exactly_three_values():
    values = {c.value for c in WorkspaceClearance}
    assert values == {"public", "internal", "restricted_nda"}
    assert len(WorkspaceClearance) == 3
    assert WorkspaceClearance("public") is WorkspaceClearance.PUBLIC


def test_workspace_clearance_rejects_unknown_value():
    with pytest.raises(ValueError):
        WorkspaceClearance("secret")


@pytest.mark.parametrize(("instance", "field"), SAMPLES, ids=IDS)
def test_entities_are_frozen(instance, field):
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(instance, field, getattr(instance, field))


@pytest.mark.parametrize(("instance", "field"), SAMPLES, ids=IDS)
def test_entities_use_slots(instance, field):
    assert not hasattr(instance, "__dict__")


def test_work_record_requires_project_tag():
    with pytest.raises(TypeError):
        WorkRecord(shift_date=date(2026, 3, 2), hours=8.5)  # type: ignore[call-arg]


def test_task_area_is_free_string():
    assert Task(title="t", area="research", status="open").area == "research"
    assert Task(title="t", area="что-угодно", status="open").area == "что-угодно"


def test_persona_workspaces_is_tuple_and_hashable():
    empty = Persona(id="p", name="n")
    assert empty.workspaces == ()
    assert isinstance(empty.workspaces, tuple)
    hash(Persona(id="p", name="n", workspaces=(WORKSPACE,)))


def test_synthetic_workspaces_map_to_clearance(synthetic_persona):
    spaces = synthetic_persona["workspaces"]
    workspaces = tuple(
        Workspace(
            id=w["id"],
            name=w["label"],
            clearance=WorkspaceClearance(w["clearance"]),
            path=w["path"],
            remote=w.get("remote"),
        )
        for w in spaces
    )
    persona = Persona(
        id=synthetic_persona["id"],
        name=synthetic_persona["display_name"],
        workspaces=workspaces,
    )
    assert {w.clearance for w in persona.workspaces} == set(WorkspaceClearance)
    assert len(persona.workspaces) == len(spaces)
