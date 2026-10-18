"""Сквозной тест цепочки /git -> оценка -> HITL -> Notion (Phase 4 Tracer & Guarded Branches)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
import subprocess
import textwrap
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from assistant_shared.hitl import ConfirmationStatus, ConfirmationStore
from src.brain.git_evaluator import (
    GitProgressEvaluator,
    NDA_EXCLUDED_LINE,
    NotionSyncError,
)
from src.connectors.git.provider import SshGitProvider
from src.core.domain.entities import (
    Persona,
    Workspace,
    WorkspaceClearance,
)
from src.notifier.bot_handler import EmailBotHandler
from src.storage.db import Database


class CountingGitProvider(SshGitProvider):
    """Обертка над SshGitProvider, регистрирующая вызовы методов с идентификаторами пространств."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.recorded_calls: list[tuple[str, str]] = []

    async def fetch_remote(self, workspace, timeout_sec=10.0) -> bool:
        ws_id = getattr(workspace, "id", str(workspace))
        self.recorded_calls.append(("fetch_remote", ws_id))
        return await super().fetch_remote(workspace, timeout_sec=timeout_sec)

    async def get_commits_since(self, workspace, since=None, max_commits=100):
        ws_id = getattr(workspace, "id", str(workspace))
        self.recorded_calls.append(("get_commits_since", ws_id))
        return await super().get_commits_since(workspace, since=since, max_commits=max_commits)


class FakeNotionClient:
    """Поддельный клиент Notion для перехвата log_project_activity."""

    def __init__(
        self,
        is_configured: bool = True,
        should_fail: bool = False,
        existing_page: dict | None = None,
    ):
        self.is_configured = is_configured
        self.should_fail = should_fail
        self.existing_page = existing_page
        self.logged_calls: list[dict] = []
        self.find_calls: list[dict] = []

    async def find_project_activity(self, **kwargs) -> dict | None:
        self.find_calls.append(kwargs)
        return self.existing_page

    async def log_project_activity(self, **kwargs) -> dict:
        if self.should_fail:
            raise RuntimeError("Notion API 500 Internal Error")
        self.logged_calls.append(kwargs)
        return {"id": "page_1234567890abcdef1234567890ab", "object": "page"}


@pytest.fixture
def tracer_repos(tmp_path: Path):
    """Создает локальный рабочий репозиторий с двумя коммитами и bare-origin."""
    repo_dir = tmp_path / "work_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=repo_dir, check=True)

    (repo_dir / "file1.txt").write_text("Hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "feat: first commit"], cwd=repo_dir, check=True)

    (repo_dir / "file2.txt").write_text("World\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "feat: second commit"], cwd=repo_dir, check=True)

    bare_origin = tmp_path / "origin.git"
    subprocess.run(["git", "clone", "--bare", str(repo_dir), str(bare_origin)], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare_origin)], cwd=repo_dir, check=True)

    secret_dir = tmp_path / "secret_nda_dir"
    secret_dir.mkdir()

    return repo_dir, bare_origin, secret_dir


def test_gate_runs_before_any_provider_call():
    """ast-проверка порядка внутри GitProgressEvaluator.evaluate: git_chain_workspaces стоит раньше fetch_remote и get_commits_since."""
    source = textwrap.dedent(inspect.getsource(GitProgressEvaluator.evaluate))
    tree = ast.parse(source)

    gate_line = None
    provider_lines: list[int] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_name = ""
            if isinstance(node.func, ast.Name):
                call_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                call_name = node.func.attr
            if call_name == "git_chain_workspaces":
                if gate_line is None or node.lineno < gate_line:
                    gate_line = node.lineno
            elif call_name in ("fetch_remote", "get_commits_since"):
                provider_lines.append(node.lineno)

    assert gate_line is not None, "git_chain_workspaces не вызывается в evaluate()"
    assert provider_lines, "Провайдер git не вызывается в evaluate()"
    for p_line in provider_lines:
        assert gate_line < p_line, f"git_chain_workspaces (строка {gate_line}) должен вызываться до обращения к провайдеру (строка {p_line})"


def test_handlers_call_is_authorized_first():
    """ast-проверка: в обработчиках bot_handler вызов _is_authorized стоит раньше любого await."""
    target_methods = ["handle_cmd_git", "cb_ntn_request", "cb_ntn_confirm", "cb_ntn_reject"]

    for method_name in target_methods:
        method = getattr(EmailBotHandler, method_name, None)
        assert method is not None, f"Метод {method_name} отсутствует в EmailBotHandler"
        source = textwrap.dedent(inspect.getsource(method))
        tree = ast.parse(source)

        fn_def = tree.body[0]
        assert isinstance(fn_def, (ast.FunctionDef, ast.AsyncFunctionDef))

        first_auth_line = None
        first_await_line = None

        for stmt in ast.walk(fn_def):
            if isinstance(stmt, ast.Call):
                name = ""
                if isinstance(stmt.func, ast.Attribute):
                    name = stmt.func.attr
                elif isinstance(stmt.func, ast.Name):
                    name = stmt.func.id
                if name == "_is_authorized":
                    if first_auth_line is None or stmt.lineno < first_auth_line:
                        first_auth_line = stmt.lineno
            elif isinstance(stmt, ast.Await):
                if first_await_line is None or stmt.lineno < first_await_line:
                    first_await_line = stmt.lineno

        assert first_auth_line is not None, f"{method_name} не вызывает _is_authorized"
        if first_await_line is not None:
            assert first_auth_line < first_await_line, (
                f"В {method_name} _is_authorized (строка {first_auth_line}) должен быть вызван "
                f"до любого await (строка {first_await_line})"
            )


