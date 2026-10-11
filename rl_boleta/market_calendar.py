"""Frozen US cash-equity core sessions for the paper's March--July 2025 period.

Intentionally bounded: extending the period requires checking official notices,
including exceptional closures. This is not a futures/options calendar.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

NAME = "us-equities-paper-2025"
FIRST = date(2025, 3, 3)
LAST = date(2025, 7, 31)
SOURCES = [
    "https://ir.theice.com/press/news-details/2024/NYSE-Group-Announces-2025-2026-and-2027-Holiday-and-Early-Closings-Calendar/default.aspx",
    "https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2025-37",
]
CLOSURES = {
    date(2025, 4, 18): "Good Friday",
    date(2025, 5, 26): "Memorial Day",
    date(2025, 6, 19): "Juneteenth",
    date(2025, 7, 4): "Independence Day",
}
EARLY_CLOSES = {date(2025, 7, 3): time(13)}
ZONE = ZoneInfo("America/New_York")


def window(day):
    if not FIRST <= day <= LAST:
        raise ValueError(f"calendar date outside verified scope: {day} ({FIRST}..{LAST})")
    if day.weekday() >= 5 or day in CLOSURES:
        return None
    return (datetime.combine(day, time(9, 30), ZONE),
            datetime.combine(day, EARLY_CLOSES.get(day, time(16)), ZONE))


def dates(first, last):
    if first > last:
        raise ValueError("session first date must not exceed last date")
    window(first)
    window(last)
    day = first
    while day <= last:
        yield day
        day += timedelta(days=1)


def metadata():
    return {"name": NAME, "version": 1, "timezone": "America/New_York",
            "verified_first_date": str(FIRST), "verified_last_date": str(LAST),
            "closures": {str(k): v for k, v in CLOSURES.items()},
            "early_closes": {str(k): v.isoformat() for k, v in EARLY_CLOSES.items()},
            "sources": SOURCES, "verified_at": "2026-10-08"}
