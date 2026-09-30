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


class LessonModification(BaseModel):
    old_lesson: Lesson
    new_lesson: Lesson
    change_type: str = "room_changed"
    detail: str = ""


class ScheduleDiff(BaseModel):
    has_changes: bool
    old_hash: str | None = None
    new_hash: str
    added_lessons: list[Lesson] = Field(default_factory=list)
    removed_lessons: list[Lesson] = Field(default_factory=list)
    modified_lessons: list[LessonModification] = Field(default_factory=list)
    unchanged_count: int = 0


GUAP_BELL_SCHEDULE: dict[str, int] = {
    "09:30": 1,
    "11:10": 2,
    "13:00": 3,
    "15:10": 4,
    "17:00": 5,
    "18:40": 6,
    "20:20": 7,
}

LESSON_TYPE_SHORT: dict[LessonType, str] = {
    LessonType.LECTURE: "Лек",
    LessonType.LAB: "Лаб",
    LessonType.PRACTICE: "Пр",
    LessonType.EXAM: "Экз",
    LessonType.UNKNOWN: "Пара",
}

SUBJECT_SHORT_NAMES: dict[str, str] = {
    "физические основы нанотехнологий": "ФОНТ",
    "основы проектной деятельности в профессии": "ОПДвП",
    "основы проектной деятельности": "ОПД",
    "физика": "Физика",
}


def get_guap_pair_number(start_time: time | str) -> int | None:
    """Returns official SUAI/GUAP pair number (1..7) based on start bell time."""
    time_str = start_time.strftime("%H:%M") if isinstance(start_time, time) else str(start_time)[:5]
    if time_str in GUAP_BELL_SCHEDULE:
        return GUAP_BELL_SCHEDULE[time_str]
    try:
        parts = [int(p) for p in time_str.split(":")]
        total_mins = parts[0] * 60 + parts[1]
        for bell_str, pair_num in GUAP_BELL_SCHEDULE.items():
            b_parts = [int(p) for p in bell_str.split(":")]
            b_mins = b_parts[0] * 60 + b_parts[1]
            if abs(total_mins - b_mins) <= 15:
                return pair_num
    except Exception:
        pass
    return None


def format_academic_lesson_line(lesson: Lesson) -> str:
    """Formats single lesson matching Dmitry's required concise format:
    e.g. '2) 11:10 • [Лаб] Физика (гр. 1632, ауд. 31-04б)'
    """
    pair_num = get_guap_pair_number(lesson.start_time)
    short_type = LESSON_TYPE_SHORT.get(lesson.lesson_type, "Пара")

    subj_clean = lesson.subject.strip()
    short_subj = SUBJECT_SHORT_NAMES.get(subj_clean.lower(), subj_clean)

    start_str = lesson.start_time.strftime("%H:%M")

    meta_parts = []
    if lesson.group:
        meta_parts.append(f"гр. {lesson.group}")
    if lesson.room and lesson.room not in ("Не указана", "—", ""):
        clean_room = lesson.room.replace(" (Гастелло 15)", "").strip()
        if clean_room.lower().startswith("ауд."):
            clean_room = clean_room[4:].strip()
        elif clean_room.lower().startswith("ауд"):
            clean_room = clean_room[3:].strip()
        meta_parts.append(f"ауд. {clean_room}")

    meta_str = f" ({', '.join(meta_parts)})" if meta_parts else ""
    num_prefix = f"{pair_num})" if pair_num else "•"

    return f"{num_prefix} {start_str} • [{short_type}] {short_subj}{meta_str}"


