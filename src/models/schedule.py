from datetime import datetime, date, time
from enum import Enum
import hashlib
from pydantic import BaseModel, Field


class LessonType(str, Enum):
    LECTURE = "LECTURE"
    PRACTICE = "PRACTICE"
    LAB = "LAB"
    EXAM = "EXAM"
    UNKNOWN = "UNKNOWN"


class Lesson(BaseModel):
    subject: str = Field(..., description="Название предмета")
    lesson_type: LessonType = Field(default=LessonType.UNKNOWN)
    date: date
    start_time: time
    end_time: time
    room: str = Field(default="Не указана")
    teacher: str | None = None
    building: str | None = None
    group: str | None = None

    @property
    def deterministic_hash(self) -> str:
        raw_key = f"{self.date.isoformat()}_{self.start_time.isoformat()}_{self.subject}_{self.room}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @property
    def time_slot_key(self) -> str:
        """Key identifying date and time slot for change tracking (e.g. rescheduling / room changes)."""
        return f"{self.date.isoformat()}_{self.start_time.isoformat()}"


class ScheduleDay(BaseModel):
    date: date
    lessons: list[Lesson] = Field(default_factory=list)


class SchedulePayload(BaseModel):
    group_or_teacher_id: str
    fetched_at: datetime
    days: list[ScheduleDay]

    @property
    def payload_hash(self) -> str:
        all_hashes = "".join(sorted([l.deterministic_hash for d in self.days for l in d.lessons]))
        return hashlib.sha256(all_hashes.encode("utf-8")).hexdigest()

    def get_all_lessons(self) -> list[Lesson]:
        lessons: list[Lesson] = []
        for day in self.days:
            lessons.extend(day.lessons)
        return lessons


class ScheduleDiff(BaseModel):
    has_changes: bool
    old_hash: str | None = None
    new_hash: str
    added_lessons: list[Lesson] = Field(default_factory=list)
    removed_lessons: list[Lesson] = Field(default_factory=list)
    unchanged_count: int = 0
