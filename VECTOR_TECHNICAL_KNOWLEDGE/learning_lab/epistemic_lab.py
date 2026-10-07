"""
VECTOR Digital Twin Lab — EpistemicTracker sensitivity lab (Task 78 Phase 8).

Ground truth (`core/loop/decision_engine.py::_epistemic_penalty()`, read
directly): the ONLY claim_id it ever looks up is
`f"action_domain:{action_type}"`. It never reads a
`belief:*`-namespaced key. This module PROVES that empirically (not by
citing the source) via a paired experiment, rather than assuming either
namespace matters.
"""
from __future__ import annotations

from scenario import Scenario, CandidateSpec, EpistemicBeliefSpec
from experiments import run_paired, ComparisonResult

ACTION = "search_web"
PARAMS = {"q": "epistemic_probe"}
DOMAIN_CLAIM = "action_domain:search_web"


def _candidate() -> CandidateSpec:
    return CandidateSpec(action_type=ACTION, params=dict(PARAMS), confidence=0.5, urgency=0.5)


def exp_without_vs_with_epistemic_state():
    a = Scenario(label="epistemic: none (unknown domain)", candidates=[_candidate()])
    b = Scenario(label="epistemic: action_domain belief, low confidence", candidates=[_candidate()],
                 epistemic_beliefs=[EpistemicBeliefSpec(DOMAIN_CLAIM, "last_outcome=failed",
                                                         confidence=0.15)])
    return "without_vs_with_low_confidence_action_domain_belief", a, b


def exp_low_vs_high_confidence():
    a = Scenario(label="epistemic: action_domain, low confidence (<0.3)", candidates=[_candidate()],
                 epistemic_beliefs=[EpistemicBeliefSpec(DOMAIN_CLAIM, "v", confidence=0.15)])
    b = Scenario(label="epistemic: action_domain, high confidence (>=0.5)", candidates=[_candidate()],
                 epistemic_beliefs=[EpistemicBeliefSpec(DOMAIN_CLAIM, "v", confidence=0.85)])
    return "low_vs_high_confidence_action_domain_belief", a, b


def exp_high_confidence_vs_none():
    """Does a WELL-KNOWN domain (high confidence) score any BETTER than an
    unknown one? Per _epistemic_penalty()'s own doc: high confidence -> 1.0
    (neutral), same as unknown -> 1.0 (neutral) — this experiment measures
    whether that symmetry actually holds, rather than assuming the docstring
    is accurate."""
    a = Scenario(label="epistemic: none (unknown domain)", candidates=[_candidate()])
    b = Scenario(label="epistemic: action_domain, high confidence", candidates=[_candidate()],
                 epistemic_beliefs=[EpistemicBeliefSpec(DOMAIN_CLAIM, "v", confidence=0.9)])
    return "high_confidence_vs_unknown_domain", a, b


def exp_stale_belief_penalty():
    """TTL-expired belief -> heaviest 0.70 dampening, per _epistemic_penalty()."""
    a = Scenario(label="epistemic: fresh action_domain belief", candidates=[_candidate()],
                 epistemic_beliefs=[EpistemicBeliefSpec(DOMAIN_CLAIM, "v", confidence=0.9, ttl_hours=72)])
    b = Scenario(label="epistemic: same belief but TTL-expired (stale)", candidates=[_candidate()],
                 epistemic_beliefs=[EpistemicBeliefSpec(DOMAIN_CLAIM, "v", confidence=0.9,
                                                         ttl_hours=1, age_hours_override=500)])
    return "fresh_vs_stale_action_domain_belief", a, b


def exp_belief_namespace_has_no_measured_influence():
    """The falsification test: a `belief:*` claim (the general-purpose
    EpistemicTracker namespace used elsewhere, e.g. user_name/location) must
    NOT change search_web's score at all, because _epistemic_penalty() never
    looks it up."""
    a = Scenario(label="epistemic: no belief:* claim", candidates=[_candidate()])
    b = Scenario(label="epistemic: belief:user_name claim, high confidence", candidates=[_candidate()],
                 epistemic_beliefs=[EpistemicBeliefSpec("belief:user_name", "Arghyadeep", confidence=0.95)])
    return "belief_namespace_vs_none_same_action_domain_untouched", a, b


ALL_EXPERIMENTS = [
    exp_without_vs_with_epistemic_state,
    exp_low_vs_high_confidence,
    exp_high_confidence_vs_none,
    exp_stale_belief_penalty,
    exp_belief_namespace_has_no_measured_influence,
]


def run_all() -> list[ComparisonResult]:
    results = []
    for fn in ALL_EXPERIMENTS:
        label, a, b = fn()
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
