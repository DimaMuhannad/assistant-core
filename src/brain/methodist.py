"""Methodist Agent: Specialized educational and methodological AI agent for SUAI Physics Dept."""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from src import config
from src.storage.db import Database

logger = logging.getLogger(__name__)

METHODIST_SYSTEM_PROMPT = """Ты — официальный AI-агент-методист кафедры физики (Кафедра №1) Санкт-Петербургского государственного университета аэрокосмического приборостроения (ГУАП).
Твой куратор и ведущий преподаватель: доцент кафедры физики, к.ф.-м.н. Попов Дмитрий Александрович.

ТВОЯ ЕДИНСТВЕННАЯ И СТРОГО ОГРАНИЧЕННАЯ МИССИЯ:
Быть безупречным экспертом по учебному процессу, рабочим программам дисциплин (РПД), методическим указаниям, ГОСТам оформления студенческих работ и локальным нормативным актам (ЛНА) ГУАП.

ОБЛАСТЬ ТВОЕЙ КОМПЕТЕНЦИИ (IN-SCOPE):
1. Рабочие программы дисциплин (РПД): «Физика», «Физические основы нанотехнологий» (ФОНТ), «Основы проектной деятельности» (ОПД), «Основы проектной деятельности в профессии» (ОПДвП).
2. Методические указания к лабораторным работам и физическому практикуму (допуск, проведение измерений, визирование протоколов преподавателем, расчет прямых и косвенных погрешностей, правила округления, построение графиков с крестами погрешностей по МНК, защита).
3. ГОСТы оформления студенческих отчетов: ГОСТ 7.32-2017 (структура, поля 30-10-20-20 мм, шрифт 14 pt, интервал 1.5, нумерация со 2-й стр.), ГОСТ 2.105-2019 (ЕСКД), ГОСТ 7.0.5-2008 (библиографические ссылки), правила оформления титульных листов ГУАП.
4. Положение о Балльно-рейтинговой системе (БРС) ГУАП: 100-балльная шкала, текущий контроль (до 60 баллов), промежуточная аттестация (до 40 баллов), порог допуска к экзамену/зачету (35 баллов), критерии оценок (85-100 отлично, 70-84 хорошо, 55-69 удовл., <55 неудовл.).
5. Специфика требований доцента Д.А. Попова: обязательность двух страниц при проверке отчета (1-я стр. — титульный лист установленного образца с подписями; 2-я стр. — оригинальный протокол измерений с личной подписью преподавателя из лаборатории; при отсутствии подписи на протоколе работа не принимается).

СТРОЖАЙШЕЕ ПРАВИЛО ГРАНИЦЫ КОНТЕКСТА (GUARDRAIL / OUT-OF-SCOPE):
Если вопрос пользователя (студента, преподавателя или другого агента) НЕ ОТНОСИТСЯ к методической и образовательной деятельности кафедры физики ГУАП (например: вопросы про приборостроение и оптику ООО «Тидекс», личные планы, погоду, общие рассуждения, постороннее программирование, новости):
ТЫ КАТЕГОРИЧЕСКИ ОБЯЗАН ОТКАЗАТЬСЯ ОТ ОТВЕТА ПО ШАБЛОНУ:
«Извините, я — специализированный агент-методист кафедры физики ГУАП. Моя область знаний строго ограничена учебными программами (РПД), методическими указаниями, ГОСТами оформления студенческих работ и регламентами ГУАП. Я не уполномочен отвечать на вопросы вне этой предметной области.»

ПРАВИЛА ОТВЕТА (КОГДА ВОПРОС ПО ТЕМЕ):
1. Академический, доброжелательный, наставительный и четкий тон.
2. Всегда давай прямые и конкретные ссылки на документы (например: «Согласно ГОСТ 7.32-2017 (п. 2)...», «В соответствии с Положением о БРС ГУАП...», «По регламенту физического практикума кафедры №1...»).
3. Обязательно напоминай студентам о критических правилах (наличие подписи преподавателя на протоколе измерений, поля 30 мм слева, округление погрешностей до 1–2 значащих цифр).
4. Форматируй ответ в красивом Markdown, приводи примеры оформления и формулы при необходимости.
"""

