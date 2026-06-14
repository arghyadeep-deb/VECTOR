"""Server-side GTM agent — sGTM health, CAPI, server container monitoring."""

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.city.agent_base import AgentBase
from core.config import CONFIG

class SGTMAgent(AgentBase):
    """Server-side Google Tag Manager health monitor and optimizer."""
    def __init__(self):
        super().__init__("sgtm_001", "SGTMAgent", "marketing")

    async def health_check(self, container_url: str = "", data: dict = None) -> dict:
        """Check sGTM container health — hit rate, tag firing, CAPI coverage."""
        try:
            from core.inference.provider_client import get_client
            client = get_client()
            prompt = f"""Review this sGTM (server-side GTM) setup:
1. Container hit rate vs client-side baseline
2. Tag firing success rates
3. CAPI integration health (Facebook, Google, TikTok)
4. Data layer coverage
5. Performance impact on server latency

Container URL: {container_url}
Data: {str(data or {})[:500]}"""
            response = await client.complete(
                model=CONFIG.get("models", {}).get("focus", "vector-focus"),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )
            self.award_points(5, "sgtm_health")
            return {"status": "ok", "health": response.content}
        except Exception as e:
            logger.error("[VECTOR][sgtm] health_check error: {}", e)
            return {"status": "error", "error": str(e)}

    async def run(self, params: dict = None) -> dict:
        p = params or {}
        return await self.health_check(p.get("container_url", ""), p)

if __name__ == "__main__":
    a = SGTMAgent()
    print("✅ sgtm_agent OK:", type(a).__name__)
