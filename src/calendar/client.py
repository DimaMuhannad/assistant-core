import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from src.models.schedule import Lesson, ScheduleDiff
from src.storage.db import Database

logger = logging.getLogger(__name__)


class GoogleCalendarClient:
    """Manages synchronization between local schedule and Google Calendar."""

    def __init__(
        self,
        credentials_file: str = "./credentials.json",
        token_file: str = "./token.json",
        timezone_str: str = "Europe/Moscow",
        dry_run: bool = False,
    ):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.timezone_str = timezone_str
        self.dry_run = dry_run
        self.service = None
        self._init_service()

    def _init_service(self) -> None:
        """Initialize Google Calendar API service if valid tokens exist."""
        if self.dry_run:
            logger.info("GoogleCalendarClient running in DRY-RUN mode.")
            return

        token_path = Path(self.token_file)
        if not token_path.exists():
            logger.warning(
                "Google token file '%s' not found. Operating in MOCK / DRY-RUN mode until credentials are provided.",
                self.token_file,
            )
            self.dry_run = True
            return

        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            creds = Credentials.from_authorized_user_file(str(token_path))
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_path, "w") as token_out:
                    token_out.write(creds.to_json())

            self.service = build("calendar", "v3", credentials=creds)
            logger.info("Google Calendar service initialized successfully.")
        except Exception as e:
            logger.warning(
                "Failed to initialize Google Calendar API: %s. Falling back to DRY-RUN mode.",
                e,
            )
            self.dry_run = True

    async def create_event(self, calendar_id: str, lesson: Lesson) -> str:
        """Create an event in Google Calendar and return its ID."""
        summary = f"[{lesson.lesson_type.value}] {lesson.subject}"
        start_iso = f"{lesson.date.isoformat()}T{lesson.start_time.isoformat()}"
        end_iso = f"{lesson.date.isoformat()}T{lesson.end_time.isoformat()}"

        event_body = {
            "summary": summary,
            "location": lesson.room,
            "description": (
                f"Преподаватель: {lesson.teacher or 'Не указан'}\n"
                f"Группа: {lesson.group or 'Не указана'}\n"
                f"Хэш слота: {lesson.deterministic_hash}"
            ),
            "start": {
                "dateTime": start_iso,
                "timeZone": self.timezone_str,
            },
            "end": {
                "dateTime": end_iso,
                "timeZone": self.timezone_str,
            },
        }

        if self.dry_run or self.service is None:
            # Generate deterministic mock ID based on slot hash
            mock_id = f"mock_{lesson.deterministic_hash[:16]}"
            logger.info("[DRY-RUN] Created Google Calendar event '%s' (%s - %s) -> id: %s", summary, start_iso, end_iso, mock_id)
            return mock_id

        try:
            created = self.service.events().insert(calendarId=calendar_id, body=event_body).execute()
            google_id = created.get("id")
            logger.info("Created Google Calendar event '%s' -> %s", summary, google_id)
            return google_id
        except Exception as e:
            logger.error("Failed to create Google Calendar event '%s': %s", summary, e)
            raise

    async def delete_event(self, calendar_id: str, google_event_id: str) -> bool:
        """Delete an event from Google Calendar."""
        if self.dry_run or self.service is None:
            logger.info("[DRY-RUN] Deleted Google Calendar event %s", google_event_id)
            return True

        try:
            self.service.events().delete(calendarId=calendar_id, eventId=google_event_id).execute()
            logger.info("Deleted Google Calendar event %s", google_event_id)
            return True
        except Exception as e:
            logger.error("Failed to delete Google Calendar event %s: %s", google_event_id, e)
            return False

    async def sync_schedule(
        self,
        calendar_id: str,
        diff: ScheduleDiff,
        db: Database,
    ) -> dict[str, int]:
        """Synchronize schedule diff with Google Calendar idempotently.
        
        Guarantees 0 duplicate entries upon repeated runs.
        """
        stats = {"created": 0, "cancelled": 0, "skipped": 0}

        # 1. Process added lessons
        for lesson in diff.added_lessons:
            slot_id = lesson.deterministic_hash
            existing_record = await db.get_calendar_sync_record(slot_id)

            if existing_record and existing_record["status"] == "active":
                logger.debug("Event %s already synced as %s. Skipping (idempotency).", slot_id[:8], existing_record["google_event_id"])
                stats["skipped"] += 1
                continue

            # Create event in Google Calendar
            google_id = await self.create_event(calendar_id, lesson)
            start_dt = datetime.combine(lesson.date, lesson.start_time)
            end_dt = datetime.combine(lesson.date, lesson.end_time)

            await db.record_calendar_sync(
                source_event_id=slot_id,
                google_event_id=google_id,
                calendar_id=calendar_id,
                event_start=start_dt,
                event_end=end_dt,
                summary=f"[{lesson.lesson_type.value}] {lesson.subject}",
                status="active",
            )
            stats["created"] += 1

        # 2. Process removed lessons
        for lesson in diff.removed_lessons:
            slot_id = lesson.deterministic_hash
            existing_record = await db.get_calendar_sync_record(slot_id)

            if existing_record and existing_record["status"] == "active":
                await self.delete_event(calendar_id, existing_record["google_event_id"])
                start_dt = datetime.combine(lesson.date, lesson.start_time)
                end_dt = datetime.combine(lesson.date, lesson.end_time)

                await db.record_calendar_sync(
                    source_event_id=slot_id,
                    google_event_id=existing_record["google_event_id"],
                    calendar_id=calendar_id,
                    event_start=start_dt,
                    event_end=end_dt,
                    summary=existing_record["summary"],
                    status="cancelled",
                )
                stats["cancelled"] += 1

        logger.info(
            "Calendar sync finished: +%d created, -%d cancelled, %d skipped.",
            stats["created"],
            stats["cancelled"],
            stats["skipped"],
        )
        return stats
