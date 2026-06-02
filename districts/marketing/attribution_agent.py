"""Attribution agent — Consent Mode V2, server-side GTM, CAPI tracking."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from loguru import logger
from core.city.agent_base import AgentBase
from core.config import CONFIG

class AttributionAgent(AgentBase):
    """Multi-touch attribution auditor — Consent Mode V2, sGTM, CAPI health."""
    def __init__(self):
        super().__init__("attribution_001", "AttributionAgent", "marketing")

    async def audit_consent_mode(self, ga4_data: dict = None) -> dict:
        """Audit Consent Mode V2 setup — modeled conversions, consent signals."""
        try:
            from core.inference.provider_client import get_client
            client = get_client()
            prompt = f"""Audit this tracking setup for Consent Mode V2 compliance:
1. Consent signal implementation (granted/denied rates)
2. Modeled conversion quality
3. Server-side GTM migration status
4. CAPI (Conversions API) coverage for Meta/Google
5. Data gaps and recommendations

Data: {str(ga4_data or {})[:800]}"""
            response = await client.complete(
                model=CONFIG.get("models", {}).get("focus", "vector-focus"),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
            )
            self.award_points(8, "attribution_audit")
            return {"status": "ok", "audit": response.content}
        except Exception as e:
            logger.error("[VECTOR][attribution] audit error: {}", e)
            return {"status": "error", "error": str(e)}

    async def run(self, params: dict = None) -> dict:
        return await self.audit_consent_mode(params or {})

if __name__ == "__main__":
    a = AttributionAgent()
    print("✅ attribution_agent OK:", type(a).__name__)
