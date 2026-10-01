import logging
import re
from typing import Any
from aiogram import Bot
from aiogram.types import MessageEntity, InlineKeyboardMarkup, InlineKeyboardButton
import telegramify_markdown

from src.models.schedule import ScheduleDiff

logger = logging.getLogger(__name__)


def build_email_action_keyboard(email_id: int) -> InlineKeyboardMarkup:
    """Builds inline action keyboard under an incoming email."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💡 Предложить ответ",
                    callback_data=f"em:sug:{email_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Написать ответ",
                    callback_data=f"em:wr:{email_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📜 Посмотреть всю переписку",
                    callback_data=f"em:th:{email_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Ответ не требуется",
                    callback_data=f"em:close:{email_id}",
                )
            ],
        ]
    )


def build_draft_action_keyboard(draft_id: int) -> InlineKeyboardMarkup:
    """Builds confirmation buttons under a generated or composed reply draft."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Отправить",
                    callback_data=f"dr:snd:{draft_id}",
                ),
                InlineKeyboardButton(
                    text="✏️ Исправить",
                    callback_data=f"dr:edt:{draft_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data=f"dr:cnc:{draft_id}",
                )
            ],
        ]
    )


def build_lms_tasks_keyboard() -> InlineKeyboardMarkup:
    """Builds action keyboard for managing GUAP LMS assignments."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👁️ Опубликовать...", callback_data="lms:pub_menu"),
                InlineKeyboardButton(text="🔒 Скрыть...", callback_data="lms:hide_menu"),
            ],
            [
                InlineKeyboardButton(text="➕ Создать задание", callback_data="lms:create_menu"),
                InlineKeyboardButton(text="🗑️ Удалить задание", callback_data="lms:del_prompt"),
            ],
            [
                InlineKeyboardButton(text="📥 Сданные отчеты", callback_data="lms:reports"),
                InlineKeyboardButton(text="🔄 Обновить", callback_data="lms:refresh"),
            ],
        ]
    )


def build_lms_pub_hide_keyboard(action_prefix: str) -> InlineKeyboardMarkup:
    """Builds sub-menu for publishing or hiding specific lab assignments."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Лаб №1", callback_data=f"{action_prefix}1"),
                InlineKeyboardButton(text="Лаб №2", callback_data=f"{action_prefix}2"),
            ],
            [
                InlineKeyboardButton(text="Лаб №3", callback_data=f"{action_prefix}3"),
                InlineKeyboardButton(text="Лаб №4", callback_data=f"{action_prefix}4"),
            ],
            [
                InlineKeyboardButton(text="⚡ Все лабораторные", callback_data=f"{action_prefix}all"),
            ],
            [
                InlineKeyboardButton(text="◀️ Назад к заданиям", callback_data="lms:refresh"),
            ],
        ]
    )


def format_and_split_for_telegram(raw_markdown: str) -> list[tuple[str, list[MessageEntity]]]:
    """Cleans markdown and converts to native Telegram entities without escape artifacts."""
    # 1. Clean local IDE file links: [file.py](file:///path/to/file.py) -> `file.py`
    cleaned = re.sub(r"\[([^\]]+)\]\(file:///[^\)]+\)", r"`\1`", raw_markdown)
    # 2. Replace heavy checkmarks (✔️) with clean standard list bullets
    cleaned = re.sub(r"^[ \t]*[-*•]?\s*[\u2713\u2714\u2705\u2611]\uFE0F?\s*", "- ", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"[\u2713\u2714]\uFE0F?", "•", cleaned)
    # 3. Strip horizontal rule lines (---, ***, ___, -------)
    cleaned = re.sub(r"^[ \t]*[-*_—─]{3,}[ \t]*$", "", cleaned, flags=re.MULTILINE)
    # 4. Normalize excessive newlines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    # 5. Convert with custom RenderConfig (no horizontal rule dashes, clean bullets)
    config = telegramify_markdown.RenderConfig()
    config.markdown_symbol.horizontal_rule = ""
    config.markdown_symbol.unordered_list_item = "•"

    text, raw_entities = telegramify_markdown.convert(cleaned, config=config)
    chunks = telegramify_markdown.split_entities(text, raw_entities, 3900)

    result = []
    for chunk_text, chunk_entities in chunks:
        aio_entities = [
            MessageEntity(
                type=e.type,
                offset=e.offset,
                length=e.length,
                url=e.url,
                language=e.language,
                custom_emoji_id=getattr(e, "custom_emoji_id", None),
            )
            for e in chunk_entities
        ]
        result.append((chunk_text, aio_entities))
    return result


