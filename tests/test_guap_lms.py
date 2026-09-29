"""Unit tests for GuapLmsClient (pro.guap.ru)."""

import pytest
from unittest.mock import MagicMock, patch
from src.connectors.guap_lms.client import GuapLmsClient


def test_is_configured_property():
    client_empty = GuapLmsClient(email="", password="")
    assert not client_empty.is_configured

    client_valid = GuapLmsClient(email="user@guap.ru", password="secret_password")
    assert client_valid.is_configured


def test_is_authenticated_check():
    client = GuapLmsClient(email="user@guap.ru", password="pass")
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch.object(client.session, "get", return_value=mock_resp):
        assert client.is_authenticated()

    mock_resp_redir = MagicMock()
    mock_resp_redir.status_code = 302
    with patch.object(client.session, "get", return_value=mock_resp_redir):
        assert not client.is_authenticated()


def test_parse_tasks_table():
    client = GuapLmsClient(email="user@guap.ru", password="pass")
    html_content = """
    <html>
      <body>
        <table>
          <tr><th>Действия</th><th>№</th><th>Дисциплина</th><th>Название</th><th>Тип</th><th>Срок</th><th>Видимость</th><th>Дата</th></tr>
          <tr>
            <td><a href="/inside/professor/tasks/101/show">Просмотр</a></td>
            <td>1</td>
            <td>Физика (1632)</td>
            <td><a href="/inside/professor/tasks/101/show">Лабораторная работа №1</a></td>
            <td>Лабораторная работа</td>
            <td>15.10.2026</td>
            <td class="text-center"><i class="fa fa-eye text-success" title="Виден у студентов"></i></td>
            <td>20.09.2026</td>
          </tr>
          <tr>
            <td><a href="/inside/professor/tasks/102/show">Просмотр</a></td>
            <td>2</td>
            <td>ОПД (М631К)</td>
            <td><a href="/inside/professor/tasks/102/show">Тестовое задание</a></td>
            <td>Задание</td>
            <td>31.10.2026</td>
            <td class="text-center"><i class="fa fa-eye-slash text-danger" title="Не виден у студентов"></i></td>
            <td>29.09.2026</td>
          </tr>
        </table>
      </body>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.text = html_content
    mock_resp.status_code = 200

    with patch.object(client, "ensure_authenticated"):
        with patch.object(client.session, "get", return_value=mock_resp):
            tasks = client.list_tasks(semester=28)

    assert len(tasks) == 2

    # Task 1: Visible
    assert tasks[0]["id"] == 101
    assert tasks[0]["title"] == "Лабораторная работа №1"
    assert tasks[0]["is_public"] is True
    assert tasks[0]["deadline"] == "15.10.2026"

    # Task 2: Hidden
    assert tasks[1]["id"] == 102
    assert tasks[1]["title"] == "Тестовое задание"
    assert tasks[1]["is_public"] is False
    assert tasks[1]["deadline"] == "31.10.2026"


def test_parse_task_details_and_student_reports():
    client = GuapLmsClient(email="user@guap.ru", password="pass")
    html_content = """
    <html>
      <body>
        <h1>Лабораторная работа №1</h1>
        <h5>Дисциплина: Физика (1632)</h5>
        <h5>Тип: Лабораторная работа</h5>
        <h5>Выполнили: 25 из 30 студентов</h5>
        <h5>Ожидают проверки: 2 студентов</h5>
        <table>
          <tr><th>№</th><th>Студент</th><th>Группа</th><th>Статус</th><th>Дата загрузки</th><th>Дата проверки</th></tr>
          <tr>
            <td>1</td>
            <td>Иванов Иван Иванович</td>
            <td>1632</td>
            <td>Ожидает проверки</td>
            <td>28.09.2026 14:30</td>
            <td>-</td>
            <td><a href="/inside/professor/reports/55512/download">Скачать</a></td>
          </tr>
        </table>
      </body>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.text = html_content
    mock_resp.status_code = 200

    with patch.object(client, "ensure_authenticated"):
        with patch.object(client.session, "get", return_value=mock_resp):
            details = client.get_task_details(101)

    assert details["task_id"] == 101
    assert "Физика" in details["subject"]
    assert details["completed_stats"] == "25 из 30 студентов"
    assert details["pending_stats"] == "2 студентов"
    assert details["reports_count"] == 1

    rep = details["reports"][0]
    assert rep["report_id"] == 55512
    assert rep["student_name"] == "Иванов Иван Иванович"
    assert rep["group"] == "1632"
    assert rep["status"] == "Ожидает проверки"
    assert "/reports/55512/download" in rep["download_url"]


def test_create_task_omits_public_flag_when_hidden():
    client = GuapLmsClient(email="user@guap.ru", password="pass")

    create_html = """
    <form action="/inside/professor/tasks/store?id=0&semesters=28&_method=POST" method="post">
      <input type="hidden" name="token" value="mock_csrf_token_123">
    </form>
    """
    mock_get = MagicMock()
    mock_get.text = create_html
    mock_get.status_code = 200

    mock_post = MagicMock()
    mock_post.status_code = 200
    mock_post.url = "https://pro.guap.ru/inside/professor/tasks/999/show"

    captured_data = {}

    def fake_post(url, data, files, timeout):
        nonlocal captured_data
        captured_data = data
        return mock_post

    with patch.object(client, "ensure_authenticated"):
        with patch.object(client.session, "get", return_value=mock_get):
            with patch.object(client.session, "post", side_effect=fake_post):
                res = client.create_task(
                    name="[ТЕСТ] Скрытая лабораторная",
                    subject_id=3443405,
                    group_ids=[7900],
                    is_public=False,  # Should NOT include 'public' in data
                )

    assert res["status"] == "success"
    assert res["created_id"] == 999
    assert res["is_public"] is False
    assert "public" not in captured_data
    assert captured_data["token"] == "mock_csrf_token_123"
    assert captured_data["subjects[]"] == ["3443405"]
