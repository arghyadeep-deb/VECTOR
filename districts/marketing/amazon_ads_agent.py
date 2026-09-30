"""Amazon Ads agent — retail media, sponsored products/brands/display."""

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.city.agent_base import AgentBase
from core.config import CONFIG

class AmazonAdsAgent(AgentBase):
    """Amazon retail media auditor and optimizer."""
    def __init__(self):
        super().__init__("amazon_ads_001", "AmazonAdsAgent", "marketing")
        self.capabilities = ["ads", "amazon_ads", "audit", "marketing"]

    async def audit(self, account_data: dict | None = None) -> dict:
        """Audit Amazon Ads account — ACOS, TACOS, spend efficiency."""
        try:
            from core.inference.provider_client import get_client
            client = get_client()
            prompt = f"""Audit this Amazon Ads account data and provide:
1. ACOS analysis (target vs actual)
2. TACOS assessment
3. Campaign structure review (auto vs manual)
4. Keyword bid optimization recommendations
5. Product targeting gaps

Data: {str(account_data or {})[:1000]}"""
            response = await client.complete(
                model=CONFIG.get("models", {}).get("focus", "vector-focus"),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
            )
            self.award_points(8, "amazon_audit")
            return {"status": "ok", "audit": response.content, "platform": "amazon"}
        except Exception as e:
            logger.error("[VECTOR][amazon_ads] audit error: {}", e)
            return {"status": "error", "error": str(e)}

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        params = task.get("params", {}) or {}

        if task_type in ("audit", "amazon_ads_audit"):
            return await self.audit(params.get("account_data", params))

        # 2026-09-30 (Phase 3 codebase audit finding): real chat dispatch sends
        # an LLM-invented task_type that won't match the branch above, carrying
        # a real free-text question in params (see
        # tests/test_marketing_district_run_wiring.py's module docstring for
        # the bug class — same as districts/languages/hindi_coach.py's fixed
        # pattern). This agent has one real capability, so any on-topic query
        # routes to it rather than erroring.
        query = (params.get("query") or params.get("content") or task.get("query") or task.get("prompt") or "").strip()
        if query:
            return await self.audit(params.get("account_data", params))

        return {
            "status": "error",
            "error": f"unhandled type '{task_type}'",
            "supported": ["audit", "amazon_ads_audit"],
        }

if __name__ == "__main__":
    a = AmazonAdsAgent()
    print("✅ amazon_ads_agent OK:", type(a).__name__)
