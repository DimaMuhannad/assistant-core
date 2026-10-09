"""Tests for DebriefParser and Second Brain models."""

from datetime import date
import pytest
from src.brain.debrief_parser import DebriefParser
from src.models.second_brain import (
    DebriefResult,
    LifeArea,
    NewTaskItem,
    TaskPriority,
)


@pytest.mark.asyncio
async def test_debrief_parser_fallback_flow():
    parser = DebriefParser(api_key="AIzaSyYour_Mock")
    assert not parser.is_configured

    sample_transcript = (
        "Сегодня провел лабы у 3 кафедры ГУАП и доделал парсер для бота. "
        "Завтра нужно срочно заехать в отдел кадров подписать приказ. "
        "Дипломник Смирнов обещал прислать введение к пятнице."
    )

    result = await parser.parse_debrief(sample_transcript, target_date=date(2026, 9, 28))

    assert isinstance(result, DebriefResult)
    assert len(result.completed_tasks) >= 1
    assert any("лабы" in c.raw_mention.lower() or "парсер" in c.raw_mention.lower() for c in result.completed_tasks)

    assert len(result.new_tasks) >= 1
    new_task = result.new_tasks[0]
    assert "приказ" in new_task.title.lower() or "отдел кадров" in new_task.title.lower()
    assert new_task.due_date == "2026-09-29"

    assert len(result.waiting_for_items) >= 1
    waiting = result.waiting_for_items[0]
    assert "обещал" in waiting.what.lower() or "введение" in waiting.what.lower()

    # Format report
    report = parser.format_telegram_report(result)
    assert "🎙️ **Вечерний дебрифинг" in report
    assert "Завершено за день" in report
    assert "Поставлено задач на завтра" in report
    assert "Взято на контроль" in report


@pytest.mark.asyncio
async def test_debrief_parser_empty_text():
    parser = DebriefParser(api_key="AIzaSyYour_Mock")
    result = await parser.parse_debrief("", target_date=date(2026, 9, 28))

    assert len(result.completed_tasks) == 0
    assert len(result.new_tasks) == 0
    assert len(result.waiting_for_items) == 0
    assert "Нет записей" in result.journal_entry.done_summary
