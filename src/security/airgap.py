"""Корпоративный Air-Gap для изоляции конфиденциальных данных и защиты LLM-контекста.

Реализует требования ISO-02 (D-05, D-06):
- Определение принадлежности писем к рабочим пространствам уровня restricted_nda.
- Маскирование конфиденциальных тел, сниппетов и вложений маркером Air-Gap.
"""

from __future__ import annotations

from dataclasses import dataclass, is_dataclass, replace
import os
from pathlib import PurePath
from typing import Any

from src.core.domain.entities import GitCommit, WorkspaceClearance

GIT_CHAIN_ELIGIBLE_CLEARANCES: frozenset[str] = frozenset({"public", "internal"})

NDA_MASK_MARKER = "[NDA: тело и вложения скрыты Air-Gap]"
NDA_GIT_MASK_MARKER = "[NDA: сообщение коммита скрыто Air-Gap]"


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


def is_nda_workspace(workspace: Any, persona: Any | None = None) -> bool:
    """Определить, относится ли рабочее пространство к контуру restricted_nda (D-05)."""
    if workspace is None:
        return False

    # Если передан clearance напрямую (строка или enum)
    if workspace in ("restricted_nda", WorkspaceClearance.RESTRICTED_NDA):
        return True

    # Если передан объект Workspace или dict
    clearance = (
        workspace.get("clearance")
        if isinstance(workspace, dict)
        else getattr(workspace, "clearance", None)
    )
    if clearance in ("restricted_nda", WorkspaceClearance.RESTRICTED_NDA):
        return True

    # Если передан ID пространства (строка), ищем в персоне
    ws_id = (
        workspace.get("id")
        if isinstance(workspace, dict)
        else (getattr(workspace, "id", None) or (workspace if isinstance(workspace, str) else None))
    )

    try:
        from src.persona.current import current_persona

        p = persona or current_persona()
    except Exception:
        p = persona

    if p and ws_id:
        for ws in getattr(p, "workspaces", ()):
            if getattr(ws, "id", None) == ws_id:
                return getattr(ws, "clearance", None) in (
                    "restricted_nda",
                    WorkspaceClearance.RESTRICTED_NDA,
                )

    return False


def sanitize_git_commits_for_llm(
    workspace: Any,
    commits: list[GitCommit],
    persona: Any | None = None,
) -> list[GitCommit]:
    """Маскирование коммитов NDA-репозиториев перед передачей в контекст LLM (GIT-04)."""
    if not is_nda_workspace(workspace, persona):
        return commits

    sanitized: list[GitCommit] = []
    for c in commits:
        sanitized.append(
            GitCommit(
                hash=c.hash,
                author=c.author,
                date=c.date,
                message=NDA_GIT_MASK_MARKER,
                files_changed=0,
                insertions=0,
                deletions=0,
            )
        )
    return sanitized


def sanitize_notion_payload_for_airgap(
    workspace: Any,
    payload: dict[str, Any],
    persona: Any | None = None,
) -> dict[str, Any]:
    """Санитизация полезной нагрузки для Notion: для restricted_nda исключает детали коммитов и оставляет только агрегаты."""
    if not is_nda_workspace(workspace, persona):
        return payload

    clean = dict(payload)
    clean.pop("commits", None)
    clean.pop("messages", None)
    clean.pop("files", None)
    clean.pop("branches", None)
    commit_count = clean.get("commit_count", 0)
    clean["summary"] = f"Проект находится под защитой Air-Gap (NDA). Зафиксировано {commit_count} коммитов."
    return clean


def is_git_chain_eligible(workspace: Any) -> bool:
    """Определить, допущено ли рабочее пространство к цепочке Git -> LLM -> Notion (D-12, D-13).
    
    Fail-closed: разрешены только явные public и internal. Любые ошибки, None или
    неизвестные значения допуска возвращают False.
    """
    if workspace is None:
        return False

    try:
        clearance = (
            workspace.get("clearance")
            if isinstance(workspace, dict)
            else getattr(workspace, "clearance", None)
        )
        if clearance is None:
            return False

        val = clearance.value if hasattr(clearance, "value") else str(clearance)
        return val in GIT_CHAIN_ELIGIBLE_CLEARANCES
    except Exception:
        return False


@dataclass(frozen=True, slots=True)
class GitChainSplit:
    """Результат разделения пространств по допуску к цепочке Git."""

    eligible: tuple[Any, ...]
    excluded_count: int
    unresolved: bool


