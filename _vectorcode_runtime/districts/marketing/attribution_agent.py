"""Attribution agent — Consent Mode V2, server-side GTM, CAPI tracking."""

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.city.agent_base import AgentBase
from core.config import CONFIG

class AttributionAgent(AgentBase):
    """Multi-touch attribution auditor — Consent Mode V2, sGTM, CAPI health."""
    def __init__(self):
        super().__init__("attribution_001", "AttributionAgent", "marketing")
        self.capabilities = ["attribution", "audit_consent_mode", "marketing"]

    async def audit_consent_mode(self, ga4_data: dict | None = None) -> dict:
        """Audit Consent Mode V2 setup — modeled conversions, consent signals."""
        try:
            from core.inference.provider_client import get_client
            from core.loop.context_engine import ContextEngine
            client = get_client()
            prompt = f"""Audit this tracking setup for Consent Mode V2 compliance:
1. Consent signal implementation (granted/denied rates)
2. Modeled conversion quality
3. Server-side GTM migration status
4. CAPI (Conversions API) coverage for Meta/Google
5. Data gaps and recommendations

Data: {str(ga4_data or {})[:800]}"""
            # RULE 1: session_hydration_prompt() before every LLM call.
            hydration = ContextEngine().session_hydration_prompt({"query": prompt})
            response = await client.complete(
                model=CONFIG.get("models", {}).get("focus", "vector-focus"),
                messages=[
                    {"role": "system", "content": hydration},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=600,
            )
            self.award_points(8, "attribution_audit")
            return {"status": "ok", "audit": response.content}
        except Exception as e:
            logger.error("[VECTOR][attribution] audit error: {}", e)
            return {"status": "error", "error": str(e)}

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        params = task.get("params", {}) or {}

        if task_type in ("audit_consent_mode", "attribution_audit"):
            return await self.audit_consent_mode(params.get("ga4_data", params))

        # 2026-09-30 (Phase 3 codebase audit finding): real chat dispatch sends
        # an LLM-invented task_type that won't match the branch above, carrying
        # a real free-text question in params (see
        # tests/test_marketing_district_run_wiring.py's module docstring for
        # the bug class — same as districts/languages/hindi_coach.py's fixed
        # pattern). This agent has one real capability, so any on-topic query
        # routes to it rather than erroring.
        query = (params.get("query") or params.get("content") or task.get("query") or task.get("prompt") or "").strip()
        if query:
            return await self.audit_consent_mode(params.get("ga4_data", params))

        return {
            "status": "error",
            "error": f"unhandled type '{task_type}'",
            "supported": ["audit_consent_mode", "attribution_audit"],
        }

if __name__ == "__main__":
    a = AttributionAgent()
    print("✅ attribution_agent OK:", type(a).__name__)
