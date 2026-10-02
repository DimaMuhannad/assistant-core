"""Характеризация и DI секретаря: табель идёт через порт и корень композиции.

Первые два теста закоммичены до правки src (D-18): они фиксируют текст ответа
`_get_tydex_context` и работают одинаково с инлайн-импортом и с внедрением.
Тесты не читают учётные данные и боевую БД: AADHk подменяется фейком,
`db=MagicMock()`, `api_key=""`.
"""

import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.brain.secretary_dialog import SecretaryDialogEngine
from src.composition import default_timesheet_service
import src.composition
import src.notifier.bot_handler as bot_module
from src.core.domain.entities import ConnectorRole
from src.core.ports.connectors import BaseTimesheetProvider
from src.notifier.bot_handler import EmailBotHandler
from src.storage.db import Database

PACING = {
    "month": 3,
    "year": 2026,
    "delta_pacing": 1.25,
    "monthly_norm_hours": 170.0,
    "total_workdays": 20,
    "worked_hours": 42.5,
    "total_shifts": 6,
    "remaining_hours_to_norm": 127.5,
    "required_daily_pacing": 8.0,
    "remaining_workdays": 15,
}

EXPECTED_TEXT = (
    "⏱️ Табель ООО «Тидекс» (Март 2026):\n"
    "• Месячная норма: 170.0 ч (20 раб. дней по 8.5 ч)\n"
    "• Отработано фактически: 42.50 ч (6 смен/дней)\n"
    "• Текущий баланс нормы (ΔH): +1.25 ч\n"
    "• Осталось закрыть: 127.50 ч\n"
    "• Требуемый темп: 8.00 ч/день (осталось раб. дней: 15)"
)

FALLBACK_TEXT = "⏱️ Табель «Тидекс»: данные выработки временно обновляются."

TARGET = "src.connectors.aadhk.parser.AadhkIngestionService"


async def test_tydex_context_text_characterization():
    calls: list[dict] = []

    class FakeService:
        def __init__(self, db):
            self.db = db

        async def get_monthly_pacing(self, **kwargs):
            calls.append(kwargs)
            return dict(PACING)

    engine = SecretaryDialogEngine(db=MagicMock(), api_key="")
    with patch(TARGET, FakeService):
        text = await engine._get_tydex_context()

    assert text == EXPECTED_TEXT
    assert calls == [{"project_name": "Тидекс"}]


async def test_tydex_context_fallback_on_error():
    class BrokenService:
        def __init__(self, db):
            self.db = db

        async def get_monthly_pacing(self, **kwargs):
            raise RuntimeError("boom")

    engine = SecretaryDialogEngine(db=MagicMock(), api_key="")
    with patch(TARGET, BrokenService):
        text = await engine._get_tydex_context()

    assert text == FALLBACK_TEXT


async def test_secretary_uses_injected_timesheet_service():
    calls: list[dict] = []

    class ForbiddenDefault:
        def __init__(self, db):
            raise AssertionError("значение по умолчанию не должно создаваться")

    class FakeProvider:
        async def get_monthly_pacing(self, **kwargs):
            calls.append(kwargs)
            return dict(PACING)

    engine = SecretaryDialogEngine(db=MagicMock(), api_key="", timesheet_service=FakeProvider())
    with patch(TARGET, ForbiddenDefault):
        text = await engine._get_tydex_context()

    assert text == EXPECTED_TEXT
    assert calls == [{"project_name": "Тидекс"}]


async def test_default_timesheet_service_conforms_to_port():
    p = default_timesheet_service(MagicMock())

    assert isinstance(p, BaseTimesheetProvider)
    for name in (
        "health_check",
        "ingest_backup_file",
        "reconcile_all_conflicts",
        "get_timesheet_report",
        "get_monthly_pacing",
    ):
        assert inspect.iscoroutinefunction(getattr(p, name)), name
    assert p.connector_id == "aadhk_timesheet"
    assert p.role == ConnectorRole.TIMESHEET
    assert p.required_scopes == ("timesheet.read", "timesheet.write")
    assert await p.health_check() is True


