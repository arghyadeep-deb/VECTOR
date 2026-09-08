"""
VECTOR Digital Twin Lab — Level-4 behavioral-adaptation experiment (Task 78 Phase 9).

This is the central experiment the whole lab exists to support. It refuses
to declare "learning" merely because a value changed. It requires evidence
along the FULL causal chain:

    EXPERIENCE -> STATE CHANGE -> PERSISTENCE -> RETRIEVAL
                -> DECISION INFLUENCE -> BEHAVIORAL CHANGE

and it separates that from ordinary confounds using an explicit,
built-in no-learning CONTROL run (same situation, same restart, but the
learning update is skipped) — see `Level4Result.control_run` below. Full
extra confound controls (unrelated memory, different situation, time
passage, contradictory experience, ...) live in `controls.py` and reuse
this module's primitives.

DESIGN CONSTRAINT (must be documented, not hidden): "behavioral change" can
only be MEASURED when the scenario has >= 2 competing candidates whose
scores are close enough that a policy-score shift can plausibly flip the
ranking. A single-candidate scenario can prove influence up through Level 3
(persistent state change reaches the score formula) but Level 4 specifically
("did the WINNER change") is structurally untestable with one candidate —
this module raises rather than silently reporting a false Level-4 PASS in
that case.
"""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field

from isolation import IsolatedVectorEnv
from scenario import Scenario, CandidateSpec
from trace import DecisionTrace
from twin import DigitalTwin, build_isolated_engine


def _situation_hash(action_type: str, params: dict) -> str:
    return hashlib.sha256(f"{action_type}:{sorted(params.items())}".encode()).hexdigest()[:12]


@dataclass
class CausalChainEvidence:
    experience_applied: bool
    state_changed: bool                 # policy_memory row's avg_reward/sample_count actually changed
    state_before: dict
    state_after: dict
    persisted_across_restart: bool      # row survives a real close+reopen of the isolated DB
    state_after_restart: dict
    retrieved_on_recall: bool           # D2's candidate.policy_score reflects the updated row
    decision_input_changed: bool        # the "policy_score" score component actually differs D1 vs D2
    decision_score_delta: float | None
    ranking_changed: bool               # winner differs D1 vs D2 in the LEARNING run
    control_ranking_changed: bool       # winner differs D1 vs D2 in the NO-LEARNING control run
    caused_by_learned_state: bool       # ranking_changed AND NOT control_ranking_changed

    def verdict(self) -> str:
        if not self.experience_applied:
            return "NOT TESTED — experience was never applied"
        if not self.state_changed:
            return "FAIL at STATE CHANGE — experience was applied but no state row changed"
        if not self.persisted_across_restart:
            return "FAIL at PERSISTENCE — state changed but did not survive a DB close+reopen"
        if not self.retrieved_on_recall:
            return "FAIL at RETRIEVAL — persisted state was not read back into the next decision"
        if not self.decision_input_changed:
            return "FAIL at DECISION INFLUENCE — retrieved state did not change any score component"
        if not self.ranking_changed:
            return ("INCONCLUSIVE at BEHAVIORAL CHANGE — score component moved but the winner "
                    "did not change (state accumulation without adaptation)")
        if self.control_ranking_changed:
            return ("FAIL at CAUSATION — winner changed, but the no-learning CONTROL run's winner "
                    "ALSO changed, so the change is not attributable to the learned state")
        return "PASS — full causal chain demonstrated: experience caused a persistent, retrieved, decision-changing, winner-flipping behavioral change"


@dataclass
class Level4Result:
    label: str
    situation: Scenario
    run1: DecisionTrace              # before learning
    run2: DecisionTrace              # after learning, same env (real persistence)
    control_run1: DecisionTrace      # independent env, no learning applied, run 1
    control_run2: DecisionTrace      # independent env, no learning applied, run 2 (persistence no-op)
    evidence: CausalChainEvidence

    @property
    def control_run(self):
        return self.control_run2


def _run_pair_in_shared_env(scenario: Scenario, action_type: str, params: dict,
                             reward: float | None) -> tuple[DecisionTrace, DecisionTrace, CausalChainEvidence]:
    """Run the same scenario TWICE against ONE isolated env, with a real
    close+reopen of the SQLite connection between the two runs (genuine
    restart semantics, not a simulation — see isolation.py). If `reward` is
    None, this is the no-learning control: nothing is written between runs."""
    twin = DigitalTwin()
    sit_hash = _situation_hash(action_type, params)

    with IsolatedVectorEnv() as env:
        engine1 = build_isolated_engine(env)
        state_before = _read_policy_row(engine1, action_type, sit_hash)
        run1 = twin.run_in_env(env, scenario)

        state_after = state_before
        persisted = True
        if reward is not None:
            engine1._policy.update_from_outcome(action_type, sit_hash, reward)
            state_after = _read_policy_row(engine1, action_type, sit_hash)

        # Genuine restart: close the singleton connection, then reopen it
        # against the SAME on-disk file (same env.paths, same run_id) — this
        # is real cross-restart persistence, not a mock.
        import core.memory.episodic as ep
        ep.close_db_connection()

    with IsolatedVectorEnv(run_id=env.run_id, base_dir=env.paths.root) as env2:
        engine2 = build_isolated_engine(env2)
        state_after_restart = _read_policy_row(engine2, action_type, sit_hash)
        persisted = (reward is None) or (state_after_restart == state_after and state_after != state_before)
        run2 = twin.run_in_env(env2, scenario)

    return run1, run2, _partial_evidence(reward, state_before, state_after, state_after_restart, persisted)


