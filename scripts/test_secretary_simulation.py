"""Test Harness for simulating Dmitry Popov's interactions with Secretary Bot.

Runs controlled stages, measures latency, records agent traces,
and sends system responses directly to Dmitry's Telegram chat (@opd_guap_popov_bot).
"""

import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src import config
from src.storage.db import Database
from src.brain.intent_router import FastIntentRouter
from src.brain.secretary_dialog import SecretaryDialogEngine
from src.notifier.telegram import TelegramNotifier
from src.connectors.aadhk.parser import AadhkIngestionService
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("simulation")


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
        pacing = await service.get_monthly_pacing(project_name="Тидекс")

        month_names = ["", "январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
        cur_m_name = month_names[pacing["month"]].capitalize()
        delta_sign = "+" if pacing["delta_pacing"] >= 0 else ""

        text_lines = [
            f"⏱️ **Табель и баланс: ООО «Тидекс» ({cur_m_name} {pacing['year']})**\n",
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
        """Simulate an incoming user query from Dmitry."""
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
        elif route_res.action == "methodist":
            # Delegate to methodist service
            from src.brain.methodist import MethodistService
            methodist = MethodistService(self.db, model=self.model)
            clean_q = query_text.replace("@методист", "").strip()
            answer_text = await methodist.answer_academic_question(clean_q)
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
    db = Database(config.SQLITE_DB_PATH)
    await db.init_db()
    runner = SecretarySimulationRunner(db)

    print("🚀 Запуск Этапа 1 симуляции: Тестирование маршрутизатора и ответов секретаря")
    scenarios = [
        "Покажи табель тидекс",
        "Какие у меня сегодня пары в ГУАП и во сколько?",
        "Сколько часов мне осталось до закрытия месячной нормы в Тидекс?",
    ]

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
