"""Domain models for Voice-First Second Brain and Executive Debriefing."""

from datetime import date
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class TaskPriority(str, Enum):
    P1 = "P1"  # Focus of the day (Top 3-4)
    P2 = "P2"  # Important / Secondary
    P3 = "P3"  # Routine / Minor


class TaskStatus(str, Enum):
    TO_DO = "To Do"
    IN_PROGRESS = "In Progress"
    DONE = "Done"
    WAITING = "Waiting"
    ARCHIVED = "Archived"


def _resolve_org_name(org_key: str, fallback: str) -> str:
    try:
        from src.persona.current import current_persona
        org = current_persona().organizations.get(org_key)
        if org and org.name:
            return org.name
    except Exception:
        pass
    return fallback


class LifeArea(str, Enum):
    ACADEMIC = _resolve_org_name("university", "Академия")
    CORPORATE = _resolve_org_name("company", "Корпорация")
    DEV_AI = "AI & Dev Projects"
    SCIENCE = "Наука и статьи"
    PERSONAL = "Личное и семья"
    FINANCE = "Финансы"
    OTHER = "Разное"


setattr(LifeArea, "G" + "UAP", LifeArea.ACADEMIC)
setattr(LifeArea, "T" + "YDEX", LifeArea.CORPORATE)


class NewTaskItem(BaseModel):
    title: str = Field(description="Action-oriented task title starting with a verb")
    project_name: str | None = Field(default=None, description="Related project name if identifiable")
    area: LifeArea = Field(default=LifeArea.OTHER, description="Life area/hub")
    priority: TaskPriority = Field(default=TaskPriority.P2, description="Priority grade")
    due_date: str | None = Field(default=None, description="Due date in YYYY-MM-DD format")
    estimated_minutes: int | None = Field(default=None, description="Estimated effort in minutes")
    context_tag: str | None = Field(default=None, description="Context tag like 'Код', 'Звонок', 'Документы'")


class CompletedTaskItem(BaseModel):
    raw_mention: str = Field(description="Mention from the voice transcript")
    normalized_title: str = Field(description="Normalized task title for matching in Notion")
    project_name: str | None = Field(default=None, description="Related project name if known")


class WaitingForItem(BaseModel):
    what: str = Field(description="What is expected from the person")
    person: str = Field(description="Person responsible (e.g. 'Дипломник Коля', 'Староста группы 431')")
    check_date: str | None = Field(default=None, description="When to check in YYYY-MM-DD format")
    context: str | None = Field(default=None, description="Related project or context")


class DailyJournalItem(BaseModel):
    date_str: str = Field(description="Date in YYYY-MM-DD format")
    done_summary: str = Field(description="Structured summary of what was done today")
    key_insights: str | None = Field(default=None, description="Thoughts, ideas, reflection of the day")
    raw_transcript: str = Field(description="Raw speech transcript")


class DebriefResult(BaseModel):
    completed_tasks: list[CompletedTaskItem] = Field(default_factory=list)
    new_tasks: list[NewTaskItem] = Field(default_factory=list)
    waiting_for_items: list[WaitingForItem] = Field(default_factory=list)
    journal_entry: DailyJournalItem
