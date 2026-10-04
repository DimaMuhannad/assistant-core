"""Корпоративный Air-Gap для изоляции конфиденциальных данных и защиты LLM-контекста.

Реализует требования ISO-02 (D-05, D-06):
- Определение принадлежности писем к рабочим пространствам уровня restricted_nda.
- Маскирование конфиденциальных тел, сниппетов и вложений маркером Air-Gap.
"""

from __future__ import annotations

from dataclasses import is_dataclass, replace
from typing import Any

from src.core.domain.entities import WorkspaceClearance

NDA_MASK_MARKER = "[NDA: тело и вложения скрыты Air-Gap]"


def is_nda_email(email_data: dict[str, Any] | Any, persona: Any | None = None) -> bool:
    """Определить, относится ли входящее письмо к контуру restricted_nda (D-05)."""
    if email_data is None:
        return False

    try:
        from src.persona.current import current_persona

        p = persona or current_persona()
    except Exception:
        p = persona

    if p is None:
        return False

    # 1. Проверка явного уровня clearance в данных письма
    clearance = (
        email_data.get("clearance")
        if isinstance(email_data, dict)
        else getattr(email_data, "clearance", None)
    )
    if clearance in ("restricted_nda", WorkspaceClearance.RESTRICTED_NDA):
        return True

    # 2. Проверка явного workspace_id
    ws_id = (
        email_data.get("workspace_id")
        if isinstance(email_data, dict)
        else getattr(email_data, "workspace_id", None)
    )
    workspaces = getattr(p, "workspaces", [])
    if ws_id:
        for ws in workspaces:
            if ws.id == ws_id:
                return getattr(ws, "clearance", None) in (
                    "restricted_nda",
                    WorkspaceClearance.RESTRICTED_NDA,
                )

    # Собираем NDA-пространства текущей персоны
    nda_workspaces = [
        ws
        for ws in workspaces
        if getattr(ws, "clearance", None) in ("restricted_nda", WorkspaceClearance.RESTRICTED_NDA)
    ]
    if not nda_workspaces:
        return False

    # 3. Проверка по account / account_id
    account = (
        email_data.get("account_id") or email_data.get("account")
        if isinstance(email_data, dict)
        else getattr(email_data, "account_id", getattr(email_data, "account", None))
    )
    if account:
        acc_str = str(account).lower()
        for ws in nda_workspaces:
            if ws.id and ws.id.lower() == acc_str:
                return True
            if ws.account and ws.account.lower() in acc_str or acc_str in (ws.account or "").lower():
                return True

    # 4. Проверка по адресам отправителя и получателя (домены/аккаунты организации)
    sender = (
        email_data.get("sender_email") or email_data.get("sender") or email_data.get("from")
        if isinstance(email_data, dict)
        else getattr(email_data, "sender_email", getattr(email_data, "sender", None))
    )
    recipient = (
        email_data.get("recipient") or email_data.get("to")
        if isinstance(email_data, dict)
        else getattr(email_data, "recipient", None)
    )

    targets = [str(x).lower() for x in (sender, recipient) if x]

    # Сбор ключевых маркеров организации из персоны
    org_tokens: set[str] = set()
    orgs = getattr(p, "organizations", {})
    if isinstance(orgs, dict):
        for org in orgs.values():
            name = getattr(org, "name", "")
            if name:
                org_tokens.add(name.lower())
            for alias in getattr(org, "aliases", []):
                if alias:
                    org_tokens.add(str(alias).lower())

    for ws in nda_workspaces:
        if ws.account:
            acc = ws.account.lower()
            # Поиск названия организации/аккаунта в таргетах
            for token in org_tokens:
                if token in acc:
                    for target in targets:
                        if token in target:
                            return True
            for target in targets:
                if ws.id.lower() in target:
                    return True

        # Проверка ключевых слов и подстрок пространства
        for sub in getattr(ws, "forbidden_remote_substrings", []):
            if sub and any(sub.lower() in target for target in targets):
                return True

    return False


def mask_nda_email_data(email_data: dict[str, Any] | Any) -> dict[str, Any] | Any:
    """Очистить конфиденциальные поля письма строкой NDA_MASK_MARKER (D-06)."""
    if isinstance(email_data, dict):
        sanitized = dict(email_data)
        sanitized["body_plain"] = NDA_MASK_MARKER
        sanitized["body_html"] = ""
        sanitized["snippet"] = NDA_MASK_MARKER
        sanitized["attachments"] = []
        if "body" in sanitized:
            sanitized["body"] = NDA_MASK_MARKER
        return sanitized
    elif is_dataclass(email_data):
        fields = {}
        if hasattr(email_data, "body"):
            fields["body"] = NDA_MASK_MARKER
        if hasattr(email_data, "body_plain"):
            fields["body_plain"] = NDA_MASK_MARKER
        if hasattr(email_data, "snippet"):
            fields["snippet"] = NDA_MASK_MARKER
        if hasattr(email_data, "body_html"):
            fields["body_html"] = ""
        if hasattr(email_data, "attachments"):
            fields["attachments"] = ()
        return replace(email_data, **fields)

    return email_data
