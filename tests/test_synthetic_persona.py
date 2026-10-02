"""Тесты каркаса второй синтетической персоны (FND-03, D-14).

Проверяются только сами данные персоны. Проверки, которые подключат персону к реальным
кодовым путям, ожидают Фазы 3 и перечислены текстом в докстринге synthetic_persona.py
и в разделе «Ожидают Фазы 3» документа docs/BASELINE.md.

Файл не зависит от репозитория: он лежит байт-в-байт в обоих тестовых наборах.
"""

import importlib.util
from pathlib import Path
from urllib.parse import urlparse

from .synthetic_persona import SYNTHETIC_PERSONA

# Токены владельца. Одна константа; Фаза 3 (PER-08) заменит её данными персоны по умолчанию.
OWNER_TOKEN_DENYLIST = (
    "ГУАП",
    "GUAP",
    "Тидекс",
    "Tydex",
    "Попов",
    "Дмитрий Александрович",
    "DimaMuhannad",
    "guap.ru",
)

# То, что зашито в коде сегодня. Реальный Telegram ID владельца сюда не копируется
# (персональные данные): отличие проверяется зарезервированным диапазоном.
CURRENT_HARDCODED_DEFAULTS = {
    "display_name": "Попов Дмитрий Александрович",
    "short_name": "Попов Д.А.",
    "title": "доцент кафедры физики, к.ф.-м.н.",
    "organizations.university": "ГУАП",
    "organizations.company": "Тидекс",
    "telegram.bot_username": "opd_guap_popov_bot",
    "timesheet.default_project": "Тидекс",
    "timesheet.daily_norm_hours": 8.5,
    "schedule_source.base_url": "https://guap.ru/rasp",
    "lms.base_url": "https://pro.guap.ru",
    "default_area": "ГУАП",
    "workspace_ids": {"chat-app", "assistant-core", "tydex-optics", "guap-physics"},
    "workspace_paths": {
        "/opt/chat-app",
        "/opt/assistant-core",
        "/opt/work-tydex",
        "/opt/personal/guap-physics",
    },
    "workspace_names": {
        "🤖 Antigravity Web Studio (chat-app)",
        "⚙️ Assistant Core Daemon",
        "🔬 Оптические приборы и измерения (ООО «Тидекс»)",
        "🏛️ Кафедра физики ГУАП (Лабораторные и LMS)",
    },
    "forbidden_remote_substrings": {"github.com/DimaMuhannad"},
    "subject_names": {
        "физические основы нанотехнологий",
        "основы проектной деятельности в профессии",
        "основы проектной деятельности",
        "физика",
    },
    "subject_short_names": {"ФОНТ", "ОПДвП", "ОПД", "Физика"},
    "lesson_slot_starts": {"09:30", "11:10", "13:00", "15:10", "17:00", "18:40", "20:20"},
}

IDENTIFYING_FIELDS = (
    "id",
    "display_name",
    "short_name",
    "title",
    "organizations.university",
    "organizations.company",
    "telegram.authorized_user_id",
    "telegram.bot_username",
    "workspaces",
    "timesheet.default_project",
    "timesheet.daily_norm_hours",
    "schedule_source.base_url",
    "lms.base_url",
    "default_area",
    "subjects",
    "lesson_slots",
)

ALLOWED_CLEARANCES = {"public", "internal", "restricted_nda"}


def _get(data: dict, dotted: str):
    node = data
    for part in dotted.split("."):
        node = node[part]
    return node


