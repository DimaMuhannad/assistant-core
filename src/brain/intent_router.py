"""Fast Intent Router: Stateless, low-latency LLM intent classification for Telegram Bot.

Architecture & Specifications:
- Single stateless call using Gemini 3.8 Flash (with low thinking effort)
- Multi-model fallback chain: gemini-3.8-flash -> gemini-3.5-flash-lite -> gemini-3.5-flash
- Does NOT write to chat directly (pure classification engine)
- Selects between standard action presets (timesheet, schedule, emails, lms, methodist, clear)
  or delegates to full conversational SecretaryDialogEngine
- Full audit logging into SQLite router_audit_log
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class CommandResolver(Protocol):
    async def resolve_command_or_alias(self, text: str) -> str | None:
        ...

from google import genai
from google.genai import types

from src import config
from src.storage.db import Database
from src.persona.prompts import render_prompt
from src.brain.key_rotator import key_rotator

logger = logging.getLogger(__name__)

VALID_ACTIONS = {
    "timesheet",
    "evening",
    "emails",
    "lms_tasks",
    "lms_reports",
    "methodist",
    "clear_dialog",
    "ticker",
    "secretary",
    "calendar_schedule",
    "create_reminder",
    "draft_reply",
    "today",
    "help",
    "undo_clear",
    "menu",
    "lms",
}


import re


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Robust JSON extraction from LLM response handling markdown fences or leading/trailing text."""
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    # Strip markdown code blocks ```json ... ```
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    # Match any {...}
    m = re.search(r"(\{[\s\S]*\})", text)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    return None


@dataclass
class IntentResult:
    action: str
    confidence: float
    reason: str
    model: str
    latency_ms: float


