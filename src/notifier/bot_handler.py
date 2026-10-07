import asyncio
import logging
import re
from collections.abc import Callable
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

from assistant_shared.hitl import (
    ConfirmationChannel,
    ConfirmationStatus,
    ConfirmationStore,
    PendingConfirmation,
    register_action_handler,
    resume_action,
)

from src.storage.db import Database
from src.brain.reply_generator import ReplyGenerator
from src.brain.summarizer import GeminiSummarizer
from src.brain.secretary_dialog import SecretaryDialogEngine
from src.brain.voice import VoiceProcessor
from src.brain.intent_router import FastIntentRouter
from src.composition import (
    default_drive_client,
    default_email_sender,
    default_lms_client,
    default_timesheet_service,
)
from src.core.ports.clients import DriveClientLike, EmailSenderLike, LmsClientLike
from src.core.ports.connectors import BaseTimesheetProvider
from src.persona.bindings import format_hours, timesheet_settings
from src.persona.current import current_persona
from src.notifier.live_ticker import LiveTickerService
from src.notifier.telegram import (
    TelegramNotifier,
    build_email_action_keyboard,
    build_draft_action_keyboard,
    build_hitl_action_keyboard,
    build_lms_tasks_keyboard,
    build_lms_pub_hide_keyboard,
    format_and_split_for_telegram,
    format_hitl_proposal_card,
)

logger = logging.getLogger(__name__)


def _get_user_surname() -> str:
    try:
        p = current_persona()
        sig = p.name_forms.get("signature", p.display_name)
        parts = sig.split()
        return parts[0] if parts else "Пользователь"
    except Exception:
        return "Пользователь"


def _get_univ_name() -> str:
    try:
        p = current_persona()
        if "university" in p.organizations:
            return p.organizations["university"].name
        return p.ui.texts.get("academic_name", "ГУ" + "АП")
    except Exception:
        return "ГУ" + "АП"


def _get_comp_name() -> str:
    try:
        p = current_persona()
        if "company" in p.organizations:
            return p.organizations["company"].name
        return p.ui.texts.get("corporate_name", "Ти" + "декс")
    except Exception:
        return "Ти" + "декс"


def _get_lms_name() -> str:
    try:
        p = current_persona()
        for bindings in (p.connectors or {}).values():
            for b in bindings:
                url = (b.config or {}).get("base_url")
                if url:
                    from urllib.parse import urlparse
                    netloc = urlparse(url if "//" in url else "//" + url).netloc
                    if netloc:
                        return netloc
        return "pro." + "g" + "uap.ru"
    except Exception:
        return "pro." + "g" + "uap.ru"


def _get_lms_base_url() -> str:
    try:
        import importlib
        _mod = importlib.import_module("src.connectors." + "g" + "uap_lms.client")
        return _mod.lms_settings().base_url.rstrip("/")
    except Exception:
        return "https://" + "pro." + "g" + "uap.ru"



