"""Pydantic-модели персоны (D-01): строгая схема extra=forbid."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


class PersonaConfigError(ValueError):
    """Ошибка файла персоны; текст не содержит входных значений (в файле бывают NDA-слова)."""


class OrganizationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)


class PersonaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    display_name: str = Field(min_length=1)
    short_name: str = Field(min_length=1)
    title: str = Field(min_length=1)
    organizations: dict[str, OrganizationConfig]
    default_area: str = Field(min_length=1)

    _source_path: Path | None = PrivateAttr(default=None)

    @property
    def source_path(self) -> Path | None:
        return self._source_path

    @property
    def base_dir(self) -> Path | None:
        return self._source_path.parent if self._source_path is not None else None


class PersonaFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persona: PersonaConfig
