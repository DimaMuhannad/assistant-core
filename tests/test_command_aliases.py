import pytest
from unittest.mock import AsyncMock, MagicMock
from src.storage.db import Database
from src.notifier.commands import CommandRegistry
from src.brain.intent_router import FastIntentRouter

# GATE-01: порог латентности проверяется по минимуму из N замеров, чтобы одиночный пик нагрузки на VPS не краснил гейт.
LATENCY_SAMPLES = 5


@pytest.mark.asyncio
async def test_fast_intent_router_aliases(tmp_path):
    """Test FastIntentRouter resolves default catalog aliases quickly (best of LATENCY_SAMPLES < 50 ms)."""
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.init_db()
    try:
        registry = CommandRegistry(db=db)
        router = FastIntentRouter(db=db, command_registry=registry)

        test_cases = [
            ("пары", "today"),
            ("табель", "timesheet"),
            ("почта", "emails"),
            ("статус", "ticker"),
            ("вечер", "evening"),
        ]

        for text, expected_action in test_cases:
            # Прогрев без замера: первый вызов платит за холодный старт (поток aiosqlite, кэш).
            warm = await router.route(user_id=1001, message_text=text)
            assert warm.action == expected_action
            latencies = []
            for _ in range(LATENCY_SAMPLES):
                res = await router.route(user_id=1001, message_text=text)
                assert res.action == expected_action
                assert res.model == "fast-rule"
                assert res.confidence == 1.0
                latencies.append(res.latency_ms)
            assert min(latencies) < 50.0, f"{text!r} alias latency too high: {min(latencies):.2f} ms"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_hide_and_show_command(tmp_path):
    """Test hiding and restoring commands from Telegram Bot menu."""
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.init_db()
    try:
        registry = CommandRegistry(db=db)

        # Initially LMS is active
        cmds = await registry.get_telegram_commands()
        assert "lms" in [c.command for c in cmds]

        # Hide LMS
        await db.set_command_setting("lms", is_enabled=False)
        cmds_hidden = await registry.get_telegram_commands()
        assert "lms" not in [c.command for c in cmds_hidden]

        # Restore LMS
        await db.set_command_setting("lms", is_enabled=True)
        cmds_restored = await registry.get_telegram_commands()
        assert "lms" in [c.command for c in cmds_restored]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_custom_alias_registration_and_routing(tmp_path):
    """Test custom aliases resolution via FastIntentRouter."""
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.init_db()
    try:
        registry = CommandRegistry(db=db)
        router = FastIntentRouter(db=db, command_registry=registry)

        # Register custom alias: "лабы" -> "lms"
        await db.set_custom_alias("лабы", "lms")
        res = await router.route(user_id=1001, message_text="лабы")
        assert res.action == "lms"
        assert res.model == "fast-rule"
        assert res.confidence == 1.0

        # Remove custom alias
        removed = await db.remove_custom_alias("лабы")
        assert removed is True
        resolved = await registry.resolve_command_or_alias("лабы")
        assert resolved is None
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_menu_command_rendering(tmp_path):
    """Меню: lms есть в каталоге, отключение убирает его из меню, пользовательский алиас разрешается (WR-11)."""
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.init_db()
    try:
        registry = CommandRegistry(db=db)

        catalog = registry._build_default_catalog(registry.persona_getter())
        assert any(c.name == "lms" for c in catalog)

        # До отключения lms входит и в список активных команд, и в меню бота
        active_before = {c.name for c in await registry.get_active_commands()}
        menu_before = {c.command for c in await registry.get_telegram_commands()}
        assert "lms" in active_before
        assert "lms" in menu_before

        # После отключения lms исчезает из обоих представлений меню
        await db.set_command_setting("lms", is_enabled=False)
        active_after = {c.name for c in await registry.get_active_commands()}
        menu_after = {c.command for c in await registry.get_telegram_commands()}
        assert "lms" not in active_after
        assert "lms" not in menu_after

        # Пользовательский алиас разрешается в каноническую команду
        await db.set_custom_alias("карточки", "timesheet")
        assert await registry.resolve_command_or_alias("карточки") == "timesheet"
    finally:
        await db.close()


# =========================================================================
# Phase 9 Plan 09-04: UX Ergonomics Audit, Edge Caching, and Telemetry (UXQ-04)
# =========================================================================

def _make_mock_message(user_id: int = 12345, chat_id: int = 12345, text: str = "/today") -> MagicMock:
    from aiogram.types import Message, User, Chat
    msg = MagicMock(spec=Message)
    msg.message_id = 999
    msg.text = text
    user = MagicMock(spec=User)
    user.id = user_id
    msg.from_user = user
    chat = MagicMock(spec=Chat)
    chat.id = chat_id
    msg.chat = chat
    msg.answer = AsyncMock()
    bot = MagicMock()
    bot.edit_message_reply_markup = AsyncMock()
    msg.bot = bot
    return msg


