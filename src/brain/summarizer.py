import logging
from datetime import date, datetime
from typing import Any

from google import genai
from google.genai import types

from src import config
from src.models.schedule import Lesson, format_academic_lesson_line
from src.persona.models import PersonaConfigError
from src.persona.prompts import render_prompt
from src.security.airgap import is_nda_email, mask_nda_email_data

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
        timesheet_pacing: dict[str, Any] | None = None,
    ) -> str:
        """Generate an executive morning brief combining schedule, emails, and action items."""
        if actionable_emails:
            actionable_emails = [
                mask_nda_email_data(e) if is_nda_email(e) else e
                for e in actionable_emails
            ]

        if not self.is_configured:
            logger.info("Gemini API key not configured, falling back to deterministic template.")
            return self._generate_fallback_brief(target_date, lessons, action_items, actionable_emails, upcoming_lessons, timesheet_pacing)

        try:
            client = self.get_client()

            # 1. Format schedule with academic pair numbers (e.g. '2) 11:10 • [Лаб] Физика (гр. 1632, ауд. 31-04б)')
            schedule_context = []
            if lessons:
                for l in lessons:
                    schedule_context.append(format_academic_lesson_line(l))
            else:
                schedule_context.append("• Занятий сегодня по расписанию нет (методический/свободный день).")
                if upcoming_lessons:
                    next_date = upcoming_lessons[0][0]
                    weekday_names = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
                    next_wd = weekday_names[next_date.weekday()]
                    schedule_context.append(f"\nБлижайшие пары ({next_date.strftime('%d.%m')}, {next_wd}):")
                    for d, l in upcoming_lessons:
                        if d == next_date:
                            schedule_context.append(format_academic_lesson_line(l))

            # 2. Actionable emails summary context
            emails_section = ""
            if actionable_emails:
                stud_cnt = sum(1 for e in actionable_emails if e.get("category") == "guap_student")
                dept_cnt = sum(1 for e in actionable_emails if e.get("category") == "guap_dept")
                emails_section = (
                    f"=== СВОДКА ПО ВХОДЯЩЕЙ ПОЧТЕ ===\n"
                    f"Всего неотвеченных писем, требующих действия: {len(actionable_emails)} (студенты: {stud_cnt}, кафедра: {dept_cnt}).\n"
                    f"Команда детального разбора для Telegram: /emails\n\n"
                )

            # 3. Categorize action items: Dedicated OPD Messengers vs Deadlines vs Notes
            opd_messenger_items = []
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
                src_type = item.get("source_type") or ""
                temp_status = payload.get("temporal_status") or ""

                # Check if item is from student Telegram groups (ОПД)
                if src_type in ("telegram_group", "channel") or any(g in summary for g in ("м631к", "м531", "М631K", "М631к")):
                    clean_sum = summary
                    for prefix in ("[м631к Основы проектной деятельности]", "[м531 Основы проектной деятельности]", "[М631K]"):
                        clean_sum = clean_sum.replace(prefix, "").strip()
                    for tag in ("[SCHEDULE_CHANGE]", "[DOCUMENT/LINK]", "[Сообщение отправлено сегодня]"):
                        clean_sum = clean_sum.replace(tag, "").strip()
                    # Add back short group tag
                    grp_tag = "м631к" if "м631к" in summary else ("м531" if "м531" in summary else "ОПД")
                    opd_messenger_items.append(f"[{grp_tag}] {clean_sum}")
                elif "дедлайн" in temp_status.lower() or "дедлайн" in summary.lower():
                    active_deadlines.append(f"{summary} (Статус: {temp_status})")
                else:
                    fresh_notes.append(f"{summary} (Статус: {temp_status})")

            # 4. Timesheet section
            timesheet_section = ""
            if timesheet_pacing:
                m_delta = timesheet_pacing.get("morning_delta", 0.0)
                m_sign = "+" if m_delta > 0 else ""
                rel_d = timesheet_pacing.get("latest_date_formatted", "сегодня")
                timesheet_section = (
                    f"=== ТАБЕЛЬ И БАЛАНС ЧАСОВ «ТИДЕКС» ===\n"
                    f"Дельта нормы на утро: {m_sign}{m_delta:.1f} ч (актуально на {rel_d})\n\n"
                )

            # 5. Messenger summary section
            messenger_section = "=== СВОДКА ПО МЕССЕНДЖЕРАМ (ТЕЛЕГРАМ ГРУППЫ ОПД) ===\n"
            if opd_messenger_items:
                messenger_section += "\n".join(f"• {it}" for it in opd_messenger_items)
            else:
                messenger_section += "• В студенческих чатах (м531, м631к, М631К) срочных вопросов нет."
            messenger_section += "\n\n"

            items_block = []
            if active_deadlines:
                items_block.append("АКТИВНЫЕ ПРЕДСТОЯЩИЕ ДЕДЛАЙНЫ:\n" + "\n".join(f"• {d}" for d in active_deadlines))
            if fresh_notes:
                items_block.append("АКТУАЛЬНЫЕ МАТЕРИАЛЫ И УВЕДОМЛЕНИЯ:\n" + "\n".join(f"• {n}" for n in fresh_notes))

            weekday_names = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
            weekday_ru = weekday_names[target_date.weekday()]

            prompt = (
                f"Сегодня: {target_date.strftime('%d.%m.%Y')} ({weekday_ru})\n\n"
                f"=== ОФИЦИАЛЬНОЕ РАСПИСАНИЕ ===\n" + "\n".join(schedule_context) + "\n\n"
                f"{timesheet_section}"
                f"{emails_section}"
                f"{messenger_section}"
                f"=== ПРОЧИЕ СОБЫТИЯ И ДЕДЛАЙНЫ ===\n" + ("\n\n".join(items_block) if items_block else "Нет активных дедлайнов.") + "\n\n"
                "Сформируй структурированный утренний дайджест для преподавателя."
            )

            system_instruction = render_prompt(
                "morning_brief",
                date_str=target_date.strftime("%d.%m.%Y"),
                weekday=weekday_ru,
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

            return self._generate_fallback_brief(target_date, lessons, action_items, actionable_emails, upcoming_lessons, timesheet_pacing)

        except PersonaConfigError as e:
            logger.error("Ошибка конфигурации персоны при генерации утреннего дайджеста: %s", e)
            return self._generate_fallback_brief(target_date, lessons, action_items, actionable_emails, upcoming_lessons, timesheet_pacing)
        except Exception as e:
            logger.exception("Failed to generate brief via Gemini API: %s", e)
            return self._generate_fallback_brief(target_date, lessons, action_items, actionable_emails, upcoming_lessons, timesheet_pacing)

    def _generate_fallback_brief(
        self,
        target_date: date,
        lessons: list[Lesson],
        action_items: list[dict[str, Any]],
        actionable_emails: list[dict[str, Any]] | None = None,
        upcoming_lessons: list[tuple[date, Lesson]] | None = None,
        timesheet_pacing: dict[str, Any] | None = None,
    ) -> str:
        """Deterministic fallback brief when Gemini API is unavailable or offline."""
        weekday_names = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
        weekday_ru = weekday_names[target_date.weekday()]

        lines = [f"☀️ **Утренний дайджест на {target_date.strftime('%d.%m.%Y')} ({weekday_ru})**\n"]

        lines.append("📅 **Расписание на сегодня:**")
        if lessons:
            for l in lessons:
                lines.append(format_academic_lesson_line(l))
        else:
            lines.append("• Занятий нет (свободный/методический день).")
            if upcoming_lessons:
                next_date = upcoming_lessons[0][0]
                lines.append(f"\nБлижайшие пары ({next_date.strftime('%d.%m')}):")
                for d, l in upcoming_lessons:
                    if d == next_date:
                        lines.append(format_academic_lesson_line(l))
        lines.append("")

        if timesheet_pacing:
            m_delta = timesheet_pacing.get("morning_delta", 0.0)
            m_sign = "+" if m_delta > 0 else ""
            rel_d = timesheet_pacing.get("latest_date_formatted", "сегодня")
            lines.append("⏱️ **Табель «Тидекс»:**")
            lines.append(f"• Дельта нормы на утро: `{m_sign}{m_delta:.1f}` ч (актуально на {rel_d})\n")

        if actionable_emails:
            stud_cnt = sum(1 for e in actionable_emails if e.get("category") == "guap_student")
            dept_cnt = sum(1 for e in actionable_emails if e.get("category") == "guap_dept")
            other_cnt = len(actionable_emails) - stud_cnt - dept_cnt
            breakdown = []
            if stud_cnt:
                breakdown.append(f"студенты: {stud_cnt}")
            if dept_cnt:
                breakdown.append(f"кафедра: {dept_cnt}")
            if other_cnt:
                breakdown.append(f"прочие: {other_cnt}")
            b_str = f" ({', '.join(breakdown)})" if breakdown else ""
            lines.append("📬 **Почтовый щит:**")
            lines.append(f"• Неотвеченных важных писем: **{len(actionable_emails)}**{b_str}.")
            lines.append("• Для подробного анализа и ответов: `/emails`\n")

        opd_items = []
        general_urgent = []
        general_tasks = []
        for i in action_items:
            summary = i.get("summary_text", "")
            src_type = i.get("source_type") or ""
            if src_type in ("telegram_group", "channel") or any(g in summary for g in ("м631к", "м531", "М631K", "М631к")):
                clean_sum = summary
                for prefix in ("[м631к Основы проектной деятельности]", "[м531 Основы проектной деятельности]", "[М631K]"):
                    clean_sum = clean_sum.replace(prefix, "").strip()
                for tag in ("[SCHEDULE_CHANGE]", "[DOCUMENT/LINK]", "[Сообщение отправлено сегодня]"):
                    clean_sum = clean_sum.replace(tag, "").strip()
                grp_tag = "м631к" if "м631к" in summary else ("м531" if "м531" in summary else "ОПД")
                opd_items.append(f"[{grp_tag}] {clean_sum}")
            elif i.get("priority_score", 1) >= 3:
                general_urgent.append(summary)
            else:
                general_tasks.append(summary)

        lines.append("💬 **Мессенджеры (ОПД ГУАП):**")
        if opd_items:
            for it in opd_items[:5]:
                lines.append(f"• {it}")
        else:
            lines.append("• В студенческих чатах (м531, м631к, М631К) срочных вопросов нет.")
        lines.append("")

        if general_urgent:
            lines.append("🚨 **Срочное / Дедлайны:**")
            for u in general_urgent:
                lines.append(f"• {u}")
            lines.append("")

        if general_tasks:
            lines.append("📋 **Задачи кафедры:**")
            for n in general_tasks[:5]:
                lines.append(f"• {n}")
            lines.append("")

        lines.append("💡 **Фокус дня:**")
        lines.append("• Выполнение академического плана и консультации студентов.")

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

            bot_answered = [
                mask_nda_email_data(em) if is_nda_email(em) else em
                for em in email_stats.get("bot_answered", [])
            ]
            pending = [
                mask_nda_email_data(em) if is_nda_email(em) else em
                for em in email_stats.get("pending_actionable", [])
            ]

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
                    tmr_lines.append(format_academic_lesson_line(l))
            else:
                tmr_lines.append("• Занятий на завтра по расписанию нет (методический/свободный день).")

            opd_lines = []
            if action_items:
                for i in action_items:
                    summary = i.get("summary_text", "")
                    src_type = i.get("source_type") or ""
                    if src_type in ("telegram_group", "channel") or any(g in summary for g in ("м631к", "м531", "М631K", "М631к")):
                        clean_sum = summary
                        for prefix in ("[м631к Основы проектной деятельности]", "[м531 Основы проектной деятельности]", "[М631K]"):
                            clean_sum = clean_sum.replace(prefix, "").strip()
                        for tag in ("[SCHEDULE_CHANGE]", "[DOCUMENT/LINK]", "[Сообщение отправлено сегодня]"):
                            clean_sum = clean_sum.replace(tag, "").strip()
                        grp_tag = "м631к" if "м631к" in summary else ("м531" if "м531" in summary else "ОПД")
                        opd_lines.append(f"[{grp_tag}] {clean_sum}")

            msg_section = ""
            if opd_lines:
                msg_section = "=== СВОДКА ПО МЕССЕНДЖЕРАМ (ОПД ГУАП) ===\n" + "\n".join(f"• {it}" for it in opd_lines[:5]) + "\n\n"

            prompt = (
                f"Сегодня завершается: {target_date.strftime('%d.%m.%Y')} ({weekday_today}).\n\n"
                f"=== СТАТИСТИКА РАБОТЫ С ПОЧТОЙ ЗА ДЕНЬ ===\n" + "\n".join(email_lines) + "\n\n"
                f"=== РАСПИСАНИЕ НА ЗАВТРА ({tomorrow_date.strftime('%d.%m.%Y')}, {weekday_tmr}) ===\n" + "\n".join(tmr_lines) + "\n\n"
                + msg_section
                + "Сформируй структурированный вечерний дайджест для преподавателя."
            )

            system_instruction = render_prompt(
                "evening_digest",
                date_str=target_date.strftime("%d.%m.%Y"),
                weekday=weekday_today,
                tomorrow_date_str=tomorrow_date.strftime("%d.%m.%Y"),
                tomorrow_weekday=weekday_tmr,
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

        except PersonaConfigError as e:
            logger.error("Ошибка конфигурации персоны при генерации вечернего дайджеста: %s", e)
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

        bot_answered = [
            mask_nda_email_data(em) if is_nda_email(em) else em
            for em in email_stats.get("bot_answered", [])
        ]
        pending = [
            mask_nda_email_data(em) if is_nda_email(em) else em
            for em in email_stats.get("pending_actionable", [])
        ]

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
                lines.append(format_academic_lesson_line(l))
        else:
            lines.append("• Занятий нет (свободный/методический день).")
        lines.append("")

        opd_items = []
        if action_items:
            for i in action_items:
                summary = i.get("summary_text", "")
                src_type = i.get("source_type") or ""
                if src_type in ("telegram_group", "channel") or any(g in summary for g in ("м631к", "м531", "М631K", "М631к")):
                    clean_sum = summary
                    for prefix in ("[м631к Основы проектной деятельности]", "[м531 Основы проектной деятельности]", "[М631K]"):
                        clean_sum = clean_sum.replace(prefix, "").strip()
                    for tag in ("[SCHEDULE_CHANGE]", "[DOCUMENT/LINK]", "[Сообщение отправлено сегодня]"):
                        clean_sum = clean_sum.replace(tag, "").strip()
                    grp_tag = "м631к" if "м631к" in summary else ("м531" if "м531" in summary else "ОПД")
                    opd_items.append(f"[{grp_tag}] {clean_sum}")

        if opd_items:
            lines.append("💬 **Мессенджеры (ОПД ГУАП):**")
            for it in opd_items[:5]:
                lines.append(f"• {it}")
            lines.append("")

        lines.append("✨ **Итоги дня:**")
        lines.append("• Все запланированные коммуникации со студентами завершены.")
        lines.append("• Данные синхронизированы с базой и календарем.")

        return "\n".join(lines).strip()
