"""Доменные исключения ядра платформы."""


class AirGapViolationError(RuntimeError):
    """Попытка передачи или автогенерации данных, нарушающих политику Air-Gap."""

    pass
