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
