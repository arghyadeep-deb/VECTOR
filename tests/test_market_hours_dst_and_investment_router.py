"""Regression: core/api/routers/investment.py's /market-status endpoint used
to re-implement market-hours math itself with a hardcoded US ET offset of
-4.0 ("EDT, summer") applied YEAR-ROUND -- wrong for the ~5 months/year the
US is actually on EST (UTC-5). core/utils/market_hours.py already handles
this correctly via ZoneInfo("America/New_York")'s real DST transitions.
Fixed the router to delegate to it instead of keeping two implementations.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.utils import market_hours as market_hours_mod
from core.api.routers import investment as investment_mod


class _FrozenDatetime(datetime):
    _frozen_now: datetime

    @classmethod
    def now(cls, tz=None):
        return cls._frozen_now if tz else cls._frozen_now.replace(tzinfo=None)


def _freeze(monkeypatch, module, frozen_utc_now: datetime):
    frozen = type("_FrozenDatetime", (_FrozenDatetime,), {"_frozen_now": frozen_utc_now})
    monkeypatch.setattr(module, "datetime", frozen)


def test_old_hardcoded_offset_was_wrong_during_est(monkeypatch):
    """Prove the bug: a naive -4.0 (EDT) offset misreads a real EST-period
    UTC instant. 2026-01-15 15:00 UTC is 10:00 ET (EST, UTC-5) -- market
    open (opens 9:30 ET). The old hardcoded -4.0 offset would compute
    11:00 "ET" instead -- still open here, but the wall-clock hour is
    simply wrong, and at other UTC instants this shifts open/closed
    across the actual boundary (e.g. 20:30 UTC is 15:30 ET real EST --
    open; the broken -4.0 offset reads it as 16:30 "ET" -- closed)."""
    broken_offset_et_hour = (15 + (-4.0)) % 24  # old code's formula
    real_et_hour = datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc).astimezone(
        market_hours_mod.ZoneInfo("America/New_York")).hour
    assert real_et_hour == 10
    assert broken_offset_et_hour == 11
    assert real_et_hour != broken_offset_et_hour


def test_is_market_open_correct_across_dst_boundary(monkeypatch):
    # 2026-01-15 20:30 UTC = 15:30 ET (EST, UTC-5) -- market open (closes 16:00 ET)
    _freeze(monkeypatch, market_hours_mod, datetime(2026, 1, 15, 20, 30, tzinfo=timezone.utc))
    assert market_hours_mod.is_market_open("us-stock") is True

    # 2026-01-15 21, 30 UTC = 16:30 ET (EST) -- market closed
    _freeze(monkeypatch, market_hours_mod, datetime(2026, 1, 15, 21, 30, tzinfo=timezone.utc))
    assert market_hours_mod.is_market_open("us-stock") is False

    # 2026-07-15 20:30 UTC = 16:30 ET (EDT, UTC-4) -- market closed (summer)
    _freeze(monkeypatch, market_hours_mod, datetime(2026, 7, 15, 20, 30, tzinfo=timezone.utc))
    assert market_hours_mod.is_market_open("us-stock") is False


def test_market_status_endpoint_delegates_to_market_hours(monkeypatch):
    """The router no longer computes its own offset-based open/closed --
    both agree because the endpoint calls the shared, correct helper."""
    assert "def _market_open" not in Path(investment_mod.__file__).read_text(encoding="utf-8")

    import asyncio
    result = asyncio.run(investment_mod.get_market_status())
    assert result["us"]["open"] == market_hours_mod.is_market_open("us-stock")
    assert result["india"]["open"] == market_hours_mod.is_market_open("india-stock")
    assert result["crypto"]["open"] is True


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
