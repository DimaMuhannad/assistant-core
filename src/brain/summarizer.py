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
    ) -> str:
        """Generate an executive morning brief combining schedule and action items."""
        if not self.is_configured:
            logger.info("Gemini API key not configured, falling back to deterministic template.")
            return self._generate_fallback_brief(target_date, lessons, action_items)

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
                schedule_context.append("• Занятий по расписанию нет (методический/свободный день).")

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
                items_block.append("Нет актуальных активных задач и дедлайнов.")

            weekday_names = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
            weekday_ru = weekday_names[target_date.weekday()]

            prompt = (
                f"Сегодня: {target_date.strftime('%d.%m.%Y')} ({weekday_ru})\n\n"
                f"=== ОФИЦИАЛЬНОЕ РАСПИСАНИЕ НА СЕГОДНЯ ===\n" + "\n".join(schedule_context) + "\n\n"
                f"=== ПРОВЕРЕННЫЕ АКТУАЛЬНЫЕ СОБЫТИЯ ИЗ ЧАТОВ (ПРОШЕДШИЕ СОБЫТИЯ ОТФИЛЬТРОВАНЫ) ===\n" + "\n\n".join(items_block) + "\n\n"
                "Сформируй структурированный утренний дайджест для преподавателя."
            )

            system_instruction = (
                "Ты — персональный академический ассистент преподавателя ГУАП (Попов Д.А., Кафедра 3).\n"
                f"Сегодняшняя дата: {target_date.strftime('%d.%m.%Y')} ({weekday_ru}).\n\n"
                "КРИТИЧЕСКИЕ ПРАВИЛА ВРЕМЕННОЙ ВАЛИДАЦИИ И СВЕЖЕСТИ:\n"
                f"1. Любые сообщения о парах или переносах из прошлого (до {target_date.strftime('%d.%m.%Y')}) УЖЕ СОСТОЯЛИСЬ. Их КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО выдавать за сегодняшние или предстоящие события!\n"
                "2. Если в расписании на сегодня нет пар, четко фиксируй: '• Занятий нет (свободный/методический день)'.\n"
                "3. В блоке предстоящих дедлайнов указывай только будущие даты с количеством оставшихся дней.\n\n"
                "СТАНДАРТЫ ОФОРМЛЕНИЯ ДЛЯ TELEGRAM (МОБИЛЬНЫЙ АКАДЕМИЧЕСКИЙ БРИФИНГ):\n"
                "- Заголовки разделов: используй ТОЛЬКО жирные эмодзи-заголовки. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать решетки (#, ##, ###)!\n"
                "  Примеры заголовков:\n"
                f"  ☀️ **Утренний дайджест на {target_date.strftime('%d.%m.%Y')} ({weekday_ru})**\n"
                "  📅 **Расписание на сегодня**\n"
                "  🚨 **Срочное / Дедлайны**\n"
                "  📋 **Учебные группы и задачи**\n"
                "  💡 **Фокус дня**\n"
                "- Формат расписания: для каждого занятия строго соблюдай структуру:\n"
                "  • 09:30–11:00 | [Тип] Название предмета\n"
                "    📍 Корпус/аудитория • Группа: номер_группы\n"
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

        return "\n".join(lines).strip()
