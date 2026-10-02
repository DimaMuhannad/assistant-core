"""Pydantic-модели персоны (D-01): строгая схема extra=forbid."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

_ID_PATTERN = r"^[a-z0-9][a-z0-9-]*$"


class PersonaConfigError(ValueError):
    """Ошибка файла персоны; текст не содержит входных значений (в файле бывают NDA-слова)."""


class OrganizationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)


class WorkspaceConfig(BaseModel):
    """Рабочее пространство персоны; правила NDA - данные пространства (D-14, PER-04)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=_ID_PATTERN)
    label: str = Field(min_length=1)
    path: str = Field(min_length=1)
    clearance: Literal["public", "internal", "restricted_nda"]
    account: str = ""
    clearance_label: str = ""
    color: str | None = None
    remote: str | None = None
    forbidden_remote_substrings: list[str] = Field(default_factory=list)
    forbidden_keywords: list[str] = Field(default_factory=list)
    remote_violation_message: str | None = None

    @model_validator(mode="after")
    def _nda_requires_rules(self) -> "WorkspaceConfig":
        # fail-closed: пустые данные не должны молча выключить блокировку NDA (edge D03, OQ7)
        if self.clearance == "restricted_nda" and not (
            self.forbidden_remote_substrings and self.forbidden_keywords
        ):
            raise ValueError(f"пространство restricted_nda {self.id} без правил NDA")
        return self


class PersonaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    display_name: str = Field(min_length=1)
    short_name: str = Field(min_length=1)
    title: str = Field(min_length=1)
    organizations: dict[str, OrganizationConfig]
    default_area: str = Field(min_length=1)
    workspaces: list[WorkspaceConfig] = Field(default_factory=list)

    _source_path: Path | None = PrivateAttr(default=None)

    @field_validator("workspaces")
    @classmethod
    def _workspace_ids_unique(cls, value: list[WorkspaceConfig]) -> list[WorkspaceConfig]:
        ids = [ws.id for ws in value]
        if len(ids) != len(set(ids)):
            raise ValueError("идентификаторы рабочих пространств повторяются")
        return value

    @property
    def source_path(self) -> Path | None:
        return self._source_path

    @property
    def base_dir(self) -> Path | None:
        return self._source_path.parent if self._source_path is not None else None


class PersonaFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persona: PersonaConfig
