import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import Channel, Chat, User

from src.config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION_PATH
from src.detector.tg_filter import TelegramMessageFilter
from src.models.message import TelegramMessage
from src.storage.db import Database

logger = logging.getLogger(__name__)


class TelegramCollector:
    """Telethon Userbot client for autonomous Telegram chat/channel ingestion."""

    def __init__(
        self,
        db: Database,
        api_id: int | None = TELEGRAM_API_ID,
        api_hash: str = TELEGRAM_API_HASH,
        session_path: str = TELEGRAM_SESSION_PATH,
    ) -> None:
        self.db = db
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_stem = str(Path(session_path)).removesuffix(".session")
        self.filter = TelegramMessageFilter()
        self._client: TelegramClient | None = None

    def get_client(self) -> TelegramClient:
        if self._client is None:
            if not self.api_id or not self.api_hash:
                raise ValueError("TELEGRAM_API_ID or TELEGRAM_API_HASH not configured.")
            self._client = TelegramClient(self.session_stem, self.api_id, self.api_hash)
        return self._client

    async def connect(self) -> TelegramClient:
        client = self.get_client()
        if not client.is_connected():
            await client.connect()
        return client

    async def disconnect(self) -> None:
        if self._client and self._client.is_connected():
            await self._client.disconnect()

    async def is_authorized(self) -> bool:
        client = await self.connect()
        return await client.is_user_authorized()

    async def list_dialogs(self, limit: int = 30) -> list[dict[str, Any]]:
        """List active user dialogs (groups, channels, direct chats)."""
        client = await self.connect()
        dialogs = await client.get_dialogs(limit=limit)
        results = []
        for d in dialogs:
            entity_type = "channel" if d.is_channel else ("group" if d.is_group else "user")
            username = getattr(d.entity, "username", None)
            results.append(
                {
                    "id": d.id,
                    "title": d.name,
                    "type": entity_type,
                    "username": f"@{username}" if username else None,
                    "unread_count": d.unread_count,
                }
            )
        return results

    async def fetch_messages(
        self,
        peer: str | int,
        limit: int = 50,
        min_id: int = 0,
    ) -> tuple[str, str, list[TelegramMessage]]:
        """Fetch raw messages from a peer (username, link, or ID) and normalize to TelegramMessage."""
        client = await self.connect()
        entity = await client.get_entity(peer)
        chat_id = getattr(entity, "id", 0)
        chat_title = getattr(entity, "title", getattr(entity, "first_name", str(peer)))
        entity_type = "telegram_channel" if isinstance(entity, Channel) and not getattr(entity, "megagroup", False) else "telegram_group"

        raw_messages = []
        async for msg in client.iter_messages(entity, limit=limit, min_id=min_id):
            sender_name = None
            sender_username = None
            if msg.sender:
                if isinstance(msg.sender, User):
                    sender_name = f"{msg.sender.first_name or ''} {msg.sender.last_name or ''}".strip()
                    sender_username = msg.sender.username
                elif isinstance(msg.sender, Channel):
                    sender_name = msg.sender.title
                    sender_username = msg.sender.username

            media_type = None
            if msg.media:
                media_type = type(msg.media).__name__

            date = msg.date if msg.date else datetime.now(timezone.utc)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)

            raw_messages.append(
                TelegramMessage(
                    message_id=msg.id,
                    chat_id=chat_id,
                    chat_title=chat_title,
                    sender_id=msg.sender_id,
                    sender_name=sender_name,
                    sender_username=sender_username,
                    text=msg.text or "",
                    date=date,
                    has_media=bool(msg.media),
                    media_type=media_type,
                    reply_to_msg_id=msg.reply_to_msg_id if hasattr(msg, "reply_to_msg_id") else None,
                )
            )

        return entity_type, chat_title, raw_messages

    async def sync_chat(
        self,
        peer: str | int,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Fetch, deduplicate, filter and store messages for a target chat/channel."""
        try:
            entity_type, chat_title, messages = await self.fetch_messages(peer, limit=limit)
        except FloodWaitError as e:
            logger.warning(f"Telegram flood wait: {e.seconds} seconds required.")
            return {"error": "flood_wait", "seconds": e.seconds}
        except Exception as e:
            logger.exception(f"Failed to fetch messages for peer {peer}: {e}")
            return {"error": str(e)}

        source_id = f"tg_{peer}" if isinstance(peer, (int, str)) and not str(peer).startswith("tg_") else str(peer)

        # Upsert monitored source in database
        await self.db.upsert_monitored_source(
            source_id=source_id,
            source_type=entity_type,
            display_name=chat_title,
            config={"peer": peer, "limit": limit},
            is_active=True,
        )

        new_saved_count = 0
        action_items_created = 0
        action_items_details = []

        for msg in messages:
            # Check deduplication by SHA-256 hash
            existing = await self.db.get_content_snapshot_by_hash(source_id, msg.content_hash)
            if existing:
                continue

            # Save raw payload snapshot
            raw_payload = msg.model_dump_json()
            await self.db.save_snapshot(
                source_id=source_id,
                content_hash=msg.content_hash,
                raw_payload=raw_payload,
            )
            new_saved_count += 1

            # Run deterministic two-stage filter with temporal classification
            filter_res = self.filter.filter_message(msg)
            if filter_res.is_relevant:
                status = "expired" if filter_res.is_expired else "pending"
                action_item_id = await self.db.save_action_item(
                    source_type=entity_type,
                    priority_score=filter_res.priority,
                    summary_text=f"[{chat_title}] {filter_res.summary}",
                    payload={
                        "message_id": msg.message_id,
                        "chat_id": msg.chat_id,
                        "chat_title": chat_title,
                        "sender": msg.sender_name or msg.sender_username,
                        "text": msg.text,
                        "date": msg.date.isoformat(),
                        "category": filter_res.category,
                        "priority": filter_res.priority,
                        "matched_keywords": filter_res.matched_keywords,
                        "is_expired": filter_res.is_expired,
                        "freshness_label": filter_res.freshness_label,
                        "temporal_status": filter_res.temporal_status,
                    },
                    status=status,
                )
                action_items_created += 1
                if not filter_res.is_expired:
                    action_items_details.append(
                        {
                            "action_item_id": action_item_id,
                            "category": filter_res.category,
                            "priority": filter_res.priority,
                            "summary": filter_res.summary,
                            "freshness_label": filter_res.freshness_label,
                        }
                    )


        return {
            "source_id": source_id,
            "chat_title": chat_title,
            "entity_type": entity_type,
            "fetched_messages": len(messages),
            "new_snapshots_saved": new_saved_count,
            "action_items_created": action_items_created,
            "action_items": action_items_details,
        }
