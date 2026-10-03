"""PER-09 (промпты): вторая персона на тех же render_prompt и потребителях даёт свои промпты.

Для каждого из 8 ключей шаблонов персоны текст синтетической персоны отличается от текста
персоны по умолчанию, содержит её display_name и не содержит токенов владельца (T-03-27).
Шаблоны синтетической персоны лежат в tests/fixtures/synthetic_prompts (не в data: Pitfall 1).
"""

import json
import shutil
from pathlib import Path

import pytest
from google import genai

from src.persona.current import use_persona
from src.persona.loader import PERSONA_CONFIG_ENV, load_persona
from src.persona.models import PersonaConfig
from src.persona.prompts import render_prompt

from .persona_tokens import owner_tokens
from .synthetic_persona import SYNTHETIC_PERSONA, synthetic_to_config
from .test_prompt_snapshot import RENDER_VARS, TEMPLATE_KEYS, FakeGeminiClient, captured_system_instruction

TEMPLATES_DIR = Path(__file__).parent / "fixtures" / "synthetic_prompts"


@pytest.fixture(autouse=True)
def forbid_real_gemini_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Реальный genai.Client запрещён: тесты работают без сети."""

    def _boom(*args, **kwargs):
        raise AssertionError("реальный genai.Client запрещён в тестах промптов персоны")

    monkeypatch.setattr(genai, "Client", _boom)


@pytest.fixture
def default_persona(monkeypatch: pytest.MonkeyPatch) -> PersonaConfig:
    monkeypatch.delenv(PERSONA_CONFIG_ENV, raising=False)
    return load_persona()


@pytest.fixture
def synthetic_persona_loaded(tmp_path: Path) -> PersonaConfig:
    """Синтетическая персона с 8 собственными шаблонами, загруженная тем же load_persona."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    for key in TEMPLATE_KEYS:
        shutil.copyfile(TEMPLATES_DIR / f"{key}.jinja2", prompts_dir / f"{key}.jinja2")
    config = synthetic_to_config(
        SYNTHETIC_PERSONA, prompts={key: f"prompts/{key}.jinja2" for key in TEMPLATE_KEYS}
    )
    path = tmp_path / "persona.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return load_persona(path)


def _all_tokens(persona: PersonaConfig) -> set[str]:
    classes = owner_tokens(persona.model_dump(mode="json"))
    return {token for values in classes.values() for token in values}


@pytest.mark.parametrize("key", TEMPLATE_KEYS)
def test_synthetic_persona_prompts_differ(
    key: str, default_persona: PersonaConfig, synthetic_persona_loaded: PersonaConfig
) -> None:
    runtime_vars = RENDER_VARS.get(key, {})

    default_text = render_prompt(key, persona=default_persona, **runtime_vars)
    synthetic_text = render_prompt(key, persona=synthetic_persona_loaded, **runtime_vars)

    assert synthetic_text != default_text
    assert synthetic_persona_loaded.display_name in synthetic_text
    folded = synthetic_text.casefold()
    leaked = sorted(token for token in _all_tokens(default_persona) if token.casefold() in folded)
    assert not leaked, f"{key}: в промпте синтетической персоны найдено {len(leaked)} токенов владельца"


def test_synthetic_prompt_templates_have_no_owner_tokens(default_persona: PersonaConfig) -> None:
    tokens = _all_tokens(default_persona)
    files = sorted(TEMPLATES_DIR.glob("*.jinja2"))
    assert {f.stem for f in files} == set(TEMPLATE_KEYS)
    for file in files:
        folded = file.read_text(encoding="utf-8").casefold()
        leaked = [token for token in tokens if token.casefold() in folded]
        assert not leaked, f"{file.name}: найдено {len(leaked)} токенов владельца"


async def test_same_consumer_path_uses_active_persona(
    synthetic_persona_loaded: PersonaConfig, default_persona: PersonaConfig
) -> None:
    """Тот же потребитель (ReplyGenerator) берёт промпт активной персоны."""
    from src.brain.reply_generator import ReplyGenerator

    email = {
        "sender_name": "Студент",
        "sender_email": "student@example.org",
        "subject": "Вопрос",
        "body_plain": "Здравствуйте",
        "category": "guap_student",
    }

    generator = ReplyGenerator(api_key="x")
    fake = FakeGeminiClient()
    generator._client = fake
    with use_persona(synthetic_persona_loaded):
        await generator.generate_reply(email)

    captured = captured_system_instruction(fake)
    assert captured == render_prompt("reply_generator", persona=synthetic_persona_loaded)
    assert captured != render_prompt("reply_generator", persona=default_persona)
