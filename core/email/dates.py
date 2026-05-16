import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


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


def format_list_date(date_str: str) -> str:
    """Email list rows: today → '3:42 PM', this year → 'Apr 15', older → 'Apr 15, 2024'."""
    date = _safe_parse(date_str)
    if not date:
        return date_str
    now = datetime.now(timezone.utc) if date.tzinfo else datetime.now()
    if date.date() == now.date():
        return date.strftime("%-I:%M %p").lstrip("0") if hasattr(date, "strftime") else date.strftime("%I:%M %p")
    if date.year == now.year:
        return date.strftime("%b %-d")
    return date.strftime("%b %-d, %Y")


def format_detail_date(date_str: str) -> str:
    """Email detail header: 'Tue, Apr 15, 3:42 PM'."""
    date = _safe_parse(date_str)
    if not date:
        return date_str
    return date.strftime("%a, %b %-d, %I:%M %p").replace(" 0", " ")


def format_short_date(date_str: str) -> str:
    """Thread message headers — time only: '3:42 PM'."""
    date = _safe_parse(date_str)
    if not date:
        return date_str
    return date.strftime("%I:%M %p").lstrip("0")


def format_quoted_date(date_str: str | None) -> str:
    """Quoted reply blocks: 'Tue, Apr 15, 2026, 3:42 PM'."""
    if not date_str:
        return ""
    date = _safe_parse(date_str)
    if not date:
        return date_str
    return date.strftime("%a, %b %-d, %Y, %I:%M %p").replace(" 0", " ")


if __name__ == "__main__":
    ts = "2026-05-17T15:42:00Z"
    assert format_quoted_date(ts) != ""
    assert format_list_date(ts) != ""
    assert format_detail_date(ts) != ""
    assert format_short_date(ts) != ""
    assert format_quoted_date(None) == ""
    print("✅ dates.py OK")
