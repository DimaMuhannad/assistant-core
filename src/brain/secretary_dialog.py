"""Secretary Dialog Engine: Conversational AI interface for Dmitry Popov's Personal Secretary.

Coordinates:
- Schedule and timetable queries (GUAP)
- Tydex working hours pacing (AADHk)
- Unanswered email triage and summaries
- Fulltext keyword email search (Mail.ru, GUAP, Gmail)
- Telegram chat and action item search
- Local documents, forms, templates, and regulations access
- LMS pro.guap.ru submissions & tasks
- Academic and methodological questions (delegating to MethodistService)
- Multi-turn conversation memory with persistent storage in SQLite
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
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

ВАЖНЕЙШЕЕ ПРАВИЛО ДОСТУПА К ДАННЫМ И ПАМЯТИ:
1. Ты ОБЛАДАЕШЬ ПОЛНЫМ ТЕХНИЧЕСКИМ ДОСТУПОМ ко всей инфраструктуре доцента Попова Д.А. Фоновый демон 24/7 собирает и сохраняет:
   - Входящие и исходящие письма со всех почтовых ящиков (Mail.ru scipopov@mail.ru, ГУАП scipopov@guap.ru, Gmail brattri3@gmail.com).
   - Сообщения из Telegram-чатов и каналов кафедры физики и студенческих групп (М631K, м531, м631к).
   - Локальную базу документов, бланков, приказов (эффективный контракт, Приказ № 05-259/26 от 17.04.2026, Таблица 3 критериев, бланки отчетов зам. зав. каф. Новиковой Ю.А., образец отчета Попова Д.А.).
   - Личный кабинет pro.guap.ru и расписание пар ГУАП.
   - Табель AADHk ООО «Тидекс».
2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО заявлять «у меня нет прямого технического доступа к вашей почте или Telegram» или советовать пользователю «настройте фильтр поиска самостоятельно» или говорить «если вы найдете шаблоны...».
3. Все результаты поиска по почте, Telegram и локальным файлам уже переданы тебе ниже в блоке оперативных системных данных. Опирайся на них и цитируй конкретные даты, отправителей, темы и документы!

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

    async def _get_email_overview(self) -> str:
        """Fetch overview of pending actionable emails."""
        try:
            actionable = await self.db.list_actionable_emails(limit=5)
            if not actionable:
                return "📬 Почтовый статус: все срочные входящие письма обработаны, неотвеченных сообщений нет."
            
            lines = [f"📬 Активные письма, требующие ответа ({len(actionable)}):"]
            for em in actionable:
                sender = em.get("sender_name") or em.get("sender_email")
                subj = em.get("subject", "Без темы")
                snip = (em.get("snippet") or "")[:120]
                lines.append(f"• От {sender}: «{subj}» — {snip}")
            return "\n".join(lines)
        except Exception as e:
            logger.debug("Could not fetch email context: %s", e)
            return "📬 Почта: актуализация списка..."

    async def _search_email_context(self, user_msg: str) -> str:
        """Search email database for specific queries or keywords."""
        try:
            emails = await self.db.search_emails(user_msg, limit=5)
            if not emails:
                return ""

            lines = [f"📧 НАЙДЕННЫЕ ПИСЬМА В ЛОКАЛЬНОЙ БАЗЕ ПОЧТЫ (Mail.ru, ГУАП, Gmail) [{len(emails)} шт.]:"]
            for em in emails:
                date_str = str(em.get("date_sent", ""))[:16].replace("T", " ")
                sender = em.get("sender_name") or em.get("sender_email")
                subj = em.get("subject", "Без темы")
                body = (em.get("body_plain") or em.get("snippet") or "")[:280].strip()
                snippet_clean = " ".join(body.split())
                lines.append(f"• [{date_str}] От: {sender} ({em.get('sender_email')})\n  Тема: «{subj}»\n  Текст: {snippet_clean}")

            return "\n".join(lines)
        except Exception as e:
            logger.debug("Could not search email messages: %s", e)
            return ""

    async def _search_telegram_context(self, user_msg: str) -> str:
        """Search monitored Telegram messages and action items."""
        msg_lower = user_msg.lower()

        STOPWORDS = {
            "поищи", "найди", "поиск", "ищи", "посмотри", "глянь", "проверь", "проверить", "найти",
            "почте", "почта", "почту", "почты", "почтой", "письмо", "письма", "писем", "письмах",
            "сообщение", "сообщения", "сообщений", "сообщениях",
            "группе", "группа", "группу", "группы", "группах",
            "чате", "чат", "чата", "чаты", "чатах", "телеграм", "telegram", "телеге",
            "или", "что", "где", "когда", "есть", "было", "были", "был", "была", "какие", "какой", "какая", "какое",
            "скинь", "пришли", "отправь", "дай", "покажи", "пожалуйста", "секретарь", "бот",
            "для", "про", "обо", "обоих", "все", "всё", "всех", "мне", "нам", "вас", "вашей", "нашей", "его", "ее", "её",
        }

        def stem_token(w: str) -> str:
            w_l = w.lower()
            for end in ("ый", "ой", "ий", "ая", "яя", "ое", "ее", "ые", "ие", "ых", "их", "ым", "им", "ом", "ем", "ам", "ям", "ами", "ями", "ах", "ях", "ов", "ев", "ей", "а", "я", "у", "ю", "е", "о"):
                if w_l.endswith(end) and len(w_l) - len(end) >= 4:
                    return w_l[:-len(end)]
            return w_l

        words = [w.strip(".,?!:;\"'()[]{}«»").lower() for w in user_msg.split()]
        filtered_words = [w for w in words if len(w) > 2 and w not in STOPWORDS]
        active_words = filtered_words if filtered_words else [w for w in words if len(w) > 2]
        tokens = [stem_token(t) for t in active_words]

        found_items: list[dict[str, Any]] = []
        if tokens:
            clauses = []
            params: list[Any] = []
            for t in tokens[:4]:
                clauses.append("(LOWER(summary_text) LIKE ? OR LOWER(payload_json) LIKE ?)")
                p = f"%{t}%"
                params.extend([p, p])

            where_sql = " OR ".join(clauses)
            params.append(5)
            try:
                async with self.db.connection() as conn:
                    cursor = await conn.execute(
                        f"SELECT id, summary_text, payload_json, created_at FROM action_items WHERE {where_sql} ORDER BY id DESC LIMIT ?;",
                        tuple(params),
                    )
                    rows = await cursor.fetchall()
                    found_items = [dict(r) for r in rows]
            except Exception as e:
                logger.debug("Error searching action items: %s", e)

        if found_items:
            lines = ["📱 НАЙДЕННЫЕ СООБЩЕНИЯ В TELEGRAM-КАНАЛАХ:"]
            for item in found_items:
                lines.append(f"• [{str(item.get('created_at', ''))[:16]}] {item.get('summary_text', '')}")
            return "\n".join(lines)

        if any(k in msg_lower for k in ("телеграм", "telegram", "чат", "групп", "тг")):
            return (
                "📱 Telegram: В отслеживаемых Telegram-группах (студенческие группы кафедры: м531, м631к, М631К) "
                "сообщений по данному запросу нет (это учебные студенческие группы, а не служебный чат кафедры). "
                "Вся служебная кафедральная рассылка от зам. зав. каф. Новиковой Ю.А. велась через корпоративную электронную почту."
            )

        return ""

    def _search_local_files_context(self, user_msg: str) -> tuple[str, list[dict[str, Any]]]:
        """Search local documents, templates, and regulations in methodist raw storage."""
        msg_lower = user_msg.lower()
        base_dir = Path("/opt/assistant-core/data/methodist/raw")
        if not base_dir.exists():
            return "", []

        found_files = []
        catalog = [
            {
                "path": base_dir / "templates" / "Форма_отчета_эффективный_контракт_ППС_2026.docx",
                "name": "Форма_отчета_эффективный_контракт_ППС_2026.docx",
                "desc": "Официальный действующий бланк отчета кафедры физики от Новиковой Ю.А. (август 2026)",
                "keywords": ["контракт", "эффективн", "шаблон", "бланк", "форма", "ппс", "новиков"],
            },
            {
                "path": base_dir / "dept_physics" / "Попов_ДА_Образец_отчета_эффективный_контракт.docx",
                "name": "Попов_ДА_Образец_отчета_эффективный_контракт.docx",
                "desc": "Утвержденный заполненный образец отчета доцента Д.А. Попова (10.8 балла)",
                "keywords": ["контракт", "эффективн", "попов", "образец", "пример", "отчет"],
            },
            {
                "path": base_dir / "admin_lna" / "Приказ_ГУАП_05-259-26_Эффективный_контракт_2026.pdf",
                "name": "Приказ_ГУАП_05-259-26_Эффективный_контракт_2026.pdf",
                "desc": "Приказ ректора ГУАП № 05-259/26 от 17.04.2026 об утверждении изменений в критериях",
                "keywords": ["приказ", "контракт", "эффективн", "05-259", "регламент", "лна"],
            },
            {
                "path": base_dir / "admin_lna" / "Критерии_эффективного_контракта_ГУАП_2026.pdf",
                "name": "Критерии_эффективного_контракта_ГУАП_2026.pdf",
                "desc": "Официальная шкала баллов и критериев стимулирующих выплат (Таблица 3 Положения)",
                "keywords": ["критери", "балл", "таблиц", "шкал", "контракт", "эффективн", "стимулир"],
            },
            {
                "path": base_dir / "admin_lna" / "polozhenie_ob_effektivnom_kontrakte_guap_2026.md",
                "name": "polozhenie_ob_effektivnom_kontrakte_guap_2026.md",
                "desc": "Сводный аналитический регламент эффективного контракта кафедры физики ГУАП 2026",
                "keywords": ["положен", "регламент", "контракт", "эффективн"],
            },
            {
                "path": base_dir / "templates" / "Титульный_лист_и_протокол_ЛР2_Оптика.docx",
                "name": "Титульный_лист_и_протокол_ЛР2_Оптика.docx",
                "desc": "Официальный шаблон титульного листа и протокола измерений ЛР по оптике",
                "keywords": ["титульн", "оптик", "протокол", "лаб"],
            },
            {
                "path": base_dir / "templates" / "Титульный_лист_отчета_о_практической_работе_2025.docx",
                "name": "Титульный_лист_отчета_о_практической_работе_2025.docx",
                "desc": "Официальный шаблон титульного листа практической работы ГУАП",
                "keywords": ["титульн", "практик", "отчет"],
            },
        ]

        for item in catalog:
            if item["path"].exists() and any(k in msg_lower for k in item["keywords"]):
                found_files.append(item)

        if not found_files:
            return "", []

        lines = ["📂 ДОСТУПНЫЕ ЛОКАЛЬНЫЕ ФАЙЛЫ И БЛАНКИ В БАЗЕ СЕКРЕТАРЯ (ГОТОВЫ К ОТПРАВКЕ):"]
        for f in found_files:
            lines.append(f"• `{f['name']}` — {f['desc']} (Путь: {f['path']})")
        lines.append("💡 *Если пользователь просит прислать/скинуть файл, секретарь может сразу отправить его прямо в чат Telegram!*")

        return "\n".join(lines), found_files

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

    async def _build_grounding_context(
        self,
        user_msg: str,
        now_local: datetime,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Gather all real-time operational context and search hits into a unified grounding block."""
        now_str = now_local.strftime("%A, %d %B %Y г., %H:%M MSK")
        
        # Parallel data retrieval
        schedule_task = self._get_schedule_context(now_local)
        tydex_task = self._get_tydex_context()
        email_overview_task = self._get_email_overview()
        email_search_task = self._search_email_context(user_msg)
        tg_search_task = self._search_telegram_context(user_msg)
        lms_task = self._get_lms_context()

        sched_ctx, tydex_ctx, em_over_ctx, em_search_ctx, tg_ctx, lms_ctx = await asyncio.gather(
            schedule_task, tydex_task, email_overview_task, email_search_task, tg_search_task, lms_task
        )

        local_files_ctx, matched_files = self._search_local_files_context(user_msg)

        blocks = [
            f"🕒 Текущее системное время: {now_str}",
            sched_ctx,
            tydex_ctx,
            em_over_ctx,
        ]

        if em_search_ctx:
            blocks.append(em_search_ctx)
        if tg_ctx:
            blocks.append(tg_ctx)
        if local_files_ctx:
            blocks.append(local_files_ctx)
        blocks.append(lms_ctx)

        # Check if query needs deep Methodist assistance (exclude pure search/administrative requests)
        is_search_or_admin_query = any(k in user_msg.lower() for k in (
            "поищи", "найди", "поиск", "почт", "письм", "телеграм", "telegram", "чат", "групп",
            "расписан", "пар", "тидекс", "табел", "часы", "норм", "файлы", "скинь", "пришли", "отправь"
        ))
        if not is_search_or_admin_query:
            try:
                scope_res = await self.methodist.check_scope(user_msg)
                if scope_res.get("is_in_scope", False):
                    methodist_ans = await self.methodist.ask(user_msg, caller="secretary_dialog")
                    ans_text = (methodist_ans.get("answer") or "").strip()
                    if (
                        not methodist_ans.get("is_out_of_scope")
                        and ans_text
                        and not ans_text.startswith("Извините, я — специализированный агент-методист")
                        and "не имею доступа" not in ans_text
                    ):
                        blocks.append(
                            f"📚 СПРАВКА ОТ АГЕНТА-МЕТОДИСТА КАФЕДРЫ ФИЗИКИ (ОФИЦИАЛЬНЫЙ РЕГЛАМЕНТ/ПОСОБИЯ):\n"
                            f"{ans_text}"
                        )
            except Exception as me:
                logger.debug("Methodist enrichment skipped: %s", me)

        return "\n\n".join(blocks), matched_files

    async def answer_user_message(
        self,
        user_id: int,
        message_text: str,
        return_files: bool = False,
    ) -> Any:
        """Process arbitrary user message with multi-turn memory and system grounding."""
        cleaned_text = message_text.strip()
        if not cleaned_text:
            msg = "Я готов ответить на любой ваш вопрос. Напишите, что вас интересует!"
            return (msg, []) if return_files else msg

        # Handle explicit reset command
        if cleaned_text.lower() in ("/clear", "/reset", "очисти диалог", "забудь контекст", "сброс"):
            await self.db.clear_dialog_history(user_id)
            msg = "🧹 **Контекст диалога успешно очищен.** Я готов к новым вопросам!"
            return (msg, []) if return_files else msg

        now_local = datetime.now(ZoneInfo(config.TZ))

        # 1. Fetch grounding context & matched files
        grounding_context, matched_files = await self._build_grounding_context(cleaned_text, now_local)

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

Дай прямой, точный, вежливый и структурированный ответ как его личный секретарь. Если найдены письма или документы, прямо укажи их даты, отправителя и подробности."""

        # 4. Generate response via Gemini with multi-model fallback
        if not self.is_configured:
            answer_text = (
                "⚠️ Сервис генерации временно работает в автономном режиме (без ключа API).\n\n"
                f"**Краткая оперативная сводка:**\n\n"
                f"{grounding_context}"
            )
        else:
            candidate_models = [self.model, "gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-flash-lite-latest"]
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

                    resp = await asyncio.wait_for(
                        client.aio.models.generate_content(
                            model=mod,
                            contents=user_prompt,
                            config=types.GenerateContentConfig(**cfg_kwargs),
                        ),
                        timeout=25.0,
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

        if return_files:
            return answer_text, matched_files
        return answer_text