@pytest.mark.asyncio
async def test_tracer_git_command_to_notion_write(tmp_path: Path, tracer_repos):
    """Сквозной трассирующий тест: /git -> ntn:req -> ntn:conf -> запись в Notion."""
    repo_dir, bare_origin, secret_dir = tracer_repos

    ws_public = Workspace(
        id="ws_pub_1",
        name="Public Project",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(repo_dir),
        remote=str(bare_origin),
        notion_project="11111111111111111111111111111111",
    )
    ws_nda = Workspace(
        id="ws_secret_nda",
        name="Top Secret NDA",
        clearance=WorkspaceClearance.RESTRICTED_NDA,
        path=str(secret_dir),
        remote="git@secret.internal:corp/classified.git",
        ssh_alias="secret_box",
        notion_project="22222222222222222222222222222222",
    )

    persona = Persona(
        id="owner_p",
        name="Owner Persona",
        workspaces=(ws_public, ws_nda),
    )

    db_path = str(tmp_path / "bot_test.db")
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.init_db()

    store = ConfirmationStore(db_path)
    git_provider = CountingGitProvider()
    fake_notion = FakeNotionClient(is_configured=True)

    evaluator = GitProgressEvaluator(
        git_provider=git_provider,
        notion_client=fake_notion,
        confirmation_store=store,
        persona=persona,
        default_activity_db_id="33333333333333333333333333333333",
    )

    user_id = 999888
    bot_mock = AsyncMock()
    handler = EmailBotHandler(
        bot=bot_mock,
        db=db,
        allowed_user_id=user_id,
        git_evaluator=evaluator,
    )

    # 1. Шаг команды /git
    status_msg = AsyncMock()
    msg = AsyncMock()
    msg.from_user.id = user_id
    msg.answer = AsyncMock(return_value=status_msg)

    await handler.handle_cmd_git(msg)

    assert status_msg.edit_text.called, "status_msg.edit_text должен быть вызван"
    run_text, run_kwargs = status_msg.edit_text.call_args[0][0], status_msg.edit_text.call_args[1]

    # Проверка текста ответа
    assert "Public Project" in run_text
    assert "Зафиксировано 2 коммита" in run_text
    assert "NDA: исключено из оценки" in run_text

    # Проверка, что NDA-пространство никогда не опрашивалось
    assert not any(ws_id == "ws_secret_nda" for _, ws_id in git_provider.recorded_calls)

    # Проверка клавиатуры со списком проектов
    run_kb = run_kwargs.get("reply_markup")
    assert run_kb is not None, "Клавиатура с кнопками ntn:req должна присутствовать"

    req_button = None
    for row in run_kb.inline_keyboard:
        for btn in row:
            if btn.callback_data.startswith("ntn:req:"):
                req_button = btn
                break
    assert req_button is not None, "Кнопка ntn:req не найдена в клавиатуре"

    # 2. Шаг нажатия кнопки ntn:req (создание карточки)
    req_cb = AsyncMock()
    req_cb.from_user.id = user_id
    req_cb.data = req_button.callback_data
    req_cb.message.answer = AsyncMock()

    await handler.cb_ntn_request(req_cb)

    assert req_cb.message.answer.called, "cb_ntn_request должен отправить карточку в чат"
    card_text = req_cb.message.answer.call_args[0][0]
    card_kb = req_cb.message.answer.call_args[1].get("reply_markup")

    assert "Public Project" in card_text
    assert "Сводка для Notion" in card_text or "Notion" in card_text
    assert card_kb is not None, "Карточка должна содержать кнопки ntn:conf и ntn:rej"

    conf_btn = None
    for row in card_kb.inline_keyboard:
        for btn in row:
            if btn.callback_data.startswith("ntn:conf:"):
                conf_btn = btn
                break
    assert conf_btn is not None, "Кнопка ntn:conf не найдена в карточке"

    # 3. Шаг нажатия ntn:conf (подтверждение публикации в Notion)
    conf_cb = AsyncMock()
    conf_cb.from_user.id = user_id
    conf_cb.data = conf_btn.callback_data
    conf_cb.message.edit_text = AsyncMock()

    await handler.cb_ntn_confirm(conf_cb)

    assert conf_cb.message.edit_text.called, "cb_ntn_confirm должен обновить сообщение успехом"
    success_text = conf_cb.message.edit_text.call_args[0][0]
    assert "Записано в Notion" in success_text
    assert "Public Project" in success_text

    # Проверка вызова FakeNotion: ровно 1 вызов с правильными параметрами
    assert len(fake_notion.logged_calls) == 1
    call_args = fake_notion.logged_calls[0]
    assert call_args["database_id"] == "33333333333333333333333333333333"
    assert call_args["project_page_id"] == "11111111111111111111111111111111"
    assert call_args["commit_count"] == 2
    assert call_args["status"] == "Активно"

    # Контурная проверка: NDA-пространство никогда не касалось ни git, ни Notion
    assert not any(ws_id == "ws_secret_nda" for _, ws_id in git_provider.recorded_calls)


@pytest.mark.asyncio
async def test_rejection_does_not_post_to_notion(tmp_path: Path, tracer_repos):
    """Отклонение: ntn:rej переводит карточку в rejected, FakeNotion не вызывается."""
    repo_dir, bare_origin, _ = tracer_repos
    ws_public = Workspace(
        id="ws_pub_rej",
        name="Reject Project",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(repo_dir),
        remote=str(bare_origin),
        notion_project="11111111111111111111111111111111",
    )
    persona = Persona(id="p1", name="Owner", workspaces=(ws_public,))
    db_path = str(tmp_path / "bot_rej.db")
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.init_db()

    store = ConfirmationStore(db_path)
    git_provider = CountingGitProvider()
    fake_notion = FakeNotionClient(is_configured=True)

    evaluator = GitProgressEvaluator(
        git_provider=git_provider,
        notion_client=fake_notion,
        confirmation_store=store,
        persona=persona,
        default_activity_db_id="33333333333333333333333333333333",
    )
    user_id = 111222
    handler = EmailBotHandler(bot=AsyncMock(), db=db, allowed_user_id=user_id, git_evaluator=evaluator)

    # Запускаем оценку и создаем карточку
    run = await evaluator.evaluate()
    proposal = await evaluator.propose_card(run.entries[0], run.date_iso)
    conf = proposal.confirmation

    rej_cb = AsyncMock()
    rej_cb.from_user.id = user_id
    rej_cb.data = f"ntn:rej:{conf.id}"
    rej_cb.message.edit_text = AsyncMock()

    await handler.cb_ntn_reject(rej_cb)

    assert rej_cb.message.edit_text.called
    assert "Отклонено" in rej_cb.message.edit_text.call_args[0][0]
    assert len(fake_notion.logged_calls) == 0

    updated = await store.get_confirmation(conf.id)
    assert updated is not None
    assert updated.status == ConfirmationStatus.REJECTED


