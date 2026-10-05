"""Regression for vectorcode/src/vc_agents/loop_guard.py's LoopGuard.check_call():

check_call()'s warn-before-block wrapper deduplicated on `verdict.reason`,
the human-readable message string. For the identical_call trigger, that
message embeds the current call count ("...repeated {n} times..."), which
increments on every single call -- so the dedup key was never the same
twice after the first block-worthy call, and `cycle_key not in
self._warned_cycles` was always True. The guard therefore warned forever
and never actually reached the "block" stage its own docstring promises
("warn on first cycle, block on second"), defeating the entire purpose of
a tool meant to prevent degenerate agent loops.

Confirmed live before the fix: 8 identical calls with
max_identical_calls=3 all came back blocked=False (5 of them past the
point they should have been blocked). Fixed by adding a stable
`trigger_key` field to LoopVerdict, set independently of the
human-readable `reason` text, and using that (not `reason`) as the
warn-before-block dedup key.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.vc_agents.loop_guard import LoopGuard, LoopGuardConfig


def _guard(**overrides) -> LoopGuard:
    config = LoopGuardConfig(warn_before_block=True, **overrides)
    guard = LoopGuard(config)
    guard._rust_impl = None  # force the pure-Python path deterministically
    return guard


def test_identical_call_warns_once_then_actually_blocks():
    guard = _guard(max_identical_calls=3)

    results = [guard.check_call("my_tool", '{"x": 1}') for _ in range(8)]

    # Calls 1-3: under the limit, never flagged.
    assert all(not r.blocked and not r.warned for r in results[:3])
    # Call 4: first time over the limit -- warn, but let it through once.
    assert results[3].blocked is False and results[3].warned is True
    # Calls 5-8: must now genuinely block, not warn forever.
    assert all(r.blocked is True for r in results[4:]), (
        "guard never reached the block stage -- warn-before-block dedup regressed"
    )


def test_poll_budget_warns_once_then_blocks():
    guard = _guard(poll_tool_budget=2, max_identical_calls=100)

    # Vary arguments so the identical-call hash check never fires; only
    # the per-tool poll budget should trigger here.
    results = [
        guard.check_call("poller", f'{{"page": {i}}}') for i in range(6)
    ]

    assert all(not r.blocked for r in results[:2])
    assert results[2].blocked is False and results[2].warned is True
    assert all(r.blocked is True for r in results[3:])


def test_distinct_tools_get_independent_warn_cycles():
    guard = _guard(max_identical_calls=1)

    # Exhaust the warning for tool_a; tool_b must still get its own warn,
    # not be silently blocked because of an overly-broad dedup key.
    guard.check_call("tool_a", "{}")
    warned_a = guard.check_call("tool_a", "{}")
    first_b = guard.check_call("tool_b", "{}")

    assert warned_a.warned is True and warned_a.blocked is False
    assert first_b.blocked is False and first_b.warned is False


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
