"""PER-09: те же кодовые пути дают для второй (синтетической) персоны другие результаты.

Сводное доказательство независимости платформы от одного человека: промпты секретаря, маршрутизатора
и методиста, рабочие пространства, дефолты (область, табель, расписание, ЛК, каталоги методиста)
и scope-решения методиста. Значения персоны по умолчанию читаются из загруженной персоны, а не из
копий в тестах. Синтетическая персона грузится тем же load_persona через конвертер каркаса Фазы 1
и шаблоны tests/fixtures/synthetic_prompts. В src нет ветвления по id персоны.
"""

from pathlib import Path

import pytest
from google import genai

from src.brain.methodist import MethodistService
from src.persona.bindings import (
    lms_settings,
    methodist_settings,
    schedule_source_settings,
    timesheet_settings,
)
from src.persona.current import use_persona
from src.persona.loader import DEFAULT_PERSONA_PATH, PERSONA_CONFIG_ENV, load_persona
from src.persona.models import PersonaConfig
from src.persona.prompts import render_prompt
from src.storage.db import Database

from .synthetic_persona import SYNTHETIC_PERSONA
from .test_persona_prompts import default_persona, synthetic_persona_loaded  # noqa: F401  (фикстуры)
from .test_prompt_snapshot import RENDER_VARS

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
ALLOWED_CLEARANCES = {"public", "internal", "restricted_nda"}


