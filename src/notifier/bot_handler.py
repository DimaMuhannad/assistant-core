import logging
from datetime import datetime, timezone, date
from typing import Any

from aiogram import Router, F, Bot
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import Command

from src.storage.db import Database
from src.brain.reply_generator import ReplyGenerator
from src.brain.summarizer import GeminiSummarizer
from src.sender.email_sender import EmailSender
from src.notifier.telegram import (
    TelegramNotifier,
    build_email_action_keyboard,
    build_draft_action_keyboard,
    format_and_split_for_telegram,
)

logger = logging.getLogger(__name__)


class EmailBotHandler:
    """Handles Telegram inline callbacks, message cleanup, and interactive replies for email workflow."""

    def __init__(
        self,
        db: Database,
        reply_generator: ReplyGenerator,
        email_sender: EmailSender,
        notifier: TelegramNotifier,
        bot: Bot | None = None,
        allowed_user_id: int | str | None = None,
        summarizer: GeminiSummarizer | None = None,
    ):
        self.db = db
        self.reply_generator = reply_generator
        self.email_sender = email_sender
        self.notifier = notifier
        self.allowed_user_id = int(allowed_user_id) if allowed_user_id else None
        self.bot = bot or getattr(notifier, "_shared_bot", None)
        if not self.bot:
            token = getattr(notifier, "bot_token", "")
            if token:
                try:
                    self.bot = Bot(token=token)
                except Exception as e:
                    logger.warning("Could not initialize Bot with token: %s", e)
                    self.bot = None
        self.summarizer = summarizer or GeminiSummarizer()

        self.router = Router()
        # In-memory FSM state: user_id -> {"action": "edit"|"write", "draft_id": int, "email_id": int, ...}
        self.waiting_input: dict[int, dict[str, Any]] = {}
        # Tracking messages to delete upon sending: email_id -> set of message_ids
        self.session_messages: dict[int, set[int]] = {}

        self._register_handlers()

    def _is_authorized(self, user_id: int) -> bool:
        if self.allowed_user_id is None:
            return True
        return user_id == self.allowed_user_id

    def register_message(self, email_id: int, message_id: int) -> None:
        """Register a Telegram message ID to be cleaned up when email interaction completes."""
        if email_id not in self.session_messages:
            self.session_messages[email_id] = set()
        self.session_messages[email_id].add(message_id)

    async def cleanup_email_session(self, chat_id: int, email_id: int) -> None:
        """Deletes all messages associated with this email (card, draft, prompts) to leave chat spotless."""
        # 1. Gather all tracked in-memory message IDs
        msg_ids = self.session_messages.pop(email_id, set())

        # 2. Check DB for persisted card_message_id
        email_data = await self.db.get_email_by_id(email_id)
        if email_data and email_data.get("card_message_id"):
            msg_ids.add(email_data["card_message_id"])

        logger.info("Cleaning up %d message(s) from chat %s for email id=%s", len(msg_ids), chat_id, email_id)
        for mid in msg_ids:
            try:
                await self.bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception as e:
                logger.debug("Could not delete message %d: %s", mid, e)

    def _register_handlers(self) -> None:
        # Commands
        self.router.message(Command("start", "help"))(self.handle_cmd_help)
        self.router.message(Command("emails", "inbox"))(self.handle_cmd_emails)
        self.router.message(Command("evening", "digest"))(self.handle_cmd_evening)
        self.router.message(Command("timesheet", "tydex", "hours"))(self.handle_cmd_timesheet)
        self.router.message(Command("cancel", "cansel"))(self.handle_cmd_cancel)

        # Callbacks under email card
        self.router.callback_query(F.data.startswith("em:sug:"))(self.cb_suggest_reply)
        self.router.callback_query(F.data.startswith("em:wr:"))(self.cb_write_reply)
        self.router.callback_query(F.data.startswith("em:th:"))(self.cb_view_thread)

        # Callbacks under timesheet
        self.router.callback_query(F.data == "ts:sync_gdrive")(self.cb_timesheet_sync)

        # Callbacks under draft card
        self.router.callback_query(F.data.startswith("dr:snd:"))(self.cb_send_reply)
        self.router.callback_query(F.data.startswith("dr:edt:"))(self.cb_edit_draft)
        self.router.callback_query(F.data.startswith("dr:cnc:"))(self.cb_cancel_draft)
        self.router.callback_query(F.data == "dr:cnc_input")(self.cb_cancel_input)

        # Interactive text messages (for edit or manual draft entry)
        self.router.message(F.text)(self.handle_user_text)

        # Photos and screenshots
        self.router.message(F.photo)(self.handle_user_photo)

        # Documents (files, images, txt, pdf)
        self.router.message(F.document)(self.handle_user_document)

    async def handle_cmd_help(self, message: Message) -> None:
        if not self._is_authorized(message.from_user.id):
            return
        text = (
            "🤖 **Академический ассистент ГУАП (Кафедра физики)**\n\n"
            "Сервис 24/7 ведет мониторинг расписания, почты и рабочих чатов.\n\n"
            "Доступные команды:\n"
            "• `/emails` — показать неотвеченные письма студентов и кафедры\n"
            "• `/timesheet` — учет часов в «Тидекс» и наложения на пары ГУАП\n"
            "• `/evening` — вечерний дайджест со статистикой обработки писем\n"
            "• `/help` — справка по возможностям бота\n\n"
            "После отправки ответа на письмо все карточки и служебные сообщения автоматически удаляются из чата, "
            "а статистика ответов сохраняется в вечернем дайджесте."
        )
        await self.notifier.send_message(text, chat_id=message.chat.id)


    async def handle_cmd_emails(self, message: Message) -> None:
        if not self._is_authorized(message.from_user.id):
            return
        actionable = await self.db.list_actionable_emails(limit=10)
        if not actionable:
            await self.notifier.send_message("✨ **Все входящие письма обработаны!** Неотвеченных писем нет.", chat_id=message.chat.id)
            return

        await self.notifier.send_message(
            f"📬 **Список активных писем, требующих ответа ({len(actionable)}):**",
            chat_id=message.chat.id,
        )
        for item in actionable:
            full_email = await self.db.get_email_by_id(item["id"])
            if full_email:
                sent_ids = await self.notifier.send_actionable_email_card(full_email, chat_id=message.chat.id)
                if sent_ids:
                    await self.db.set_email_card_msg_id(item["id"], sent_ids[-1])
                    self.register_message(item["id"], sent_ids[-1])

    async def handle_cmd_evening(self, message: Message) -> None:
        """Trigger evening digest on demand."""
        if not self._is_authorized(message.from_user.id):
            return
        status_msg = await message.answer("🌙 Собираю вечерний дайджест за сегодня...")
        try:
            from datetime import timedelta
            from src import config
            from src.models.schedule import SchedulePayload

            today = date.today()
            tomorrow = today + timedelta(days=1)

            email_stats = await self.db.get_daily_email_stats(today)

            tomorrow_lessons = []
            snap = await self.db.get_latest_snapshot(f"rasp_guap_{config.SCHEDULE_TARGET_ID}")
            if snap and snap.get("raw_payload"):
                try:
                    payload = SchedulePayload.model_validate_json(snap["raw_payload"])
                    for day in payload.days:
                        if day.date == tomorrow:
                            tomorrow_lessons = day.lessons
                except Exception as pe:
                    logger.warning("Failed to parse schedule payload: %s", pe)

            digest_md = await self.summarizer.generate_evening_digest(
                target_date=today,
                email_stats=email_stats,
                tomorrow_date=tomorrow,
                tomorrow_lessons=tomorrow_lessons,
            )
            try:
                await status_msg.delete()
            except Exception:
                pass
            await self.notifier.send_evening_digest(digest_md, chat_id=message.chat.id)
        except Exception as e:
            logger.exception("Error generating evening digest: %s", e)
            await status_msg.edit_text(f"❌ Ошибка генерации дайджеста: {e}")

    async def handle_cmd_cancel(self, message: Message) -> None:
        """Cancel active draft edit/write prompt or ongoing interaction."""
        if not self._is_authorized(message.from_user.id):
            return

        state = self.waiting_input.pop(message.from_user.id, None)
        if state and self.bot:
            prompt_id = state.get("prompt_msg_id")
            if prompt_id:
                try:
                    await self.bot.delete_message(chat_id=message.chat.id, message_id=prompt_id)
                except Exception:
                    pass

        try:
            await message.delete()
        except Exception:
            pass

        status_msg = await message.answer("🛑 **Действие отменено.** Чат очищен.")
        if self.bot:
            async def _cleanup():
                await asyncio.sleep(4)
                try:
                    await status_msg.delete()
                except Exception:
                    pass
            asyncio.create_task(_cleanup())

    async def cb_suggest_reply(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            await callback.answer("Доступ ограничен.", show_alert=True)
            return

        try:
            email_id = int(callback.data.split(":")[-1])
        except (ValueError, IndexError):
            await callback.answer("Неверный ID письма.")
            return

        # Immediate toast notification to Telegram
        await callback.answer("💡 Генерирую проект ответа через Gemini...")

        # Register the card message ID for cleanup
        self.register_message(email_id, callback.message.message_id)

        # Temporary placeholder with visual progress
        placeholder = await callback.message.answer("⏳ **Генерирую проект ответа через Gemini...**")
        self.register_message(email_id, placeholder.message_id)

        email_data = await self.db.get_email_by_id(email_id)
        if not email_data:
            await placeholder.edit_text("❌ Ошибка: письмо не найдено в базе данных.")
            return

        draft_text = await self.reply_generator.generate_reply(email_data)
        draft_id = await self.db.create_email_draft(email_id, draft_text)
        draft_info = await self.db.get_email_draft(draft_id)

        if draft_info:
            await self.db.set_draft_msg_id(draft_id, placeholder.message_id)
            reply_subject = f"Re: {draft_info['subject']}" if not draft_info['subject'].lower().startswith("re:") else draft_info['subject']
            s_name = draft_info.get("sender_name") or draft_info.get("sender_email")

            card_text = (
                f"💡 **Предложенный проект ответа**\n\n"
                f"👤 **Кому:** **{s_name}** (`{draft_info.get('sender_email')}`)\n"
                f"📌 **Тема:** {reply_subject}\n\n"
                f"📝 **Текст ответа:**\n"
                f"{draft_text.strip()}"
            )
            chunks = format_and_split_for_telegram(card_text)
            if len(chunks) == 1:
                await placeholder.edit_text(
                    text=chunks[0][0],
                    entities=chunks[0][1],
                    reply_markup=build_draft_action_keyboard(draft_id),
                )
            else:
                # If large, delete placeholder and send full card
                try:
                    await placeholder.delete()
                except Exception:
                    pass
                sent_ids = await self.notifier.send_draft_reply_card(draft_info, chat_id=callback.message.chat.id)
                for sid in sent_ids:
                    self.register_message(email_id, sid)
        else:
            await placeholder.edit_text("❌ Ошибка создания черновика.")

    async def cb_send_reply(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            await callback.answer("Доступ ограничен.", show_alert=True)
            return

        try:
            draft_id = int(callback.data.split(":")[-1])
        except (ValueError, IndexError):
            await callback.answer("Неверный ID черновика.")
            return

        draft_info = await self.db.get_email_draft(draft_id)
        if not draft_info:
            await callback.answer("Черновик не найден.")
            return

        if draft_info.get("draft_status") == "sent":
            await callback.answer("⚠️ Этот ответ уже был отправлен ранее.", show_alert=True)
            return

        await callback.answer("📤 Отправляю письмо адресату...")

        email_id = draft_info["email_id"]
        recipient = draft_info["sender_email"]
        subject = draft_info.get("subject") or "Без темы"
        reply_subject = f"Re: {subject}" if not subject.lower().startswith("re:") else subject
        body = draft_info["draft_text"]
        account_id = draft_info.get("account_id") or "mailru"
        in_reply_to = draft_info.get("message_id")
        references = draft_info.get("references_text") or in_reply_to

        res = await self.email_sender.send_reply(
            to_email=recipient,
            subject=reply_subject,
            body=body,
            account_id=account_id,
            in_reply_to=in_reply_to,
            references=references,
        )

        if res.get("success"):
            await self.db.update_email_draft(draft_id, status="sent")
            await self.db.mark_email_as_answered(
                email_id,
                reply_message_id=res.get("message_id"),
                user_email=res.get("from"),
            )

            # Native Telegram pop-up alert (no chat clutter)
            await callback.answer(f"✅ Ответ успешно отправлен на {recipient}!\nЧат очищен.", show_alert=True)

            # Clean up all messages relating to this email from the chat
            self.register_message(email_id, callback.message.message_id)
            await self.cleanup_email_session(callback.message.chat.id, email_id)
        else:
            err = res.get("error", "Неизвестная ошибка")
            await callback.message.answer(f"❌ **Ошибка при отправке письма:**\n`{err}`")

    async def cb_cancel_draft(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            return

        try:
            draft_id = int(callback.data.split(":")[-1])
            await self.db.update_email_draft(draft_id, status="cancelled")
        except Exception:
            pass

        await callback.answer("Отменено", show_alert=False)
        try:
            await callback.message.delete()
        except Exception:
            pass

    async def cb_edit_draft(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            return

        try:
            draft_id = int(callback.data.split(":")[-1])
        except (ValueError, IndexError):
            await callback.answer("Неверный ID.")
            return

        user_id = callback.from_user.id

        # DEBOUNCE: if already waiting for input on this draft, prevent duplicate clicks
        if user_id in self.waiting_input and self.waiting_input[user_id].get("draft_id") == draft_id:
            await callback.answer("Ожидаю текст правок в чате...", show_alert=False)
            return

        draft_info = await self.db.get_email_draft(draft_id)
        if not draft_info:
            await callback.answer("Черновик не найден.")
            return

        # 1. Instant callback acknowledgment
        await callback.answer("Пишите свои исправления в чат", show_alert=False)

        # 2. Instant standard prompt message (non-generated, instantaneous)
        cancel_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена ввода", callback_data="dr:cnc_input")]
            ]
        )
        prompt_msg = await callback.message.answer(
            "✏️ **Пишите свои исправления в чат:**",
            reply_markup=cancel_kb,
        )

        email_id = draft_info["email_id"]
        self.register_message(email_id, prompt_msg.message_id)
        self.register_message(email_id, callback.message.message_id)

        self.waiting_input[user_id] = {
            "action": "edit",
            "draft_id": draft_id,
            "email_id": email_id,
            "prompt_msg_id": prompt_msg.message_id,
            "draft_msg_id": callback.message.message_id,
        }

    async def cb_write_reply(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            return

        try:
            email_id = int(callback.data.split(":")[-1])
        except (ValueError, IndexError):
            await callback.answer("Неверный ID.")
            return

        user_id = callback.from_user.id
        if user_id in self.waiting_input and self.waiting_input[user_id].get("email_id") == email_id:
            await callback.answer("Ожидаю текст ответа в чате...", show_alert=False)
            return

        # 1. Instant callback acknowledgment
        await callback.answer("Пишите текст ответа в чат", show_alert=False)

        # 2. Instant standard prompt message
        cancel_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена ввода", callback_data="dr:cnc_input")]
            ]
        )
        prompt_msg = await callback.message.answer(
            "✏️ **Пишите текст ответа в чат:**",
            reply_markup=cancel_kb,
        )

        self.register_message(email_id, prompt_msg.message_id)
        self.register_message(email_id, callback.message.message_id)

        self.waiting_input[user_id] = {
            "action": "write",
            "email_id": email_id,
            "prompt_msg_id": prompt_msg.message_id,
        }

    async def cb_cancel_input(self, callback: CallbackQuery) -> None:
        if callback.from_user.id in self.waiting_input:
            del self.waiting_input[callback.from_user.id]
        await callback.answer("Ввод отменен.")
        try:
            await callback.message.delete()
        except Exception:
            pass

    async def cb_view_thread(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            return

        try:
            email_id = int(callback.data.split(":")[-1])
        except (ValueError, IndexError):
            await callback.answer("Неверный ID.")
            return

        await callback.answer("Загружаю переписку...")

        email_data = await self.db.get_email_by_id(email_id)
        if not email_data:
            await callback.message.answer("❌ Письмо не найдено.")
            return

        thread_id = email_data.get("thread_id")
        messages = await self.db.get_thread_messages(thread_id)

        if not messages:
            await callback.message.answer("📜 В этой цепочке пока только 1 сообщение (текущее).")
            return

        lines = [f"📜 **История переписки ({len(messages)} сообщ.)**\n📌 **Тема:** {email_data.get('subject', 'Без темы')}\n"]

        for idx, m in enumerate(messages, 1):
            s_name = m.get("sender_name") or m.get("sender_email")
            s_date = str(m.get("date_sent", ""))[:16].replace("T", " ")
            body_prev = (m.get("body_plain") or m.get("snippet") or "").strip()
            body_short = body_prev[:400] + ("..." if len(body_prev) > 400 else "")

            status_icon = "📨" if not m.get("is_answered") else "✅"
            lines.append(f"{idx}. {status_icon} **{s_name}** ({s_date}):")
            lines.append(f"_{body_short}_\n")

        full_thread_text = "\n".join(lines).strip()
        thread_msg = await callback.message.answer(full_thread_text)
        self.register_message(email_id, thread_msg.message_id)

    async def handle_user_text(self, message: Message) -> None:
        user_id = message.from_user.id
        if not self._is_authorized(user_id):
            return

        state = self.waiting_input.pop(user_id, None)
        if not state:
            return  # Normal text message unrelated to email draft prompt

        # 1. Clean up user's own typed message to keep chat spotless
        try:
            await message.delete()
        except Exception:
            pass

        # 2. Clean up prompt message
        prompt_id = state.get("prompt_msg_id")
        if prompt_id:
            try:
                await self.bot.delete_message(chat_id=message.chat.id, message_id=prompt_id)
            except Exception:
                pass

        action = state.get("action")
        email_id = state.get("email_id")

        if action == "edit":
            draft_id = state.get("draft_id")
            draft_msg_id = state.get("draft_msg_id")
            draft_info = await self.db.get_email_draft(draft_id)
            if not draft_info:
                return

            # Show quick in-place loading state on the existing draft message
            if draft_msg_id:
                try:
                    await self.bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=draft_msg_id,
                        text="⏳ **Обновляю проект ответа с учетом ваших правок...**",
                    )
                except Exception:
                    pass

            refined_text = await self.reply_generator.refine_reply(
                original_draft=draft_info["draft_text"],
                edit_instructions=message.text.strip(),
                incoming_email_data=draft_info,
            )

            await self.db.update_email_draft(draft_id, draft_text=refined_text)
            updated_draft = await self.db.get_email_draft(draft_id)

            if updated_draft:
                reply_subject = f"Re: {updated_draft['subject']}" if not updated_draft['subject'].lower().startswith("re:") else updated_draft['subject']
                s_name = updated_draft.get("sender_name") or updated_draft.get("sender_email")
                card_text = (
                    f"💡 **Предложенный проект ответа**\n\n"
                    f"👤 **Кому:** **{s_name}** (`{updated_draft.get('sender_email')}`)\n"
                    f"📌 **Тема:** {reply_subject}\n\n"
                    f"📝 **Текст ответа:**\n"
                    f"{refined_text.strip()}"
                )
                chunks = format_and_split_for_telegram(card_text)
                if draft_msg_id and len(chunks) == 1:
                    try:
                        await self.bot.edit_message_text(
                            chat_id=message.chat.id,
                            message_id=draft_msg_id,
                            text=chunks[0][0],
                            entities=chunks[0][1],
                            reply_markup=build_draft_action_keyboard(draft_id),
                        )
                        return
                    except Exception:
                        pass

                # If couldn't edit in place, send new draft card
                sent_ids = await self.notifier.send_draft_reply_card(updated_draft, chat_id=message.chat.id)
                for sid in sent_ids:
                    self.register_message(email_id, sid)

        elif action == "write":
            manual_text = message.text.strip()
            draft_id = await self.db.create_email_draft(email_id, manual_text)
            draft_info = await self.db.get_email_draft(draft_id)

            if draft_info:
                sent_ids = await self.notifier.send_draft_reply_card(draft_info, chat_id=message.chat.id)
                for sid in sent_ids:
                    self.register_message(email_id, sid)

    async def handle_user_photo(self, message: Message) -> None:
        user_id = message.from_user.id
        if not self._is_authorized(user_id):
            return

        if not self.bot or not message.photo:
            return

        try:
            largest_photo = message.photo[-1]
            file_info = await self.bot.get_file(largest_photo.file_id)
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest_filename = f"screenshot_{timestamp_str}_{largest_photo.file_id[:8]}.jpg"
            dest_path = f"/opt/chat-app/uploads/{dest_filename}"

            await self.bot.download_file(file_info.file_path, destination=dest_path)
            logger.info("Saved incoming photo to %s", dest_path)

            caption = message.caption or ""
            status_msg = await message.answer("📸 **Скриншот получен и сохранен!** Анализирую...")

            analysis_text = ""
            if self.summarizer and self.summarizer.is_configured:
                try:
                    with open(dest_path, "rb") as f:
                        img_bytes = f.read()
                    client = self.summarizer.get_client()
                    from google.genai import types
                    resp = await client.aio.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=[
                            types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                            "Ты — персональный академический ассистент. Распознай весь ключевой текст на этом скриншоте (OCR), опиши суть и определи, есть ли здесь токен, ссылка, задача или расписание. Ответь лаконично."
                        ]
                    )
                    analysis_text = resp.text.strip() if resp and resp.text else ""
                except Exception as ve:
                    logger.warning("Gemini vision analysis failed: %s", ve)

            reply_parts = [f"📸 **Скриншот сохранен:** `{dest_filename}`"]
            if caption:
                reply_parts.append(f"💬 **Подпись:** {caption}")
            if analysis_text:
                reply_parts.append(f"\n🔍 **Распознанное содержимое:**\n{analysis_text}")

            await status_msg.edit_text("\n\n".join(reply_parts))

        except Exception as e:
            logger.exception("Error handling incoming photo: %s", e)
            await message.answer(f"⚠️ Не удалось сохранить скриншот: {e}")

    async def handle_user_document(self, message: Message) -> None:
        user_id = message.from_user.id
        if not self._is_authorized(user_id):
            return

        if not self.bot or not message.document:
            return

        try:
            doc = message.document
            file_info = await self.bot.get_file(doc.file_id)
            dest_filename = doc.file_name or f"doc_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            dest_path = f"/opt/chat-app/uploads/{dest_filename}"

            await self.bot.download_file(file_info.file_path, destination=dest_path)
            logger.info("Saved incoming document to %s", dest_path)

            caption = message.caption or ""
            msg_parts = [f"📄 **Файл сохранен:** `{dest_filename}` ({round(doc.file_size / 1024, 1) if doc.file_size else 0} KB)"]
            if caption:
                msg_parts.append(f"💬 **Подпись:** {caption}")

            # Check if this is an AADHk Time Recording SQLite backup
            fname_lower = dest_filename.lower()
            if fname_lower.endswith(".db") or "aadhk" in fname_lower or "time" in fname_lower:
                try:
                    from src.connectors.aadhk.parser import AadhkIngestionService
                    ingestion = AadhkIngestionService(self.db)
                    res = await ingestion.ingest_backup_file(dest_path)
                    if res["parsed_count"] > 0:
                        msg_parts.append("\n⏱️ **Учет времени AADHk («Тидекс») успешно импортирован:**")
                        msg_parts.append(f"• Распознано смен: **{res['parsed_count']}** (новых: {res['new_inserted_count']})")
                        msg_parts.append(f"• Суммарное время: **{res['total_hours']} ч.**")
                        if res.get("by_task"):
                            msg_parts.append("• **По задачам:**")
                            for tname, thours in res["by_task"].items():
                                msg_parts.append(f"  — {tname}: {thours} ч.")
                        if res["conflicts_count"] > 0:
                            msg_parts.append(f"\n⚠️ **Обнаружены коллизии с расписанием ГУАП:** {res['conflicts_count']} шт.")
                        else:
                            msg_parts.append("\n✔️ **Коллизий с занятиями ГУАП нет** (наложения отсутствуют).")
                except Exception as ie:
                    logger.debug("Document is not an AADHk backup or failed parsing: %s", ie)

            await message.answer("\n".join(msg_parts))

        except Exception as e:
            logger.exception("Error handling incoming document: %s", e)
            await message.answer(f"⚠️ Не удалось сохранить файл: {e}")

    async def handle_cmd_timesheet(self, message: Message) -> None:
        """Handle /timesheet, /tydex, /hours commands."""
        if not self._is_authorized(message.from_user.id):
            return

        from src.connectors.aadhk.parser import AadhkIngestionService

        service = AadhkIngestionService(self.db)
        await service.reconcile_all_conflicts()
        report = await service.get_timesheet_report(project_name="Тидекс")
        summary = report.get("summary", {})
        conflicts = report.get("conflicts", [])

        text_lines = [
            "⏱️ **Учет времени: ООО «Тидекс»**\n",
            f"• **Всего отработано:** `{summary.get('total_hours', 0.0):.2f}` ч ({summary.get('total_shifts', 0)} смен)",
            f"• **Чистые часы (без наложений):** `{summary.get('clean_hours', 0.0):.2f}` ч",
            f"• **Часов с наложениями:** `{summary.get('conflict_hours', 0.0):.2f}` ч",
            f"• **Сумма выплат:** `{summary.get('total_amount', 0.0):,.2f}` ₽\n",
        ]

        if conflicts:
            text_lines.append(f"⚠️ **Обнаруженные пересечения с парами ГУАП ({len(conflicts)}):**")
            for c in conflicts[:5]:
                st = str(c.get("start_time", ""))[:16].replace("T", " ")
                et = str(c.get("end_time", ""))[11:16]
                text_lines.append(f"• `{st} - {et}` ({c.get('duration_minutes', 0)} мин): {c.get('conflict_details', '')}")
            text_lines.append("")
        else:
            text_lines.append("✅ **Пересечений с расписанием ГУАП не обнаружено!** (100% согласовано)\n")

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Синхронизировать с Google Drive", callback_data="ts:sync_gdrive")],
            ]
        )
        msg_text = "\n".join(text_lines)
        if self.notifier:
            await self.notifier.send_message(msg_text, chat_id=message.chat.id, reply_markup=kb)
        else:
            await message.answer(msg_text, reply_markup=kb)

    async def cb_timesheet_sync(self, callback: CallbackQuery) -> None:
        """Handle inline callback to sync AADHk database directly from Google Drive."""
        if not self._is_authorized(callback.from_user.id):
            await callback.answer("Нет доступа.", show_alert=True)
            return

        await callback.answer("Синхронизация с Google Drive...")
        from src.connectors.gdrive.client import GoogleDriveClient
        from src.connectors.aadhk.parser import AadhkIngestionService

        client = GoogleDriveClient()
        if not client.is_configured:
            await callback.message.answer("❌ Google Drive не настроен или отсутствует токен.")
            return

        sync_res = await client.sync_aadhk_from_drive(self.db)
        if sync_res.get("status") != "success":
            await callback.message.answer(f"⚠️ Ошибка синхронизации: {sync_res.get('message', 'Файл не найден на Google Диске')}")
            return

        service = AadhkIngestionService(self.db)
        await service.reconcile_all_conflicts()
        summary = await self.db.get_timesheet_summary(project_name="Тидекс")
        conflicts = await self.db.get_timesheet_conflicts(limit=5)

        text_lines = [
            "🔄 **Синхронизация с Google Drive завершена!**\n",
            f"• Файл: `{sync_res.get('file_name')}`",
            f"• Новых смен добавлено: `{sync_res.get('ingestion_result', {}).get('new_inserted_count', 0)}`",
            f"• Всего отработано: `{summary.get('total_hours', 0.0):.2f}` ч",
            f"• Чистые часы: `{summary.get('clean_hours', 0.0):.2f}` ч",
            f"• Начислено: `{summary.get('total_amount', 0.0):,.2f}` ₽\n",
        ]
        if conflicts:
            text_lines.append(f"⚠️ **Наложения на пары ГУАП ({len(conflicts)}):**")
            for c in conflicts[:3]:
                st = str(c.get("start_time", ""))[:16].replace("T", " ")
                text_lines.append(f"• `{st}`: {c.get('conflict_details', '')}")
        else:
            text_lines.append("✅ Все смены согласованы без наложений на пары.")

        await callback.message.answer("\n".join(text_lines))

