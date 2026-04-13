from __future__ import annotations

from datetime import datetime, time


FROZEN_UNTIL_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
)


def parse_frozen_until(value: str) -> datetime | None:
    normalized = value.strip()
    if not normalized:
        return None

    for date_format in FROZEN_UNTIL_FORMATS:
        try:
            parsed = datetime.strptime(normalized, date_format)
        except ValueError:
            continue
        if date_format.endswith("%d"):
            return datetime.combine(parsed.date(), time.max.replace(microsecond=0))
        return parsed
    return None


def format_frozen_remaining(value: str, messages: dict[str, str], now: datetime | None = None) -> str:
    parsed = parse_frozen_until(value)
    if not parsed:
        return messages["frozen_remaining_not_set"]

    current_time = now or datetime.now()
    remaining_seconds = int((parsed - current_time).total_seconds())
    if remaining_seconds <= 0:
        return messages["frozen_remaining_expired"]

    days, remainder = divmod(remaining_seconds, 24 * 60 * 60)
    hours, remainder = divmod(remainder, 60 * 60)
    minutes = max(1, remainder // 60)

    if days > 0:
        return messages["frozen_remaining_days_hours"].format(days=days, hours=hours)
    if hours > 0:
        return messages["frozen_remaining_hours_minutes"].format(hours=hours, minutes=minutes)
    return messages["frozen_remaining_minutes"].format(minutes=minutes)
