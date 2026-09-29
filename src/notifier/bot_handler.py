import asyncio
import logging
import re
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
from src.brain.secretary_dialog import SecretaryDialogEngine
from src.brain.voice import VoiceProcessor
from src.sender.email_sender import EmailSender
from src.connectors.guap_lms.client import GuapLmsClient
from src.notifier.telegram import (
    TelegramNotifier,
    build_email_action_keyboard,
    build_draft_action_keyboard,
    build_lms_tasks_keyboard,
    build_lms_pub_hide_keyboard,
    format_and_split_for_telegram,
)

logger = logging.getLogger(__name__)


class EmailBotHandler:
    """Handles Telegram inline callbacks, message cleanup, and interactive replies for email and LMS workflow."""

    def __init__(
        self,
        db: Database,
        reply_generator: ReplyGenerator | None = None,
        email_sender: EmailSender | None = None,
        notifier: TelegramNotifier | None = None,
        bot: Bot | None = None,
        allowed_user_id: int | str | None = None,
        summarizer: GeminiSummarizer | None = None,
        lms_client: GuapLmsClient | None = None,
    ):
        self.db = db
        self.reply_generator = reply_generator or ReplyGenerator()
        self.email_sender = email_sender or EmailSender()
        self.notifier = notifier
        self.allowed_user_id = int(allowed_user_id) if allowed_user_id else None
        self.lms_client = lms_client or GuapLmsClient()
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
        self.dialog_engine = SecretaryDialogEngine(db=self.db)
        self.voice_processor = VoiceProcessor()

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

        # LMS Commands
        self.router.message(Command("tasks", "lms", "labs"))(self.handle_cmd_lms_tasks)
        self.router.message(Command("reports", "submissions"))(self.handle_cmd_lms_reports)
        self.router.message(Command("lms_publish"))(self.handle_cmd_lms_publish)
        self.router.message(Command("lms_hide"))(self.handle_cmd_lms_hide)
        self.router.message(Command("lms_create"))(self.handle_cmd_lms_create)
        self.router.message(Command("lms_delete"))(self.handle_cmd_lms_delete)

        # Methodist Commands
        self.router.message(Command("methodist", "gost", "rpd"))(self.handle_cmd_methodist)
        self.router.message(Command("methodist_teach"))(self.handle_cmd_methodist_teach)
        self.router.message(Command("methodist_stats"))(self.handle_cmd_methodist_stats)
        self.router.message(Command("methodist_books"))(self.handle_cmd_methodist_books)
        self.router.message(Command("methodist_toc"))(self.handle_cmd_methodist_toc)
        self.router.message(Command("methodist_reindex"))(self.handle_cmd_methodist_reindex)

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

        # Callbacks under LMS tasks
        self.router.callback_query(F.data == "lms:pub_menu")(self.cb_lms_pub_menu)
        self.router.callback_query(F.data.startswith("lms:pub:"))(self.cb_lms_pub_action)
        self.router.callback_query(F.data == "lms:hide_menu")(self.cb_lms_hide_menu)
        self.router.callback_query(F.data.startswith("lms:hide:"))(self.cb_lms_hide_action)
        self.router.callback_query(F.data == "lms:reports")(self.cb_lms_reports)
        self.router.callback_query(F.data == "lms:refresh")(self.cb_lms_refresh)
        self.router.callback_query(F.data == "lms:del_prompt")(self.cb_lms_del_prompt)
        self.router.callback_query(F.data.startswith("lms:del_confirm:"))(self.cb_lms_del_confirm)
        self.router.callback_query(F.data == "lms:create_menu")(self.cb_lms_create_menu)

        # Interactive text messages (for edit, commands, or conversational secretary)
        self.router.message(Command("clear", "reset"))(self.handle_cmd_clear_dialog)
        self.router.message(F.text)(self.handle_user_text)

        # Voice messages (audio transcription and conversational secretary)
        self.router.message(F.voice)(self.handle_user_voice)

        # Photos and screenshots
        self.router.message(F.photo)(self.handle_user_photo)

        # Documents (files, images, txt, pdf)
        self.router.message(F.document)(self.handle_user_document)

    async def handle_cmd_help(self, message: Message) -> None:
        if not self._is_authorized(message.from_user.id):
            return
        text = (
            "🤖 **Персональный секретарь и ассистент ГУАП (Кафедра физики)**\n\n"
            "Сервис 24/7 ведет мониторинг расписания, почты, задач и личного кабинета pro.guap.ru.\n\n"
            "💬 **Диалог в свободной форме:**\n"
            "Вы можете писать или отправлять **голосовые сообщения** с любыми вопросами (расписание, аудитории, баланс часов в «Тидекс», письма, отчеты в LMS, ГОСТы, учебники, эффективный контракт).\n\n"
            "Доступные команды:\n"
            "• `/clear` — сбросить контекст диалога с секретарем\n"
            "• `/tasks` — управление заданиями pro.guap.ru (публикация, скрытие, создание, удаление)\n"
            "• `/reports` — сданные студенческие отчеты, ожидающие проверки\n"
            "• `/lms_publish <№|id>` — опубликовать лабораторную работу для всех групп (или по ID)\n"
            "• `/lms_hide <№|id>` — скрыть лабораторную работу от студентов\n"
            "• `/lms_create <группа> <название>` — создать новое задание\n"
            "• `/lms_delete <id>` — удалить задание по ID\n"
            "• `/emails` — показать неотвеченные письма студентов и кафедры\n"
            "• `/methodist <вопрос>` — консультация с агентом-методистом (учебники Коваленко, задачники, лабы, ГОСТы)\n"
            "• `/methodist_books` — каталог учебников Коваленко, задачников и практикумов\n"
            "• `/methodist_toc <id>` — оглавление учебного пособия с номерами страниц\n"
            "• `/methodist_teach <тема> | <текст>` — дообучение методиста новым правилам кафедры\n"
            "• `/methodist_stats` — статистика базы знаний и разделов\n"
            "• `/timesheet` — табель и пейсинг выработки нормы в «Тидекс»\n"
            "• `/evening` — вечерний дайджест со статистикой обработки писем\n"
            "• `/help` — справка по возможностям бота"
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
            user_msg = message.text.strip().lower()
            if user_msg in ("задания", "список заданий", "покажи задания", "пары", "лабы", "лабораторные"):
                await self.handle_cmd_lms_tasks(message)
                return
            if user_msg in ("отчеты", "проверь отчеты", "сданные отчеты", "работы", "сданные работы"):
                await self.handle_cmd_lms_reports(message)
                return
            m_pub = re.match(r"^опубликуй\s*(?:лаб(?:ораторн(?:ую|ые))?)?\s*(?:№\s*)?(\d+|все)", user_msg)
            if m_pub:
                target = m_pub.group(1)
                target_code = "all" if target == "все" else target
                await self._execute_visibility_change(message, target_code, is_public=True)
                return
            m_hide = re.match(r"^скрой\s*(?:лаб(?:ораторн(?:ую|ые))?)?\s*(?:№\s*)?(\d+|все)", user_msg)
            if m_hide:
                target = m_hide.group(1)
                target_code = "all" if target == "все" else target
                await self._execute_visibility_change(message, target_code, is_public=False)
                return
            if any(k in user_msg for k in ("смен", "табел", "тидекс", "часы", "часов", "выработк", "обнови данные")):
                await self.handle_cmd_timesheet(message)
                return
            if user_msg.startswith(("@методист", "методист,", "методист ")) or any(k in user_msg for k in ("по госту", "титульн", "погрешност", "по брс", "правило оформления отчета")):
                clean_q = re.sub(r"^@?методист[:,]?\s*", "", message.text.strip(), flags=re.IGNORECASE)
                if clean_q:
                    await self._handle_methodist_query(message, clean_q)
                    return

            # Conversational dialogue with Secretary Assistant
            await self._handle_secretary_dialog(message, message.text.strip())
            return

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

        if action == "lms_create":
            parts = message.text.strip().split(maxsplit=1)
            if len(parts) < 2:
                await message.answer("⚠️ Неверный формат. Укажите группу и название, например:\n`1632 Попов: Лабораторная работа №5`")
                return
            await self._create_task_from_params(message.chat.id, parts[0], parts[1])
            return

        if action == "lms_delete":
            m = re.search(r"\d+", message.text)
            if not m:
                await message.answer("⚠️ Не удалось распознать ID задания. Отправьте числовой ID (например `3422`):")
                return
            task_id = int(m.group(0))
            confirm_kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text=f"🗑️ Да, удалить {task_id}", callback_data=f"lms:del_confirm:{task_id}"),
                        InlineKeyboardButton(text="❌ Отмена", callback_data="dr:cnc_input"),
                    ]
                ]
            )
            await message.answer(
                f"⚠️ **Вы действительно хотите удалить задание `{task_id}` с pro.guap.ru?**\n"
                f"Это действие необратимо.",
                reply_markup=confirm_kb,
            )
            return

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

            # Check if this document is directed to Methodist Agent
            c_lower = caption.lower()
            if any(t in c_lower for t in ("#методист", "#рпд", "#гост", "#методичка", "методист")):
                try:
                    from src.brain.methodist import MethodistService
                    ms = MethodistService(self.db)
                    ing_res = await ms.ingest_file(dest_path)
                    msg_parts.append("\n🎓 **Документ добавлен в базу знаний методиста:**")
                    msg_parts.append(f"• Документ: `{ing_res['title']}`")
                    msg_parts.append(f"• Категория: `{ing_res['category']}`")
                    msg_parts.append(f"• Проиндексировано чанков в FTS5: **{ing_res['chunks_count']}**")
                except Exception as me:
                    logger.debug("Failed adding doc to methodist: %s", me)

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
        pacing = await service.get_monthly_pacing(project_name="Тидекс")

        month_names = ["", "январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
        cur_m_name = month_names[pacing["month"]].capitalize()
        delta_sign = "+" if pacing["delta_pacing"] >= 0 else ""

        text_lines = [
            f"⏱️ **Табель и баланс: ООО «Тидекс» ({cur_m_name} {pacing['year']})**\n",
            f"• **Месячная норма:** `{pacing['monthly_norm_hours']:.1f}` ч ({pacing['total_workdays']} раб. дней по 8.5 ч)",
            f"• **Фактически зачтено:** `{pacing['worked_hours']:.2f}` ч ({pacing['total_shifts']} дней/смен)",
            f"• **Ожидаемый темп на сегодня:** `{pacing['expected_hours_to_date']:.1f}` ч ({pacing['elapsed_workdays']} дней)",
            f"• **Текущий баланс нормы (ΔH):** `{delta_sign}{pacing['delta_pacing']:.2f}` ч",
            f"• **Начислено за месяц:** `{pacing['total_amount']:,.2f}` ₽\n",
        ]

        if pacing["remaining_workdays"] > 0:
            text_lines.append(f"🎯 **План на остаток месяца ({pacing['remaining_workdays']} раб. дн.):**")
            text_lines.append(f"• Осталось закрыть: `{pacing['remaining_hours_to_norm']:.2f}` ч")
            text_lines.append(f"• Необходимый темп: `{pacing['required_daily_pacing']:.2f}` ч/день\n")
        else:
            if pacing["remaining_hours_to_norm"] == 0:
                text_lines.append("🎉 **Месячная норма полностью выполнена без недоработок!**\n")
            else:
                text_lines.append(f"⚠️ **Недоработка за месяц:** `{pacing['remaining_hours_to_norm']:.2f}` ч\n")

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

    # -------------------------------------------------------------
    # Methodist Agent Handlers (Educational Regulations, GOSTs, RPD)
    # -------------------------------------------------------------

    async def handle_cmd_methodist(self, message: Message) -> None:
        """Handle /methodist, /gost, /rpd commands."""
        parts = message.text.strip().split(maxsplit=1)
        query = parts[1].strip() if len(parts) > 1 else ""
        if not query:
            text = (
                "🎓 **Агент-методист кафедры физики ГУАП (Кафедра №1)**\n\n"
                "Я специализируюсь на регламентах учебного процесса, РПД, ГОСТах оформления отчетов и БРС.\n\n"
                "Примеры запросов:\n"
                "• `/methodist какие поля и шрифт по ГОСТу для отчета?`\n"
                "• `/methodist что обязательно должно быть на второй странице отчета?`\n"
                "• `/methodist сколько баллов по БРС нужно для допуска к экзамену?`\n"
                "• `/methodist как оформить титульный лист лабораторной?`\n\n"
                "💡 *Вы также можете просто спросить меня в чате:* `@методист <вопрос>` или `Методист, ...`"
            )
            await message.answer(text)
            return

        await self._handle_methodist_query(message, query)

    async def _handle_methodist_query(self, message: Message, query: str) -> None:
        """Query MethodistService and return authoritative answer with citations."""
        from src.brain.methodist import MethodistService
        service = MethodistService(self.db)
        status_msg = await message.answer("🔍 *Методист кафедры сверяет оглавления пособий, формулы и ГОСТы...*")
        res = await service.ask(query, caller="tg_user", caller_id=str(message.from_user.id))
        try:
            await status_msg.delete()
        except Exception:
            pass

        answer = res.get("answer", "")
        sources = res.get("sources", [])
        src_text = ""
        if sources:
            src_items = []
            for s in sources:
                d_title = s.get("doc_title", "")
                sec = s.get("section", "")
                pages = s.get("pages")
                if pages:
                    src_items.append(f"• _{d_title}_ [{sec}] (стр. {pages})")
                elif sec:
                    src_items.append(f"• _{d_title}_ [{sec}]")
                elif d_title:
                    src_items.append(f"• _{d_title}_")

            if src_items:
                unique_src = list(dict.fromkeys(src_items))
                src_text = "\n\n📚 **Использованные первоисточники (выгрузка страниц):**\n" + "\n".join(unique_src[:4])

        await message.answer(f"🎓 **Методист кафедры физики:**\n\n{answer}{src_text}")

    async def handle_cmd_clear_dialog(self, message: Message) -> None:
        """Handle /clear or /reset to wipe conversational memory."""
        if not self._is_authorized(message.from_user.id):
            return
        await self.db.clear_dialog_history(message.from_user.id)
        text = "🧹 **Память диалога успешно очищена.** Я готов к новым вопросам!"
        if self.notifier:
            await self.notifier.send_message(text, chat_id=message.chat.id)
        else:
            await message.answer(text)

    async def _handle_secretary_dialog(self, message: Message, text: str) -> None:
        """Handle conversational queries to Dmitry Popov's personal secretary."""
        try:
            await self.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        except Exception:
            pass

        answer = await self.dialog_engine.answer_user_message(
            user_id=message.from_user.id,
            message_text=text,
        )

        if self.notifier:
            await self.notifier.send_message(answer, chat_id=message.chat.id)
        else:
            await message.answer(answer)

    async def handle_user_voice(self, message: Message) -> None:
        """Handle voice messages: transcribe audio and process via conversational secretary."""
        if not self._is_authorized(message.from_user.id):
            return

        try:
            await self.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        except Exception:
            pass

        import io
        try:
            voice_file = await self.bot.get_file(message.voice.file_id)
            voice_bytes_io = io.BytesIO()
            await self.bot.download_file(voice_file.file_path, destination=voice_bytes_io)
            voice_bytes = voice_bytes_io.getvalue()

            voice_res = await self.voice_processor.transcribe(
                voice_bytes,
                duration_seconds=message.voice.duration,
            )

            if not voice_res.success or not voice_res.transcription:
                await message.answer("⚠️ Не удалось распознать голосовое сообщение. Попробуйте написать текстом.")
                return

            recognized_text = voice_res.transcription.strip()
            # Send preview of transcription
            await message.answer(f"🎙️ *«{recognized_text}»*")

            # Route to conversational secretary
            await self._handle_secretary_dialog(message, recognized_text)
        except Exception as e:
            logger.exception("Error processing voice message: %s", e)
            await message.answer(f"⚠️ Ошибка обработки голосового сообщения ({e}).")

    async def handle_cmd_methodist_books(self, message: Message) -> None:
        """Display list of indexed textbooks and lab manuals with TOC stats."""
        from src.brain.methodist import MethodistService
        service = MethodistService(self.db)
        stats = await service.get_stats()
        books = stats.get("books", [])
        if not books:
            await message.answer("📚 Учебные пособия с оглавлениями пока не проиндексированы.")
            return

        lines = ["📚 **Учебные издания кафедры физики (проиндексированные оглавления):**\n"]
        for b in books:
            lines.append(f"• `ID {b['id']}` **{b['title']}**\n  Категория: `{b['category']}` | Разделов: **{b['toc_count']}** | Стр. {b['pages']}")

        lines.append("\n💡 *Для просмотра оглавления пособия используйте:* `/methodist_toc <ID>`")
        await message.answer("\n".join(lines))

    async def handle_cmd_methodist_toc(self, message: Message) -> None:
        """Display Table of Contents for a specific book ID."""
        parts = message.text.strip().split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            await message.answer("⚠️ Укажите числовой ID книги из каталога. Пример: `/methodist_toc 25`\nСписок доступных книг: `/methodist_books`")
            return

        doc_id = int(parts[1].strip())
        from src.brain.methodist import MethodistService
        service = MethodistService(self.db)
        toc = await service.get_book_toc(doc_id)
        if not toc:
            await message.answer(f"Пособие с ID {doc_id} не найдено или в нем нет оглавления.")
            return

        book_title = toc[0].get("book_title", f"Книга {doc_id}")
        lines = [f"📖 **Оглавление пособия:**\n*{book_title}*\n"]
        for item in toc[:35]:
            ch_num = f"{item['chapter_number']}. " if item.get("chapter_number") else ""
            lines.append(f"• `[стр. {item['page_start']}-{item['page_end']}]` {ch_num}{item['chapter_title']}")

        if len(toc) > 35:
            lines.append(f"\n_...и еще {len(toc) - 35} разделов_")

        await message.answer("\n".join(lines))

    async def handle_cmd_methodist_reindex(self, message: Message) -> None:
        """Trigger reindexing of all materials in data/methodist/raw/."""
        if not self._is_authorized(message.from_user.id):
            return
        status_msg = await message.answer("🔄 *Запущен режим дообучения: сканирование и индексация пособий ГУАП...*")
        from src.brain.methodist import MethodistService
        service = MethodistService(self.db)
        report = await service.reindex_all_materials()
        try:
            await status_msg.delete()
        except Exception:
            pass
        await message.answer(
            f"✅ **Индексация завершена успешно!**\n\n"
            f"• Всего обработано файлов: **{report.get('total_processed', 0)}**\n"
            f"• Просмотреть статистику: `/methodist_stats`\n"
            f"• Каталог изданий: `/methodist_books`"
        )

    async def handle_cmd_methodist_teach(self, message: Message) -> None:
        """Handle /methodist_teach command to teach the agent a new rule."""
        if not self._is_authorized(message.from_user.id):
            return
        parts = message.text.strip().split(maxsplit=1)
        if len(parts) < 2 or "|" not in parts[1]:
            await message.answer(
                "⚠️ Формат дообучения методиста:\n"
                "`/methodist_teach Заголовок правила | Текст регламента или указания`\n\n"
                "Пример:\n"
                "`/methodist_teach Правило допуска к лабе 3 | Для допуска студент обязан предоставить решенные задачи 1-3`"
            )
            return
        title, content = parts[1].split("|", 1)
        from src.brain.methodist import MethodistService
        service = MethodistService(self.db)
        res = await service.teach_guideline(title.strip(), content.strip())
        await message.answer(
            f"✅ **Правило успешно усвоено методистом!**\n\n"
            f"• Заголовок: `{title.strip()}`\n"
            f"• Файл: `{res.get('file_path')}`\n"
            f"• Проиндексировано чанков в FTS5: **{res.get('ingest_result', {}).get('chunks_count', 0)}**"
        )

    async def handle_cmd_methodist_stats(self, message: Message) -> None:
        """Display indexed Methodist knowledge base statistics."""
        from src.brain.methodist import MethodistService
        service = MethodistService(self.db)
        stats = await service.get_stats()
        text_lines = [
            "🎓 **База знаний агента-методиста кафедры физики:**\n",
            f"• Всего документов: **{stats.get('total_documents', 0)}**",
            f"• Проиндексированных разделов/глав: **{stats.get('total_toc_entries', 0)}**",
        ]
        by_cat = stats.get("by_category", {})
        for cat, cnt in by_cat.items():
            text_lines.append(f"  — `{cat}`: {cnt} документов")
        text_lines.append("\n📚 **Каталог пособий и оглавлений:** `/methodist_books`")
        text_lines.append("📖 **Просмотр оглавления книги:** `/methodist_toc <ID>`")
        await message.answer("\n".join(text_lines))

    # -------------------------------------------------------------
    # LMS (pro.guap.ru) Management & Monitoring Methods
    # -------------------------------------------------------------

    def _format_lms_tasks_overview(self, tasks: list[dict[str, Any]]) -> str:
        """Format an overview of LMS lab assignments grouped by study group."""
        if not tasks:
            return "📋 **Задания pro.guap.ru:**\n\nЗаданий на текущий семестр не найдено."

        total_count = len(tasks)
        public_count = sum(1 for t in tasks if t.get("is_public"))
        hidden_count = total_count - public_count

        lines = [
            "📋 **Задания кафедры физики (pro.guap.ru)**\n",
            f"• Всего заданий в ЛК: **{total_count}**",
            f"• Опубликовано (видно студентам): **{public_count}** 👁️",
            f"• Скрыто (в черновиках): **{hidden_count}** 🔒\n",
            "**Статус по группам:**",
        ]

        by_group: dict[str, list[dict[str, Any]]] = {}
        for t in tasks:
            subj_group = t.get("subject", "Общие")
            grp_match = re.search(r"\b([МM]?\d{3,4}[А-Яа-яA-Za-z]*)\b", subj_group)
            grp_name = grp_match.group(1) if grp_match else subj_group[:15]
            by_group.setdefault(grp_name, []).append(t)

        for grp, grp_tasks in sorted(by_group.items()):
            task_status_parts = []
            grp_tasks_sorted = sorted(grp_tasks, key=lambda x: str(x.get("title", "")))
            for gt in grp_tasks_sorted:
                t_title = gt.get("title", "")
                lab_m = re.search(r"№\s*(\d+)|Лабораторная\s+работа\s*№?\s*(\d+)", t_title, re.I)
                num = lab_m.group(1) or lab_m.group(2) if lab_m else gt.get("ordernum", "?")
                icon = "👁️" if gt.get("is_public") else "🔒"
                task_status_parts.append(f"{icon} №{num} (`{gt.get('id')}`)")
            lines.append(f"• **Гр. {grp}:** " + ", ".join(task_status_parts))

        lines.append("\n💡 *Используйте кнопки ниже для управления видимостью, создания/удаления или проверки отчетов.*")
        return "\n".join(lines)

    async def _execute_visibility_change(
        self,
        message_or_query: Message | CallbackQuery,
        target_code: str,
        is_public: bool,
    ) -> None:
        """Executes publishing or hiding lab assignments on pro.guap.ru."""
        action_verb = "Публикую" if is_public else "Скрываю"
        past_verb = "опубликовано" if is_public else "скрыто"
        icon = "👁️" if is_public else "🔒"

        is_cb = isinstance(message_or_query, CallbackQuery)
        if is_cb:
            await message_or_query.answer(f"{action_verb}...")
            send_target = message_or_query.message
        else:
            send_target = message_or_query

        status_msg = await send_target.answer(f"⏳ {action_verb} задания на pro.guap.ru (цель: `{target_code}`)...")

        try:
            tasks = await asyncio.to_thread(self.lms_client.list_tasks, 28)
            popov_tasks = [t for t in tasks if "попов" in t.get("title", "").lower()]
            active_tasks = popov_tasks if popov_tasks else tasks

            if target_code == "all":
                target_tasks = active_tasks
            elif target_code.isdigit() and len(target_code) <= 2:
                target_tasks = [
                    t for t in active_tasks
                    if f"№{target_code}" in t.get("title", "") or f"№ {target_code}" in t.get("title", "")
                ]
            else:
                target_tasks = [t for t in tasks if str(t.get("id")) == str(target_code)]

            if not target_tasks:
                await status_msg.edit_text(f"⚠️ Не найдены задания, соответствующие критерию `{target_code}`.")
                return

            updated_count = 0
            already_count = 0
            for t in target_tasks:
                if t.get("is_public") == is_public:
                    already_count += 1
                    continue
                ok = await asyncio.to_thread(self.lms_client.set_task_visibility, t["id"], is_public)
                if ok:
                    updated_count += 1

            result_lines = [
                f"{icon} **Результат изменения видимости:**\n",
                f"• Обновлено заданий: **{updated_count}** (статус: {past_verb})",
            ]
            if already_count > 0:
                result_lines.append(f"• Уже находились в этом статусе: **{already_count}**")
            result_lines.append(f"• Всего проверено заданий: **{len(target_tasks)}**")

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📋 К списку заданий", callback_data="lms:refresh")]
                ]
            )
            await status_msg.edit_text("\n".join(result_lines), reply_markup=kb)

        except Exception as e:
            logger.exception("Error changing visibility: %s", e)
            await status_msg.edit_text(f"⚠️ Ошибка при изменении видимости: {e}")

    async def _create_task_from_params(self, chat_id: int, group_name: str, task_title: str) -> None:
        """Helper to create a task given group name and title."""
        status_msg = await self.bot.send_message(chat_id, f"⏳ Создаю задание `{task_title}` для гр. `{group_name}`...")
        try:
            disciplines = await asyncio.to_thread(self.lms_client.get_disciplines)
            matched_subj_id = None
            matched_group_id = None
            for disc in disciplines:
                if disc.get("semester") != 28:
                    continue
                for g in disc.get("groups", []):
                    if g.get("text", "").strip().lower() == group_name.strip().lower():
                        matched_subj_id = disc.get("id")
                        matched_group_id = g.get("id")
                        break
                if matched_subj_id:
                    break

            if not matched_subj_id or not matched_group_id:
                await status_msg.edit_text(
                    f"⚠️ Группа `{group_name}` не найдена среди ваших дисциплин на 28 семестр.\n"
                    f"Доступные группы: 1632, 1538, 8626, М562, М553, М431К, М651Ксв, М531, М631К."
                )
                return

            res = await asyncio.to_thread(
                self.lms_client.create_task,
                name=task_title,
                subject_id=matched_subj_id,
                group_ids=[matched_group_id],
                semester_id=28,
                is_public=False,
            )
            created_id = res.get("created_id")
            if res.get("status") == "success" and created_id:
                await status_msg.edit_text(
                    f"✅ **Задание успешно создано!**\n\n"
                    f"• ID: `{created_id}`\n"
                    f"• Название: **{task_title}**\n"
                    f"• Группа: **{group_name}**\n"
                    f"• Статус: 🔒 Скрыто (черновик)\n\n"
                    f"🔗 [Открыть в ЛК](https://pro.guap.ru/inside/professor/tasks/{created_id}/show)"
                )
            else:
                await status_msg.edit_text(f"⚠️ Не удалось создать задание: статус {res.get('status_code')}")
        except Exception as e:
            logger.exception("Error creating LMS task: %s", e)
            await status_msg.edit_text(f"⚠️ Ошибка создания задания: {e}")

    async def handle_cmd_lms_tasks(self, message: Message) -> None:
        """Handle /tasks command."""
        if not self._is_authorized(message.from_user.id):
            return

        status_msg = await message.answer("⏳ Загружаю список заданий из pro.guap.ru...")
        try:
            tasks = await asyncio.to_thread(self.lms_client.list_tasks, 28)
            popov_tasks = [t for t in tasks if "попов" in t.get("title", "").lower()]
            display_tasks = popov_tasks if popov_tasks else tasks

            overview = self._format_lms_tasks_overview(display_tasks)
            kb = build_lms_tasks_keyboard()
            await status_msg.edit_text(overview, reply_markup=kb)
        except Exception as e:
            logger.exception("Error listing LMS tasks: %s", e)
            await status_msg.edit_text(f"⚠️ Ошибка при загрузке заданий: {e}")

    async def handle_cmd_lms_reports(self, message: Message) -> None:
        """Handle /reports command."""
        if not self._is_authorized(message.from_user.id):
            return

        status_msg = await message.answer("🔍 Проверяю сданные отчеты на pro.guap.ru...")
        try:
            submissions = await self.db.list_lms_submissions(limit=25)
            if not submissions:
                tasks = await asyncio.to_thread(self.lms_client.list_tasks, 28)
                public_tasks = [t for t in tasks if t.get("is_public")]
                for pt in public_tasks:
                    details = await asyncio.to_thread(self.lms_client.get_task_details, pt["id"])
                    for rep in details.get("reports", []):
                        if rep.get("report_id"):
                            await self.db.record_lms_submission(
                                report_id=rep["report_id"],
                                task_id=pt["id"],
                                task_title=pt["title"],
                                student_name=rep["student_name"],
                                group_name=rep["group"],
                                status=rep["status"],
                                upload_date=rep.get("upload_date", ""),
                                check_date=rep.get("check_date", ""),
                                download_url=rep.get("download_url", ""),
                            )
                submissions = await self.db.list_lms_submissions(limit=25)

            if not submissions:
                await status_msg.edit_text(
                    "📥 **Сданных студенческих отчетов пока нет.**\n\n"
                    "Как только студенты загрузят первые работы, бот мгновенно уведомит вас в чате."
                )
                return

            lines = [f"📥 **Сданные студенческие отчеты ({len(submissions)}):**\n"]
            for s in submissions:
                st_icon = "⏳" if "ожидает" in s.get("status", "").lower() or not s.get("check_date") else "✅"
                lines.append(
                    f"{st_icon} **{s['student_name']}** (гр. {s['group_name']})\n"
                    f"  📌 {s['task_title']}\n"
                    f"  📅 Сдано: {s.get('upload_date', '—')} | Статус: `{s['status']}`\n"
                    f"  🔗 [Открыть в ЛК](https://pro.guap.ru/inside/professor/tasks/{s['task_id']}/show)\n"
                )
            await status_msg.edit_text("\n".join(lines))
        except Exception as e:
            logger.exception("Error checking reports: %s", e)
            await status_msg.edit_text(f"⚠️ Ошибка при проверке отчетов: {e}")

    async def handle_cmd_lms_publish(self, message: Message) -> None:
        """Handle /lms_publish command."""
        if not self._is_authorized(message.from_user.id):
            return
        args = message.text.removeprefix("/lms_publish").strip().lower()
        if not args:
            kb = build_lms_pub_hide_keyboard("lms:pub:")
            await message.answer("👁️ **Выберите, какие лабораторные работы опубликовать:**", reply_markup=kb)
            return
        target = "all" if args in ("all", "все") else args
        await self._execute_visibility_change(message, target, is_public=True)

    async def handle_cmd_lms_hide(self, message: Message) -> None:
        """Handle /lms_hide command."""
        if not self._is_authorized(message.from_user.id):
            return
        args = message.text.removeprefix("/lms_hide").strip().lower()
        if not args:
            kb = build_lms_pub_hide_keyboard("lms:hide:")
            await message.answer("🔒 **Выберите, какие лабораторные работы скрыть (в черновик):**", reply_markup=kb)
            return
        target = "all" if args in ("all", "все") else args
        await self._execute_visibility_change(message, target, is_public=False)

    async def handle_cmd_lms_create(self, message: Message) -> None:
        """Handle /lms_create command."""
        if not self._is_authorized(message.from_user.id):
            return
        args_text = message.text.removeprefix("/lms_create").strip()
        if not args_text:
            cancel_kb = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="dr:cnc_input")]]
            )
            prompt_msg = await message.answer(
                "➕ **Создание нового задания на pro.guap.ru**\n\n"
                "Отправьте в чат сообщение в формате:\n"
                "`<номер группы> <название задания>`\n\n"
                "Пример:\n"
                "`1632 Попов: Лабораторная работа №5`\n\n"
                "_Задание будет создано как черновик (скрыто от студентов)._",
                reply_markup=cancel_kb,
            )
            self.waiting_input[message.from_user.id] = {
                "action": "lms_create",
                "prompt_msg_id": prompt_msg.message_id,
            }
            return

        parts = args_text.split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("⚠️ Укажите группу и название задания, например:\n`/lms_create 1632 Попов: Лабораторная работа №5`")
            return
        await self._create_task_from_params(message.chat.id, parts[0], parts[1])

    async def handle_cmd_lms_delete(self, message: Message) -> None:
        """Handle /lms_delete command."""
        if not self._is_authorized(message.from_user.id):
            return
        args_text = message.text.removeprefix("/lms_delete").strip()
        m = re.search(r"\d+", args_text)
        if not m:
            cancel_kb = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="dr:cnc_input")]]
            )
            prompt_msg = await message.answer(
                "🗑️ Введите ID задания для удаления (например, `3422`):",
                reply_markup=cancel_kb,
            )
            self.waiting_input[message.from_user.id] = {
                "action": "lms_delete",
                "prompt_msg_id": prompt_msg.message_id,
            }
            return

        task_id = int(m.group(0))
        confirm_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=f"🗑️ Да, удалить {task_id}", callback_data=f"lms:del_confirm:{task_id}"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="dr:cnc_input"),
                ]
            ]
        )
        await message.answer(
            f"⚠️ **Вы действительно хотите удалить задание `{task_id}` с pro.guap.ru?**\n"
            f"Это действие необратимо.",
            reply_markup=confirm_kb,
        )

    async def cb_lms_pub_menu(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            return
        await callback.answer()
        kb = build_lms_pub_hide_keyboard("lms:pub:")
        await callback.message.edit_text(
            "👁️ **Выберите, какие лабораторные работы опубликовать для студентов:**",
            reply_markup=kb,
        )

    async def cb_lms_pub_action(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            return
        target = callback.data.split(":")[-1]
        await self._execute_visibility_change(callback, target, is_public=True)

    async def cb_lms_hide_menu(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            return
        await callback.answer()
        kb = build_lms_pub_hide_keyboard("lms:hide:")
        await callback.message.edit_text(
            "🔒 **Выберите, какие лабораторные работы скрыть от студентов (черновик):**",
            reply_markup=kb,
        )

    async def cb_lms_hide_action(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            return
        target = callback.data.split(":")[-1]
        await self._execute_visibility_change(callback, target, is_public=False)

    async def cb_lms_reports(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            return
        await callback.answer("Загружаю отчеты...")
        await self.handle_cmd_lms_reports(callback.message)

    async def cb_lms_refresh(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            return
        await callback.answer("Обновляю список...")
        try:
            tasks = await asyncio.to_thread(self.lms_client.list_tasks, 28)
            popov_tasks = [t for t in tasks if "попов" in t.get("title", "").lower()]
            display_tasks = popov_tasks if popov_tasks else tasks
            overview = self._format_lms_tasks_overview(display_tasks)
            kb = build_lms_tasks_keyboard()
            await callback.message.edit_text(overview, reply_markup=kb)
        except Exception as e:
            await callback.message.answer(f"⚠️ Ошибка обновления: {e}")

    async def cb_lms_del_prompt(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            return
        await callback.answer()
        cancel_kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="dr:cnc_input")]]
        )
        prompt_msg = await callback.message.answer(
            "🗑️ **Удаление задания:**\n\nОтправьте в чат **ID задания** (или команду `/lms_delete <id>`), которое нужно удалить:",
            reply_markup=cancel_kb,
        )
        self.waiting_input[callback.from_user.id] = {
            "action": "lms_delete",
            "prompt_msg_id": prompt_msg.message_id,
        }

    async def cb_lms_del_confirm(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            return
        try:
            task_id = int(callback.data.split(":")[-1])
        except (ValueError, IndexError):
            await callback.answer("Неверный ID задания.")
            return

        await callback.answer("Удаляю задание...")
        try:
            ok = await asyncio.to_thread(self.lms_client.delete_task, task_id)
            if ok:
                await callback.message.edit_text(f"✅ Задание `{task_id}` успешно удалено из pro.guap.ru!")
            else:
                await callback.message.edit_text(f"⚠️ Не удалось удалить задание `{task_id}` (проверьте права или наличие в ЛК).")
        except Exception as e:
            logger.exception("Error deleting task %s: %s", task_id, e)
            await callback.message.edit_text(f"⚠️ Ошибка при удалении задания: {e}")

    async def cb_lms_create_menu(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            return
        await callback.answer()
        cancel_kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="dr:cnc_input")]]
        )
        prompt_msg = await callback.message.answer(
            "➕ **Создание нового задания на pro.guap.ru**\n\n"
            "Отправьте в чат сообщение в формате:\n"
            "`<номер группы> <название задания>`\n\n"
            "Пример:\n"
            "`1632 Попов: Лабораторная работа №5`\n\n"
            "_Задание будет создано как черновик (скрыто от студентов)._",
            reply_markup=cancel_kb,
        )
        self.waiting_input[callback.from_user.id] = {
            "action": "lms_create",
            "prompt_msg_id": prompt_msg.message_id,
        }