SCOPE_CHECK_PROMPT = """Определи, относится ли следующий вопрос к методическому и образовательному контексту кафедры физики ГУАП (РПД, лабораторные работы по физике/ФОНТ/ОПД, расчет погрешностей, правила оформления отчетов по ГОСТ 7.32/2.105, титульные листы, правила защиты, БРС ГУАП, правила сдачи долгов/экзаменов).

Вопрос: "{question}"

Ответь строго в формате JSON:
{{
  "is_in_scope": true/false,
  "category": "gost" | "rpd" | "lab_manual" | "admin_lna" | "dept_physics" | "out_of_scope",
  "reason": "краткое пояснение"
}}
"""


class MethodistService:
    """Core autonomous agent for academic regulations, GOSTs, and curriculum."""

    def __init__(
        self,
        db: Database,
        raw_dir: str | Path = "/opt/assistant-core/data/methodist/raw",
        kb_dir: str | Path = "/opt/assistant-core/data/methodist/knowledge_base",
        api_key: str | None = config.GEMINI_API_KEY,
        model: str = config.GEMINI_MODEL,
    ) -> None:
        self.db = db
        self.raw_dir = Path(raw_dir)
        self.kb_dir = Path(kb_dir)
        self.api_key = api_key or ""
        self.model = model
        self._client: genai.Client | None = None

    def get_client(self) -> genai.Client:
        if self._client is None:
            if not self.api_key:
                raise ValueError("GEMINI_API_KEY is not configured.")
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    # --- 1. Ingestion & Indexing ---

    def _split_into_sections(self, content: str, default_title: str) -> list[dict[str, str]]:
        """Split markdown content into logical chunks based on headers."""
        lines = content.split("\n")
        chunks: list[dict[str, str]] = []
        current_title = default_title
        current_lines: list[str] = []

        for line in lines:
            if line.startswith("## ") or line.startswith("# "):
                if current_lines:
                    text_block = "\n".join(current_lines).strip()
                    if len(text_block) > 40:
                        chunks.append({"section_title": current_title, "chunk_text": text_block})
                    current_lines = []
                current_title = line.lstrip("#").strip()
            current_lines.append(line)

        if current_lines:
            text_block = "\n".join(current_lines).strip()
            if len(text_block) > 40:
                chunks.append({"section_title": current_title, "chunk_text": text_block})

        return chunks

    async def ingest_file(self, file_path: str | Path, category: str | None = None) -> dict[str, Any]:
        """Read a file, parse chunks, compute hash, and index into SQLite & FTS5."""
        p = Path(file_path)
        if not p.is_file():
            raise FileNotFoundError(f"File not found: {p}")

        content = p.read_text(encoding="utf-8")
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        # Determine category from parent directory if not provided
        if not category:
            parent_name = p.parent.name
            category = parent_name if parent_name in ("gost", "rpd", "lab_manuals", "admin_lna", "dept_physics") else "general"

        title = p.stem.replace("_", " ")
        first_line = content.strip().split("\n")[0]
        if first_line.startswith("# "):
            title = first_line.lstrip("#").strip()

        chunks = self._split_into_sections(content, default_title=title)

        # Extract summary deterministically from first paragraph without wasting LLM quota
        paras = [p.strip() for p in content.split("\n\n") if p.strip() and not p.strip().startswith("#")]
        summary_text = paras[0][:400] if paras else title
        key_terms = category

        doc_id = await self.db.save_methodist_document(
            category=category,
            title=title,
            file_path=str(p.resolve()),
            content_hash=content_hash,
            summary=summary_text,
            key_terms=key_terms,
            total_chunks=len(chunks),
        )

        inserted_chunks = await self.db.replace_methodist_chunks(doc_id, chunks)
        logger.info("Ingested methodist document '%s' (ID %d) with %d chunks into FTS5", title, doc_id, inserted_chunks)

        return {
            "doc_id": doc_id,
            "title": title,
            "category": category,
            "chunks_count": inserted_chunks,
            "file_path": str(p),
        }

    async def ingest_all_raw_directory(self) -> dict[str, Any]:
        """Scan entire raw/ directory and index all markdown and text documents."""
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        results = []
        for file_p in self.raw_dir.rglob("*.md"):
            try:
                res = await self.ingest_file(file_p)
                results.append(res)
            except Exception as e:
                logger.error("Failed ingesting %s: %s", file_p.name, e)

        return {
            "total_ingested": len(results),
            "documents": results,
        }

    # --- 2. Scope Verification & Query Answering ---

    async def check_scope(self, question: str) -> dict[str, Any]:
        """Check if question falls strictly inside Methodist domain using heuristics and LLM."""
        q_lower = question.lower()
        out_of_scope_keywords = [
            "тидекс", "табель", "смен", "часы работы", "выработка", "погод",
            "анекдот", "фильм", "игра", "криптовалют", "биткоин", "ресторан",
            "билет", "поезд", "рейс", "курс валют", "новости", "политик"
        ]
        if any(k in q_lower for k in out_of_scope_keywords):
            return {
                "is_in_scope": False,
                "category": "out_of_scope",
                "reason": "Вопрос относится к сторонней теме вне методической работы кафедры физики ГУАП",
            }

        academic_keywords = [
            "гост", "титульн", "отчет", "лабораторн", "физик", "фонт", "опд",
            "брс", "баллы", "погрешност", "протокол", "допуск", "защита",
            "практикум", "зачет", "экзамен", "кафедр", "попов", "гастелло",
            "формул", "график", "мнк", "шрифт", "поля", "студент", "семестр",
            "дедлайн", "пересдач", "рпд", "проектн", "лаба", "лабы", "методичк",
            "оформлен", "подпис", "правил"
        ]
        if any(k in q_lower for k in academic_keywords):
            return {"is_in_scope": True, "category": "academic", "reason": "Academic keyword matched"}

        try:
            client = self.get_client()
            prompt = SCOPE_CHECK_PROMPT.format(question=question)
            resp = await client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )
            raw = (resp.text or "{}").strip()
            return json.loads(raw)
        except Exception as e:
            logger.debug("Scope check error: %s", e)
            return {"is_in_scope": False, "category": "out_of_scope", "reason": "Unrecognized scope"}

    async def ask(
        self,
        question: str,
        caller: str = "user",
        caller_id: str | None = None,
    ) -> dict[str, Any]:
        """Ask a question to the Methodist Agent with strict scope guardrails and FTS retrieval."""
        cleaned_q = question.strip()
        if not cleaned_q:
            return {
                "answer": "Пожалуйста, задайте вопрос по методическим указаниям, РПД, ГОСТам или регламентам ГУАП.",
                "is_out_of_scope": True,
                "sources": [],
            }

        # 1. Guardrail Scope Check
        scope_res = await self.check_scope(cleaned_q)
        if not scope_res.get("is_in_scope", True):
            rejection_text = (
                "Извините, я — специализированный агент-методист кафедры физики ГУАП. "
                "Моя область знаний строго ограничена учебными программами (РПД), методическими указаниями, "
                "ГОСТами оформления студенческих работ и регламентами ГУАП. "
                "Я не уполномочен отвечать на вопросы вне этой предметной области."
            )
            await self.db.log_methodist_qa(
                caller_type=caller,
                caller_id=caller_id,
                question=cleaned_q,
                answer=rejection_text,
                sources_json=json.dumps([]),
                is_out_of_scope=True,
            )
            return {
                "answer": rejection_text,
                "is_out_of_scope": True,
                "sources": [],
                "scope_reason": scope_res.get("reason", "Out of domain"),
            }

        # 2. Retrieve relevant chunks via FTS5
        retrieved_chunks = await self.db.search_methodist_fts(cleaned_q, limit=6)

        # Format context for model
        context_blocks = []
        sources = []
        for ch in retrieved_chunks:
            sec = ch.get("section_title", "")
            d_title = ch.get("doc_title", "")
            txt = ch.get("chunk_text", "")
            context_blocks.append(f"### Источник: {d_title} [{sec}]\n{txt}")
            sources.append({"doc_title": d_title, "section": sec})

        combined_context = "\n\n".join(context_blocks)
        if not combined_context:
            combined_context = "В базе знаний пока нет точных совпадений по ключевым словам вопроса. Отвечай на основе общих академических стандартов кафедры физики ГУАП."

        # 3. Generate authoritative response via Gemini 3.8
        user_prompt = f"""КОНТЕКСТ МЕТОДИЧЕСКОЙ БАЗЫ ЗНАНИЙ КАФЕДРЫ ФИЗИКИ:
{combined_context}

ВОПРОС:
{cleaned_q}

Сформируй исчерпывающий, структурированный, академически точный ответ с конкретными ссылками на ГОСТы, разделы РПД или регламенты кафедры."""

        import asyncio
        client = self.get_client()
        answer_text = ""
        levels = ["MEDIUM", "LOW", "LOW"]
        for attempt, level in enumerate(levels):
            try:
                resp = await client.aio.models.generate_content(
                    model=self.model,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=METHODIST_SYSTEM_PROMPT,
                        temperature=0.2,
                        thinking_config=types.ThinkingConfig(thinking_level=level),
                    ),
                )
                answer_text = (resp.text or "").strip()
                if answer_text:
                    break
            except Exception as e:
                logger.warning("Attempt %d (level=%s) failed: %s", attempt + 1, level, e)
                if attempt < len(levels) - 1:
                    await asyncio.sleep(1.5 * (attempt + 1))
                else:
                    answer_text = f"⚠️ Временная ошибка сервиса генерации методического ответа ({e}). Пожалуйста, повторите запрос через минуту."

        # 4. Log interaction into persistent memory
        await self.db.log_methodist_qa(
            caller_type=caller,
            caller_id=caller_id,
            question=cleaned_q,
            answer=answer_text,
            sources_json=json.dumps(sources, ensure_ascii=False),
            is_out_of_scope=False,
        )

        return {
            "answer": answer_text,
            "is_out_of_scope": False,
            "sources": sources,
            "chunks_used": len(retrieved_chunks),
        }

    # --- 3. Teaching & On-the-fly Knowledge Ingestion ---

    async def teach_guideline(self, title: str, content: str, category: str = "dept_physics") -> dict[str, Any]:
        """Save a new guideline/rule into agent's directory, index it, and confirm learning."""
        target_dir = self.raw_dir / category
        target_dir.mkdir(parents=True, exist_ok=True)

        clean_slug = re.sub(r"[^\w\-]+", "_", title.lower()).strip("_")
        file_path = target_dir / f"{clean_slug}.md"

        header = f"# {title}\n\n*Добавлено преподавателем: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n"
        file_path.write_text(header + content.strip() + "\n", encoding="utf-8")

        ingest_res = await self.ingest_file(file_path, category=category)
        return {
            "status": "success",
            "file_path": str(file_path),
            "ingest_result": ingest_res,
        }

    async def get_stats(self) -> dict[str, Any]:
        """Return summary of indexed knowledge base."""
        docs = await self.db.list_methodist_documents()
        by_cat = {}
        for d in docs:
            c = d.get("category", "other")
            by_cat[c] = by_cat.get(c, 0) + 1
        return {
            "total_documents": len(docs),
            "by_category": by_cat,
            "documents": [{"title": d["title"], "category": d["category"], "chunks": d["total_chunks"]} for d in docs],
        }