# ---------------------------------------------------------------------------
# Характеризация трёх путей бота (D-18, Pitfall 6): /timesheet, синхронизация
# табеля с Google Drive, AADHk-ветка приёма документа. Закоммичено ДО правки
# bot_handler.py. Подменяются только модули-источники: после DI имён
# коннекторов в модуле бота не будет, а патч источника работает до и после.
# ---------------------------------------------------------------------------

DRIVE_TARGET = "src.connectors.gdrive.client.GoogleDriveClient"
OWNER_ID = 12345
STRANGER_ID = 999
UPLOAD_PATH = "/opt/chat-app/uploads/synthetic_backup.db"


@pytest.fixture
async def in_memory_db():
    db = Database(":memory:")
    await db.init_db()
    yield db
    await db.close()


def make_handler(db, bot=None):
    return EmailBotHandler(db=db, allowed_user_id=OWNER_ID, bot=bot or MagicMock())


def make_message(user_id=OWNER_ID):
    msg = MagicMock()
    msg.from_user.id = user_id
    msg.chat.id = user_id
    msg.chat.type = "private"
    msg.caption = ""
    msg.answer = AsyncMock()
    return msg


def make_callback(user_id=OWNER_ID):
    cb = MagicMock()
    cb.from_user.id = user_id
    cb.answer = AsyncMock()
    cb.message.answer = AsyncMock()
    return cb


def make_fake_aadhk(calls, pacing=None, ingest_result=None, ingest_exc=None):
    """Класс-фейк AADHk: каждый вызов пишет (имя, args, kwargs) в общий список."""

    class FakeAadhk:
        def __init__(self, db):
            self.db = db
            calls.append(("__init__", (db,), {}))

        async def reconcile_all_conflicts(self, *args, **kwargs):
            calls.append(("reconcile_all_conflicts", args, kwargs))

        async def get_monthly_pacing(self, *args, **kwargs):
            calls.append(("get_monthly_pacing", args, kwargs))
            return dict(pacing if pacing is not None else PACING)

        async def ingest_backup_file(self, *args, **kwargs):
            calls.append(("ingest_backup_file", args, kwargs))
            if ingest_exc is not None:
                raise ingest_exc
            return ingest_result

    return FakeAadhk


def method_calls(calls):
    """Вызовы без служебной записи о создании фейка."""
    return [c for c in calls if c[0] != "__init__"]


def make_fake_drive(instances, configured=True, sync_result=None):
    """Класс-фейк Drive: экземпляры складываются в список, db запоминается."""

    class FakeDrive:
        def __init__(self):
            self.synced_db = None
            instances.append(self)

        @property
        def is_configured(self):
            return configured

        async def sync_aadhk_from_drive(self, db):
            self.synced_db = db
            return sync_result

    return FakeDrive


def make_document_message(file_name="synthetic_backup.db", file_size=2048):
    msg = make_message()
    msg.document = MagicMock(file_id="f1", file_name=file_name, file_size=file_size)
    return msg


def make_document_bot():
    bot = MagicMock()
    bot.get_file = AsyncMock(return_value=MagicMock(file_path="remote/path"))
    bot.download_file = AsyncMock()
    return bot


async def test_cmd_timesheet_characterization(in_memory_db):
    """Известный дефект до Фазы 2: неопределённое имя в f-строке заголовка табеля.

    Команда /timesheet падает с NameError после расчёта, ещё до отправки ответа.
    Фаза 2 поведение не меняет. Решение владельца 2026-10-02: не чинить в
    Фазе 2; исправление выносится отдельной задачей в backlog, а этот тест
    при исправлении переписывают в той же задаче.
    """
    calls: list = []
    handler = make_handler(in_memory_db)
    msg = make_message()

    with patch(TARGET, make_fake_aadhk(calls)):
        with pytest.raises(NameError, match="cur_m_name"):
            await handler.handle_cmd_timesheet(msg)

    assert method_calls(calls) == [
        ("reconcile_all_conflicts", (), {}),
        ("get_monthly_pacing", (), {"project_name": "Тидекс"}),
    ]
    msg.answer.assert_not_called()


