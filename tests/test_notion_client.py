"""Unit tests for NotionAsyncClient and property builders."""

from unittest.mock import AsyncMock, patch, MagicMock
import pytest
import httpx

from src.connectors.notion import schema
from src.connectors.notion.client import NotionAsyncClient
from src.models.second_brain import (
    CompletedTaskItem,
    DailyJournalItem,
    DebriefResult,
    LifeArea,
    NewTaskItem,
    TaskPriority,
    WaitingForItem,
)


def test_schema_builders():
    assert schema.title_property("Hello") == {"title": [{"text": {"content": "Hello"}}]}
    assert schema.select_property("P1") == {"select": {"name": "P1"}}
    assert schema.status_property("Done") == {"status": {"name": "Done"}}
    assert schema.date_property("2026-09-29") == {"date": {"start": "2026-09-29"}}
    assert schema.number_property(45) == {"number": 45}
    assert schema.relation_property(["id1", "id2"]) == {"relation": [{"id": "id1"}, {"id": "id2"}]}


@pytest.mark.asyncio
async def test_notion_client_unconfigured():
    client = NotionAsyncClient(api_key="")
    assert not client.is_configured
    assert await client.get_current_user() is None

    result = DebriefResult(
        completed_tasks=[],
        new_tasks=[],
        waiting_for_items=[],
        journal_entry=DailyJournalItem(
            date_str="2026-09-28",
            done_summary="Nothing",
            key_insights=None,
            raw_transcript="",
        ),
    )
    report = await client.sync_debrief(result)
    assert report["journal_created"] is False
    assert len(report["created_tasks"]) == 0


@pytest.mark.asyncio
async def test_notion_client_create_and_sync():
    client = NotionAsyncClient(api_key="ntn_mock_12345")
    assert client.is_configured

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "page_task_123"}
    mock_resp.raise_for_status = MagicMock()

    mock_async_client = AsyncMock()
    mock_async_client.post.return_value = mock_resp
    mock_async_client.patch.return_value = mock_resp
    mock_async_client.__aenter__.return_value = mock_async_client
    mock_async_client.__aexit__.return_value = None

    with patch.object(client, "_client", return_value=mock_async_client):
        # 1. Test create_task
        task_res = await client.create_task(
            database_id="db_tasks_123",
            title="Заехать в отдел кадров",
            priority="P1",
            area="ГУАП",
            due_date="2026-09-29",
        )
        assert task_res["id"] == "page_task_123"
        assert mock_async_client.post.called

        # 2. Test mark_task_done
        done_res = await client.mark_task_done("page_task_123")
        assert done_res["id"] == "page_task_123"
        assert mock_async_client.patch.called

        # 3. Test sync_debrief
        debrief_res = DebriefResult(
            completed_tasks=[
                CompletedTaskItem(raw_mention="Сдал лабы", normalized_title="Сдал лабы", project_name="ГУАП")
            ],
            new_tasks=[
                NewTaskItem(title="Подписать приказ", area=LifeArea.GUAP, priority=TaskPriority.P1)
            ],
            waiting_for_items=[
                WaitingForItem(what="Введение", person="Коля", check_date="2026-10-02")
            ],
            journal_entry=DailyJournalItem(
                date_str="2026-09-28",
                done_summary="Сдал лабы",
                key_insights="Все отлично",
                raw_transcript="Текст",
            ),
        )

        def mock_post_handler(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            if "/query" in url:
                resp.json.return_value = {"results": [{"id": "existing_page_id"}]}
            else:
                resp.json.return_value = {"id": "new_page_id_123"}
            return resp

        mock_async_client.post.side_effect = mock_post_handler

        sync_report = await client.sync_debrief(
            debrief_res,
            tasks_db_id="db_tasks_123",
            waiting_db_id="db_wait_123",
            journal_db_id="db_journ_123",
        )

        assert "existing_page_id" in sync_report["marked_done"]
        assert len(sync_report["created_tasks"]) == 1
        assert len(sync_report["created_waiting"]) == 1
        assert sync_report["journal_created"] is True


@pytest.mark.asyncio
async def test_find_project_activity_payload():
    client = NotionAsyncClient(api_key="ntn_mock_12345")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"results": [{"id": "act_page_1"}]}
    mock_resp.raise_for_status = MagicMock()

    mock_async_client = AsyncMock()
    mock_async_client.post.return_value = mock_resp
    mock_async_client.__aenter__.return_value = mock_async_client
    mock_async_client.__aexit__.return_value = None

    with patch.object(client, "_client", return_value=mock_async_client):
        res = await client.find_project_activity(
            database_id="db_act_999",
            project_page_id="proj_page_777",
            date_iso="2026-10-11",
        )

    assert res == {"id": "act_page_1"}
    mock_async_client.post.assert_called_once_with(
        "/databases/db_act_999/query",
        json={
            "filter": {
                "and": [
                    {"property": "Project", "relation": {"contains": "proj_page_777"}},
                    {"property": "Date", "date": {"equals": "2026-10-11"}},
                ]
            },
            "page_size": 1,
        },
    )


