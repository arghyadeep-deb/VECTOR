"""Regression for vectorcode/src/agent/usage_pricing.py's format_token_count_compact().

Just below a unit threshold (e.g. 999_999, just under the 1_000_000 "M"
threshold), the function picks the smaller unit ("K") and rounds the
scaled value with ".0f" -- 999.999 rounds to "1000", producing the display
string "1000K" instead of rolling over into the next bigger unit, "1M".
The same rollover happens at the M/B boundary (999_994_999 -> "1000M"
instead of "1B"). Fixed by detecting a >=1000 rounded value and
re-rendering against the next bigger unit.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_SRC = Path(__file__).parent.parent / "vectorcode" / "src" / "agent" / "usage_pricing.py"


def _load_format_token_count_compact():
    """Extract just this pure function via regex so the test doesn't need
    to satisfy usage_pricing.py's full package-relative import chain
    (agent/model_metadata.py etc.), which is irrelevant to this bug."""
    src = _SRC.read_text(encoding="utf-8")
    m = re.search(r"def format_token_count_compact.*?(?=\n\ndef |\Z)", src, re.S)
    assert m, "format_token_count_compact not found in usage_pricing.py"
    ns: dict = {}
    exec(m.group(0), ns)
    return ns["format_token_count_compact"]


format_token_count_compact = _load_format_token_count_compact()


def test_just_below_million_rolls_over_to_M_not_1000K():
    for v in (999_994, 999_995, 999_999):
        result = format_token_count_compact(v)
        assert result == "1M", f"format_token_count_compact({v}) == {result!r}, expected '1M'"


def test_just_below_billion_rolls_over_to_B_not_1000M():
    for v in (999_994_999, 999_995_001):
        result = format_token_count_compact(v)
        assert result == "1B", f"format_token_count_compact({v}) == {result!r}, expected '1B'"


def test_exact_and_ordinary_values_unaffected():
    assert format_token_count_compact(999) == "999"
    assert format_token_count_compact(1_000_000) == "1M"
    assert format_token_count_compact(1_500) == "1.5K"
    assert format_token_count_compact(123_456_789) == "123M"
    assert format_token_count_compact(-999_999) == "-1M"


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
