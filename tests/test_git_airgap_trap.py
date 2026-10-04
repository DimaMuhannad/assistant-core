"""Тесты сквозного Air-Gap для Git-коммитов и изоляции LLM-контекста (GIT-03, GIT-04).

Проверяет:
1. Защиту от утечек NDA: сообщения коммитов, имена файлов и диффы репозиториев
   restricted_nda никогда не передаются в стороннюю LLM (T-07-01).
2. Работу SpyGenAIClient, перехватывающего все промпты и гарантирующего 0 NDA-строк.
3. Санитизацию полезной нагрузки для Notion: в контуре NDA передаются только
   агрегаты (число коммитов и даты).
4. Обычную обработку публичных репозиториев (public/internal) с семантическими сводками.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import jinja2
import pytest

from src.core.domain.entities import GitCommit, Persona, Workspace, WorkspaceClearance
from src.persona.current import use_persona
from src.security.airgap import (
    NDA_GIT_MASK_MARKER,
    is_nda_workspace,
    sanitize_git_commits_for_llm,
    sanitize_notion_payload_for_airgap,
)


class SpyGenAIClient:
    """Шпион-ловушка вместо genai.Client для проверки отсутствия NDA-токенов в запросах к LLM."""

    def __init__(self, forbidden_patterns: list[str] | None = None):
        self.recorded_calls: list[dict[str, Any]] = []
        self.forbidden_patterns = forbidden_patterns or [
            "SECRET_NDA_KEY_123",
            "proprietary_thz_laser_driver",
            "confidential_optics_schematics.py",
            "TOP_SECRET_TIREX_ALGORITHM",
        ]

        self.aio = MagicMock()
        self.aio.models = MagicMock()
        self.aio.models.generate_content = AsyncMock(side_effect=self._mock_generate_content)

    async def _mock_generate_content(self, model: str, contents: Any, config: Any = None) -> Any:
        contents_str = str(contents)
        sys_inst = str(getattr(config, "system_instruction", ""))

        for forbidden in self.forbidden_patterns:
            assert forbidden not in contents_str, (
                f"УТЕЧКА В LLM: Конфиденциальный токен '{forbidden}' обнаружен в contents!"
            )
            assert forbidden not in sys_inst, (
                f"УТЕЧКА В LLM: Конфиденциальный токен '{forbidden}' обнаружен в system_instruction!"
            )

        self.recorded_calls.append({
            "model": model,
            "contents": contents_str,
            "system_instruction": sys_inst,
            "config": config,
        })

        mock_resp = MagicMock()
        mock_resp.text = "Сводка: Проект активно развивается, зафиксировано 3 коммита."
        return mock_resp


@pytest.fixture
def nda_workspace() -> Workspace:
    return Workspace(
        id="ws_tydex_nda",
        name="Tydex THz Photonics Core",
        clearance=WorkspaceClearance.RESTRICTED_NDA,
        path="/opt/tydex/optics_core",
        ssh_alias="tydex-server",
        notion_project="notion-proj-001",
    )


@pytest.fixture
def public_workspace() -> Workspace:
    return Workspace(
        id="ws_guap_public",
        name="GUAP Open Lab",
        clearance=WorkspaceClearance.PUBLIC,
        path="/opt/guap/open_lab",
        ssh_alias=None,
        notion_project="notion-proj-002",
    )


@pytest.fixture
def secret_nda_commits() -> list[GitCommit]:
    now = datetime.now(timezone.utc)
    return [
        GitCommit(
            hash="aaa1111111111111111111111111111111111111",
            author="Dev Team",
            date=now,
            message="feat: add proprietary_thz_laser_driver with SECRET_NDA_KEY_123",
            files_changed=4,
            insertions=120,
            deletions=10,
        ),
        GitCommit(
            hash="bbb2222222222222222222222222222222222222",
            author="Optics Engineer",
            date=now,
            message="fix(core): update confidential_optics_schematics.py and TOP_SECRET_TIREX_ALGORITHM",
            files_changed=2,
            insertions=15,
            deletions=3,
        ),
    ]


@pytest.fixture
def public_commits() -> list[GitCommit]:
    now = datetime.now(timezone.utc)
    return [
        GitCommit(
            hash="ccc3333333333333333333333333333333333333",
            author="Academic Student",
            date=now,
            message="feat: implement open source physics wave simulator",
            files_changed=3,
            insertions=50,
            deletions=5,
        ),
    ]


def test_is_nda_workspace_detection(nda_workspace: Workspace, public_workspace: Workspace):
    """Корректное определение уровня допуска рабочего пространства (D-05)."""
    assert is_nda_workspace(nda_workspace) is True
    assert is_nda_workspace(public_workspace) is False
    assert is_nda_workspace("restricted_nda") is True
    assert is_nda_workspace("public") is False

    # Проверка через персону по ID
    dummy_persona = Persona(
        id="p_test",
        name="Test Persona",
        workspaces=(nda_workspace, public_workspace),
    )
    with use_persona(dummy_persona):
        assert is_nda_workspace("ws_tydex_nda") is True
        assert is_nda_workspace("ws_guap_public") is False
        assert is_nda_workspace("ws_unknown") is False


def test_sanitize_git_commits_nda(nda_workspace: Workspace, secret_nda_commits: list[GitCommit]):
    """Для NDA-репозиториев сообщения коммитов заменяются на NDA_GIT_MASK_MARKER, диффы обнуляются."""
    sanitized = sanitize_git_commits_for_llm(nda_workspace, secret_nda_commits)
    assert len(sanitized) == len(secret_nda_commits)

    for c in sanitized:
        assert c.message == NDA_GIT_MASK_MARKER
        assert c.files_changed == 0
        assert c.insertions == 0
        assert c.deletions == 0
        assert "SECRET_NDA_KEY_123" not in c.message
        assert "proprietary_thz_laser_driver" not in c.message
        assert "confidential_optics_schematics.py" not in c.message


def test_sanitize_git_commits_public(public_workspace: Workspace, public_commits: list[GitCommit]):
    """Для публичных репозиториев коммиты не модифицируются."""
    sanitized = sanitize_git_commits_for_llm(public_workspace, public_commits)
    assert sanitized == public_commits
    assert sanitized[0].message == "feat: implement open source physics wave simulator"


@pytest.mark.asyncio
async def test_nda_commits_not_sent_to_llm(
    nda_workspace: Workspace,
    secret_nda_commits: list[GitCommit],
):
    """Сквозной тест-ловушка: ни один NDA-секрет не попадает в запрос к LLM (GIT-04, T-07-01)."""
    spy = SpyGenAIClient()

    # 1. Санитизируем коммиты
    safe_commits = sanitize_git_commits_for_llm(nda_workspace, secret_nda_commits)

    # 2. Рендерим шаблон промпта git_progress.jinja2
    template_path = Path("/opt/assistant-core/src/persona/prompts/git_progress.jinja2")
    template = jinja2.Template(template_path.read_text(encoding="utf-8"))

    prompt_text = template.render(
        project_name=nda_workspace.name,
        commits=safe_commits,
        period_start="2026-03-20",
        period_end="2026-03-27",
        is_stagnant=False,
        clearance="restricted_nda",
    )

    # 3. Отправляем в LLM через шпиона-ловушку
    await spy.aio.models.generate_content(model="gemini-2.5-flash", contents=prompt_text)

    # 4. Проверяем перехваченный запрос
    assert len(spy.recorded_calls) == 1
    call_content = spy.recorded_calls[0]["contents"]
    assert "РЕЖИМ БЕЗОПАСНОСТИ AIR-GAP" in call_content
    assert NDA_GIT_MASK_MARKER not in call_content  # В режиме NDA коммиты вообще не выводятся списком
    assert "SECRET_NDA_KEY_123" not in call_content
    assert "proprietary_thz_laser_driver" not in call_content
    assert "confidential_optics_schematics.py" not in call_content
    assert "TOP_SECRET_TIREX_ALGORITHM" not in call_content


@pytest.mark.asyncio
async def test_public_commits_processed_normally(
    public_workspace: Workspace,
    public_commits: list[GitCommit],
):
    """Для открытого проекта сообщения коммитов корректно поступают в промпт для семантического анализа."""
    spy = SpyGenAIClient()
    safe_commits = sanitize_git_commits_for_llm(public_workspace, public_commits)

    template_path = Path("/opt/assistant-core/src/persona/prompts/git_progress.jinja2")
    template = jinja2.Template(template_path.read_text(encoding="utf-8"))

    prompt_text = template.render(
        project_name=public_workspace.name,
        commits=safe_commits,
        period_start="2026-03-20",
        period_end="2026-03-27",
        is_stagnant=False,
        clearance="public",
    )

    await spy.aio.models.generate_content(model="gemini-2.5-flash", contents=prompt_text)

    assert len(spy.recorded_calls) == 1
    call_content = spy.recorded_calls[0]["contents"]
    assert "feat: implement open source physics wave simulator" in call_content
    assert "Academic Student" in call_content


def test_nda_notion_payload_is_sanitized(
    nda_workspace: Workspace,
    public_workspace: Workspace,
    secret_nda_commits: list[GitCommit],
):
    """Полезная нагрузка отчета для Notion в контуре NDA содержит исключительно число коммитов и даты."""
    raw_nda_payload = {
        "workspace_id": nda_workspace.id,
        "notion_project_id": nda_workspace.notion_project,
        "date_iso": "2026-03-27",
        "commit_count": len(secret_nda_commits),
        "status": "Активно",
        "commits": secret_nda_commits,
        "messages": [c.message for c in secret_nda_commits],
        "files": ["confidential_optics_schematics.py", "proprietary_driver.c"],
        "branches": ["feature/secret-laser"],
        "summary": "Добавлены закрытые алгоритмы SECRET_NDA_KEY_123",
    }

    sanitized_payload = sanitize_notion_payload_for_airgap(nda_workspace, raw_nda_payload)

    # Запрещенные детальные поля должны быть полностью удалены
    assert "commits" not in sanitized_payload
    assert "messages" not in sanitized_payload
    assert "files" not in sanitized_payload
    assert "branches" not in sanitized_payload

    # Разрешенные агрегатные поля сохранены
    assert sanitized_payload["commit_count"] == 2
    assert sanitized_payload["date_iso"] == "2026-03-27"
    assert sanitized_payload["workspace_id"] == "ws_tydex_nda"

    # Резюме не содержит секретов
    assert "SECRET_NDA_KEY_123" not in sanitized_payload["summary"]
    assert "Air-Gap (NDA)" in sanitized_payload["summary"]

    # Для публичного пространства санитизация не удаляет полезную нагрузку
    raw_public_payload = {
        "workspace_id": public_workspace.id,
        "commit_count": 1,
        "summary": "Открытая лабораторная работа",
    }
    clean_public = sanitize_notion_payload_for_airgap(public_workspace, raw_public_payload)
    assert clean_public == raw_public_payload
