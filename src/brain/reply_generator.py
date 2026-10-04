import logging
import re
from typing import Any

from google import genai
from google.genai import types

from src import config
from src.core.exceptions import AirGapViolationError
from src.persona.prompts import render_prompt
from src.security.airgap import is_nda_email

logger = logging.getLogger(__name__)


class ReplyGenerator:
    """Generates and refines professional email reply drafts using Gemini models."""

    def __init__(
        self,
        api_key: str | None = config.GEMINI_API_KEY,
        model: str = config.GEMINI_MODEL,
    ):
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

    async def generate_reply(
        self,
        email_data: dict[str, Any],
        user_instructions: str | None = None,
    ) -> str:
        """Generate draft reply for an incoming email message."""
        if is_nda_email(email_data):
            logger.warning("Reply generation blocked for restricted_nda email: %s", email_data.get("id"))
            raise AirGapViolationError("Автогенерация ответа запрещена политикой Air-Gap")

        sender_name = email_data.get("sender_name") or ""
        sender_email = email_data.get("sender_email") or ""
        subject = email_data.get("subject") or "Без темы"
        body = email_data.get("body_plain") or email_data.get("snippet") or ""
        category = email_data.get("category") or "guap_student"

        cat_desc = "Студент ГУАП" if category == "guap_student" else "Сотрудник кафедры/деканата ГУАП"

        prompt_parts = [
            f"Категория отправителя: {cat_desc}",
            f"От: {sender_name} <{sender_email}>",
            f"Тема входящего письма: {subject}",
            f"Текст входящего письма:\n\"\"\"\n{body.strip()}\n\"\"\"",
        ]

        if user_instructions:
            prompt_parts.append(
                f"\nУказания преподавателя (Дмитрия Александровича) по ответу:\n{user_instructions.strip()}"
            )
        else:
            prompt_parts.append(
                "\nСоставь оптимальный, дружелюбный и профессиональный ответ по существу."
            )

        prompt = "\n".join(prompt_parts)

        if not self.is_configured:
            return self._fallback_reply(sender_name, category)

        candidate_models = ["gemini-3.5-flash-lite", self.model, "gemini-3.8-flash"]
        # deduplicate
        seen = set()
        models_to_try = [m for m in candidate_models if not (m in seen or seen.add(m))]

        system_instruction = render_prompt("reply_generator")
        client = self.get_client()
        for cand in models_to_try:
            try:
                response = await client.aio.models.generate_content(
                    model=cand,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.3,
                    ),
                )
                if response and response.text:
                    text = response.text.strip()
                    # Strip markdown block quotes or extra backticks if model generated them
                    text = re.sub(r"^```[a-z]*\n?", "", text)
                    text = re.sub(r"\n?```$", "", text).strip()
                    return text
            except Exception as e:
                logger.warning("Reply generation with model %s failed: %s", cand, e)

        return self._fallback_reply(sender_name, category)

    async def refine_reply(
        self,
        original_draft: str,
        edit_instructions: str,
        incoming_email_data: dict[str, Any] | None = None,
    ) -> str:
        """Refines an existing draft reply based on user feedback or corrections."""
        if not self.is_configured:
            return f"{original_draft}\n\n[Дополнение]: {edit_instructions}"

        prompt = (
            f"Исходный черновик ответа:\n\"\"\"\n{original_draft}\n\"\"\"\n\n"
            f"Правки и пожелания преподавателя к черновику:\n\"{edit_instructions}\"\n\n"
            "Скорректируй текст ответа с учетом этих правок. Сохрани официальную вежливую подпись и структуру."
        )

        candidate_models = ["gemini-3.5-flash-lite", self.model, "gemini-3.8-flash"]
        system_instruction = render_prompt("reply_generator")
        client = self.get_client()

        for cand in candidate_models:
            try:
                response = await client.aio.models.generate_content(
                    model=cand,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.3,
                    ),
                )
                if response and response.text:
                    text = response.text.strip()
                    text = re.sub(r"^```[a-z]*\n?", "", text)
                    text = re.sub(r"\n?```$", "", text).strip()
                    return text
            except Exception as e:
                logger.warning("Reply refinement with model %s failed: %s", cand, e)

        return f"{original_draft}\n\n{edit_instructions}"

    def _fallback_reply(self, sender_name: str, category: str) -> str:
        greeting = f"Здравствуйте, {sender_name}!" if sender_name else "Здравствуйте!"
        return (
            f"{greeting}\n\n"
            "Ваше письмо получено. Ознакомился с вашим вопросом. "
            "Материалы приняты в работу / подробные комментарии предоставлю в ближайшее время на консультации или ответным письмом.\n\n"
            "С уважением,\n"
            "Дмитрий Александрович Попов\n"
            "Доцент кафедры физики ГУАП, к.ф.-м.н."
        )
