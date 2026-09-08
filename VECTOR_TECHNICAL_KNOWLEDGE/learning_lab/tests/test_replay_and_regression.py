"""Replay determinism + regression case classification tests."""
from __future__ import annotations

import json

from scenario import Scenario, CandidateSpec, PolicyUpdateSpec
from replay import record, replay
from regression import save_case, check_case, RegressionVerdict


def _scenario(label="replay_test"):
    return Scenario(label=label, candidates=[
        CandidateSpec(action_type="search_web", params={"q": "rt"}, confidence=0.7, urgency=0.5),
        CandidateSpec(action_type="check_calendar", params={}, confidence=0.5, urgency=0.5),
    ])


def test_unmodified_scenario_replays_deterministically(tmp_path):
    path = tmp_path / "scenario.json"
    record(_scenario(), path)
    result = replay(path)
    assert result.matched, result.reason


def test_modified_scenario_replay_reports_a_specific_reason(tmp_path):
    path = tmp_path / "scenario.json"
    record(_scenario(), path)

    # Mutate the saved scenario on disk to inject a policy update that was
    # not present at record time — this MUST change the outcome.
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["scenario"]["policy_updates"] = [
        {"action_type": "search_web", "params": {"q": "rt"}, "reward": 0.99, "note": "injected"}
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = replay(path)
    assert not result.matched
    assert "score changed" in result.reason or "selected_action changed" in result.reason


def test_regression_case_preserved_when_nothing_changes(tmp_path):
    case = save_case("case_a", _scenario(), tmp_path)
    check = check_case(case)
    assert check.verdict == RegressionVerdict.PRESERVED


def test_regression_case_unintended_change_detected(tmp_path):
    case = save_case("case_b", _scenario(), tmp_path)
    payload = json.loads(case.path.read_text(encoding="utf-8"))
    payload["scenario"]["policy_updates"] = [
        {"action_type": "search_web", "params": {"q": "rt"}, "reward": 0.99, "note": "injected"}
    ]
    case.path.write_text(json.dumps(payload), encoding="utf-8")

    check = check_case(case)
    assert check.verdict == RegressionVerdict.UNINTENDED_CHANGE


def test_regression_case_intended_change_accepted(tmp_path):
    case = save_case("case_c", _scenario(), tmp_path)
    case.accept_change = True
    payload = json.loads(case.path.read_text(encoding="utf-8"))
    payload["scenario"]["policy_updates"] = [
        {"action_type": "search_web", "params": {"q": "rt"}, "reward": 0.99, "note": "injected"}
    ]
    case.path.write_text(json.dumps(payload), encoding="utf-8")

    check = check_case(case)
    assert check.verdict == RegressionVerdict.INTENDED_CHANGE
