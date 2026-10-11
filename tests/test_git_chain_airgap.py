"""Тесты матрицы допуска и ужесточённого шлюза git_chain_workspaces (план 04-05, GIT-01, GIT-04)."""

from pathlib import Path, PurePath
import pytest

from src.core.domain.entities import Persona, Workspace, WorkspaceClearance
from src.persona.loader import load_persona
from src.security.airgap import is_git_chain_eligible, git_chain_workspaces

from .synthetic_persona import SYNTHETIC_PERSONA, synthetic_to_config


class _BrokenClearance:
    @property
    def clearance(self):
        raise RuntimeError("faulty clearance property")


def test_is_git_chain_eligible_matrix() -> None:
    # 1. public и internal (как str и как StrEnum) -> True
    assert is_git_chain_eligible(Workspace(id="1", name="1", clearance=WorkspaceClearance.PUBLIC, path="/p")) is True
    assert is_git_chain_eligible(Workspace(id="2", name="2", clearance=WorkspaceClearance.INTERNAL, path="/p")) is True
    assert is_git_chain_eligible({"clearance": "public"}) is True
    assert is_git_chain_eligible({"clearance": "internal"}) is True
    assert is_git_chain_eligible({"clearance": WorkspaceClearance.PUBLIC}) is True
    assert is_git_chain_eligible({"clearance": WorkspaceClearance.INTERNAL}) is True

    # 2. restricted_nda, weird, пустая строка, None -> False
    assert is_git_chain_eligible(Workspace(id="3", name="3", clearance=WorkspaceClearance.RESTRICTED_NDA, path="/p")) is False
    assert is_git_chain_eligible({"clearance": "restricted_nda"}) is False
    assert is_git_chain_eligible({"clearance": WorkspaceClearance.RESTRICTED_NDA}) is False
    assert is_git_chain_eligible({"clearance": "weird"}) is False
    assert is_git_chain_eligible({"clearance": ""}) is False
    assert is_git_chain_eligible(None) is False
    assert is_git_chain_eligible({"clearance": None}) is False

    # 3. Объект без атрибута clearance, объект с исключением в property clearance -> False
    assert is_git_chain_eligible(object()) is False
    assert is_git_chain_eligible({}) is False
    assert is_git_chain_eligible(_BrokenClearance()) is False


def test_git_chain_overlap_remote() -> None:
    # Допущенное пространство с тем же remote (включая .git и разный регистр), что у NDA, исключается
    nda_ws = Workspace(
        id="nda",
        name="NDA",
        clearance=WorkspaceClearance.RESTRICTED_NDA,
        path="/nda/repo",
        remote="git@github.com:Secret/Repo.git",
    )
    public_same_remote = Workspace(
        id="pub",
        name="PUB",
        clearance=WorkspaceClearance.PUBLIC,
        path="/pub/repo",
        remote="git@github.com:secret/repo",
    )
    persona = Persona(id="p", name="n", workspaces=(nda_ws, public_same_remote))

    split = git_chain_workspaces(persona)
    assert split.unresolved is False
    assert split.eligible == ()
    assert split.excluded_count == 2


def test_git_chain_overlap_alias() -> None:
    # Допущенное пространство с тем же ssh_alias, что у NDA, исключается
    nda_ws = Workspace(
        id="nda",
        name="NDA",
        clearance=WorkspaceClearance.RESTRICTED_NDA,
        path="/nda/repo",
        ssh_alias="Secret-Host",
    )
    public_same_alias = Workspace(
        id="pub",
        name="PUB",
        clearance=WorkspaceClearance.PUBLIC,
        path="/pub/repo",
        ssh_alias="secret-host",
    )
    persona = Persona(id="p", name="n", workspaces=(nda_ws, public_same_alias))

    split = git_chain_workspaces(persona)
    assert split.unresolved is False
    assert split.eligible == ()
    assert split.excluded_count == 2