async def test_cmd_timesheet_unauthorized_does_nothing(in_memory_db):
    calls: list = []
    handler = make_handler(in_memory_db)
    msg = make_message(user_id=STRANGER_ID)

    with patch(TARGET, make_fake_aadhk(calls)):
        result = await handler.handle_cmd_timesheet(msg)

    assert result is None
    assert calls == []
    msg.answer.assert_not_called()


async def test_timesheet_sync_unauthorized(in_memory_db):
    aadhk_calls: list = []
    drives: list = []
    handler = make_handler(in_memory_db)
    cb = make_callback(user_id=STRANGER_ID)

    with patch(TARGET, make_fake_aadhk(aadhk_calls)), patch(DRIVE_TARGET, make_fake_drive(drives)):
        await handler.cb_timesheet_sync(cb)

    cb.answer.assert_called_once_with("Нет доступа.", show_alert=True)
    cb.message.answer.assert_not_called()
    assert drives == []
    assert aadhk_calls == []


async def test_timesheet_sync_drive_not_configured(in_memory_db):
    aadhk_calls: list = []
    drives: list = []
    handler = make_handler(in_memory_db)
    cb = make_callback()

    with patch(TARGET, make_fake_aadhk(aadhk_calls)), patch(
        DRIVE_TARGET, make_fake_drive(drives, configured=False)
    ):
        await handler.cb_timesheet_sync(cb)

    cb.answer.assert_called_once_with("Синхронизация с Google Drive...")
    cb.message.answer.assert_called_once_with("❌ Google Drive не настроен или отсутствует токен.")
    assert len(drives) == 1
    assert method_calls(aadhk_calls) == []


async def test_timesheet_sync_error_status(in_memory_db):
    aadhk_calls: list = []
    drives: list = []
    handler = make_handler(in_memory_db)
    cb = make_callback()
    sync_result = {"status": "error", "message": "нет файла"}

    with patch(TARGET, make_fake_aadhk(aadhk_calls)), patch(
        DRIVE_TARGET, make_fake_drive(drives, sync_result=sync_result)
    ):
        await handler.cb_timesheet_sync(cb)

    cb.message.answer.assert_called_once_with("⚠️ Ошибка синхронизации: нет файла")
    assert method_calls(aadhk_calls) == []


async def test_timesheet_sync_success_text(in_memory_db):
    aadhk_calls: list = []
    drives: list = []
    handler = make_handler(in_memory_db)
    cb = make_callback()
    sync_result = {
        "status": "success",
        "file_name": "synthetic.db",
        "ingestion_result": {"new_inserted_count": 2},
    }
    summary_mock = AsyncMock(
        return_value={"total_hours": 10.0, "clean_hours": 9.5, "total_amount": 12345.0}
    )
    conflicts_mock = AsyncMock(
        return_value=[{"start_time": "2026-03-02T10:00:00", "conflict_details": "пара 2"}]
    )

    with patch(TARGET, make_fake_aadhk(aadhk_calls)), patch(
        DRIVE_TARGET, make_fake_drive(drives, sync_result=sync_result)
    ), patch.object(in_memory_db, "get_timesheet_summary", summary_mock), patch.object(
        in_memory_db, "get_timesheet_conflicts", conflicts_mock
    ):
        await handler.cb_timesheet_sync(cb)

    expected = (
        "🔄 **Синхронизация с Google Drive завершена!**\n"
        "\n"
        "• Файл: `synthetic.db`\n"
        "• Новых смен добавлено: `2`\n"
        "• Всего отработано: `10.00` ч\n"
        "• Чистые часы: `9.50` ч\n"
        "• Начислено: `12,345.00` ₽\n"
        "\n"
        "⚠️ **Наложения на пары ГУАП (1):**\n"
        "• `2026-03-02 10:00`: пара 2"
    )
    cb.message.answer.assert_called_once_with(expected)
    assert method_calls(aadhk_calls) == [("reconcile_all_conflicts", (), {})]
    summary_mock.assert_called_once_with(project_name="Тидекс")
    conflicts_mock.assert_called_once_with(limit=5)
    assert len(drives) == 1
    assert drives[0].synced_db is in_memory_db