@pytest.mark.asyncio
async def test_unauthorized_user_blocked_on_command_and_callbacks(tmp_path: Path, tracer_repos):
    """Посторонний пользователь получает отказ на /git и всех колбэках."""
    repo_dir, bare_origin, _ = tracer_repos
    ws = Workspace(
        id="ws_pub",
        name="Pub",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(repo_dir),
        remote=str(bare_origin),
        notion_project="11111111111111111111111111111111",
    )
    db_path = str(tmp_path / "bot_unauth.db")
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.init_db()

    store = ConfirmationStore(db_path)
    git_provider = CountingGitProvider()
    fake_notion = FakeNotionClient()
    evaluator = GitProgressEvaluator(
        git_provider=git_provider,
        notion_client=fake_notion,
        confirmation_store=store,
        persona=Persona(id="p", name="O", workspaces=(ws,)),
        default_activity_db_id="33333333333333333333333333333333",
    )

    allowed_user = 100
    stranger = 999
    handler = EmailBotHandler(bot=AsyncMock(), db=db, allowed_user_id=allowed_user, git_evaluator=evaluator)

    # 1. /git
    msg = AsyncMock()
    msg.from_user.id = stranger
    await handler.handle_cmd_git(msg)
    assert not msg.answer.called

    # 2. ntn:req
    cb_req = AsyncMock()
    cb_req.from_user.id = stranger
    cb_req.data = "ntn:req:abcd:0"
    await handler.cb_ntn_request(cb_req)
    cb_req.answer.assert_called_with("⛔ Доступ запрещен", show_alert=True)

    # 3. ntn:conf
    cb_conf = AsyncMock()
    cb_conf.from_user.id = stranger
    cb_conf.data = "ntn:conf:some-id"
    await handler.cb_ntn_confirm(cb_conf)
    cb_conf.answer.assert_called_with("⛔ Доступ запрещен", show_alert=True)

    # 4. ntn:rej
    cb_rej = AsyncMock()
    cb_rej.from_user.id = stranger
    cb_rej.data = "ntn:rej:some-id"
    await handler.cb_ntn_reject(cb_rej)
    cb_rej.answer.assert_called_with("⛔ Доступ запрещен", show_alert=True)

    assert len(fake_notion.logged_calls) == 0
    assert len(git_provider.recorded_calls) == 0


@pytest.mark.asyncio
async def test_only_nda_workspaces_no_provider_calls(tmp_path: Path):
    """Только NDA: ноль вызовов провайдера, строка NDA в ответе, кнопок нет."""
    ws_nda = Workspace(
        id="ws_nda_only",
        name="NDA Only",
        clearance=WorkspaceClearance.RESTRICTED_NDA,
        path=str(tmp_path / "nda_dir"),
        remote="git@sec:nda.git",
        ssh_alias="sec_box",
        notion_project="11111111111111111111111111111111",
    )
    db_path = str(tmp_path / "bot_nda.db")
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.init_db()

    store = ConfirmationStore(db_path)
    git_provider = CountingGitProvider()
    fake_notion = FakeNotionClient()
    evaluator = GitProgressEvaluator(
        git_provider=git_provider,
        notion_client=fake_notion,
        confirmation_store=store,
        persona=Persona(id="p", name="O", workspaces=(ws_nda,)),
        default_activity_db_id="33333333333333333333333333333333",
    )
    user_id = 555
    handler = EmailBotHandler(bot=AsyncMock(), db=db, allowed_user_id=user_id, git_evaluator=evaluator)

    status_msg = AsyncMock()
    msg = AsyncMock()
    msg.from_user.id = user_id
    msg.answer = AsyncMock(return_value=status_msg)

    await handler.handle_cmd_git(msg)

    assert len(git_provider.recorded_calls) == 0
    run_text, kwargs = status_msg.edit_text.call_args[0][0], status_msg.edit_text.call_args[1]
    assert NDA_EXCLUDED_LINE in run_text
    assert kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_unknown_clearance_and_failing_persona_excluded(tmp_path: Path):
    """Неизвестный допуск и ошибка чтения персоны исключаются fail-closed."""
    ws_weird = SimpleNamespace(
        id="ws_weird",
        name="Weird Project",
        clearance="super_confidential_unknown",
        path=str(tmp_path),
        remote="git@weird:repo.git",
        notion_project="11111111111111111111111111111111",
    )
    db_path = str(tmp_path / "bot_fail.db")
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.init_db()
    store = ConfirmationStore(db_path)
    git_provider = CountingGitProvider()
    fake_notion = FakeNotionClient()

    # 1. Неизвестный clearance
    evaluator = GitProgressEvaluator(
        git_provider=git_provider,
        notion_client=fake_notion,
        confirmation_store=store,
        persona=SimpleNamespace(workspaces=[ws_weird]),
        default_activity_db_id="33333333333333333333333333333333",
    )
    run = await evaluator.evaluate()
    assert run.nda_excluded is True
    assert len(run.entries) == 0
    assert len(git_provider.recorded_calls) == 0

    # 2. Персона с ошибкой
    class BrokenPersona:
        @property
        def workspaces(self):
            raise RuntimeError("Database error loading workspaces")

    evaluator_broken = GitProgressEvaluator(
        git_provider=git_provider,
        notion_client=fake_notion,
        confirmation_store=store,
        persona=BrokenPersona(),
        default_activity_db_id="33333333333333333333333333333333",
    )
    run_broken = await evaluator_broken.evaluate()
    assert run_broken.nda_excluded is True
    assert len(run_broken.entries) == 0
    assert len(git_provider.recorded_calls) == 0


