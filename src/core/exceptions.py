"""Доменные исключения ядра платформы."""


class AirGapViolationError(RuntimeError):
    """Попытка передачи или автогенерации данных, нарушающих политику Air-Gap."""

    pass


class MissingScopeError(PermissionError):
    """Попытка инициализации или вызова коннектора без необходимых разрешений."""

    pass

