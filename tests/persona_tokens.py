"""Токены профиля владельца, вычисленные из данных персоны (PER-08, D-16).

Правило копий: у модуля две байт-в-байт одинаковые копии - backend/tests/ в chat-app и tests/ в
assistant-core. Дрейф ловит шаг гейта «токены персоны (дрейф SHA-256)» (scripts/gate.py); копии
существуют до общей библиотеки Фазы 4, править нужно обе одновременно. Только stdlib, без
импортов src и app.

owner_tokens(config) принимает словарь полей персоны (форма model_dump(mode="json") или
personas.config_json) и возвращает классы токенов: name, organization, account, path, domain.
token_classes_in_line(line, tokens) отвечает, токены каких классов встречаются в строке.
Первые потребители: проверка статики index.html (03-06) и сканер хардкода (03-10), который
заменяет denylist каркаса Фазы 1.
"""

from urllib.parse import urlparse

MIN_TOKEN_LENGTH = 3
TOKEN_CLASSES = ("name", "organization", "account", "path", "domain")


def _registrable_domain(url: str) -> str:
    """Две последние метки хоста: pro.guap.ru -> guap.ru; без хоста - пустая строка."""
    parsed = urlparse(url if "//" in url else "//" + url)
    host = (parsed.hostname or "").strip(".")
    labels = [label for label in host.split(".") if label]
    return ".".join(labels[-2:]) if len(labels) >= 2 else ""


def _last_segment(value: str) -> str:
    """Имя аккаунта после хоста: github.com/Someone -> Someone."""
    parts = [part for part in value.strip().strip("/").split("/") if part]
    return parts[-1] if len(parts) >= 2 else ""


def owner_tokens(config: dict) -> dict[str, set[str]]:
    """Токены профиля из данных персоны; токены короче MIN_TOKEN_LENGTH отбрасываются."""
    if isinstance(config.get("persona"), dict):
        config = config["persona"]

    tokens: dict[str, set[str]] = {cls: set() for cls in TOKEN_CLASSES}

    display_name = str(config.get("display_name", "")).strip()
    tokens["name"].update(
        [display_name, str(config.get("short_name", "")).strip()]
        + [str(value).strip() for value in (config.get("name_forms") or {}).values()]
    )
    words = display_name.split()
    if words:
        tokens["name"].add(words[0])  # фамилия
        if len(words) > 1:
            tokens["name"].add(" ".join(words[1:]))  # имя и отчество

    for organization in (config.get("organizations") or {}).values():
        tokens["organization"].add(str(organization.get("name", "")).strip())
        tokens["organization"].update(str(a).strip() for a in organization.get("aliases") or [])

    for workspace in config.get("workspaces") or []:
        for substring in workspace.get("forbidden_remote_substrings") or []:
            tokens["account"].add(_last_segment(str(substring)))
        if workspace.get("clearance") != "public":
            tokens["path"].add(str(workspace.get("path", "")).strip())
    tokens["account"].add(str((config.get("telegram") or {}).get("bot_username") or "").strip())

    for bindings in (config.get("connectors") or {}).values():
        for binding in bindings or []:
            base_url = (binding.get("config") or {}).get("base_url")
            if base_url:
                tokens["domain"].add(_registrable_domain(str(base_url)))

    return {
        cls: {token for token in values if len(token) >= MIN_TOKEN_LENGTH}
        for cls, values in tokens.items()
    }


def token_classes_in_line(line: str, tokens: dict[str, set[str]]) -> set[str]:
    """Классы токенов, хотя бы один токен которых встречается в строке (без учёта регистра)."""
    folded = line.casefold()
    return {
        cls
        for cls, values in tokens.items()
        if any(token.casefold() in folded for token in values)
    }
