"""Характеризация и DI секретаря: табель идёт через порт и корень композиции.

Первые два теста закоммичены до правки src (D-18): они фиксируют текст ответа
`_get_tydex_context` и работают одинаково с инлайн-импортом и с внедрением.
Тесты не читают учётные данные и боевую БД: AADHk подменяется фейком,
`db=MagicMock()`, `api_key=""`.
"""

from unittest.mock import MagicMock, patch

from src.brain.secretary_dialog import SecretaryDialogEngine

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
