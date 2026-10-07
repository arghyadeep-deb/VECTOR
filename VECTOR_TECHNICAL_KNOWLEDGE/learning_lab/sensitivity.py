"""
VECTOR Digital Twin Lab — decision sensitivity analysis (Task 78 Phase 12).

Systematically toggles ONE factor at a time (holding everything else fixed)
and reports Δscore, to identify which mechanisms are genuinely
decision-critical in the REAL 5-factor formula
(core/loop/decision_engine.py DecisionEngine.W_GOAL..W_COST) versus which
ones are wired in but structurally inert for a given scenario shape.
"""
from __future__ import annotations

from dataclasses import dataclass

from scenario import Scenario, CandidateSpec, PolicyUpdateSpec, CounterfactualRejectionSpec, EpistemicBeliefSpec
from twin import DigitalTwin

ACTION = "search_web"
PARAMS = {"q": "sensitivity_probe"}


@dataclass
class FactorSensitivity:
    factor: str
    weight_in_formula: str
    score_low: float
    score_high: float
    delta: float
    is_decision_critical: bool  # |delta| > 0.02 chosen as a non-trivial-movement threshold
    note: str = ""


def _run(spec: CandidateSpec, **scenario_kwargs) -> float:
    trace = DigitalTwin().run(Scenario(label="sensitivity_probe", candidates=[spec], **scenario_kwargs))
    return trace.candidates[0].total_score


def analyze_confidence() -> FactorSensitivity:
    low = _run(CandidateSpec(ACTION, PARAMS, confidence=0.1, urgency=0.5))
    high = _run(CandidateSpec(ACTION, PARAMS, confidence=0.95, urgency=0.5))
    return _mk("confidence", "W_CONF=0.25 (direct candidate field)", low, high)


def analyze_urgency() -> FactorSensitivity:
    low = _run(CandidateSpec(ACTION, PARAMS, confidence=0.5, urgency=0.05))
    high = _run(CandidateSpec(ACTION, PARAMS, confidence=0.5, urgency=0.95))
    return _mk("urgency", "W_URGENCY=0.15 (direct candidate field)", low, high)


def analyze_timing_score() -> FactorSensitivity:
    low = _run(CandidateSpec(ACTION, PARAMS, confidence=0.5, urgency=0.5, timing_score=0.0))
    high = _run(CandidateSpec(ACTION, PARAMS, confidence=0.5, urgency=0.5, timing_score=1.0))
    return _mk("timing_score", "W_TIMING=0.10 (direct candidate field)", low, high)


def analyze_estimated_cost() -> FactorSensitivity:
    low = _run(CandidateSpec(ACTION, PARAMS, confidence=0.5, urgency=0.5, estimated_cost_inr=0.0))
    high = _run(CandidateSpec(ACTION, PARAMS, confidence=0.5, urgency=0.5, estimated_cost_inr=10.0))
    return _mk("estimated_cost_inr", "-W_COST=0.05 (penalty, capped at cost/10)", low, high)


def analyze_goal_alignment() -> FactorSensitivity:
    low = _run(CandidateSpec(ACTION, PARAMS, confidence=0.5, urgency=0.5, goal_ids=[]))
    high = _run(CandidateSpec(ACTION, PARAMS, confidence=0.5, urgency=0.5, goal_ids=["g_daily_commit"]),
                goals=None)  # real seeded goals include g_daily_commit at priority 7, progress 0.0
    return _mk("goal_alignment", "W_GOAL=0.30 (via GoalSystem.get_active_goals())", low, high,
               note="'low' has no goal_ids -> fixed 0.3 floor per _score_goal_alignment(); "
                    "'high' targets a real active goal.")


def analyze_policy_history() -> FactorSensitivity:
    low = _run(CandidateSpec(ACTION, PARAMS, confidence=0.5, urgency=0.5))  # fresh DB, DEFAULT_SCORE=0.5
    high = _run(CandidateSpec(ACTION, PARAMS, confidence=0.5, urgency=0.5),
                policy_updates=[PolicyUpdateSpec(ACTION, PARAMS, reward=0.98)])
    return _mk("policy_score", "W_POLICY=0.20 (via PolicyMemory.get_score())", low, high)


def analyze_epistemic_state() -> FactorSensitivity:
    low = _run(CandidateSpec(ACTION, PARAMS, confidence=0.5, urgency=0.5))  # unknown domain -> factor 1.0
    high = _run(CandidateSpec(ACTION, PARAMS, confidence=0.5, urgency=0.5),
                epistemic_beliefs=[EpistemicBeliefSpec("action_domain:search_web", "v", confidence=0.9,
                                                        ttl_hours=1, age_hours_override=500)])  # stale -> 0.70x
    return _mk("epistemic_factor", "post-score multiplier in [0.70, 1.0]", low, high,
               note="'high' here means MOST dampened (stale belief), since epistemic state can only "
                    "ever reduce the score, never increase it above the undampened baseline.")


def analyze_counterfactual_state() -> FactorSensitivity:
    """Expected to show delta == 0.0 EXACTLY — proves (does not merely
    claim) that counterfactual state is not a scoring input at all."""
    low = _run(CandidateSpec(ACTION, PARAMS, confidence=0.5, urgency=0.5))
    high = _run(CandidateSpec(ACTION, PARAMS, confidence=0.5, urgency=0.5),
                counterfactual_rejections=[CounterfactualRejectionSpec(
                    proposal=f"{ACTION} {PARAMS}", reason="rejected")])
    return _mk("counterfactual_state", "NOT part of the score formula (post-hoc veto only)", low, high,
               note="A non-zero delta here would be a genuine, surprising discovery — see report.")


def analyze_memory_recall() -> FactorSensitivity:
    """EpisodicMemory has no read path anywhere in DecisionEngine's scoring
    at all (only a WRITE, logging every candidate) — expected delta 0.0."""
    low = _run(CandidateSpec(ACTION, PARAMS, confidence=0.5, urgency=0.5))
    high = _run(CandidateSpec(ACTION, PARAMS, confidence=0.5, urgency=0.5))  # nothing to vary — see note
    return _mk("episodic_memory_recall", "NOT read anywhere in _score_candidate()", low, high,
               note="No experiment varies this because there is no read path to vary — "
                    "EpisodicMemory.store() is write-only from DecisionEngine's perspective.")


def _mk(factor, weight, low, high, note="") -> FactorSensitivity:
    delta = high - low
    return FactorSensitivity(factor, weight, low, high, delta, abs(delta) > 0.02, note)


ALL_FACTORS = [
    analyze_confidence, analyze_urgency, analyze_timing_score, analyze_estimated_cost,
    analyze_goal_alignment, analyze_policy_history, analyze_epistemic_state,
    analyze_counterfactual_state, analyze_memory_recall,
]


def run_all() -> list[FactorSensitivity]:
    return [fn() for fn in ALL_FACTORS]


def report(results: list[FactorSensitivity]) -> str:
    lines = ["DECISION SENSITIVITY REPORT", "=" * 60]
    for r in sorted(results, key=lambda r: abs(r.delta), reverse=True):
        crit = "CRITICAL" if r.is_decision_critical else "negligible"
        lines.append(f"{r.factor:24} Δ={r.delta:+.4f}  [{crit}]  ({r.weight_in_formula})")
        if r.note:
            lines.append(f"{'':24} note: {r.note}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    print(report(run_all()))
