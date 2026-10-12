"""Тесты матрицы допуска и ужесточённого шлюза git_chain_workspaces (план 04-05, GIT-01, GIT-04)."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePath
from typing import Any
from unittest.mock import AsyncMock, MagicMock
import pytest

from assistant_shared.hitl import ConfirmationStore
from src.brain.git_evaluator import GitProgressEvaluator, NDA_EXCLUDED_LINE
from src.core.domain.entities import GitCommit, Persona, Workspace, WorkspaceClearance
from src.main import run_git_progress_cycle
from src.notifier.bot_handler import EmailBotHandler
from src.persona.loader import load_persona
from src.security.airgap import is_git_chain_eligible, git_chain_workspaces
from src.storage.db import Database

from .synthetic_persona import SYNTHETIC_PERSONA, synthetic_to_config


class _BrokenClearance:
    @property
    def clearance(self):
        raise RuntimeError("faulty clearance property")


def test_is_git_chain_eligible_matrix() -> None:
    # 1. public и internal (как str и как StrEnum) -> True
    assert is_git_chain_eligible(Workspace(id="1", name="1", clearance=WorkspaceClearance.PUBLIC, path="/p")) is True
    assert is_git_chain_eligible(Workspace(id="2", name="2", clearance=WorkspaceClearance.INTERNAL, path="/p")) is True
    assert is_git_chain_eligible({"clearance": "public"}) is True
    assert is_git_chain_eligible({"clearance": "internal"}) is True
    assert is_git_chain_eligible({"clearance": WorkspaceClearance.PUBLIC}) is True
    assert is_git_chain_eligible({"clearance": WorkspaceClearance.INTERNAL}) is True

    # 2. restricted_nda, weird, пустая строка, None -> False
    assert is_git_chain_eligible(Workspace(id="3", name="3", clearance=WorkspaceClearance.RESTRICTED_NDA, path="/p")) is False
    assert is_git_chain_eligible({"clearance": "restricted_nda"}) is False
    assert is_git_chain_eligible({"clearance": WorkspaceClearance.RESTRICTED_NDA}) is False
    assert is_git_chain_eligible({"clearance": "weird"}) is False
    assert is_git_chain_eligible({"clearance": ""}) is False
    assert is_git_chain_eligible(None) is False
    assert is_git_chain_eligible({"clearance": None}) is False

    # 3. Объект без атрибута clearance, объект с исключением в property clearance -> False
    assert is_git_chain_eligible(object()) is False
    assert is_git_chain_eligible({}) is False
    assert is_git_chain_eligible(_BrokenClearance()) is False


def test_git_chain_overlap_remote() -> None:
    # Допущенное пространство с тем же remote (включая .git и разный регистр), что у NDA, исключается
    nda_ws = Workspace(
        id="nda",
        name="NDA",
        clearance=WorkspaceClearance.RESTRICTED_NDA,
        path="/nda/repo",
        remote="git@github.com:Secret/Repo.git",
    )
    public_same_remote = Workspace(
        id="pub",
        name="PUB",
        clearance=WorkspaceClearance.PUBLIC,
        path="/pub/repo",
        remote="git@github.com:secret/repo",
    )
    persona = Persona(id="p", name="n", workspaces=(nda_ws, public_same_remote))

    split = git_chain_workspaces(persona)
    assert split.unresolved is False
    assert split.eligible == ()
    assert split.excluded_count == 2


def test_git_chain_overlap_alias() -> None:
    # Допущенное пространство с тем же ssh_alias, что у NDA, исключается
    nda_ws = Workspace(
        id="nda",
        name="NDA",
        clearance=WorkspaceClearance.RESTRICTED_NDA,
        path="/nda/repo",
        ssh_alias="Secret-Host",
    )
    public_same_alias = Workspace(
        id="pub",
        name="PUB",
        clearance=WorkspaceClearance.PUBLIC,
        path="/pub/repo",
        ssh_alias="secret-host",
    )
    persona = Persona(id="p", name="n", workspaces=(nda_ws, public_same_alias))

    split = git_chain_workspaces(persona)
    assert split.unresolved is False
    assert split.eligible == ()
    assert split.excluded_count == 2


def test_git_chain_overlap_path_equal() -> None:
    # Допущенное пространство с тем же path (с учётом регистра/слэшей), что у NDA, исключается
    nda_ws = Workspace(
        id="nda",
        name="NDA",
        clearance=WorkspaceClearance.RESTRICTED_NDA,
        path="/var/repos/project/",
    )
    public_same_path = Workspace(
        id="pub",
        name="PUB",
        clearance=WorkspaceClearance.PUBLIC,
        path="/var/repos/project",
    )
    persona = Persona(id="p", name="n", workspaces=(nda_ws, public_same_path))

    split = git_chain_workspaces(persona)
    assert split.unresolved is False
    assert split.eligible == ()
    assert split.excluded_count == 2


def test_git_chain_overlap_path_nested() -> None:
    # Допущенное пространство с path, вложенным в путь NDA или содержащим его, исключается
    nda_ws = Workspace(
        id="nda",
        name="NDA",
        clearance=WorkspaceClearance.RESTRICTED_NDA,
        path="/var/repos/nda_parent",
    )
    public_nested = Workspace(
        id="pub",
        name="PUB",
        clearance=WorkspaceClearance.PUBLIC,
        path="/var/repos/nda_parent/sub_repo",
    )
    persona = Persona(id="p", name="n", workspaces=(nda_ws, public_nested))

    split = git_chain_workspaces(persona)
    assert split.unresolved is False
    assert split.eligible == ()
    assert split.excluded_count == 2

    # И наоборот: публичный родитель содержит NDA внутри
    pub_parent = Workspace(
        id="pub_parent",
        name="PUB Parent",
        clearance=WorkspaceClearance.PUBLIC,
        path="/var/repos/nda_parent",
    )
    nda_nested = Workspace(
        id="nda_child",
        name="NDA Child",
        clearance=WorkspaceClearance.RESTRICTED_NDA,
        path="/var/repos/nda_parent/sub_nda",
    )
    persona2 = Persona(id="p2", name="n2", workspaces=(pub_parent, nda_nested))

    split2 = git_chain_workspaces(persona2)
    assert split2.unresolved is False
    assert split2.eligible == ()
    assert split2.excluded_count == 2


def test_git_chain_non_overlap_kept() -> None:
    # Непересекающиеся пространства остаются
    nda_ws = Workspace(
        id="nda",
        name="NDA",
        clearance=WorkspaceClearance.RESTRICTED_NDA,
        path="/var/nda",
        remote="git@corp.example:nda/repo.git",
        ssh_alias="corp-ssh",
    )
    public_ws = Workspace(
        id="pub",
        name="PUB",
        clearance=WorkspaceClearance.PUBLIC,
        path="/var/public",
        remote="https://github.com/owner/open.git",
        ssh_alias="github-ssh",
    )
    internal_ws = Workspace(
        id="internal",
        name="INT",
        clearance=WorkspaceClearance.INTERNAL,
        path="/var/internal",
        remote="https://git.internal.example/dep/proj.git",
        ssh_alias=None,
    )
    persona = Persona(id="p", name="n", workspaces=(nda_ws, public_ws, internal_ws))

    split = git_chain_workspaces(persona)
    assert split.unresolved is False
    assert len(split.eligible) == 2
    assert split.eligible == (public_ws, internal_ws)
    assert split.excluded_count == 1


def test_git_chain_unresolved_handling() -> None:
    # 1. persona is None -> unresolved=True
    split_none = git_chain_workspaces(None)
    assert split_none.unresolved is True
    assert split_none.eligible == ()
    assert split_none.excluded_count == 0

    # 2. Исключение в to_domain() -> unresolved=True
    class BrokenPersona:
        def to_domain(self):
            raise RuntimeError("to_domain failed")

    split_err = git_chain_workspaces(BrokenPersona())
    assert split_err.unresolved is True
    assert split_err.eligible == ()
    assert split_err.excluded_count == 0

    # 3. Пустой список пространств -> unresolved=False, eligible=(), excluded_count=0
    empty_persona = Persona(id="p", name="n", workspaces=())
    split_empty = git_chain_workspaces(empty_persona)
    assert split_empty.unresolved is False
    assert split_empty.eligible == ()
    assert split_empty.excluded_count == 0


TEST_NDA_MARKER = "TEST_NDA_SECRET_MARKER_999"
TEST_USER_ID = 999888
DEFAULT_ACTIVITY_DB_ID = "33333333333333333333333333333333"
PUB_NOTION_PROJECT = "11111111111111111111111111111111"
NDA_NOTION_PROJECT = "22222222222222222222222222222222"


class TrapGitProvider:
    """Ловушка git-провайдера для фиксации обращений к репозиториям."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def list_repositories(self) -> list[Workspace]:
        self.calls.append(("list_repositories", None))
        return []

    async def fetch_remote(self, workspace: Any, timeout_sec: float = 30.0) -> bool:
        ws_id = getattr(workspace, "id", str(workspace))
        self.calls.append(("fetch_remote", ws_id))
        return True

    async def get_commits_since(
        self,
        workspace: Any,
        since: datetime | None = None,
        max_commits: int = 100,
    ) -> list[GitCommit]:
        ws_id = getattr(workspace, "id", str(workspace))
        self.calls.append(("get_commits_since", ws_id))
        now = datetime.now(timezone.utc)
        return [
            GitCommit(
                hash="1111111111111111111111111111111111111111",
                author=f"Author {ws_id}",
                date=now,
                message=f"feat: feature commit for workspace {ws_id}",
                files_changed=1,
                insertions=10,
                deletions=2,
            ),
            GitCommit(
                hash="2222222222222222222222222222222222222222",
                author=f"Author {ws_id}",
                date=now,
                message=f"fix: bugfix commit for workspace {ws_id}",
                files_changed=2,
                insertions=5,
                deletions=1,
            ),
        ]


