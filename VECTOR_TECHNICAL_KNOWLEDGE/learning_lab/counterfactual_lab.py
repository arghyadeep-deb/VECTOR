"""
VECTOR Digital Twin Lab — CounterfactualMemory sensitivity lab (Task 78 Phase 7).

Ground truth established in twin.py's dependency map (re-derived directly
from source, not assumed from Task 71/72): `CounterfactualMemory.should_avoid()`
is NEVER consulted inside `DecisionEngine.evaluate()`/`_score_candidate()`.
It is checked in `autonomous_loop.py:1090-1126` AFTER a winner is already
selected — a post-hoc veto, not a scoring input, faithfully reproduced here
as `twin.counterfactual_veto()`.

That means: candidate RANKING is, by construction, unaffected by
counterfactual state (there is nothing to measure there — see
`exp_veto_does_not_change_ranking` below, which proves this rather than
asserting it). What counterfactual state CAN do is:
  (a) directly block a specific already-selected action from being taken
      this cycle (a veto, not a re-ranking), and
  (b) INDIRECTLY reshape future ranking, because a veto also forces a
      hardcoded reward=0.05 PolicyMemory penalty
      (autonomous_loop.py:1115) — this is the one real, closed feedback
      path from "past rejection" to "future candidate selection", and this
      module measures it explicitly rather than assuming it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from scenario import Scenario, CandidateSpec, CounterfactualRejectionSpec
from twin import DigitalTwin

ACTION = "delete_logs"
PARAMS = {"target": "all"}
# MUST match twin.counterfactual_veto()'s exact proposal format
# (f"{action_type} {json.dumps(params, default=str)}") — a hand-typed
# Python-repr string like "{'target': 'all'}" tokenizes differently from
# json.dumps's "{\"target\": \"all\"}" under the real _jaccard() similarity
# check and silently fails to match (caught by this module's own test suite).
_PROPOSAL = f"{ACTION} {json.dumps(PARAMS, default=str)}"


def _candidate() -> CandidateSpec:
    return CandidateSpec(action_type=ACTION, params=dict(PARAMS), confidence=0.9, urgency=0.5)


@dataclass
class VetoProbe:
    label: str
    vetoed: bool
    veto_reason: str
    winner: str | None
    winner_score: float | None


def _probe(label: str, rejections: list[CounterfactualRejectionSpec]) -> VetoProbe:
    scenario = Scenario(label=label, candidates=[_candidate()],
                         counterfactual_rejections=rejections)
    trace = DigitalTwin().run(scenario)
    return VetoProbe(label, trace.counterfactual_vetoed, trace.veto_reason,
                      trace.selected_action, trace.winner_score())


def exp_no_rejection() -> VetoProbe:
    return _probe("no_rejection", [])


def exp_one_matching_rejection() -> VetoProbe:
    return _probe("one_matching_rejection", [
        CounterfactualRejectionSpec(proposal=_PROPOSAL,
                                     reason="Too destructive — irreversible")
    ])


def exp_repeated_matching_rejection() -> VetoProbe:
    return _probe("repeated_matching_rejection", [
        CounterfactualRejectionSpec(proposal=_PROPOSAL, reason="rejected #1"),
        CounterfactualRejectionSpec(proposal=_PROPOSAL, reason="rejected #2"),
        CounterfactualRejectionSpec(proposal=_PROPOSAL, reason="rejected #3"),
    ])


def exp_old_rejection_decays() -> VetoProbe:
    """T4 staleness decay: a rejection ~50 days old (decay_days default 7 ->
    ~7 half-lives) should have decayed similarity well under the 0.7 veto
    threshold, unlike a fresh one — this is the "candidate recovery"
    experiment the task asks for, using the REAL `_decay_factor()` math."""
    return _probe("old_rejection_decays", [
        CounterfactualRejectionSpec(proposal=_PROPOSAL,
                                     reason="rejected long ago", created_at_days_ago=50.0)
    ])


def exp_recent_rejection_blocks() -> VetoProbe:
    return _probe("recent_rejection_blocks", [
        CounterfactualRejectionSpec(proposal=_PROPOSAL,
                                     reason="rejected moments ago", created_at_days_ago=0.01)
    ])


def exp_unrelated_rejection_does_not_block() -> VetoProbe:
    """Candidate suppression must be similarity-scoped, not global — an
    unrelated past rejection must not veto an unrelated action."""
    return _probe("unrelated_rejection_does_not_block", [
        CounterfactualRejectionSpec(proposal="post_to_twitter {'text': 'hello'}",
                                     reason="owner said never post automatically")
    ])


def exp_veto_does_not_change_ranking():
    """Direct proof (not assumption) that counterfactual state never alters
    candidate SCORES/ranking — only whether the already-ranked winner is
    allowed to execute. Runs the SAME two-candidate scenario with
    apply_counterfactual_veto True vs False and diffs the score components."""
    from experiments import run_paired
    cands = [_candidate(), CandidateSpec(action_type="search_web", params={"q": "safe"}, confidence=0.4, urgency=0.4)]
    rejections = [CounterfactualRejectionSpec(proposal=_PROPOSAL, reason="blocked")]
    a = Scenario(label="veto disabled", candidates=cands, counterfactual_rejections=rejections,
                 apply_counterfactual_veto=False)
    b = Scenario(label="veto enabled", candidates=cands, counterfactual_rejections=rejections,
                 apply_counterfactual_veto=True)
    result = run_paired("veto_toggle_does_not_change_scores_or_ranking", a, b)
    score_moved = any(d.delta and abs(d.delta) > 1e-9 for d in result.score_deltas)
    return result, score_moved


def exp_indirect_policy_penalty_reshapes_future_ranking():
    """The ONE real closed loop: repeatedly veto the same action across N
    independent cycles (each cycle's forced reward=0.05 lands in the SAME
    isolated PolicyMemory because we share one IsolatedVectorEnv/engine
    across cycles) and show the action's OWN future policy_score falling,
    then compare its ranking against a never-vetoed rival candidate."""
    from isolation import IsolatedVectorEnv
    from twin import DigitalTwin, build_isolated_engine, build_isolated_counterfactual, counterfactual_veto, \
        _apply_counterfactual_rejections
    from core.loop.decision_engine import Candidate
    import asyncio

    rival = CandidateSpec(action_type="search_web", params={"q": "safe"}, confidence=0.5, urgency=0.5)
    seed_rejection = [CounterfactualRejectionSpec(proposal=_PROPOSAL, reason="blocked-seed")]

    winner_scores: list[float] = []
    rival_scores: list[float] = []
    with IsolatedVectorEnv() as env:
        engine = build_isolated_engine(env)
        cf = build_isolated_counterfactual(env)
        _apply_counterfactual_rejections(cf, seed_rejection)
        for cycle in range(5):
            candidates = [Candidate(ACTION, dict(PARAMS), confidence=0.9, urgency=0.5),
                          Candidate(rival.action_type, dict(rival.params), confidence=0.5, urgency=0.5)]
            decision = asyncio.run(engine.evaluate(candidates))
            by_type = {c.action_type: c.total_score for c in decision.all_candidates}
            winner_scores.append(by_type.get(ACTION, 0.0))
            rival_scores.append(by_type.get(rival.action_type, 0.0))
            if decision.winner.action_type == ACTION:
                veto = counterfactual_veto(cf, decision.winner.action_type, decision.winner.params)
                if veto.vetoed:
                    import hashlib
                    sit_hash = hashlib.sha256(
                        f"{ACTION}:{sorted(PARAMS.items())}".encode()
                    ).hexdigest()[:12]
                    engine._policy.update_from_outcome(ACTION, sit_hash, reward=0.05)
    return {"winner_scores_per_cycle": winner_scores, "rival_scores_per_cycle": rival_scores}


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    for fn in (exp_no_rejection, exp_one_matching_rejection, exp_repeated_matching_rejection,
               exp_old_rejection_decays, exp_recent_rejection_blocks,
               exp_unrelated_rejection_does_not_block):
        p = fn()
        print(f"{p.label:40} vetoed={p.vetoed!s:5} reason={p.veto_reason[:40]!r}")
    result, moved = exp_veto_does_not_change_ranking()
    print("\nveto toggle changed any score component?", moved)
    print(exp_indirect_policy_penalty_reshapes_future_ranking())