@pytest.mark.asyncio
async def test_stale_token_and_invalid_index(tmp_path: Path):
    """Устаревший токен или неверный индекс дают ответ 'Результат устарел'."""
    db_path = str(tmp_path / "bot_stale.db")
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.init_db()
    store = ConfirmationStore(db_path)
    evaluator = GitProgressEvaluator(
        git_provider=CountingGitProvider(),
        notion_client=FakeNotionClient(),
        confirmation_store=store,
        persona=None,
    )
    handler = EmailBotHandler(bot=AsyncMock(), db=db, allowed_user_id=123, git_evaluator=evaluator)

    cb = AsyncMock()
    cb.from_user.id = 123

    # Неизвестный токен
    cb.data = "ntn:req:badtoken:0"
    await handler.cb_ntn_request(cb)
    cb.answer.assert_called_with("Результат устарел, повторите /git", show_alert=True)

    # Известный токен, нечисловой индекс: ветка «Неверный индекс», а не «устарел»
    handler._git_runs["goodtoken"] = MagicMock(entries=[])
    cb.data = "ntn:req:goodtoken:xyz"
    await handler.cb_ntn_request(cb)
    cb.answer.assert_called_with("Неверный индекс", show_alert=True)

    # Известный токен, индекс вне диапазона
    cb.data = "ntn:req:goodtoken:5"
    await handler.cb_ntn_request(cb)
    cb.answer.assert_called_with("Результат устарел, повторите /git", show_alert=True)


@pytest.mark.asyncio
async def test_notion_proj_stub_marked_not_ready(tmp_path: Path, tracer_repos):
    """Заглушка notion-proj-* дает статус 'Notion не настроен' и не создает кнопку."""
    repo_dir, bare_origin, _ = tracer_repos
    ws = Workspace(
        id="ws_stub",
        name="Stub Project",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(repo_dir),
        remote=str(bare_origin),
        notion_project="notion-proj-lab",
    )
    db_path = str(tmp_path / "bot_stub.db")
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.init_db()
    store = ConfirmationStore(db_path)
    evaluator = GitProgressEvaluator(
        git_provider=CountingGitProvider(),
        notion_client=FakeNotionClient(),
        confirmation_store=store,
        persona=Persona(id="p", name="O", workspaces=(ws,)),
        default_activity_db_id="33333333333333333333333333333333",
    )
    handler = EmailBotHandler(bot=AsyncMock(), db=db, allowed_user_id=123, git_evaluator=evaluator)

    status_msg = AsyncMock()
    msg = AsyncMock()
    msg.from_user.id = 123
    msg.answer = AsyncMock(return_value=status_msg)

    await handler.handle_cmd_git(msg)

    run_text, kwargs = status_msg.edit_text.call_args[0][0], status_msg.edit_text.call_args[1]
    assert "Notion не настроен" in run_text
    assert kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_notion_error_handled_gracefully(tmp_path: Path, tracer_repos):
    """Сбой Notion API превращается в сообщение 'Не записано в Notion, повторите' без падения."""
    repo_dir, bare_origin, _ = tracer_repos
    ws = Workspace(
        id="ws_err",
        name="Error Project",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(repo_dir),
        remote=str(bare_origin),
        notion_project="11111111111111111111111111111111",
    )
    db_path = str(tmp_path / "bot_err.db")
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.init_db()
    store = ConfirmationStore(db_path)
    failing_notion = FakeNotionClient(should_fail=True)
    evaluator = GitProgressEvaluator(
        git_provider=CountingGitProvider(),
        notion_client=failing_notion,
        confirmation_store=store,
        persona=Persona(id="p", name="O", workspaces=(ws,)),
        default_activity_db_id="33333333333333333333333333333333",
    )
    handler = EmailBotHandler(bot=AsyncMock(), db=db, allowed_user_id=123, git_evaluator=evaluator)

    run = await evaluator.evaluate()
    proposal = await evaluator.propose_card(run.entries[0], run.date_iso)
    conf = proposal.confirmation

    cb = AsyncMock()
    cb.from_user.id = 123
    cb.data = f"ntn:conf:{conf.id}"

    await handler.cb_ntn_confirm(cb)

    cb.answer.assert_called_with("Не записано в Notion, повторите", show_alert=True)


@pytest.mark.asyncio
async def test_repeat_confirm_after_success_idempotent(tmp_path: Path, tracer_repos):
    """Повторное нажатие ntn:conf после успеха сообщает 'Запрос уже обработан'."""
    repo_dir, bare_origin, _ = tracer_repos
    ws = Workspace(
        id="ws_rep",
        name="Rep Project",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(repo_dir),
        remote=str(bare_origin),
        notion_project="11111111111111111111111111111111",
    )
    db_path = str(tmp_path / "bot_rep.db")
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.init_db()
    store = ConfirmationStore(db_path)
    fake_notion = FakeNotionClient()
    evaluator = GitProgressEvaluator(
        git_provider=CountingGitProvider(),
        notion_client=fake_notion,
        confirmation_store=store,
        persona=Persona(id="p", name="O", workspaces=(ws,)),
        default_activity_db_id="33333333333333333333333333333333",
    )
    handler = EmailBotHandler(bot=AsyncMock(), db=db, allowed_user_id=123, git_evaluator=evaluator)

    run = await evaluator.evaluate()
    proposal = await evaluator.propose_card(run.entries[0], run.date_iso)
    conf = proposal.confirmation

    cb = AsyncMock()
    cb.from_user.id = 123
    cb.data = f"ntn:conf:{conf.id}"
    cb.message.edit_text = AsyncMock()

    # Первый вызов - успех
    await handler.cb_ntn_confirm(cb)
    assert len(fake_notion.logged_calls) == 1

    # Второй вызов - защита от повтора
    cb2 = AsyncMock()
    cb2.from_user.id = 123
    cb2.data = f"ntn:conf:{conf.id}"
    await handler.cb_ntn_confirm(cb2)
    cb2.answer.assert_called_with("Запрос уже обработан (confirmed)", show_alert=True)
    assert len(fake_notion.logged_calls) == 1


