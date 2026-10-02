"""Regression: core/email/dates.py's format_list_date() compared an aware
date's own .date() (the SENDER's local calendar date, from a real email
Date: header offset like "+0530") directly against datetime.now(utc).date()
-- not the same basis. An email sent "today" in UTC terms could be
misclassified as not-today (showing "May 18" instead of a time like
"2:00 AM") whenever the sender's offset pushes their local calendar date to
a different day than UTC's, near UTC midnight.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.email import dates as dates_mod
from core.email.dates import format_list_date


class _FrozenDatetime(datetime):
    """Real datetime subclass -- strptime()/astimezone() work exactly like
    the real thing (returns _FrozenDatetime instances, which still support
    .date()/.tzinfo/.hour/.minute), only now() is pinned."""
    _frozen_now: datetime

    @classmethod
    def now(cls, tz=None):
        return cls._frozen_now if tz else cls._frozen_now.replace(tzinfo=None)


def _freeze(monkeypatch, frozen_utc_now: datetime):
    frozen = type("_FrozenDatetime", (_FrozenDatetime,), {"_frozen_now": frozen_utc_now})
    monkeypatch.setattr(dates_mod, "datetime", frozen)


def test_format_list_date_uses_utc_basis_for_today_check(monkeypatch):
    # Sender-local date is 2026-05-18, but the same instant in UTC is still
    # 2026-05-17 -- "now" (frozen) is 2026-05-17 in UTC too, so this email
    # genuinely IS "today" and must render as a time, not a date.
    _freeze(monkeypatch, datetime(2026, 5, 17, 23, 0, 0, tzinfo=timezone.utc))
    result = format_list_date("2026-05-18T02:00:00+0530")
    assert result == "2:00 AM", f"expected a time (today), got {result!r}"


def test_format_list_date_non_today_still_shows_date(monkeypatch):
    # Display still uses the email's own (sender-local) date fields -- the
    # fix only changes the "is this today" comparison basis, not what's
    # shown -- so this correctly shows "May 18" (the sender's own date),
    # not "May 17" (its UTC equivalent).
    _freeze(monkeypatch, datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc))
    result = format_list_date("2026-05-18T02:00:00+0530")
    assert result == "May 18", f"expected the sender-local month/day (not today), got {result!r}"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
