"""Pydantic-модели персоны (D-01): строгая схема extra=forbid."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    field_validator,
    model_validator,
)

if TYPE_CHECKING:
    from src.core.domain.entities import Persona

_ID_PATTERN = r"^[a-z0-9][a-z0-9-]*$"
# Единственная допустимая форма идентификатора Telegram в файле персоны (D-05): ${ИМЯ_ПЕРЕМЕННОЙ}.
_ENV_PLACEHOLDER = re.compile(r"^\$\{([A-Z][A-Z0-9_]*)\}$")
_DIGITS = re.compile(r"^[0-9]+$")


class PersonaConfigError(ValueError):
    """Ошибка файла персоны; текст не содержит входных значений (в файле бывают NDA-слова)."""


def _normalize_keywords(value: list[str]) -> list[str]:
    """Ключевые слова сравниваются с `.lower()` запроса: приводим так же; пустые отвергаем (WR-06)."""
    normalized = [item.strip().lower() for item in value]
    if any(not item for item in normalized):
        raise ValueError("ключевое слово не может быть пустым (совпало бы с любым запросом)")
    return normalized


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


class TelegramConfig(BaseModel):
    """Telegram персоны: идентификаторы только плейсхолдерами ${VAR} (PER-01, D-05)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    authorized_user_ids: list[str] = Field(default_factory=list)
    bot_username: str | None = None

    @field_validator("authorized_user_ids")
    @classmethod
    def _only_env_placeholders(cls, value: list[str]) -> list[str]:
        for item in value:
            if not _ENV_PLACEHOLDER.match(item):
                # значение не печатается: литерал мог быть настоящим идентификатором
                raise ValueError("идентификатор Telegram задаётся только плейсхолдером ${ИМЯ}")
        return value


