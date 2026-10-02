"""Regression: core/email/search.py's _normalize_date() appended "Z" to a
datetime.strptime() result from formats that never parse a timezone --
always naive -- fabricating a UTC marker the user's bare "2025-01-01"
input never specified. districts/communications/email_agent.py's
search_emails() string-compares this directly against the emails.date
column, which is stored via naive local datetime.now().isoformat() (no
"Z") -- the mismatched suffix made before:/after: filters compare
unreliably at boundary timestamps.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.email.search import parse_search_query


def test_normalized_date_has_no_fabricated_utc_marker():
    result = parse_search_query("after:2025-01-01")
    assert result.date_start is not None
    assert not result.date_start.endswith("Z"), (
        f"date_start {result.date_start!r} fabricates a UTC marker the input never specified"
    )


def test_normalized_date_matches_naive_isoformat_storage_convention():
    # This is literally what districts/communications/email_agent.py stores
    # into the `date` column: datetime.now().isoformat() -- naive, no "Z".
    stored_style = datetime(2025, 1, 1, 0, 0, 0).isoformat()
    result = parse_search_query("after:2025-01-01")
    assert result.date_start == stored_style


def test_boundary_comparison_no_longer_misorders_same_moment():
    # Same nominal moment, stored style (with microseconds, no Z) vs the
    # normalized filter value -- must compare as equal-or-after, not before.
    stored = "2025-01-01T00:00:00.000000"
    filter_value = parse_search_query("after:2025-01-01").date_start
    assert stored >= filter_value, (
        f"stored={stored!r} should sort >= filter={filter_value!r} for the same moment"
    )


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