def test_git_chain_overlap_path_equal() -> None:
    # Допущенное пространство с тем же path (с учётом регистра/слэшей), что у NDA, исключается
    nda_ws = Workspace(
        id="nda",
        name="NDA",
        clearance=WorkspaceClearance.RESTRICTED_NDA,
        path="/var/repos/project/",
    )
    public_same_path = Workspace(
        id="pub",
        name="PUB",
        clearance=WorkspaceClearance.PUBLIC,
        path="/var/repos/project",
    )
    persona = Persona(id="p", name="n", workspaces=(nda_ws, public_same_path))

    split = git_chain_workspaces(persona)
    assert split.unresolved is False
    assert split.eligible == ()
    assert split.excluded_count == 2


def test_git_chain_overlap_path_nested() -> None:
    # Допущенное пространство с path, вложенным в путь NDA или содержащим его, исключается
    nda_ws = Workspace(
        id="nda",
        name="NDA",
        clearance=WorkspaceClearance.RESTRICTED_NDA,
        path="/var/repos/nda_parent",
    )
    public_nested = Workspace(
        id="pub",
        name="PUB",
        clearance=WorkspaceClearance.PUBLIC,
        path="/var/repos/nda_parent/sub_repo",
    )
    persona = Persona(id="p", name="n", workspaces=(nda_ws, public_nested))

    split = git_chain_workspaces(persona)
    assert split.unresolved is False
    assert split.eligible == ()
    assert split.excluded_count == 2

    # И наоборот: публичный родитель содержит NDA внутри
    pub_parent = Workspace(
        id="pub_parent",
        name="PUB Parent",
        clearance=WorkspaceClearance.PUBLIC,
        path="/var/repos/nda_parent",
    )
    nda_nested = Workspace(
        id="nda_child",
        name="NDA Child",
        clearance=WorkspaceClearance.RESTRICTED_NDA,
        path="/var/repos/nda_parent/sub_nda",
    )
    persona2 = Persona(id="p2", name="n2", workspaces=(pub_parent, nda_nested))

    split2 = git_chain_workspaces(persona2)
    assert split2.unresolved is False
    assert split2.eligible == ()
    assert split2.excluded_count == 2


def test_git_chain_non_overlap_kept() -> None:
    # Непересекающиеся пространства остаются
    nda_ws = Workspace(
        id="nda",
        name="NDA",
        clearance=WorkspaceClearance.RESTRICTED_NDA,
        path="/var/nda",
        remote="git@corp.example:nda/repo.git",
        ssh_alias="corp-ssh",
    )
    public_ws = Workspace(
        id="pub",
        name="PUB",
        clearance=WorkspaceClearance.PUBLIC,
        path="/var/public",
        remote="https://github.com/owner/open.git",
        ssh_alias="github-ssh",
    )
    internal_ws = Workspace(
        id="internal",
        name="INT",
        clearance=WorkspaceClearance.INTERNAL,
        path="/var/internal",
        remote="https://git.internal.example/dep/proj.git",
        ssh_alias=None,
    )
    persona = Persona(id="p", name="n", workspaces=(nda_ws, public_ws, internal_ws))

    split = git_chain_workspaces(persona)
    assert split.unresolved is False
    assert len(split.eligible) == 2
    assert split.eligible == (public_ws, internal_ws)
    assert split.excluded_count == 1


def test_git_chain_unresolved_handling() -> None:
    # 1. persona is None -> unresolved=True
    split_none = git_chain_workspaces(None)
    assert split_none.unresolved is True
    assert split_none.eligible == ()
    assert split_none.excluded_count == 0

    # 2. Исключение в to_domain() -> unresolved=True
    class BrokenPersona:
        def to_domain(self):
            raise RuntimeError("to_domain failed")

    split_err = git_chain_workspaces(BrokenPersona())
    assert split_err.unresolved is True
    assert split_err.eligible == ()
    assert split_err.excluded_count == 0

    # 3. Пустой список пространств -> unresolved=False, eligible=(), excluded_count=0
    empty_persona = Persona(id="p", name="n", workspaces=())
    split_empty = git_chain_workspaces(empty_persona)
    assert split_empty.unresolved is False
    assert split_empty.eligible == ()
    assert split_empty.excluded_count == 0
