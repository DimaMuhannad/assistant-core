"""Характеризация и DI секретаря: табель идёт через порт и корень композиции.

Первые два теста закоммичены до правки src (D-18): они фиксируют текст ответа
`_get_tydex_context` и работают одинаково с инлайн-импортом и с внедрением.
Тесты не читают учётные данные и боевую БД: AADHk подменяется фейком,
`db=MagicMock()`, `api_key=""`.
"""

import inspect
from unittest.mock import MagicMock, patch

from src.brain.secretary_dialog import SecretaryDialogEngine
from src.composition import default_timesheet_service
from src.core.domain.entities import ConnectorRole
from src.core.ports.connectors import BaseTimesheetProvider

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