@pytest.fixture(autouse=True)
def forbid_real_gemini_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Реальный genai.Client запрещён: тесты работают без сети (scope-проверка без ключа)."""

    def _boom(*args, **kwargs):
        raise AssertionError("реальный genai.Client запрещён в тестах PER-09")

    monkeypatch.setattr(genai, "Client", _boom)


def test_default_persona_loads_without_persona_config_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PERSONA_CONFIG_ENV, raising=False)

    persona = load_persona()

    assert persona.source_path == DEFAULT_PERSONA_PATH
    assert persona.id and persona.display_name
    assert persona.id != SYNTHETIC_PERSONA["id"]
    assert persona.display_name != SYNTHETIC_PERSONA["display_name"]


@pytest.mark.parametrize("key", ["secretary", "intent_router", "methodist"])
def test_synthetic_prompts_differ_for_roadmap_three(
    key: str, default_persona: PersonaConfig, synthetic_persona_loaded: PersonaConfig  # noqa: F811
) -> None:
    runtime_vars = RENDER_VARS.get(key, {})

    default_text = render_prompt(key, persona=default_persona, **runtime_vars)
    synthetic_text = render_prompt(key, persona=synthetic_persona_loaded, **runtime_vars)

    assert default_text and synthetic_text
    assert synthetic_text != default_text
    assert synthetic_persona_loaded.display_name in synthetic_text
    assert synthetic_persona_loaded.display_name not in default_text


def test_synthetic_workspaces_differ(
    default_persona: PersonaConfig, synthetic_persona_loaded: PersonaConfig  # noqa: F811
) -> None:
    default_domain = default_persona.to_domain()
    synthetic_domain = synthetic_persona_loaded.to_domain()

    default_ids = {ws.id for ws in default_domain.workspaces}
    synthetic_ids = {ws.id for ws in synthetic_domain.workspaces}
    assert default_ids.isdisjoint(synthetic_ids)
    assert len(default_domain.workspaces) == 4
    assert len(synthetic_domain.workspaces) == 3
    assert {ws.path for ws in default_domain.workspaces}.isdisjoint(
        {ws.path for ws in synthetic_domain.workspaces}
    )
    for persona in (default_persona, synthetic_persona_loaded):
        assert {ws.clearance for ws in persona.workspaces} == ALLOWED_CLEARANCES

    def nda_remote_rules(persona: PersonaConfig) -> set[str]:
        return {
            rule
            for ws in persona.workspaces
            if ws.clearance == "restricted_nda"
            for rule in ws.forbidden_remote_substrings
        }

    default_rules = nda_remote_rules(default_persona)
    synthetic_rules = nda_remote_rules(synthetic_persona_loaded)
    assert default_rules and synthetic_rules
    assert default_rules.isdisjoint(synthetic_rules)


def test_synthetic_defaults_differ(
    default_persona: PersonaConfig, synthetic_persona_loaded: PersonaConfig  # noqa: F811
) -> None:
    assert synthetic_persona_loaded.default_area != default_persona.default_area
    assert {a.value for a in synthetic_persona_loaded.task_areas}.isdisjoint(
        {a.value for a in default_persona.task_areas}
    )
    assert synthetic_persona_loaded.default_area in {a.value for a in synthetic_persona_loaded.task_areas}

    default_timesheet = timesheet_settings(default_persona)
    synthetic_timesheet = timesheet_settings(synthetic_persona_loaded)
    assert synthetic_timesheet.default_project != default_timesheet.default_project
    assert synthetic_timesheet.daily_norm_hours != default_timesheet.daily_norm_hours

    default_schedule = schedule_source_settings(default_persona)
    synthetic_schedule = schedule_source_settings(synthetic_persona_loaded)
    assert synthetic_schedule.base_url != default_schedule.base_url
    assert {s.start for s in synthetic_schedule.lesson_slots}.isdisjoint(
        {s.start for s in default_schedule.lesson_slots}
    )
    assert set(synthetic_schedule.subjects).isdisjoint(default_schedule.subjects)
    assert set(synthetic_schedule.subjects.values()).isdisjoint(default_schedule.subjects.values())

    assert lms_settings(synthetic_persona_loaded).base_url != lms_settings(default_persona).base_url

    default_raw_dir = methodist_settings(default_persona).raw_dir
    with use_persona(synthetic_persona_loaded):
        synthetic_raw_dir = methodist_settings().raw_dir
    assert synthetic_raw_dir != default_raw_dir
    assert methodist_settings(synthetic_persona_loaded).raw_dir == synthetic_raw_dir


async def test_synthetic_scope_decisions_differ(
    default_persona: PersonaConfig, synthetic_persona_loaded: PersonaConfig  # noqa: F811
) -> None:
    """Те же вопросы и тот же MethodistService.check_scope: решения зависят только от персоны."""
    db = Database(db_path=":memory:")
    await db.init_db()
    methodist = MethodistService(db, api_key="")

    default_rules = methodist_settings(default_persona).scope_rules
    synthetic_rules = methodist_settings(synthetic_persona_loaded).scope_rules
    owner_question = f"Расскажи про {default_rules.academic_keywords[0]} и оформление"
    synthetic_company = synthetic_persona_loaded.organizations["company"].name
    synthetic_question = f"Расскажи про {synthetic_company}"

    # вопрос со словом области владельца: у него в области, у синтетической персоны - нет
    default_owner = await methodist.check_scope(owner_question)
    with use_persona(synthetic_persona_loaded):
        synthetic_owner = await methodist.check_scope(owner_question)
    assert default_owner["is_in_scope"] is True and default_owner["category"] == "academic"
    assert synthetic_owner["is_in_scope"] is False
    assert synthetic_owner["category"] != default_owner["category"]

    # вопрос с названием компании синтетической персоны: у неё отказ с её причиной, у владельца - иная причина
    default_company = await methodist.check_scope(synthetic_question)
    with use_persona(synthetic_persona_loaded):
        synthetic_company_decision = await methodist.check_scope(synthetic_question)
    assert synthetic_company_decision["is_in_scope"] is False
    assert synthetic_company_decision["category"] == "out_of_scope"
    assert synthetic_company_decision["reason"] == synthetic_rules.out_of_scope_reason
    assert default_company["reason"] != synthetic_company_decision["reason"]

    # вопрос со словом из out_of_scope владельца: отказ с причиной владельца, у синтетической причина иная
    stop_question = f"Расскажи про {default_rules.out_of_scope_keywords[0]}"
    default_stop = await methodist.check_scope(stop_question)
    with use_persona(synthetic_persona_loaded):
        synthetic_stop = await methodist.check_scope(stop_question)
    assert default_stop["is_in_scope"] is False
    assert default_stop["reason"] == default_rules.out_of_scope_reason
    assert synthetic_stop["reason"] != default_stop["reason"]


def test_no_persona_id_branching_in_src(
    default_persona: PersonaConfig  # noqa: F811
) -> None:
    ids = [default_persona.id, SYNTHETIC_PERSONA["id"]]
    offenders = [
        f"{path.relative_to(SRC_DIR.parent)}: {persona_id}"
        for path in sorted(SRC_DIR.rglob("*.py"))
        for persona_id in ids
        if persona_id in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not offenders, "в src найден литерал id персоны (ветвление по id запрещено):\n" + "\n".join(offenders)


def test_file_catalog_relpath_and_keywords_validated() -> None:
    """WR-06: relpath только внутри raw_dir, ключевые слова нормализуются, пустые отвергаются."""
    import pytest
    from pydantic import ValidationError

    from src.persona.models import FileCatalogEntry

    for bad in ("../x.docx", "/etc/passwd", "a/../../b", "a\\b"):
        with pytest.raises(ValidationError):
            FileCatalogEntry(relpath=bad, desc="d")
    with pytest.raises(ValidationError):
        FileCatalogEntry(relpath="a.docx", desc="d", keywords=[" "])
    entry = FileCatalogEntry(relpath="a/b.docx", desc="d", keywords=["  АбВ "])
    assert entry.keywords == ["абв"]
