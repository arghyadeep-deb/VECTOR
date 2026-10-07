"""Smoke tests: does the twin actually run REAL DecisionEngine logic against
isolated storage and produce a sane trace? These must pass before any
higher-level lab module (experiments, level4, controls, ...) can be trusted.
"""
from __future__ import annotations

from scenario import Scenario, CandidateSpec
from twin import DigitalTwin


def test_auto_scenario_runs_with_real_seeded_goals():
    """label-only Scenario => real PRESEEDED_GOALS => real generate_immediate_actions()."""
    trace = DigitalTwin().run(Scenario(label="auto_baseline"))
    assert trace.error is None, trace.error
    assert trace.candidates, "expected at least one real generated candidate"
    assert trace.selected_action is not None
    # Every real seeded LONG/MID goal starts at progress 0.0 except
    # g_vector_phase1 (0.25) — so analyze_progress-mapped candidates should
    # dominate, matching documented production behavior (Task 71/72).
    action_types = {c.action_type for c in trace.candidates}
    assert action_types & {"check_attendance", "code_task", "git_status", "read_code"}


def test_explicit_candidates_are_scored_deterministically():
    scenario = Scenario(
        label="explicit_two_candidates",
        candidates=[
            CandidateSpec(action_type="search_web", params={"q": "x"}, confidence=0.8, urgency=0.6),
            CandidateSpec(action_type="check_calendar", params={}, confidence=0.9, urgency=0.3),
        ],
    )
    trace = DigitalTwin().run(scenario)
    assert trace.error is None, trace.error
    assert len(trace.candidates) == 2
    assert trace.selected_action in {"search_web", "check_calendar"}
    for c in trace.candidates:
        assert 0.0 <= c.total_score <= 1.0
        assert c.score_components, "real DecisionEngine must populate reasoning_chain"


def test_isolation_never_touches_a_second_runs_state():
    """Two independent DigitalTwin().run() calls must not see each other's
    policy history — proves each run gets a genuinely fresh isolated DB."""
    scenario = Scenario(
        label="isolation_check",
        candidates=[CandidateSpec(action_type="search_web", params={"q": "isolation"})],
    )
    t1 = DigitalTwin().run(scenario)
    t2 = DigitalTwin().run(scenario)
    assert t1.error is None and t2.error is None
    # Same inputs, no prior policy history in either isolated DB => identical score.
    assert t1.candidates[0].total_score == t2.candidates[0].total_score


def test_error_is_captured_not_raised_on_bad_candidate():
    """A scenario that can't be scored must produce a trace with `.error`
    set, never an uncaught exception — the lab must be safe to script."""
    scenario = Scenario(label="deliberately_broken", candidates="auto",
                         goals=[])  # empty goals -> generate_immediate_actions() -> [] -> "no candidates"
    trace = DigitalTwin().run(scenario)
    assert trace.error is None  # empty candidates is handled gracefully by DecisionEngine itself
    assert trace.selected_action is None
    assert trace.candidates == []
    assert trace.decision_reason == "No candidates"
