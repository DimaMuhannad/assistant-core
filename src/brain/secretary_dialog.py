"""Secretary Dialog Engine: Conversational AI interface for Dmitry Popov's Personal Secretary.

Coordinates:
- Schedule and timetable queries (GUAP)
- Tydex working hours pacing (AADHk)
- Unanswered email triage and summaries
- LMS pro.guap.ru submissions & tasks
- Academic and methodological questions (delegating to MethodistService)
- Multi-turn conversation memory with persistent storage in SQLite
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta, date
from typing import Any
from zoneinfo import ZoneInfo

from google import genai
from google.genai import types

from src import config
from src.storage.db import Database
from src.brain.methodist import MethodistService
from src.models.schedule import SchedulePayload, Lesson

logger = logging.getLogger(__name__)

SECRETARY_SYSTEM_PROMPT = """Ты — персональный цифровой секретарь-референт и академический помощник доцента Попова Дмитрия Александровича.

ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ (ТВОЕГО РУКОВОДИТЕЛЯ):
- ФИО: Попов Дмитрий Александрович, кандидат физико-математических наук.
- Основные должности и сферы деятельности:
  1. Доцент кафедры физики (Кафедра №1) ГУАП (0.75 ставки). Дисциплины: «Физика», «Физические основы нанотехнологий» (ФОНТ), «Основы проектной деятельности» (ОПД), «Основы проектной деятельности в профессии» (ОПДвП). Личный кабинет преподавателя: pro.guap.ru.
  2. Научный сотрудник сектора приборов ООО «Тидекс» (приборостроение, терагерцовая и ИК оптика). Режим: свободное посещение, норма 8.5 часов в сутки в течение 5 рабочих дней в неделю (базовая норма недели 42.5 ч). Ключевой фокус учета — баланс нормы к концу каждого календарного месяца (ΔH >= 0). Учет ведется через приложение AADHk.

ТВОЯ МИССИЯ И ОБЯЗАННОСТИ:
1. Быть внимательным, пунктуальным, предупредительным и компетентным секретарем.
2. Отвечать на любые вопросы Дмитрия Александровича на естественном русском языке в свободной форме:
   - По расписанию пар, времени, аудиториям, группам, переносам и свободным окнам.
   - По выработке рабочего времени в «Тидекс», дельте нормы (ΔH), отработанным часам и требуемому темпу до конца месяца.
   - По входящей почте, студенческим письмам, требующим ответа, и переписке с кафедрой.
   - По заданиям и студенческим отчетам в LMS pro.guap.ru.
   - По методическим вопросам (ГОСТы, титульные листы, правила защиты, формулы, учебники Коваленко, эффективный контракт).
   - По планированию дня, задачам, напоминаниям и общим рассуждениям.

