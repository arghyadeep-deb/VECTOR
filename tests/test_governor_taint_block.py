"""Regression guard: a taint violation must BLOCK dispatch, not just log.

Security fix 2026-06-21 (audit finding): governor.dispatch tagged user-supplied
content and detected when it flowed to a shell/exec or net sink — but only
logged a warning and proceeded. A control that doesn't control. Now it returns
a 'blocked' result. Source-level guard (governor.dispatch needs a full registry
+ agents to invoke behaviorally; the structural check is the soak-safe choice).
"""
import inspect

from core.city.governor import Governor


def test_taint_violation_returns_blocked():
    src = inspect.getsource(Governor.dispatch)
    start = src.index("Taint tracking")
    region = src[start:start + 1400]
    assert "BLOCKED" in region, "taint violation no longer escalated"
    assert "return" in region and '"blocked"' in region, (
        "taint violation only logs — it must RETURN a blocked status"
    )


def test_taint_block_precedes_dispatch():
    src = inspect.getsource(Governor.dispatch)
    # the taint block must sit before the agent is actually run
    assert src.index("Taint tracking") < src.index("agent.run(task)"), (
        "taint check runs after dispatch — too late to block"
    )
