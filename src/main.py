import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone, date, time as dt_time
from zoneinfo import ZoneInfo
from pathlib import Path

# Ensure project root is first in sys.path and remove script directory to avoid shadowing stdlib 'calendar'
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if sys.path and sys.path[0] == _SCRIPT_DIR:
    sys.path.pop(0)
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from apscheduler.schedulers.asyncio import AsyncIOScheduler


from src import config
from src.storage.db import Database
from src.parser.schedule_parser import ScheduleParser
from src.detector.diff import ScheduleChangeDetector
from src.calendar.client import GoogleCalendarClient
from src.notifier.telegram import TelegramNotifier
from src.collector.tg_collector import TelegramCollector
from src.collector.email_collector import EmailCollector
from src.brain.summarizer import GeminiSummarizer
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

    if current_payload is None:
        logger.warning(
            "Schedule fetch/parse was unsuccessful for id=%s (status=%s, error=%s). Skipping cycle to preserve current calendar.",
            config.SCHEDULE_TARGET_ID,
            fetch_res.status_code,
            fetch_res.error_message,
        )
        return


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


async def run_telegram_collector_cycle(
    db: Database,
    collector: TelegramCollector,
    notifier: TelegramNotifier,
) -> None:
    """Run one ingestion cycle for monitored Telegram channels/chats."""
    try:
        if not await collector.is_authorized():
            logger.warning("Telegram Userbot is not authorized. Skipping Telegram collection cycle.")
            return

        sources = await db.list_monitored_sources()
        tg_sources = [s for s in sources if str(s.get("source_type", "")).startswith("telegram_")]
        if not tg_sources:
            logger.info("No Telegram sources registered for monitoring.")
            return

        logger.info("Starting Telegram collection cycle for %d sources...", len(tg_sources))
        all_urgent_items = []

        for src in tg_sources:
            peer_str = str(src["id"]).removeprefix("tg_")
            try:
                peer: int | str = int(peer_str)
            except ValueError:
                peer = peer_str

            logger.info("Syncing Telegram source: %s (%s)", src.get("display_name"), peer)
            res = await collector.sync_chat(peer=peer, limit=30)
            if res.get("action_items"):
                urgent = [it for it in res["action_items"] if it.get("priority", 1) >= 3]
                all_urgent_items.extend(urgent)

        if all_urgent_items:
            logger.info("Found %d urgent action item(s). Sending Telegram notification...", len(all_urgent_items))
            await notifier.send_action_items_alert(all_urgent_items)
    except Exception as e:
        logger.exception("Error during Telegram collection cycle: %s", e)


async def run_email_collector_cycle(
    db: Database,
    email_collector: EmailCollector,
    notifier: TelegramNotifier,
) -> None:
    """Run periodic email collection cycle (incremental, last 3 days)."""
    try:
        logger.info("Starting email collection cycle...")
        res = await email_collector.sync_all_accounts(days=3)
        total_new = sum(r.get("inserted", 0) for k, r in res.items() if isinstance(r, dict))
        logger.info("Email collection finished: %d new email(s) ingested.", total_new)

        # Notify if new student or department emails arrive
        if total_new > 0:
            student_or_dept = await db.list_recent_emails(limit=total_new, non_noise_only=True)
            academic_items = [
                e for e in student_or_dept
                if e.get("category") in ("guap_student", "guap_dept")
                and e.get("requires_action")
                and not e.get("is_answered")
                and not e.get("is_expired")
            ]
            for email_item in academic_items:
                sender = email_item.get("sender_email", "")
                subject = email_item.get("subject", "Без темы")
                cat_label = "Студент" if email_item.get("category") == "guap_student" else "Кафедра/ГУАП"
                snippet = email_item.get("snippet", "")[:150]
                msg_text = (
                    f"📬 *Новое письмо ({cat_label})*\n"
                    f"👤 *От:* `{sender}`\n"
                    f"📌 *Тема:* {subject}\n"
                    f"💬 _{snippet}..."
                )
                await notifier.send_message(msg_text)
    except Exception as e:
        logger.exception("Error during email collection cycle: %s", e)


