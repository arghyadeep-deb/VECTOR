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
    """The taint section must escalate to a blocked RETURN, not just log.

    2026-08-06: this used to slice a fixed `src[start:start + 1400]` window.
    That broke when a comment was added inside the taint section — it pushed
    the (unchanged, still-correct) blocking code to ~3,800 chars past the
    marker, so the window no longer reached it and the test failed while the
    security control was completely intact. A magic character count is not
    the invariant; "the taint check blocks before the agent runs" is.

    So scan the real region: from the taint marker to the point where the
    agent is actually invoked. That is strictly stronger than the old window
    (it cannot silently pass because the code drifted out of view) and it
    cannot break again just because someone wrote a longer comment.
    """
    src = inspect.getsource(Governor.dispatch)
    start = src.index("Taint tracking")
    region = src[start:src.index("agent.run(task)")]
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
