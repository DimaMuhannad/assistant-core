import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from aiogram.types import Message, Chat, User
from src.notifier.telegram import TelegramNotifier
from src.notifier.bot_handler import EmailBotHandler


@pytest.mark.asyncio
async def test_telegram_notifier_blocks_group_dispatch_without_allow_group():
    """Verify that TelegramNotifier drops messages to negative chat IDs unless allow_group=True."""
    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    notifier = TelegramNotifier(bot_token="test_token", user_id=922302501, bot=mock_bot)

    # 1. Negative chat ID without allow_group -> MUST be blocked
    sent_ids = await notifier.send_message(
        text_markdown="Test message into group",
        chat_id=-1003920021945,
        allow_group=False,
    )
    assert sent_ids == []
    mock_bot.send_message.assert_not_called()

    # 2. String negative chat ID without allow_group -> MUST be blocked
    sent_ids_str = await notifier.send_message(
        text_markdown="Test message into group",
        chat_id="-1003920021945",
        allow_group=False,
    )
    assert sent_ids_str == []
    mock_bot.send_message.assert_not_called()

    # 3. Explicit sanction allow_group=True -> permitted
    fake_sent = MagicMock()
    fake_sent.message_id = 42
    mock_bot.send_message.return_value = fake_sent

    sent_ids_allowed = await notifier.send_message(
        text_markdown="Sanctioned post to group",
        chat_id=-1003920021945,
        allow_group=True,
    )
    assert sent_ids_allowed == [42]
    mock_bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_bot_handler_filters_out_group_messages():
    """Verify that BotHandler router-level filters completely drop group messages."""
    mock_db = MagicMock()
    mock_notifier = MagicMock()
    mock_bot = MagicMock()

    handler = EmailBotHandler(
        bot=mock_bot,
        db=mock_db,
        notifier=mock_notifier,
        allowed_user_id=922302501,
    )

    # Simulate message from Dmitry inside a student group (supergroup)
    group_chat = Chat(id=-1003920021945, type="supergroup", title="м631к Основы проектной деятельности")
    dmitry_user = User(id=922302501, is_bot=False, first_name="Dmitry")
    group_msg = Message(
        message_id=101,
        date=datetime.now(),
        chat=group_chat,
        from_user=dmitry_user,
        text="Готова ваша комната создана.",
    )

    # Mock intent router and dialog engine
    handler.intent_router.route = AsyncMock()
    handler.dialog_engine.answer_user_message = AsyncMock()

    # Propagate event through the router with bot
    await handler.router.propagate_event("message", group_msg, bot=mock_bot)

    # Assert neither intent router nor dialog engine were ever invoked
    handler.intent_router.route.assert_not_called()
    handler.dialog_engine.answer_user_message.assert_not_called()
    mock_notifier.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_bot_handler_processes_private_messages():
    """Verify that BotHandler correctly processes private messages from authorized user."""
    mock_db = MagicMock()
    mock_notifier = MagicMock()
    mock_notifier.send_message = AsyncMock(return_value=[1])
    mock_bot = MagicMock()
    mock_bot.send_chat_action = AsyncMock()

    handler = EmailBotHandler(
        bot=mock_bot,
        db=mock_db,
        notifier=mock_notifier,
        allowed_user_id=922302501,
    )

    private_chat = Chat(id=922302501, type="private", first_name="Dmitry")
    dmitry_user = User(id=922302501, is_bot=False, first_name="Dmitry")
    priv_msg = Message(
        message_id=102,
        date=datetime.now(),
        chat=private_chat,
        from_user=dmitry_user,
        text="Привет, как дела?",
    )

    mock_route = MagicMock()
    mock_route.action = "secretary"
    mock_route.confidence = 0.95
    mock_route.model = "test"
    mock_route.latency_ms = 100.0

    handler.intent_router.route = AsyncMock(return_value=mock_route)
    handler.dialog_engine.answer_user_message = AsyncMock(return_value=("Ответ секретаря", []))

    await handler.router.propagate_event("message", priv_msg, bot=mock_bot)

    handler.intent_router.route.assert_called_once()
    handler.dialog_engine.answer_user_message.assert_called_once()
    mock_notifier.send_message.assert_called_once_with("Ответ секретаря", chat_id=922302501)
