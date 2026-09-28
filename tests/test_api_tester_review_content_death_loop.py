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
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from districts.qa.api_tester import APITester


@pytest.mark.asyncio
async def test_review_content_is_skipped_without_penalty():
    """The exact real-world dispatch shape from core/event_bus/wiring.py's
    CONTENT_READY trigger."""
    tester = APITester()
    tester.deduct_points = MagicMock()
    tester.award_points = MagicMock()

    result = await tester.run({"type": "review_content", "district": "qa", "params": {}})

    assert result["status"] == "not_applicable"
    tester.deduct_points.assert_not_called()
    tester.award_points.assert_not_called()


@pytest.mark.asyncio
async def test_arbitrary_unmatched_task_type_is_also_skipped_without_penalty():
    tester = APITester()
    tester.deduct_points = MagicMock()
    tester.award_points = MagicMock()

    result = await tester.run({"type": "some_other_misrouted_task"})

    assert result["status"] == "not_applicable"
    tester.deduct_points.assert_not_called()


@pytest.mark.asyncio
async def test_full_suite_still_runs_and_can_still_score():
    """The fix must not break APITester's own real job -- an explicit
    full_suite request still runs the real health check and can still
    award/deduct points based on the result."""
    tester = APITester()
    tester.run_full_suite = MagicMock(return_value=[])
    tester.compute_api_health = MagicMock(return_value={
        "grade": "F", "passed": 0, "total": 8, "avg_latency_ms": 0,
        "pass_rate": 0, "p95_latency_ms": 0, "slow_endpoints": [],
        "api_reachable": False, "failed_endpoints": ["/health"],
    })
    tester._get_memory = MagicMock(return_value=MagicMock(store=MagicMock()))
    tester._get_obsidian = MagicMock(return_value=MagicMock(write_note=MagicMock()))
    tester.deduct_points = MagicMock()

    result = await tester.run({"type": "full_suite"})

    assert result["status"] == "ok"
    tester.deduct_points.assert_called_once_with(20, "api_failing")


@pytest.mark.asyncio
async def test_single_endpoint_test_unaffected():
    tester = APITester()
    tester.test_endpoint = MagicMock(return_value={"ok": True})
    tester.award_points = MagicMock()

    result = await tester.run({"type": "single", "path": "/health"})

    assert result["status"] == "ok"
    tester.award_points.assert_called_once_with(15, "api_endpoint_tested")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