@pytest.mark.asyncio
async def test_nda_unique_markers_not_leaked(tmp_path: Path, caplog):
    """Маркеры NDA-пространства не попадают в ответ бота, логи или вызовы клиентов."""
    marker_name = "TOP_SECRET_CODENAME_X77"
    nda_repo = tmp_path / "classified_subfolder_x77"
    nda_repo.mkdir()
    marker_commit = "classified proprietary patent logic x77"
    subprocess.run(["git", "init", "-b", "main"], cwd=nda_repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=nda_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=nda_repo, check=True)
    (nda_repo / "patent_x77.txt").write_text("x77\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=nda_repo, check=True)
    subprocess.run(["git", "commit", "-m", marker_commit], cwd=nda_repo, check=True, capture_output=True)
    marker_path = str(nda_repo)
    nda_log = subprocess.run(
        ["git", "log", "--format=%s"], cwd=nda_repo, check=True, capture_output=True, text=True
    ).stdout
    assert marker_commit in nda_log, "маркер коммита должен реально попасть в тестовый NDA-репозиторий"

    ws_nda = Workspace(
        id="ws_classified",
        name=marker_name,
        clearance=WorkspaceClearance.RESTRICTED_NDA,
        path=marker_path,
        remote=f"git@corp.internal:{marker_name}.git",
        ssh_alias="corp_box",
        notion_project="11111111111111111111111111111111",
    )
    db_path = str(tmp_path / "bot_leak.db")
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.init_db()
    store = ConfirmationStore(db_path)
    git_provider = CountingGitProvider()
    fake_notion = FakeNotionClient()
    evaluator = GitProgressEvaluator(
        git_provider=git_provider,
        notion_client=fake_notion,
        confirmation_store=store,
        persona=Persona(id="p", name="O", workspaces=(ws_nda,)),
        default_activity_db_id="33333333333333333333333333333333",
    )
    handler = EmailBotHandler(bot=AsyncMock(), db=db, allowed_user_id=123, git_evaluator=evaluator)

    status_msg = AsyncMock()
    msg = AsyncMock()
    msg.from_user.id = 123
    msg.answer = AsyncMock(return_value=status_msg)

    await handler.handle_cmd_git(msg)

    run_text = status_msg.edit_text.call_args[0][0]

    assert marker_name not in run_text
    assert marker_path not in run_text
    assert marker_commit not in run_text

    logs = caplog.text
    assert marker_name not in logs
    assert marker_path not in logs
    assert marker_commit not in logs

    assert len(git_provider.recorded_calls) == 0
    assert len(fake_notion.logged_calls) == 0


# --- Task 2: сквозные сценарии (план 04-10) --------------------------------------------------

@pytest.mark.asyncio
async def test_reject_writes_nothing_and_blocks_same_day(tmp_path: Path, tracer_repos):
    """Отклонение: ntn:rej, FakeNotion без вызовов; повторный /git и ntn:req в тот же день показывают состояние «отклонена», новой карточки нет."""
    repo_dir, bare_origin, _ = tracer_repos
    ws = Workspace(
        id="ws_rej_block",
        name="Reject Block Project",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(repo_dir),
        remote=str(bare_origin),
        notion_project="11111111111111111111111111111111",
    )
    db_path = str(tmp_path / "bot_rej_block.db")
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.init_db()

    store = ConfirmationStore(db_path)
    git_provider = CountingGitProvider()
    fake_notion = FakeNotionClient(is_configured=True)
    evaluator = GitProgressEvaluator(
        git_provider=git_provider,
        notion_client=fake_notion,
        confirmation_store=store,
        persona=Persona(id="p1", name="Owner", workspaces=(ws,)),
        default_activity_db_id="33333333333333333333333333333333",
    )
    user_id = 777
    handler = EmailBotHandler(bot=AsyncMock(), db=db, allowed_user_id=user_id, git_evaluator=evaluator)

    # 1. Первый прогон команды /git и запрос карточки
    status_msg = AsyncMock()
    msg = AsyncMock()
    msg.from_user.id = user_id
    msg.answer = AsyncMock(return_value=status_msg)
    await handler.handle_cmd_git(msg)

    reply_markup = status_msg.edit_text.call_args[1]["reply_markup"]
    btn_req = reply_markup.inline_keyboard[0][0]

    req_cb = AsyncMock()
    req_cb.from_user.id = user_id
    req_cb.data = btn_req.callback_data
    req_cb.message = AsyncMock()
    req_cb.message.answer = AsyncMock()
    req_cb.answer = AsyncMock()
    await handler.cb_ntn_request(req_cb)

    card_kb = req_cb.message.answer.call_args[1]["reply_markup"]
    btn_rej = next(b for row in card_kb.inline_keyboard for b in row if b.callback_data.startswith("ntn:rej:"))

    # Отклоняем карточку
    rej_cb = AsyncMock()
    rej_cb.from_user.id = user_id
    rej_cb.data = btn_rej.callback_data
    rej_cb.message = AsyncMock()
    rej_cb.message.edit_text = AsyncMock()
    rej_cb.answer = AsyncMock()
    await handler.cb_ntn_reject(rej_cb)

    assert len(fake_notion.logged_calls) == 0

    # 2. Повторный прогон /git в тот же день
    status_msg2 = AsyncMock()
    msg2 = AsyncMock()
    msg2.from_user.id = user_id
    msg2.answer = AsyncMock(return_value=status_msg2)
    await handler.handle_cmd_git(msg2)

    reply_markup2 = status_msg2.edit_text.call_args[1]["reply_markup"]
    btn_req2 = reply_markup2.inline_keyboard[0][0]

    req_cb2 = AsyncMock()
    req_cb2.from_user.id = user_id
    req_cb2.data = btn_req2.callback_data
    req_cb2.message = AsyncMock()
    req_cb2.message.answer = AsyncMock()
    req_cb2.answer = AsyncMock()
    await handler.cb_ntn_request(req_cb2)

    req_cb2.answer.assert_called_with("Карточка за этот период отклонена", show_alert=True)
    req_cb2.message.answer.assert_not_called()
    assert len(fake_notion.logged_calls) == 0


@pytest.mark.asyncio
async def test_rerun_same_day_keeps_single_card(tmp_path: Path, tracer_repos):
    """Повторный прогон: два /git и два ntn:req за один день оставляют одну запись в хранилище и одну отправленную карточку."""
    repo_dir, bare_origin, _ = tracer_repos
    ws = Workspace(
        id="ws_rerun_single",
        name="Rerun Single Project",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(repo_dir),
        remote=str(bare_origin),
        notion_project="11111111111111111111111111111111",
    )
    db_path = str(tmp_path / "bot_rerun_single.db")
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.init_db()

    store = ConfirmationStore(db_path)
    git_provider = CountingGitProvider()
    fake_notion = FakeNotionClient(is_configured=True)
    evaluator = GitProgressEvaluator(
        git_provider=git_provider,
        notion_client=fake_notion,
        confirmation_store=store,
        persona=Persona(id="p1", name="Owner", workspaces=(ws,)),
        default_activity_db_id="33333333333333333333333333333333",
    )
    user_id = 777
    handler = EmailBotHandler(bot=AsyncMock(), db=db, allowed_user_id=user_id, git_evaluator=evaluator)

    # Первый /git и ntn:req
    status_msg1 = AsyncMock()
    msg1 = AsyncMock()
    msg1.from_user.id = user_id
    msg1.answer = AsyncMock(return_value=status_msg1)
    await handler.handle_cmd_git(msg1)

    btn_req1 = status_msg1.edit_text.call_args[1]["reply_markup"].inline_keyboard[0][0]
    req_cb1 = AsyncMock()
    req_cb1.from_user.id = user_id
    req_cb1.data = btn_req1.callback_data
    req_cb1.message = AsyncMock()
    req_cb1.message.answer = AsyncMock()
    req_cb1.answer = AsyncMock()
    await handler.cb_ntn_request(req_cb1)
    assert req_cb1.message.answer.called

    # Второй /git и ntn:req
    status_msg2 = AsyncMock()
    msg2 = AsyncMock()
    msg2.from_user.id = user_id
    msg2.answer = AsyncMock(return_value=status_msg2)
    await handler.handle_cmd_git(msg2)

    btn_req2 = status_msg2.edit_text.call_args[1]["reply_markup"].inline_keyboard[0][0]
    req_cb2 = AsyncMock()
    req_cb2.from_user.id = user_id
    req_cb2.data = btn_req2.callback_data
    req_cb2.message = AsyncMock()
    req_cb2.message.answer = AsyncMock()
    req_cb2.answer = AsyncMock()
    await handler.cb_ntn_request(req_cb2)
    assert req_cb2.message.answer.called

    # В хранилище ровно одна запись!
    confs = await store.find_confirmations(action_type="notion_project_sync")
    assert len(confs) == 1


@pytest.mark.asyncio
async def test_page_already_in_notion_not_duplicated(tmp_path: Path, tracer_repos):
    """Запись уже есть в Notion: find_project_activity вернул страницу, подтверждение завершается успехом без вызова create."""
    repo_dir, bare_origin, _ = tracer_repos
    ws = Workspace(
        id="ws_dedup_test",
        name="Dedup Project",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(repo_dir),
        remote=str(bare_origin),
        notion_project="11111111111111111111111111111111",
    )
    db_path = str(tmp_path / "bot_dedup.db")
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.init_db()

    store = ConfirmationStore(db_path)
    git_provider = CountingGitProvider()
    fake_notion = FakeNotionClient(
        is_configured=True,
        existing_page={"id": "page-notion-already-there-888", "object": "page"},
    )
    evaluator = GitProgressEvaluator(
        git_provider=git_provider,
        notion_client=fake_notion,
        confirmation_store=store,
        persona=Persona(id="p1", name="Owner", workspaces=(ws,)),
        default_activity_db_id="33333333333333333333333333333333",
    )
    user_id = 777
    handler = EmailBotHandler(bot=AsyncMock(), db=db, allowed_user_id=user_id, git_evaluator=evaluator)

    # Прогоняем /git и ntn:req
    status_msg = AsyncMock()
    msg = AsyncMock()
    msg.from_user.id = user_id
    msg.answer = AsyncMock(return_value=status_msg)
    await handler.handle_cmd_git(msg)

    btn_req = status_msg.edit_text.call_args[1]["reply_markup"].inline_keyboard[0][0]
    req_cb = AsyncMock()
    req_cb.from_user.id = user_id
    req_cb.data = btn_req.callback_data
    req_cb.message = AsyncMock()
    req_cb.message.answer = AsyncMock()
    req_cb.answer = AsyncMock()
    await handler.cb_ntn_request(req_cb)

    card_kb = req_cb.message.answer.call_args[1]["reply_markup"]
    btn_conf = next(b for row in card_kb.inline_keyboard for b in row if b.callback_data.startswith("ntn:conf:"))

    conf_cb = AsyncMock()
    conf_cb.from_user.id = user_id
    conf_cb.data = btn_conf.callback_data
    conf_cb.message = AsyncMock()
    conf_cb.message.edit_text = AsyncMock()
    conf_cb.answer = AsyncMock()

    await handler.cb_ntn_confirm(conf_cb)

    # find_project_activity был вызван
    assert len(fake_notion.find_calls) == 1
    # log_project_activity НЕ был вызван (дедупликация)
    assert len(fake_notion.logged_calls) == 0

    conf_cb.answer.assert_called_with("Записано в Notion")
    assert conf_cb.message.edit_text.called


@pytest.mark.asyncio
async def test_ssh_failure_status_line_and_daemon_alive(tmp_path: Path):
    """Сбой SSH: remote указывает на несуществующий путь, настоящий git fetch падает: строка «сбой SSH», карточки и кнопки нет, обработчик не падает."""
    repo_dir = tmp_path / "ssh_fail_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=repo_dir, check=True)
    (repo_dir / "f.txt").write_text("ok\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, check=True)

    # Remote на несуществующий локальный путь
    broken_remote = str(tmp_path / "broken_nonexistent_origin.git")
    subprocess.run(["git", "remote", "add", "origin", broken_remote], cwd=repo_dir, check=True)

    ws_broken = Workspace(
        id="ws_broken_ssh",
        name="Broken SSH Project",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(repo_dir),
        remote=broken_remote,
        notion_project="11111111111111111111111111111111",
    )
    db_path = str(tmp_path / "bot_ssh_fail.db")
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.init_db()

    store = ConfirmationStore(db_path)
    # Настоящий SshGitProvider без моков!
    real_git = SshGitProvider()
    fake_notion = FakeNotionClient(is_configured=True)
    evaluator = GitProgressEvaluator(
        git_provider=real_git,
        notion_client=fake_notion,
        confirmation_store=store,
        persona=Persona(id="p1", name="Owner", workspaces=(ws_broken,)),
        default_activity_db_id="33333333333333333333333333333333",
    )
    user_id = 777
    handler = EmailBotHandler(bot=AsyncMock(), db=db, allowed_user_id=user_id, git_evaluator=evaluator)

    status_msg = AsyncMock()
    msg = AsyncMock()
    msg.from_user.id = user_id
    msg.answer = AsyncMock(return_value=status_msg)

    # Не должно упасть!
    await handler.handle_cmd_git(msg)

    run_text = status_msg.edit_text.call_args[0][0]
    reply_markup = status_msg.edit_text.call_args[1]["reply_markup"]

    assert "сбой SSH" in run_text
    # Для упавшего fetch кнопки Notion нет
    assert reply_markup is None


@pytest.mark.asyncio
async def test_scheduler_cycle_card_to_notion_write(tmp_path: Path, tracer_repos):
    """Вход планировщика: run_git_progress_cycle отправляет карточку с кнопками, нажатие ntn:conf по её идентификатору пишет в Notion один раз."""
    from src.main import run_git_progress_cycle

    repo_dir, bare_origin, _ = tracer_repos
    ws = Workspace(
        id="ws_sched_test",
        name="Scheduler Cycle Project",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(repo_dir),
        remote=str(bare_origin),
        notion_project="11111111111111111111111111111111",
    )
    db_path = str(tmp_path / "bot_sched_cycle.db")
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.init_db()

    store = ConfirmationStore(db_path)
    git_provider = CountingGitProvider()
    fake_notion = FakeNotionClient(is_configured=True)
    evaluator = GitProgressEvaluator(
        git_provider=git_provider,
        notion_client=fake_notion,
        confirmation_store=store,
        persona=Persona(id="p1", name="Owner", workspaces=(ws,)),
        default_activity_db_id="33333333333333333333333333333333",
    )
    user_id = 777
    handler = EmailBotHandler(bot=AsyncMock(), db=db, allowed_user_id=user_id, git_evaluator=evaluator)

    notifier = AsyncMock()
    notifier.send_message = AsyncMock()

    # Запуск цикла планировщика
    await run_git_progress_cycle(evaluator, notifier)

    # Карточка отправлена через notifier.send_message
    assert notifier.send_message.called
    card_call = next(
        c for c in notifier.send_message.call_args_list if c.kwargs.get("reply_markup") is not None
    )
    kb = card_call.kwargs["reply_markup"]
    btn_conf = next(b for row in kb.inline_keyboard for b in row if b.callback_data.startswith("ntn:conf:"))

    # Нажимаем кнопку ntn:conf
    conf_cb = AsyncMock()
    conf_cb.from_user.id = user_id
    conf_cb.data = btn_conf.callback_data
    conf_cb.message = AsyncMock()
    conf_cb.message.edit_text = AsyncMock()
    conf_cb.answer = AsyncMock()

    await handler.cb_ntn_confirm(conf_cb)

    assert len(fake_notion.logged_calls) == 1
    conf_cb.answer.assert_called_with("Записано в Notion")


# --- Доработка по ревизии 2026-10-15 (quick 261015-9sl) ---------------------------------------


async def _build_stack(tmp_path, repo_dir, bare_origin, ws_id, *, should_fail=False, user_id=123):
    """Собирает связку Database + ConfirmationStore + GitProgressEvaluator + EmailBotHandler на tmp_path."""
    ws = Workspace(
        id=ws_id,
        name=f"{ws_id} project",
        clearance=WorkspaceClearance.PUBLIC,
        path=str(repo_dir),
        remote=str(bare_origin),
        notion_project="11111111111111111111111111111111",
    )
    db_path = str(tmp_path / f"{ws_id}.db")
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.init_db()
    store = ConfirmationStore(db_path)
    notion = FakeNotionClient(is_configured=True, should_fail=should_fail)
    evaluator = GitProgressEvaluator(
        git_provider=CountingGitProvider(),
        notion_client=notion,
        confirmation_store=store,
        persona=Persona(id="p1", name="Owner", workspaces=(ws,)),
        default_activity_db_id="33333333333333333333333333333333",
    )
    handler = EmailBotHandler(bot=AsyncMock(), db=db, allowed_user_id=user_id, git_evaluator=evaluator)
    return SimpleNamespace(
        handler=handler,
        evaluator=evaluator,
        store=store,
        notion=notion,
        user_id=user_id,
    )


def _make_callback(user_id, data):
    """Фейковый CallbackQuery с заданными from_user.id и data."""
    cb = AsyncMock()
    cb.from_user.id = user_id
    cb.data = data
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    return cb


async def _open_card(stack):
    """Выполняет /git и ntn:req, возвращает (callback ntn:conf, callback ntn:rej, id карточки)."""
    status_msg = AsyncMock()
    msg = AsyncMock()
    msg.from_user.id = stack.user_id
    msg.answer = AsyncMock(return_value=status_msg)
    await stack.handler.handle_cmd_git(msg)

    run_markup = status_msg.edit_text.call_args[1]["reply_markup"]
    req_data = next(
        b.callback_data
        for row in run_markup.inline_keyboard
        for b in row
        if b.callback_data.startswith("ntn:req:")
    )
    req_cb = _make_callback(stack.user_id, req_data)
    await stack.handler.cb_ntn_request(req_cb)

    card_kb = req_cb.message.answer.call_args[1]["reply_markup"]
    conf_data = next(
        b.callback_data for row in card_kb.inline_keyboard for b in row if b.callback_data.startswith("ntn:conf:")
    )
    rej_data = next(
        b.callback_data for row in card_kb.inline_keyboard for b in row if b.callback_data.startswith("ntn:rej:")
    )
    conf_id = conf_data.split(":", 2)[2]
    return conf_data, rej_data, conf_id


@pytest.mark.asyncio
async def test_notion_failure_reopens_card_to_pending(tmp_path: Path, tracer_repos):
    """Сбой Notion при подтверждении возвращает карточку в pending (reopen_action); после восстановления Notion повтор пишет ровно один раз."""
    repo_dir, bare_origin, _ = tracer_repos
    stack = await _build_stack(tmp_path, repo_dir, bare_origin, "ws_reopen", should_fail=True)
    conf_data, _, conf_id = await _open_card(stack)

    cb = _make_callback(stack.user_id, conf_data)
    await stack.handler.cb_ntn_confirm(cb)

    cb.answer.assert_called_with("Не записано в Notion, повторите", show_alert=True)
    conf = await stack.store.get_confirmation(conf_id)
    assert conf.status == ConfirmationStatus.PENDING
    assert conf.confirmed_by is None
    assert conf.confirmed_at is None
    assert stack.notion.logged_calls == []

    stack.notion.should_fail = False
    cb2 = _make_callback(stack.user_id, conf_data)
    await stack.handler.cb_ntn_confirm(cb2)
    cb2.answer.assert_called_with("Записано в Notion")
    assert len(stack.notion.logged_calls) == 1
    conf = await stack.store.get_confirmation(conf_id)
    assert conf.status == ConfirmationStatus.CONFIRMED


@pytest.mark.asyncio
async def test_notion_failure_without_reopen_would_leave_card_confirmed(
    tmp_path: Path, tracer_repos, monkeypatch
):
    """Зонд мутации: при подменённом reopen_action карточка после сбоя остаётся confirmed, а повтор отвечает «уже обработан».
    Тест подменяет reopen_action и НЕ фиксирует желаемое поведение продукта; он доказывает, что утверждения теста 1 не пустые.
    """

    async def _noop_reopen(self, confirmation_id):
        return None

    monkeypatch.setattr(ConfirmationStore, "reopen_action", _noop_reopen)

    repo_dir, bare_origin, _ = tracer_repos
    stack = await _build_stack(tmp_path, repo_dir, bare_origin, "ws_reopen_probe", should_fail=True)
    conf_data, _, conf_id = await _open_card(stack)

    cb = _make_callback(stack.user_id, conf_data)
    await stack.handler.cb_ntn_confirm(cb)

    conf = await stack.store.get_confirmation(conf_id)
    assert conf.status == ConfirmationStatus.CONFIRMED

    stack.notion.should_fail = False
    cb2 = _make_callback(stack.user_id, conf_data)
    await stack.handler.cb_ntn_confirm(cb2)
    cb2.answer.assert_called_with("Запрос уже обработан (confirmed)", show_alert=True)
    assert stack.notion.logged_calls == []


@pytest.mark.asyncio
async def test_no_notion_writes_before_confirmation_after_request(tmp_path: Path, tracer_repos):
    """После /git и ntn:req до нажатия владельцем ноль записей в Notion; карточка в pending; контрольное подтверждение пишет один раз."""
    repo_dir, bare_origin, _ = tracer_repos
    stack = await _build_stack(tmp_path, repo_dir, bare_origin, "ws_zero_req")
    conf_data, _, _ = await _open_card(stack)

    assert stack.notion.logged_calls == []
    confs = await stack.store.find_confirmations(action_type="notion_project_sync")
    assert len(confs) == 1
    assert confs[0].status == ConfirmationStatus.PENDING

    cb = _make_callback(stack.user_id, conf_data)
    await stack.handler.cb_ntn_confirm(cb)
    assert len(stack.notion.logged_calls) == 1


@pytest.mark.asyncio
async def test_no_notion_writes_before_confirmation_after_scheduler_cycle(tmp_path: Path, tracer_repos):
    """После цикла планировщика карточка отправлена в pending и ноль записей в Notion; нажатие ntn:conf пишет один раз."""
    from src.main import run_git_progress_cycle

    repo_dir, bare_origin, _ = tracer_repos
    stack = await _build_stack(tmp_path, repo_dir, bare_origin, "ws_zero_cycle", user_id=777)

    notifier = AsyncMock()
    notifier.send_message = AsyncMock()
    await run_git_progress_cycle(stack.evaluator, notifier)

    assert stack.notion.logged_calls == []
    confs = await stack.store.find_confirmations(action_type="notion_project_sync")
    assert len(confs) == 1
    assert confs[0].status == ConfirmationStatus.PENDING

    card_call = next(
        c for c in notifier.send_message.call_args_list if c.kwargs.get("reply_markup") is not None
    )
    kb = card_call.kwargs["reply_markup"]
    btn_conf = next(b for row in kb.inline_keyboard for b in row if b.callback_data.startswith("ntn:conf:"))

    cb = _make_callback(stack.user_id, btn_conf.callback_data)
    await stack.handler.cb_ntn_confirm(cb)
    assert len(stack.notion.logged_calls) == 1


@pytest.mark.asyncio
async def test_confirm_after_reject_does_not_write_to_notion(tmp_path: Path, tracer_repos):
    """Подтверждение после отклонения отвечает «уже обработан (rejected)», в Notion ничего не пишет, статус остаётся rejected."""
    repo_dir, bare_origin, _ = tracer_repos
    stack = await _build_stack(tmp_path, repo_dir, bare_origin, "ws_conf_after_rej")
    conf_data, rej_data, conf_id = await _open_card(stack)

    await stack.handler.cb_ntn_reject(_make_callback(stack.user_id, rej_data))
    conf = await stack.store.get_confirmation(conf_id)
    assert conf.status == ConfirmationStatus.REJECTED

    cb = _make_callback(stack.user_id, conf_data)
    await stack.handler.cb_ntn_confirm(cb)

    cb.answer.assert_called_with("Запрос уже обработан (rejected)", show_alert=True)
    assert stack.notion.logged_calls == []
    conf = await stack.store.get_confirmation(conf_id)
    assert conf.status == ConfirmationStatus.REJECTED


@pytest.mark.asyncio
async def test_reject_after_confirm_keeps_confirmed_record(tmp_path: Path, tracer_repos):
    """Отклонение после подтверждения не портит данные: статус confirmed, confirmed_by не меняется, записей в Notion не прибавляется.
    Тест фиксирует безопасность данных, а не текст ответа: cb_ntn_reject при confirmed отвечает «Уже подтверждено» и ничего не меняет (04-REVISION.md, раздел 2 п. 6).
    """
    repo_dir, bare_origin, _ = tracer_repos
    stack = await _build_stack(tmp_path, repo_dir, bare_origin, "ws_rej_after_conf", user_id=777)
    conf_data, rej_data, conf_id = await _open_card(stack)

    await stack.handler.cb_ntn_confirm(_make_callback(stack.user_id, conf_data))
    conf = await stack.store.get_confirmation(conf_id)
    assert conf.status == ConfirmationStatus.CONFIRMED
    assert conf.confirmed_by == str(stack.user_id)
    assert len(stack.notion.logged_calls) == 1

    await stack.handler.cb_ntn_reject(_make_callback(stack.user_id, rej_data))

    conf = await stack.store.get_confirmation(conf_id)
    assert conf.status == ConfirmationStatus.CONFIRMED
    assert conf.confirmed_by == str(stack.user_id)
    assert len(stack.notion.logged_calls) == 1

