from datetime import date, time
import pytest
from src.brain.summarizer import GeminiSummarizer
from src.models.schedule import Lesson, LessonType


def test_summarizer_initialization_offline() -> None:
    summarizer = GeminiSummarizer(api_key="")
    assert not summarizer.is_configured


@pytest.mark.asyncio
async def test_summarizer_fallback_brief_generation() -> None:
    summarizer = GeminiSummarizer(api_key="")
    today = date(2026, 9, 28)
    lessons = [
        Lesson(
            subject="Физические основы нанотехнологий",
            lesson_type=LessonType.LECTURE,
            date=today,
            start_time=time(9, 30),
            end_time=time(11, 0),
            room="ауд. 13-05",
        )
    ]
    action_items = [
        {
            "priority_score": 3,
            "summary_text": "[SCHEDULE_CHANGE] Завтра занятие в аудитории там и обсудим переносы",
        },
        {
            "priority_score": 2,
            "summary_text": "[ACADEMIC_TASK] Домашнее задание к 03.10",
        },
    ]

    brief = await summarizer.generate_morning_brief(today, lessons, action_items)
    assert "Утренний дайджест" in brief
    assert "Физические основы нанотехнологий" in brief
    assert "13-05" in brief
    assert "Срочное" in brief
    assert "Завтра занятие в аудитории" in brief