СТИЛЬ И ТОН ОБЩЕНИЯ:
- Обращайся к Дмитрию Александровичу уважительно, на «вы» (или по имени-отчеству при уместности).
- Тон: деловой, тактичный, доброжелательный, лаконичный и предельно точный.
- Без лишней "воды", пространных вступлений и дежурных фраз. Сразу переходи к сути.
- Форматируй ответы в аккуратном структурированном Markdown (выделяй ключевые цифры, время, аудитории, формулы).
- Используй визуальные эмодзи-маркеры в стиле Telegram (📅, ⏱️, 📬, 🎓, 📍, •, ✔️).
"""


class SecretaryDialogEngine:
    """Conversational AI engine providing natural dialogue capabilities to the secretary bot."""

    def __init__(
        self,
        db: Database,
        api_key: str | None = config.GEMINI_API_KEY,
        model: str = config.GEMINI_MODEL,
        methodist: MethodistService | None = None,
    ) -> None:
        self.db = db
        self.api_key = api_key or ""
        self.model = model
        self.methodist = methodist or MethodistService(db, api_key=api_key, model=model)
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

    async def _get_schedule_context(self, now_local: datetime) -> str:
        """Fetch schedule ground truth for today and next 7 days."""
        today = now_local.date()
        target_id = config.SCHEDULE_TARGET_ID
        snap = await self.db.get_latest_snapshot(f"rasp_guap_{target_id}")
        
        lines: list[str] = []
        if snap and snap.get("raw_payload"):
            try:
                payload = SchedulePayload.model_validate_json(snap["raw_payload"])
                today_lessons: list[Lesson] = []
                upcoming_by_day: dict[date, list[Lesson]] = {}

                for day in payload.days:
                    if day.date == today:
                        today_lessons.extend(day.lessons)
                    elif today < day.date <= today + timedelta(days=7):
                        upcoming_by_day.setdefault(day.date, []).extend(day.lessons)

                if today_lessons:
                    lines.append(f"📅 Расписание на сегодня ({today.strftime('%d.%m.%Y')}):")
                    for l in today_lessons:
                        type_str = l.lesson_type.value if hasattr(l.lesson_type, "value") else str(l.lesson_type)
                        grp = f", гр. {l.group}" if l.group else ""
                        lines.append(f"• {l.start_time.strftime('%H:%M')}–{l.end_time.strftime('%H:%M')} | [{type_str}] {l.subject} (Ауд. {l.room}{grp})")
                else:
                    lines.append(f"📅 На сегодня ({today.strftime('%d.%m.%Y')}) пар по расписанию нет (методический/свободный день).")

                if upcoming_by_day:
                    lines.append("\n📅 Ближайшие пары на неделе:")
                    sorted_dates = sorted(upcoming_by_day.keys())
                    for d in sorted_dates[:4]:
                        wd_names = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
                        wd_str = wd_names[d.weekday()]
                        d_str = f"{d.strftime('%d.%m')} ({wd_str})"
                        lines.append(f"• {d_str}:")
                        for l in upcoming_by_day[d]:
                            type_str = l.lesson_type.value if hasattr(l.lesson_type, "value") else str(l.lesson_type)
                            grp = f", гр. {l.group}" if l.group else ""
                            lines.append(f"  - {l.start_time.strftime('%H:%M')}–{l.end_time.strftime('%H:%M')} [{type_str}] {l.subject} (Ауд. {l.room}{grp})")
            except Exception as e:
                logger.debug("Could not parse schedule snapshot: %s", e)

        if not lines:
            lines.append("📅 Данные расписания ГУАП временно недоступны или нет запланированных пар.")

        return "\n".join(lines)

    async def _get_tydex_context(self) -> str:
        """Fetch working hours pacing from AADHk parser."""
        try:
            from src.connectors.aadhk.parser import AadhkIngestionService
            service = AadhkIngestionService(self.db)
            pacing = await service.get_monthly_pacing(project_name="Тидекс")

            month_names = ["", "январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
            cur_m_name = month_names[pacing["month"]].capitalize()
            delta_sign = "+" if pacing["delta_pacing"] >= 0 else ""

            return (
                f"⏱️ Табель ООО «Тидекс» ({cur_m_name} {pacing['year']}):\n"
                f"• Месячная норма: {pacing['monthly_norm_hours']:.1f} ч ({pacing['total_workdays']} раб. дней по 8.5 ч)\n"
                f"• Отработано фактически: {pacing['worked_hours']:.2f} ч ({pacing['total_shifts']} смен/дней)\n"
                f"• Текущий баланс нормы (ΔH): {delta_sign}{pacing['delta_pacing']:.2f} ч\n"
                f"• Осталось закрыть: {pacing['remaining_hours_to_norm']:.2f} ч\n"
                f"• Требуемый темп: {pacing['required_daily_pacing']:.2f} ч/день (осталось раб. дней: {pacing['remaining_workdays']})"
            )
        except Exception as e:
            logger.debug("Could not compute Tydex pacing: %s", e)
            return "⏱️ Табель «Тидекс»: данные выработки временно обновляются."

    async def _get_email_context(self) -> str:
        """Fetch overview of pending actionable emails."""
        try:
            actionable = await self.db.list_actionable_emails(limit=5)
            if not actionable:
                return "📬 Почта: все входящие письма обработаны, неотвеченных сообщений нет."
            
            lines = [f"📬 Почта ({len(actionable)} неотвеченных писем, требующих внимания):"]
            for em in actionable:
                sender = em.get("sender_name") or em.get("sender_email")
                subj = em.get("subject", "Без темы")
                snip = (em.get("snippet") or "")[:120]
                lines.append(f"• От {sender}: «{subj}» — {snip}")
            return "\n".join(lines)
        except Exception as e:
            logger.debug("Could not fetch email context: %s", e)
            return "📬 Почта: актуализация списка..."

    async def _get_lms_context(self) -> str:
        """Fetch overview of LMS submissions."""
        try:
            subs = await self.db.list_lms_submissions(limit=5)
            unreviewed = [s for s in subs if not s.get("status") or s.get("status") == "pending"]
            if unreviewed:
                return f"🎓 LMS pro.guap.ru: ожидают проверки {len(unreviewed)} отчетов студентов."
            return "🎓 LMS pro.guap.ru: все сданные отчеты проверены или новых отчетов нет."
        except Exception as e:
            logger.debug("Could not fetch LMS context: %s", e)
            return "🎓 LMS pro.guap.ru: мониторинг активен."

    async def _build_grounding_context(self, user_msg: str, now_local: datetime) -> str:
        """Gather all real-time operational context into a unified grounding block."""
        now_str = now_local.strftime("%A, %d %B %Y г., %H:%M MSK")
        
        # Parallel data retrieval
        schedule_task = self._get_schedule_context(now_local)
        tydex_task = self._get_tydex_context()
        email_task = self._get_email_context()
        lms_task = self._get_lms_context()

        sched_ctx, tydex_ctx, email_ctx, lms_ctx = await asyncio.gather(
            schedule_task, tydex_task, email_task, lms_task
        )

        blocks = [
            f"🕒 Текущее системное время: {now_str}",
            sched_ctx,
            tydex_ctx,
            email_ctx,
            lms_ctx,
        ]

        # Check if query needs deep Methodist assistance
        try:
            scope_res = await self.methodist.check_scope(user_msg)
            if scope_res.get("is_in_scope", False):
                methodist_ans = await self.methodist.ask(user_msg, caller="secretary_dialog")
                if not methodist_ans.get("is_out_of_scope") and methodist_ans.get("answer"):
                    blocks.append(
                        f"📚 СПРАВКА ОТ АГЕНТА-МЕТОДИСТА КАФЕДРЫ ФИЗИКИ (ОФИЦИАЛЬНЫЙ РЕГЛАМЕНТ/ПОСОБИЯ):\n"
                        f"{methodist_ans['answer']}"
                    )
        except Exception as me:
            logger.debug("Methodist enrichment skipped: %s", me)

        return "\n\n".join(blocks)

    async def answer_user_message(self, user_id: int, message_text: str) -> str:
        """Process arbitrary user message with multi-turn memory and system grounding."""
        cleaned_text = message_text.strip()
        if not cleaned_text:
            return "Я готов ответить на любой ваш вопрос. Напишите, что вас интересует!"

        # Handle explicit reset command
        if cleaned_text.lower() in ("/clear", "/reset", "очисти диалог", "забудь контекст", "сброс"):
            await self.db.clear_dialog_history(user_id)
            return "🧹 **Контекст диалога успешно очищен.** Я готов к новым вопросам!"

        now_local = datetime.now(ZoneInfo(config.TZ))

        # 1. Fetch grounding context
        grounding_context = await self._build_grounding_context(cleaned_text, now_local)

        # 2. Fetch recent conversation history (last 8 messages)
        history_rows = await self.db.get_recent_dialog_history(user_id, limit=8)
        dialog_history_lines = []
        for row in history_rows:
            speaker = "Пользователь (Дмитрий Александрович)" if row["role"] == "user" else "Секретарь"
            dialog_history_lines.append(f"{speaker}: {row['content']}")

        history_block = "\n".join(dialog_history_lines) if dialog_history_lines else "История диалога пуста (новое обращение)."

        # 3. Assemble complete prompt
        user_prompt = f"""### ОПЕРАТИВНЫЕ СИСТЕМНЫЕ ДАННЫЕ (GROUND TRUTH):
{grounding_context}