async def test_timesheet_sync_fresh_drive_client_per_callback(in_memory_db):
    drives: list = []
    handler = make_handler(in_memory_db)

    with patch(DRIVE_TARGET, make_fake_drive(drives, configured=False)):
        await handler.cb_timesheet_sync(make_callback())
        await handler.cb_timesheet_sync(make_callback())

    assert len(drives) == 2
    assert drives[0] is not drives[1]


async def test_document_aadhk_branch_text(in_memory_db):
    calls: list = []
    bot = make_document_bot()
    handler = make_handler(in_memory_db, bot=bot)
    msg = make_document_message()
    ingest_result = {
        "parsed_count": 3,
        "new_inserted_count": 2,
        "total_hours": 12.5,
        "by_task": {"Синтетика": 12.5},
        "conflicts_count": 1,
    }

    with patch(TARGET, make_fake_aadhk(calls, ingest_result=ingest_result)):
        await handler.handle_user_document(msg)

    expected = (
        "📄 **Файл сохранен:** `synthetic_backup.db` (2.0 KB)\n"
        "\n"
        "⏱️ **Учет времени AADHk («Тидекс») успешно импортирован:**\n"
        "• Распознано смен: **3** (новых: 2)\n"
        "• Суммарное время: **12.5 ч.**\n"
        "• **По задачам:**\n"
        "  — Синтетика: 12.5 ч.\n"
        "\n"
        "⚠️ **Обнаружены коллизии с расписанием ГУАП:** 1 шт."
    )
    msg.answer.assert_called_once_with(expected)
    assert method_calls(calls) == [("ingest_backup_file", (UPLOAD_PATH,), {})]
    bot.download_file.assert_called_once_with("remote/path", destination=UPLOAD_PATH)
    assert not Path(UPLOAD_PATH).exists()


async def test_document_aadhk_branch_swallows_errors(in_memory_db):
    calls: list = []
    bot = make_document_bot()
    handler = make_handler(in_memory_db, bot=bot)
    msg = make_document_message()

    with patch(TARGET, make_fake_aadhk(calls, ingest_exc=RuntimeError("boom"))):
        await handler.handle_user_document(msg)

    msg.answer.assert_called_once_with("📄 **Файл сохранен:** `synthetic_backup.db` (2.0 KB)")
    assert method_calls(calls) == [("ingest_backup_file", (UPLOAD_PATH,), {})]
    assert not Path(UPLOAD_PATH).exists()


# ---------------------------------------------------------------------------
# DI бота: зависимости приходят через конструктор, значения по умолчанию
# собирает src.composition (D-11, D-12, D-13).
# ---------------------------------------------------------------------------


class ForbiddenDefault:
    """Подмена конкретного класса: любое создание значения по умолчанию - ошибка."""

    def __init__(self, *args, **kwargs):
        raise AssertionError("значение по умолчанию не должно создаваться")


class RecordingTimesheetProvider:
    def __init__(self, calls, ingest_result=None):
        self.calls = calls
        self.ingest_result = ingest_result

    async def ingest_backup_file(self, *args, **kwargs):
        self.calls.append(("ingest_backup_file", args, kwargs))
        return self.ingest_result

    async def reconcile_all_conflicts(self, *args, **kwargs):
        self.calls.append(("reconcile_all_conflicts", args, kwargs))


