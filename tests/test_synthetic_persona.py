"""Тесты каркаса второй синтетической персоны (FND-03, D-14; PER-08, D-16).

Проверяются данные синтетической персоны против данных персоны по умолчанию (фикстура
default_persona_config): токены профиля и отличия вычисляются из персоны, а не из копий
в тестах. Проверки, которые подключают персону к реальным кодовым путям, включены в Фазе 3
(список в докстринге synthetic_persona.py и в разделе «Включено в Фазе 3» docs/BASELINE.md).

Файл не зависит от репозитория: он лежит байт-в-байт в обоих тестовых наборах.
"""

from urllib.parse import urlparse

from .persona_tokens import owner_tokens
from .synthetic_persona import SYNTHETIC_PERSONA, synthetic_to_config

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


def test_no_owner_tokens(synthetic_persona, default_persona_config):
    tokens = {
        token.casefold()
        for values in owner_tokens(default_persona_config).values()
        for token in values
    }
    assert tokens, "токены персоны по умолчанию не вычислены - проверка была бы бессмысленной"
    for text in _all_strings(synthetic_persona):
        low = text.casefold()
        for token in tokens:
            assert token not in low, f"токен профиля владельца (длина {len(token)}) в строке {text!r}"


def _default_view(default: dict) -> dict:
    """Поля персоны по умолчанию в тех же координатах, что и у словаря каркаса."""
    schedule = default["connectors"]["schedule_source"][0]["config"]
    timesheet = default["connectors"]["timesheet"][0]["config"]
    workspaces = default["workspaces"]
    return {
        "display_name": default["display_name"],
        "short_name": default["short_name"],
        "title": default["title"],
        "organizations.university": default["organizations"]["university"]["name"],
        "organizations.company": default["organizations"]["company"]["name"],
        "telegram.bot_username": default["telegram"]["bot_username"],
        "timesheet.default_project": timesheet["default_project"],
        "timesheet.daily_norm_hours": timesheet["daily_norm_hours"],
        "schedule_source.base_url": schedule["base_url"],
        "lms.base_url": default["connectors"]["lms"][0]["config"]["base_url"],
        "default_area": default["default_area"],
        "workspace_ids": {w["id"] for w in workspaces},
        "workspace_paths": {w["path"] for w in workspaces},
        "workspace_names": {w["label"] for w in workspaces},
        "forbidden_remote_substrings": {
            rule for w in workspaces for rule in w.get("forbidden_remote_substrings") or []
        },
        "subject_names": set(schedule["subjects"]),
        "subject_short_names": set(schedule["subjects"].values()),
        "lesson_slot_starts": {str(slot["start"]) for slot in schedule["lesson_slots"]},
    }


def test_every_identifying_field_differs_from_default_persona(synthetic_persona, default_persona_config):
    current = _default_view(default_persona_config)
    # Синтетическая персона проходит через тот же конвертер, что и в тестах Фазы 3.
    assert synthetic_to_config(synthetic_persona)["persona"]["id"] != default_persona_config["id"]
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
        assert _get(synthetic_persona, path) != current[path], f"совпадает с персоной по умолчанию: {path}"

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


def test_no_real_nda_keywords(synthetic_persona, default_persona_config):
    # Слова NDA - данные пространств персоны по умолчанию (forbidden_keywords): в этот файл они не копируются.
    keywords = [
        word
        for workspace in default_persona_config["workspaces"]
        for word in (workspace.get("forbidden_keywords") or [])
    ]
    assert keywords, "список NDA-слов пуст - проверка была бы бессмысленной"
    for text in _all_strings(synthetic_persona):
        low = text.lower()
        for word in keywords:
            assert word.lower() not in low, f"реальное NDA-слово в строке {text!r}"
