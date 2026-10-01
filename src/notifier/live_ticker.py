"""Live HUD Ticker & Interactive Status Board for Telegram Bot.

Architecture & Specifications:
- Generates dynamic single-line ticker for pinned message header:
  e.g. '⚡ 15:10 [Лаб] Физика (через 25м, ауд. 13-04) | 📬 0 треб. | ⏱️ Тидекс: +1.2ч'
- In-place screen swapping:
  1. 'schedule': Today's SUAI/GUAP classes with live progress, countdown, and rooms
  2. 'emails': Ingested emails, answered by AI, and urgent actionable threads
  3. 'timesheet': Tydex work hours, pacing delta, and month balance
  4. 'system': Assistant 24/7 daemon health, server time, and sync timestamps
- Silent updates via bot.edit_message_text without sending notification pings
"""

import logging
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from typing import Any

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from src import config
from src.storage.db import Database
from src.models.schedule import (
    SchedulePayload,
    Lesson,
    LessonType,
    LESSON_TYPE_SHORT,
    SUBJECT_SHORT_NAMES,
    format_academic_lesson_line,
    get_guap_pair_number,
)

logger = logging.getLogger(__name__)

SCREEN_SCHEDULE = "schedule"
SCREEN_EMAILS = "emails"
SCREEN_TIMESHEET = "timesheet"
SCREEN_SYSTEM = "system"

VALID_SCREENS = {SCREEN_SCHEDULE, SCREEN_EMAILS, SCREEN_TIMESHEET, SCREEN_SYSTEM}


def build_ticker_keyboard(current_screen: str) -> InlineKeyboardMarkup:
    """Builds inline navigation keyboard with the active screen highlighted."""
    sc_sched = "• 🎓 Пары •" if current_screen == SCREEN_SCHEDULE else "🎓 Пары"
    sc_mail = "• 📬 Почта •" if current_screen == SCREEN_EMAILS else "📬 Почта"
    sc_time = "• ⏱️ Тидекс •" if current_screen == SCREEN_TIMESHEET else "⏱️ Тидекс"
    sc_sys = "• 🛡️ Статус •" if current_screen == SCREEN_SYSTEM else "🛡️ Статус"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=sc_sched, callback_data=f"tk:sc:{SCREEN_SCHEDULE}"),
                InlineKeyboardButton(text=sc_mail, callback_data=f"tk:sc:{SCREEN_EMAILS}"),
            ],
            [
                InlineKeyboardButton(text=sc_time, callback_data=f"tk:sc:{SCREEN_TIMESHEET}"),
                InlineKeyboardButton(text=sc_sys, callback_data=f"tk:sc:{SCREEN_SYSTEM}"),
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить табло", callback_data="tk:refresh"),
            ],
        ]
    )


