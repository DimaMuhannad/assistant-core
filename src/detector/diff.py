import logging
from src.models.schedule import Lesson, ScheduleDiff, SchedulePayload

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

        added = [
            lesson
            for h, lesson in new_lessons_map.items()
            if h not in old_lessons_map
        ]
        removed = [
            lesson
            for h, lesson in old_lessons_map.items()
            if h not in new_lessons_map
        ]
        unchanged_count = len(
            set(old_lessons_map.keys()) & set(new_lessons_map.keys())
        )

        logger.info(
            "Schedule diff detected: +%d added, -%d removed, %d unchanged (old=%s, new=%s)",
            len(added),
            len(removed),
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
            unchanged_count=unchanged_count,
        )
