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
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
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

    async def fetch_schedule_raw(self, target_id: str, endpoint: str = "", param_name: str = "pr") -> FetchResult:
        """Fetch raw schedule payload with retry and timeout protection.
        
        Guarantees that network errors or timeouts will never crash the calling daemon.
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}" if endpoint else self.base_url
        params = {param_name: target_id} if target_id else None

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

    def parse_html_payload(
        self,
        html_content: str,
        group_or_teacher_id: str,
        target_date: date | None = None,
    ) -> SchedulePayload:
        """Parse university schedule HTML page into SchedulePayload.
        
        Extracts day headers, time slots, subject names, room numbers, and teachers.
        """
        from bs4 import BeautifulSoup
        import re
        from datetime import timedelta

        soup = BeautifulSoup(html_content, "html.parser")
        days_map = {
            "Понедельник": 0,
            "Вторник": 1,
            "Среда": 2,
            "Четверг": 3,
            "Пятница": 4,
            "Суббота": 5,
            "Воскресенье": 6,
        }
        time_slots = {
            "1 пара": (dt_time(9, 30), dt_time(11, 0)),
            "2 пара": (dt_time(11, 10), dt_time(12, 40)),
            "3 пара": (dt_time(13, 0), dt_time(14, 30)),
            "4 пара": (dt_time(15, 10), dt_time(16, 40)),
            "5 пара": (dt_time(17, 0), dt_time(18, 30)),
            "6 пара": (dt_time(18, 40), dt_time(20, 10)),
        }

        base_date = target_date or date.today()
        # Monday of this week
        monday = base_date - timedelta(days=base_date.weekday())

        # Determine current week type from page header (▲ UPPER / ▼ LOWER)
        current_week_type = "UNKNOWN"
        for d in soup.find_all("div"):
            txt = d.get_text(" ", strip=True)
            if "учебного года" in txt or "неделя" in txt:
                if "▲" in txt or "верхняя" in txt.lower():
                    current_week_type = "UPPER"
                    break
                elif "▼" in txt or "нижняя" in txt.lower():
                    current_week_type = "LOWER"
                    break

        days_dict: dict[date, list[Lesson]] = {}
        current_day_date = None
        current_slot_times = None

        time_pattern = re.compile(r"(\d{1,2}:\d{2})\s*[-–—]\s*(\d{1,2}:\d{2})")

        for elem in soup.find_all(["h4", "h3", "div"]):
            classes = elem.get("class", [])
            text = elem.get_text(" ", strip=True)

            if elem.name in ["h4", "h3"]:
                day_name = text.strip()
                if day_name in days_map:
                    day_offset = days_map[day_name]
                    current_day_date = monday + timedelta(days=day_offset)
                    if current_day_date not in days_dict:
                        days_dict[current_day_date] = []
                    current_slot_times = None
                continue

            if current_day_date and "text-danger" in classes and "пара (" in text:
                time_match = time_pattern.search(text)
                if time_match:
                    sh, sm = map(int, time_match.group(1).split(":"))
                    eh, em = map(int, time_match.group(2).split(":"))
                    current_slot_times = (dt_time(sh, sm), dt_time(eh, em))
                else:
                    for slot_name, slot_range in time_slots.items():
                        if slot_name in text:
                            current_slot_times = slot_range
                            break
                continue

            if current_day_date and current_slot_times and "d-flex" in classes and "gap-2" in classes:
                if any(clearing in text for clearing in ["Очистить", "Показать расписание"]):
                    continue

                if current_week_type == "UPPER" and "▼" in text:
                    continue
                if current_week_type == "LOWER" and "▲" in text:
                    continue

                l_type = LessonType.UNKNOWN
                if "Лекция" in text:
                    l_type = LessonType.LECTURE
                elif "Лабораторное занятие" in text:
                    l_type = LessonType.LAB
                elif "Практическое занятие" in text:
                    l_type = LessonType.PRACTICE
                elif "Экзамен" in text:
                    l_type = LessonType.EXAM

                room_match = re.search(r"ауд\.\s*([^—\n\r]+)", text)
                room = ("ауд. " + room_match.group(1).replace("\xa0", " ").strip()) if room_match else "Не указана"
                room = re.sub(r"\s+", " ", room)

                subject = text
                for prefix in ["▲", "▼", "Лекция", "Лабораторное занятие", "Практическое занятие"]:
                    subject = subject.replace(prefix, "")
                if room_match:
                    subject = subject.split("ауд.")[0]
                subject = subject.replace("\xa0", " ").strip(" .–—") or "Учебное занятие"
                subject = re.sub(r"\s+", " ", subject)

                teacher_match = re.search(r"преп:\s*([^.]+)", text)
                teacher = teacher_match.group(1).replace("\xa0", " ").strip() if teacher_match else None
                if teacher:
                    teacher = re.sub(r"\s+", " ", teacher)

                group_match = re.search(r"гр:\s*([^\r\n—]+)", text)
                group = group_match.group(1).replace("\xa0", " ").strip() if group_match else None
                if group:
                    group = re.sub(r"\s+", " ", group)

                days_dict[current_day_date].append(
                    Lesson(
                        subject=subject,
                        lesson_type=l_type,
                        date=current_day_date,
                        start_time=current_slot_times[0],
                        end_time=current_slot_times[1],
                        room=room,
                        teacher=teacher,
                        group=group,
                    )
                )

        days: list[ScheduleDay] = [
            ScheduleDay(date=d, lessons=lessons)
            for d, lessons in sorted(days_dict.items(), key=lambda x: x[0])
            if lessons
        ]

        # Generic fallback if custom structure yielded 0 lessons
        if not days:
            # Fallback to general table/div search
            current_day_date = base_date
            current_lessons = []
            for item in soup.find_all(["tr", "div", "li"], class_=re.compile(r"lesson|item|row|study", re.IGNORECASE)):
                text = item.get_text(separator=" ", strip=True)
                time_match = time_pattern.search(text)
                if not time_match:
                    continue
                start_str, end_str = time_match.groups()
                try:
                    sh, sm = map(int, start_str.split(":"))
                    eh, em = map(int, end_str.split(":"))
                    start_t = dt_time(sh, sm)
                    end_t = dt_time(eh, em)
                except Exception:
                    continue

                l_type = LessonType.UNKNOWN
                upper_text = text.upper()
                if any(k in upper_text for k in ["(ЛР)", " ЛР ", "ЛАБ"]):
                    l_type = LessonType.LAB
                elif any(k in upper_text for k in ["(ПР)", " ПР ", "ПРАКТ"]):
                    l_type = LessonType.PRACTICE
                elif any(k in upper_text for k in ["(Л)", " Л ", "ЛЕКЦ"]):
                    l_type = LessonType.LECTURE

                room_match = re.search(r"(?:ауд\.?|комн\.?|каб\.?|корп\.?)\s*([0-9A-Za-zА-Яа-я\-]+)", text, re.IGNORECASE)
                room = room_match.group(0) if room_match else "Не указана"
                subject = time_pattern.sub("", text)
                if room_match:
                    subject = subject.replace(room_match.group(0), "")
                subject = subject.strip(" -–—,.")[:100] or "Учебное занятие"

                current_lessons.append(
                    Lesson(
                        subject=subject,
                        lesson_type=l_type,
                        date=current_day_date,
                        start_time=start_t,
                        end_time=end_t,
                        room=room,
                    )
                )
            if current_lessons:
                days.append(ScheduleDay(date=current_day_date, lessons=current_lessons))

        return SchedulePayload(
            group_or_teacher_id=group_or_teacher_id,
            fetched_at=datetime.now(timezone.utc),
            days=days,
        )

