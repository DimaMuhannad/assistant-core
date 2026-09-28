"""Notion API property builders and database schema definitions."""

from typing import Any


def title_property(text: str) -> dict[str, Any]:
    return {"title": [{"text": {"content": text}}]}


def rich_text_property(text: str) -> dict[str, Any]:
    return {"rich_text": [{"text": {"content": text}}]}


def select_property(name: str) -> dict[str, Any]:
    return {"select": {"name": name}}


def status_property(name: str) -> dict[str, Any]:
    return {"status": {"name": name}}


def date_property(start_date: str) -> dict[str, Any]:
    return {"date": {"start": start_date}}


def number_property(value: int | float) -> dict[str, Any]:
    return {"number": value}


def relation_property(page_ids: list[str]) -> dict[str, Any]:
    return {"relation": [{"id": pid} for pid in page_ids]}


# Canonical database property names
class TaskProperties:
    TITLE = "Task"
    STATUS = "Status"
    PRIORITY = "Priority"
    AREA = "Area"
    DUE_DATE = "Due Date"
    PROJECT = "Project"
    ESTIMATED_MINUTES = "Estimated Minutes"


class ProjectProperties:
    NAME = "Name"
    AREA = "Area"
    STATUS = "Status"
    TARGET_DATE = "Target Date"
    KEY_RESULT = "Key Result"


class WaitingForProperties:
    WHAT = "What"
    PERSON = "Person"
    CHECK_DATE = "Check Date"
    STATUS = "Status"
    CONTEXT = "Context"


class JournalProperties:
    DATE = "Date"
    DONE_SUMMARY = "Done Summary"
    KEY_INSIGHTS = "Key Insights"
    RAW_TRANSCRIPT = "Raw Transcript"
