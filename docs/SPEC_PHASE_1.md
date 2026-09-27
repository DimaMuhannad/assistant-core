# SPEC_PHASE_1.md: Техническая спецификация Фазы 1

## 1. Назначение модуля
Автономный сервис для регулярного мониторинга расписания учебных занятий, выявления изменений на уровне отдельных слотов и синхронизации событий с Google Календарем без дублирования.

## 2. Модели данных (Pydantic v2)

```python
from datetime import datetime, date, time
from enum import Enum
from pydantic import BaseModel, Field
import hashlib

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
```

## 3. Критерии приемки (Definition of Done)
1. Пятикратный повторный запуск скрипта на неизменном расписании создает ровно 0 дубликатов в Google Календаре.
2. Сервис запускается в Docker-контейнере через `docker compose up -d`.
3. Ошибки сети или таймауты сайта логируются без падения демона.
