"""
V.E.C.T.O.R. SelfEvolver.
Self-improvement engine — analyzes past decisions and evolves agent behavior.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger
from datetime import datetime
from core.config import CONFIG


class SelfEvolver:
    """
    Analyzes V.E.C.T.O.R.'s decision history to find improvement patterns.
    Uses Ollama to analyze reasoning chains and suggest behavioral changes.
    RULE 11: all analysis via Ollama (no external API).
    """

    def __init__(self):
        self._ollama_host = CONFIG["ollama_host"]
        self._reasoning_model = CONFIG["models"]["reasoning"]
        self._evolution_log: list[dict] = []
        logger.info("[VECTOR][self_evolver] SelfEvolver initialized")

    async def analyze_decision(self, decision: dict) -> dict:
        """Analyze a single decision and suggest improvements."""
        try:
            import ollama
            client = ollama.Client(host=self._ollama_host)

            prompt = f"Analyze this V.E.C.T.O.R. decision for improvements:\n\n"
            prompt += f"Action: {decision.get('action_type', 'unknown')}\n"
            prompt += f"Reasoning: {decision.get('reasoning_chain', 'N/A')[:500]}\n"
            prompt += f"Outcome: {decision.get('outcome', 'unknown')}\n"
            prompt += f"Confidence: {decision.get('confidence', 0.5)}\n\n"
            prompt += "Provide: 1) What went well, 2) What could improve, 3) Rule/policy update suggestion"

            response = client.chat(
                model=self._reasoning_model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.3, "num_predict": 600}
            )

            analysis = response["message"]["content"]
            evolution_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "decision": decision.get("action_type"),
                "analysis": analysis,
                "reward": decision.get("reward", 0.5),
            }
            self._evolution_log.append(evolution_entry)
            logger.info(f"[VECTOR][self_evolver] Decision analyzed: {decision.get('action_type')}")
            return {"analysis": analysis, "logged": True}

        except Exception as e:
            logger.error(f"[VECTOR][self_evolver] Analysis failed: {e}")
            return {"analysis": f"Analysis failed: {e}", "logged": False}

    def get_evolution_report(self) -> dict:
        """Generate an evolution report from logged decisions."""
        if not self._evolution_log:
            return {"status": "no_data", "message": "No decisions analyzed yet"}
        high_reward = [e for e in self._evolution_log if e.get("reward", 0) >= 0.7]
        low_reward = [e for e in self._evolution_log if e.get("reward", 0) < 0.4]
        return {
            "total_decisions": len(self._evolution_log),
            "high_performing": len(high_reward),
            "low_performing": len(low_reward),
            "success_rate": round(len(high_reward) / len(self._evolution_log), 2),
            "recent_insights": [e["analysis"][:200] for e in self._evolution_log[-3:]],
        }

    def suggest_policy_update(self) -> list[str]:
        """Extract policy update suggestions from evolution log."""
        suggestions = []
        for entry in self._evolution_log:
            analysis = entry.get("analysis", "")
            if "update" in analysis.lower() or "rule" in analysis.lower() or "policy" in analysis.lower():
                suggestions.append(analysis[:300])
        return suggestions


if __name__ == "__main__":
    import asyncio
    se = SelfEvolver()
    asyncio.run(se.analyze_decision({"action_type": "code_commit", "reasoning_chain": "Good test coverage", "outcome": "success", "reward": 0.8}))
    print(se.get_evolution_report())