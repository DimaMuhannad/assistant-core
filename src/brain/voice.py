import json
import logging
import re
from typing import Any
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from src import config

logger = logging.getLogger(__name__)


class VoiceAnalysisResult(BaseModel):
    success: bool = True
    transcription: str = ""
    summary: str = ""
    action_items: list[str] = Field(default_factory=list)
    category: str = "info"  # task, schedule, question, info
    is_urgent: bool = False
    duration_seconds: int | None = None
    error: str | None = None


class VoiceProcessor:
    """Multimodal voice message processor utilizing Gemini 2.5 Flash for audio understanding."""

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

    async def process_voice(
        self,
        voice_bytes: bytes,
        mime_type: str = "audio/ogg",
        duration_seconds: int | None = None,
        sender_name: str | None = None,
        chat_title: str | None = None,
    ) -> VoiceAnalysisResult:
        """Transcribe and analyze a Telegram voice note with zero local GPU/RAM overhead."""
        if not voice_bytes:
            return VoiceAnalysisResult(success=False, error="Empty voice payload")

        if not self.is_configured:
            logger.info("Gemini API key not configured, returning mock voice transcription.")
            return VoiceAnalysisResult(
                success=True,
                transcription="[Тестовая расшифровка голосового сообщения: обсуждение расписания лабораторных работ]",
                summary="Обсуждение расписания лабораторных работ в университете.",
                action_items=["Уточнить время консультации по лабораторным работам"],
                category="question",
                is_urgent=False,
                duration_seconds=duration_seconds,
            )

        context_info = []
        if sender_name:
            context_info.append(f"Отправитель: {sender_name}")
        if chat_title:
            context_info.append(f"Чат/Группа: {chat_title}")
        context_str = f"Контекст: {', '.join(context_info)}\n" if context_info else ""

        system_instruction = (
            "Ты — интеллектуальный ассистент-секретарь преподавателя университета (ГУАП).\n"
            "Тебе передана аудиозапись — голосовое сообщение из Telegram.\n\n"
            "Твоя задача:\n"
            "1. Максимально точно расшифровать речь на русском языке со знаками препинания и заглавными буквами.\n"
            "   Корректно распознавай профессиональный контекст ГУАП:\n"
            "   - Предметы: Физика, Физические основы нанотехнологий (ФОНТ), Основы проектной деятельности (ОПД);\n"
            "   - Корпуса и аудитории: Гастелло 15, Ленсовета 14, ауд. 31-04а, 32-03, 12-02, 13-05;\n"
            "   - Номера групп: м431к, м531, м631к, 8626, 1632.\n"
            "2. Сформулировать краткую суть сообщения (1-2 предложения).\n"
            "3. Выделить конкретные поручения, задачи, запросы дат или дедлайнов (action_items).\n"
            "4. Определить категорию (task | schedule | question | info) и срочность (is_urgent: true/false).\n\n"
            "Верни ответ СТРОГО в формате JSON без markdown-обёртки:\n"
            "{\n"
            '  "transcription": "полный текст распознанной речи",\n'
            '  "summary": "краткая суть",\n'
            '  "action_items": ["действие 1", "действие 2"],\n'
            '  "category": "task | schedule | question | info",\n'
            '  "is_urgent": false\n'
            "}"
        )

        try:
            client = self.get_client()
            audio_part = types.Part.from_bytes(data=voice_bytes, mime_type=mime_type)

            response = client.models.generate_content(
                model=self.model,
                contents=[
                    system_instruction,
                    f"{context_str}Пожалуйста, расшифруй и проанализируй эту аудиозапись:",
                    audio_part,
                ],
            )

            raw_text = (response.text or "").strip()
            # Clean possible markdown block wrappers ```json ... ```
            cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
            cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()

            data = json.loads(cleaned)
            return VoiceAnalysisResult(
                success=True,
                transcription=data.get("transcription", ""),
                summary=data.get("summary", ""),
                action_items=data.get("action_items", []),
                category=data.get("category", "info"),
                is_urgent=bool(data.get("is_urgent", False)),
                duration_seconds=duration_seconds,
            )
        except Exception as e:
            logger.exception("Failed to process voice note with Gemini: %s", e)
            return VoiceAnalysisResult(
                success=False,
                error=f"Voice processing error: {e}",
                duration_seconds=duration_seconds,
            )
