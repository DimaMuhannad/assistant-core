"""Сквозной тест цепочки /git -> оценка -> HITL -> Notion (Phase 4 Tracer & Guarded Branches)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
import subprocess
import textwrap
from types import SimpleNamespace
from unittest.mock import AsyncMock

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

    def __init__(self, is_configured: bool = True, should_fail: bool = False):
        self.is_configured = is_configured
        self.should_fail = should_fail
        self.logged_calls: list[dict] = []

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

    # Неверный формат индекса
    cb.data = "ntn:req:badtoken:xyz"
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
    marker_path = str(tmp_path / "classified_subfolder_x77")
    marker_commit = "classified proprietary patent logic x77"

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
