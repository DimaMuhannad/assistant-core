#!/usr/bin/env python3
"""Generate executive daily brief using Gemini API and send to Telegram."""

import asyncio
from datetime import date
from pathlib import Path
import sys

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src import config
from src.brain.summarizer import GeminiSummarizer
from src.models.schedule import SchedulePayload
from src.notifier.telegram import TelegramNotifier
from src.storage.db import Database


async def run_brief(send_to_telegram: bool = True, source_id: str | None = None) -> str:
    db = Database(config.SQLITE_DB_PATH)
    await db.init_db()

    target_date = date.today()

    # 1. Fetch today's lessons from latest schedule snapshot
    today_lessons = []
    effective_source_id = source_id or getattr(config, "SCHEDULE_SOURCE_ID", None) or f"rasp_{config.SCHEDULE_TARGET_ID}"
    latest_snap = await db.get_latest_snapshot(effective_source_id)
    if not latest_snap:
        latest_snap = await db.get_latest_snapshot()
    if latest_snap and latest_snap.get("raw_payload"):
        try:
            payload = SchedulePayload.model_validate_json(latest_snap["raw_payload"])
            for day in payload.days:
                if day.date == target_date:
                    today_lessons = day.lessons
                    break
        except Exception as e:
            print(f"[!] Warning: Could not parse schedule snapshot: {e}")

    # 2. Fetch pending action items from Telegram chats
    action_items = await db.get_pending_action_items(limit=20)

    # 3. Generate brief with Gemini
    summarizer = GeminiSummarizer(api_key=config.GEMINI_API_KEY, model=config.GEMINI_MODEL)
    brief = await summarizer.generate_morning_brief(
        target_date=target_date,
        lessons=today_lessons,
        action_items=action_items,
    )

    # 4. Send to Telegram
    if send_to_telegram:
        notifier = TelegramNotifier(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            user_id=config.TELEGRAM_USER_ID,
        )
        await notifier.send_daily_brief(brief)

    await db.close()
    return brief


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate executive daily brief using Gemini API and send to Telegram.")
    parser.add_argument("--source-id", default=None, help="Schedule source ID (optional)")
    parser.add_argument("--no-telegram", action="store_true", help="Do not send brief to Telegram")
    args = parser.parse_args()

    brief_text = asyncio.run(run_brief(send_to_telegram=not args.no_telegram, source_id=args.source_id))
    print("\n" + "=" * 40)
    print(brief_text)
    print("=" * 40 + "\n")
