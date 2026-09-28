import re
from datetime import date, datetime, timedelta, timezone
from typing import NamedTuple


class TemporalInfo(NamedTuple):
    is_expired: bool
    status: str
    target_event_date: date | None
    deadline_date: date | None
    days_ago: int
    days_remaining: int | None
    freshness_label: str  # "TODAY", "YESTERDAY", "RECENT", "ACTIVE_FUTURE", "EXPIRED", "STALE"


class TemporalClassifier:
    """Extracts and evaluates temporal information from chat messages relative to reference date."""

    DEADLINE_REGEX = re.compile(
        r"(?:к|до|дедлайн|сдать\s+до|срок\s+до|срок\s+сдачи)\s*(\d{1,2})[\.\/](\d{1,2})(?:[\.\/](\d{2,4}))?",
        re.IGNORECASE,
    )
    PARENTHESES_DATE_REGEX = re.compile(r"\((\d{1,2})[\.\/](\d{1,2})\)")
    
    RELATIVE_TERMS = [
        (re.compile(r"\bсегодня\b", re.IGNORECASE), 0),
        (re.compile(r"\bзавтра\b", re.IGNORECASE), 1),
        (re.compile(r"\bпослезавтра\b", re.IGNORECASE), 2),
        (re.compile(r"\bвчера\b", re.IGNORECASE), -1),
    ]

    @classmethod
    def analyze(
        cls,
        text: str,
        message_date: datetime,
        reference_date: date | None = None,
    ) -> TemporalInfo:
        if reference_date is None:
            reference_date = datetime.now(timezone.utc).date()

        msg_d = message_date.date() if isinstance(message_date, datetime) else message_date
        days_ago = (reference_date - msg_d).days

        # 1. Check relative words (сегодня, завтра, etc.)
        target_event_date: date | None = None
        for pattern, offset in cls.RELATIVE_TERMS:
            if pattern.search(text):
                target_event_date = msg_d + timedelta(days=offset)
                break

        # 2. Check explicit deadlines (к 03.10, до 26.09)
        deadline_date: date | None = None
        dl_match = cls.DEADLINE_REGEX.search(text)
        if dl_match:
            try:
                day = int(dl_match.group(1))
                month = int(dl_match.group(2))
                year = int(dl_match.group(3)) if dl_match.group(3) else reference_date.year
                if year < 100:
                    year += 2000
                deadline_date = date(year, month, day)
            except ValueError:
                deadline_date = None

        # 3. Check dates in parentheses, e.g. (26.09)
        if not target_event_date and not deadline_date:
            par_match = cls.PARENTHESES_DATE_REGEX.search(text)
            if par_match:
                try:
                    day = int(par_match.group(1))
                    month = int(par_match.group(2))
                    target_event_date = date(reference_date.year, month, day)
                except ValueError:
                    target_event_date = None

        # 4. Determine expiration and freshness status
        is_expired = False
        days_remaining = None

        if deadline_date:
            days_remaining = (deadline_date - reference_date).days
            if deadline_date < reference_date:
                is_expired = True
                status = f"Дедлайн прошел ({deadline_date.strftime('%d.%m')})"
                freshness_label = "EXPIRED"
            else:
                is_expired = False
                status = f"Активный дедлайн к {deadline_date.strftime('%d.%m')} (осталось {days_remaining} дн.)"
                freshness_label = "ACTIVE_FUTURE"
        elif target_event_date:
            days_remaining = (target_event_date - reference_date).days
            if target_event_date < reference_date:
                is_expired = True
                status = f"Событие уже прошло ({target_event_date.strftime('%d.%m')})"
                freshness_label = "EXPIRED"
            elif target_event_date == reference_date:
                is_expired = False
                status = "Событие запланировано на сегодня"
                freshness_label = "TODAY"
            else:
                is_expired = False
                status = f"Событие запланировано на {target_event_date.strftime('%d.%m')} (+{days_remaining} дн.)"
                freshness_label = "ACTIVE_FUTURE"
        else:
            # No specific dates in text — rely on message sending recency
            if days_ago <= 0:
                freshness_label = "TODAY"
                status = "Сообщение отправлено сегодня"
            elif days_ago == 1:
                freshness_label = "YESTERDAY"
                status = "Сообщение отправлено вчера"
            elif days_ago <= 3:
                freshness_label = "RECENT"
                status = f"Отправлено {days_ago} дн. назад"
            else:
                freshness_label = "STALE"
                is_expired = True
                status = f"Устаревшее ({days_ago} дн. назад)"

        return TemporalInfo(
            is_expired=is_expired,
            status=status,
            target_event_date=target_event_date,
            deadline_date=deadline_date,
            days_ago=days_ago,
            days_remaining=days_remaining,
            freshness_label=freshness_label,
        )
