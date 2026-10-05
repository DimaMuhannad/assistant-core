"""Declarative schemas for Secretary tools using Google GenAI SDK.

Defines schemas for calendar events, reminders, email drafts, and email search,
along with the ActionProposal data structure for HITL confirmation.
"""

from dataclasses import dataclass, field
from typing import Any
from google.genai import types


@dataclass
class ActionProposal:
    """Structured proposal for an action requiring user confirmation (HITL)."""

    action_type: str
    params: dict[str, Any] = field(default_factory=dict)
    proposal_text: str = ""


tool_create_calendar_event = types.FunctionDeclaration(
    name="create_calendar_event",
    description="Запланировать событие в Google Calendar владельца. Требует точной даты и времени начала/окончания.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "title": types.Schema(type=types.Type.STRING, description="Название события или встречи"),
            "date": types.Schema(type=types.Type.STRING, description="Дата в формате YYYY-MM-DD"),
            "start_time": types.Schema(type=types.Type.STRING, description="Время начала в формате HH:MM"),
            "end_time": types.Schema(type=types.Type.STRING, description="Время окончания в формате HH:MM"),
            "description": types.Schema(type=types.Type.STRING, description="Подробное описание или контекст события"),
            "location": types.Schema(type=types.Type.STRING, description="Место проведения или аудитория"),
        },
        required=["title", "date", "start_time", "end_time"],
    ),
)

tool_create_reminder = types.FunctionDeclaration(
    name="create_reminder",
    description="Создать локальное напоминание или дедлайн в базе данных ассистента.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "text": types.Schema(type=types.Type.STRING, description="Суть напоминания или задачи"),
            "due_date": types.Schema(type=types.Type.STRING, description="Срок выполнения в формате YYYY-MM-DD или YYYY-MM-DD HH:MM"),
            "target": types.Schema(type=types.Type.STRING, description="Связанное лицо, адресат или студент (опционально)"),
            "category": types.Schema(type=types.Type.STRING, description="Категория задачи: academic, corporate, general"),
        },
        required=["text", "due_date"],
    ),
)

tool_draft_email_reply = types.FunctionDeclaration(
    name="draft_email_reply",
    description="Сформировать проект (черновик) ответа на входящее электронное письмо в почтовой базе.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "email_id": types.Schema(type=types.Type.INTEGER, description="Числовой ID входящего письма в SQLite"),
            "reply_text": types.Schema(type=types.Type.STRING, description="Текст проекта ответа"),
        },
        required=["email_id", "reply_text"],
    ),
)

tool_search_emails = types.FunctionDeclaration(
    name="search_emails",
    description="Найти письма в локальной базе по отправителю, ключевым словам или теме (первый шаг контекстного планирования).",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "query": types.Schema(type=types.Type.STRING, description="Поисковый запрос или ключевые слова"),
            "sender": types.Schema(type=types.Type.STRING, description="Имя или email отправителя (например, 'Новикова')"),
            "limit": types.Schema(type=types.Type.INTEGER, description="Максимальное число возвращаемых писем (по умолчанию 5)"),
        },
        required=["query"],
    ),
)

SECRETARY_TOOLS = [
    types.Tool(function_declarations=[
        tool_create_calendar_event,
        tool_create_reminder,
        tool_draft_email_reply,
        tool_search_emails,
    ])
]

__all__ = [
    "ActionProposal",
    "tool_create_calendar_event",
    "tool_create_reminder",
    "tool_draft_email_reply",
    "tool_search_emails",
    "SECRETARY_TOOLS",
]