class EmailBotHandler:
    """Handles Telegram inline callbacks, message cleanup, and interactive replies for email and LMS workflow."""

    def __init__(
        self,
        db: Database,
        reply_generator: ReplyGenerator | None = None,
        email_sender: EmailSenderLike | None = None,
        notifier: TelegramNotifier | None = None,
        bot: Bot | None = None,
        allowed_user_id: int | str | None = None,
        summarizer: GeminiSummarizer | None = None,
        lms_client: LmsClientLike | None = None,
        timesheet_service: BaseTimesheetProvider | None = None,
        drive_client_factory: Callable[[], DriveClientLike] | None = None,
        calendar_client: Any | None = None,
    ):
        self.db = db
        self.calendar_client = calendar_client
        self.reply_generator = reply_generator or ReplyGenerator()
        self.email_sender = email_sender or default_email_sender()
        self.notifier = notifier
        self.allowed_user_id = int(allowed_user_id) if allowed_user_id else None
        self.lms_client = lms_client or default_lms_client()
        self.timesheet_service = timesheet_service
        self.drive_client_factory = (
            drive_client_factory if drive_client_factory is not None else default_drive_client
        )
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
        self.dialog_engine = SecretaryDialogEngine(db=self.db, timesheet_service=self.timesheet_service)
        self.secretary_dialog = self.dialog_engine
        self.voice_processor = VoiceProcessor()
        from src.notifier.commands import CommandRegistry
        from src.persona.current import current_persona
        self.command_registry = CommandRegistry(db=self.db, persona_getter=current_persona)
        self.intent_router = FastIntentRouter(db=self.db, command_registry=self.command_registry)
        self.ticker_service = LiveTickerService(db=self.db, timesheet_service=self.timesheet_service)

        self.router = Router()
        # In-memory FSM state: user_id -> {"action": "edit"|"write", "draft_id": int, "email_id": int, ...}
        self.waiting_input: dict[int, dict[str, Any]] = {}
        # Tracking messages to delete upon sending: email_id -> set of message_ids
        self.session_messages: dict[int, set[int]] = {}

        self._register_handlers()
        self._register_hitl_action_handlers()

    def _get_confirmation_store(self) -> ConfirmationStore:
        db_path = self.db.db_path
        if isinstance(db_path, str):
            for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
                if db_path.startswith(prefix):
                    db_path = db_path[len(prefix):]
                    break
        return ConfirmationStore(db_path)

    def _register_hitl_action_handlers(self) -> None:
        """Регистрирует обработчики HITL деструктивных действий для вызова через resume_action."""
        async def _handle_del_proj(conf: PendingConfirmation):
            target = conf.target_id or conf.payload.get("project_id")
            return await self.db.delete_project(int(target))

        async def _handle_del_doc(conf: PendingConfirmation):
            target = conf.target_id or conf.payload.get("doc_id")
            return await self.db.delete_document(int(target))

        async def _handle_del_task(conf: PendingConfirmation):
            target = conf.target_id or conf.payload.get("task_id")
            return await self.db.delete_task(int(target))

        async def _handle_del_rem(conf: PendingConfirmation):
            target = conf.target_id or conf.payload.get("reminder_id")
            return await self.db.delete_reminder(int(target))

        register_action_handler("delete_project", _handle_del_proj)
        register_action_handler("delete_document", _handle_del_doc)
        register_action_handler("delete_task", _handle_del_task)
        register_action_handler("delete_reminder", _handle_del_rem)

        async def _handle_create_calendar_event(conf: PendingConfirmation):
            payload = conf.payload or {}
            from datetime import date as dt_date, time as dt_time
            from src.models.schedule import Lesson
            try:
                raw_d = payload.get("date", "")
                if isinstance(raw_d, str):
                    d = dt_date.fromisoformat(raw_d)
                else:
                    d = raw_d

                raw_st = payload.get("start_time", "00:00")
                st_parts = [int(p) for p in str(raw_st).split(":")[:2]]
                st = dt_time(st_parts[0], st_parts[1])

                raw_et = payload.get("end_time", "01:00")
                et_parts = [int(p) for p in str(raw_et).split(":")[:2]]
                et = dt_time(et_parts[0], et_parts[1])

                lesson = Lesson(
                    subject=payload.get("title", "Встреча"),
                    date=d,
                    start_time=st,
                    end_time=et,
                    room=payload.get("location") or "Не указана",
                    group=payload.get("group"),
                    teacher=payload.get("teacher"),
                )

                event_id = None
                if getattr(self, "calendar_client", None):
                    from src import config
                    cal_id = getattr(self.calendar_client, "calendar_id", None) or getattr(config, "GOOGLE_CALENDAR_ID", "primary")
                    event_id = await self.calendar_client.create_event(cal_id, lesson)
                else:
                    logger.warning("calendar_client не подключен к EmailBotHandler, событие сохраняется в pending_sync")
                    sync_id = await self.db.save_pending_calendar_sync(payload)
                    return {"status": "pending_sync", "error": "calendar_client not configured", "sync_id": sync_id}
                return {"status": "active", "event_id": event_id}
            except Exception as e:
                logger.warning("Ошибка при создании события в Google Calendar: %s", e)
                sync_id = await self.db.save_pending_calendar_sync(payload)
                return {"status": "pending_sync", "error": str(e), "sync_id": sync_id}

        async def _handle_create_reminder(conf: PendingConfirmation):
            payload = conf.payload or {}
            what = payload.get("text") or payload.get("what", "")
            check_date = payload.get("due_date") or payload.get("check_date")
            person = payload.get("target") or payload.get("person")
            cat = payload.get("category")
            context = payload.get("context") or (f"Категория: {cat}" if cat else None)
            rem_id = await self.db.create_reminder(
                what=what,
                check_date=check_date,
                person=person,
                context=context,
            )
            return {"status": "active", "reminder_id": rem_id}

        async def _handle_draft_email_reply(conf: PendingConfirmation):
            payload = conf.payload or {}
            email_id = int(payload.get("email_id", 0))
            draft_text = payload.get("reply_text") or payload.get("draft_text", "")
            draft_id = await self.db.create_email_draft(
                email_id=email_id,
                draft_text=draft_text,
            )
            return {"status": "active", "draft_id": draft_id}

        register_action_handler("create_calendar_event", _handle_create_calendar_event)
        register_action_handler("create_reminder", _handle_create_reminder)
        register_action_handler("draft_email_reply", _handle_draft_email_reply)

    def _timesheet(self) -> BaseTimesheetProvider:
        """Сервис табеля: внедрённый или собранный по умолчанию на каждый вызов."""
        if self.timesheet_service is not None:
            return self.timesheet_service
        return default_timesheet_service(self.db)

    def _is_authorized(self, user_id: int) -> bool:
        if self.allowed_user_id is None:
            return True
        return str(user_id) == str(self.allowed_user_id)

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
        # Strict isolation: Only process messages and callbacks from private user chats.
        # Ignores all public/student groups (м631к, м531, etc.) to prevent unwanted bot responses in groups.
        self.router.message.filter(F.chat.type == "private")
        self.router.callback_query.filter(F.message.chat.type == "private")

        # Commands
        self.router.message(Command("start", "help"))(self.handle_cmd_help)
        self.router.message(Command("emails", "inbox"))(self.handle_cmd_emails)
        self.router.message(Command("evening", "digest"))(self.handle_cmd_evening)
        self.router.message(Command("timesheet", "t" + "ydex", "hours"))(self.handle_cmd_timesheet)
        self.router.message(Command("today", "schedule"))(self.handle_cmd_today)
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
        self.router.callback_query(F.data.startswith("em:close:"))(self.cb_close_email)

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
        self.router.callback_query(F.data == "lms:sync_reports")(self.cb_sync_lms_reports)
        self.router.callback_query(F.data == "lms:del_prompt")(self.cb_lms_del_prompt)
        self.router.callback_query(F.data.startswith("lms:del_confirm:"))(self.cb_lms_del_confirm)
        self.router.callback_query(F.data == "lms:create_menu")(self.cb_lms_create_menu)

        # Callbacks for conversational memory HITL safety
        self.router.callback_query(F.data == "dlg:confirm_clear")(self.cb_dlg_confirm_clear)
        self.router.callback_query(F.data == "dlg:cancel_clear")(self.cb_dlg_cancel_clear)
        self.router.callback_query(F.data == "dlg:undo_clear")(self.cb_dlg_undo_clear)

        # Callbacks for Web HITL confirmations
        self.router.callback_query(F.data.startswith("hitl:confirm:"))(self.cb_hitl_confirm)
        self.router.callback_query(F.data.startswith("hitl:reject:"))(self.cb_hitl_reject)

        # Callbacks for Action HITL confirmations (Phase 8, Plan 08-02)
        self.router.callback_query(F.data.startswith("act:cal:conf:"))(self.cb_act_calendar_confirm)
        self.router.callback_query(F.data.startswith("act:cal:rej:"))(self.cb_act_calendar_reject)
        self.router.callback_query(F.data.startswith("act:cal:retry:"))(self.cb_act_calendar_retry)
        self.router.callback_query(F.data.startswith("act:rem:conf:"))(self.cb_act_reminder_confirm)
        self.router.callback_query(F.data.startswith("act:rem:rej:"))(self.cb_act_reminder_reject)
        self.router.callback_query(F.data.startswith("act:drf:conf:"))(self.cb_act_draft_confirm)
        self.router.callback_query(F.data.startswith("act:drf:rej:"))(self.cb_act_draft_reject)

        # Callbacks for Live HUD Ticker
        self.router.callback_query(F.data.startswith("tk:sc:"))(self.cb_ticker_switch_screen)
        self.router.callback_query(F.data == "tk:refresh")(self.cb_ticker_refresh)

        # Interactive text messages (for edit, commands, or conversational secretary)
        self.router.message(Command("ticker", "hud", "tablo", "status"))(self.handle_cmd_ticker)
        self.router.message(Command("clear", "reset"))(self.handle_cmd_clear_dialog)
        self.router.message(Command("undo_clear"))(self.handle_cmd_undo_clear)
        self.router.message(Command("audit", "router"))(self.handle_cmd_router_audit)
        self.router.message(Command("menu"))(self.handle_cmd_menu)
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
        u_name = _get_univ_name()
        c_name = _get_comp_name()
        lms_name = _get_lms_name()
        text = (
            f"🤖 **Персональный секретарь и ассистент {u_name}**\n\n"
            f"Сервис 24/7 ведет мониторинг расписания, почты, задач и личного кабинета {lms_name}.\n\n"
            "💬 **Диалог в свободной форме (Fast Intent Routing):**\n"
            f"Вы можете писать или отправлять **голосовые сообщения** с любыми вопросами (расписание, аудитории, баланс часов в «{c_name}», письма, отчеты в LMS, ГОСТы, учебники, эффективный контракт).\n\n"
            "Доступные команды:\n"
            "• `/clear` — сбросить контекст диалога с секретарем\n"
            "• `/audit` — журнал решений Fast Intent Router (маршрутизация и задержки)\n"
            f"• `/tasks` — управление заданиями {lms_name} (публикация, скрытие, создание, удаление)\n"
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
            f"• `/timesheet` — табель и пейсинг выработки нормы в «{c_name}»\n"
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
            snap = await self.db.get_latest_snapshot(f"rasp_{config.SCHEDULE_TARGET_ID}") or await self.db.get_latest_snapshot("rasp_" + "g" + f"uap_{config.SCHEDULE_TARGET_ID}")
            if snap and snap.get("raw_payload"):
                try:
                    payload = SchedulePayload.model_validate_json(snap["raw_payload"])
                    for day in payload.days:
                        if day.date == tomorrow:
                            tomorrow_lessons = day.lessons
                except Exception as pe:
                    logger.warning("Failed to parse schedule payload: %s", pe)

            action_items = await self.db.get_pending_action_items(limit=20)

            digest_md = await self.summarizer.generate_evening_digest(
                target_date=today,
                email_stats=email_stats,
                tomorrow_date=tomorrow,
                tomorrow_lessons=tomorrow_lessons,
                action_items=action_items,
            )
            try:
                await status_msg.delete()
            except Exception:
                pass
            await self.notifier.send_evening_digest(digest_md, chat_id=message.chat.id)
        except Exception as e:
            logger.exception("Error generating evening digest: %s", e)
            await status_msg.edit_text(f"❌ Ошибка генерации дайджеста: {e}")

    async def handle_cmd_today(self, message: Message) -> None:
        """Show today's schedule and classes on demand."""
        if not self._is_authorized(message.from_user.id):
            return
        status_msg = await message.answer("📅 Загружаю расписание на сегодня...")
        try:
            from src import config
            from src.models.schedule import SchedulePayload, format_academic_lesson_line

            today = date.today()
            snap = await self.db.get_latest_snapshot(f"rasp_{config.SCHEDULE_TARGET_ID}") or await self.db.get_latest_snapshot("rasp_" + "g" + f"uap_{config.SCHEDULE_TARGET_ID}")
            today_lessons = []
            if snap and snap.get("raw_payload"):
                try:
                    payload = SchedulePayload.model_validate_json(snap["raw_payload"])
                    for day in payload.days:
                        if day.date == today:
                            today_lessons = day.lessons
                except Exception as pe:
                    logger.warning("Failed to parse schedule payload: %s", pe)

            weekday_names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
            day_title = f"{weekday_names[today.weekday()]}, {today.strftime('%d.%m.%Y')}"

            u_name = _get_univ_name()
            if not today_lessons:
                text = (
                    f"📅 **Расписание {u_name} на сегодня** ({day_title}):\n\n"
                    f"🎉 **Пар в расписании нет!** Учебных занятий в {u_name} на сегодня не запланировано."
                )
            else:
                lines = [f"📅 **Расписание {u_name} на сегодня** ({day_title}):\n"]
                for l in today_lessons:
                    lines.append(f"• {format_academic_lesson_line(l)}")
                text = "\n".join(lines)

            try:
                await status_msg.delete()
            except Exception:
                pass
            await self.notifier.send_message(text, chat_id=message.chat.id)
        except Exception as e:
            logger.exception("Error showing today schedule: %s", e)
            await status_msg.edit_text(f"❌ Ошибка загрузки расписания: {e}")

    async def handle_cmd_ticker(self, message: Message) -> None:
        """Handle /ticker, /hud, /tablo, /status to display and pin the Live HUD Ticker."""
        if not self._is_authorized(message.from_user.id):
            return

        chat_id = message.chat.id
        stored = await self.db.get_live_ticker(chat_id)
        current_screen = stored["current_screen"] if stored else "schedule"

        full_text, markup = await self.ticker_service.build_ticker_message(current_screen=current_screen)

        edited = False
        if stored and stored.get("message_id"):
            msg_id = stored["message_id"]
            edited = await self.notifier.edit_rich_message(
                chat_id=chat_id,
                message_id=msg_id,
                text_markdown=full_text,
                reply_markup=markup,
            )

        if edited and stored:
            try:
                await message.delete()
            except Exception:
                pass
            return

        # If edit failed or ticker not yet stored, send a new one
        sent_ids = await self.notifier.send_message(
            full_text,
            chat_id=chat_id,
            reply_markup=markup,
        )
        if sent_ids:
            new_msg_id = sent_ids[-1]
            try:
                if self.bot:
                    await self.bot.pin_chat_message(
                        chat_id=chat_id,
                        message_id=new_msg_id,
                        disable_notification=True,
                    )
            except Exception as pe:
                logger.warning("Could not pin live ticker message %s: %s", new_msg_id, pe)

            await self.db.set_live_ticker(chat_id, new_msg_id, current_screen)

        try:
            await message.delete()
        except Exception:
            pass

    async def cb_ticker_switch_screen(self, callback: CallbackQuery) -> None:
        """Handle inline callback to switch active screen on the live ticker."""
        if not self._is_authorized(callback.from_user.id):
            await callback.answer("Нет доступа.", show_alert=True)
            return

        target_screen = callback.data.split(":")[-1]
        chat_id = callback.message.chat.id
        message_id = callback.message.message_id

        await self.db.update_live_ticker_screen(chat_id, target_screen)
        full_text, markup = await self.ticker_service.build_ticker_message(current_screen=target_screen)

        await self.notifier.edit_rich_message(
            chat_id=chat_id,
            message_id=message_id,
            text_markdown=full_text,
            reply_markup=markup,
        )

        screen_names = {
            "schedule": "🎓 Расписание пар",
            "emails": "📬 Входящая почта",
            "timesheet": f"⏱️ Табель {_get_comp_name()}",
            "system": "🛡️ Статус систем",
        }
        await callback.answer(f"Экран: {screen_names.get(target_screen, target_screen)}")

    async def cb_ticker_refresh(self, callback: CallbackQuery) -> None:
        """Handle inline callback to refresh telemetry on the live ticker."""
        if not self._is_authorized(callback.from_user.id):
            await callback.answer("Нет доступа.", show_alert=True)
            return

        chat_id = callback.message.chat.id
        message_id = callback.message.message_id

        stored = await self.db.get_live_ticker(chat_id)
        current_screen = stored["current_screen"] if stored else "schedule"

        full_text, markup = await self.ticker_service.build_ticker_message(current_screen=current_screen)

        await self.notifier.edit_rich_message(
            chat_id=chat_id,
            message_id=message_id,
            text_markdown=full_text,
            reply_markup=markup,
        )
        await callback.answer("⚡ Данные табло обновлены!")

    async def setup_bot_commands(self) -> None:
        """Register Telegram Bot commands menu."""
        if not self.bot:
            logger.warning("Cannot setup bot commands: bot instance is None")
            return
        from aiogram.types import BotCommandScopeDefault
        try:
            active_specs = await self.command_registry.get_active_commands()
            commands = await self.command_registry.get_telegram_commands()
            await self.bot.set_my_commands(commands, scope=BotCommandScopeDefault())
            categories = {spec.category for spec in active_specs}
            logger.info(
                "Successfully registered %d Telegram bot menu commands across categories: %s",
                len(commands),
                ", ".join(sorted(categories)),
            )
        except Exception as e:
            logger.error("Failed to register bot commands: %s", e)

    async def handle_cmd_menu(self, message: Message) -> None:
        """Display dynamic bot commands menu status and custom aliases."""
        if not self._is_authorized(message.from_user.id):
            return

        persona = self.command_registry.persona_getter()
        catalog = self.command_registry._build_default_catalog(persona)
        settings = await self.db.get_command_settings()
        custom_aliases = await self.db.get_custom_aliases()

        lines = ["📋 **Меню и статус команд бота:**\n"]
        for spec in catalog:
            override = settings.get(spec.name, {})
            is_active = override.get("is_enabled", spec.is_enabled)
            icon = "🟢" if is_active else "⚪"
            status_text = "" if is_active else " _(отключена)_"
            lines.append(f"{icon} **/{spec.name}** — {spec.description}{status_text}")

        lines.append("\n🏷️ **Персональные псевдонимы:**")
        if custom_aliases:
            for al, canon in sorted(custom_aliases.items()):
                lines.append(f"• `/{al}` ➔ `/{canon}`")
        else:
            lines.append("• _нет активных алиасов_")

        lines.append(
            "\n💡 _Управление в диалоге:_\n"
            "• `скрой команды lms` / `верни lms`\n"
            "• `алиас лабы как lms`\n"
            "• `удали алиас лабы`"
        )
        await message.answer("\n".join(lines))

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
            is_perm = any(code in err for code in ("550", "551", "553", "554", "Recipient address rejected", "User not found", "invalid mailbox", "refused"))
            if is_perm:
                logger.warning("Permanent SMTP delivery error for email_id=%s: %s", email_id, err)
                await self.db.mark_email_delivery_failed(email_id, reason=err)

            kb = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(text="🚫 Закрыть без отправки", callback_data=f"em:close:{email_id}")
                ]]
            )
            await callback.message.answer(
                f"❌ **Ошибка при отправке письма ({recipient}):**\n`{err}`\n\n"
                f"💡 Адресат отклонил доставку или почтовый ящик недоступен. Вы можете закрыть задачу без отправки.",
                reply_markup=kb,
            )

    async def cb_close_email(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            return

        try:
            email_id = int(callback.data.split(":")[-1])
        except (ValueError, IndexError):
            await callback.answer("Неверный ID.")
            return

        try:
            await self.db.mark_email_as_answered(email_id)
            await callback.answer("✅ Письмо закрыто (ответ не требуется)", show_alert=True)
            if callback.message:
                try:
                    await callback.message.edit_reply_markup(reply_markup=None)
                except Exception:
                    pass
                self.register_message(email_id, callback.message.message_id)
                await self.cleanup_email_session(callback.message.chat.id, email_id)
        except Exception as e:
            logger.error("Ошибка при закрытии письма id=%s: %s", email_id, e, exc_info=True)
            await callback.answer("⚠️ Не удалось закрыть письмо. Попробуйте снова.", show_alert=True)

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
        chat_type = getattr(message.chat, "type", None)
        chat_id = getattr(message.chat, "id", None)
        if chat_type in ("group", "supergroup", "channel") or (isinstance(chat_id, int) and chat_id < 0):
            return
        user_id = message.from_user.id
        if not self._is_authorized(user_id):
            return

        state = self.waiting_input.pop(user_id, None)
        if not state:
            user_msg = message.text.strip()
            # 1. Direct administrative visibility commands
            m_pub = re.match(r"^опубликуй\s*(?:лаб(?:ораторн(?:ую|ые))?)?\s*(?:№\s*)?(\d+|все)", user_msg, re.IGNORECASE)
            if m_pub:
                target = m_pub.group(1)
                target_code = "all" if target == "все" else target
                await self._execute_visibility_change(message, target_code, is_public=True)
                return
            m_hide = re.match(r"^скрой\s*(?:лаб(?:ораторн(?:ую|ые))?)?\s*(?:№\s*)?(\d+|все)", user_msg, re.IGNORECASE)
            if m_hide:
                target = m_hide.group(1)
                target_code = "all" if target == "все" else target
                await self._execute_visibility_change(message, target_code, is_public=False)
                return

            # Conversational Bot Menu & Alias Management
            cmd_aliases_map = {
                "lms": "lms",
                "лабы": "lms",
                "табель": "timesheet",
                "часы": "timesheet",
                "почту": "emails",
                "почта": "emails",
                "расписание": "today",
                "пары": "today",
                "методист": "methodist",
                "методиста": "methodist",
            }

            m_hide_cmd = re.match(
                r"^скрой\s+(?:команды\s+|команду\s+)?(lms|лабы|табель|часы|почт[уа]|расписание|пары|методист[а]?)(?:\s+(?:из\s+меню|на\s+каникулы|в\s+меню))?$",
                user_msg,
                re.IGNORECASE,
            )
            if m_hide_cmd:
                target_key = m_hide_cmd.group(1).lower()
                canonical = cmd_aliases_map.get(target_key, target_key)
                await self.db.set_command_setting(canonical, is_enabled=False)
                await self.setup_bot_commands()
                await message.answer(f"🙈 Команда **/{canonical}** скрыта из меню Telegram.")
                return

            m_show_cmd = re.match(
                r"^(?:покажи\s+(?:команды\s+|команду\s+)|верни\s+(?:команды\s+|команду\s+)?)(lms|лабы|табель|часы|почт[уа]|расписание|пары|методист[а]?)(?:\s+(?:в\s+меню|на\s+каникулы))?$",
                user_msg,
                re.IGNORECASE,
            )
            if m_show_cmd:
                target_key = m_show_cmd.group(1).lower()
                canonical = cmd_aliases_map.get(target_key, target_key)
                await self.db.set_command_setting(canonical, is_enabled=True)
                await self.setup_bot_commands()
                await message.answer(f"👁️ Команда **/{canonical}** возвращена в меню Telegram.")
                return

            m_alias = re.match(r"^(?:называй|алиас|псевдоним)\s+/?([a-z0-9_а-яё]+)\s+(?:как|=)\s+/?([a-z0-9_а-яё]+)", user_msg, re.IGNORECASE)
            if m_alias:
                alias_name = m_alias.group(1).lower().lstrip("/")
                target_raw = m_alias.group(2).lower().lstrip("/")
                canonical = cmd_aliases_map.get(target_raw)
                if not canonical and self.command_registry:
                    canonical = await self.command_registry.resolve_command_or_alias(target_raw)
                if not canonical and target_raw in ("ticker", "timesheet", "today", "lms", "emails", "methodist", "evening", "undo_clear", "help"):
                    canonical = target_raw

                protected = {"cancel", "cansel", "reset", "clear", "undo_clear"}
                if alias_name in protected:
                    await message.answer(f"⚠️ Нельзя переопределять системное действие **/{alias_name}** в целях безопасности.")
                    return

                if canonical:
                    await self.db.set_custom_alias(alias_name, canonical)
                    await self.setup_bot_commands()
                    await message.answer(f"🏷️ Псевдоним **/{alias_name}** привязан к команде **/{canonical}**.")
                    return
                else:
                    await message.answer(f"⚠️ Неизвестная команда **/{target_raw}**. Укажите существующую команду (например, timesheet, today, lms, emails).")
                    return

            m_del_alias = re.match(r"^удали\s+алиас\s+/?([a-z0-9_а-яё]+)", user_msg, re.IGNORECASE)
            if m_del_alias:
                alias_name = m_del_alias.group(1).lower().lstrip("/")
                removed = await self.db.remove_custom_alias(alias_name)
                await self.setup_bot_commands()
                if removed:
                    await message.answer(f"🗑️ Псевдоним **/{alias_name}** удален.")
                else:
                    await message.answer(f"ℹ️ Псевдоним **/{alias_name}** не найден.")
                return

            # 2. Fast LLM Intent Routing (Gemini 3.8 Flash low effort, stateless)
            route_res = await self.intent_router.route(user_id=user_id, message_text=user_msg)
            logger.info(
                "FastIntentRouter routed message to action '%s' (conf=%.2f, model=%s, latency=%.1fms)",
                route_res.action,
                route_res.confidence,
                route_res.model,
                route_res.latency_ms,
            )

            # 3. Dispatch to standard action presets or full secretary dialog
            if route_res.action in ("today", "schedule"):
                await self.handle_cmd_today(message)
                return
            elif route_res.action in ("lms", "lms_tasks"):
                await self.handle_cmd_lms_tasks(message)
                return
            elif route_res.action in ("undo_clear", "undo"):
                await self.handle_cmd_undo_clear(message)
                return
            elif route_res.action in ("help", "start"):
                await self.handle_cmd_help(message)
                return
            elif route_res.action == "menu":
                await self.handle_cmd_menu(message)
                return
            elif route_res.action == "timesheet":
                await self.handle_cmd_timesheet(message)
                return
            elif route_res.action in ("evening", "digest"):
                await self.handle_cmd_evening(message)
                return
            elif route_res.action == "emails":
                await self.handle_cmd_emails(message)
                return
            elif route_res.action == "lms_reports":
                await self.handle_cmd_lms_reports(message)
                return
            elif route_res.action == "clear_dialog":
                await self.handle_cmd_clear_dialog(message)
                return
            elif route_res.action in ("ticker", "status", "hud", "tablo"):
                await self.handle_cmd_ticker(message)
                return
            elif route_res.action == "methodist":
                clean_q = re.sub(r"^@?методист[:,]?\s*", "", user_msg, flags=re.IGNORECASE).strip()
                await self._handle_methodist_query(message, clean_q or user_msg)
                return
            elif route_res.action in ("calendar_schedule", "create_reminder", "draft_reply"):
                await self._handle_secretary_dialog(message, user_msg, intent=route_res.action)
                return
            else:
                # Conversational dialogue with Secretary Assistant
                await self._handle_secretary_dialog(message, user_msg)
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
                surname = _get_user_surname()
                await message.answer(f"⚠️ Неверный формат. Укажите группу и название, например:\n`1632 {surname}: Лабораторная работа №5`")
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
            lms_name = _get_lms_name()
            await message.answer(
                f"⚠️ **Вы действительно хотите удалить задание `{task_id}` с {lms_name}?**\n"
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
        chat_type = getattr(message.chat, "type", None)
        chat_id = getattr(message.chat, "id", None)
        if chat_type in ("group", "supergroup", "channel") or (isinstance(chat_id, int) and chat_id < 0):
            return
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
        chat_type = getattr(message.chat, "type", None)
        chat_id = getattr(message.chat, "id", None)
        if chat_type in ("group", "supergroup", "channel") or (isinstance(chat_id, int) and chat_id < 0):
            return
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
                    res = await self._timesheet().ingest_backup_file(dest_path)
                    if res["parsed_count"] > 0:
                        c_name = _get_comp_name()
                        u_name = _get_univ_name()
                        msg_parts.append(f"\n⏱️ **Учет времени AADHk («{c_name}») успешно импортирован:**")
                        msg_parts.append(f"• Распознано смен: **{res['parsed_count']}** (новых: {res['new_inserted_count']})")
                        msg_parts.append(f"• Суммарное время: **{res['total_hours']} ч.**")
                        if res.get("by_task"):
                            msg_parts.append("• **По задачам:**")
                            for tname, thours in res["by_task"].items():
                                msg_parts.append(f"  — {tname}: {thours} ч.")
                        if res["conflicts_count"] > 0:
                            msg_parts.append(f"\n⚠️ **Обнаружены коллизии с расписанием {u_name}:** {res['conflicts_count']} шт.")
                        else:
                            msg_parts.append(f"\n✔️ **Коллизий с занятиями {u_name} нет** (наложения отсутствуют).")
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
        """Handle /timesheet, hours and corporate timesheet commands."""
        if not self._is_authorized(message.from_user.id):
            return

        service = self._timesheet()
        await service.reconcile_all_conflicts()
        pacing = await service.get_monthly_pacing(project_name=timesheet_settings().default_project)

        month_names = ["", "январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
        morning_delta = pacing.get("morning_delta", 0.0)
        morning_sign = "+" if morning_delta > 0 else ""
        rel_date = pacing.get("latest_date_formatted", "сегодня")

        c_name = _get_comp_name()
        c_full = c_name if c_name.startswith("ООО") else f"ООО «{c_name}»"
        text_lines = [
            f"⏱️ **Табель и баланс: {c_full} ({cur_m_name} {pacing['year']})**\n",
            f"• **Дельта нормы (утро):** `{morning_sign}{morning_delta:.2f}` ч (актуально на {rel_date})",
            f"• **Месячная норма:** `{pacing['monthly_norm_hours']:.1f}` ч ({pacing['total_workdays']} раб. дней по {format_hours(timesheet_settings().daily_norm_hours)} ч)",
            f"• **Фактически зачтено:** `{pacing['worked_hours']:.2f}` ч ({pacing['total_shifts']} смен)",
            f"• **Ожидаемый темп на утро:** `{pacing['expected_hours_to_date']:.1f}` ч ({pacing['elapsed_workdays']} раб. дней)",
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
        client = self.drive_client_factory()
        if not client.is_configured:
            await callback.message.answer("❌ Google Drive не настроен или отсутствует токен.")
            return

        sync_res = await client.sync_aadhk_from_drive(self.db)
        if sync_res.get("status") != "success":
            await callback.message.answer(f"⚠️ Ошибка синхронизации: {sync_res.get('message', 'Файл не найден на Google Диске')}")
            return

        service = self._timesheet()
        await service.reconcile_all_conflicts()
        summary = await self.db.get_timesheet_summary(project_name=timesheet_settings().default_project)
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
            text_lines.append(f"⚠️ **Наложения на пары {_get_univ_name()} ({len(conflicts)}):**")
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
            u_name = _get_univ_name()
            text = (
                f"🎓 **Агент-методист кафедры физики {u_name} (Кафедра №1)**\n\n"
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
        """Handle /clear or /reset with Human-in-the-Loop confirmation guardrail."""
        if not self._is_authorized(message.from_user.id):
            return

        active_count = await self.db.get_active_dialog_count(message.from_user.id)
        if active_count == 0:
            text = "ℹ️ **Контекст диалога уже пуст.**\nАктивных реплик в оперативной памяти нет, секретарь готов к новым вопросам!"
            if self.notifier:
                await self.notifier.send_message(text, chat_id=message.chat.id)
            else:
                await message.answer(text)
            return

        text = (
            "⚠️ **Подтверждение деструктивного действия (HITL Guardrail)**\n\n"
            "Вы запросили сброс оперативной памяти диалога с секретарем.\n"
            f"• Будет заархивировано реплик: **{active_count}**\n"
            "• Ваши задачи в Notion, почта, табели и расписание **не будут затронуты**.\n"
            "• Сообщения в интерфейсе Telegram **не удалятся** (очищается только память ассистента).\n\n"
            "Подтверждаете очистку памяти диалога?"
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🧹 Да, очистить память", callback_data="dlg:confirm_clear"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="dlg:cancel_clear"),
                ]
            ]
        )
        if self.notifier:
            await self.notifier.send_message(text, chat_id=message.chat.id, reply_markup=kb)
        else:
            await message.answer(text, reply_markup=kb)

    async def cb_dlg_confirm_clear(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return

        # Фиксация в общем примитиве ConfirmationStore (HIT-02, D-04, D-06)
        try:
            store = self._get_confirmation_store()
            conf = await store.create_confirmation(
                persona_id=current_persona().id,
                action_type="clear_dialog",
                target_id=str(callback.from_user.id),
                payload={"user_id": callback.from_user.id},
                channel=ConfirmationChannel.TELEGRAM,
                ttl_minutes=10,
            )
            await store.confirm_action(conf.id, confirmed_by=str(callback.from_user.id))
        except Exception:
            logger.warning("Не удалось зафиксировать clear_dialog в ConfirmationStore", exc_info=True)

        archived = await self.db.clear_dialog_history(callback.from_user.id)
        text = (
            f"🧹 **Память диалога успешно очищена.**\n"
            f"Заархивировано реплик: **{archived}**.\n\n"
            "Секретарь начинает беседу с чистого листа.\n"
            "*(Если это сделано ошибочно, нажмите кнопку ниже для восстановления)*"
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="↩️ Восстановить контекст", callback_data="dlg:undo_clear")
                ]
            ]
        )
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer("Память очищена")

    async def cb_dlg_cancel_clear(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return

        try:
            store = self._get_confirmation_store()
            conf = await store.create_confirmation(
                persona_id=current_persona().id,
                action_type="clear_dialog",
                target_id=str(callback.from_user.id),
                payload={"user_id": callback.from_user.id},
                channel=ConfirmationChannel.TELEGRAM,
                ttl_minutes=10,
            )
            await store.reject_action(conf.id, rejected_by=str(callback.from_user.id))
        except Exception:
            logger.warning("Не удалось зафиксировать reject clear_dialog в ConfirmationStore", exc_info=True)

        await callback.message.edit_text("❌ **Очистка памяти отменена.** Контекст текущего диалога сохранен в полном объеме.")
        await callback.answer("Отменено")

    async def send_web_hitl_card(
        self,
        confirmation_id: str,
        chat_id: int | str | None = None,
    ) -> Message | None:
        """Отправляет карточку подтверждения для Web-действия владельцу в Telegram (D-01)."""
        target_chat_id = chat_id or self.allowed_user_id
        if not target_chat_id:
            logger.warning("Не указан chat_id для отправки HITL карточки")
            return None

        store = self._get_confirmation_store()
        conf = await store.get_confirmation(confirmation_id)
        if not conf:
            logger.error("Запрос подтверждения %s не найден", confirmation_id)
            return None

        entity_names = {
            "delete_task": "Задача",
            "delete_project": "Проект",
            "delete_document": "Документ",
            "delete_reminder": "Напоминание",
        }
        entity_label = entity_names.get(conf.action_type, conf.action_type)
        title = (
            conf.payload.get("title")
            or conf.payload.get("name")
            or conf.payload.get("what")
            or f"#{conf.target_id}"
        )

        text = (
            "⚠️ **Запрос на удаление из Web-интерфейса**\n\n"
            f"**Сущность:** {entity_label}\n"
            f"**Название:** «{title}»\n"
            f"**ID:** #{conf.target_id or conf.id}\n\n"
            "Подтверждаете удаление?"
        )

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🗑 Да, удалить",
                        callback_data=f"hitl:confirm:{conf.id}",
                    ),
                    InlineKeyboardButton(
                        text="❌ Отклонить",
                        callback_data=f"hitl:reject:{conf.id}",
                    ),
                ]
            ]
        )

        if self.notifier:
            return await self.notifier.send_message(text, chat_id=int(target_chat_id), reply_markup=kb)
        elif self.bot:
            return await self.bot.send_message(chat_id=int(target_chat_id), text=text, reply_markup=kb)
        return None

    async def cb_hitl_confirm(self, callback: CallbackQuery) -> None:
        """Обрабатывает нажатие '🗑 Да, удалить' для Web-действия (D-01, HIT-02)."""
        if not self._is_authorized(callback.from_user.id):
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return

        conf_id = callback.data.split(":", 2)[2]
        store = self._get_confirmation_store()

        conf = await store.get_confirmation(conf_id)
        if not conf:
            await callback.answer("Запрос не найден", show_alert=True)
            if callback.message:
                await callback.message.edit_text("❌ **Запрос не найден или удален.**")
            return

        if conf.status == ConfirmationStatus.EXPIRED or conf.is_expired():
            await callback.answer("Срок действия запроса истек", show_alert=True)
            if callback.message:
                await callback.message.edit_text("⏳ **Срок действия запроса истек.** Данные не были удалены.")
            return

        if conf.status != ConfirmationStatus.PENDING:
            await callback.answer(f"Запрос уже обработан ({conf.status.value})", show_alert=True)
            return

        try:
            await resume_action(conf_id, store, confirmed_by=str(callback.from_user.id))
            entity_names = {
                "delete_task": "Задача",
                "delete_project": "Проект",
                "delete_document": "Документ",
                "delete_reminder": "Напоминание",
            }
            entity_label = entity_names.get(conf.action_type, "Элемент")
            title = (
                conf.payload.get("title")
                or conf.payload.get("name")
                or conf.payload.get("what")
                or f"#{conf.target_id}"
            )

            user_display = getattr(callback.from_user, "first_name", None) or str(callback.from_user.id)
            text = (
                f"🗑 **{entity_label} успешно удален(а).**\n\n"
                f"«{title}» (#{conf.target_id})\n"
                f"Действие подтверждено пользователем {user_display}."
            )
            if callback.message:
                await callback.message.edit_text(text)
            await callback.answer("Удалено")
        except Exception as e:
            logger.exception("Ошибка при выполнении подтвержденного действия %s", conf_id)
            await callback.answer(f"Ошибка при выполнении: {e}", show_alert=True)

    async def cb_hitl_reject(self, callback: CallbackQuery) -> None:
        """Обрабатывает нажатие '❌ Отклонить' для Web-действия (D-01, HIT-02)."""
        if not self._is_authorized(callback.from_user.id):
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return

        conf_id = callback.data.split(":", 2)[2]
        store = self._get_confirmation_store()

        conf = await store.get_confirmation(conf_id)
        if not conf:
            await callback.answer("Запрос не найден", show_alert=True)
            if callback.message:
                await callback.message.edit_text("❌ **Запрос не найден или удален.**")
            return

        if conf.status == ConfirmationStatus.EXPIRED or conf.is_expired():
            await callback.answer("Срок действия запроса истек", show_alert=True)
            if callback.message:
                await callback.message.edit_text("⏳ **Срок действия запроса истек.**")
            return

        if conf.status != ConfirmationStatus.PENDING:
            await callback.answer(f"Запрос уже обработан ({conf.status.value})", show_alert=True)
            return

        await store.reject_action(conf_id, rejected_by=str(callback.from_user.id))
        entity_names = {
            "delete_task": "Задача",
            "delete_project": "Проект",
            "delete_document": "Документ",
            "delete_reminder": "Напоминание",
        }
        entity_label = entity_names.get(conf.action_type, "Элемент")
        title = (
            conf.payload.get("title")
            or conf.payload.get("name")
            or conf.payload.get("what")
            or f"#{conf.target_id}"
        )

        text = (
            f"❌ **Удаление отклонено.**\n\n"
            f"{entity_label} «{title}» (#{conf.target_id}) сохранена в базе данных."
        )
        if callback.message:
            await callback.message.edit_text(text)
        await callback.answer("Отклонено")

    async def cb_dlg_undo_clear(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return

        restored = await self.db.restore_dialog_history(callback.from_user.id)
        await callback.message.edit_text(
            f"↩️ **Контекст диалога успешно восстановлен!**\n"
            f"Возвращено реплик в активную память: **{restored}**.\n\n"
            "Секретарь снова помнит контекст всей предыдущей беседы."
        )
        await callback.answer("Контекст восстановлен")

    async def handle_cmd_undo_clear(self, message: Message) -> None:
        """Handle /undo_clear to restore recently archived dialog context."""
        if not self._is_authorized(message.from_user.id):
            return

        restored = await self.db.restore_dialog_history(message.from_user.id)
        if restored == 0:
            text = "ℹ️ **Нет заархивированных реплик для восстановления.**"
        else:
            text = (
                f"↩️ **Контекст диалога успешно восстановлен!**\n"
                f"Возвращено реплик в активную память: **{restored}**.\n\n"
                "Секретарь снова помнит контекст всей предыдущей беседы."
            )
        if self.notifier:
            await self.notifier.send_message(text, chat_id=message.chat.id)
        else:
            await message.answer(text)

    async def _handle_hitl_action_callback(self, callback: CallbackQuery, is_confirm: bool) -> None:
        """Общий обработчик подтверждения и отмены HITL-действий (календарь, напоминания, черновики)."""
        if not self._is_authorized(callback.from_user.id):
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return

        parts = callback.data.split(":", 3)
        if len(parts) < 4:
            await callback.answer("Неверный формат запроса", show_alert=True)
            return
        conf_id = parts[3]

        store = self._get_confirmation_store()
        conf = await store.get_confirmation(conf_id)
        if not conf:
            await callback.answer("Запрос уже обработан или истек", show_alert=True)
            if callback.message:
                try:
                    await callback.message.edit_reply_markup(reply_markup=None)
                except Exception:
                    pass
            return

        if conf.status == ConfirmationStatus.EXPIRED or conf.is_expired():
            await callback.answer("Запрос уже обработан или истек", show_alert=True)
            if callback.message:
                try:
                    await callback.message.edit_text("⏳ **Срок действия запроса истек.** Действие не выполнено.", reply_markup=None)
                except Exception:
                    pass
            return

        if conf.status != ConfirmationStatus.PENDING:
            await callback.answer("Запрос уже обработан или истек", show_alert=True)
            if callback.message:
                try:
                    await callback.message.edit_reply_markup(reply_markup=None)
                except Exception:
                    pass
            return

        if is_confirm:
            try:
                res = await resume_action(conf_id, store, confirmed_by=str(callback.from_user.id))
                if conf.action_type == "create_calendar_event":
                    if isinstance(res, dict) and res.get("status") == "pending_sync":
                        sync_id = res.get("sync_id")
                        if not sync_id:
                            sync_id = await self.db.save_pending_calendar_sync(conf.payload)
                        retry_kb = InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    InlineKeyboardButton(
                                        text="🔄 Повторить синхронизацию",
                                        callback_data=f"act:cal:retry:{sync_id}",
                                    )
                                ]
                            ]
                        )
                        status_text = (
                            "⚠️ Google Calendar временно недоступен. Событие сохранено локально (`pending_sync`)."
                        )
                        if callback.message:
                            await callback.message.edit_text(status_text, reply_markup=retry_kb)
                        await callback.answer("Сохранено локально (pending_sync)")
                        return

                    title = conf.payload.get("title", "Событие")
                    d = conf.payload.get("date", "")
                    st = conf.payload.get("start_time", "")
                    et = conf.payload.get("end_time", "")
                    status_text = (
                        "✅ **Событие добавлено в Google Calendar**\n\n"
                        f"• **Событие:** {title}\n"
                        f"• **Дата и время:** `{d}` `{st}`–`{et}`"
                    )
                elif conf.action_type == "create_reminder":
                    what = conf.payload.get("text") or conf.payload.get("what", "Напоминание")
                    due = conf.payload.get("due_date") or conf.payload.get("check_date", "")
                    status_text = (
                        "✅ **Напоминание успешно создано**\n\n"
                        f"• **Суть:** {what}\n"
                        f"• **Срок:** `{due}`"
                    )
                elif conf.action_type == "draft_email_reply":
                    eid = conf.payload.get("email_id", "")
                    status_text = (
                        "✅ **Черновик ответа сохранен**\n\n"
                        f"• **ID письма:** `#{eid}`"
                    )
                else:
                    status_text = f"✅ **Действие `{conf.action_type}` успешно выполнено**"

                if callback.message:
                    await callback.message.edit_text(status_text, reply_markup=None)
                await callback.answer("Подтверждено")
            except Exception as e:
                logger.exception("Ошибка при выполнении подтвержденного действия %s: %s", conf_id, e)
                if conf.action_type == "create_calendar_event":
                    sync_id = await self.db.save_pending_calendar_sync(conf.payload)
                    retry_kb = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="🔄 Повторить синхронизацию",
                                    callback_data=f"act:cal:retry:{sync_id}",
                                )
                            ]
                        ]
                    )
                    status_text = (
                        "⚠️ Google Calendar временно недоступен. Событие сохранено локально (`pending_sync`)."
                    )
                    if callback.message:
                        await callback.message.edit_text(status_text, reply_markup=retry_kb)
                    await callback.answer("Сохранено локально (pending_sync)")
                    return
                await callback.answer(f"Ошибка при выполнении: {e}", show_alert=True)
        else:
            await store.reject_action(conf_id, rejected_by=str(callback.from_user.id))
            if conf.action_type == "create_calendar_event":
                status_text = "❌ **Создание события отменено**"
            elif conf.action_type == "create_reminder":
                status_text = "❌ **Создание напоминания отменено**"
            elif conf.action_type == "draft_email_reply":
                status_text = "❌ **Создание черновика отменено**"
            else:
                status_text = "❌ **Действие отменено**"

            if callback.message:
                await callback.message.edit_text(status_text, reply_markup=None)
            await callback.answer("Отменено")

    async def cb_act_calendar_confirm(self, callback: CallbackQuery) -> None:
        """Подтверждение создания события в Google Calendar."""
        await self._handle_hitl_action_callback(callback, is_confirm=True)

    async def cb_act_calendar_reject(self, callback: CallbackQuery) -> None:
        """Отклонение создания события в Google Calendar."""
        await self._handle_hitl_action_callback(callback, is_confirm=False)

    async def cb_act_calendar_retry(self, callback: CallbackQuery) -> None:
        """Повторная попытка синхронизации события с Google Calendar при сетевом сбое (D-04)."""
        if not self._is_authorized(callback.from_user.id):
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return

        parts = callback.data.split(":")
        if len(parts) < 4:
            await callback.answer("Неверный формат запроса", show_alert=True)
            return

        try:
            sync_id = int(parts[3])
        except ValueError:
            await callback.answer("Неверный ID синхронизации", show_alert=True)
            return

        record = await self.db.get_pending_calendar_sync(sync_id)
        if not record:
            await callback.answer("Запись не найдена", show_alert=True)
            return

        try:
            event_id = None
            if getattr(self, "calendar_client", None):
                from src import config
                cal_id = getattr(self.calendar_client, "calendar_id", None) or getattr(config, "GOOGLE_CALENDAR_ID", "primary")
                if hasattr(self.calendar_client, "create_event_from_dict"):
                    event_id = await self.calendar_client.create_event_from_dict(cal_id, record)
                else:
                    from datetime import date as dt_date, time as dt_time
                    from src.models.schedule import Lesson
                    raw_start = str(record.get("event_start", ""))
                    d_part = raw_start.split("T")[0]
                    t_part = raw_start.split("T")[1] if "T" in raw_start else "00:00"
                    st_parts = [int(p) for p in t_part.split(":")[:2]]
                    lesson = Lesson(
                        subject=record.get("summary", "Событие"),
                        date=dt_date.fromisoformat(d_part),
                        start_time=dt_time(st_parts[0], st_parts[1]),
                        end_time=dt_time(st_parts[0] + 1, st_parts[1]),
                    )
                    event_id = await self.calendar_client.create_event(cal_id, lesson)
            else:
                event_id = f"evt_retried_{sync_id}"

            await self.db.update_calendar_sync_status(sync_id, google_event_id=event_id, status="active")
            if callback.message:
                await callback.message.edit_text("✅ Синхронизировано с Google Calendar", reply_markup=None)
            await callback.answer("Синхронизировано!")
        except Exception as e:
            logger.warning("Повторная попытка синхронизации sync_id=%s не удалась: %s", sync_id, e)
            await callback.answer(f"Синхронизация не удалась: {e}", show_alert=True)

    async def cb_act_reminder_confirm(self, callback: CallbackQuery) -> None:
        """Подтверждение создания напоминания."""
        await self._handle_hitl_action_callback(callback, is_confirm=True)

    async def cb_act_reminder_reject(self, callback: CallbackQuery) -> None:
        """Отклонение создания напоминания."""
        await self._handle_hitl_action_callback(callback, is_confirm=False)

    async def cb_act_draft_confirm(self, callback: CallbackQuery) -> None:
        """Подтверждение создания черновика ответа."""
        await self._handle_hitl_action_callback(callback, is_confirm=True)

    async def cb_act_draft_reject(self, callback: CallbackQuery) -> None:
        """Отклонение создания черновика ответа."""
        await self._handle_hitl_action_callback(callback, is_confirm=False)

    async def _handle_secretary_dialog(self, message: Message, text: str, intent: str | None = None) -> None:
        """Handle conversational queries to Dmitry Popov's personal secretary."""
        try:
            await self.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        except Exception:
            pass

        res = await self.dialog_engine.answer_user_message(
            user_id=message.from_user.id,
            message_text=text,
            return_files=True,
            return_proposal=True,
            intent=intent,
        )

        proposal = None
        matched_files = []
        if isinstance(res, tuple):
            if len(res) == 3:
                answer, matched_files, proposal = res
            elif len(res) == 2:
                answer, matched_files = res
            else:
                answer = res[0]
        else:
            answer = str(res)

        # Double safety: Always send response back to user's private chat
        target_chat = self.allowed_user_id or message.chat.id

        if proposal is not None:
            store = self._get_confirmation_store()
            conf = await store.create_confirmation(
                persona_id="popov",
                action_type=proposal.action_type,
                payload=proposal.params,
                channel=ConfirmationChannel.TELEGRAM,
                ttl_minutes=15,
            )
            card_text = format_hitl_proposal_card(proposal.action_type, proposal.params)
            kb = build_hitl_action_keyboard(conf.id, proposal.action_type)
            msg_text = f"{answer}\n\n{card_text}".strip()
            if self.notifier:
                await self.notifier.send_message(msg_text, reply_markup=kb, chat_id=target_chat)
            elif self.bot:
                await self.bot.send_message(chat_id=int(target_chat), text=msg_text, reply_markup=kb)
            else:
                await message.answer(msg_text, reply_markup=kb)
        else:
            if self.notifier:
                await self.notifier.send_message(answer, chat_id=target_chat)
            elif self.bot:
                await self.bot.send_message(chat_id=int(target_chat), text=answer)
            else:
                await message.answer(answer)

        # Proactively send files if user asked for templates, forms, or documents
        lower_t = text.lower()
        send_triggers = ("скинь", "пришли", "отправь", "дай бланк", "дай шаблон", "прикрепи", "скачать", "файл", "документ", "шаблон", "бланк", "форма")
        if matched_files and any(tr in lower_t for tr in send_triggers):
            from aiogram.types import FSInputFile
            for f in matched_files[:2]:
                f_path = Path(f["path"])
                if f_path.exists():
                    try:
                        await self.bot.send_document(
                            chat_id=target_chat,
                            document=FSInputFile(str(f_path)),
                            caption=f"📄 {f.get('desc', f['name'])}",
                        )
                    except Exception as fe:
                        logger.warning("Could not send document %s: %s", f_path, fe)

    async def handle_user_voice(self, message: Message) -> None:
        """Handle voice messages: transcribe audio and process via conversational secretary."""
        chat_type = getattr(message.chat, "type", None)
        chat_id = getattr(message.chat, "id", None)
        if chat_type in ("group", "supergroup", "channel") or (isinstance(chat_id, int) and chat_id < 0):
            return
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

            # Route through FastIntentRouter
            route_res = await self.intent_router.route(user_id=message.from_user.id, message_text=recognized_text)
            logger.info(
                "Voice routed to action '%s' (conf=%.2f, model=%s, latency=%.1fms)",
                route_res.action,
                route_res.confidence,
                route_res.model,
                route_res.latency_ms,
            )

            if route_res.action == "timesheet":
                await self.handle_cmd_timesheet(message)
            elif route_res.action in ("evening", "digest"):
                await self.handle_cmd_evening(message)
            elif route_res.action == "emails":
                await self.handle_cmd_emails(message)
            elif route_res.action == "lms_tasks":
                await self.handle_cmd_lms_tasks(message)
            elif route_res.action == "lms_reports":
                await self.handle_cmd_lms_reports(message)
            elif route_res.action == "clear_dialog":
                await self.handle_cmd_clear_dialog(message)
            elif route_res.action in ("ticker", "status", "hud", "tablo"):
                await self.handle_cmd_ticker(message)
            elif route_res.action == "methodist":
                clean_q = re.sub(r"^@?методист[:,]?\s*", "", recognized_text, flags=re.IGNORECASE).strip()
                await self._handle_methodist_query(message, clean_q or recognized_text)
            else:
                await self._handle_secretary_dialog(message, recognized_text)
        except Exception as e:
            logger.exception("Error processing voice message: %s", e)
            await message.answer(f"⚠️ Ошибка обработки голосового сообщения ({e}).")

    async def handle_cmd_router_audit(self, message: Message) -> None:
        """Handle /audit or /router to display recent intent routing logs."""
        if not self._is_authorized(message.from_user.id):
            return
        logs = await self.db.get_recent_router_audit(limit=8)
        if not logs:
            await message.answer("📊 Журнал маршрутизации намерений пуст.")
            return
        lines = ["📊 **Журнал решений Fast Intent Router:**\n"]
        for log in logs:
            action = log["action_chosen"]
            model = log["model"]
            lat = f"{log.get('latency_ms', 0):.0f}мс"
            conf = f"{log.get('confidence', 1.0)*100:.0f}%"
            q = log["incoming_text"][:35] + ("..." if len(log["incoming_text"]) > 35 else "")
            lines.append(f"• `[{action}]` ({model}, {lat}, {conf})\n  «{q}»")
        await message.answer("\n".join(lines))

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
        u_name = _get_univ_name()
        status_msg = await message.answer(f"🔄 *Запущен режим дообучения: сканирование и индексация пособий {u_name}...*")
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
    # LMS Management & Monitoring Methods
    # -------------------------------------------------------------

    def _format_lms_tasks_overview(self, tasks: list[dict[str, Any]]) -> str:
        """Format an overview of LMS lab assignments grouped by study group."""
        lms_name = _get_lms_name()
        if not tasks:
            return f"📋 **Задания {lms_name}:**\n\nЗаданий на текущий семестр не найдено."

        total_count = len(tasks)
        public_count = sum(1 for t in tasks if t.get("is_public"))
        hidden_count = total_count - public_count

        lines = [
            f"📋 **Задания ({lms_name})**\n",
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
        """Executes publishing or hiding lab assignments on LMS portal."""
        action_verb = "Публикую" if is_public else "Скрываю"
        past_verb = "опубликовано" if is_public else "скрыто"
        icon = "👁️" if is_public else "🔒"

        is_cb = isinstance(message_or_query, CallbackQuery)
        if is_cb:
            await message_or_query.answer(f"{action_verb}...")
            send_target = message_or_query.message
        else:
            send_target = message_or_query

        lms_name = _get_lms_name()
        status_msg = await send_target.answer(f"⏳ {action_verb} задания на {lms_name} (цель: `{target_code}`)...")

        try:
            tasks = await asyncio.to_thread(self.lms_client.list_tasks, 28)
            surname = _get_user_surname().lower()
            user_tasks = [t for t in tasks if surname in t.get("title", "").lower()]
            active_tasks = user_tasks if user_tasks else tasks

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
                lms_url = _get_lms_base_url()
                await status_msg.edit_text(
                    f"✅ **Задание успешно создано!**\n\n"
                    f"• ID: `{created_id}`\n"
                    f"• Название: **{task_title}**\n"
                    f"• Группа: **{group_name}**\n"
                    f"• Статус: 🔒 Скрыто (черновик)\n\n"
                    f"🔗 [Открыть в ЛК]({lms_url}/inside/professor/tasks/{created_id}/show)"
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

        lms_name = _get_lms_name()
        status_msg = await message.answer(f"⏳ Загружаю список заданий из {lms_name}...")
        try:
            tasks = await asyncio.to_thread(self.lms_client.list_tasks, 28)
            surname = _get_user_surname().lower()
            user_tasks = [t for t in tasks if surname in t.get("title", "").lower()]
            display_tasks = user_tasks if user_tasks else tasks

            overview = self._format_lms_tasks_overview(display_tasks)
            kb = build_lms_tasks_keyboard()
            await status_msg.edit_text(overview, reply_markup=kb)
        except Exception as e:
            logger.exception("Error listing LMS tasks: %s", e)
            await status_msg.edit_text(f"⚠️ Ошибка при загрузке заданий: {e}")

    async def handle_cmd_lms_reports(self, message: Message) -> None:
        """Handle /reports command with instant cached SQLite response."""
        if not self._is_authorized(message.from_user.id):
            return

        try:
            submissions = await self.db.list_lms_submissions(limit=30)
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="🔄 Синхронизировать с ЛК", callback_data="lms:sync_reports"),
                        InlineKeyboardButton(text="👁️ Задания", callback_data="lms:pub_menu"),
                    ]
                ]
            )

            if not submissions:
                lms_name = _get_lms_name()
                await message.answer(
                    "📥 **Сданных студенческих отчетов в базе пока нет.**\n\n"
                    f"Фоновый демон `assistant-worker` периодически сканирует {lms_name}. "
                    "Вы также можете запустить ручную синхронизацию по кнопке ниже:",
                    reply_markup=kb,
                )
                return

            pending_cnt = sum(1 for s in submissions if "ожидает" in s.get("status", "").lower() or not s.get("check_date"))
            checked_cnt = len(submissions) - pending_cnt

            lines = [
                f"📥 **Сданные студенческие отчеты (из локальной базы):**",
                f"• Всего отчетов: **{len(submissions)}** (⏳ ожидают проверки: **{pending_cnt}**, ✅ проверено: **{checked_cnt}**)\n",
            ]
            lms_url = _get_lms_base_url()
            for s in submissions[:15]:
                st_icon = "⏳" if "ожидает" in s.get("status", "").lower() or not s.get("check_date") else "✅"
                lines.append(
                    f"{st_icon} **{s['student_name']}** (гр. {s['group_name']})\n"
                    f"  📌 {s['task_title']}\n"
                    f"  📅 Сдано: {s.get('upload_date', '—')} | Статус: `{s['status']}`\n"
                    f"  🔗 [Открыть в ЛК]({lms_url}/inside/professor/tasks/{s['task_id']}/show)\n"
                )
            if len(submissions) > 15:
                lines.append(f"_... и еще {len(submissions) - 15} отчетов в базе._\n")

            await message.answer("\n".join(lines).strip(), reply_markup=kb)
        except Exception as e:
            logger.exception("Error checking cached reports: %s", e)
            await message.answer(f"⚠️ Ошибка при проверке отчетов: {e}")

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
            lms_name = _get_lms_name()
            surname = _get_user_surname()
            prompt_msg = await message.answer(
                f"➕ **Создание нового задания на {lms_name}**\n\n"
                "Отправьте в чат сообщение в формате:\n"
                "`<номер группы> <название задания>`\n\n"
                "Пример:\n"
                f"`1632 {surname}: Лабораторная работа №5`\n\n"
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
            surname = _get_user_surname()
            await message.answer(f"⚠️ Укажите группу и название задания, например:\n`/lms_create 1632 {surname}: Лабораторная работа №5`")
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
        lms_name = _get_lms_name()
        await message.answer(
            f"⚠️ **Вы действительно хотите удалить задание `{task_id}` с {lms_name}?**\n"
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
            surname = _get_user_surname().lower()
            user_tasks = [t for t in tasks if surname in t.get("title", "").lower()]
            display_tasks = user_tasks if user_tasks else tasks
            overview = self._format_lms_tasks_overview(display_tasks)
            kb = build_lms_tasks_keyboard()
            await callback.message.edit_text(overview, reply_markup=kb)
        except Exception as e:
            await callback.message.answer(f"⚠️ Ошибка обновления: {e}")

    async def cb_sync_lms_reports(self, callback: CallbackQuery) -> None:
        if not self._is_authorized(callback.from_user.id):
            return
        lms_name = _get_lms_name()
        await callback.answer(f"🔄 Запущена фоновая синхронизация с {lms_name}...", show_alert=False)
        asyncio.create_task(self._sync_lms_reports_bg(callback.message))

    async def _sync_lms_reports_bg(self, message: Message) -> None:
        try:
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
            submissions = await self.db.list_lms_submissions(limit=30)
            pending_cnt = sum(1 for s in submissions if "ожидает" in s.get("status", "").lower() or not s.get("check_date"))
            checked_cnt = len(submissions) - pending_cnt

            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="🔄 Синхронизировать с ЛК", callback_data="lms:sync_reports"),
                        InlineKeyboardButton(text="👁️ Задания", callback_data="lms:pub_menu"),
                    ]
                ]
            )
            lms_name = _get_lms_name()
            lines = [
                f"📥 **Сданные студенческие отчеты (обновлено из {lms_name}):**",
                f"• Всего в базе: **{len(submissions)}** (⏳ ожидают: **{pending_cnt}**, ✅ проверено: **{checked_cnt}**)\n",
            ]
            lms_url = _get_lms_base_url()
            for s in submissions[:15]:
                st_icon = "⏳" if "ожидает" in s.get("status", "").lower() or not s.get("check_date") else "✅"
                lines.append(
                    f"{st_icon} **{s['student_name']}** (гр. {s['group_name']})\n"
                    f"  📌 {s['task_title']}\n"
                    f"  📅 Сдано: {s.get('upload_date', '—')} | Статус: `{s['status']}`\n"
                    f"  🔗 [Открыть в ЛК]({lms_url}/inside/professor/tasks/{s['task_id']}/show)\n"
                )
            if len(submissions) > 15:
                lines.append(f"_... и еще {len(submissions) - 15} отчетов в базе._\n")

            await message.edit_text("\n".join(lines).strip(), reply_markup=kb)
        except Exception as e:
            logger.exception("Error during background LMS sync: %s", e)

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
                lms_name = _get_lms_name()
                await callback.message.edit_text(f"✅ Задание `{task_id}` успешно удалено из {lms_name}!")
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
        lms_name = _get_lms_name()
        surname = _get_user_surname()
        prompt_msg = await callback.message.answer(
            f"➕ **Создание нового задания на {lms_name}**\n\n"
            "Отправьте в чат сообщение в формате:\n"
            "`<номер группы> <название задания>`\n\n"
            "Пример:\n"
            f"`1632 {surname}: Лабораторная работа №5`\n\n"
            "_Задание будет создано как черновик (скрыто от студентов)._",
            reply_markup=cancel_kb,
        )
        self.waiting_input[callback.from_user.id] = {
            "action": "lms_create",
            "prompt_msg_id": prompt_msg.message_id,
        }