class TrapLlm:
    """Ловушка LLM-клиента по образцу SpyGenAIClient."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.aio = MagicMock()
        self.aio.models = MagicMock()
        self.aio.models.generate_content = AsyncMock(side_effect=self._mock_generate_content)

    async def _mock_generate_content(self, model: str, contents: Any, config: Any = None) -> Any:
        sys_inst = str(getattr(config, "system_instruction", ""))
        self.calls.append({
            "model": model,
            "contents": str(contents),
            "system_instruction": sys_inst,
            "config": config,
        })
        resp = MagicMock()
        resp.text = "Сводка LLM: Успешный ход разработки."
        return resp


class TrapNotion:
    """Ловушка Notion-клиента: фиксирует вызовы find_project_activity и log_project_activity."""

    def __init__(self, is_configured: bool = True) -> None:
        self.is_configured = is_configured
        self.calls: list[dict[str, Any]] = []

    async def find_project_activity(self, **kwargs: Any) -> dict[str, Any] | None:
        self.calls.append({"method": "find_project_activity", **kwargs})
        return None

    async def log_project_activity(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"method": "log_project_activity", **kwargs})
        return {"id": "test_page"}


@dataclass
class StandContext:
    db: Database
    store: ConfirmationStore
    evaluator: GitProgressEvaluator
    handler: EmailBotHandler
    git_trap: TrapGitProvider
    llm_trap: TrapLlm
    notion_trap: TrapNotion
    user_id: int
    bot_mock: AsyncMock


async def create_trap_stand(
    scenario: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> StandContext:
    db_path = str(tmp_path / f"bot_{scenario}.db")
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.init_db()

    store = ConfirmationStore(db_path)
    git_trap = TrapGitProvider()
    llm_trap = TrapLlm()
    notion_trap = TrapNotion(is_configured=True)

    pub_dir = tmp_path / f"pub_repo_{scenario}"
    pub_dir.mkdir(parents=True, exist_ok=True)
    (pub_dir / ".git").mkdir(parents=True, exist_ok=True)

    pub_ws = Workspace(
        id=f"ws_pub_{scenario}",
        name=f"Public Project {scenario}",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(pub_dir),
        remote=f"git@github.com:open/{scenario}.git",
        ssh_alias=f"ssh-pub-{scenario}",
        notion_project=PUB_NOTION_PROJECT,
    )

    nda_dir = tmp_path / f"nda_repo_{scenario}_{TEST_NDA_MARKER}"
    nda_dir.mkdir(parents=True, exist_ok=True)
    (nda_dir / ".git").mkdir(parents=True, exist_ok=True)

    nda_ws = Workspace(
        id=f"ws_nda_{scenario}_{TEST_NDA_MARKER}",
        name=f"NDA Project {scenario} {TEST_NDA_MARKER}",
        clearance=WorkspaceClearance.RESTRICTED_NDA,
        path=str(nda_dir),
        remote=f"git@secret.internal:{scenario}/{TEST_NDA_MARKER}.git",
        ssh_alias=f"ssh-nda-{scenario}-{TEST_NDA_MARKER}",
        notion_project=NDA_NOTION_PROJECT,
    )

    persona: Any = None

    if scenario == "only_nda":
        persona = Persona(id=f"p_{scenario}", name="Owner", workspaces=(nda_ws,))

    elif scenario == "mixed":
        persona = Persona(id=f"p_{scenario}", name="Owner", workspaces=(pub_ws, nda_ws))

    elif scenario == "unknown_clearance":
        unk_dir = tmp_path / f"unk_repo_{scenario}_{TEST_NDA_MARKER}"
        unk_dir.mkdir(parents=True, exist_ok=True)
        (unk_dir / ".git").mkdir(parents=True, exist_ok=True)
        unk_ws = Workspace(
            id=f"ws_unk_{scenario}_{TEST_NDA_MARKER}",
            name=f"Unk Project {scenario} {TEST_NDA_MARKER}",
            clearance="confidential_unknown_level",
            path=str(unk_dir),
            remote=f"git@unk.internal:{scenario}/{TEST_NDA_MARKER}.git",
            ssh_alias=f"ssh-unk-{scenario}-{TEST_NDA_MARKER}",
            notion_project=NDA_NOTION_PROJECT,
        )
        persona = Persona(id=f"p_{scenario}", name="Owner", workspaces=(unk_ws,))

    elif scenario == "persona_error":
        class BrokenWorkspacesPersona:
            id = f"p_broken_{scenario}"
            name = "Broken"

            @property
            def workspaces(self) -> Any:
                raise RuntimeError(f"Database error reading workspaces with marker {TEST_NDA_MARKER}")

            def to_domain(self) -> Any:
                return self

        persona = BrokenWorkspacesPersona()
        def _failing_current_persona() -> Any:
            raise RuntimeError(f"Cannot load persona {TEST_NDA_MARKER}")
        monkeypatch.setattr("src.persona.current.current_persona", _failing_current_persona)

    elif scenario == "persona_none":
        persona = None
        def _failing_current_persona() -> Any:
            raise RuntimeError(f"Cannot load persona {TEST_NDA_MARKER}")
        monkeypatch.setattr("src.persona.current.current_persona", _failing_current_persona)

    elif scenario == "overlap_remote":
        shared_remote = f"git@github.com:shared/{scenario}/{TEST_NDA_MARKER}.git"
        ov_nda = Workspace(
            id=f"ws_nda_ov_{scenario}_{TEST_NDA_MARKER}",
            name=f"NDA Overlap {scenario} {TEST_NDA_MARKER}",
            clearance=WorkspaceClearance.RESTRICTED_NDA,
            path=str(nda_dir),
            remote=shared_remote,
            ssh_alias=f"ssh-nda-ov-{TEST_NDA_MARKER}",
            notion_project=NDA_NOTION_PROJECT,
        )
        ov_pub = Workspace(
            id=f"ws_pub_ov_{scenario}",
            name=f"Public Overlap {scenario}",
            clearance=WorkspaceClearance.PUBLIC,
            path=str(pub_dir),
            remote=shared_remote,
            ssh_alias="ssh-pub-ov",
            notion_project=PUB_NOTION_PROJECT,
        )
        persona = Persona(id=f"p_{scenario}", name="Owner", workspaces=(ov_nda, ov_pub))

    elif scenario == "overlap_path":
        nda_parent_dir = tmp_path / f"nda_parent_{scenario}_{TEST_NDA_MARKER}"
        pub_child_dir = nda_parent_dir / f"sub_pub_{scenario}"
        nda_parent_dir.mkdir(parents=True, exist_ok=True)
        pub_child_dir.mkdir(parents=True, exist_ok=True)
        (nda_parent_dir / ".git").mkdir(parents=True, exist_ok=True)
        (pub_child_dir / ".git").mkdir(parents=True, exist_ok=True)

        path_nda = Workspace(
            id=f"ws_nda_path_{scenario}_{TEST_NDA_MARKER}",
            name=f"NDA Path {scenario} {TEST_NDA_MARKER}",
            clearance=WorkspaceClearance.RESTRICTED_NDA,
            path=str(nda_parent_dir),
            remote=f"git@secret.internal:{scenario}/{TEST_NDA_MARKER}.git",
            ssh_alias=f"ssh-nda-path-{TEST_NDA_MARKER}",
            notion_project=NDA_NOTION_PROJECT,
        )
        path_pub = Workspace(
            id=f"ws_pub_path_{scenario}",
            name=f"Public Path {scenario}",
            clearance=WorkspaceClearance.PUBLIC,
            path=str(pub_child_dir),
            remote=f"git@github.com:open/{scenario}_nested.git",
            ssh_alias="ssh-pub-path",
            notion_project=PUB_NOTION_PROJECT,
        )
        persona = Persona(id=f"p_{scenario}", name="Owner", workspaces=(path_nda, path_pub))

    elif scenario == "public_only":
        persona = Persona(id=f"p_{scenario}", name="Owner", workspaces=(pub_ws,))

    else:
        raise ValueError(f"Unknown scenario: {scenario}")

    evaluator = GitProgressEvaluator(
        git_provider=git_trap,
        notion_client=notion_trap,
        confirmation_store=store,
        persona=persona,
        default_activity_db_id=DEFAULT_ACTIVITY_DB_ID,
        llm_client=llm_trap,
    )

    bot_mock = AsyncMock()
    handler = EmailBotHandler(
        bot=bot_mock,
        db=db,
        allowed_user_id=TEST_USER_ID,
        git_evaluator=evaluator,
    )

    return StandContext(
        db=db,
        store=store,
        evaluator=evaluator,
        handler=handler,
        git_trap=git_trap,
        llm_trap=llm_trap,
        notion_trap=notion_trap,
        user_id=TEST_USER_ID,
        bot_mock=bot_mock,
    )


async def _click_all_notion_buttons(
    handler: EmailBotHandler,
    user_id: int,
    reply_markup: Any,
) -> list[str]:
    """Нажимает все выданные кнопки ntn:req и ntn:conf через реальные колбэки бота."""
    collected_texts: list[str] = []
    if not reply_markup or not hasattr(reply_markup, "inline_keyboard"):
        return collected_texts

    for row in reply_markup.inline_keyboard:
        for btn in row:
            if btn.callback_data and btn.callback_data.startswith("ntn:req:"):
                req_cb = AsyncMock()
                req_cb.from_user.id = user_id
                req_cb.data = btn.callback_data
                req_cb.message = AsyncMock()
                req_cb.message.answer = AsyncMock()
                await handler.cb_ntn_request(req_cb)

                if req_cb.message.answer.called:
                    card_text = req_cb.message.answer.call_args[0][0]
                    collected_texts.append(card_text)
                    card_kb = req_cb.message.answer.call_args[1].get("reply_markup")
                    if card_kb and hasattr(card_kb, "inline_keyboard"):
                        for c_row in card_kb.inline_keyboard:
                            for c_btn in c_row:
                                if c_btn.callback_data and c_btn.callback_data.startswith("ntn:conf:"):
                                    conf_cb = AsyncMock()
                                    conf_cb.from_user.id = user_id
                                    conf_cb.data = c_btn.callback_data
                                    conf_cb.message = AsyncMock()
                                    conf_cb.message.edit_text = AsyncMock()
                                    await handler.cb_ntn_confirm(conf_cb)
                                    if conf_cb.message.edit_text.called:
                                        conf_text = conf_cb.message.edit_text.call_args[0][0]
                                        collected_texts.append(conf_text)
    return collected_texts


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    [
        "only_nda",
        "mixed",
        "unknown_clearance",
        "persona_error",
        "persona_none",
        "overlap_remote",
        "overlap_path",
    ],
)
async def test_runtime_traps_nda_scenarios(
    scenario: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Проверка Air-Gap в 7 сценариях: 0 обращений к NDA и отсутствие утечек маркера."""
    stand = await create_trap_stand(scenario, tmp_path, monkeypatch)

    status_msg = AsyncMock()
    msg = AsyncMock()
    msg.from_user.id = stand.user_id
    msg.answer = AsyncMock(return_value=status_msg)

    await stand.handler.handle_cmd_git(msg)

    assert status_msg.edit_text.called
    run_text = status_msg.edit_text.call_args[0][0]
    reply_markup = status_msg.edit_text.call_args[1].get("reply_markup")

    button_texts = await _click_all_notion_buttons(stand.handler, stand.user_id, reply_markup)
    all_texts = [run_text] + button_texts

    assert TEST_NDA_MARKER not in repr(stand.git_trap.calls)
    assert TEST_NDA_MARKER not in repr(stand.llm_trap.calls)
    assert TEST_NDA_MARKER not in repr(stand.notion_trap.calls)
    assert TEST_NDA_MARKER not in repr(all_texts)
    assert TEST_NDA_MARKER not in repr(stand.bot_mock.mock_calls)

    assert NDA_EXCLUDED_LINE in run_text

    if scenario == "mixed":
        assert reply_markup is not None
        assert any(call[1] == f"ws_pub_{scenario}" for call in stand.git_trap.calls)
        assert not any(TEST_NDA_MARKER in str(call[1]) for call in stand.git_trap.calls)
        assert len(stand.llm_trap.calls) == 1
        assert len(stand.notion_trap.calls) >= 1
    else:
        assert reply_markup is None
        assert len(stand.git_trap.calls) == 0
        assert len(stand.llm_trap.calls) == 0
        assert len(stand.notion_trap.calls) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    [
        "only_nda",
        "mixed",
        "unknown_clearance",
        "persona_error",
        "persona_none",
        "overlap_remote",
        "overlap_path",
    ],
)
async def test_runtime_traps_scheduler_cycle(
    scenario: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Проверка Air-Gap при запуске планировщиком run_git_progress_cycle."""
    stand = await create_trap_stand(scenario, tmp_path, monkeypatch)
    notifier = AsyncMock()
    notifier.send_message = AsyncMock()

    await run_git_progress_cycle(stand.evaluator, notifier)

    assert TEST_NDA_MARKER not in repr(stand.git_trap.calls)
    assert TEST_NDA_MARKER not in repr(stand.llm_trap.calls)
    assert TEST_NDA_MARKER not in repr(stand.notion_trap.calls)
    assert TEST_NDA_MARKER not in repr(notifier.send_message.call_args_list)

    assert any(NDA_EXCLUDED_LINE in str(args) for args in notifier.send_message.call_args_list)

    if scenario == "mixed":
        assert any(call[1] == f"ws_pub_{scenario}" for call in stand.git_trap.calls)
        assert not any(TEST_NDA_MARKER in str(call[1]) for call in stand.git_trap.calls)
        assert len(stand.llm_trap.calls) == 1
        assert len(stand.notion_trap.calls) == 0
    else:
        assert len(stand.git_trap.calls) == 0
        assert len(stand.llm_trap.calls) == 0
        assert len(stand.notion_trap.calls) == 0


@pytest.mark.asyncio
async def test_traps_are_not_vacuous(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Контрольный тест: на персоне только из public-пространств ловушки фиксируют вызовы git, LLM и Notion."""
    stand = await create_trap_stand("public_only", tmp_path, monkeypatch)

    status_msg = AsyncMock()
    msg = AsyncMock()
    msg.from_user.id = stand.user_id
    msg.answer = AsyncMock(return_value=status_msg)

    await stand.handler.handle_cmd_git(msg)

    assert status_msg.edit_text.called
    run_text = status_msg.edit_text.call_args[0][0]
    reply_markup = status_msg.edit_text.call_args[1].get("reply_markup")

    assert NDA_EXCLUDED_LINE not in run_text
    assert reply_markup is not None

    assert any(call[0] == "fetch_remote" for call in stand.git_trap.calls)
    assert any(call[0] == "get_commits_since" for call in stand.git_trap.calls)
    assert len(stand.llm_trap.calls) >= 1

    assert len(stand.notion_trap.calls) == 0

    button_texts = await _click_all_notion_buttons(stand.handler, stand.user_id, reply_markup)
    assert any("Записано в Notion" in text for text in button_texts)

    assert len(stand.notion_trap.calls) >= 1
    assert any(call.get("method") == "log_project_activity" for call in stand.notion_trap.calls)
