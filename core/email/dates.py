# --- Windows console UTF-8 safety (VECTOR codemod) ---
import sys as _vsys  # noqa: E402
for _vstream in (_vsys.stdout, _vsys.stderr):
    try:
        if _vstream is not None and hasattr(_vstream, "reconfigure") and (getattr(_vstream, "encoding", "") or "").lower() not in ("utf-8", "utf8"):
            _vstream.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
# ---------------------------------------------------------------------------


__all__ = [
    "format_detail_date",
    "format_list_date",
    "format_quoted_date",
    "format_short_date",
]

import platform
from datetime import datetime, timezone


_IS_WINDOWS = platform.system() == "Windows"


def _safe_parse(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%a, %d %b %Y %H:%M:%S %z",
    ):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def _day(dt: datetime) -> str:
    """Return day-of-month without leading zero, cross-platform."""
    return str(dt.day)


def _time12(dt: datetime) -> str:
    """Return 12-hour time like '3:42 PM', cross-platform."""
    h = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{h}:{dt.minute:02d} {ampm}"


def format_list_date(date_str: str) -> str:
    """Email list rows: today → '3:42 PM', this year → 'Apr 15', older → 'Apr 15, 2024'."""
    date = _safe_parse(date_str)
    if not date:
        return date_str
    now = datetime.now(timezone.utc) if date.tzinfo else datetime.now()
    # Compare calendar dates in a common basis: an aware `date` may carry a
    # non-UTC sender offset (e.g. "+0530" from an email's real Date: header),
    # so its own .date() is the SENDER's local calendar date, not UTC's --
    # comparing that directly against `now`'s UTC calendar date misclassifies
    # "today" near UTC midnight for any non-UTC-offset sender.
    compare_date = date.astimezone(timezone.utc) if date.tzinfo else date
    if compare_date.date() == now.date():
        return _time12(date)
    month = date.strftime("%b")
    if date.year == now.year:
        return f"{month} {_day(date)}"
    return f"{month} {_day(date)}, {date.year}"


def format_detail_date(date_str: str) -> str:
    """Email detail header: 'Tue, Apr 15, 3:42 PM'."""
    date = _safe_parse(date_str)
    if not date:
        return date_str
    weekday = date.strftime("%a")
    month = date.strftime("%b")
    return f"{weekday}, {month} {_day(date)}, {_time12(date)}"


def format_short_date(date_str: str) -> str:
    """Thread message headers — time only: '3:42 PM'."""
    date = _safe_parse(date_str)
    if not date:
        return date_str
    return _time12(date)


def format_quoted_date(date_str: str | None) -> str:
    """Quoted reply blocks: 'Tue, Apr 15, 2026, 3:42 PM'."""
    if not date_str:
        return ""
    date = _safe_parse(date_str)
    if not date:
        return date_str
    weekday = date.strftime("%a")
    month = date.strftime("%b")
    return f"{weekday}, {month} {_day(date)}, {date.year}, {_time12(date)}"


if __name__ == "__main__":
    ts = "2026-05-17T15:42:00Z"
    assert format_quoted_date(ts) != ""
    assert format_list_date(ts) != ""
    assert format_detail_date(ts) != ""
    assert format_short_date(ts) != ""
    assert format_quoted_date(None) == ""
    print("✅ dates.py OK")