async def run_morning_brief_cycle(
    db: Database,
    schedule_parser: ScheduleParser,
    summarizer: GeminiSummarizer,
    notifier: TelegramNotifier,
    force: bool = False,
) -> None:
    """Run morning executive brief cycle (daily at 08:00 MSK or triggered on startup)."""
    try:
        now_local = datetime.now(ZoneInfo(config.TZ))
        today = now_local.date()

        if not force:
            latest_brief = await db.get_latest_snapshot("daily_morning_brief")
            if latest_brief and latest_brief.get("captured_at"):
                brief_date_str = str(latest_brief["captured_at"])[:10]
                if brief_date_str == today.isoformat():
                    logger.info("Morning brief for %s was already sent today. Skipping.", today)
                    return

        logger.info("Starting morning executive brief cycle for %s...", today)

        # 1. Lessons for today & upcoming
        today_lessons: list[Lesson] = []
        upcoming_lessons: list[tuple[date, Lesson]] = []
        snap = await db.get_latest_snapshot(f"rasp_guap_{config.SCHEDULE_TARGET_ID}")
        if snap and snap.get("raw_payload"):
            try:
                payload = SchedulePayload.model_validate_json(snap["raw_payload"])
                for day in payload.days:
                    if day.date == today:
                        today_lessons = day.lessons
                    elif day.date > today and not upcoming_lessons:
                        upcoming_lessons = [(day.date, l) for l in day.lessons]
            except Exception as se:
                logger.warning("Failed to parse schedule payload for brief: %s", se)

        # 2. Actionable emails (unanswered student/dept letters)
        actionable_emails = await db.list_actionable_emails(limit=10)

        # 3. Action items from monitored Telegram chats
        action_items = await db.get_pending_action_items(limit=20)

        # 4. Generate brief via summarizer
        brief_markdown = await summarizer.generate_morning_brief(
            target_date=today,
            lessons=today_lessons,
            action_items=action_items,
            actionable_emails=actionable_emails,
            upcoming_lessons=upcoming_lessons,
        )

        # 5. Send via Telegram
        sent = await notifier.send_daily_brief(brief_markdown)
        if sent:
            await db.save_snapshot(
                source_id="daily_morning_brief",
                content_hash=today.isoformat(),
                raw_payload=brief_markdown,
            )
            logger.info("Morning brief for %s successfully sent to Telegram.", today)
    except Exception as e:
        logger.exception("Error during morning brief cycle: %s", e)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Assistant Core - Phase 1 & 2 Worker Daemon")
    parser.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    parser.add_argument("--brief", action="store_true", help="Force send morning brief and exit")
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
    telegram_collector = TelegramCollector(db=db)
    email_collector = EmailCollector(db=db)
    summarizer = GeminiSummarizer()

    # Track morning brief source in DB
    await db.upsert_monitored_source(
        source_id="daily_morning_brief",
        source_type="briefing",
        display_name="Daily Morning Brief",
        config={"hour": 8, "minute": 0},
    )

    if args.brief:
        logger.info("Force sending morning brief via --brief flag...")
        await run_morning_brief_cycle(db, schedule_parser, summarizer, notifier, force=True)
        await telegram_collector.disconnect()
        await db.close()
        return

    # Run initial cycles
    await run_sentinel_cycle(db, schedule_parser, calendar_client, notifier)
    await run_telegram_collector_cycle(db, telegram_collector, notifier)
    await run_email_collector_cycle(db, email_collector, notifier)

    # If current time is between 08:00 and 12:00 MSK and today's brief was not sent, send it now
    now_local = datetime.now(ZoneInfo(config.TZ))
    if 8 <= now_local.hour < 12:
        await run_morning_brief_cycle(db, schedule_parser, summarizer, notifier, force=False)

    if args.once:
        logger.info("Executed single cycle (--once). Shutting down.")
        await telegram_collector.disconnect()
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
    # Telegram userbot collector runs every 30 minutes
    scheduler.add_job(
        run_telegram_collector_cycle,
        "interval",
        minutes=30,
        args=[db, telegram_collector, notifier],
        id="telegram_collector_job",
        replace_existing=True,
    )
    # Email collector runs every 15 minutes
    scheduler.add_job(
        run_email_collector_cycle,
        "interval",
        minutes=15,
        args=[db, email_collector, notifier],
        id="email_collector_job",
        replace_existing=True,
    )
    # Morning brief runs daily at 08:00 MSK
    scheduler.add_job(
        run_morning_brief_cycle,
        "cron",
        hour=8,
        minute=0,
        args=[db, schedule_parser, summarizer, notifier],
        id="morning_brief_job",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started. Morning brief at 08:00, Schedule polling every %d hour(s), Telegram chats every 30 min, Email every 15 min. Press Ctrl+C to terminate.",
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
        logger.info("Gracefully shutting down scheduler, userbot and database...")
        scheduler.shutdown(wait=False)
        await telegram_collector.disconnect()
        await db.close()
        logger.info("Shutdown complete.")



if __name__ == "__main__":
    asyncio.run(main())