@pytest.mark.asyncio
async def test_find_project_activity_results():
    client = NotionAsyncClient(api_key="ntn_mock_12345")

    # 1. Результат с записью
    mock_resp_found = MagicMock()
    mock_resp_found.status_code = 200
    mock_resp_found.json.return_value = {"results": [{"id": "page_found"}]}
    mock_resp_found.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp_found
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch.object(client, "_client", return_value=mock_client):
        found = await client.find_project_activity("db", "proj", "2026-10-11")
        assert found == {"id": "page_found"}

    # 2. Пустой результат
    mock_resp_empty = MagicMock()
    mock_resp_empty.status_code = 200
    mock_resp_empty.json.return_value = {"results": []}
    mock_resp_empty.raise_for_status = MagicMock()

    mock_client.post.return_value = mock_resp_empty
    with patch.object(client, "_client", return_value=mock_client):
        empty = await client.find_project_activity("db", "proj", "2026-10-11")
        assert empty is None


@pytest.mark.asyncio
async def test_find_project_activity_http_error():
    client = NotionAsyncClient(api_key="ntn_mock_12345")
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server Error", request=MagicMock(), response=mock_resp
    )

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch.object(client, "_client", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            await client.find_project_activity("db", "proj", "2026-10-11")


@pytest.mark.asyncio
async def test_find_project_activity_no_logging(caplog):
    ident_value = "mock_notion_key"
    client = NotionAsyncClient(api_key=ident_value)
    response_body_text = "body_containing_private_project_details_abc"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"results": [{"id": "act_1", "text": response_body_text}]}
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with caplog.at_level("DEBUG"):
        with patch.object(client, "_client", return_value=mock_client):
            await client.find_project_activity("db", "proj", "2026-10-11")

    assert ident_value not in caplog.text
    assert response_body_text not in caplog.text


def test_notion_required_scopes():
    from src.persona.current import current_persona

    assert hasattr(NotionAsyncClient, "required_scopes")
    assert NotionAsyncClient.required_scopes == ("notion.read", "notion.write")

    # required_scopes адаптера является подмножеством scopes привязки notion персоны по умолчанию
    persona = current_persona()
    notion_bindings = getattr(persona.connectors, "notion", [])
    if notion_bindings:
        assert set(NotionAsyncClient.required_scopes).issubset(set(notion_bindings[0].scopes))


def test_notion_client_satisfies_protocol():
    from src.core.ports.clients import NotionClientLike

    client = NotionAsyncClient(api_key="")
    assert isinstance(client, NotionClientLike)
    assert hasattr(NotionAsyncClient, "find_project_activity")
    assert hasattr(NotionAsyncClient, "log_project_activity")

