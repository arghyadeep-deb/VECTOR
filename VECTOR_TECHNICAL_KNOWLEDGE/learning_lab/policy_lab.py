"""
VECTOR Digital Twin Lab — PolicyMemory sensitivity lab (Task 78 Phase 6).

Every experiment here uses the REAL `PolicyMemory.get_score()`/
`update_from_outcome()` online-averaging formula (core/memory/policy.py) —
nothing here reimplements that math; it only chooses WHAT prior experience
to feed it via Scenario.policy_updates before scoring.
"""
from __future__ import annotations

from scenario import Scenario, CandidateSpec, PolicyUpdateSpec
from experiments import run_paired, ComparisonResult

ACTION = "search_web"
PARAMS = {"q": "policy_lab_probe"}


def _base_candidate() -> CandidateSpec:
    # confidence/urgency/timing fixed and identical across every experiment
    # in this module so ONLY the policy component can move the score.
    return CandidateSpec(action_type=ACTION, params=dict(PARAMS), confidence=0.5, urgency=0.5)


def exp_increased_vs_decreased_reward():
    a = Scenario(label="policy: high reward prior", candidates=[_base_candidate()],
                 policy_updates=[PolicyUpdateSpec(ACTION, PARAMS, reward=0.95, note="one great outcome")])
    b = Scenario(label="policy: low reward prior", candidates=[_base_candidate()],
                 policy_updates=[PolicyUpdateSpec(ACTION, PARAMS, reward=0.05, note="one terrible outcome")])
    return "increased_vs_decreased_reward", a, b


def exp_no_history_vs_positive_reward():
    a = Scenario(label="policy: no history", candidates=[_base_candidate()])
    b = Scenario(label="policy: one positive reward", candidates=[_base_candidate()],
                 policy_updates=[PolicyUpdateSpec(ACTION, PARAMS, reward=0.9)])
    return "no_history_vs_positive_reward", a, b


def exp_repeated_positive_reward():
    a = Scenario(label="policy: single positive reward", candidates=[_base_candidate()],
                 policy_updates=[PolicyUpdateSpec(ACTION, PARAMS, reward=0.9)])
    b = Scenario(label="policy: five repeated positive rewards", candidates=[_base_candidate()],
                 policy_updates=[PolicyUpdateSpec(ACTION, PARAMS, reward=0.9) for _ in range(5)])
    return "repeated_positive_reward_vs_single", a, b


def exp_contradictory_rewards():
    """Online average of [0.9, 0.1] == average of two mid-range rewards —
    tests whether PolicyMemory can even represent "contradictory" evidence
    or whether it silently collapses to an indistinguishable midpoint (this
    is exactly the "unbounded cumulative average with no decay" limitation
    Task 71/72 already documented — this experiment MEASURES it, not merely
    cites it)."""
    a = Scenario(label="policy: two consistent mid rewards", candidates=[_base_candidate()],
                 policy_updates=[PolicyUpdateSpec(ACTION, PARAMS, reward=0.5),
                                  PolicyUpdateSpec(ACTION, PARAMS, reward=0.5)])
    b = Scenario(label="policy: two contradictory rewards (0.9 then 0.1)", candidates=[_base_candidate()],
                 policy_updates=[PolicyUpdateSpec(ACTION, PARAMS, reward=0.9),
                                  PolicyUpdateSpec(ACTION, PARAMS, reward=0.1)])
    return "contradictory_vs_consistent_rewards", a, b


def exp_different_action_types_isolated():
    """Reward on action X must NOT leak into action Y's policy score — proves
    PolicyMemory keys on (action_type, situation_hash), not a global signal."""
    cand_x = CandidateSpec(action_type="search_web", params={"q": "x"}, confidence=0.5, urgency=0.5)
    cand_y = CandidateSpec(action_type="check_calendar", params={}, confidence=0.5, urgency=0.5)
    a = Scenario(label="policy: no reward on either action", candidates=[cand_x, cand_y])
    b = Scenario(label="policy: reward only on search_web", candidates=[cand_x, cand_y],
                 policy_updates=[PolicyUpdateSpec("search_web", {"q": "x"}, reward=0.95)])
    return "reward_isolated_to_its_own_action_type", a, b


def exp_different_situation_same_action():
    """Same action_type, different params => different situation_hash =>
    reward must NOT transfer, since PolicyMemory keys on the (action_type,
    situation_hash) pair, not on action_type alone."""
    trained_params = {"q": "trained_on_this_query"}
    probe_params = {"q": "never_seen_this_query"}
    a = Scenario(label="policy: probe query, no history", candidates=[
        CandidateSpec(action_type=ACTION, params=probe_params, confidence=0.5, urgency=0.5)])
    b = Scenario(label="policy: probe query, but reward was on a DIFFERENT query", candidates=[
        CandidateSpec(action_type=ACTION, params=probe_params, confidence=0.5, urgency=0.5)],
        policy_updates=[PolicyUpdateSpec(ACTION, trained_params, reward=0.95)])
    return "reward_does_not_transfer_across_situation_hash", a, b


ALL_EXPERIMENTS = [
    exp_increased_vs_decreased_reward,
    exp_no_history_vs_positive_reward,
    exp_repeated_positive_reward,
    exp_contradictory_rewards,
    exp_different_action_types_isolated,
    exp_different_situation_same_action,
]


def run_all() -> list[ComparisonResult]:
    results = []
    for exp_fn in ALL_EXPERIMENTS:
        label, a, b = exp_fn()
        results.append(run_paired(label, a, b))
    return results


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    for r in run_all():
        print(r.summary())
        print()