def _read_policy_row(engine, action_type: str, situation_hash: str) -> dict:
    from core.memory.episodic import get_temp_cursor
    with get_temp_cursor() as cursor:
        row = cursor.execute(
            "SELECT avg_reward, sample_count FROM policy_memory WHERE action_type=? AND situation_hash=?",
            (action_type, situation_hash),
        ).fetchone()
    return {"avg_reward": row[0], "sample_count": row[1]} if row else {}


def _partial_evidence(reward, before, after, after_restart, persisted) -> CausalChainEvidence:
    return CausalChainEvidence(
        experience_applied=reward is not None,
        state_changed=(reward is not None and after != before),
        state_before=before, state_after=after,
        persisted_across_restart=persisted,
        state_after_restart=after_restart,
        retrieved_on_recall=False, decision_input_changed=False, decision_score_delta=None,
        ranking_changed=False, control_ranking_changed=False, caused_by_learned_state=False,
    )


def run_level4_experiment(label: str, scenario: Scenario, learned_action_type: str,
                            learned_params: dict, outcome_reward: float) -> Level4Result:
    """The full experiment. `scenario` MUST contain >= 2 candidates (see
    module docstring) for the Level-4 "did the winner change" check to be
    meaningful; a ValueError is raised otherwise so a misconfigured
    experiment fails loudly instead of silently reporting FAIL."""
    if scenario.candidates == "auto" or len(scenario.candidates) < 2:
        raise ValueError(
            "Level-4 experiments require an explicit scenario with >= 2 competing "
            "candidates — a single-candidate (or 'auto') scenario cannot measure "
            "whether learned state changes the WINNER, only whether it changes a score."
        )

    run1, run2, evidence = _run_pair_in_shared_env(scenario, learned_action_type, learned_params, outcome_reward)
    control1, control2, _ = _run_pair_in_shared_env(scenario, learned_action_type, learned_params, None)

    # RETRIEVAL + DECISION INFLUENCE — compare the learned action's policy_score
    # score component between run1 and run2.
    def _policy_component(trace: DecisionTrace, action_type: str) -> float | None:
        for c in trace.candidates:
            if c.action_type == action_type:
                for comp in c.score_components:
                    if comp["factor"] == "policy_score":
                        return comp["value"]
        return None

    p1 = _policy_component(run1, learned_action_type)
    p2 = _policy_component(run2, learned_action_type)
    retrieved = (p2 is not None and p2 != 0.5) or (p1 != p2 if p1 is not None and p2 is not None else False)
    decision_input_changed = (p1 is not None and p2 is not None and abs(p1 - p2) > 1e-9)
    delta = (p2 - p1) if decision_input_changed else None

    ranking_changed = run1.selected_action != run2.selected_action
    control_ranking_changed = control1.selected_action != control2.selected_action

    evidence.retrieved_on_recall = bool(retrieved)
    evidence.decision_input_changed = bool(decision_input_changed)
    evidence.decision_score_delta = delta
    evidence.ranking_changed = bool(ranking_changed)
    evidence.control_ranking_changed = bool(control_ranking_changed)
    evidence.caused_by_learned_state = bool(ranking_changed and not control_ranking_changed)

    return Level4Result(label=label, situation=scenario, run1=run1, run2=run2,
                         control_run1=control1, control_run2=control2, evidence=evidence)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    # A deliberately CLOSE two-candidate race so a real reward is capable of
    # flipping the winner — a landslide scenario would prove nothing.
    scenario = Scenario(
        label="level4_close_race",
        candidates=[
            CandidateSpec(action_type="search_web", params={"q": "level4"}, confidence=0.60, urgency=0.5),
            CandidateSpec(action_type="check_calendar", params={}, confidence=0.62, urgency=0.5),
        ],
    )
    result = run_level4_experiment(
        "search_web_learns_from_great_outcome", scenario,
        learned_action_type="search_web", learned_params={"q": "level4"}, outcome_reward=0.98,
    )
    print("run1 winner:", result.run1.selected_action, result.run1.winner_score())
    print("run2 winner:", result.run2.selected_action, result.run2.winner_score())
    print("control1 winner:", result.control_run1.selected_action)
    print("control2 winner:", result.control_run2.selected_action)
    print()
    print("VERDICT:", result.evidence.verdict())
