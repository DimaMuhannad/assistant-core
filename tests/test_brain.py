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
    assert "1) 09:30 • [Лек] ФОНТ (ауд. 13-05)" in brief
    assert "13-05" in brief
    assert "Срочное" in brief
    assert "Завтра занятие в аудитории" in brief


def test_format_academic_lesson_line():
    from src.models.schedule import format_academic_lesson_line

    l1 = Lesson(
        subject="Физика",
        lesson_type=LessonType.LAB,
        date=date(2026, 9, 30),
        start_time=time(11, 10),
        end_time=time(12, 40),
        room="31-04б (Гастелло 15)",
        group="1632",
    )
    res = format_academic_lesson_line(l1)
    assert res == "2) 11:10 • [Лаб] Физика (гр. 1632, ауд. 31-04б)"

    l2 = Lesson(
        subject="Основы проектной деятельности",
        lesson_type=LessonType.PRACTICE,
        date=date(2026, 9, 30),
        start_time=time(13, 0),
        end_time=time(14, 30),
        room="ауд. 22-10",
        group="м531",
    )
    res2 = format_academic_lesson_line(l2)
    assert res2 == "3) 13:00 • [Пр] ОПД (гр. м531, ауд. 22-10)"


@pytest.mark.asyncio
async def test_morning_brief_with_timesheet_and_opd_messengers() -> None:
    summarizer = GeminiSummarizer(api_key="")
    today = date(2026, 9, 30)
    lessons = [
        Lesson(
            subject="Физика",
            lesson_type=LessonType.LAB,
            date=today,
            start_time=time(11, 10),
            end_time=time(12, 40),
            room="31-04б",
            group="1632",
        )
    ]
    action_items = [
        {
            "priority_score": 1,
            "source_type": "telegram_group",
            "summary_text": "[м631к Основы проектной деятельности] Вопрос по паспорту проекта",
        },
        {
            "priority_score": 3,
            "source_type": "guap_dept",
            "summary_text": "Сдать отчет по НИР до пятницы",
        },
    ]
    timesheet_pacing = {
        "morning_delta": 6.5,
        "latest_date_formatted": "29.09",
    }
    brief = await summarizer.generate_morning_brief(
        target_date=today,
        lessons=lessons,
        action_items=action_items,
        timesheet_pacing=timesheet_pacing,
    )
    assert "2) 11:10 • [Лаб] Физика (гр. 1632, ауд. 31-04б)" in brief
    assert "Дельта нормы на утро: `+6.5` ч (актуально на 29.09)" in brief
    assert "💬 **Мессенджеры (ОПД ГУАП):**" in brief
    assert "[м631к] Вопрос по паспорту проекта" in brief
    assert "🚨 **Срочное / Дедлайны:**" in brief
    assert "Сдать отчет по НИР до пятницы" in brief


@pytest.mark.asyncio
async def test_evening_digest_fallback_academic_and_opd() -> None:
    summarizer = GeminiSummarizer(api_key="")
    today = date(2026, 9, 30)
    tmr = date(2026, 10, 1)
    tomorrow_lessons = [
        Lesson(
            subject="Основы проектной деятельности",
            lesson_type=LessonType.PRACTICE,
            date=tmr,
            start_time=time(9, 30),
            end_time=time(11, 0),
            room="13-05",
            group="м631к",
        )
    ]
    action_items = [
        {
            "source_type": "telegram_group",
            "summary_text": "[м531 Основы проектной деятельности] Студенты прикрепили отчет к этапу 1",
        }
    ]
    email_stats = {"bot_answered": [], "pending_actionable": []}
    digest = await summarizer.generate_evening_digest(
        target_date=today,
        email_stats=email_stats,
        tomorrow_date=tmr,
        tomorrow_lessons=tomorrow_lessons,
        action_items=action_items,
    )
    assert "1) 09:30 • [Пр] ОПД (гр. м631к, ауд. 13-05)" in digest
    assert "💬 **Мессенджеры (ОПД ГУАП):**" in digest
    assert "[м531] Студенты прикрепили отчет к этапу 1" in digest
