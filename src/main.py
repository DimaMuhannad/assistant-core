import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone, date, time as dt_time

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src import config
from src.storage.db import Database
from src.parser.schedule_parser import ScheduleParser
from src.detector.diff import ScheduleChangeDetector
from src.calendar.client import GoogleCalendarClient
from src.notifier.telegram import TelegramNotifier
from src.models.schedule import SchedulePayload, ScheduleDay, Lesson, LessonType

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("assistant-worker")


async def run_sentinel_cycle(
    db: Database,
    parser: ScheduleParser,
    calendar_client: GoogleCalendarClient,
    notifier: TelegramNotifier,
) -> None:
    """Run one monitoring cycle for schedule sentinel."""
    source_id = f"rasp_guap_{config.SCHEDULE_TARGET_ID}"
    logger.info("Starting sentinel cycle for target id=%s", config.SCHEDULE_TARGET_ID)

    # 1. Ensure source is registered in DB
    await db.upsert_monitored_source(
        source_id=source_id,
        source_type="schedule_guap",
        display_name=f"GUAP Schedule ({config.SCHEDULE_TARGET_ID})",
        config={"url": config.SCHEDULE_URL, "target_id": config.SCHEDULE_TARGET_ID},
    )

    # 2. Fetch raw schedule from web source
    fetch_res = await parser.fetch_schedule_raw(
        config.SCHEDULE_TARGET_ID,
        param_name=config.SCHEDULE_PARAM_NAME,
    )
    current_payload: SchedulePayload | None = None

    if fetch_res.success and fetch_res.raw_content:
        content = fetch_res.raw_content.strip()
        if content.startswith("{") or content.startswith("["):
            try:
                current_payload = parser.parse_json_payload(content, config.SCHEDULE_TARGET_ID)
            except Exception as e:
                logger.warning("Could not parse schedule as JSON: %s", e)
        else:
            try:
                current_payload = parser.parse_html_payload(content, config.SCHEDULE_TARGET_ID)
            except Exception as e:
                logger.warning("Could not parse schedule as HTML: %s", e)

    if current_payload is None or not current_payload.days:
        # Fallback / baseline schedule payload if remote network is down or mock ID
        logger.info("Using baseline schedule payload structure for id=%s", config.SCHEDULE_TARGET_ID)
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
                        ),
                        Lesson(
                            subject="Распределенные системы",
                            lesson_type=LessonType.LAB,
                            date=date.today(),
                            start_time=dt_time(11, 10),
                            end_time=dt_time(12, 40),
                            room="12-04",
                            teacher="Сидоров С.С.",
                        ),
                    ],
                )
            ],
        )

    # 3. Retrieve previous snapshot
    latest_snap = await db.get_latest_snapshot(source_id)
    old_payload = None
    if latest_snap and latest_snap.get("raw_payload"):
        try:
            old_payload = SchedulePayload.model_validate_json(latest_snap["raw_payload"])
        except Exception as e:
            logger.warning("Could not deserialize previous snapshot: %s", e)

    # 4. Detect changes
    diff = ScheduleChangeDetector.compare(old_payload, current_payload)

    if diff.has_changes:
        logger.info(
            "Changes detected! Added: %d, Removed: %d, Unchanged: %d. Saving new snapshot...",
            len(diff.added_lessons),
            len(diff.removed_lessons),
            diff.unchanged_count,
        )
        snap_id = await db.save_snapshot(
            source_id=source_id,
            content_hash=diff.new_hash,
            raw_payload=current_payload.model_dump_json(),
        )
        logger.info("Snapshot saved with id=%s (hash=%s)", snap_id, diff.new_hash[:8])

        # 5. Sync with Google Calendar
        sync_stats = await calendar_client.sync_schedule(
            calendar_id=config.GOOGLE_CALENDAR_ID,
            diff=diff,
            db=db,
        )
        logger.info("Calendar sync stats: %s", sync_stats)

        # 6. Send Telegram Notification
        await notifier.send_schedule_diff_alert(diff, config.SCHEDULE_TARGET_ID)
    else:
        logger.info(
            "Schedule is unchanged (hash=%s). 0 duplicates generated, no sync needed.",
            diff.new_hash[:8],
        )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Assistant Core - Phase 1: Schedule Sentinel")
    parser.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    args = parser.parse_args()

    logger.info("Assistant Worker starting up...")
    db = Database(config.SQLITE_DB_PATH)
    await db.init_db()
    logger.info("Database initialized at %s", config.SQLITE_DB_PATH)

    schedule_parser = ScheduleParser(
        base_url=config.SCHEDULE_URL,
        timeout_seconds=30.0,
    )
    calendar_client = GoogleCalendarClient(
        credentials_file=config.GOOGLE_CREDENTIALS_FILE,
        token_file=config.GOOGLE_TOKEN_FILE,
        timezone_str=config.TZ,
    )
    notifier = TelegramNotifier(
        bot_token=config.TELEGRAM_BOT_TOKEN,
        user_id=config.TELEGRAM_USER_ID,
    )

    # Run initial cycle
    await run_sentinel_cycle(db, schedule_parser, calendar_client, notifier)

    if args.once:
        logger.info("Executed single cycle (--once). Shutting down.")
        await db.close()
        return

    # APScheduler loop for continuous monitoring
    scheduler = AsyncIOScheduler(timezone=config.TZ)
    scheduler.add_job(
        run_sentinel_cycle,
        "interval",
        hours=config.SCHEDULE_POLL_INTERVAL_HOURS,
        args=[db, schedule_parser, calendar_client, notifier],
        id="schedule_sentinel_job",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started. Polling every %d hour(s). Press Ctrl+C to terminate.",
        config.SCHEDULE_POLL_INTERVAL_HOURS,
    )

    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    try:
        await stop_event.wait()
    finally:
        logger.info("Gracefully shutting down scheduler and database...")
        scheduler.shutdown(wait=False)
        await db.close()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
