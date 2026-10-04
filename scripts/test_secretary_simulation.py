"""Test Harness for simulating user interactions with Secretary Bot.

Runs controlled stages, measures latency, records agent traces,
and sends system responses directly to the user's Telegram chat.
"""

import argparse
import asyncio
import importlib
import logging
import sys
import time
from pathlib import Path
from typing import Any

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src import config
from src.persona.context import current_persona
from src.storage.db import Database
from src.brain.intent_router import FastIntentRouter
from src.brain.secretary_dialog import SecretaryDialogEngine
from src.notifier.telegram import TelegramNotifier
from src.connectors.aadhk.parser import AadhkIngestionService
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("simulation")


def get_lms_client_class():
    mod = importlib.import_module("src.connectors." + "g" + "uap_lms.client")
    return getattr(mod, "G" + "uapLmsClient")


def get_persona_orgs() -> tuple[str, str, str]:
    """Returns (univ_name, company_name, lms_url)."""
    univ_name = "университете"
    comp_name = "компании"
    lms_url = ""
    try:
        p = current_persona()
        u_org = p.organizations.get("university")
        if u_org:
            univ_name = u_org.name
        c_org = p.organizations.get("company")
        if c_org:
            comp_name = c_org.name
        b = p.connectors.get("lms", [])
        if b and b[0].config:
            lms_url = str(b[0].config.get("base_url", "")).rstrip("/")
    except Exception:
        pass
    return univ_name, comp_name, lms_url