class TaskAreaConfig(BaseModel):
    """Область задач: подпись формы и (отдельно) подпись кнопки фильтра (OQ3)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str = Field(min_length=1)
    label: str = Field(min_length=1)
    filter_label: str | None = None
    show_in_filter: bool = True


class UiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    texts: dict[str, str] = Field(default_factory=dict)


class ConnectorBindingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(default="main", min_length=1)
    provider: str = Field(min_length=1)
    scopes: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


_HHMM = r"^[0-9]{2}:[0-9]{2}$"
_HTTP_URL = r"^https?://\S+$"


class _LessonSlotParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    number: int = Field(ge=1)
    # строка, не число: незакавыченное 11:10 PyYAML (YAML 1.1) читает как 670 - это ошибка схемы
    start: str = Field(pattern=_HHMM)
    end: str | None = Field(default=None, pattern=_HHMM)


class _ScheduleSourceParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: str = Field(pattern=_HTTP_URL)
    lesson_slots: list[_LessonSlotParams]
    subjects: dict[str, str]


class _TimesheetParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    default_project: str = Field(min_length=1)
    daily_norm_hours: float = Field(gt=0)


class _LmsParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: str = Field(pattern=_HTTP_URL)


# Параметры привязок по ролям (WR-04): проверяются при загрузке, а не в момент вызова.
_ROLE_PARAMS: dict[str, type[BaseModel]] = {
    "schedule_source": _ScheduleSourceParams,
    "timesheet": _TimesheetParams,
    "lms": _LmsParams,
}


class ConnectorsConfig(BaseModel):
    """Привязки по ролям; ключи совпадают с ConnectorRole, на роль допускается несколько (PER-02)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schedule_source: list[ConnectorBindingConfig] = Field(default_factory=list)
    calendar_sync: list[ConnectorBindingConfig] = Field(default_factory=list)
    timesheet: list[ConnectorBindingConfig] = Field(default_factory=list)
    lms: list[ConnectorBindingConfig] = Field(default_factory=list)
    git_source: list[ConnectorBindingConfig] = Field(default_factory=list)
    notion: list[ConnectorBindingConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _binding_ids_unique_within_role(self) -> "ConnectorsConfig":
        for role in type(self).model_fields:
            ids = [binding.id for binding in getattr(self, role)]
            if len(ids) != len(set(ids)):
                raise ValueError(f"идентификаторы привязок роли {role} повторяются")
        return self

    @model_validator(mode="after")
    def _role_params_valid(self) -> "ConnectorsConfig":
        for role, params_model in _ROLE_PARAMS.items():
            for binding in getattr(self, role):
                try:
                    params_model.model_validate(binding.config)
                except ValidationError as exc:
                    # только loc и msg: значения конфигурации не печатаются
                    details = "; ".join(
                        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                        for item in exc.errors(
                            include_input=False, include_url=False, include_context=False
                        )
                    )
                    raise ValueError(
                        f"параметры привязки {role} ({binding.id}) некорректны: {details}"
                    ) from None
        return self


class FileCatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    relpath: str = Field(min_length=1)
    desc: str = Field(min_length=1)
    keywords: list[str] = Field(default_factory=list)

    @field_validator("relpath")
    @classmethod
    def _relpath_inside_raw_dir(cls, value: str) -> str:
        # форма пути: относительный, без «..» (иначе Path.__truediv__ выведет за raw_dir)
        pure = PurePosixPath(value)
        if not value.strip() or "\\" in value or pure.is_absolute() or ".." in pure.parts:
            raise ValueError("relpath должен быть относительным путём внутри raw_dir")
        return value

    @field_validator("keywords")
    @classmethod
    def _keywords_normalized(cls, value: list[str]) -> list[str]:
        return _normalize_keywords(value)


class ScopeRulesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    out_of_scope_keywords: list[str] = Field(default_factory=list)
    academic_keywords: list[str] = Field(default_factory=list)
    out_of_scope_reason: str = Field(min_length=1)

    @field_validator("out_of_scope_keywords", "academic_keywords")
    @classmethod
    def _keywords_normalized(cls, value: list[str]) -> list[str]:
        return _normalize_keywords(value)


class MethodistConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_dir: str = Field(min_length=1)
    kb_dir: str = Field(min_length=1)
    file_catalog: list[FileCatalogEntry] = Field(default_factory=list)
    scope_rules: ScopeRulesConfig


class PersonaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    display_name: str = Field(min_length=1)
    short_name: str = Field(min_length=1)
    title: str = Field(min_length=1)
    organizations: dict[str, OrganizationConfig]
    default_area: str = Field(min_length=1)
    name_forms: dict[str, str] = Field(default_factory=dict)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    task_areas: list[TaskAreaConfig]
    ui: UiConfig = Field(default_factory=UiConfig)
    workspaces: list[WorkspaceConfig] = Field(default_factory=list)
    connectors: ConnectorsConfig = Field(default_factory=ConnectorsConfig)
    methodist: MethodistConfig
    prompts: dict[str, str] = Field(default_factory=dict)  # ключ -> путь шаблона .jinja2 (D-09)
    gemini_keys: list[str] = Field(default_factory=list)

    _source_path: Path | None = PrivateAttr(default=None)

    @field_validator("workspaces")
    @classmethod
    def _workspace_ids_unique(cls, value: list[WorkspaceConfig]) -> list[WorkspaceConfig]:
        ids = [ws.id for ws in value]
        if len(ids) != len(set(ids)):
            raise ValueError("идентификаторы рабочих пространств повторяются")
        return value

    @field_validator("prompts")
    @classmethod
    def _prompt_paths_relative(cls, value: dict[str, str]) -> dict[str, str]:
        # форма пути; существование и выход за каталог (symlink) проверяет загрузчик (T-03-23)
        for key, relpath in value.items():
            pure = PurePosixPath(relpath)
            if (
                not relpath.strip()
                or "\\" in relpath
                or pure.is_absolute()
                or ".." in pure.parts
                or pure.suffix != ".jinja2"
            ):
                raise ValueError(
                    f"путь шаблона {key} должен быть относительным, внутри каталога персоны, "
                    "с расширением .jinja2"
                )
        return value

    @model_validator(mode="after")
    def _areas_consistent(self) -> "PersonaConfig":
        values = [area.value for area in self.task_areas]
        if len(values) != len(set(values)):
            raise ValueError("значения task_areas повторяются")
        if self.default_area not in values:
            raise ValueError("default_area не входит в task_areas")
        return self

    def _env_names(self) -> tuple[str, ...]:
        return tuple(
            match.group(1)
            for item in self.telegram.authorized_user_ids
            if (match := _ENV_PLACEHOLDER.match(item))
        )

    def unresolved_env_vars(self, env: Mapping[str, str] | None = None) -> tuple[str, ...]:
        """Имена переменных, не заданных (или пустых) в окружении; значения не возвращаются."""
        environ = os.environ if env is None else env
        return tuple(name for name in self._env_names() if not environ.get(name, "").strip())

    def resolve_authorized_user_ids(
        self, env: Mapping[str, str] | None = None, *, strict: bool = False
    ) -> tuple[int, ...]:
        """Развернуть плейсхолдеры в момент вызова; пустое значение в результат не попадает."""
        environ = os.environ if env is None else env
        resolved: list[int] = []
        for name in self._env_names():
            raw = environ.get(name, "").strip()
            if not raw:
                if strict:
                    raise PersonaConfigError(f"переменная окружения {name} не задана")
                continue
            if not _DIGITS.match(raw):
                raise PersonaConfigError(f"переменная окружения {name} не число")
            resolved.append(int(raw))
        return tuple(resolved)

    def to_domain(self) -> "Persona":
        from src.core.domain.entities import Persona, Workspace, WorkspaceClearance

        return Persona(
            id=self.id,
            name=self.display_name,
            workspaces=tuple(
                Workspace(
                    id=ws.id,
                    name=ws.label,
                    clearance=WorkspaceClearance(ws.clearance),
                    path=ws.path,
                    remote=ws.remote,
                )
                for ws in self.workspaces
            ),
        )

    @property
    def source_path(self) -> Path | None:
        return self._source_path

    @property
    def base_dir(self) -> Path | None:
        return self._source_path.parent if self._source_path is not None else None


class PersonaFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persona: PersonaConfig
