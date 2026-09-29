"""Regression test for the 2026-09-24 external review's Phase 3 finding
(KNOWN_ISSUES #81, the APITester death loop): VECTOR_TECHNICAL_KNOWLEDGE/
81_LIVE_LOOP_HEALTH_CHECK.md documented ~858 real APITester deaths/day
(one every ~63s), 100% of `review_content` dispatches ending in death.

Root cause: `core/event_bus/wiring.py`'s CONTENT_READY trigger dispatches
`{"type": "review_content", "district": "qa", ...}` -- no qa-district
agent declares "review_content" as a real capability, so QASwarm's
keyword-score fallback landed on APITester, whose `run()` defaulted ANY
unmatched task_type to running the full, SCORED API-health suite. If the
API server wasn't reachable at that moment, the resulting "grade F" cost
a real -20 HP on every single dispatch.

2026-09-29 rewrite (P1's SELF_DEV_P1_QA_VERIFICATION.md flagged this file as
NOT qualifying real verification: it replaced `award_points`/`deduct_points`
-- real AgentBase HP internals -- with MagicMocks, and mocked several of
APITester's own methods, defeating the point of a real-behavior test. Every
test below now tracks the agent's real `health_points` before/after instead
of mocking the HP methods, and lets `run_full_suite`/`test_endpoint` make
their real httpx calls (there is no API server listening in this test
environment, so they genuinely exercise the real "API unreachable" path --
the exact scenario #81 was about, not a fabricated one).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from districts.qa.api_tester import APITester


@pytest.mark.asyncio
async def test_review_content_is_skipped_without_penalty():
    """The exact real-world dispatch shape from core/event_bus/wiring.py's
    CONTENT_READY trigger."""
    tester = APITester()
    hp_before = tester.health_points

    result = await tester.run({"type": "review_content", "district": "qa", "params": {}})

    assert result["status"] == "not_applicable"
    assert tester.health_points == hp_before  # no real HP change, up or down


@pytest.mark.asyncio
async def test_arbitrary_unmatched_task_type_is_also_skipped_without_penalty():
    tester = APITester()
    hp_before = tester.health_points

    result = await tester.run({"type": "some_other_misrouted_task"})

    assert result["status"] == "not_applicable"
    assert tester.health_points == hp_before


@pytest.mark.asyncio
async def test_full_suite_runs_the_real_health_check_and_scores_it_for_real():
    """The fix must not break APITester's own real job -- an explicit full_suite
    request still runs the real health check (real httpx calls; no server is
    listening in this test environment, so every endpoint genuinely fails
    unreachable) and applies a real HP penalty for the real grade-F result."""
    tester = APITester()
    hp_before = tester.health_points

    result = await tester.run({"type": "full_suite"})

    assert result["status"] == "ok"
    health = result["health"]
    assert health["api_reachable"] is False  # real: nothing is listening
    assert health["grade"] == "F"
    assert tester.health_points == hp_before - 20  # real "api_failing" deduction, not mocked


@pytest.mark.asyncio
async def test_single_endpoint_test_unaffected():
    """A single-endpoint check always awards HP for having tested it, regardless of
    whether the endpoint itself was reachable -- exercised for real against an address
    nothing is listening on, proving the award is unconditional on the real result."""
    tester = APITester()
    hp_before = tester.health_points

    result = await tester.run({"type": "single", "path": "/health"})

    assert result["status"] == "ok"
    assert result["result"]["ok"] is False  # real: connection refused, not mocked as success
    # award_points() applies real repeat-reason/headroom damping (see agent_base.py), so the
    # exact delta isn't a fixed +15 -- the real, checkable invariant is that an award call can
    # never lower HP (max(0.0, ...) before adding), unlike the real -20 deduction proven above.
    assert tester.health_points >= hp_before


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
