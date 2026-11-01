"""Trading calendar — holiday-aware market skip logic for NSE/BSE."""
from datetime import date, timedelta

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()


# NSE/BSE holidays 2026 (approximate — update annually)
NSE_HOLIDAYS_2026 = {
    date(2026, 1, 26),  # Republic Day
    date(2026, 3, 31),  # Holi (approx)
    date(2026, 4, 14),  # Dr. Ambedkar Jayanti
    date(2026, 5, 1),   # Maharashtra Day
    date(2026, 8, 15),  # Independence Day
    date(2026, 10, 2),  # Gandhi Jayanti
    date(2026, 11, 4),  # Diwali (approx)
    date(2026, 12, 25), # Christmas
}

def is_trading_day(d: date = None, market: str = "NSE") -> bool:
    """Check if given date is a trading day (not weekend, not holiday)."""
    if d is None:
        d = date.today()
    if d.weekday() >= 5:  # Saturday or Sunday
        return False
    if market in ("NSE", "BSE") and d in NSE_HOLIDAYS_2026:
        return False
    return True

def next_trading_day(from_date: date = None, market: str = "NSE") -> date:
    """Return the next trading day from given date."""
    d = (from_date or date.today()) + timedelta(days=1)
    while not is_trading_day(d, market):
        d += timedelta(days=1)
    return d

def should_skip_today(market: str = "NSE") -> bool:
    """Return True if today's analysis should be skipped (not a trading day)."""
    return not is_trading_day(market=market)

if __name__ == "__main__":
    print("✅ trading_calendar OK")
    print("Today is trading day:", is_trading_day())
    print("Next trading day:", next_trading_day())