def _make_mock_callback(
    user_id: int = 12345,
    chat_id: int = 12345,
    message_id: int = 888,
    data: str = "fb:up:888",
) -> MagicMock:
    from aiogram.types import CallbackQuery, User, Chat, Message
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    user = MagicMock(spec=User)
    user.id = user_id
    cb.from_user = user
    msg = MagicMock(spec=Message)
    msg.message_id = message_id
    chat = MagicMock(spec=Chat)
    chat.id = chat_id
    msg.chat = chat
    msg.edit_reply_markup = AsyncMock()
    cb.message = msg
    cb.answer = AsyncMock()
    return cb


@pytest.mark.asyncio
async def test_edge_caching_latency_sub_250ms(tmp_path):
    """Test that repeated /today and /timesheet requests are served from edge cache in < 250 ms (UXQ-04)."""
    import time
    from src.notifier.bot_handler import EmailBotHandler

    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.init_db()
    try:
        user_id = 12345
        mock_notifier = MagicMock()
        mock_notifier.is_configured = True
        mock_notifier.send_message = AsyncMock(return_value=[1001])

        handler = EmailBotHandler(
            db=db,
            allowed_user_id=user_id,
            notifier=mock_notifier,
        )

        # 1. Warm up /today
        today_msg = _make_mock_message(user_id=user_id, text="/today")
        await handler.handle_cmd_today(today_msg)

        # Cached calls must be served with sub-250ms latency (actually < 50ms); best of LATENCY_SAMPLES
        today_samples_ms = []
        for _ in range(LATENCY_SAMPLES):
            t0 = time.perf_counter()
            await handler.handle_cmd_today(today_msg)
            today_samples_ms.append((time.perf_counter() - t0) * 1000)
        elapsed_today_ms = min(today_samples_ms)

        assert elapsed_today_ms < 250.0, f"/today cached latency too high: {elapsed_today_ms:.2f} ms"

        # 2. Warm up /timesheet
        ts_msg = _make_mock_message(user_id=user_id, text="/timesheet")
        mock_ts_service = MagicMock()
        mock_ts_service.reconcile_all_conflicts = AsyncMock()
        mock_ts_service.get_monthly_pacing = AsyncMock(
            return_value={
                "month": 10,
                "year": 2026,
                "morning_delta": 2.5,
                "expected_hours_to_date": 40.0,
                "elapsed_workdays": 5,
                "total_amount": 50000.0,
                "monthly_norm_hours": 160.0,
                "total_workdays": 20,
                "worked_hours": 42.5,
                "total_shifts": 6,
                "remaining_workdays": 15,
                "remaining_hours_to_norm": 117.5,
                "required_daily_pacing": 7.83,
            }
        )
        handler.timesheet_service = mock_ts_service

        await handler.handle_cmd_timesheet(ts_msg)

        # Repeated calls to /timesheet must be served from cache; best of LATENCY_SAMPLES
        ts_samples_ms = []
        for _ in range(LATENCY_SAMPLES):
            t1 = time.perf_counter()
            await handler.handle_cmd_timesheet(ts_msg)
            ts_samples_ms.append((time.perf_counter() - t1) * 1000)
        elapsed_ts_ms = min(ts_samples_ms)

        assert elapsed_ts_ms < 250.0, f"/timesheet cached latency too high: {elapsed_ts_ms:.2f} ms"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_clear_edge_cache_invalidation(tmp_path):
    """Test invalidation of edge cache by prefix and completely (UXQ-04)."""
    import time
    from src.notifier.bot_handler import EmailBotHandler

    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.init_db()
    try:
        handler = EmailBotHandler(
            db=db,
            allowed_user_id=12345,
        )

        handler._edge_cache["today:2026-10-07"] = (time.time() + 900, "Today schedule text")
        handler._edge_cache["timesheet:2026-10-07"] = (time.time() + 1800, "Timesheet text")

        # Invalidate timesheet only
        handler.clear_edge_cache("timesheet")
        assert "timesheet:2026-10-07" not in handler._edge_cache
        assert "today:2026-10-07" in handler._edge_cache

        # Invalidate all
        handler.clear_edge_cache()
        assert len(handler._edge_cache) == 0
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_dialog_feedback_db_logging(tmp_path):
    """Test storing dialog feedback telemetry into dialog_feedback_log in SQLite (UXQ-04)."""
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.init_db()
    try:
        await db.log_dialog_feedback(message_id=777, user_id=12345, feedback_type="up")
        await db.log_dialog_feedback(message_id=778, user_id=12345, feedback_type="down")

        feedbacks = await db.get_dialog_feedback(message_id=777)
        assert len(feedbacks) == 1
        assert feedbacks[0]["message_id"] == 777
        assert feedbacks[0]["user_id"] == 12345
        assert feedbacks[0]["feedback_type"] == "up"

        feedbacks_down = await db.get_dialog_feedback(message_id=778)
        assert len(feedbacks_down) == 1
        assert feedbacks_down[0]["feedback_type"] == "down"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_build_dialog_feedback_keyboard_and_callbacks(tmp_path):
    """Test generating feedback keyboard and handling fb:up / fb:down callbacks with deduplication."""
    from src.notifier.telegram import build_dialog_feedback_keyboard
    from src.notifier.bot_handler import EmailBotHandler

    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.init_db()
    try:
        # 1. Keyboard structure
        kb = build_dialog_feedback_keyboard(msg_id=505)
        assert len(kb.inline_keyboard) == 1
        buttons = kb.inline_keyboard[0]
        assert len(buttons) == 2
        assert "👍" in buttons[0].text
        assert buttons[0].callback_data == "fb:up:505"
        assert "👎" in buttons[1].text
        assert buttons[1].callback_data == "fb:down:505"

        # 2. Callback handling
        handler = EmailBotHandler(
            db=db,
            allowed_user_id=12345,
        )

        cb_up = _make_mock_callback(user_id=12345, message_id=505, data="fb:up:505")
        await handler.cb_dialog_feedback(cb_up)

        # Toast answer called
        cb_up.answer.assert_called_with("Спасибо за обратную связь!")
        # Message markup updated to thank you note
        cb_up.message.edit_reply_markup.assert_called_once()
        called_kb = cb_up.message.edit_reply_markup.call_args.kwargs["reply_markup"]
        assert "Спасибо за отзыв! 👍" in called_kb.inline_keyboard[0][0].text

        # Verify DB record
        logs = await db.get_dialog_feedback(505)
        assert len(logs) == 1
        assert logs[0]["feedback_type"] == "up"

        # 3. Deduplication: second click by the same user on the same message
        cb_up_repeat = _make_mock_callback(user_id=12345, message_id=505, data="fb:up:505")
        await handler.cb_dialog_feedback(cb_up_repeat)
        cb_up_repeat.answer.assert_called_with("Вы уже оставили отзыв на этот ответ.")
        # No second row inserted into DB
        logs_after = await db.get_dialog_feedback(505)
        assert len(logs_after) == 1
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_connector_health_alert_and_check(tmp_path):
    """Test proactive connector diagnostic alerts and health check callback."""
    from src.notifier.bot_handler import EmailBotHandler

    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.init_db()
    try:
        user_id = 12345
        mock_notifier = MagicMock()
        mock_notifier.is_configured = True
        mock_notifier.send_message = AsyncMock(return_value=[1200])

        handler = EmailBotHandler(
            db=db,
            allowed_user_id=user_id,
            notifier=mock_notifier,
        )

        await handler.send_connector_health_alert(
            chat_id=user_id,
            service_name="ГУАП LMS",
            issue_text="Сессионный токен устарел или служба недоступна",
        )

        mock_notifier.send_message.assert_called_once()
        call_args, call_kwargs = mock_notifier.send_message.call_args
        sent_text = call_args[0]
        sent_kb = call_kwargs["reply_markup"]

        assert "⚠️ **Служба ГУАП LMS временно недоступна**" in sent_text
        assert "Сессионный токен устарел" in sent_text
        assert sent_kb.inline_keyboard[0][0].callback_data == "chk:ГУАП LMS"
        assert "🔄 Проверить подключение" in sent_kb.inline_keyboard[0][0].text

        # Test callback for check
        cb = _make_mock_callback(user_id=user_id, data="chk:ГУАП LMS")
        await handler.cb_connector_health_check(cb)
        cb.answer.assert_called_with("Проверка связи со службой ГУАП LMS...")
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_secretary_dialog_feedback_attachment(tmp_path):
    """Test that secretary dialog attaches feedback keyboard to model responses."""
    from src.notifier.bot_handler import EmailBotHandler

    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.init_db()
    try:
        user_id = 12345
        mock_bot = MagicMock()
        sent_msg = MagicMock()
        sent_msg.message_id = 6789
        mock_bot.send_message = AsyncMock(return_value=sent_msg)
        mock_bot.edit_message_reply_markup = AsyncMock()

        handler = EmailBotHandler(
            db=db,
            allowed_user_id=user_id,
            bot=mock_bot,
        )

        handler.dialog_engine.answer_user_message = AsyncMock(
            return_value=("Завтра у вас две пары на Гастелло.", [], None)
        )

        user_msg = _make_mock_message(user_id=user_id, text="Сколько пар завтра?")
        await handler._handle_secretary_dialog(user_msg, "Сколько пар завтра?")

        # Verify message was sent and feedback keyboard was attached
        mock_bot.send_message.assert_called_once()
        mock_bot.edit_message_reply_markup.assert_called_once()
        edit_kwargs = mock_bot.edit_message_reply_markup.call_args.kwargs
        assert edit_kwargs["message_id"] == 6789
        assert edit_kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "fb:up:6789"
        assert edit_kwargs["reply_markup"].inline_keyboard[0][1].callback_data == "fb:down:6789"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_ticker_refresh_loading_screen_and_restore(tmp_path):
    """Test that cb_ticker_refresh shows interim loading screen and restores active screen."""
    from src.notifier.bot_handler import EmailBotHandler
    from src.notifier.live_ticker import build_ticker_keyboard

    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.init_db()
    try:
        user_id = 12345
        chat_id = 12345
        msg_id = 999

        # Set live ticker with 'system' screen
        await db.set_live_ticker(chat_id=chat_id, message_id=msg_id, current_screen="system")

        mock_notifier = MagicMock()
        mock_notifier.edit_rich_message = AsyncMock(return_value=True)

        handler = EmailBotHandler(
            db=db,
            allowed_user_id=user_id,
            notifier=mock_notifier,
        )
        handler._refresh_pause_seconds = 0.01

        handler.ticker_service.build_ticker_message = AsyncMock(
            return_value=("⚡ Свежее табло | ⏱️ Норма OK", build_ticker_keyboard("system"))
        )

        cb_refresh = _make_mock_callback(user_id=user_id, message_id=msg_id, data="tk:refresh")
        await handler.cb_ticker_refresh(cb_refresh)

        # 1. Check callback answered immediately
        cb_refresh.answer.assert_called_once()

        # 2. Check edit_rich_message was called for progress steps and final restore:
        assert mock_notifier.edit_rich_message.call_count >= 5
        first_call = mock_notifier.edit_rich_message.call_args_list[0]
        assert "СБОР ДАННЫХ И ОБНОВЛЕНИЕ ТАБЛО" in first_call.kwargs["text_markdown"]
        # Button should be noop
        assert first_call.kwargs["reply_markup"].inline_keyboard[2][0].callback_data == "noop"

        last_call = mock_notifier.edit_rich_message.call_args_list[-1]
        assert "Свежее табло" in last_call.kwargs["text_markdown"]
        # Screen preserved as 'system'
        assert "• 🛡️ Статус •" in last_call.kwargs["reply_markup"].inline_keyboard[1][1].text

        # 3. Test cb_noop
        cb_noop = _make_mock_callback(user_id=user_id, message_id=msg_id, data="noop")
        await handler.cb_noop(cb_noop)
        cb_noop.answer.assert_called_once()
        assert "уже выполняется" in cb_noop.answer.call_args[0][0]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_prefix_vs_free_text_routing(tmp_path):
    """Test strict separation of slash prefixes vs free-text semantic routing (Issue #46).

    - '/лабы' or 'лабы' (single-word) triggers fast-path 'lms'.
    - '/лабы 1' (slash prefix with args) triggers fast-path 'lms'.
    - 'лабы проверить запиши в календарь на завтра' (multi-word, no leading slash)
      is NOT hijacked to 'lms', but correctly routes to 'calendar_schedule'.
    - '/напомни ...' and '/календарь ...' trigger deterministic fast-path.
    """
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.init_db()
    try:
        registry = CommandRegistry(db=db)
        router = FastIntentRouter(db=db, command_registry=registry)

        await db.set_custom_alias("лабы", "lms")

        # 1. Exact single-word alias
        res1 = await router.route(user_id=1, message_text="лабы")
        assert res1.action == "lms"
        assert res1.model == "fast-rule"

        # 2. Leading slash alias
        res2 = await router.route(user_id=1, message_text="/лабы")
        assert res2.action == "lms"
        assert res2.model == "fast-rule"

        # 3. Leading slash with arguments
        res3 = await router.route(user_id=1, message_text="/лабы отчеты")
        assert res3.action == "lms"
        assert res3.model == "fast-rule"

        # 4. Multi-word sentence without slash must NOT be hijacked to lms!
        # It must resolve via calendar intent or full semantic parsing.
        res4 = await router.route(user_id=1, message_text="лабы проверить запиши в календарь на завтра")
        assert res4.action == "calendar_schedule"
        assert res4.action != "lms"

        # 5. Direct prefix for reminders
        res5 = await router.route(user_id=1, message_text="/напомни проверить отчеты студентов")
        assert res5.action == "create_reminder"
        assert res5.model == "fast-rule"

        # 6. Direct prefix for calendar
        res6 = await router.route(user_id=1, message_text="/календарь консультация в 15:00")
        assert res6.action == "calendar_schedule"
        assert res6.model == "fast-rule"
    finally:
        await db.close()


