"""Рендер системных промптов из Jinja2-шаблонов персоны (PER-07, D-08, D-09).

Шаблоны лежат рядом с файлом персоны (поле prompts: ключ -> относительный путь) и
рендерятся в песочнице: SandboxedEnvironment, StrictUndefined (неизвестная переменная -
ошибка, а не пустая строка), без автоэкранирования (текст уходит в LLM, не в HTML) и с
сохранением завершающего перевода строки (иначе текст промпта изменится).

Персона читается в момент вызова (current_persona), не при импорте (Pitfall 8).
Пользовательский ввод передаётся переменной шаблона, а не частью его текста (T-03-22).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from jinja2 import FileSystemLoader, StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment

from src.persona.current import current_persona
from src.persona.models import PersonaConfig, PersonaConfigError


@lru_cache(maxsize=8)
def _environment(base_dir: str) -> SandboxedEnvironment:
    return SandboxedEnvironment(
        loader=FileSystemLoader(base_dir),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
    )


def render_prompt(
    key: str, persona: PersonaConfig | None = None, **runtime_vars: Any
) -> str:
    """Отрендерить шаблон `key` персоны; `persona` по умолчанию - текущая персона процесса."""
    persona = persona if persona is not None else current_persona()
    relpath = persona.prompts.get(key)
    if relpath is None:
        raise PersonaConfigError(f"в персоне {persona.id} нет шаблона «{key}»")
    base_dir = persona.base_dir
    if base_dir is None:
        raise PersonaConfigError(
            f"персона {persona.id} создана не из файла: каталог шаблонов неизвестен"
        )
    # persona задаётся последней: runtime-переменные не подменяют данные персоны
    context = {**runtime_vars, "persona": persona.model_dump(mode="json")}
    try:
        template = _environment(str(base_dir)).get_template(relpath)
        return template.render(context)
    except TemplateError as exc:
        # без значений контекста: в персоне бывают NDA-слова; только ключ и тип ошибки
        raise PersonaConfigError(
            f"шаблон «{key}» персоны {persona.id} не отрендерен: {type(exc).__name__}"
        ) from None