class TelegramNotifier:
    """Sends schedule update alerts and executive digests to Telegram with specialized academic formatting."""

    def __init__(self, bot_token: str | None, user_id: str | int | None, bot: Bot | None = None):
        self.bot_token = bot_token
        self.user_id = user_id
        self._shared_bot = bot
        self.is_configured = bool(
            (bot_token or bot) and user_id and not (bot_token and bot_token.startswith("123456789:ABC"))
        )

    async def _send_rich_message(
        self,
        text_markdown: str,
        reply_markup: Any | None = None,
        chat_id: str | int | None = None,
        allow_group: bool = False,
    ) -> list[int]:
        """Sends markdown formatted message using native Telegram entities with clean text fallback. Returns list of sent message IDs."""
        if not self.is_configured:
            return []

        target_chat = chat_id or self.user_id

        # Strict safety guardrail: prevent accidental broadcast to group/channel without explicit sanction
        if target_chat and str(target_chat).startswith("-") and not allow_group:
            logger.error(
                "SAFETY BLOCK: Prevented unauthorized message transmission to group/channel %s without explicit allow_group sanction!",
                target_chat,
            )
            return []

        should_close_bot = False
        if self._shared_bot:
            bot = self._shared_bot
        else:
            bot = Bot(token=self.bot_token)
            should_close_bot = True

        sent_msg_ids: list[int] = []
        try:
            chunks = format_and_split_for_telegram(text_markdown)
            num_chunks = len(chunks)
            for idx, (chunk_text, aio_entities) in enumerate(chunks):
                if chunk_text.strip():
                    is_last = (idx == num_chunks - 1)
                    sent_msg = await bot.send_message(
                        chat_id=target_chat,
                        text=chunk_text,
                        entities=aio_entities,
                        reply_markup=reply_markup if is_last else None,
                    )
                    if sent_msg and hasattr(sent_msg, "message_id"):
                        sent_msg_ids.append(sent_msg.message_id)
            return sent_msg_ids
        except Exception as e:
            logger.warning("Native entities dispatch failed (%s), falling back to clean text", e)
            clean = re.sub(r"\[([^\]]+)\]\(file:///[^\)]+\)", r"\1", text_markdown)
            clean = re.sub(r"^[ \t]*[-*_—─]{3,}[ \t]*$", "", clean, flags=re.MULTILINE)
            fallback_msg = await bot.send_message(
                chat_id=target_chat,
                text=clean[:3900],
                reply_markup=reply_markup,
            )
            if fallback_msg and hasattr(fallback_msg, "message_id"):
                sent_msg_ids.append(fallback_msg.message_id)
            return sent_msg_ids
        finally:
            if should_close_bot:
                await bot.session.close()

    async def send_message(
        self,
        text_markdown: str,
        reply_markup: Any | None = None,
        chat_id: str | int | None = None,
        allow_group: bool = False,
    ) -> list[int]:
        """Send formatted markdown message to user. Returns list of message IDs."""
        return await self._send_rich_message(
            text_markdown,
            reply_markup=reply_markup,
            chat_id=chat_id,
            allow_group=allow_group,
        )

    async def edit_rich_message(
        self,
        chat_id: str | int,
        message_id: int,
        text_markdown: str,
        reply_markup: Any | None = None,
    ) -> bool:
        """Edits an existing telegram message in-place using rich markdown entities.
        Silently ignores 'message is not modified' and logs errors gracefully."""
        if not self.is_configured:
            return False

        should_close_bot = False
        if self._shared_bot:
            bot = self._shared_bot
        else:
            bot = Bot(token=self.bot_token)
            should_close_bot = True

        try:
            chunks = render_telegram_markdown(text_markdown)
            if not chunks:
                return False
            chunk_text, chunk_entities = chunks[0]
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=chunk_text,
                entities=chunk_entities,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
            return True
        except Exception as e:
            err_msg = str(e).lower()
            if "message is not modified" in err_msg:
                return True
            logger.warning("edit_rich_message failed for chat %s, msg %s: %s", chat_id, message_id, e)
            return False
        finally:
            if should_close_bot:
                await bot.session.close()

    async def send_actionable_email_card(
        self,
        email_data: dict[str, Any],
        chat_id: str | int | None = None,
    ) -> list[int]:
        """Sends a card with FULL email text and interactive action buttons. Returns sent message IDs."""
        email_id = email_data.get("id")
        sender_name = email_data.get("sender_name") or ""
        sender_email = email_data.get("sender_email") or ""
        subject = email_data.get("subject") or "Без темы"
        date_sent = email_data.get("date_sent") or ""
        if hasattr(date_sent, "strftime"):
            date_str = date_sent.strftime("%d.%m.%Y %H:%M")
        else:
            date_str = str(date_sent)[:16].replace("T", " ")

        category = email_data.get("category", "guap_student")
        cat_label = "Студент ГУАП" if category == "guap_student" else "Кафедра/Университет"
        sender_display = f"**{sender_name}** (`{sender_email}`)" if sender_name else f"`{sender_email}`"

        body = (email_data.get("body_plain") or email_data.get("snippet") or "").strip()
        if not body:
            body = "Текст письма отсутствует."

        message_text = (
            f"📬 **Входящее письмо ({cat_label})**\n\n"
            f"👤 **От:** {sender_display}\n"
            f"📌 **Тема:** {subject}\n"
            f"🕒 **Дата:** {date_str}\n\n"
            f"📝 **Текст письма:**\n"
            f"{body}"
        )

        keyboard = build_email_action_keyboard(email_id) if email_id else None
        return await self._send_rich_message(message_text, reply_markup=keyboard, chat_id=chat_id)

    async def send_draft_reply_card(
        self,
        draft_data: dict[str, Any],
        chat_id: str | int | None = None,
    ) -> list[int]:
        """Sends a card with proposed reply draft and confirmation buttons. Returns sent message IDs."""
        draft_id = draft_data.get("draft_id") or draft_data.get("id")
        sender_name = draft_data.get("sender_name") or ""
        sender_email = draft_data.get("sender_email") or ""
        subject = draft_data.get("subject") or ""
        reply_subject = f"Re: {subject}" if not subject.lower().startswith("re:") else subject
        draft_text = (draft_data.get("draft_text") or "").strip()

        target_display = f"**{sender_name}** (`{sender_email}`)" if sender_name else f"`{sender_email}`"

        message_text = (
            f"💡 **Предложенный проект ответа**\n\n"
            f"👤 **Кому:** {target_display}\n"
            f"📌 **Тема:** {reply_subject}\n\n"
            f"📝 **Текст ответа:**\n"
            f"{draft_text}"
        )

        keyboard = build_draft_action_keyboard(draft_id) if draft_id else None
        return await self._send_rich_message(message_text, reply_markup=keyboard, chat_id=chat_id)

    async def send_evening_digest(self, digest_markdown: str, chat_id: str | int | None = None) -> bool:
        """Send evening executive summary to Telegram."""
        if not digest_markdown:
            return False
        res = await self._send_rich_message(digest_markdown, chat_id=chat_id)
        return len(res) > 0

    async def send_schedule_diff_alert(self, diff: ScheduleDiff, target_id: str) -> bool:
        """Send formatted alert when schedule changes are detected."""
        if not diff.has_changes:
            return False

        lines = [f"📅 **Обновление расписания преподавателя (ID: {target_id})**\n"]

        if diff.modified_lessons:
            lines.append(f"🔄 **Изменения в парах ({len(diff.modified_lessons)}):**")
            for mod in diff.modified_lessons:
                nl = mod.new_lesson
                ol = mod.old_lesson
                type_name = {
                    "LECTURE": "Лекция",
                    "PRACTICE": "Практика",
                    "LAB": "Лаб. работа",
                    "EXAM": "Экзамен",
                    "UNKNOWN": "Пара",
                }.get(nl.lesson_type.value, nl.lesson_type.value)

                lines.append(
                    f"• {nl.date.strftime('%d.%m')} {nl.start_time.strftime('%H:%M')}–{nl.end_time.strftime('%H:%M')} "
                    f"| [{type_name}] {nl.subject}"
                )
                if ol.room != nl.room:
                    lines.append(f"  📍 Аудитория: ~{ol.room}~ ➡️ **{nl.room}**")
                if ol.group != nl.group:
                    lines.append(f"  👥 Группа: ~{ol.group}~ ➡️ **{nl.group}**")
                if ol.teacher != nl.teacher:
                    lines.append(f"  👤 Преподаватель: ~{ol.teacher}~ ➡️ **{nl.teacher}**")
            lines.append("")

        if diff.added_lessons:
            lines.append(f"➕ **Новые пары ({len(diff.added_lessons)}):**")
            for l in diff.added_lessons:
                type_name = {
                    "LECTURE": "Лекция",
                    "PRACTICE": "Практика",
                    "LAB": "Лаб. работа",
                    "EXAM": "Экзамен",
                    "UNKNOWN": "Пара",
                }.get(l.lesson_type.value, l.lesson_type.value)

                room_str = f"📍 {l.room}" if l.room and l.room != "Не указана" else ""
                group_str = f"Группа: {l.group}" if hasattr(l, "group") and l.group else ""
                details = " • ".join(filter(None, [room_str, group_str]))

                lines.append(
                    f"• {l.date.strftime('%d.%m')} {l.start_time.strftime('%H:%M')}–{l.end_time.strftime('%H:%M')} "
                    f"| [{type_name}] {l.subject}"
                )
                if details:
                    lines.append(f"  {details}")
            lines.append("")

        if diff.removed_lessons:
            lines.append(f"➖ **Отмененные / перенесенные пары ({len(diff.removed_lessons)}):**")
            for l in diff.removed_lessons:
                room_str = f"📍 {l.room}" if l.room and l.room != "Не указана" else ""
                lines.append(
                    f"• {l.date.strftime('%d.%m')} {l.start_time.strftime('%H:%M')}–{l.end_time.strftime('%H:%M')} "
                    f"| {l.subject}"
                )
                if room_str:
                    lines.append(f"  {room_str}")
            lines.append("")

        message_text = "\n".join(lines).strip()

        if not self.is_configured:
            logger.info("[TELEGRAM DRY-RUN] Alert for target %s:\n%s", target_id, message_text)
            return True

        success = await self._send_rich_message(message_text)
        if success:
            logger.info("Telegram notification sent successfully to user %s", self.user_id)
        return success

    async def send_action_items_alert(self, items: list[dict[str, Any]]) -> bool:
        """Send formatted alert for newly detected urgent action items from Telegram chats."""
        if not items:
            return False

        lines = [f"⚡ **Информационный щит: важные события ({len(items)})**\n"]
        for it in items:
            priority = it.get("priority", 1)
            priority_icon = "🚨" if priority >= 3 else "📌"
            category = it.get("category", "info").upper()
            summary = it.get("summary", "")
            lines.append(f"{priority_icon} **[{category}]** {summary}")

        message_text = "\n".join(lines).strip()

        if not self.is_configured:
            logger.info("[TELEGRAM DRY-RUN] Action items alert:\n%s", message_text)
            return True

        success = await self._send_rich_message(message_text)
        if success:
            logger.info("Sent action items alert to Telegram user %s", self.user_id)
        return success

    async def send_daily_brief(self, brief_markdown: str) -> bool:
        """Send morning executive brief generated by Gemini."""
        if not brief_markdown:
            return False

        if not self.is_configured:
            logger.info("[TELEGRAM DRY-RUN] Daily brief:\n%s", brief_markdown)
            return True

        success = await self._send_rich_message(brief_markdown)
        if success:
            logger.info("Sent daily brief to Telegram user %s", self.user_id)
        return success

    async def send_voice_transcription_card(
        self,
        voice_res: Any,
        sender_name: str = "",
        chat_title: str = "",
    ) -> bool:
        """Send formatted card for transcribed voice message."""
        if not voice_res:
            return False

        dur_seconds = getattr(voice_res, "duration_seconds", None)
        dur_str = f" ({dur_seconds} сек)" if dur_seconds else ""
        lines = [f"🎙️ **Голосовое сообщение{dur_str}**"]

        origin = []
        if sender_name:
            origin.append(f"От: *{sender_name}*")
        if chat_title:
            origin.append(f"Чат: *{chat_title}*")
        if origin:
            lines.append(" • ".join(origin))

        lines.append("")

        transcription = getattr(voice_res, "transcription", "")
        if transcription:
            lines.append("📝 **Расшифровка:**")
            lines.append(f"«{transcription}»\n")

        summary = getattr(voice_res, "summary", "")
        if summary:
            lines.append(f"📌 **Суть:** {summary}\n")

        action_items = getattr(voice_res, "action_items", [])
        if action_items:
            lines.append("⚡ **Выделенные задачи:**")
            for item in action_items:
                lines.append(f"• {item}")
            lines.append("")

        message_text = "\n".join(lines).strip()
        if not self.is_configured:
            logger.info("[TELEGRAM DRY-RUN] Voice card:\n%s", message_text)
            return True

        return await self._send_rich_message(message_text)