async def test_bot_uses_injected_timesheet_service(in_memory_db):
    calls: list = []
    drives: list = []
    ingest_result = {
        "parsed_count": 3,
        "new_inserted_count": 2,
        "total_hours": 12.5,
        "by_task": {"Синтетика": 12.5},
        "conflicts_count": 1,
    }
    provider = RecordingTimesheetProvider(calls, ingest_result=ingest_result)
    sync_result = {
        "status": "success",
        "file_name": "synthetic.db",
        "ingestion_result": {"new_inserted_count": 2},
    }
    bot = make_document_bot()
    handler = EmailBotHandler(
        db=in_memory_db,
        allowed_user_id=OWNER_ID,
        bot=bot,
        timesheet_service=provider,
        drive_client_factory=make_fake_drive(drives, sync_result=sync_result),
    )
    msg = make_document_message()
    cb = make_callback()
    summary_mock = AsyncMock(
        return_value={"total_hours": 10.0, "clean_hours": 9.5, "total_amount": 12345.0}
    )
    conflicts_mock = AsyncMock(
        return_value=[{"start_time": "2026-03-02T10:00:00", "conflict_details": "пара 2"}]
    )

    with patch(TARGET, ForbiddenDefault), patch(DRIVE_TARGET, ForbiddenDefault), patch.object(
        in_memory_db, "get_timesheet_summary", summary_mock
    ), patch.object(in_memory_db, "get_timesheet_conflicts", conflicts_mock):
        await handler.handle_user_document(msg)
        await handler.cb_timesheet_sync(cb)

    msg.answer.assert_called_once_with(
        "📄 **Файл сохранен:** `synthetic_backup.db` (2.0 KB)\n"
        "\n"
        "⏱️ **Учет времени AADHk («Тидекс») успешно импортирован:**\n"
        "• Распознано смен: **3** (новых: 2)\n"
        "• Суммарное время: **12.5 ч.**\n"
        "• **По задачам:**\n"
        "  — Синтетика: 12.5 ч.\n"
        "\n"
        "⚠️ **Обнаружены коллизии с расписанием ГУАП:** 1 шт."
    )
    cb.message.answer.assert_called_once_with(
        "🔄 **Синхронизация с Google Drive завершена!**\n"
        "\n"
        "• Файл: `synthetic.db`\n"
        "• Новых смен добавлено: `2`\n"
        "• Всего отработано: `10.00` ч\n"
        "• Чистые часы: `9.50` ч\n"
        "• Начислено: `12,345.00` ₽\n"
        "\n"
        "⚠️ **Наложения на пары ГУАП (1):**\n"
        "• `2026-03-02 10:00`: пара 2"
    )
    assert calls == [
        ("ingest_backup_file", (UPLOAD_PATH,), {}),
        ("reconcile_all_conflicts", (), {}),
    ]
    assert drives[0].synced_db is in_memory_db


async def test_bot_uses_injected_drive_client_factory(in_memory_db):
    factory_calls: list = []
    drives: list = []
    fake_cls = make_fake_drive(drives, configured=False)

    def factory():
        factory_calls.append(1)
        return fake_cls()

    handler = EmailBotHandler(
        db=in_memory_db,
        allowed_user_id=OWNER_ID,
        bot=MagicMock(),
        drive_client_factory=factory,
    )
    cb1, cb2 = make_callback(), make_callback()

    with patch(DRIVE_TARGET, ForbiddenDefault):
        await handler.cb_timesheet_sync(cb1)
        await handler.cb_timesheet_sync(cb2)

    cb1.message.answer.assert_called_once_with("❌ Google Drive не настроен или отсутствует токен.")
    cb2.message.answer.assert_called_once_with("❌ Google Drive не настроен или отсутствует токен.")
    assert len(factory_calls) == 2
    assert len(drives) == 2


async def test_bot_defaults_come_from_composition(in_memory_db):
    h = EmailBotHandler(db=in_memory_db, allowed_user_id=123)

    assert type(h.lms_client).__name__ == "GuapLmsClient"
    assert type(h.email_sender).__name__ == "EmailSender"
    assert h.drive_client_factory is src.composition.default_drive_client
    assert h.timesheet_service is None


async def test_bot_passes_timesheet_service_to_secretary(in_memory_db):
    fake = RecordingTimesheetProvider([])
    h = EmailBotHandler(
        db=in_memory_db, allowed_user_id=OWNER_ID, bot=MagicMock(), timesheet_service=fake
    )

    assert h.dialog_engine.timesheet_service is fake


def test_bot_handler_has_no_concrete_connector_names():
    for name in ("GuapLmsClient", "EmailSender", "AadhkIngestionService", "GoogleDriveClient"):
        assert not hasattr(bot_module, name), name
