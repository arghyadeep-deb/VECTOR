"""
VECTOR Digital Twin Lab — Level 5 (generalization) / Level 6 (correction)
research scaffolding (Task 78 Phase 15, optional).

Per Task 78: do NOT implement production generalization or correction-
learning systems here. This module does two different things:

1. `run_domain_generalization_experiment()` — a REAL, working experiment
   against EXISTING production logic. It is not a mock: it tests whether
   `DecisionEngine._epistemic_penalty()`'s exact-action bucketing
   (`action_domain:<full_action_type>`) constitutes a generalization channel
   — i.e. whether an epistemic belief formed by ONE action_type can
   measurably affect the score of a DIFFERENT action_type that happens to
   share the same domain prefix. This is legitimate because it exercises
   code that already exists; it does not add a new generalization system.

2. `CorrectionExperienceRecord` / `run_correction_provenance_probe()` — pure
   SCAFFOLDING. There is currently no production mechanism anywhere in the
   traced decision pipeline that tags an experience with WHO/WHAT produced
   it (owner correction vs ordinary automated outcome vs LLM-generated text
   vs random variation) — `PolicyMemory.update_from_outcome()` takes a bare
   `reward: float` with no provenance parameter at all, and
   `CounterfactualMemory.record_rejection()`'s `reason: str` is free text,
   not a structured, machine-checkable provenance tag. `run_correction_provenance_probe()`
   therefore does not run a real experiment — it runs the SAME reward twice
   under two different claimed provenances and demonstrates (this IS the
   finding) that the two runs are indistinguishable to PolicyMemory, because
   there is nowhere in its schema to record provenance at all. This is
   reported as a structural gap, not fixed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from scenario import Scenario, CandidateSpec, EpistemicBeliefSpec, PolicyUpdateSpec
from experiments import run_paired, ComparisonResult
from twin import DigitalTwin


# ── Level 5: does domain-level epistemic bucketing generalize? ──────────────

def run_domain_generalization_experiment() -> ComparisonResult:
    """search_web and search_arxiv share a word prefix. A belief recorded
    against action_domain:search_web should affect
    BOTH action_types' epistemic dampening if — and only if —
    _epistemic_penalty() buckets by prefix rather than by exact action type.
    Current production uses exact action types, so no movement is expected;
    the traced pipeline; PolicyMemory itself (exact situation_hash keying)
    has none (see policy_lab.exp_different_situation_same_action)."""
    probe = CandidateSpec(action_type="search_arxiv", params={"q": "generalization_probe"},
                           confidence=0.5, urgency=0.5)
    a = Scenario(label="no belief about the 'search' domain at all", candidates=[probe])
    b = Scenario(
        label="stale belief recorded against a DIFFERENT search_* action_type",
        candidates=[probe],
        epistemic_beliefs=[EpistemicBeliefSpec(
            "action_domain:search_web", "v", confidence=0.9, ttl_hours=1, age_hours_override=500,
        )],  # note: this claim_id is domain-level, never mentions search_arxiv specifically
    )
    return run_paired("epistemic_exact_action_does_not_generalize_by_prefix", a, b)


# ── Level 6: correction provenance — scaffold only, no real mechanism exists ─

@dataclass
class CorrectionExperienceRecord:
    """The shape a REAL correction-learning system would need. Nothing in
    the current codebase constructs or consumes an object like this — it is
    provided so a future Learning V2 implementation has a starting contract
    to implement against, and so this scaffold's probe can demonstrate the
    gap precisely."""
    action_type: str
    params: dict
    reward: float
    provenance: Literal["owner_correction", "ordinary_outcome", "llm_generated", "random_variation"]
    raw_text: str = ""


def run_correction_provenance_probe() -> dict:
    """Applies the SAME reward under two different claimed provenances
    (owner_correction vs random_variation) via the real
    `PolicyMemory.update_from_outcome(action_type, situation_hash, reward)`
    signature — which has no provenance parameter — and shows the resulting
    policy rows are byte-identical. This IS the finding: the current
    architecture cannot distinguish a deliberate owner correction from
    random output variation once it reaches PolicyMemory, because
    provenance is discarded (never even passed in) at the call boundary.
    A real Level-6 experiment cannot be built until a provenance field
    exists somewhere on the write path — this probe exists to make that
    gap reproducible, not to paper over it."""
    action, params = "search_web", {"q": "correction_probe"}
    owner = CorrectionExperienceRecord(action, params, reward=0.9, provenance="owner_correction",
                                        raw_text="No, use scholarly sources next time.")
    random_variation = CorrectionExperienceRecord(action, params, reward=0.9, provenance="random_variation")

    results = {}
    for rec in (owner, random_variation):
        scenario = Scenario(
            label=f"correction_probe_{rec.provenance}",
            candidates=[CandidateSpec(action_type=rec.action_type, params=rec.params, confidence=0.5, urgency=0.5)],
            # PolicyUpdateSpec has no provenance field either — mirrors the real
            # PolicyMemory.update_from_outcome() signature exactly, which is the point.
            policy_updates=[PolicyUpdateSpec(rec.action_type, rec.params, reward=rec.reward)],
        )
        trace = DigitalTwin().run(scenario)
        results[rec.provenance] = trace.candidates[0].policy_score

    return {
        "scores_by_claimed_provenance": results,
        "indistinguishable": len(set(results.values())) == 1,
        "finding": (
            "PolicyMemory.update_from_outcome(action_type, situation_hash, reward) has no "
            "provenance parameter. An owner's deliberate correction and an arbitrary reward "
            "labeled 'random_variation' produce IDENTICAL policy state — provenance is lost "
            "before it ever reaches persistent storage. A real Level-6 correction-learning "
            "experiment requires this gap to be closed first (see 78_DIGITAL_TWIN_LAB.md "
            "§20 post-experiment recommendations)."
        ),
    }


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    print(run_domain_generalization_experiment().summary())
    print()
    probe = run_correction_provenance_probe()
    print("scores by claimed provenance:", probe["scores_by_claimed_provenance"])
    print("indistinguishable:", probe["indistinguishable"])
    print(probe["finding"])
