"""Regression: BudgetMeter.check_quota()'s global daily-limit check summed
daily_spent across all agents, but only ever reset the REQUESTING agent's
own hourly/daily/monthly window (_maybe_reset is lazy-eval, called only
when that agent itself makes a call). An agent that goes quiet for over a
day keeps a stale, never-reset daily_spent forever -- the global sum could
include that ghost charge and wrongly block every OTHER agent's real,
current-day activity.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.metering.budget_meter import BudgetMeter


def test_stale_other_agent_spend_does_not_poison_global_check(tmp_path):
    meter = BudgetMeter(budget_file=tmp_path / "budgets.json")
    meter.set_limits("quiet_agent", daily_usd=5.0)
    meter._global_daily_limit = 10.0

    # quiet_agent spent heavily yesterday, then went quiet.
    budget = meter._get_or_create("quiet_agent")
    budget.daily_spent = 9.0
    budget.last_reset_daily = time.time() - 90000  # > 24h ago

    # A second agent makes a real request today.
    allowed, reason = meter.check_quota("active_agent")
    assert allowed, f"active_agent wrongly blocked by a stale ghost charge: {reason}"


def test_genuinely_fresh_other_agent_spend_still_counts(tmp_path):
    meter = BudgetMeter(budget_file=tmp_path / "budgets.json")
    meter._global_daily_limit = 5.0

    budget = meter._get_or_create("busy_agent")
    budget.daily_spent = 9.0
    budget.last_reset_daily = time.time()  # fresh, within window

    allowed, reason = meter.check_quota("another_agent")
    assert not allowed
    assert "global daily budget exceeded" in reason.lower()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