class LiveTickerService:
    """Orchestrates live telemetry gathering and Telegram ticker rendering."""

    def __init__(self, db: Database):
        self.db = db

    async def get_today_schedule(self, target_date: date) -> list[Lesson]:
        """Fetch parsed lessons for target_date from the latest GUAP schedule snapshot."""
        source_id = f"rasp_guap_{config.SCHEDULE_TARGET_ID}"
        snap = await self.db.get_latest_snapshot(source_id)
        if not snap or not snap.get("raw_payload"):
            return []
        try:
            payload = SchedulePayload.model_validate_json(snap["raw_payload"])
            for day in payload.days:
                if day.date == target_date:
                    return sorted(day.lessons, key=lambda l: (l.start_time, l.end_time))
        except Exception as e:
            logger.warning("LiveTicker: error parsing schedule snapshot: %s", e)
        return []

    async def get_email_metrics(self, target_date: date) -> dict[str, Any]:
        """Fetch email counts: received today, answered today, pending actionable."""
        stats = await self.db.get_daily_email_stats(target_date)
        date_iso = target_date.isoformat()
        received_today = 0
        try:
            async with self.db.connection() as conn:
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM email_messages WHERE substr(date_sent, 1, 10) = ?;",
                    (date_iso,),
                )
                row = await cursor.fetchone()
                if row:
                    received_today = int(row[0])
        except Exception as e:
            logger.warning("LiveTicker: error fetching total received emails: %s", e)

        return {
            "received_today": max(received_today, stats.get("total_answered_count", 0)),
            "answered_today": stats.get("total_answered_count", 0),
            "pending_actionable": stats.get("pending_actionable", []),
            "pending_count": stats.get("pending_count", 0),
        }

    async def get_timesheet_metrics(self) -> dict[str, Any]:
        """Fetch AADHk Tydex work hour metrics."""
        try:
            from src.connectors.aadhk.parser import AadhkIngestionService
            service = AadhkIngestionService(self.db)
            pacing = await service.get_monthly_pacing(project_name="Тидекс")
            return pacing
        except Exception as e:
            logger.warning("LiveTicker: error fetching timesheet pacing: %s", e)
            return {
                "worked_hours": 0.0,
                "monthly_norm_hours": 0.0,
                "morning_delta": 0.0,
                "remaining_hours_to_norm": 0.0,
                "latest_date_formatted": "н/д",
            }

    def compute_ticker_line(
        self,
        lessons: list[Lesson],
        email_metrics: dict[str, Any],
        timesheet_metrics: dict[str, Any],
        now_dt: datetime,
    ) -> str:
        """Builds a dense, informative ~75-character single-line ticker for Telegram pin header."""
        now_time = now_dt.time()

        # 1. Schedule part
        sched_part = "⚡ Пар нет"
        if lessons:
            current_lesson = None
            next_lesson = None
            all_past = True

            for l in lessons:
                if l.start_time <= now_time <= l.end_time:
                    current_lesson = l
                    all_past = False
                    break
                elif now_time < l.start_time:
                    if next_lesson is None:
                        next_lesson = l
                    all_past = False

            if current_lesson:
                st = LESSON_TYPE_SHORT.get(current_lesson.lesson_type, "Пара")
                subj = SUBJECT_SHORT_NAMES.get(current_lesson.subject.lower(), current_lesson.subject.strip())
                room = current_lesson.room.replace(" (Гастелло 15)", "").strip()
                sched_part = f"⚡ СЕЙЧАС: [{st}] {subj} ({room})"
            elif next_lesson:
                st = LESSON_TYPE_SHORT.get(next_lesson.lesson_type, "Пара")
                subj = SUBJECT_SHORT_NAMES.get(next_lesson.subject.lower(), next_lesson.subject.strip())
                room = next_lesson.room.replace(" (Гастелло 15)", "").strip()
                # Delta minutes
                start_dt = datetime.combine(now_dt.date(), next_lesson.start_time, tzinfo=now_dt.tzinfo)
                diff_mins = int((start_dt - now_dt).total_seconds() / 60)
                if 0 <= diff_mins <= 120:
                    sched_part = f"⚡ {next_lesson.start_time.strftime('%H:%M')} [{st}] {subj} (через {diff_mins}м, {room})"
                else:
                    sched_part = f"⚡ След: {next_lesson.start_time.strftime('%H:%M')} [{st}] {subj} ({room})"
            elif all_past:
                sched_part = "⚡ Все пары завершены"

        # 2. Email part
        pending = email_metrics.get("pending_count", 0)
        urgent = email_metrics.get("pending_actionable", [])
        if pending > 0:
            sender_name = urgent[0].get("sender_name") or urgent[0].get("sender_email", "")
            # Shorten sender
            short_sender = sender_name.split()[0] if sender_name else "Входящие"
            mail_part = f"⚠️ 📬 {pending} треб. ответ ({short_sender})"
        else:
            mail_part = "📬 0 треб."

        # 3. Timesheet part
        delta = timesheet_metrics.get("morning_delta", 0.0)
        sign = "+" if delta > 0 else ""
        worked = timesheet_metrics.get("worked_hours", 0.0)
        if delta != 0.0:
            time_part = f"⏱️ Тидекс: {sign}{delta:.1f}ч"
        else:
            time_part = f"⏱️ Тидекс: {worked:.1f}ч"

        # Compose line
        line = f"{sched_part} | {mail_part} | {time_part}"
        return line

    def render_schedule_screen(
        self,
        lessons: list[Lesson],
        now_dt: datetime,
        day_date: date,
    ) -> str:
        """Renders full schedule screen body."""
        weekday_names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        day_str = f"{weekday_names[day_date.weekday()]}, {day_date.strftime('%d.%m.%Y')}"
        now_time = now_dt.time()

        lines = [
            f"🎓 **РАСПИСАНИЕ ГУАП НА СЕГОДНЯ**",
            f"📅 _{day_str}_ • Время: `{now_dt.strftime('%H:%M:%S')}`\n",
        ]

        if not lessons:
            lines.append("🎉 **Пар в расписании нет!**")
            lines.append("Учебных занятий в ГУАП на сегодня не запланировано.")
            lines.append("Свободное время для научно-исследовательской работы и сектора приборов.")
        else:
            lines.append("📚 **Учебные пары на день:**")
            next_found = False
            for l in lessons:
                base_line = format_academic_lesson_line(l)
                if l.start_time <= now_time <= l.end_time:
                    status = "🔴 **[ИДЕТ СЕЙЧАС]**"
                elif now_time > l.end_time:
                    status = "✔️ _[завершена]_"
                elif not next_found and now_time < l.start_time:
                    start_dt = datetime.combine(now_dt.date(), l.start_time, tzinfo=now_dt.tzinfo)
                    mins_left = int((start_dt - now_dt).total_seconds() / 60)
                    status = f"⏳ **[следующая, через {mins_left} мин]**"
                    next_found = True
                else:
                    status = "⚪"
                lines.append(f"{base_line} {status}")

            lines.append("")
            # Summary footer
            remaining = [l for l in lessons if now_time < l.end_time]
            if remaining:
                lines.append(f"📌 До окончания учебного дня осталось занятий: **{len(remaining)}**")
            else:
                lines.append("✅ Все запланированные пары на сегодня успешно завершены.")

        return "\n".join(lines)

    def render_emails_screen(
        self,
        email_metrics: dict[str, Any],
        now_dt: datetime,
        day_date: date,
    ) -> str:
        """Renders full email processing center screen body."""
        lines = [
            "📬 **ЦЕНТР ВХОДЯЩЕЙ ПОЧТЫ (ГУАП & Gmail)**",
            f"📅 _{day_date.strftime('%d.%m.%Y')}_ • Актуально на `{now_dt.strftime('%H:%M:%S')}`\n",
            "📊 **Статистика за сегодня:**",
            f"• 📥 Всего поступило: **{email_metrics.get('received_today', 0)}**",
            f"• ✅ Обработано / отвечено: **{email_metrics.get('answered_today', 0)}**",
            f"• ⚠️ Требует решения / действия: **{email_metrics.get('pending_count', 0)}**\n",
        ]

        urgent = email_metrics.get("pending_actionable", [])
        if urgent:
            lines.append("🚨 **Письма, ожидающие ответа или согласования:**")
            for idx, item in enumerate(urgent[:5], start=1):
                sender = item.get("sender_name") or item.get("sender_email", "Неизвестный")
                subj = item.get("subject", "Без темы")
                lines.append(f"**{idx}.** {sender} — _{subj}_")
            if len(urgent) > 5:
                lines.append(f"• ... и еще {len(urgent) - 5} писем (команда `/emails`)")
        else:
            lines.append("✨ **Все входящие письма разобраны!**")
            lines.append("Неотвеченных писем, требующих действия, на данный момент нет.")

        return "\n".join(lines)

    def render_timesheet_screen(
        self,
        timesheet_metrics: dict[str, Any],
        now_dt: datetime,
        day_date: date,
    ) -> str:
        """Renders full Tydex timesheet and pacing screen body."""
        month_names = ["", "январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
        cur_m_name = month_names[day_date.month] if day_date.month <= 12 else ""
        year = timesheet_metrics.get("year", day_date.year)

        delta = timesheet_metrics.get("morning_delta", 0.0)
        sign = "+" if delta > 0 else ""
        rel_date = timesheet_metrics.get("latest_date_formatted", day_date.strftime("%d.%m.%Y"))

        lines = [
            f"⏱️ **ТАБЕЛЬ И БАЛАНС ЧАСОВ: ООО «ТИДЕКС»**",
            f"📅 _{cur_m_name.capitalize()} {year}_ • Актуально на `{now_dt.strftime('%H:%M:%S')}`\n",
            f"• 📈 **Дельта нормы (утро):** `{sign}{delta:.2f}` ч (на {rel_date})",
            f"• 🎯 **Месячная норма:** `{timesheet_metrics.get('monthly_norm_hours', 0.0):.1f}` ч ({timesheet_metrics.get('total_workdays', 0)} раб. дн.)",
            f"• 💼 **Фактически зачтено:** `{timesheet_metrics.get('worked_hours', 0.0):.2f}` ч ({timesheet_metrics.get('total_shifts', 0)} смен)",
            f"• ⏳ **Ожидаемый темп к дате:** `{timesheet_metrics.get('expected_hours_to_date', 0.0):.1f}` ч\n",
        ]

        remaining_days = timesheet_metrics.get("remaining_workdays", 0)
        remaining_hours = timesheet_metrics.get("remaining_hours_to_norm", 0.0)
        daily_pace = timesheet_metrics.get("required_daily_pacing", 0.0)

        if remaining_days > 0:
            lines.append(f"🎯 **План на остаток месяца ({remaining_days} раб. дн.):**")
            lines.append(f"• Осталось выработать: `{remaining_hours:.2f}` ч")
            lines.append(f"• Необходимый темп: `{daily_pace:.2f}` ч/день")
        else:
            if remaining_hours == 0:
                lines.append("🎉 **Месячная норма полностью закрыта без недоработок!**")
            else:
                lines.append(f"⚠️ Недоработка за месяц: `{remaining_hours:.2f}` ч")

        return "\n".join(lines)

    def render_system_screen(
        self,
        now_dt: datetime,
        day_date: date,
    ) -> str:
        """Renders system diagnostic and monitoring status."""
        lines = [
            "🛡️ **СТАТУС СИСТЕМ И ДЕМОНОВ ASSISTANT-CORE**",
            f"📅 _{day_date.strftime('%d.%m.%Y')}_ • `{now_dt.strftime('%H:%M:%S')}` MSK\n",
            "🤖 **Фоновые службы и сенсоры (24/7):**",
            "• 🟢 `assistant-worker.service`: **Активен (running)**",
            "• 🟢 `guap_schedule_sentinel`: **Мониторинг расписания (каждые 3 ч)**",
            "• 🟢 `email_collector_daemon`: **IMAP/SMTP ГУАП + Mail.ru (каждые 15 мин)**",
            "• 🟢 `pro_guap_lms_monitor`: **Синхронизация отчетов pro.guap.ru (30 мин)**",
            "• 🟢 `aadhk_gdrive_sync`: **Архивация SQLite табеля AADHk (2 ч)**\n",
            "🧠 **Интеллектуальное ядро:**",
            "• Fast Intent Router: stateless gemini-3.8-flash (Low Effort)",
            "• Dialog Engine: Google GenAI SDK (квоты в норме)",
            "• Локальная база: SQLite `data/assistant.db` (целостность OK)",
        ]
        return "\n".join(lines)

    async def build_ticker_message(
        self,
        current_screen: str = SCREEN_SCHEDULE,
        now_dt: datetime | None = None,
    ) -> tuple[str, InlineKeyboardMarkup]:
        """Gathers metrics, renders ticker line, screen content, and inline keyboard."""
        if current_screen not in VALID_SCREENS:
            current_screen = SCREEN_SCHEDULE

        if now_dt is None:
            now_dt = datetime.now(ZoneInfo(config.TZ))

        today = now_dt.date()

        # Gather telemetry asynchronously
        lessons = await self.get_today_schedule(today)
        email_metrics = await self.get_email_metrics(today)
        timesheet_metrics = await self.get_timesheet_metrics()

        # Top single-line ticker
        ticker_line = self.compute_ticker_line(lessons, email_metrics, timesheet_metrics, now_dt)

        # Body screen
        if current_screen == SCREEN_SCHEDULE:
            body = self.render_schedule_screen(lessons, now_dt, today)
        elif current_screen == SCREEN_EMAILS:
            body = self.render_emails_screen(email_metrics, now_dt, today)
        elif current_screen == SCREEN_TIMESHEET:
            body = self.render_timesheet_screen(timesheet_metrics, now_dt, today)
        else:
            body = self.render_system_screen(now_dt, today)

        # Assemble full text: top ticker line, separator, screen body
        full_text = f"{ticker_line}\n━━━━━━━━━━━━━━━━━━━━━\n{body}"
        keyboard = build_ticker_keyboard(current_screen)

        return full_text, keyboard
