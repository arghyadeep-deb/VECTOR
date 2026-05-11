"""
V.E.C.T.O.R. CounterfactualMemory.
Stores "what if" scenarios — hypothetical alternatives V.E.C.T.O.R. considered but didn't choose.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger
import uuid
from datetime import datetime


class CounterfactualMemory:
    """
    Stores hypothetical scenarios: 'What if I had done X instead of Y?'
    Used for self-improvement and learning from missed opportunities.
    """

    def __init__(self):
        self._scenarios: dict[str, dict] = {}
        logger.info("[VECTOR][counterfactual] CounterfactualMemory initialized")

    def record_scenario(
        self,
        original_action: str,
        chosen_reason: str,
        alternative: str,
        alternative_outcome: str,
        context: dict | None = None,
    ) -> dict:
        """Record a counterfactual scenario."""
        scenario = {
            "id": str(uuid.uuid4()),
            "original_action": original_action,
            "chosen_reason": chosen_reason,
            "alternative": alternative,
            "alternative_outcome": alternative_outcome,
            "context": context or {},
            "created_at": datetime.utcnow().isoformat(),
            "useful": None,
        }
        self._scenarios[scenario["id"]] = scenario
        logger.info(f"[VECTOR][counterfactual] Scenario recorded: {original_action} vs {alternative}")
        return scenario

    def mark_useful(self, scenario_id: str, useful: bool, reason: str = ""):
        """Mark a counterfactual scenario as useful for learning."""
        if scenario_id in self._scenarios:
            self._scenarios[scenario_id]["useful"] = useful
            self._scenarios[scenario_id]["feedback_reason"] = reason
            logger.info(f"[VECTOR][counterfactual] Scenario {scenario_id} marked {'useful' if useful else 'not useful'}: {reason}")

    def get_similar(self, action: str, limit: int = 5) -> list[dict]:
        """Get similar counterfactual scenarios."""
        results = [
            s for s in self._scenarios.values()
            if action.lower() in s["original_action"].lower()
        ]
        return results[:limit]

    def get_insights(self) -> list[str]:
        """Generate insights from counterfactual patterns."""
        useful = [s for s in self._scenarios.values() if s.get("useful") is True]
        insights = []
        for s in useful:
            insights.append(
                f"When considering '{s['original_action']}', "
                f"alternative '{s['alternative']}' was better ({s.get('feedback_reason', '')})"
            )
        return insights


if __name__ == "__main__":
    cf = CounterfactualMemory()
    cf.record_scenario(
        "Used linear search",
        "Simpler code",
        "Used binary search",
        "10x faster but more complex",
        {"dataset_size": 10000},
    )
    print(cf.get_insights())