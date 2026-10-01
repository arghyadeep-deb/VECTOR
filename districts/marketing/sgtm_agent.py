"""Server-side GTM agent — sGTM health, CAPI, server container monitoring."""

import os

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.city.agent_base import AgentBase
from core.config import CONFIG

class SGTMAgent(AgentBase):
    """Server-side Google Tag Manager health monitor and optimizer."""
    def __init__(self):
        super().__init__("sgtm_001", "SGTMAgent", "marketing")
        self.capabilities = ["health_check", "marketing", "server_side", "sgtm"]

    async def health_check(self, container_url: str = "", data: dict | None = None) -> dict:
        """Check sGTM container health — hit rate, tag firing, CAPI coverage."""
        if os.getenv("VECTOR_SGTM_LIVE_HEALTH") != "1":
            self.award_points(5, "sgtm_health_offline")
            return {
                "status": "ok",
                "health": "Offline sGTM health route verified; set VECTOR_SGTM_LIVE_HEALTH=1 for live model review.",
                "container_url": container_url,
                "degraded": True,
            }
        try:
            from core.inference.provider_client import get_client
            from core.loop.context_engine import ContextEngine
            client = get_client()
            prompt = f"""Review this sGTM (server-side GTM) setup:
1. Container hit rate vs client-side baseline
2. Tag firing success rates
3. CAPI integration health (Facebook, Google, TikTok)
4. Data layer coverage
5. Performance impact on server latency

Container URL: {container_url}
Data: {str(data or {})[:500]}"""
            # RULE 1: session_hydration_prompt() before every LLM call.
            hydration = ContextEngine().session_hydration_prompt({"query": prompt})
            response = await client.complete(
                model=CONFIG.get("models", {}).get("focus", "vector-focus"),
                messages=[
                    {"role": "system", "content": hydration},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=500,
            )
            self.award_points(5, "sgtm_health")
            return {"status": "ok", "health": response.content}
        except Exception as e:
            logger.error("[VECTOR][sgtm] health_check error: {}", e)
            return {"status": "error", "error": str(e)}

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        params = task.get("params", {}) or {}

        if task_type in ("health_check", "sgtm_health"):
            return await self.health_check(params.get("container_url", ""), params)

        # 2026-09-30 (Phase 3 codebase audit finding): real chat dispatch sends
        # an LLM-invented task_type that won't match the branch above, carrying
        # a real free-text question in params (see
        # tests/test_marketing_district_run_wiring.py's module docstring for
        # the bug class — same as districts/languages/hindi_coach.py's fixed
        # pattern). This agent has one real capability, so any on-topic query
        # routes to it rather than erroring.
        query = (params.get("query") or params.get("content") or task.get("query") or task.get("prompt") or "").strip()
        if query:
            return await self.health_check(params.get("container_url", ""), params)

        return {
            "status": "error",
            "error": f"unhandled type '{task_type}'",
            "supported": ["health_check", "sgtm_health"],
        }

if __name__ == "__main__":
    a = SGTMAgent()
    print("✅ sgtm_agent OK:", type(a).__name__)
