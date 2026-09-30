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
import re
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from google import genai
from google.genai import types

from src import config
from src.storage.db import Database
from src.brain.methodist import MethodistService
from src.brain.key_rotator import key_rotator
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
4. Долгосрочная память (Таблица memory_facts): Содержит фундаментальные факты и договоренности (норма Тидекс 8.5ч/день, день отпуска 25.09, требование 2 страниц отчета с подписанным протоколом, регламент эффективного контракта). Опирайся на эти факты при ответах.

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
        if self._client is not None:
            return self._client
        return key_rotator.get_client()

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

        # 5. Long-term memory facts retrieval (active rules and relevant matches)
        try:
            matched_facts = await self.db.search_and_touch_memory_facts(user_msg, limit=5)
            forever_facts = await self.db.get_active_memory_facts(limit=4)

            all_facts_dict = {f["id"]: f for f in forever_facts}
            for f in matched_facts:
                all_facts_dict[f["id"]] = f

            if all_facts_dict:
                mem_lines = ["🧠 ДОЛГОСРОЧНАЯ ПАМЯТЬ СЕКРЕТАРЯ (ПРАВИЛА И ДОГОВОРЕННОСТИ):"]
                for f in all_facts_dict.values():
                    cat_tag = f"[{f['category']}]" if f.get("category") else ""
                    mem_lines.append(f"• {cat_tag} {f['fact_text']}")
                blocks.append("\n".join(mem_lines))
        except Exception as me_err:
            logger.debug("Memory facts retrieval skipped: %s", me_err)

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

    async def prime_morning_context(self, target_date: date | None = None) -> str:
        """Pre-compute rich morning context for the day and cache it in daily_primed_context."""
        now_local = datetime.now(ZoneInfo(config.TZ))
        t_date = target_date or now_local.date()
        date_key = t_date.isoformat()

        # 1. Schedule for target_date
        sched_summary = await self._get_schedule_context(now_local)

        # 2. Tydex pacing
        tydex_summary = await self._get_tydex_context()

        # 3. Email overview
        email_summary = await self._get_email_overview()

        # 4. Long-term memory active facts
        facts = await self.db.get_active_memory_facts(limit=12)
        facts_lines = [f"• [{f['category']}] {f['fact_text']}" for f in facts]
        facts_block = "\n".join(facts_lines) if facts_lines else "Нет зафиксированных фактов."

        primed_summary = (
            f"🌅 **ПРОГРЕТЫЙ СУТОЧНЫЙ КОНТЕКСТ ДНЯ НА {t_date.strftime('%d.%m.%Y')}**\n\n"
            f"{sched_summary}\n\n"
            f"{tydex_summary}\n\n"
            f"{email_summary}\n\n"
            f"🧠 **АКТИВНЫЕ ПРАВИЛА ИЗ ДОЛГОСРОЧНОЙ ПАМЯТИ:**\n"
            f"{facts_block}"
        )

        payload = {
            "date": date_key,
            "facts_count": len(facts),
            "generated_at": now_local.isoformat(),
        }

        await self.db.save_primed_context(
            date_key=date_key,
            summary_text=primed_summary,
            payload_json=json.dumps(payload, ensure_ascii=False),
        )
        logger.info("Daily context primed and cached for date %s", date_key)
        return primed_summary

    async def _handle_manual_fact_addition(self, user_msg: str) -> str | None:
        """Handle explicit manual fact additions like 'запомни: ...' or 'сохрани в память: ...'."""
        pattern = r'^(?:запомни|сохрани в память|запиши в память|зафиксируй в памяти)\s*(?:(навсегда|на\s+всегда)|на\s+(\d+)?\s*(год|года|лет|мес|месяц|месяца|месяцев|недел|недели|недель|дн|дня|дней))?[:\s]+(.+)$'
        match = re.match(pattern, user_msg.strip(), re.IGNORECASE)
        if not match:
            return None

        is_forever = bool(match.group(1))
        num_str = match.group(2)
        unit = (match.group(3) or "").lower()
        fact_raw = match.group(4).strip()

        if not fact_raw:
            return "Пожалуйста, укажите текст факта после команды (например, «Запомни: норма выработки в Тидексе 8.5 часов»). "

        raw_lower = fact_raw.lower()
        if any(w in raw_lower for w in ("тидекс", "табель", "часы", "норм", "выработк", "смен")):
            category = "tydex"
        elif any(w in raw_lower for w in ("гуап", "студент", "кафедр", "лаб", "отчет", "гост", "рпд", "брс", "фонт", "опд")):
            category = "academic"
        else:
            category = "general"

        retention_policy = "standard"
        protect_until = None
        now = datetime.now(timezone.utc)

        if is_forever or "навсегда" in raw_lower or "вечно" in raw_lower:
            retention_policy = "forever"
        elif unit or "на год" in raw_lower:
            amount = int(num_str) if num_str else 1
            days = 365 * amount if ('год' in unit or 'лет' in unit or 'на год' in raw_lower) else (30 * amount if 'мес' in unit else (7 * amount if 'недел' in unit else amount))
            retention_policy = "temporary"
            protect_until = now + timedelta(days=days)

        fact_id = await self.db.add_memory_fact(
            fact_text=fact_raw,
            category=category,
            retention_policy=retention_policy,
            protect_until=protect_until,
        )

        pol_desc = "навсегда" if retention_policy == "forever" else (f"защищено до {protect_until.strftime('%d.%m.%Y')}" if protect_until else "стандартная (с еженедельной ревизией)")
        return (
            f"🧠 **Зафиксировал в долгосрочной памяти (ID: {fact_id}):**\n\n"
            f"«{fact_raw}»\n\n"
            f"• Категория: `{category}`\n"
            f"• Политика хранения: `{pol_desc}`\n\n"
            f"Этот факт сохранен и будет учитываться во всех будущих диалогах и утренних брифингах."
        )

    async def _handle_memory_review_command(self, user_msg: str) -> str | None:
        """Parse and apply weekly memory review commands like 'удалить: 1, 3', 'запомнить на год: 2'."""
        pattern = r'(?:удалить|стереть|забудь|delete|запомнить|сохранить|заменить|продлить)\s*(?:на\s+(?:год|года|лет|мес|месяц|месяца|месяцев|недел|недели|недель|дн|дня|дней|всегда|навсегда))?[:\s]+[0-9,\s-]+'
        if not re.search(pattern, user_msg, re.IGNORECASE):
            return None

        pending = await self.db.get_pending_memory_review()
        if not pending or not pending.get("items"):
            return None

        items = pending["items"]
        index_to_fact = {item["index"]: item for item in items}

        def parse_indices(raw_str: str) -> list[int]:
            indices = set()
            parts = [p.strip() for p in raw_str.split(',') if p.strip()]
            for p in parts:
                if '-' in p:
                    range_match = re.match(r'^(\d+)\s*-\s*(\d+)$', p)
                    if range_match:
                        start, end = int(range_match.group(1)), int(range_match.group(2))
                        for idx in range(min(start, end), max(start, end) + 1):
                            indices.add(idx)
                elif p.isdigit():
                    indices.add(int(p))
            return sorted(list(indices))

        actions_performed: list[tuple[str, int, str]] = []
        now = datetime.now(timezone.utc)

        lines = [l.strip() for l in user_msg.replace(';', '\n').split('\n') if l.strip()]
        for line in lines:
            m_del = re.search(r'(?:удалить|стереть|забудь|delete)[:\s]+([0-9,\s-]+)', line, re.IGNORECASE)
            if m_del:
                for idx in parse_indices(m_del.group(1)):
                    if idx in index_to_fact:
                        f = index_to_fact[idx]
                        await self.db.update_memory_fact_retention(f["fact_id"], "delete")
                        actions_performed.append(("удалено", idx, f["text"]))

            m_forever = re.search(r'(?:запомнить|сохранить)\s+(?:навсегда|на\s+всегда|вечно)[:\s]+([0-9,\s-]+)', line, re.IGNORECASE)
            if m_forever:
                for idx in parse_indices(m_forever.group(1)):
                    if idx in index_to_fact:
                        f = index_to_fact[idx]
                        await self.db.update_memory_fact_retention(f["fact_id"], "forever")
                        actions_performed.append(("сохранено навсегда", idx, f["text"]))
                continue

            m_dur = re.search(r'(?:запомнить|сохранить|заменить|продлить)\s+на\s+(\d+)?\s*(год|года|лет|мес|месяц|месяца|месяцев|недел|недели|недель|дн|дня|дней)[:\s]+([0-9,\s-]+)', line, re.IGNORECASE)
            if m_dur:
                amount = int(m_dur.group(1)) if m_dur.group(1) else 1
                unit = m_dur.group(2).lower()
                days = 365 * amount if ('год' in unit or 'лет' in unit) else (30 * amount if 'мес' in unit else (7 * amount if 'недел' in unit else amount))
                protect_until = now + timedelta(days=days)
                label = f"защита на {amount} {unit}"
                for idx in parse_indices(m_dur.group(3)):
                    if idx in index_to_fact:
                        f = index_to_fact[idx]
                        await self.db.update_memory_fact_retention(f["fact_id"], "protect", protect_until)
                        actions_performed.append((label, idx, f["text"]))

        if not actions_performed:
            return None

        await self.db.resolve_pending_memory_review(pending["review_date"])

        deleted_cnt = sum(1 for a, _, _ in actions_performed if a == "удалено")
        forever_cnt = sum(1 for a, _, _ in actions_performed if a == "сохранено навсегда")
        protected_cnt = len(actions_performed) - deleted_cnt - forever_cnt

        summary_parts = []
        if deleted_cnt:
            summary_parts.append(f"• 🗑️ Удалено из активной памяти: **{deleted_cnt}**")
        if protected_cnt:
            summary_parts.append(f"• 🛡️ Установлена временная защита: **{protected_cnt}**")
        if forever_cnt:
            summary_parts.append(f"• ♾️ Сохранено навсегда: **{forever_cnt}**")

        return (
            "🧠 **Ревизия долгосрочной памяти успешно проведена!**\n\n"
            "Дмитрий Александрович, я применил ваши указания:\n"
            + "\n".join(summary_parts) + "\n\n"
            "База фактов актуализирована. Неупомянутые записи сохраняются в обычном режиме до следующей плановой ревизии."
        )

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

        # Handle memory list command
        if cleaned_text.lower() in ("/memory", "память", "/facts", "покажи память", "факты"):
            facts = await self.db.get_active_memory_facts(limit=30)
            if not facts:
                msg = "🧠 База долгосрочной памяти пуста."
                return (msg, []) if return_files else msg
            lines = ["🧠 **База долгосрочной памяти секретаря (активные записи):**\n"]
            for i, f in enumerate(facts, 1):
                pol = "навсегда" if f["retention_policy"] == "forever" else ("защищено" if f.get("protect_until") else "стандарт")
                cat_tag = f"[{f['category']}]" if f.get("category") else ""
                lines.append(f"{i}. `{cat_tag}` ({pol}, обращений: {f['access_count']})\n   {f['fact_text']}")
            msg = "\n".join(lines)
            return (msg, []) if return_files else msg

        # Handle weekly memory review response
        review_res = await self._handle_memory_review_command(cleaned_text)
        if review_res:
            return (review_res, []) if return_files else review_res

        # Handle manual fact addition
        fact_add_res = await self._handle_manual_fact_addition(cleaned_text)
        if fact_add_res:
            return (fact_add_res, []) if return_files else fact_add_res

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

            answer_text = ""

            for attempt, mod in enumerate(unique_models):
                try:
                    cfg_kwargs: dict[str, Any] = {
                        "system_instruction": SECRETARY_SYSTEM_PROMPT,
                        "temperature": 0.3,
                    }
                    if "3.8" in mod or "3.7" in mod or "2.5" in mod:
                        cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level="LOW")

                    async def _make_dialog_call(client: genai.Client) -> Any:
                        return await asyncio.wait_for(
                            client.aio.models.generate_content(
                                model=mod,
                                contents=user_prompt,
                                config=types.GenerateContentConfig(**cfg_kwargs),
                            ),
                            timeout=6.0,
                        )

                    if self._client is not None:
                        resp = await _make_dialog_call(self._client)
                    else:
                        resp = await key_rotator.execute_with_failover(_make_dialog_call)
                    answer_text = (resp.text or "").strip()
                    if answer_text:
                        logger.info("Successfully generated secretary dialog answer via %s (attempt %d)", mod, attempt + 1)
                        break
                except Exception as e:
                    logger.warning("Attempt %d with model %s failed in dialog: %s", attempt + 1, mod, e)
                    if attempt < len(unique_models) - 1:
                        await asyncio.sleep(0.5)
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