class FastIntentRouter:
    """Fast stateless LLM intent router for dispatching incoming messages."""

    _model_cooldowns: dict[str, float] = {}

    def __init__(
        self,
        db: Database,
        api_key: str | None = config.GEMINI_API_KEY,
        model: str = config.GEMINI_MODEL,
        command_registry: CommandResolver | None = None,
    ) -> None:
        self.db = db
        self.api_key = api_key or ""
        self.model = model or "gemini-3.8-flash"
        self.command_registry = command_registry
        self._client: genai.Client | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("AIzaSyYour"))

    def get_client(self) -> genai.Client:
        if self._client is not None:
            return self._client
        return key_rotator.get_client()

    async def route(self, user_id: int, message_text: str) -> IntentResult:
        """Route an incoming message to an action without persisting conversation context."""
        cleaned = message_text.strip()
        t0 = time.perf_counter()

        # 0. Registry fast-path (< 10 ms deterministic resolution without LLM)
        if self.command_registry is not None:
            canonical = await self.command_registry.resolve_command_or_alias(cleaned)
            if canonical:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                res = IntentResult(
                    action=canonical,
                    confidence=1.0,
                    reason=f"Детерминированный алиас из CommandRegistry: {cleaned}",
                    model="fast-rule",
                    latency_ms=latency_ms,
                )
                await self._audit(user_id, cleaned, res)
                return res

        # 1. Deterministic instant fast-paths for unambiguous keywords/commands
        lower = cleaned.lower()
        if lower in ("/clear", "сброс", "очисти диалог", "забудь контекст", "/reset"):
            res = IntentResult(
                action="clear_dialog",
                confidence=1.0,
                reason="Детерминированный сброс диалога",
                model="fast-rule",
                latency_ms=0.0,
            )
            await self._audit(user_id, cleaned, res)
            return res

        timesheet_cmds = {"/timesheet", "табель", "покажи табель", "выработка", "норма часов", "баланс часов"}
        try:
            from src.persona.current import current_persona
            comp = current_persona().organizations.get("company")
            if comp:
                for a in [comp.name] + list(comp.aliases):
                    if a:
                        timesheet_cmds.add(f"часы {a.lower()}")
                        timesheet_cmds.add(f"карточка {a.lower()}")
        except Exception:
            pass

        if lower in timesheet_cmds:
            res = IntentResult(
                action="timesheet",
                confidence=1.0,
                reason="Детерминированный шорткат табеля",
                model="fast-rule",
                latency_ms=0.0,
            )
            await self._audit(user_id, cleaned, res)
            return res

        if lower in ("/evening", "/digest", "вечерний дайджест", "вечерняя сводка", "итоги дня", "дебрифинг"):
            res = IntentResult(
                action="evening",
                confidence=1.0,
                reason="Детерминированный шорткат вечернего дайджеста",
                model="fast-rule",
                latency_ms=0.0,
            )
            await self._audit(user_id, cleaned, res)
            return res

        if lower in ("/emails", "почта", "письма", "неотвеченные письма", "список писем", "входящие письма"):
            res = IntentResult(
                action="emails",
                confidence=1.0,
                reason="Детерминированный шорткат почты",
                model="fast-rule",
                latency_ms=0.0,
            )
            await self._audit(user_id, cleaned, res)
            return res

        if lower in ("/tasks", "/lms_tasks", "задания", "список заданий", "управление заданиями", "меню заданий"):
            res = IntentResult(
                action="lms_tasks",
                confidence=1.0,
                reason="Детерминированный шорткат заданий LMS",
                model="fast-rule",
                latency_ms=0.0,
            )
            await self._audit(user_id, cleaned, res)
            return res

        if lower in ("/reports", "/submissions", "отчеты", "сданные отчеты", "проверь отчеты", "работы студентов"):
            res = IntentResult(
                action="lms_reports",
                confidence=1.0,
                reason="Детерминированный шорткат отчетов LMS",
                model="fast-rule",
                latency_ms=0.0,
            )
            await self._audit(user_id, cleaned, res)
            return res

        # Slash command prefixes for planning & reminders (Issue #46)
        if lower.startswith(("/напомни", "/remind", "/напоминание")):
            res = IntentResult(
                action="create_reminder",
                confidence=1.0,
                reason="Детерминированный префикс напоминания",
                model="fast-rule",
                latency_ms=0.0,
            )
            await self._audit(user_id, cleaned, res)
            return res

        if lower.startswith(("/календарь", "/calendar", "/событие")):
            res = IntentResult(
                action="calendar_schedule",
                confidence=1.0,
                reason="Детерминированный префикс календаря",
                model="fast-rule",
                latency_ms=0.0,
            )
            await self._audit(user_id, cleaned, res)
            return res

        cal_phrases = ("запиши в календарь", "добавь в календарь", "запланируй встречу")
        if any(p in lower for p in cal_phrases):
            res = IntentResult(
                action="calendar_schedule",
                confidence=1.0,
                reason="Детерминированный шорткат календаря",
                model="fast-rule",
                latency_ms=0.0,
            )
            await self._audit(user_id, cleaned, res)
            return res

        rem_phrases = ("поставь дедлайн", "создай напоминание", "добавь напоминание", "напомни мне")
        is_reminder = any(p in lower for p in rem_phrases) or (
            "напомни" in lower
            and not any(q in lower for q in ("сколько", "расписани", "пар", "какие", "какой", "какая", "когда", "?"))
        )
        if is_reminder:
            res = IntentResult(
                action="create_reminder",
                confidence=1.0,
                reason="Детерминированный шорткат напоминания",
                model="fast-rule",
                latency_ms=0.0,
            )
            await self._audit(user_id, cleaned, res)
            return res

        draft_phrases = ("ответь на письмо", "черновик ответа", "подготовь ответ")
        if any(p in lower for p in draft_phrases):
            res = IntentResult(
                action="draft_reply",
                confidence=1.0,
                reason="Детерминированный шорткат черновика ответа",
                model="fast-rule",
                latency_ms=0.0,
            )
            await self._audit(user_id, cleaned, res)
            return res

        if lower in ("/today", "/schedule", "пары", "расписание"):
            res = IntentResult(
                action="today",
                confidence=1.0,
                reason="Детерминированный шорткат расписания",
                model="fast-rule",
                latency_ms=0.0,
            )
            await self._audit(user_id, cleaned, res)
            return res

        if lower in ("/help", "/start", "помощь", "справка"):
            res = IntentResult(
                action="help",
                confidence=1.0,
                reason="Детерминированный шорткат справки",
                model="fast-rule",
                latency_ms=0.0,
            )
            await self._audit(user_id, cleaned, res)
            return res

        if lower in ("/undo_clear", "/undo", "верни память", "отмени сброс"):
            res = IntentResult(
                action="undo_clear",
                confidence=1.0,
                reason="Детерминированный шорткат восстановления диалога",
                model="fast-rule",
                latency_ms=0.0,
            )
            await self._audit(user_id, cleaned, res)
            return res

        if lower in ("/menu", "меню"):
            res = IntentResult(
                action="menu",
                confidence=1.0,
                reason="Детерминированный шорткат меню",
                model="fast-rule",
                latency_ms=0.0,
            )
            await self._audit(user_id, cleaned, res)
            return res

        if not self.is_configured:
            # Fallback to full conversational secretary in offline mode
            res = IntentResult(
                action="secretary",
                confidence=1.0,
                reason="Автономный режим (без API ключа)",
                model="offline",
                latency_ms=0.0,
            )
            await self._audit(user_id, cleaned, res)
            return res

        # 2. Candidate models fallback chain
        candidate_models = [
            self.model,
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-flash-lite-latest",
            "gemini-3.6-flash",
        ]
        unique_models = []
        for m in candidate_models:
            if m not in unique_models:
                unique_models.append(m)

        system_instruction = render_prompt("intent_router")
        now_ts = time.time()
        for attempt, mod in enumerate(unique_models):
            if now_ts < self._model_cooldowns.get(mod, 0):
                continue

            try:
                cfg_kwargs: dict[str, Any] = {
                    "system_instruction": system_instruction,
                    "response_mime_type": "application/json",
                    "temperature": 0.1,
                }
                if "3.8" in mod or "3.7" in mod:
                    cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level="LOW")

                async def _make_call(client: genai.Client) -> Any:
                    return await asyncio.wait_for(
                        client.aio.models.generate_content(
                            model=mod,
                            contents=f'Входящее сообщение: "{cleaned}"',
                            config=types.GenerateContentConfig(**cfg_kwargs),
                        ),
                        timeout=4.0,
                    )

                if self._client is not None:
                    resp = await _make_call(self._client)
                else:
                    resp = await key_rotator.execute_with_failover(_make_call)
                self._model_cooldowns.pop(mod, None)
                latency_ms = (time.perf_counter() - t0) * 1000.0
                text_resp = (resp.text or "").strip()
                data = extract_json_object(text_resp)
                if not data:
                    raise ValueError(f"Could not parse valid JSON from model response: {text_resp[:120]}")

                action = data.get("action", "secretary")
                if action not in VALID_ACTIONS:
                    action = "secretary"
                conf = float(data.get("confidence", 0.9))
                reason = str(data.get("reason", "Распознан интент"))

                res = IntentResult(
                    action=action,
                    confidence=conf,
                    reason=reason,
                    model=mod,
                    latency_ms=latency_ms,
                )
                await self._audit(user_id, cleaned, res)
                return res

            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    self._model_cooldowns[mod] = time.time() + 60.0
                elif "503" in err_str or "UNAVAILABLE" in err_str:
                    self._model_cooldowns[mod] = time.time() + 15.0

                logger.warning("FastIntentRouter attempt %d with model %s failed: %s", attempt + 1, mod, e)
                if attempt < len(unique_models) - 1:
                    continue

        # 3. Safe fallback to conversational secretary if all models fail
        latency_ms = (time.perf_counter() - t0) * 1000.0
        fallback_res = IntentResult(
            action="secretary",
            confidence=0.5,
            reason="Резервная передача секретарю после сбоя вызовов классификатора",
            model="fallback",
            latency_ms=latency_ms,
        )
        await self._audit(user_id, cleaned, fallback_res)
        return fallback_res

    async def _audit(self, user_id: int, incoming_text: str, res: IntentResult) -> None:
        """Audit the routing decision in SQLite for monitoring and traceability."""
        try:
            await self.db.log_router_audit(
                user_id=user_id,
                incoming_text=incoming_text,
                action_chosen=res.action,
                model=res.model,
                latency_ms=res.latency_ms,
                confidence=res.confidence,
                reasoning_brief=res.reason,
            )
        except Exception as e:
            logger.warning("Could not persist router audit log: %s", e)
