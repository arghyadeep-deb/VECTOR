"""Generate the recorded example scenarios referenced by the lab design."""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from replay import record
from scenario import CandidateSpec, CounterfactualRejectionSpec, PolicyUpdateSpec, Scenario


OUT = Path(__file__).resolve().parent / "scenarios"


def main() -> int:
    """Regenerate all fixtures and return the resulting fixture count."""
    OUT.mkdir(exist_ok=True)
    record(Scenario(label="auto_seeded_goals_baseline", candidates="auto"),
           OUT / "scenario_001_auto_seeded_goals.json")
    record(Scenario(label="close_race", candidates=[
        CandidateSpec("search_web", {"q": "l4t"}, confidence=0.60, urgency=0.5),
        CandidateSpec("check_calendar", {}, confidence=0.62, urgency=0.5),
    ]), OUT / "scenario_002_close_race.json")
    record(Scenario(
        label="counterfactual_veto_demo",
        candidates=[CandidateSpec("delete_logs", {"target": "all"}, confidence=0.9, urgency=0.5)],
        counterfactual_rejections=[CounterfactualRejectionSpec(
            proposal='delete_logs {"target": "all"}', reason="Too destructive — irreversible",
        )],
    ), OUT / "scenario_003_counterfactual_veto.json")
    record(Scenario(
        label="policy_influenced",
        candidates=[
            CandidateSpec("search_web", {"q": "policy_demo"}, confidence=0.5, urgency=0.5),
            CandidateSpec("check_calendar", {}, confidence=0.5, urgency=0.5),
        ],
        policy_updates=[PolicyUpdateSpec("search_web", {"q": "policy_demo"}, reward=0.95)],
    ), OUT / "scenario_004_policy_influenced.json")

    count = len(list(OUT.glob("scenario_*.json")))
    logger.info("[VECTOR][learning_lab] wrote {} scenario fixtures to {}", count, OUT)
    return count


if __name__ == "__main__":
    main()
