import logging
from src.models.schedule import Lesson, LessonModification, ScheduleDiff, SchedulePayload

logger = logging.getLogger(__name__)


class ScheduleChangeDetector:
    """Detects and categorizes changes between two schedule versions."""

    @staticmethod
    def compare(
        old_payload: SchedulePayload | None,
        new_payload: SchedulePayload,
    ) -> ScheduleDiff:
        """Compare old and new schedule payloads and return a detailed diff."""
        new_hash = new_payload.payload_hash

        if old_payload is None:
            new_lessons = new_payload.get_all_lessons()
            return ScheduleDiff(
                has_changes=True,
                old_hash=None,
                new_hash=new_hash,
                added_lessons=new_lessons,
                removed_lessons=[],
                unchanged_count=0,
            )

        old_hash = old_payload.payload_hash

        if old_hash == new_hash:
            all_lessons = new_payload.get_all_lessons()
            return ScheduleDiff(
                has_changes=False,
                old_hash=old_hash,
                new_hash=new_hash,
                added_lessons=[],
                removed_lessons=[],
                unchanged_count=len(all_lessons),
            )

        old_lessons_map: dict[str, Lesson] = {
            lesson.deterministic_hash: lesson for lesson in old_payload.get_all_lessons()
        }
        new_lessons_map: dict[str, Lesson] = {
            lesson.deterministic_hash: lesson for lesson in new_payload.get_all_lessons()
        }

        # Identify modifications (e.g. room change, group change) for same date, start_time, and subject
        modified: list[LessonModification] = []
        unmatched_added: list[Lesson] = []
        unmatched_removed: dict[str, Lesson] = {
            h: lesson for h, lesson in old_lessons_map.items() if h not in new_lessons_map
        }

        for h_new, new_l in new_lessons_map.items():
            if h_new in old_lessons_map:
                continue

            # Find matching lesson in unmatched_removed with same date, start_time, and subject
            matched_old_hash = None
            for h_old, old_l in unmatched_removed.items():
                if (
                    old_l.date == new_l.date
                    and old_l.start_time == new_l.start_time
                    and old_l.subject.strip().lower() == new_l.subject.strip().lower()
                ):
                    matched_old_hash = h_old
                    break

            if matched_old_hash:
                old_l = unmatched_removed.pop(matched_old_hash)
                details = []
                change_type = "details_changed"
                if old_l.room != new_l.room:
                    details.append(f"Аудитория: {old_l.room} -> {new_l.room}")
                    change_type = "room_changed"
                if old_l.group != new_l.group:
                    details.append(f"Группа: {old_l.group} -> {new_l.group}")
                if old_l.teacher != new_l.teacher:
                    details.append(f"Преподаватель: {old_l.teacher} -> {new_l.teacher}")

                modified.append(
                    LessonModification(
                        old_lesson=old_l,
                        new_lesson=new_l,
                        change_type=change_type,
                        detail="; ".join(details) if details else "Изменение параметров занятия",
                    )
                )
            else:
                unmatched_added.append(new_l)

        added = unmatched_added
        removed = list(unmatched_removed.values())
        unchanged_count = len(
            set(old_lessons_map.keys()) & set(new_lessons_map.keys())
        )

        logger.info(
            "Schedule diff detected: +%d added, -%d removed, ~%d modified, %d unchanged (old=%s, new=%s)",
            len(added),
            len(removed),
            len(modified),
            unchanged_count,
            old_hash[:8],
            new_hash[:8],
        )

        return ScheduleDiff(
            has_changes=True,
            old_hash=old_hash,
            new_hash=new_hash,
            added_lessons=added,
            removed_lessons=removed,
            modified_lessons=modified,
            unchanged_count=unchanged_count,
        )
