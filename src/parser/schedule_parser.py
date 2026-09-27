import json
import logging
import time
from datetime import datetime, timezone, date, time as dt_time
from typing import Any
import httpx
from pydantic import BaseModel, Field

from src.models.schedule import Lesson, LessonType, ScheduleDay, SchedulePayload

logger = logging.getLogger(__name__)


class FetchResult(BaseModel):
    success: bool
    status_code: int | None = None
    raw_content: str | None = None
    error_message: str | None = None
    elapsed_ms: float = 0.0


class ScheduleParser:
    """HTTP parser for retrieving and parsing schedule data with network resilience."""

    def __init__(
        self,
        base_url: str = "https://rasp.guap.ru/",
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
        user_agent: str = "AssistantCore-ScheduleSentinel/1.0",
        proxy: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.user_agent = user_agent
        self.proxy = proxy

    def _get_client(self) -> httpx.AsyncClient:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.8",
        }
        kwargs: dict[str, Any] = {
            "headers": headers,
            "timeout": httpx.Timeout(self.timeout_seconds),
            "follow_redirects": True,
        }
        if self.proxy:
            kwargs["proxy"] = self.proxy
        return httpx.AsyncClient(**kwargs)

    async def fetch_schedule_raw(self, target_id: str, endpoint: str = "") -> FetchResult:
        """Fetch raw schedule payload with retry and timeout protection.
        
        Guarantees that network errors or timeouts will never crash the calling daemon.
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}" if endpoint else self.base_url
        params = {"id": target_id} if target_id else None

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            t_start = time.perf_counter()
            try:
                async with self._get_client() as client:
                    response = await client.get(url, params=params)
                    elapsed = (time.perf_counter() - t_start) * 1000

                    if response.is_success:
                        return FetchResult(
                            success=True,
                            status_code=response.status_code,
                            raw_content=response.text,
                            elapsed_ms=elapsed,
                        )
                    else:
                        logger.warning(
                            "HTTP %s fetching schedule for id=%s (attempt %d/%d)",
                            response.status_code,
                            target_id,
                            attempt,
                            self.max_retries,
                        )
                        last_error = f"HTTP status error: {response.status_code}"
            except httpx.TimeoutException as exc:
                elapsed = (time.perf_counter() - t_start) * 1000
                logger.warning(
                    "Timeout (%ss) fetching schedule for id=%s (attempt %d/%d): %s",
                    self.timeout_seconds,
                    target_id,
                    attempt,
                    self.max_retries,
                    exc,
                )
                last_error = f"Connection timeout: {exc}"
            except httpx.NetworkError as exc:
                elapsed = (time.perf_counter() - t_start) * 1000
                logger.warning(
                    "Network error fetching schedule for id=%s (attempt %d/%d): %s",
                    target_id,
                    attempt,
                    self.max_retries,
                    exc,
                )
                last_error = f"Network error: {exc}"
            except Exception as exc:
                elapsed = (time.perf_counter() - t_start) * 1000
                logger.error("Unexpected error fetching schedule: %s", exc, exc_info=True)
                last_error = f"Unexpected error: {exc}"

        return FetchResult(
            success=False,
            error_message=last_error,
            elapsed_ms=elapsed,
        )

    def parse_json_payload(self, raw_json: str, group_or_teacher_id: str) -> SchedulePayload:
        """Parse structured schedule JSON into normalized Pydantic SchedulePayload."""
        data = json.loads(raw_json)
        days: list[ScheduleDay] = []

        raw_days = data.get("days", [])
        for d in raw_days:
            parsed_date = date.fromisoformat(d["date"]) if isinstance(d["date"], str) else d["date"]
            lessons: list[Lesson] = []
            for l in d.get("lessons", []):
                start_t = dt_time.fromisoformat(l["start_time"]) if isinstance(l["start_time"], str) else l["start_time"]
                end_t = dt_time.fromisoformat(l["end_time"]) if isinstance(l["end_time"], str) else l["end_time"]
                lesson_type_str = l.get("lesson_type", "UNKNOWN").upper()
                try:
                    l_type = LessonType(lesson_type_str)
                except ValueError:
                    l_type = LessonType.UNKNOWN

                lessons.append(
                    Lesson(
                        subject=l["subject"],
                        lesson_type=l_type,
                        date=parsed_date,
                        start_time=start_t,
                        end_time=end_t,
                        room=l.get("room", "Не указана"),
                        teacher=l.get("teacher"),
                        building=l.get("building"),
                        group=l.get("group"),
                    )
                )
            days.append(ScheduleDay(date=parsed_date, lessons=lessons))

        return SchedulePayload(
            group_or_teacher_id=group_or_teacher_id,
            fetched_at=datetime.now(timezone.utc),
            days=days,
        )
