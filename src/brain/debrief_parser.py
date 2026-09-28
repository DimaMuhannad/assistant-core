"""Debrief parser that extracts structured actions, commitments, and journal notes from voice transcripts."""

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any

from google import genai
from google.genai import types

from src import config
from src.models.second_brain import (
    CompletedTaskItem,
    DailyJournalItem,
    DebriefResult,
    LifeArea,
    NewTaskItem,
    TaskPriority,
    WaitingForItem,
)

logger = logging.getLogger(__name__)


DEBRIEF_SYSTEM_PROMPT = """Ты — персональный исполнительный секретарь (Executive Chief of Staff) доцента кафедры физики ГУАП и научного сотрудника сектора приборов компании «Тидекс» Попова Дмитрия Александровича.

Твоя задача: детально проанализировать расшифровку вечернего голосового сообщения (дебрифинга) Дмитрия Александровича за день и декомпозировать ее в строгий JSON.

Сферы жизни (area):
- "ГУАП" (лабораторные, лекции, деканат, эффективный контракт, студенты)
- "Тидекс" (сектор приборов, спектрометры, ячейки Голея, приборный софт, инженерия)
- "AI & Dev Projects" (chat-app, assistant-core, боты, архитектура)
- "Наука и статьи" (ВАК, Scopus, РИНЦ, конференции, гранты)
- "Личное и семья" (быт, здоровье, отдых)
- "Финансы"
- "Разное"

Правила классификации:
1. completed_tasks: Что было фактически завершено/сделано сегодня. Формулируй кратко, выделяя суть действия.
2. new_tasks: Задачи, которые нужно сделать (завтра или в будущем). Формулируй название с глагола в неопределенной форме ("Подписать приказ", "Написать парсер").
   - priority: P1 (топ-3 фокус дня), P2 (важно), P3 (мелкое/рутина).
   - due_date: определи конкретную дату в формате YYYY-MM-DD на основе контекста (если сказано "завтра" — рассчитай относительно переданной даты).
3. waiting_for_items: Договоренности, обязательства других людей перед Дмитрием Александровичем ("дипломник обещал прислать", "староста должна передать списки", "коллега обещал посмотреть").
   - person: кто должен сделать.
   - what: что именно ожидается.
   - check_date: когда нужно проконтролировать/спросить (YYYY-MM-DD).
4. journal_entry:
   - done_summary: маркированный список главных достижений дня (2-5 пунктов).
   - key_insights: ключевые выводы, мысли, рефлексия, идеи.
   - raw_transcript: исходный текст без изменений.

Ответ СТРОГО в формате валидного JSON по указанной схеме. Без вводных слов и Markdown-оберток."""


