"""
Root-caused a critical, previously-undiscovered bug found while debugging a
live soak run (2026-06-24): core/loop/autonomous_loop.py's observe_loop()
calls `guard.reset()` after LoopGuard terminates (max_iterations exceeded),
but LoopGuardState never defined a `reset()` method at all (only
`reset_recent_calls()`, which only clears the phantom-detection ring buffer).

Real-world impact, confirmed via data/logs/vector_loop.log during a live
run: `_violations` is an append-only list and `is_terminated` is
`any(v.kind == "max_iterations" for v in self._violations)` -- so once the
guard hits its first max_iterations violation, is_terminated is permanently
True forever (nothing ever removes items from _violations). Every
subsequent observe tick: guard.tick() increments iteration, sees
is_terminated still True, calls the nonexistent guard.reset(), raises
AttributeError, gets caught by observe_loop's outer except and logged as an
ERROR via _capture_loop_error -- then the loop sleeps and repeats, forever.
Confirmed live: 2628 occurrences accumulated in well under a minute of
runtime, roughly 2/second.

Since guard is a single long-lived instance created once per observe_loop()
invocation (not recreated per tick), this means the loop guard has been
permanently broken on every single tick after the first ~50 ticks of any
run, for as long as this code has existed -- a real, severe, previously
invisible defect (no log sink existed to surface it before this session).

Fixed: added LoopGuardState.reset() that clears iteration, _violations,
_recent_calls, and restarts _started_at -- restoring the guard to a fresh,
usable state for the next task cycle, exactly matching the call site's own
comment ("LoopGuard terminated — resetting").
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_loop_guard_state_has_a_real_reset_method():
    from core.loop.loop_guard import LoopGuardState

    guard = LoopGuardState(task_id="test")
    assert hasattr(guard, "reset"), "LoopGuardState must define reset() -- autonomous_loop.py calls it directly"


def test_reset_clears_iteration_count():
    from core.loop.loop_guard import LoopGuardState

    guard = LoopGuardState(task_id="test", max_iterations=5)
    for _ in range(6):
        guard.tick()
    assert guard.iteration == 6
    guard.reset()
    assert guard.iteration == 0


def test_reset_clears_termination_state():
    """The exact bug: is_terminated must become False again after reset(),
    not stay permanently True (the real-world infinite-error-loop cause)."""
    from core.loop.loop_guard import LoopGuardState

    guard = LoopGuardState(task_id="test", max_iterations=3)
    for _ in range(4):
        guard.tick()
    assert guard.is_terminated is True
    guard.reset()
    assert guard.is_terminated is False


def test_guard_is_usable_again_after_reset_for_many_cycles():
    """Real-world reproduction: the guard must survive many
    terminate-then-reset cycles without ever permanently sticking, exactly
    as autonomous_loop.py's observe_loop() does every interval forever."""
    from core.loop.loop_guard import LoopGuardState

    guard = LoopGuardState(task_id="test", max_iterations=5)
    for _cycle in range(20):
        for _ in range(6):
            guard.tick()
        if guard.is_terminated:
            guard.reset()
        assert guard.is_terminated is False


def test_reset_clears_phantom_detection_buffer_too():
    from core.loop.loop_guard import LoopGuardState

    guard = LoopGuardState(task_id="test")
    guard.check_phantom("some_tool", {"a": 1})
    guard.check_phantom("some_tool", {"a": 1})
    assert len(guard._recent_calls) == 2
    guard.reset()
    assert len(guard._recent_calls) == 0


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
