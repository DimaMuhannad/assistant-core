import logging
from datetime import datetime, timezone
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
from src.sender.email_sender import EmailSender
from src.notifier.telegram import (
    TelegramNotifier,
    build_email_action_keyboard,
    build_draft_action_keyboard,
)

logger = logging.getLogger(__name__)


class EmailBotHandler:
    """Handles Telegram inline callbacks and interactive replies for incoming email workflow."""

    def __init__(
        self,
        db: Database,
        reply_generator: ReplyGenerator,
        email_sender: EmailSender,
        notifier: TelegramNotifier,
        allowed_user_id: int | str | None = None,
    ):
        self.db = db
        self.reply_generator = reply_generator
        self.email_sender = email_sender
        self.notifier = notifier
        self.allowed_user_id = int(allowed_user_id) if allowed_user_id else None

        self.router = Router()
        # In-memory FSM state: user_id -> {"action": "edit"|"write", "draft_id": int, "email_id": int}
        self.waiting_input: dict[int, dict[str, Any]] = {}

        self._register_handlers()

    def _is_authorized(self, user_id: int) -> bool:
        if self.allowed_user_id is None:
            return True
        return user_id == self.allowed_user_id

    def _register_handlers(self) -> None:
        # Commands
        self.router.message(Command("start", "help"))(self.handle_cmd_help)
        self.router.message(Command("emails", "inbox"))(self.handle_cmd_emails)

        # Callbacks under email card
        self.router.callback_query(F.data.startswith("em:sug:"))(self.cb_suggest_reply)
        self.router.callback_query(F.data.startswith("em:wr:"))(self.cb_write_reply)
        self.router.callback_query(F.data.startswith("em:th:"))(self.cb_view_thread)

        # Callbacks under draft card
        self.router.callback_query(F.data.startswith("dr:snd:"))(self.cb_send_reply)
        self.router.callback_query(F.data.startswith("dr:edt:"))(self.cb_edit_draft)
        self.router.callback_query(F.data.startswith("dr:cnc:"))(self.cb_cancel_draft)
        self.router.callback_query(F.data == "dr:cnc_input")(self.cb_cancel_input)

        # Interactive text messages (for edit or manual draft entry)
        self.router.message(F.text)(self.handle_user_text)

    async def handle_cmd_help(self, message: Message) -> None:
        if not self._is_authorized(message.from_user.id):
            return
        text = (
            "🤖 **Академический ассистент ГУАП (Кафедра физики)**\n\n"
            "Сервис 24/7 ведет мониторинг расписания, почты и рабочих чатов.\n\n"
            "Доступные команды:\n"
            "• `/emails` — показать неотвеченные письма студентов и кафедры\n"
            "• `/help` — справка по возможностям бота\n\n"
            "При поступлении новых писем бот автоматически присылает карточку с полным текстом и кнопками ответа."
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
                await self.notifier.send_actionable_email_card(full_email, chat_id=message.chat.id)

    async def cb_suggest_reply(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            await callback.answer("Доступ ограничен.", show_alert=True)
            return

        try:
            email_id = int(callback.data.split(":")[-1])
        except (ValueError, IndexError):
            await callback.answer("Неверный ID письма.")
            return

        await callback.answer("💡 Генерирую проект ответа через Gemini...")

        email_data = await self.db.get_email_by_id(email_id)
        if not email_data:
            await callback.message.answer("❌ Ошибка: письмо не найдено в базе данных.")
            return

        draft_text = await self.reply_generator.generate_reply(email_data)
        draft_id = await self.db.create_email_draft(email_id, draft_text)
        draft_info = await self.db.get_email_draft(draft_id)

        if draft_info:
            await self.notifier.send_draft_reply_card(draft_info, chat_id=callback.message.chat.id)
        else:
            await callback.message.answer("❌ Ошибка создания черновика.")

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

        await callback.answer("📤 Отправляю письмо...")

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
                draft_info["email_id"],
                reply_message_id=res.get("message_id"),
                user_email=res.get("from"),
            )

            now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
            success_text = (
                f"✅ **Ответ успешно отправлен адресату!**\n\n"
                f"👤 **Кому:** `{recipient}`\n"
                f"📌 **Тема:** {reply_subject}\n"
                f"🕒 **Время отправки:** {now_str}\n"
                f"📧 **Отправлено через:** `{res.get('from')}`\n\n"
                f"Письмо отмечено в системе как отвеченное."
            )
            # Remove inline keyboard from the draft message and append confirmation
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            await self.notifier.send_message(success_text, chat_id=callback.message.chat.id)
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

        await callback.answer("Отменено")
        try:
            await callback.message.edit_text("❌ **Создание ответа отменено.**", reply_markup=None)
        except Exception:
            await callback.message.answer("❌ **Создание ответа отменено.**")

    async def cb_edit_draft(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            return

        try:
            draft_id = int(callback.data.split(":")[-1])
        except (ValueError, IndexError):
            await callback.answer("Неверный ID.")
            return

        draft_info = await self.db.get_email_draft(draft_id)
        if not draft_info:
            await callback.answer("Черновик не найден.")
            return

        self.waiting_input[callback.from_user.id] = {
            "action": "edit",
            "draft_id": draft_id,
            "email_id": draft_info["email_id"],
        }

        await callback.answer()
        cancel_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена ввода", callback_data="dr:cnc_input")]
            ]
        )
        msg_text = (
            "✏️ **Редактирование черновика ответа**\n\n"
            "Напишите в ответ ваши правки или пожелания (например: *«Добавь, что я буду на кафедре в четверг с 12 до 15»* "
            "или просто отправьте новый полный текст ответа):"
        )
        await callback.message.answer(msg_text, reply_markup=cancel_kb)

    async def cb_write_reply(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            return

        try:
            email_id = int(callback.data.split(":")[-1])
        except (ValueError, IndexError):
            await callback.answer("Неверный ID.")
            return

        self.waiting_input[callback.from_user.id] = {
            "action": "write",
            "email_id": email_id,
        }

        await callback.answer()
        cancel_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена ввода", callback_data="dr:cnc_input")]
            ]
        )
        msg_text = (
            "✏️ **Ручной ввод ответа**\n\n"
            "Отправьте сообщением текст, который вы хотите отправить адресату в ответ:"
        )
        await callback.message.answer(msg_text, reply_markup=cancel_kb)

    async def cb_cancel_input(self, callback: CallbackQuery) -> None:
        if callback.from_user.id in self.waiting_input:
            del self.waiting_input[callback.from_user.id]
        await callback.answer("Ввод отменен.")
        try:
            await callback.message.edit_text("❌ Ввод отменен.", reply_markup=None)
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
        await self.notifier.send_message(full_thread_text, chat_id=callback.message.chat.id)

    async def handle_user_text(self, message: Message) -> None:
        user_id = message.from_user.id
        if not self._is_authorized(user_id):
            return

        state = self.waiting_input.pop(user_id, None)
        if not state:
            return  # Normal message not related to email draft workflow

        action = state.get("action")

        if action == "edit":
            draft_id = state.get("draft_id")
            draft_info = await self.db.get_email_draft(draft_id)
            if not draft_info:
                await message.answer("❌ Черновик не найден.")
                return

            status_msg = await message.answer("🔄 Обновляю черновик с учетом ваших правок...")
            refined_text = await self.reply_generator.refine_reply(
                original_draft=draft_info["draft_text"],
                edit_instructions=message.text.strip(),
                incoming_email_data=draft_info,
            )

            await self.db.update_email_draft(draft_id, draft_text=refined_text)
            updated_draft = await self.db.get_email_draft(draft_id)

            try:
                await status_msg.delete()
            except Exception:
                pass

            if updated_draft:
                await self.notifier.send_draft_reply_card(updated_draft, chat_id=message.chat.id)

        elif action == "write":
            email_id = state.get("email_id")
            email_data = await self.db.get_email_by_id(email_id)
            if not email_data:
                await message.answer("❌ Письмо не найдено.")
                return

            manual_text = message.text.strip()
            # If user didn't write standard signature, optionally format or keep clean
            draft_id = await self.db.create_email_draft(email_id, manual_text)
            draft_info = await self.db.get_email_draft(draft_id)

            if draft_info:
                await self.notifier.send_draft_reply_card(draft_info, chat_id=message.chat.id)
            else:
                await message.answer("❌ Ошибка сохранения черновика.")