### ПРЕДЫДУЩИЙ ДИАЛОГ:
{history_block}

### НОВОЕ СООБЩЕНИЕ ОТ ДМИТРИЯ АЛЕКСАНДРОВИЧА:
{cleaned_text}

Дай прямой, точный, вежливый и структурированный ответ как его личный секретарь."""

        # 4. Generate response via Gemini with multi-model fallback
        if not self.is_configured:
            answer_text = (
                "⚠️ Сервис генерации временно работает в автономном режиме (без ключа API).\n\n"
                f"**Краткая оперативная сводка:**\n\n"
                f"{grounding_context}"
            )
        else:
            candidate_models = [self.model, "gemini-3.7-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-flash-lite-latest"]
            unique_models = []
            for m in candidate_models:
                if m not in unique_models:
                    unique_models.append(m)

            client = self.get_client()
            answer_text = ""

            for attempt, mod in enumerate(unique_models):
                try:
                    cfg_kwargs: dict[str, Any] = {
                        "system_instruction": SECRETARY_SYSTEM_PROMPT,
                        "temperature": 0.3,
                    }
                    if "3.8" in mod or "3.7" in mod or "2.5" in mod:
                        cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level="LOW")

                    resp = await client.aio.models.generate_content(
                        model=mod,
                        contents=user_prompt,
                        config=types.GenerateContentConfig(**cfg_kwargs),
                    )
                    answer_text = (resp.text or "").strip()
                    if answer_text:
                        logger.info("Successfully generated secretary dialog answer via %s (attempt %d)", mod, attempt + 1)
                        break
                except Exception as e:
                    logger.warning("Attempt %d with model %s failed in dialog: %s", attempt + 1, mod, e)
                    if attempt < len(unique_models) - 1:
                        await asyncio.sleep(1.0)
                    else:
                        answer_text = (
                            "⚠️ Сервис генерации временно недоступен из-за ограничений сети/квот.\n\n"
                            f"**Краткая оперативная сводка:**\n\n"
                            f"{grounding_context}"
                        )

        # 5. Persist interaction to multi-turn memory
        try:
            await self.db.save_dialog_message(user_id=user_id, role="user", content=cleaned_text)
            await self.db.save_dialog_message(user_id=user_id, role="model", content=answer_text)
        except Exception as se:
            logger.debug("Could not save dialog turn to DB: %s", se)

        return answer_text
