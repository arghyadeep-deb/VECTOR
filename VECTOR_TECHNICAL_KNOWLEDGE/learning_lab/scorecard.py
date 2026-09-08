"""
VECTOR Digital Twin Lab — automated Level 0-7 scorecard (Task 78 Phase 16).

Every verdict here is DERIVED from an actual experiment run in this
process — nothing is hardcoded. A database row changing is never, by
itself, sufficient for a PASS above Level 0/1 (Task 78's explicit
instruction).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from scenario import Scenario, CandidateSpec, PolicyUpdateSpec
from twin import DigitalTwin, make_situation_hash
from isolation import IsolatedVectorEnv
from level4_experiment import run_level4_experiment


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_TESTED = "NOT_TESTED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class LevelResult:
    level: int
    name: str
    verdict: Verdict
    evidence: str


def _level_0_1_2_storage_retrieval_influence() -> tuple[LevelResult, LevelResult, LevelResult]:
    """One shared probe answers all three: write a reward, read the row
    back directly (0/1), then confirm it moves a real score (2)."""
    action, params = "search_web", {"q": "scorecard_probe"}
    sit_hash = make_situation_hash(action, params)

    with IsolatedVectorEnv() as env:
        from twin import build_isolated_engine
        engine = build_isolated_engine(env)
        from core.memory.episodic import get_temp_cursor

        with get_temp_cursor() as cur:
            before = cur.execute(
                "SELECT COUNT(*) FROM policy_memory WHERE action_type=? AND situation_hash=?",
                (action, sit_hash),
            ).fetchone()[0]
        score_before = engine._policy.get_score(action, sit_hash)

        engine._policy.update_from_outcome(action, sit_hash, reward=0.93)

        with get_temp_cursor() as cur:
            after = cur.execute(
                "SELECT COUNT(*) FROM policy_memory WHERE action_type=? AND situation_hash=?",
                (action, sit_hash),
            ).fetchone()[0]
        score_after = engine._policy.get_score(action, sit_hash)

    storage = LevelResult(0, "STORAGE", Verdict.PASS if after > before else Verdict.FAIL,
                           f"policy_memory row count {before} -> {after} after update_from_outcome()")
    retrieval = LevelResult(1, "RETRIEVAL", Verdict.PASS if score_after != score_before else Verdict.FAIL,
                             f"get_score() returned {score_before} before, {score_after} after")

    from sensitivity import analyze_policy_history
    sens = analyze_policy_history()
    influence = LevelResult(
        2, "INFLUENCE",
        Verdict.PASS if sens.is_decision_critical else Verdict.FAIL,
        f"score with no history={sens.score_low:.4f}, with strong positive history={sens.score_high:.4f}, "
        f"Δ={sens.delta:+.4f}",
    )
    return storage, retrieval, influence


def _level_3_persistence() -> LevelResult:
    from controls import control_5_restart_between_learning_and_recall
    outcome = control_5_restart_between_learning_and_recall()
    return LevelResult(
        3, "PERSISTENT STATE",
        Verdict.PASS if outcome.ranking_changed else Verdict.FAIL,
        outcome.explanation,
    )


def _level_4_behavioral_adaptation() -> LevelResult:
    scenario = Scenario(label="scorecard_level4", candidates=[
        CandidateSpec(action_type="search_web", params={"q": "scorecard4"}, confidence=0.60, urgency=0.5),
        CandidateSpec(action_type="check_calendar", params={}, confidence=0.62, urgency=0.5),
    ])
    result = run_level4_experiment("scorecard_level4", scenario, "search_web", {"q": "scorecard4"},
                                    outcome_reward=0.98)
    verdict_str = result.evidence.verdict()
    if verdict_str.startswith("PASS"):
        v = Verdict.PASS
    elif verdict_str.startswith("INCONCLUSIVE"):
        v = Verdict.INCONCLUSIVE
    else:
        v = Verdict.FAIL
    return LevelResult(4, "BEHAVIORAL ADAPTATION", v, verdict_str)


def _level_5_generalization() -> LevelResult:
    from scaffold_l5_l6 import run_domain_generalization_experiment
    result = run_domain_generalization_experiment()
    moved = any(d.delta and abs(d.delta) > 1e-9 for d in result.score_deltas)
    if moved:
        return LevelResult(5, "GENERALIZATION", Verdict.PASS,
                            "A belief recorded on the shared 'search' domain measurably changed "
                            "search_arxiv's score even though the belief was never recorded "
                            "against search_arxiv specifically — a real (narrow, domain-prefix-"
                            "only) generalization channel exists via epistemic dampening.")
    return LevelResult(5, "GENERALIZATION", Verdict.FAIL,
                        "No measured cross-action-type score movement — no generalization "
                        "channel is currently active for this scenario shape.")


def _level_6_correction() -> LevelResult:
    from scaffold_l5_l6 import run_correction_provenance_probe
    probe = run_correction_provenance_probe()
    return LevelResult(6, "CORRECTION", Verdict.NOT_IMPLEMENTED, probe["finding"])


def _level_7_meta_learning() -> LevelResult:
    return LevelResult(
        7, "META-LEARNING", Verdict.NOT_IMPLEMENTED,
        "No experiment was built — every traced learning parameter (PolicyMemory's plain "
        "online average with no decay, EpistemicTracker's fixed CONFIG-sourced decay_rate, "
        "CounterfactualMemory's fixed decay_days) is a static constant, never itself adjusted "
        "based on accumulated experience. There is no meta-parameter anywhere in the traced "
        "pipeline for a meta-learning experiment to even target.",
    )


def run_scorecard() -> list[LevelResult]:
    storage, retrieval, influence = _level_0_1_2_storage_retrieval_influence()
    return [
        storage, retrieval, influence,
        _level_3_persistence(),
        _level_4_behavioral_adaptation(),
        _level_5_generalization(),
        _level_6_correction(),
        _level_7_meta_learning(),
    ]


def report(results: list[LevelResult]) -> str:
    lines = ["VECTOR DIGITAL TWIN LAB — LEVEL 0-7 SCORECARD", "=" * 60]
    for r in results:
        lines.append(f"LEVEL {r.level} — {r.name:24} {r.verdict.value}")
        lines.append(f"          {r.evidence}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    print(report(run_scorecard()))
