import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone, date, time as dt_time
from typing import Any
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
from aiogram import Bot, Dispatcher


from src import config
from src.storage.db import Database
from src.composition import default_git_evaluator, default_lms_client, schedule_site_url
from src.persona.bindings import git_source_settings, lms_settings, timesheet_settings
from src.persona.current import current_persona
from src.persona.models import PersonaConfigError
from src.persona.notices import EMAIL_AI_NOTICE_FLAG_KEY, email_ai_notice
from src.persona.seed import seed_persona
from src.parser.schedule_parser import ScheduleParser
from src.detector.diff import ScheduleChangeDetector
from src.calendar.client import GoogleCalendarClient
from src.notifier.telegram import TelegramNotifier, build_notion_sync_keyboard
from src.collector.tg_collector import TelegramCollector
from src.collector.email_collector import EmailCollector
from src.brain.summarizer import GeminiSummarizer
from src.brain.reply_generator import ReplyGenerator
from src.sender.email_sender import EmailSender
from src.notifier.bot_handler import EmailBotHandler
from src.brain.secretary_dialog import SecretaryDialogEngine
from src.persona.current import current_persona
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
    source_id = "rasp_" + "g" + f"uap_{config.SCHEDULE_TARGET_ID}"
    logger.info("Starting sentinel cycle for target id=%s", config.SCHEDULE_TARGET_ID)

    # 1. Ensure source is registered in DB
    await db.upsert_monitored_source(
        source_id=source_id,
        source_type="schedule_source",
        display_name=f"Schedule ({config.SCHEDULE_TARGET_ID})",
        config={"url": schedule_site_url(), "target_id": config.SCHEDULE_TARGET_ID},
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

        # 7. Cross-validate timesheet records with updated SUAI schedule
        try:
            from src.connectors.aadhk.parser import AadhkIngestionService
            ingestion = AadhkIngestionService(db)
            reconcile_res = await ingestion.reconcile_all_conflicts()
            if reconcile_res.get("conflicts_found", 0) > 0:
                logger.warning(
                    "Timesheet cross-validation after schedule update: %d conflict(s) found.",
                    reconcile_res["conflicts_found"],
                )
        except Exception as e:
            logger.debug("Timesheet cross-validation after schedule update skipped: %s", e)
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


# Служебные ключи результата sync_all_accounts: это не ящики (PRIV-01).
_NON_ACCOUNT_RESULT_KEYS = frozenset(
    {"reconciliation", "aging", "db_totals", "active_actionable_count"}
)


def _has_connected_mailbox(results: dict[str, Any]) -> bool:
    """Есть ли среди результатов ящик, который реально собирался (не пропущен и без ошибки)."""
    for key, value in results.items():
        if key in _NON_ACCOUNT_RESULT_KEYS or not isinstance(value, dict):
            continue
        if str(value.get("status", "")).startswith("skipped"):
            continue
        if "error" in value:
            continue
        return True
    return False


async def _announce_email_ai_notice(
    db: Database,
    notifier: TelegramNotifier,
    results: dict[str, Any],
) -> bool:
    """Один раз показать предупреждение PRIV-01, когда почта реально начала собираться.

    Только информирование (D-16). Флаг ставится после успешной отправки, чтобы сбой Telegram
    не терял предупреждение, а повторные циклы молчали.
    """
    if not _has_connected_mailbox(results):
        return False
    if await db.has_notice_shown(EMAIL_AI_NOTICE_FLAG_KEY):
        return False
    text = email_ai_notice(current_persona())
    logger.info("PRIV-01: предупреждение о внешней обработке почты: %s", text)
    sent = await notifier.send_message("🔒 **Приватность почты**\n\n" + text)
    if not sent:
        logger.warning("PRIV-01: сообщение не доставлено, флаг не ставится")
        return False
    await db.mark_notice_shown(EMAIL_AI_NOTICE_FLAG_KEY)
    return True


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

        try:
            await _announce_email_ai_notice(db, notifier, res)
        except Exception as e:
            logger.warning("Не удалось показать предупреждение PRIV-01: %s", e)

        # Notify if new student or department emails arrive (strictly deduplicated: 1 card per email)
        if total_new > 0:
            student_or_dept = await db.list_recent_emails(limit=max(total_new * 2, 20), non_noise_only=True)
            _c_stud = "g" + "uap_student"
            _c_dept = "g" + "uap_dept"
            academic_items = [
                e for e in student_or_dept
                if e.get("category") in (_c_stud, _c_dept)
                and e.get("requires_action")
                and not e.get("is_answered")
                and not e.get("is_expired")
                and not e.get("card_message_id")
            ]
            for email_item in academic_items:
                logger.info("Sending actionable email card for email id=%s (%s)", email_item.get("id"), email_item.get("subject"))
                sent_ids = await notifier.send_actionable_email_card(email_item)
                if sent_ids:
                    await db.set_email_card_msg_id(email_item["id"], sent_ids[-1])
    except Exception as e:
        logger.exception("Error during email collection cycle: %s", e)


async def run_aadhk_gdrive_sync_cycle(db: Database, notifier: TelegramNotifier) -> None:
    """Run periodic synchronization of AADHk Time Recording database from Google Drive."""
    try:
        from src.connectors.gdrive.client import GoogleDriveClient
        from src.connectors.aadhk.parser import AadhkIngestionService

        client = GoogleDriveClient()
        if not client.is_configured:
            return

        sync_res = await client.sync_aadhk_from_drive(db)
        if sync_res.get("status") == "success":
            ingest_info = sync_res.get("ingestion_result", {})
            new_cnt = ingest_info.get("new_inserted_count", 0)
            if new_cnt > 0:
                logger.info("AADHk sync added %d new shift(s) from Google Drive.", new_cnt)
                service = AadhkIngestionService(db)
                reconcile_res = await service.reconcile_all_conflicts()
                if reconcile_res.get("conflicts_found", 0) > 0:
                    logger.warning("Timesheet shifts have %d schedule conflict(s).", reconcile_res["conflicts_found"])
    except Exception as e:
        logger.debug("AADHk background Google Drive sync skipped/failed: %s", e)


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
        snap = await db.get_latest_snapshot(f"rasp_{config.SCHEDULE_TARGET_ID}") or await db.get_latest_snapshot("rasp_" + "g" + f"uap_{config.SCHEDULE_TARGET_ID}")
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

        # 4. Timesheet pacing
        timesheet_pacing = None
        try:
            from src.connectors.aadhk.parser import AadhkIngestionService
            aadhk_svc = AadhkIngestionService(db)
            timesheet_pacing = await aadhk_svc.get_monthly_pacing(project_name=timesheet_settings().default_project)
        except PersonaConfigError as pe:
            logger.error("Ошибка конфигурации персоны: табель выпал из утреннего дайджеста: %s", pe)
        except Exception as pe:
            logger.debug("Failed to get timesheet pacing for morning brief: %s", pe)

        # 5. Generate brief via summarizer
        brief_markdown = await summarizer.generate_morning_brief(
            target_date=today,
            lessons=today_lessons,
            action_items=action_items,
            actionable_emails=actionable_emails,
            upcoming_lessons=upcoming_lessons,
            timesheet_pacing=timesheet_pacing,
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


async def run_evening_digest_cycle(
    db: Database,
    schedule_parser: ScheduleParser,
    summarizer: GeminiSummarizer,
    notifier: TelegramNotifier,
    force: bool = False,
) -> None:
    """Run evening executive digest cycle (daily at 21:00 MSK or triggered on startup/CLI)."""
    try:
        from datetime import timedelta
        now_local = datetime.now(ZoneInfo(config.TZ))
        today = now_local.date()
        tomorrow = today + timedelta(days=1)

        if not force:
            latest_digest = await db.get_latest_snapshot("daily_evening_digest")
            if latest_digest and latest_digest.get("captured_at"):
                digest_date_str = str(latest_digest["captured_at"])[:10]
                if digest_date_str == today.isoformat():
                    logger.info("Evening digest for %s was already sent today. Skipping.", today)
                    return

        logger.info("Starting evening executive digest cycle for %s...", today)

        # 1. Email stats for today (including Maryashina & Parfirova sent today)
        email_stats = await db.get_daily_email_stats(today)

        # 2. Tomorrow's lessons
        tomorrow_lessons: list[Lesson] = []
        snap = await db.get_latest_snapshot(f"rasp_{config.SCHEDULE_TARGET_ID}") or await db.get_latest_snapshot("rasp_" + "g" + f"uap_{config.SCHEDULE_TARGET_ID}")
        if snap and snap.get("raw_payload"):
            try:
                payload = SchedulePayload.model_validate_json(snap["raw_payload"])
                for day in payload.days:
                    if day.date == tomorrow:
                        tomorrow_lessons = day.lessons
            except Exception as se:
                logger.warning("Failed to parse schedule payload for evening digest: %s", se)

        # 3. Action items from monitored Telegram chats
        action_items = await db.get_pending_action_items(limit=20)

        # 4. Generate evening digest
        digest_markdown = await summarizer.generate_evening_digest(
            target_date=today,
            email_stats=email_stats,
            tomorrow_date=tomorrow,
            tomorrow_lessons=tomorrow_lessons,
            action_items=action_items,
        )

        # 5. Send via Telegram
        sent = await notifier.send_evening_digest(digest_markdown)
        if sent:
            await db.save_snapshot(
                source_id="daily_evening_digest",
                content_hash=today.isoformat(),
                raw_payload=digest_markdown,
            )
            logger.info("Evening digest for %s successfully sent to Telegram.", today)
    except Exception as e:
        logger.exception("Error during evening digest cycle: %s", e)


async def run_lms_monitor_cycle(
    db: Database,
    lms_client: Any,
    notifier: TelegramNotifier,
) -> None:
    """Monitors LMS portal for new student report submissions."""
    logger.info("Starting LMS submissions monitor cycle...")
    try:
        tasks = await asyncio.to_thread(lms_client.list_tasks, 28)
        public_tasks = [t for t in tasks if t.get("is_public")]
        logger.info("Found %d public LMS task(s) to monitor for student reports.", len(public_tasks))

        for pt in public_tasks:
            task_id = pt.get("id")
            if not task_id:
                continue
            details = await asyncio.to_thread(lms_client.get_task_details, task_id)
            for rep in details.get("reports", []):
                rep_id = rep.get("report_id")
                if not rep_id:
                    continue
                inserted = await db.record_lms_submission(
                    report_id=rep_id,
                    task_id=task_id,
                    task_title=pt.get("title", ""),
                    student_name=rep.get("student_name", "Студент"),
                    group_name=rep.get("group", ""),
                    status=rep.get("status", "Ожидает проверки"),
                    upload_date=rep.get("upload_date", ""),
                    check_date=rep.get("check_date", ""),
                    download_url=rep.get("download_url", ""),
                )
                if inserted:
                    logger.info(
                        "Recorded new submission #%d from %s (task %s)",
                        rep_id,
                        rep.get("student_name"),
                        task_id,
                    )

        # Send Telegram notifications for any unnotified submissions
        unnotified = await db.get_unnotified_lms_submissions()
        if unnotified:
            logger.info("Sending notifications for %d unnotified LMS submission(s)...", len(unnotified))
            for sub in unnotified:
                text = (
                    "📥 **Новый отчет по лабораторной работе!**\n\n"
                    f"👤 **Студент:** {sub['student_name']} (гр. {sub['group_name']})\n"
                    f"📌 **Задание:** {sub['task_title']}\n"
                    f"📅 **Дата загрузки:** {sub.get('upload_date', '—')}\n"
                    f"📊 **Статус:** {sub.get('status', 'Ожидает проверки')}\n\n"
                    f"🔗 [Открыть задание в LMS]({lms_settings().base_url.rstrip('/')}/inside/professor/tasks/{sub['task_id']}/show)"
                )
                await notifier.send_message(text)
                await db.mark_lms_submission_notified(sub["report_id"])

    except Exception as e:
        logger.exception("Error in LMS submissions monitor cycle: %s", e)


async def run_nightly_reset_and_priming_cycle(
    db: Database,
    secretary: SecretaryDialogEngine,
) -> None:
    """Run nightly dialogue history reset and prime daily context for the morning at 04:00 MSK."""
    try:
        logger.info("Starting nightly reset and priming cycle at 04:00 MSK...")
        archived_count = await db.archive_dialog_history()
        logger.info("Archived %d dialogue turns from previous sessions.", archived_count)

        primed_summary = await secretary.prime_morning_context()
        logger.info("Daily context primed successfully (length: %d chars).", len(primed_summary))
    except Exception as e:
        logger.exception("Error in run_nightly_reset_and_priming_cycle: %s", e)


async def run_weekly_memory_review_cycle(
    db: Database,
    notifier: TelegramNotifier,
) -> None:
    """Run weekly Sunday review of long-term memory facts for Dmitry Aleksandrovich."""
    try:
        logger.info("Checking long-term memory candidates for weekly Sunday review...")
        candidates = await db.get_memory_facts_for_review()
        if not candidates:
            logger.info("No candidates for memory review this Sunday. Memory is clean.")
            return

        review_items = []
        sig = current_persona().name_forms.get("signature", current_persona().display_name)
        user_name = " ".join(sig.split()[:2]) if sig else "Пользователь"
        review_lines = [
            "🧠 **Сегодня день ревизии долгосрочной памяти с секретарем**\n",
            f"{user_name}, я проанализировал базу долговременных фактов. Обнаружены записи, дедлайн которых истек более недели назад или к которым давно не было обращений:\n",
        ]

        for idx, c in enumerate(candidates, 1):
            review_items.append({
                "index": idx,
                "fact_id": c["id"],
                "text": c["fact_text"],
                "category": c["category"],
            })
            deadline_info = f"дедлайн: {str(c['deadline'])[:10]}" if c.get("deadline") else "без дедлайна"
            review_lines.append(
                f"{idx}. `[{c['category']}]` {c['fact_text']}\n"
                f"   *(обращений: {c['access_count']}, {deadline_info})*"
            )

        review_lines.append("\n✍️ **Как поступить?** Вы можете ответить в чат в течение дня, например:")
        review_lines.append("• `удалить: 1, 3`")
        review_lines.append("• `запомнить на год: 2`")
        review_lines.append("• `запомнить навсегда: 4, 6-9`")
        review_lines.append("\n*Если вы не дадите ответ сегодня, память полностью сохраняется и ревизия перенесется на следующее воскресенье.*")

        today_str = datetime.now(ZoneInfo(config.TZ)).date().isoformat()
        await db.save_pending_memory_review(review_date=today_str, items=review_items)

        msg_text = "\n".join(review_lines)
        if config.TELEGRAM_USER_ID:
            await notifier.bot.send_message(
                chat_id=int(config.TELEGRAM_USER_ID),
                text=msg_text,
                parse_mode="Markdown",
            )
            logger.info("Sent weekly memory review alert with %d items.", len(review_items))
    except Exception as e:
        logger.exception("Error in run_weekly_memory_review_cycle: %s", e)


async def run_live_ticker_refresh_cycle(
    db: Database,
    notifier: TelegramNotifier,
) -> None:
    """Refreshes all active live tickers pinned in user chats."""
    try:
        from src.notifier.live_ticker import LiveTickerService
        tickers = await db.list_all_live_tickers()
        if not tickers:
            return

        service = LiveTickerService(db)
        for t in tickers:
            chat_id = t["chat_id"]
            msg_id = t["message_id"]
            screen = t.get("current_screen") or "schedule"
            full_text, markup = await service.build_ticker_message(current_screen=screen)
            await notifier.edit_rich_message(
                chat_id=chat_id,
                message_id=msg_id,
                text_markdown=full_text,
                reply_markup=markup,
            )
    except Exception as e:
        logger.warning("Error in run_live_ticker_refresh_cycle: %s", e)


async def run_git_progress_cycle(evaluator: Any, notifier: Any) -> None:
    """Недельный цикл оценки прогресса в Git-репозиториях и создания карточек Notion (D-03, D-05)."""
    if evaluator is None:
        logger.info("Цикл оценки git пропущен: оценщик не инициализирован")
        return

    try:
        run = await evaluator.evaluate()
        proposals = await evaluator.propose_cards(run)
        for proposal in proposals:
            if getattr(proposal, "created", False):
                try:
                    text = evaluator.format_card_text(proposal.confirmation)
                    reply_markup = build_notion_sync_keyboard(proposal.confirmation.id)
                    await notifier.send_message(text, reply_markup=reply_markup)
                except Exception as e:
                    logger.warning(
                        "Не удалось отправить карточку Notion %s: %s",
                        getattr(getattr(proposal, "confirmation", None), "id", "?"),
                        e,
                    )

        changed = evaluator.register_run_signature(run)
        summary = evaluator.format_background_summary(run)
        if changed and summary:
            await notifier.send_message(summary)
    except Exception as e:
        logger.warning("Ошибка цикла оценки git: %s", e)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Assistant Core - Phase 1 & 2 Worker Daemon")
    parser.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    parser.add_argument("--brief", action="store_true", help="Force send morning brief and exit")
    parser.add_argument("--evening", action="store_true", help="Force send evening digest and exit")
    parser.add_argument("--prime", action="store_true", help="Force pre-compute daily morning context frame and exit")
    parser.add_argument("--review", action="store_true", help="Force trigger weekly memory review check and exit")
    parser.add_argument("--send-email-cards", action="store_true", help="Send cards for all current actionable emails")
    parser.add_argument("--send-email-id", type=int, help="Send card for a specific email by ID")
    args = parser.parse_args()

    logger.info("Assistant Worker starting up...")
    db = Database(config.SQLITE_DB_PATH)
    await db.init_db()
    logger.info("Database initialized at %s", config.SQLITE_DB_PATH)

    # Персона из config/persona.yaml в БД: по таблицам её читает chat-app (D-02).
    persona = current_persona()
    counts = await seed_persona(db, persona)
    logger.info(
        "Персона %s записана в БД: пространств %d, привязок %d",
        persona.id,
        counts["workspaces"],
        counts["bindings"],
    )
    missing = persona.unresolved_env_vars()
    if missing:
        logger.warning("Не заданы переменные окружения персоны: %s", ", ".join(missing))

    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    notifier = TelegramNotifier(
        bot_token=config.TELEGRAM_BOT_TOKEN,
        user_id=config.TELEGRAM_USER_ID,
        bot=bot,
    )
    reply_generator = ReplyGenerator()
    email_sender = EmailSender()
    summarizer = GeminiSummarizer()
    lms_client = default_lms_client()
    try:
        git_evaluator = default_git_evaluator(db)
    except Exception as e:
        logger.warning("Цепочка git не подключена: %s", e)
        git_evaluator = None

    calendar_client = GoogleCalendarClient(
        credentials_file=config.GOOGLE_CREDENTIALS_FILE,
        token_file=config.GOOGLE_TOKEN_FILE,
        timezone_str=config.TZ,
    )
    calendar_client.calendar_id = config.GOOGLE_CALENDAR_ID

    bot_handler = EmailBotHandler(
        db=db,
        reply_generator=reply_generator,
        email_sender=email_sender,
        notifier=notifier,
        bot=bot,
        allowed_user_id=config.TELEGRAM_USER_ID,
        summarizer=summarizer,
        lms_client=lms_client,
        calendar_client=calendar_client,
        git_evaluator=git_evaluator,
    )
    dp.include_router(bot_handler.router)
    await bot_handler.setup_bot_commands()

    schedule_parser = ScheduleParser(
        base_url=schedule_site_url(),
        timeout_seconds=30.0,
    )
    telegram_collector = TelegramCollector(db=db)
    email_collector = EmailCollector(db=db)
    summarizer = GeminiSummarizer()

    # Track morning and evening brief sources in DB
    await db.upsert_monitored_source(
        source_id="daily_morning_brief",
        source_type="briefing",
        display_name="Daily Morning Brief",
        config={"hour": 8, "minute": 0},
    )
    await db.upsert_monitored_source(
        source_id="daily_evening_digest",
        source_type="briefing",
        display_name="Daily Evening Digest",
        config={"hour": 21, "minute": 0},
    )

    if args.send_email_id:
        logger.info("Sending card for email ID=%d...", args.send_email_id)
        email_item = await db.get_email_by_id(args.send_email_id)
        if email_item:
            sent_ids = await notifier.send_actionable_email_card(email_item)
            if sent_ids:
                await db.set_email_card_msg_id(email_item["id"], sent_ids[-1])
                bot_handler.register_message(email_item["id"], sent_ids[-1])
            logger.info("Card sent for email ID=%d", args.send_email_id)
        else:
            logger.error("Email ID=%d not found in database", args.send_email_id)
        await bot.session.close()
        await db.close()
        return

    if args.send_email_cards:
        logger.info("Sending cards for all actionable emails...")
        actionable = await db.list_actionable_emails(limit=10)
        for it in actionable:
            full_item = await db.get_email_by_id(it["id"])
            if full_item:
                sent_ids = await notifier.send_actionable_email_card(full_item)
                if sent_ids:
                    await db.set_email_card_msg_id(full_item["id"], sent_ids[-1])
                    bot_handler.register_message(full_item["id"], sent_ids[-1])
        logger.info("Sent %d actionable email card(s).", len(actionable))
        await bot.session.close()
        await db.close()
        return

    if args.brief:
        logger.info("Force sending morning brief via --brief flag...")
        await run_morning_brief_cycle(db, schedule_parser, summarizer, notifier, force=True)
        await bot.session.close()
        await telegram_collector.disconnect()
        await db.close()
        return

    if args.evening:
        logger.info("Force sending evening digest via --evening flag...")
        await run_evening_digest_cycle(db, schedule_parser, summarizer, notifier, force=True)
        await bot.session.close()
        await telegram_collector.disconnect()
        await db.close()
        return

    if args.prime:
        logger.info("Force priming daily context via --prime flag...")
        sec = SecretaryDialogEngine(db=db)
        summary = await sec.prime_morning_context()
        print(summary)
        await bot.session.close()
        await telegram_collector.disconnect()
        await db.close()
        return

    if args.review:
        logger.info("Force checking weekly memory review via --review flag...")
        await run_weekly_memory_review_cycle(db, notifier)
        await bot.session.close()
        await telegram_collector.disconnect()
        await db.close()
        return

    # Run initial cycles
    await run_sentinel_cycle(db, schedule_parser, calendar_client, notifier)
    await run_telegram_collector_cycle(db, telegram_collector, notifier)
    await run_email_collector_cycle(db, email_collector, notifier)
    await run_lms_monitor_cycle(db, lms_client, notifier)

    # If current time is between 08:00 and 12:00 MSK and today's brief was not sent, send it now
    now_local = datetime.now(ZoneInfo(config.TZ))
    if 8 <= now_local.hour < 12:
        await run_morning_brief_cycle(db, schedule_parser, summarizer, notifier, force=False)

    if args.once:
        logger.info("Executed single cycle (--once). Shutting down.")
        await bot.session.close()
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
    # LMS student reports monitor runs every 30 minutes
    scheduler.add_job(
        run_lms_monitor_cycle,
        "interval",
        minutes=30,
        args=[db, lms_client, notifier],
        id="lms_monitor_job",
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
    # Evening digest runs daily at 21:00 MSK
    scheduler.add_job(
        run_evening_digest_cycle,
        "cron",
        hour=21,
        minute=0,
        args=[db, schedule_parser, summarizer, notifier],
        id="evening_digest_job",
        replace_existing=True,
    )
    # AADHk Google Drive sync runs every 2 hours
    scheduler.add_job(
        run_aadhk_gdrive_sync_cycle,
        "interval",
        hours=2,
        args=[db, notifier],
        id="aadhk_gdrive_sync_job",
        replace_existing=True,
    )
    # Nightly reset & morning priming runs daily at 04:00 MSK
    scheduler.add_job(
        run_nightly_reset_and_priming_cycle,
        "cron",
        hour=4,
        minute=0,
        args=[db, bot_handler.dialog_engine],
        id="nightly_reset_and_priming_job",
        replace_existing=True,
    )
    # Weekly Sunday memory review runs every Sunday at 09:00 MSK
    scheduler.add_job(
        run_weekly_memory_review_cycle,
        "cron",
        day_of_week="sun",
        hour=9,
        minute=0,
        args=[db, notifier],
        id="weekly_memory_review_job",
        replace_existing=True,
    )
    # Live HUD Ticker refresh runs every 5 minutes
    scheduler.add_job(
        run_live_ticker_refresh_cycle,
        "interval",
        minutes=5,
        args=[db, notifier],
        id="live_ticker_refresh_job",
        replace_existing=True,
    )
    # Weekly Git progress evaluation and Notion cards
    gs = git_source_settings()
    scheduler.add_job(
        run_git_progress_cycle,
        "cron",
        day_of_week=gs.day_of_week,
        hour=gs.hour,
        minute=gs.minute,
        args=[git_evaluator, notifier],
        id="git_progress_job",
        replace_existing=True,
    )
    logger.info(
        "Задача git_progress_job зарегистрирована: день недели %s, время %02d:%02d",
        gs.day_of_week,
        gs.hour,
        gs.minute,
    )

    # Initial refresh of active live tickers on daemon start
    await run_live_ticker_refresh_cycle(db, notifier)

    scheduler.start()
    logger.info(
        "Scheduler started. Reset/Priming at 04:00, Morning brief at 08:00, Evening digest at 21:00, Sunday Memory review at 09:00, Polling every %d hour(s).",
        config.SCHEDULE_POLL_INTERVAL_HOURS,
    )

    # Start Telegram Bot polling in background task for interactive callbacks
    logger.info("Starting Telegram Bot dispatcher polling for interactive email callbacks...")
    await bot_handler.setup_bot_commands()
    polling_task = asyncio.create_task(
        dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
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
        logger.info("Gracefully shutting down scheduler, bot polling, userbot and database...")
        scheduler.shutdown(wait=False)
        if polling_task and not polling_task.done():
            polling_task.cancel()
            try:
                await polling_task
            except asyncio.CancelledError:
                pass
        await bot.session.close()
        await telegram_collector.disconnect()
        await db.close()
        logger.info("Shutdown complete.")



if __name__ == "__main__":
    asyncio.run(main())