class DebriefParser:
    """Parser turning free-form voice debrief transcripts into structured Second Brain items."""

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

    async def parse_debrief(
        self,
        transcript: str,
        target_date: date | None = None,
    ) -> DebriefResult:
        """Parse raw speech transcript into DebriefResult."""
        if target_date is None:
            target_date = date.today()

        date_str = target_date.strftime("%Y-%m-%d")
        clean_text = transcript.strip()

        if not clean_text:
            return DebriefResult(
                completed_tasks=[],
                new_tasks=[],
                waiting_for_items=[],
                journal_entry=DailyJournalItem(
                    date_str=date_str,
                    done_summary="Нет записей за сегодня.",
                    key_insights=None,
                    raw_transcript="",
                ),
            )

        if not self.is_configured:
            logger.info("Gemini not configured, using deterministic fallback debrief parser.")
            return self._fallback_parse(clean_text, target_date)

        try:
            client = self.get_client()
            user_prompt = f"Сегодняшняя дата: {date_str} ({target_date.strftime('%A')}).\nТранскрипт вечернего сообщения:\n\"\"\"{clean_text}\"\"\""

            # Call Gemini with structured JSON output schema
            response = await client.aio.models.generate_content(
                model=self.model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=f"{DEBRIEF_SYSTEM_PROMPT}\n\n{user_prompt}")],
                    )
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=DebriefResult,
                    temperature=0.2,
                ),
            )

            response_text = response.text or ""
            parsed_json = json.loads(response_text)
            return DebriefResult.model_validate(parsed_json)

        except Exception as e:
            logger.warning("Gemini parsing failed (%s), falling back to deterministic parser.", e)
            return self._fallback_parse(clean_text, target_date)

    def _fallback_parse(self, text: str, target_date: date) -> DebriefResult:
        """Rule-based heuristic parser used when LLM is unavailable or in offline mode."""
        date_str = target_date.strftime("%Y-%m-%d")
        tomorrow = target_date + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%Y-%m-%d")

        completed: list[CompletedTaskItem] = []
        new_tasks: list[NewTaskItem] = []
        waiting: list[WaitingForItem] = []

        sentences = re.split(r"[.!?\n]+", text)
        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue

            lower = s_clean.lower()
            # Completed heuristics
            if any(k in lower for k in ("сделал", "закрыл", "провел", "доделал", "отправил", "завершил")):
                completed.append(
                    CompletedTaskItem(
                        raw_mention=s_clean,
                        normalized_title=s_clean,
                        project_name=self._guess_project(lower),
                    )
                )
            # New task heuristics
            elif any(k in lower for k in ("нужно", "надо", "завтра", "не забыть", "планирую", "сделать")):
                prio = TaskPriority.P1 if any(k in lower for k in ("срочно", "главное", "первым делом")) else TaskPriority.P2
                new_tasks.append(
                    NewTaskItem(
                        title=s_clean,
                        project_name=self._guess_project(lower),
                        area=self._guess_area(lower),
                        priority=prio,
                        due_date=tomorrow_str if "завтра" in lower else None,
                    )
                )
            # Waiting for heuristics
            elif any(k in lower for k in ("обещал", "договорились", "спросить у", "ждём", "ждет")):
                person = "Коллега / Студент"
                for word in s_clean.split():
                    if word.istitle() and word not in ("Сегодня", "Завтра", "Также", "Еще"):
                        person = word
                        break
                waiting.append(
                    WaitingForItem(
                        what=s_clean,
                        person=person,
                        check_date=(target_date + timedelta(days=2)).strftime("%Y-%m-%d"),
                        context=self._guess_project(lower),
                    )
                )

        done_summary = "\n".join(f"• {c.normalized_title}" for c in completed) if completed else "• Текущая операционная деятельность"

        return DebriefResult(
            completed_tasks=completed,
            new_tasks=new_tasks,
            waiting_for_items=waiting,
            journal_entry=DailyJournalItem(
                date_str=date_str,
                done_summary=done_summary,
                key_insights=None,
                raw_transcript=text,
            ),
        )

    def _guess_area(self, text: str) -> LifeArea:
        if any(k in text for k in ("гуап", "кафедр", "лаб", "пары", "студент", "деканат")):
            return LifeArea.GUAP
        if any(k in text for k in ("тидекс", "прибор", "спектрометр", "голе", "датчик")):
            return LifeArea.TYDEX
        if any(k in text for k in ("код", "бот", "агент", "парсер", "github", "репозитор")):
            return LifeArea.DEV_AI
        if any(k in text for k in ("стать", "вак", "scopus", "ринц", "конференц")):
            return LifeArea.SCIENCE
        return LifeArea.OTHER

    def _guess_project(self, text: str) -> str | None:
        if any(k in text for k in ("гуап", "лаб", "кафедр")):
            return "Учебный процесс ГУАП"
        if any(k in text for k in ("тидекс", "прибор")):
            return "Проекты Тидекс"
        if any(k in text for k in ("агент", "бот", "секретар")):
            return "AI-ассистент секретарь"
        return None

    def format_telegram_report(self, result: DebriefResult) -> str:
        """Format the parsed debrief result into an executive Telegram card."""
        blocks: list[str] = [f"🎙️ **Вечерний дебрифинг: {result.journal_entry.date_str}**"]

        if result.completed_tasks:
            done_lines = "\n".join(f"  • {item.normalized_title}" for item in result.completed_tasks)
            blocks.append(f"✅ **Завершено за день (статус Done):**\n{done_lines}")
        else:
            blocks.append("✅ **Завершено за день:**\n  • Без фиксации закрытых задач.")

        if result.new_tasks:
            task_lines = []
            for t in result.new_tasks:
                prio_badge = "🔴 P1" if t.priority == TaskPriority.P1 else "🟡 P2" if t.priority == TaskPriority.P2 else "⚪ P3"
                due_info = f" | До: `{t.due_date}`" if t.due_date else ""
                area_info = f" [{t.area.value}]" if t.area else ""
                task_lines.append(f"  • {prio_badge}{area_info} **{t.title}**{due_info}")
            blocks.append(f"📌 **Поставлено задач на завтра:**\n" + "\n".join(task_lines))

        if result.waiting_for_items:
            wait_lines = []
            for w in result.waiting_for_items:
                check_info = f" (проверить: `{w.check_date}`)" if w.check_date else ""
                wait_lines.append(f"  • ⏳ **{w.person}:** {w.what}{check_info}")
            blocks.append(f"🤝 **Взято на контроль (Waiting For):**\n" + "\n".join(wait_lines))

        if result.journal_entry.key_insights:
            blocks.append(f"💡 **Инсайт дня:**\n  {result.journal_entry.key_insights}")

        return "\n\n".join(blocks)