def _norm_path(p: Any) -> str | None:
    if not isinstance(p, (str, bytes)) and not isinstance(p, os.PathLike):
        return None
    s = str(p).strip()
    if not s:
        return None
    norm = os.path.normpath(s).rstrip("/\\").casefold()
    return norm if norm else None


def _paths_overlap(p1: str | None, p2: str | None) -> bool:
    if p1 is None or p2 is None:
        return False
    if p1 == p2:
        return True
    try:
        parts1 = PurePath(p1).parts
        parts2 = PurePath(p2).parts
        if len(parts1) < len(parts2) and parts2[:len(parts1)] == parts1:
            return True
        if len(parts2) < len(parts1) and parts1[:len(parts2)] == parts2:
            return True
    except Exception:
        return True
    return False


def _norm_remote(r: Any) -> str | None:
    if not isinstance(r, str):
        return None
    s = r.strip()
    if not s:
        return None
    val = s.rstrip("/")
    if val.lower().endswith(".git"):
        val = val[:-4]
    val = val.rstrip("/").casefold()
    return val if val else None


def _remotes_overlap(r1: str | None, r2: str | None) -> bool:
    if r1 is None or r2 is None:
        return False
    return r1 == r2


def _norm_alias(a: Any) -> str | None:
    if not isinstance(a, str):
        return None
    s = a.strip()
    if not s:
        return None
    return s.casefold()


def _aliases_overlap(a1: str | None, a2: str | None) -> bool:
    if a1 is None or a2 is None:
        return False
    return a1 == a2


def _workspace_overlaps(ws: Any, other: Any) -> bool:
    """Проверяет пересечение пространств по path, remote или ssh_alias.
    
    Любая ошибка внутри трактуется как пересечение (fail-closed).
    """
    try:
        p1 = _norm_path(getattr(ws, "path", None) if not isinstance(ws, dict) else ws.get("path"))
        p2 = _norm_path(getattr(other, "path", None) if not isinstance(other, dict) else other.get("path"))
        if _paths_overlap(p1, p2):
            return True

        r1 = _norm_remote(getattr(ws, "remote", None) if not isinstance(ws, dict) else ws.get("remote"))
        r2 = _norm_remote(getattr(other, "remote", None) if not isinstance(other, dict) else other.get("remote"))
        if _remotes_overlap(r1, r2):
            return True

        a1 = _norm_alias(getattr(ws, "ssh_alias", None) if not isinstance(ws, dict) else ws.get("ssh_alias"))
        a2 = _norm_alias(getattr(other, "ssh_alias", None) if not isinstance(other, dict) else other.get("ssh_alias"))
        if _aliases_overlap(a1, a2):
            return True

        return False
    except Exception:
        return True


def git_chain_workspaces(persona: Any) -> GitChainSplit:
    """Разделить пространства персоны на допущенные к цепочке Git и исключенные (D-12, D-13, A8).
    
    Fail-closed: при persona is None или любой ошибке доступа возвращает unresolved=True.
    Исключаются не только пространства с недопущенным clearance, но и допущенные пространства,
    идентичность которых (path, remote, ssh_alias) пересекается с любым исключённым пространством.
    """
    if persona is None:
        return GitChainSplit(eligible=(), excluded_count=0, unresolved=True)

    try:
        if hasattr(persona, "to_domain") and callable(persona.to_domain):
            workspaces = persona.to_domain().workspaces
        else:
            workspaces = getattr(persona, "workspaces", ())

        first_pass_eligible: list[Any] = []
        excluded: list[Any] = []
        for ws in workspaces:
            if is_git_chain_eligible(ws):
                first_pass_eligible.append(ws)
            else:
                excluded.append(ws)

        final_eligible: list[Any] = []
        for ws in first_pass_eligible:
            has_overlap = False
            for exc_ws in excluded:
                if _workspace_overlaps(ws, exc_ws):
                    has_overlap = True
                    break
            if not has_overlap:
                final_eligible.append(ws)

        eligible_tuple = tuple(final_eligible)
        excluded_count = len(workspaces) - len(eligible_tuple)
        return GitChainSplit(
            eligible=eligible_tuple,
            excluded_count=excluded_count,
            unresolved=False,
        )
    except Exception:
        return GitChainSplit(eligible=(), excluded_count=0, unresolved=True)


