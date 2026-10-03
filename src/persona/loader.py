"""Единственный загрузчик персоны (D-01): yaml.safe_load + Pydantic extra=forbid."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import yaml
from pydantic import ValidationError

from src.persona.models import PersonaConfig, PersonaConfigError, PersonaFile

PERSONA_CONFIG_ENV = "PERSONA_CONFIG_PATH"
DEFAULT_PERSONA_PATH = Path(__file__).resolve().parents[2] / "config" / "persona.yaml"


def resolve_persona_path(
    path: str | Path | None = None, env: Mapping[str, str] | None = None
) -> Path:
    """Явный путь, затем непустая PERSONA_CONFIG_PATH, затем файл по умолчанию."""
    if path is not None and str(path) != "":
        return Path(path)
    environ = os.environ if env is None else env
    from_env = environ.get(PERSONA_CONFIG_ENV, "").strip()
    if from_env:
        return Path(from_env)
    return DEFAULT_PERSONA_PATH


def _format_validation_error(path: Path, err: ValidationError) -> str:
    # Только loc и msg: input_value нельзя выводить (в файле будут NDA-слова).
    lines = [f"файл персоны {path} не прошёл проверку:"]
    for item in err.errors(include_input=False, include_url=False, include_context=False):
        loc = ".".join(str(part) for part in item["loc"])
        lines.append(f"поле {loc}: {item['msg']}")
    return "\n".join(lines)


def load_persona(
    path: str | Path | None = None, *, env: Mapping[str, str] | None = None
) -> PersonaConfig:
    resolved = resolve_persona_path(path, env)
    try:
        text = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        reason = getattr(exc, "strerror", None) or "содержимое не в кодировке UTF-8"
        raise PersonaConfigError(f"файл персоны {resolved} не прочитан: {reason}") from None
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f", строка {mark.line + 1}" if mark is not None else ""
        raise PersonaConfigError(f"файл персоны {resolved}: ошибка разбора YAML{where}") from None
    try:
        parsed = PersonaFile.model_validate(raw)
    except ValidationError as exc:
        raise PersonaConfigError(_format_validation_error(resolved, exc)) from None
    persona = parsed.persona
    persona._source_path = resolved
    _check_template_files(resolved, persona)
    return persona


def _check_template_files(resolved: Path, persona: PersonaConfig) -> None:
    """Каждый шаблон persona.prompts - существующий файл внутри каталога персоны (T-03-23)."""
    base = resolved.parent.resolve()
    for key, relpath in persona.prompts.items():
        target = (resolved.parent / relpath).resolve()  # resolve() раскрывает symlink
        if not target.is_relative_to(base) or not target.is_file():
            raise PersonaConfigError(
                f"файл персоны {resolved}: шаблон «{key}» ({relpath}) "
                "не найден внутри каталога персоны"
            )