def _all_strings(node):
    """Рекурсивно все строки персоны: и ключи, и значения."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _all_strings(key)
            yield from _all_strings(value)
    elif isinstance(node, (list, tuple, set)):
        for item in node:
            yield from _all_strings(item)


def test_fixture_returns_independent_copy(synthetic_persona):
    assert isinstance(synthetic_persona, dict)
    assert synthetic_persona == SYNTHETIC_PERSONA
    assert synthetic_persona is not SYNTHETIC_PERSONA
    before = SYNTHETIC_PERSONA["workspaces"][0]["label"]
    synthetic_persona["workspaces"][0]["label"] = "изменено"
    synthetic_persona["telegram"]["bot_username"] = "изменено"
    assert SYNTHETIC_PERSONA["workspaces"][0]["label"] == before
    assert SYNTHETIC_PERSONA["telegram"]["bot_username"] != "изменено"


def test_identifying_fields_present_and_non_empty(synthetic_persona):
    for path in IDENTIFYING_FIELDS:
        value = _get(synthetic_persona, path)
        assert value not in (None, "", [], {}, ()), f"пустое поле: {path}"
    for workspace in synthetic_persona["workspaces"]:
        for key in ("id", "label", "path", "clearance", "account", "remote"):
            assert workspace.get(key), f"{workspace.get('id')}: пустое поле {key}"
        if workspace["clearance"] == "restricted_nda":
            assert workspace["forbidden_remote_substrings"]
            assert workspace["forbidden_keywords"]


def test_no_owner_tokens(synthetic_persona):
    lowered = [token.lower() for token in OWNER_TOKEN_DENYLIST]
    for text in _all_strings(synthetic_persona):
        low = text.lower()
        for token in lowered:
            assert token not in low, f"токен владельца {token!r} в строке {text!r}"


def test_every_identifying_field_differs_from_current_hardcode(synthetic_persona):
    current = CURRENT_HARDCODED_DEFAULTS
    for path in (
        "display_name",
        "short_name",
        "title",
        "organizations.university",
        "organizations.company",
        "telegram.bot_username",
        "timesheet.default_project",
        "timesheet.daily_norm_hours",
        "schedule_source.base_url",
        "lms.base_url",
        "default_area",
    ):
        assert _get(synthetic_persona, path) != current[path], f"совпадает с зашитым: {path}"

    workspaces = synthetic_persona["workspaces"]
    assert {w["id"] for w in workspaces}.isdisjoint(current["workspace_ids"])
    assert {w["path"] for w in workspaces}.isdisjoint(current["workspace_paths"])
    assert {w["label"] for w in workspaces}.isdisjoint(current["workspace_names"])
    remote_rules = {rule for w in workspaces for rule in w["forbidden_remote_substrings"]}
    assert remote_rules.isdisjoint(current["forbidden_remote_substrings"])
    assert set(synthetic_persona["subjects"]).isdisjoint(current["subject_names"])
    assert set(synthetic_persona["subjects"].values()).isdisjoint(current["subject_short_names"])
    starts = {slot[0] for slot in synthetic_persona["lesson_slots"].values()}
    assert starts.isdisjoint(current["lesson_slot_starts"])
    # Количество рабочих пространств тоже отличается: код не должен рассчитывать на ровно четыре.
    assert len(workspaces) != len(current["workspace_ids"])


def test_clearances_are_exactly_three_levels(synthetic_persona):
    clearances = [w["clearance"] for w in synthetic_persona["workspaces"]]
    assert set(clearances) == ALLOWED_CLEARANCES
    assert all(value in ALLOWED_CLEARANCES for value in clearances)


def test_reserved_synthetic_values(synthetic_persona):
    for workspace in synthetic_persona["workspaces"]:
        assert workspace["path"].startswith("/synthetic/")
    urls = [text for text in _all_strings(synthetic_persona) if text.startswith("http")]
    assert urls, "в персоне нет ни одного URL"
    for url in urls:
        host = urlparse(url).hostname or ""
        assert host.endswith(".example"), f"хост не зарезервирован: {url}"
    user_id = synthetic_persona["telegram"]["authorized_user_id"]
    assert isinstance(user_id, int) and not isinstance(user_id, bool)
    assert 100000000 <= user_id <= 100000999
    assert synthetic_persona["telegram"]["bot_username"].startswith("synthetic")


def _load_shield():
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "scripts" / "security_shield.py"
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location("_persona_security_shield", candidate)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise AssertionError("scripts/security_shield.py не найден выше по дереву каталогов")


def test_no_real_nda_keywords(synthetic_persona):
    # Слова читаются во время теста: в этот файл они не копируются.
    keywords = list(_load_shield().CORPORATE_NDA_KEYWORDS)
    assert keywords, "список NDA-слов пуст - проверка была бы бессмысленной"
    for text in _all_strings(synthetic_persona):
        low = text.lower()
        for word in keywords:
            assert word.lower() not in low, f"реальное NDA-слово в строке {text!r}"
