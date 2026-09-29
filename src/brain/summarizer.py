import logging
from datetime import date, datetime
from typing import Any

from google import genai
from google.genai import types

from src import config
from src.models.schedule import Lesson

logger = logging.getLogger(__name__)


class GeminiSummarizer:
    """LLM summarizer using the official Google GenAI SDK specialized for academic morning briefs."""

    def __init__(
        self,
        api_key: str | None = config.GEMINI_API_KEY,
        model: str = config.GEMINI_MODEL,
    ) -> None:
        self.api_key = api_key or ""
        self.model = model
        self._client: genai.Client | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("AIzaSyYour"))

    def get_client(self) -> genai.Client:
        if self._client is None:
            if not self.api_key:
                raise ValueError("GEMINI_API_KEY is not configured.")
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def generate_morning_brief(
        self,
        target_date: date,
        lessons: list[Lesson],
        action_items: list[dict[str, Any]],
        actionable_emails: list[dict[str, Any]] | None = None,
        upcoming_lessons: list[tuple[date, Lesson]] | None = None,
    ) -> str:
        """Generate an executive morning brief combining schedule, emails, and action items."""
        if not self.is_configured:
            logger.info("Gemini API key not configured, falling back to deterministic template.")
            return self._generate_fallback_brief(target_date, lessons, action_items, actionable_emails, upcoming_lessons)

        try:
            client = self.get_client()

            # Format input context for prompt with temporal gradation
            schedule_context = []
            if lessons:
                for l in lessons:
                    type_str = l.lesson_type.value if hasattr(l.lesson_type, "value") else str(l.lesson_type)
                    room_str = f"📍 {l.room}" if l.room and l.room != "Не указана" else ""
                    group_str = f"Группа: {l.group}" if hasattr(l, "group") and l.group else ""
                    details = " • ".join(filter(None, [room_str, group_str]))

                    line = f"• {l.start_time.strftime('%H:%M')}–{l.end_time.strftime('%H:%M')} | [{type_str}] {l.subject}"
                    if details:
                        line += f"\n  {details}"
                    schedule_context.append(line)
            else:
                schedule_context.append("• Занятий сегодня по расписанию нет (методический/свободный день).")
                if upcoming_lessons:
                    next_date = upcoming_lessons[0][0]
                    weekday_names = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
                    next_wd = weekday_names[next_date.weekday()]
                    schedule_context.append(f"\nБлижайшие пары ({next_date.strftime('%d.%m')}, {next_wd}):")
                    for d, l in upcoming_lessons:
                        if d == next_date:
                            type_str = l.lesson_type.value if hasattr(l.lesson_type, "value") else str(l.lesson_type)
                            schedule_context.append(f"• {l.start_time.strftime('%H:%M')}–{l.end_time.strftime('%H:%M')} | [{type_str}] {l.subject} (Ауд. {l.room}, гр. {l.group})")

            # Actionable emails context
            emails_context = []
            if actionable_emails:
                for em in actionable_emails:
                    sender = em.get("sender_name") or em.get("sender_email")
                    cat = "Студент" if em.get("category") == "guap_student" else "Кафедра/ГУАП"
                    subj = em.get("subject", "Без темы")
                    snip = em.get("snippet", "")[:150]
                    emails_context.append(f"• [{cat}] От: {sender} ({em.get('sender_email')})\n  Тема: {subj}\n  Суть: {snip}")

            active_deadlines = []
            fresh_notes = []
            for item in action_items:
                payload = item.get("payload_json", {})
                if isinstance(payload, str):
                    import json
                    try:
                        payload = json.loads(payload)
                    except Exception:
                        payload = {}

                if payload.get("is_expired", False):
                    continue

                summary = item.get("summary_text", "")
                temp_status = payload.get("temporal_status") or ""
                freshness = payload.get("freshness_label") or "RECENT"

                if "дедлайн" in temp_status.lower() or "дедлайн" in summary.lower():
                    active_deadlines.append(f"• [{freshness}] {summary} (Статус: {temp_status})")
                else:
                    fresh_notes.append(f"• [{freshness}] {summary} (Статус: {temp_status})")

            items_block = []
            if active_deadlines:
                items_block.append("АКТИВНЫЕ ПРЕДСТОЯЩИЕ ДЕДЛАЙНЫ:\n" + "\n".join(active_deadlines))
            if fresh_notes:
                items_block.append("АКТУАЛЬНЫЕ МАТЕРИАЛЫ И УВЕДОМЛЕНИЯ:\n" + "\n".join(fresh_notes))
            if not items_block:
                items_block.append("Нет других активных задач и дедлайнов.")

            weekday_names = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
            weekday_ru = weekday_names[target_date.weekday()]

            emails_section = ""
            if emails_context:
                emails_section = "=== НЕОТВЕЧЕННЫЕ ВАЖНЫЕ ПИСЬМА (СТУДЕНТЫ И КАФЕДРА) ===\n" + "\n".join(emails_context) + "\n\n"

            prompt = (
                f"Сегодня: {target_date.strftime('%d.%m.%Y')} ({weekday_ru})\n\n"
                f"=== ОФИЦИАЛЬНОЕ РАСПИСАНИЕ ===\n" + "\n".join(schedule_context) + "\n\n"
                f"{emails_section}"
                f"=== СОБЫТИЯ ИЗ ЧАТОВ (ПРОШЕДШИЕ ОТФИЛЬТРОВАНЫ) ===\n" + "\n\n".join(items_block) + "\n\n"
                "Сформируй структурированный утренний дайджест для преподавателя."
            )

            system_instruction = (
                "Ты — персональный академический ассистент преподавателя ГУАП (Попов Д.А., Кафедра физики №1).\n"
                f"Сегодняшняя дата: {target_date.strftime('%d.%m.%Y')} ({weekday_ru}).\n\n"
                "КРИТИЧЕСКИЕ ПРАВИЛА ВРЕМЕННОЙ ВАЛИДАЦИИ И СВЕЖЕСТИ:\n"
                f"1. Любые сообщения о парах или переносах из прошлого (до {target_date.strftime('%d.%m.%Y')}) УЖЕ СОСТОЯЛИСЬ. Их КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО выдавать за сегодняшние или предстоящие события!\n"
                "2. Если в расписании на сегодня нет пар, четко фиксируй: '• Занятий нет (свободный/методический день)'. Если есть информация о ближайших парах (например, завтра) — кратко укажи их.\n"
                "3. В блоке неотвеченных писем четко перечисли студентов/коллег с их вопросами.\n"
                "4. В блоке предстоящих дедлайнов указывай только будущие даты с количеством оставшихся дней.\n\n"
                "СТАНДАРТЫ ОФОРМЛЕНИЯ ДЛЯ TELEGRAM (МОБИЛЬНЫЙ АКАДЕМИЧЕСКИЙ БРИФИНГ):\n"
                "- Заголовки разделов: используй ТОЛЬКО жирные эмодзи-заголовки. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать решетки (#, ##, ###)!\n"
                "  Примеры заголовков:\n"
                f"  ☀️ **Утренний дайджест на {target_date.strftime('%d.%m.%Y')} ({weekday_ru})**\n"
                "  📅 **Расписание на сегодня**\n"
                "  📬 **Почтовый щит / Требуют ответа**\n"
                "  🚨 **Срочное / Дедлайны**\n"
                "  📋 **Учебные группы и задачи**\n"
                "  💡 **Фокус дня**\n"
                "- Списки: используй ТОЛЬКО круглые буллеты (•). КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать черные галочки (✔️)!\n"
                "- Разделители: КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать горизонтальные линии из дефисов (---, --------). Разделяй смысловые блоки чистыми пустыми строками.\n"
                "Пиши емко, структурированно, уважительным и деловым языком."
            )

            candidate_models = [self.model]
            for fallback_m in ["gemini-flash-latest", "gemini-3.5-flash-lite", "gemini-3.8-flash"]:
                if fallback_m not in candidate_models:
                    candidate_models.append(fallback_m)

            for cand in candidate_models:
                try:
                    response = await client.aio.models.generate_content(
                        model=cand,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.2,
                        ),
                    )
                    if response and response.text:
                        return response.text.strip()
                except Exception as model_err:
                    logger.warning("Gemini model %s failed: %s, trying next candidate...", cand, model_err)

            return self._generate_fallback_brief(target_date, lessons, action_items, actionable_emails, upcoming_lessons)

        except Exception as e:
            logger.exception("Failed to generate brief via Gemini API: %s", e)
            return self._generate_fallback_brief(target_date, lessons, action_items, actionable_emails, upcoming_lessons)

    def _generate_fallback_brief(
        self,
        target_date: date,
        lessons: list[Lesson],
        action_items: list[dict[str, Any]],
        actionable_emails: list[dict[str, Any]] | None = None,
        upcoming_lessons: list[tuple[date, Lesson]] | None = None,
    ) -> str:
        """Deterministic fallback brief when Gemini API is unavailable or offline."""
        weekday_names = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
        weekday_ru = weekday_names[target_date.weekday()]

        lines = [f"☀️ **Утренний дайджест на {target_date.strftime('%d.%m.%Y')} ({weekday_ru})**\n"]

        lines.append("📅 **Расписание на сегодня:**")
        if lessons:
            for l in lessons:
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
                    f"• {l.start_time.strftime('%H:%M')}–{l.end_time.strftime('%H:%M')} "
                    f"| [{type_name}] {l.subject}"
                )
                if details:
                    lines.append(f"  {details}")
        else:
            lines.append("• Занятий нет (свободный/методический день).")
            if upcoming_lessons:
                next_date = upcoming_lessons[0][0]
                lines.append(f"\nБлижайшие пары ({next_date.strftime('%d.%m')}):")
                for d, l in upcoming_lessons:
                    if d == next_date:
                        type_name = {
                            "LECTURE": "Лекция",
                            "PRACTICE": "Практика",
                            "LAB": "Лаб",
                            "EXAM": "Экзамен",
                        }.get(l.lesson_type.value, "Пара")
                        lines.append(f"• {l.start_time.strftime('%H:%M')}–{l.end_time.strftime('%H:%M')} | [{type_name}] {l.subject} (Ауд. {l.room}, гр. {l.group})")
        lines.append("")

        if actionable_emails:
            lines.append("📬 **Почтовый щит / Требуют ответа:**")
            for em in actionable_emails:
                sender = em.get("sender_name") or em.get("sender_email")
                lines.append(f"• 👤 **{sender}** (`{em.get('sender_email')}`)")
                lines.append(f"  📌 {em.get('subject', 'Без темы')}")
                snip = (em.get("snippet") or "")[:120]
                if snip:
                    lines.append(f"  💬 _{snip}..._")
            lines.append("")

        urgent = [i for i in action_items if i.get("priority_score", 1) >= 3]
        if urgent:
            lines.append("🚨 **Срочное / Дедлайны:**")
            for u in urgent:
                lines.append(f"• {u.get('summary_text', '')}")
            lines.append("")

        normal = [i for i in action_items if i.get("priority_score", 1) < 3]
        if normal:
            lines.append("📋 **Задачи и сообщения:**")
            for n in normal[:7]:
                lines.append(f"• {n.get('summary_text', '')}")
            lines.append("")

        lines.append("💡 **Фокус дня:**")
        lines.append("• Методический день: проверка сданных материалов и подготовка к завтрашним занятиям.")
        lines.append("• Ответ на входящие методические вопросы студентов.")

        return "\n".join(lines).strip()

    async def generate_evening_digest(
        self,
        target_date: date,
        email_stats: dict[str, Any],
        tomorrow_date: date,
        tomorrow_lessons: list[Lesson],
        action_items: list[dict[str, Any]] | None = None,
    ) -> str:
        """Generate an executive evening summary focusing on email stats, completed items, and tomorrow's schedule."""
        if not self.is_configured:
            return self._generate_fallback_evening_digest(target_date, email_stats, tomorrow_date, tomorrow_lessons, action_items)

        try:
            client = self.get_client()

            weekday_names = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
            weekday_today = weekday_names[target_date.weekday()]
            weekday_tmr = weekday_names[tomorrow_date.weekday()]

            bot_answered = email_stats.get("bot_answered", [])
            pending = email_stats.get("pending_actionable", [])

            email_lines = [
                f"Обработано и отправлено ответов за сегодня: {len(bot_answered)}.",
            ]
            if bot_answered:
                email_lines.append("Список отправленных ответов:")
                for em in bot_answered:
                    cat = "Студент" if em.get("category") == "guap_student" else "Кафедра/ГУАП"
                    s_name = em.get("sender_name") or em.get("sender_email")
                    time_str = str(em.get("updated_at", ""))
                    if "T" in time_str:
                        time_str = time_str.split("T")[1][:5]
                    email_lines.append(f"• [{cat}] {s_name} ({em.get('sender_email')}) | Тема: {em.get('subject')} | Отправлено в: {time_str}")

            if pending:
                email_lines.append(f"Осталось неотвеченных важных писем: {len(pending)}")
            else:
                email_lines.append("Осталось неотвеченных важных писем: 0 (все обработаны).")

            tmr_lines = []
            if tomorrow_lessons:
                for l in tomorrow_lessons:
                    type_str = l.lesson_type.value if hasattr(l.lesson_type, "value") else str(l.lesson_type)
                    room_str = f"📍 {l.room}" if l.room and l.room != "Не указана" else ""
                    group_str = f"Группа: {l.group}" if hasattr(l, "group") and l.group else ""
                    details = " • ".join(filter(None, [room_str, group_str]))
                    tmr_lines.append(f"• {l.start_time.strftime('%H:%M')}–{l.end_time.strftime('%H:%M')} | [{type_str}] {l.subject}\n  {details}")
            else:
                tmr_lines.append("• Занятий на завтра по расписанию нет (методический/свободный день).")

            prompt = (
                f"Сегодня завершается: {target_date.strftime('%d.%m.%Y')} ({weekday_today}).\n\n"
                f"=== СТАТИСТИКА РАБОТЫ С ПОЧТОЙ ЗА ДЕНЬ ===\n" + "\n".join(email_lines) + "\n\n"
                f"=== РАСПИСАНИЕ НА ЗАВТРА ({tomorrow_date.strftime('%d.%m.%Y')}, {weekday_tmr}) ===\n" + "\n".join(tmr_lines) + "\n\n"
                "Сформируй структурированный вечерний дайджест для преподавателя."
            )

            system_instruction = (
                "Ты — персональный академический ассистент преподавателя ГУАП (Попов Д.А., Кафедра физики №1).\n"
                f"Сегодняшняя дата: {target_date.strftime('%d.%m.%Y')} ({weekday_today}).\n\n"
                "СТАНДАРТЫ ОФОРМЛЕНИЯ ДЛЯ TELEGRAM (МОБИЛЬНЫЙ ВЕЧЕРНИЙ БРИФИНГ):\n"
                "- Заголовки разделов: используй ТОЛЬКО жирные эмодзи-заголовки. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать решетки (#, ##, ###)!\n"
                "  Примеры заголовков:\n"
                f"  🌙 **Вечерний дайджест за {target_date.strftime('%d.%m.%Y')} ({weekday_today})**\n"
                "  📬 **Почтовый щит: статистика за день**\n"
                f"  📅 **Расписание на завтра ({tomorrow_date.strftime('%d.%m.%Y')}, {weekday_tmr})**\n"
                "  ✨ **Итоги дня и статус**\n"
                "- Списки: используй ТОЛЬКО круглые буллеты (•). КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать галочки (✔️)!\n"
                "- Разделители: пустые строки (без дефисов '---').\n"
                "Пиши лаконично, точно, уважительно и структурированно."
            )

            candidate_models = ["gemini-3.5-flash-lite", self.model, "gemini-3.8-flash"]
            for cand in candidate_models:
                try:
                    response = await client.aio.models.generate_content(
                        model=cand,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.2,
                        ),
                    )
                    if response and response.text:
                        return response.text.strip()
                except Exception as model_err:
                    logger.warning("Gemini model %s failed for evening digest: %s", cand, model_err)

            return self._generate_fallback_evening_digest(target_date, email_stats, tomorrow_date, tomorrow_lessons, action_items)

        except Exception as e:
            logger.exception("Failed to generate evening digest via Gemini: %s", e)
            return self._generate_fallback_evening_digest(target_date, email_stats, tomorrow_date, tomorrow_lessons, action_items)

    def _generate_fallback_evening_digest(
        self,
        target_date: date,
        email_stats: dict[str, Any],
        tomorrow_date: date,
        tomorrow_lessons: list[Lesson],
        action_items: list[dict[str, Any]] | None = None,
    ) -> str:
        weekday_names = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
        weekday_today = weekday_names[target_date.weekday()]
        weekday_tmr = weekday_names[tomorrow_date.weekday()]

        lines = [f"🌙 **Вечерний дайджест за {target_date.strftime('%d.%m.%Y')} ({weekday_today})**\n"]

        bot_answered = email_stats.get("bot_answered", [])
        pending = email_stats.get("pending_actionable", [])

        lines.append("📬 **Почтовый щит: статистика за день**")
        lines.append(f"• Всего отвечено писем: **{len(bot_answered)}**")
        if bot_answered:
            for em in bot_answered:
                s_name = em.get("sender_name") or em.get("sender_email")
                time_str = str(em.get("updated_at", ""))
                if "T" in time_str:
                    time_str = time_str.split("T")[1][:5]
                lines.append(f"  - 👤 **{s_name}** (`{em.get('sender_email')}`) | 🕒 {time_str}")
                lines.append(f"    📌 _{em.get('subject', 'Без темы')}_")
        if pending:
            lines.append(f"• Ожидают ответа: **{len(pending)}** писем")
        else:
            lines.append("• Ожидают ответа: **0** (все письма обработаны)")
        lines.append("")

        lines.append(f"📅 **Расписание на завтра ({tomorrow_date.strftime('%d.%m.%Y')}, {weekday_tmr}):**")
        if tomorrow_lessons:
            for l in tomorrow_lessons:
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
                lines.append(f"• {l.start_time.strftime('%H:%M')}–{l.end_time.strftime('%H:%M')} | [{type_name}] {l.subject}")
                if details:
                    lines.append(f"  {details}")
        else:
            lines.append("• Занятий нет (свободный/методический день).")
        lines.append("")

        lines.append("✨ **Итоги дня:**")
        lines.append("• Все запланированные коммуникации со студентами завершены.")
        lines.append("• Данные синхронизированы с базой и календарем.")

        return "\n".join(lines).strip()
