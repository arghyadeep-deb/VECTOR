"""
V.E.C.T.O.R. RedTeamAgent — adversarial review before RED/critical actions.
Routes through provider_client (reasoning tier: github_models o3 → groq → llm7 → ollama).
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger
from core.config import CONFIG

_VERDICT_RE = re.compile(r"\b(BLOCKED|MODIFY|APPROVED)\b", re.IGNORECASE)


def _parse_verdict(text: str) -> str:
    """Extract a BLOCKED/MODIFY/APPROVED verdict from the model's free-text
    review. Fail-closed: ambiguous or absent -> BLOCKED. This is a RED-tier
    gate (core/loop/autonomous_loop.py's _act_on reads this field before
    letting a RED action through) -- an unparseable review must never read
    as a silent approval."""
    match = _VERDICT_RE.search(text or "")
    return match.group(1).upper() if match else "BLOCKED"


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

    async def attack_plan(self, plan: str | dict, context: str = "") -> dict:
        """
        Attack a plan from multiple angles: safety, logic, resource, timing.
        Returns {vulnerabilities, severity, recommendations, verdict}.

        `plan` may be a free-text description or a structured action proposal
        dict (core/loop/autonomous_loop.py's RED-tier gate passes the latter).
        `verdict` is BLOCKED/MODIFY/APPROVED, parsed from the model's review --
        before this, this method never returned a "verdict" key at all, so
        that gate's `review.get("verdict", "APPROVED")` silently defaulted to
        APPROVED on every call regardless of what the review actually found,
        and a dict `plan` crashed the old `plan[:50]` slice (caught by the
        broad except below, masking the failure as `{"error": ...}`, which
        still has no "verdict" key -- so the gate defaulted to APPROVED again).
        """
        plan_str = plan if isinstance(plan, str) else str(plan)
        prompt = (
            f"Attack this VECTOR plan from every angle:\n\nPlan: {plan_str}\n\nContext: {context}\n\n"
            "For each vulnerability specify: type (safety/logic/resource/timing), "
            "description, severity (low/medium/high/critical), and mitigation.\n\n"
            "Then, on its own final line, give an overall verdict as exactly one "
            "of: BLOCKED (a high/critical-severity vulnerability makes this unsafe "
            "to run as-is), MODIFY (fixable via the mitigations above), or "
            "APPROVED (no significant vulnerabilities found)."
        )
        try:
            content = await self._call(prompt, temperature=0.6, max_tokens=800)
            result = {
                "plan":            plan,
                "vulnerabilities": content,
                "verdict":         _parse_verdict(content),
                "timestamp":       datetime.utcnow().isoformat(),
            }
            self._attack_log.append(result)
            logger.info("[VECTOR][red_team] Plan attacked: {}...", plan_str[:50])
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
