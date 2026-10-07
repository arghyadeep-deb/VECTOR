"""Regression coverage for defects found by the final learning-lab audit."""
from __future__ import annotations

import json
import os
import ast
from pathlib import Path

import pytest

from experiments import _components_by_action
from isolation import IsolatedVectorEnv
from replay import record, replay
from scenario import Scenario
from trace import CandidateTrace, DecisionTrace
from twin import build_isolated_engine


def _trace(*, error: str | None = None) -> DecisionTrace:
    candidate = CandidateTrace(
        action_type="search_web",
        params={},
        goal_ids=[],
        confidence=0.5,
        urgency=0.5,
        timing_score=1.0,
        estimated_cost_inr=0.0,
        source="test",
        goal_alignment=0.3,
        policy_score=0.5,
        total_score=0.4,
        score_components=[
            {"factor": "policy_score", "value": 0.5, "weight": 0.2},
            {"factor": "self_model_capability", "value": "no_capable_agent", "weight": 0.85},
        ],
        reasoning_steps=[],
        rejected=False,
    )
    return DecisionTrace(
        run_id="test",
        scenario_label="test",
        situation={},
        active_goals=[],
        generated_candidates=[],
        memory_inputs={},
        policy_inputs=[],
        counterfactual_inputs={},
        epistemic_inputs=[],
        candidates=[] if error else [candidate],
        selected_action=None if error else "search_web",
        selected_params={},
        rejected_actions=[],
        decision_reason="",
        counterfactual_vetoed=False,
        veto_reason="",
        error=error,
    )


class _Twin:
    def __init__(self, trace: DecisionTrace):
        self.trace = trace

    def run(self, scenario: Scenario) -> DecisionTrace:
        return self.trace


def test_isolation_rejects_overlapping_contexts():
    with IsolatedVectorEnv():
        with pytest.raises(RuntimeError, match="already active"):
            with IsolatedVectorEnv():
                pass


def test_isolation_rejects_unconfined_base_dir(tmp_path):
    with pytest.raises(ValueError, match="run-scoped temporary"):
        with IsolatedVectorEnv(base_dir=tmp_path):
            pass


def test_isolation_covers_memory_tree_and_plan_store():
    with IsolatedVectorEnv() as env:
        assert os.environ["VECTOR_MEMORY_TREE_PATH"] == str(env.paths.memory_tree_dir)
        assert json.loads((env.paths.memory_tree_dir / "memory_tree.json").read_text(encoding="utf-8")) == {}
        engine = build_isolated_engine(env)
        assert engine._plan_store.path == env.paths.plan_store


def test_non_numeric_reasoning_signals_do_not_break_comparison_or_explanation():
    trace = _trace()
    assert _components_by_action(trace) == {
        "search_web": {"policy_score": 0.5, "total_score": 0.4}
    }
    assert "no_capable_agent" in trace.explain()


def test_replay_rejects_fingerprint_whose_stored_hash_does_not_match(tmp_path):
    scenario = Scenario(label="hash-integrity")
    path = tmp_path / "case.json"
    trace = _trace()
    record(scenario, path, twin=_Twin(trace))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["expected"]["fingerprint"]["selected_action"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = replay(path, twin=_Twin(trace))

    assert not result.matched
    assert "stored fingerprint hash" in result.reason


def test_record_refuses_to_bless_an_error_trace(tmp_path):
    with pytest.raises(RuntimeError, match="cannot record a failed twin run"):
        record(Scenario(label="failed"), tmp_path / "failed.json", twin=_Twin(_trace(error="boom")))


def test_scenario_write_is_atomic(tmp_path, monkeypatch):
    path = tmp_path / "scenario.json"
    path.write_text("previous", encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        Scenario(label="new").to_json(path)
    assert path.read_text(encoding="utf-8") == "previous"


def test_example_generator_has_no_import_time_file_writes():
    generator = Path(__file__).parents[1] / "generate_example_scenarios.py"
    tree = ast.parse(generator.read_text(encoding="utf-8"))
    def called_name(call: ast.Call) -> str:
        if isinstance(call.func, ast.Name):
            return call.func.id
        if isinstance(call.func, ast.Attribute):
            return call.func.attr
        return ""

    top_level_calls = [
        node.value for node in tree.body
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
    ]
    assert not {called_name(call) for call in top_level_calls} & {"record", "mkdir", "print"}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
