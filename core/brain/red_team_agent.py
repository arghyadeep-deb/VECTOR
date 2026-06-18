"""
V.E.C.T.O.R. RedTeamAgent — adversarial review before RED/critical actions.
Routes through provider_client (reasoning tier: github_models o3 → groq → llm7 → ollama).
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger
from core.config import CONFIG


class RedTeamAgent:
    """
    Plays devil's advocate: finds flaws in VECTOR's plans, decisions, and policies
    before they are executed. Strengthens the system through adversarial thinking.
    """

    _SYSTEM = None  # loaded lazily from PromptLibrary

    @classmethod
    def _system_prompt(cls) -> str:
        if cls._SYSTEM is None:
            try:
                from core.prompt_library import get_library
                cls._SYSTEM = get_library().get("engineering-security-engineer") or ""
            except Exception:
                cls._SYSTEM = (
                    "You are a red team security agent. Your job is to find vulnerabilities, "
                    "logic flaws, and safety risks in plans and policies. Be thorough and adversarial."
                )
        return cls._SYSTEM

    def __init__(self) -> None:
        self._attack_log: list[dict] = []
        logger.info("[VECTOR][red_team] RedTeamAgent initialized")

    async def _call(self, user_prompt: str, temperature: float = 0.6, max_tokens: int = 800) -> str:
        try:
            from core.inference.provider_client import ProviderClient
            client = ProviderClient()
            result = await client.chat(
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user",   "content": user_prompt},
                ],
                tier="reasoning",
                temperature=temperature,
                max_tokens=max_tokens,
                caller_id="red_team_agent",
            )
            return result.content
        except Exception as e:
            logger.error("[VECTOR][red_team] provider_client failed: {}", e)
            raise

    async def attack_plan(self, plan: str, context: str = "") -> dict:
        """
        Attack a plan from multiple angles: safety, logic, resource, timing.
        Returns {vulnerabilities, severity, recommendations}.
        """
        prompt = (
            f"Attack this VECTOR plan from every angle:\n\nPlan: {plan}\n\nContext: {context}\n\n"
            "For each vulnerability specify: type (safety/logic/resource/timing), "
            "description, severity (low/medium/high/critical), and mitigation."
        )
        try:
            content = await self._call(prompt, temperature=0.6, max_tokens=800)
            result = {
                "plan":            plan,
                "vulnerabilities": content,
                "timestamp":       datetime.utcnow().isoformat(),
            }
            self._attack_log.append(result)
            logger.info("[VECTOR][red_team] Plan attacked: {}...", plan[:50])
            return result
        except Exception as e:
            logger.error("[VECTOR][red_team] attack_plan failed: {}", e)
            return {"error": str(e)}

    async def audit_policy(self, policy_text: str) -> dict:
        """Audit a policy for loopholes, edge cases, and unintended consequences."""
        prompt = (
            f"Audit this VECTOR policy for weaknesses:\n\n{policy_text}\n\n"
            "Identify: 1) Ambiguous language, 2) Edge cases, "
            "3) Potential for misuse, 4) Missing safeguards"
        )
        try:
            content = await self._call(prompt, temperature=0.4, max_tokens=600)
            return {"audit_result": content, "policy": policy_text[:100]}
        except Exception as e:
            logger.error("[VECTOR][red_team] audit_policy failed: {}", e)
            return {"error": str(e)}

    def get_attack_summary(self) -> dict:
        return {
            "total_attacks":  len(self._attack_log),
            "recent_attacks": self._attack_log[-5:],
        }


if __name__ == "__main__":
    import asyncio
    rt = RedTeamAgent()
    result = asyncio.run(rt.attack_plan(
        "Deploy new agent to production",
        "Current system has 3 critical alerts",
    ))
    print(result.get("vulnerabilities", result.get("error", "unknown"))[:300])
    print("OK red_team_agent.py")
