"""Stage 4 finding #2 (external review 2026-09-24): a fallback step used to
inherit the failed step's verification unconditionally, so an unsatisfiable
check cascaded onto a fallback that itself worked and forced a second replan.
A fallback may now declare its own verification; None keeps inheritance.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.runtime.plans import Plan, PlanStep, PlanStepFallback, _try_fallback_step

_IMPOSSIBLE = {"type": "confidence_threshold", "min": 2.0}
_OWN = {"type": "status_check"}


def _plan_with(step: PlanStep) -> Plan:
    return Plan(id="p1", goal_id="", objective="t", status="active",
                created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
                steps=[step])


def _apply(step: PlanStep) -> PlanStep:
    plan = _plan_with(step)
    with patch("core.runtime.plans._get_epistemic_confidence", return_value=0.5):
        assert _try_fallback_step(plan, step) is True
    return plan.steps[0]


def test_fallback_with_own_verification_does_not_inherit_impossible_check():
    step = PlanStep(
        id="s3", action_type="git_status", verification=_IMPOSSIBLE,
        fallback=PlanStepFallback(action_type="recent_commits", verification=_OWN),
    )
    replaced = _apply(step)
    assert replaced.action_type == "recent_commits"
    assert replaced.verification == _OWN


def test_fallback_without_verification_still_inherits_original():
    step = PlanStep(
        id="s3", action_type="git_status", verification=_IMPOSSIBLE,
        fallback=PlanStepFallback(action_type="recent_commits"),
    )
    assert _apply(step).verification == _IMPOSSIBLE


def test_from_dict_round_trips_fallback_verification():
    fb = PlanStepFallback.from_dict(
        {"action_type": "recent_commits", "verification": _OWN}
    )
    assert fb.verification == _OWN
    assert PlanStepFallback.from_dict({"action_type": "x"}).verification is None
    assert PlanStepFallback.from_dict({"action_type": "x", "verification": "bad"}).verification is None
    assert PlanStepFallback.from_dict(fb.to_dict()).verification == _OWN


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
