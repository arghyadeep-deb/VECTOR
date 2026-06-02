"""Amazon Ads agent — retail media, sponsored products/brands/display."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from loguru import logger
from core.city.agent_base import AgentBase
from core.config import CONFIG

class AmazonAdsAgent(AgentBase):
    """Amazon retail media auditor and optimizer."""
    def __init__(self):
        super().__init__("amazon_ads_001", "AmazonAdsAgent", "marketing")

    async def audit(self, account_data: dict = None) -> dict:
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

    async def run(self, params: dict = None) -> dict:
        return await self.audit(params or {})

if __name__ == "__main__":
    a = AmazonAdsAgent()
    print("✅ amazon_ads_agent OK:", type(a).__name__)
