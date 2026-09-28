import logging
from datetime import date, datetime
from typing import Any

from google import genai
from google.genai import types

from src import config
from src.models.schedule import Lesson

logger = logging.getLogger(__name__)


class GeminiSummarizer:
    """LLM summarizer using the official Google GenAI SDK (gemini-3.8-flash)."""

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
    ) -> str:
        """Generate an executive morning brief combining schedule and action items."""
        if not self.is_configured:
            logger.info("Gemini API key not configured, falling back to deterministic template.")
            return self._generate_fallback_brief(target_date, lessons, action_items)

        try:
            client = self.get_client()

            # Format input context for prompt
            schedule_context = []
            if lessons:
                for l in lessons:
                    type_str = l.lesson_type.value if hasattr(l.lesson_type, "value") else str(l.lesson_type)
                    schedule_context.append(
                        f"- {l.start_time.strftime('%H:%M')}–{l.end_time.strftime('%H:%M')} "
                        f"[{type_str}] {l.subject} (ауд. {l.room})"
                    )
            else:
                schedule_context.append("- Занятий по расписанию нет (методический/свободный день).")

            items_context = []
            if action_items:
                for item in action_items[:15]:
                    summary = item.get("summary_text", "")
                    prio = item.get("priority_score", 1)
                    items_context.append(f"- [Приоритет {prio}] {summary}")
            else:
                items_context.append("- Нет новых входящих задач и уведомлений.")

            prompt = (
                f"Сегодня: {target_date.strftime('%d.%m.%Y')} ({target_date.strftime('%A')})\n\n"
                f"=== РАСПИСАНИЕ НА СЕГОДНЯ ===\n" + "\n".join(schedule_context) + "\n\n"
                f"=== ВХОДЯЩИЕ СОБЫТИЯ ИЗ ЧАТОВ И КАНАЛОВ ===\n" + "\n".join(items_context) + "\n\n"
                "Сформируй структурированный утренний дайджест для преподавателя."
            )

            system_instruction = (
                "Ты — персональный академический ассистент преподавателя ГУАП (Попов Д.А., Кафедра 3).\n"
                "Твоя задача — составить краткий, четкий и полезный утренний дайджест на русском языке.\n"
                "Формат:\n"
                "1. 📅 Расписание на сегодня: краткий список пар со временем и аудиториями.\n"
                "2. 🚨 Срочное и дедлайны: ключевые задачи с дедлайнами или изменениями в расписании.\n"
                "3. 📋 Задачи по дисциплинам/группам: ОПД (м531, м631к), физика, кафедра.\n"
                "4. 💡 Фокус дня: одна конкретная рекомендация, на что обратить внимание.\n"
                "Пиши емко, без лишней вежливости и воды. Используй понятные маркеры Markdown."
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

            return self._generate_fallback_brief(target_date, lessons, action_items)


        except Exception as e:
            logger.exception("Failed to generate brief via Gemini API: %s", e)
            return self._generate_fallback_brief(target_date, lessons, action_items)

    def _generate_fallback_brief(
        self,
        target_date: date,
        lessons: list[Lesson],
        action_items: list[dict[str, Any]],
    ) -> str:
        """Deterministic fallback brief when Gemini API is unavailable or offline."""
        lines = [f"☀️ *Утренний дайджест на {target_date.strftime('%d.%m.%Y')}*\n"]

        lines.append("📅 *Расписание на сегодня:*")
        if lessons:
            for l in lessons:
                lines.append(
                    f"• {l.start_time.strftime('%H:%M')}–{l.end_time.strftime('%H:%M')} "
                    f"{l.subject} ({l.room})"
                )
        else:
            lines.append("• Занятий нет (свободный/методический день).")
        lines.append("")

        urgent = [i for i in action_items if i.get("priority_score", 1) >= 3]
        if urgent:
            lines.append("🚨 *Срочное / Дедлайны:*")
            for u in urgent:
                lines.append(f"• {u.get('summary_text', '')}")
            lines.append("")

        normal = [i for i in action_items if i.get("priority_score", 1) < 3]
        if normal:
            lines.append("📋 *Задачи и сообщения:*")
            for n in normal[:7]:
                lines.append(f"• {n.get('summary_text', '')}")
            lines.append("")

        return "\n".join(lines).strip()
