"""
V.E.C.T.O.R. RedTeamAgent.
Adversarial testing agent — finds weaknesses before they cause problems.
"""
from loguru import logger
from datetime import datetime
from core.config import CONFIG


class RedTeamAgent:
    """
    Plays devil's advocate: finds flaws in V.E.C.T.O.R.'s plans, decisions,
    and policies before they are executed. Strengthens the system through
    adversarial thinking.
    """

    def __init__(self):
        self._ollama_host = CONFIG["ollama_host"]
        self._red_model = CONFIG["models"]["reasoning"]
        self._attack_log: list[dict] = []
        logger.info("[VECTOR][red_team] RedTeamAgent initialized")

    async def attack_plan(self, plan: str, context: str = "") -> dict:
        """
        Attack a plan from multiple angles: safety, logic, resource, timing.
        Returns {vulnerabilities: [...], severity: dict, recommendations: [...]]
        """
        try:
            import ollama
            client = ollama.Client(host=self._ollama_host)

            prompt = f"You are a red team agent. Attack this V.E.C.T.O.R. plan:\n\nPlan: {plan}\n\nContext: {context}\n\n"
            prompt += "For each vulnerability, specify: type (safety/logic/resource/timing), "
            prompt += "description, severity (low/medium/high/critical), and mitigation."

            response = client.chat(
                model=self._red_model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.6, "num_predict": 800}
            )

            result = {
                "plan": plan,
                "vulnerabilities": response["message"]["content"],
                "timestamp": datetime.utcnow().isoformat(),
            }
            self._attack_log.append(result)
            logger.info(f"[VECTOR][red_team] Plan attacked: {plan[:50]}...")
            return result

        except Exception as e:
            logger.error(f"[VECTOR][red_team] Attack failed: {e}")
            return {"error": str(e)}

    async def audit_policy(self, policy_text: str) -> dict:
        """Audit a policy for loopholes, edge cases, and unintended consequences."""
        try:
            import ollama
            client = ollama.Client(host=self._ollama_host)

            prompt = f"Audit this V.E.C.T.O.R. policy for weaknesses:\n\n{policy_text}\n\n"
            prompt += "Identify: 1) Ambiguous language, 2) Edge cases, "
            prompt += "3) Potential for misuse, 4) Missing safeguards"

            response = client.chat(
                model=self._red_model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.4, "num_predict": 600}
            )

            return {"audit_result": response["message"]["content"], "policy": policy_text[:100]}

        except Exception as e:
            logger.error(f"[VECTOR][red_team] Policy audit failed: {e}")
            return {"error": str(e)}

    def get_attack_summary(self) -> dict:
        """Get summary of all red team attacks."""
        return {
            "total_attacks": len(self._attack_log),
            "recent_attacks": self._attack_log[-5:],
        }


if __name__ == "__main__":
    import asyncio
    rt = RedTeamAgent()
    result = asyncio.run(rt.attack_plan("Deploy new agent to production", "Current system has 3 critical alerts"))
    print(result.get("vulnerabilities", result.get("error", "unknown"))[:300])