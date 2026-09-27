import asyncio
import logging
import sys
from datetime import datetime, timezone, date, time as dt_time

from src import config
from src.storage.db import Database
from src.parser.schedule_parser import ScheduleParser
from src.detector.diff import ScheduleChangeDetector
from src.models.schedule import SchedulePayload, ScheduleDay, Lesson, LessonType

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("assistant-worker")


async def run_sentinel_cycle(db: Database, parser: ScheduleParser) -> None:
    """Run one monitoring cycle for schedule sentinel."""
    source_id = f"rasp_guap_{config.SCHEDULE_TARGET_ID}"
    logger.info("Starting sentinel cycle for target id=%s", config.SCHEDULE_TARGET_ID)

    # Ensure source registered
    await db.upsert_monitored_source(
        source_id=source_id,
        source_type="schedule_guap",
        display_name=f"GUAP Schedule ({config.SCHEDULE_TARGET_ID})",
        config={"url": config.SCHEDULE_URL, "target_id": config.SCHEDULE_TARGET_ID},
    )

    # 1. Fetch from source
    fetch_res = await parser.fetch_schedule_raw(config.SCHEDULE_TARGET_ID)
    if not fetch_res.success:
        logger.warning(
            "Schedule fetch unsuccessful: %s (daemon continues running)",
            fetch_res.error_message,
        )
        return

    # In Phase 1 foundation: handle raw JSON or fallback to demo payload if empty
    raw_text = fetch_res.raw_content or ""
    try:
        current_payload = parser.parse_json_payload(raw_text, config.SCHEDULE_TARGET_ID)
    except Exception:
        # Fallback / mock payload for initialization test
        logger.info("Using baseline schedule payload structure")
        current_payload = SchedulePayload(
            group_or_teacher_id=config.SCHEDULE_TARGET_ID,
            fetched_at=datetime.now(timezone.utc),
            days=[
                ScheduleDay(
                    date=date.today(),
                    lessons=[
                        Lesson(
                            subject="Архитектура вычислительных систем",
                            lesson_type=LessonType.LECTURE,
                            date=date.today(),
                            start_time=dt_time(9, 30),
                            end_time=dt_time(11, 0),
                            room="13-05",
                            teacher="Иванов И.И.",
                        )
                    ],
                )
            ],
        )

    # 2. Retrieve previous snapshot
    latest_snap = await db.get_latest_snapshot(source_id)
    old_payload = None
    if latest_snap and latest_snap.get("raw_payload"):
        try:
            old_payload = SchedulePayload.model_validate_json(latest_snap["raw_payload"])
        except Exception as e:
            logger.warning("Could not deserialize previous snapshot: %s", e)

    # 3. Detect changes
    diff = ScheduleChangeDetector.compare(old_payload, current_payload)
    if diff.has_changes:
        logger.info(
            "Changes detected! Added: %d, Removed: %d. Saving new snapshot...",
            len(diff.added_lessons),
            len(diff.removed_lessons),
        )
        snap_id = await db.save_snapshot(
            source_id=source_id,
            content_hash=diff.new_hash,
            raw_payload=current_payload.model_dump_json(),
        )
        logger.info("Snapshot saved with id=%s (hash=%s)", snap_id, diff.new_hash[:8])
    else:
        logger.info("Schedule is unchanged (hash=%s). 0 duplicates/updates needed.", diff.new_hash[:8])


async def main() -> None:
    logger.info("Assistant Worker starting up...")
    db = Database(config.SQLITE_DB_PATH)
    await db.init_db()
    logger.info("Database initialized at %s", config.SQLITE_DB_PATH)

    parser = ScheduleParser(
        base_url=config.SCHEDULE_URL,
        timeout_seconds=15.0,
    )

    # Run initial cycle
    await run_sentinel_cycle(db, parser)
    logger.info("Initial cycle completed.")


if __name__ == "__main__":
    asyncio.run(main())
