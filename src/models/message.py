from datetime import datetime
import hashlib
from typing import Any
from pydantic import BaseModel, Field


class TelegramMessage(BaseModel):
    """Normalized Telegram message collected via MTProto."""

    message_id: int
    chat_id: int
    chat_title: str
    sender_id: int | None = None
    sender_name: str | None = None
    sender_username: str | None = None
    text: str = ""
    date: datetime
    has_media: bool = False
    media_type: str | None = None
    reply_to_msg_id: int | None = None
    content_hash: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.content_hash:
            raw_key = f"{self.chat_id}:{self.message_id}:{self.text}"
            self.content_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class FilterResult(BaseModel):
    """Result of deterministic rule-based message filtering."""

    is_relevant: bool
    priority: int = 1  # 1: Low, 2: Medium, 3: High / Urgent
    category: str = "general"  # deadline, schedule_change, faculty_notice, exam, etc.
    matched_keywords: list[str] = Field(default_factory=list)
    summary: str = ""


class FilteredActionItem(BaseModel):
    """An action item created from a filtered message."""

    source_type: str = "telegram"
    priority_score: int
    summary_text: str
    payload: dict[str, Any]
    status: str = "pending"