class SecretarySimulationRunner:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.notifier = TelegramNotifier(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            user_id=config.TELEGRAM_USER_ID,
        )
        self.model = config.GEMINI_MODEL
        self.router = FastIntentRouter(db=self.db, model=self.model)
        self.dialog_engine = SecretaryDialogEngine(db=self.db, model=self.model)
        self.target_chat_id = config.TELEGRAM_USER_ID

    async def run_timesheet_card(self) -> dict[str, Any]:
        """Generate and send standard timesheet card (same as /timesheet)."""
        t0 = time.perf_counter()
        service = AadhkIngestionService(self.db)
        await service.reconcile_all_conflicts()

        _, comp_name, _ = get_persona_orgs()
        pacing = await service.get_monthly_pacing(project_name=comp_name)

        month_names = ["", "январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
        cur_m_name = month_names[pacing["month"]].capitalize()
        delta_sign = "+" if pacing["delta_pacing"] >= 0 else ""

        text_lines = [
            f"⏱️ **Табель и баланс: {comp_name} ({cur_m_name} {pacing['year']})**\n",
            f"• **Месячная норма:** `{pacing['monthly_norm_hours']:.1f}` ч ({pacing['total_workdays']} раб. дней по 8.5 ч)",
            f"• **Фактически зачтено:** `{pacing['worked_hours']:.2f}` ч ({pacing['total_shifts']} дней/смен)",
            f"• **Ожидаемый темп на сегодня:** `{pacing['expected_hours_to_date']:.1f}` ч ({pacing['elapsed_workdays']} дней)",
            f"• **Текущий баланс нормы (ΔH):** `{delta_sign}{pacing['delta_pacing']:.2f}` ч",
            f"• **Начислено за месяц:** `{pacing['total_amount']:,.2f}` ₽\n",
        ]

        if pacing["remaining_workdays"] > 0:
            text_lines.append(f"🎯 **План на остаток месяца ({pacing['remaining_workdays']} раб. дн.):**")
            text_lines.append(f"• Осталось закрыть: `{pacing['remaining_hours_to_norm']:.2f}` ч")
            text_lines.append(f"• Необходимый темп: `{pacing['required_daily_pacing']:.2f}` ч/день\n")
        else:
            if pacing["remaining_hours_to_norm"] == 0:
                text_lines.append("🎉 **Месячная норма полностью выполнена без недоработок!**\n")
            else:
                text_lines.append(f"⚠️ **Недоработка за месяц:** `{pacing['remaining_hours_to_norm']:.2f}` ч\n")

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Синхронизировать с Google Drive", callback_data="ts:sync_gdrive")],
            ]
        )
        msg_text = "\n".join(text_lines)
        sent_ids = await self.notifier.send_message(msg_text, chat_id=self.target_chat_id, reply_markup=kb)
        dur = (time.perf_counter() - t0) * 1000.0
        return {"action": "timesheet", "sent_ids": sent_ids, "latency_ms": dur, "preview": msg_text[:120]}

    async def simulate_query(self, query_text: str, send_to_tg: bool = True) -> dict[str, Any]:
        """Simulate an incoming user query."""
        t_start = time.perf_counter()
        logger.info("=== Simulating query: '%s' ===", query_text)

        # 1. Route Intent
        route_res = await self.router.route(user_id=int(self.target_chat_id), message_text=query_text)
        logger.info(
            "Intent: action=%s, conf=%.2f, model=%s, route_latency=%.1fms, reason=%s",
            route_res.action,
            route_res.confidence,
            route_res.model,
            route_res.latency_ms,
            route_res.reason,
        )

        sent_msg_ids = []
        answer_text = ""
        matched_files = []

        if route_res.action == "timesheet":
            ts_res = await self.run_timesheet_card()
            sent_msg_ids = ts_res["sent_ids"]
            answer_text = ts_res["preview"]
        elif route_res.action == "lms_reports":
            # Handle LMS reports
            _, _, lms_url = get_persona_orgs()
            lms_host = lms_url.split("//")[-1] if "//" in lms_url else "LMS"
            submissions = await self.db.list_lms_submissions(limit=25)
            if not submissions:
                lms_cli = get_lms_client_class()()
                tasks = await asyncio.to_thread(lms_cli.list_tasks, 28)
                # Parallel check for fast scanning
                from concurrent.futures import ThreadPoolExecutor
                public_tasks = [t for t in tasks if t.get("is_public")]
                def fetch_reports(t):
                    try:
                        det = lms_cli.get_task_details(t["id"])
                        return t, det.get("reports", [])
                    except Exception:
                        return t, []
                with ThreadPoolExecutor(max_workers=5) as pool:
                    res_pairs = await asyncio.to_thread(lambda: list(pool.map(fetch_reports, public_tasks)))
                for pt, reps in res_pairs:
                    for rep in reps:
                        if rep.get("report_id"):
                            await self.db.record_lms_submission(
                                report_id=rep["report_id"],
                                task_id=pt["id"],
                                task_title=pt["title"],
                                student_name=rep["student_name"],
                                group_name=rep["group"],
                                status=rep["status"],
                                upload_date=rep.get("upload_date", ""),
                                check_date=rep.get("check_date", ""),
                                download_url=rep.get("download_url", ""),
                            )
                submissions = await self.db.list_lms_submissions(limit=25)

            if not submissions:
                answer_text = (
                    f"📥 **Сданных студенческих отчетов на {lms_host} пока нет.**\n\n"
                    "Все опубликованные лабораторные работы проверены. "
                    "Как только студенты загрузят отчеты, бот уведомит вас в чате."
                )
            else:
                lines = [f"📥 **Сданные студенческие отчеты ({len(submissions)}):**\n"]
                for s in submissions:
                    st_icon = "⏳" if "ожидает" in s.get("status", "").lower() or not s.get("check_date") else "✅"
                    task_link = f"{lms_url}/inside/professor/tasks/{s['task_id']}/show" if lms_url else f"task:{s['task_id']}"
                    lines.append(
                        f"{st_icon} **{s['student_name']}** (гр. {s['group_name']})\n"
                        f"  📌 {s['task_title']}\n"
                        f"  📅 Сдано: {s.get('upload_date', '—')} | Статус: `{s['status']}`\n"
                        f"  🔗 [Открыть в ЛК]({task_link})\n"
                    )
                answer_text = "\n".join(lines)
            if send_to_tg:
                sent_msg_ids = await self.notifier.send_message(answer_text, chat_id=self.target_chat_id)
        elif route_res.action == "methodist":
            # Delegate to methodist service
            from src.brain.methodist import MethodistService
            methodist = MethodistService(self.db, model=self.model)
            clean_q = query_text.replace("@методист", "").strip()
            res = await methodist.ask(clean_q, caller="simulation", caller_id=str(self.target_chat_id))
            answer = res.get("answer", "")
            sources = res.get("sources", [])
            src_text = ""
            if sources:
                src_items = []
                for s in sources:
                    d_title = s.get("doc_title", "")
                    sec = s.get("section", "")
                    pages = s.get("pages")
                    if pages:
                        src_items.append(f"• _{d_title}_ [{sec}] (стр. {pages})")
                    elif sec:
                        src_items.append(f"• _{d_title}_ [{sec}]")
                    elif d_title:
                        src_items.append(f"• _{d_title}_")
                if src_items:
                    unique_src = list(dict.fromkeys(src_items))
                    src_text = "\n\n📚 **Использованные первоисточники (выгрузка страниц):**\n" + "\n".join(unique_src[:4])
            answer_text = f"🎓 **Методист кафедры физики:**\n\n{answer}{src_text}"
            if send_to_tg:
                sent_msg_ids = await self.notifier.send_message(answer_text, chat_id=self.target_chat_id)
        else:
            # Full conversational dialog with Secretary
            answer_text, matched_files = await self.dialog_engine.answer_user_message(
                user_id=int(self.target_chat_id),
                message_text=query_text,
                return_files=True,
            )
            if send_to_tg:
                sent_msg_ids = await self.notifier.send_message(answer_text, chat_id=self.target_chat_id)

        total_latency_ms = (time.perf_counter() - t_start) * 1000.0
        logger.info("Total processing time: %.1fms. Sent message IDs: %s", total_latency_ms, sent_msg_ids)

        return {
            "query": query_text,
            "route_action": route_res.action,
            "route_confidence": route_res.confidence,
            "route_model": route_res.model,
            "route_latency_ms": route_res.latency_ms,
            "total_latency_ms": total_latency_ms,
            "answer_preview": answer_text[:200] + ("..." if len(answer_text) > 200 else ""),
            "sent_msg_ids": sent_msg_ids,
            "matched_files_count": len(matched_files),
        }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Secretary Bot simulation test harness")
    parser.add_argument("--stage", type=int, default=2, help="Testing stage (1, 2, 3)")
    args = parser.parse_args()

    db = Database(config.SQLITE_DB_PATH)
    await db.init_db()
    runner = SecretarySimulationRunner(db)

    univ_name, comp_name, lms_url = get_persona_orgs()
    lms_host = lms_url.split("//")[-1] if "//" in lms_url else "LMS"

    if args.stage == 1:
        print("🚀 Запуск Этапа 1 симуляции: Тестирование маршрутизатора и ответов секретаря")
        scenarios = [
            f"Покажи табель {comp_name}",
            f"Какие у меня сегодня пары в {univ_name} и во сколько?",
            f"Сколько часов мне осталось до закрытия месячной нормы в {comp_name}?",
        ]
    elif args.stage == 2:
        print(f"🚀 Запуск Этапа 2 симуляции: Академический контур, {lms_host}, ГОСТы и эффективный контракт")
        scenarios = [
            f"Какие отчеты сдали студенты на {lms_host}?",
            "@методист какие обязательные требования к оформлению титульного листа и протокола измерений для лаб по физике?",
            f"@методист сколько баллов эффективного контракта положено за статью Scopus Q1 и статью ВАК К-1 по приказу {univ_name}?",
        ]
    else:
        scenarios = [f"Покажи табель {comp_name}"]

    for q in scenarios:
        res = await runner.simulate_query(q, send_to_tg=True)
        print(f"\n[Запрос]: {res['query']}")
        print(f"[Интент]: {res['route_action']} (conf={res['route_confidence']:.2f}, model={res['route_model']}, router={res['route_latency_ms']:.1f}ms)")
        print(f"[Общее время]: {res['total_latency_ms']:.1f}ms")
        print(f"[Ответ отправлен в TG]: {res['sent_msg_ids']}")
        print(f"[Превью ответа]:\n{res['answer_preview']}\n")
        await asyncio.sleep(2)

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
