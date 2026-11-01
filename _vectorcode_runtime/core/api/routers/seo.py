"""SEO router — /seo/status, /seo/geo-score, /seo/audit, /seo/keywords."""

import sys
from typing import List, Optional

__all__ = [
    "router",
    "seo_status",
    "compute_geo_score",
    "run_seo_audit",
    "get_keyword_analysis",
]


from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/seo", tags=["seo"])

@router.get("/status")
async def seo_status():
    """Report available SEO tools."""
    tools = []
    pagespeed_configured = False
    gsc_configured = False
    try:
        from core.config import CONFIG
        if CONFIG.get("pagespeed_api_key"):
            pagespeed_configured = True
            tools.append("pagespeed")
        if CONFIG.get("gsc_client_email") and CONFIG.get("gsc_private_key"):
            gsc_configured = True
            tools.append("gsc")
    except Exception as e:
        logger.warning(f"[VECTOR][api][seo] status failed: {e}")

    return {"pagespeed_configured": pagespeed_configured, "gsc_configured": gsc_configured, "tools": tools}


@router.post("/geo-score")
async def compute_geo_score(brand: str, queries: Optional[List[str]] = None):
    """Compute GEO score for brand across AI search engines."""
    from districts.marketing.geo_optimizer_agent import GEOOptimizerAgent
    agent = GEOOptimizerAgent()
    return await agent.geo_score(brand, queries or ["best AI assistant", "top productivity tools"])


@router.post("/audit")
async def run_seo_audit(url: str):
    """Run full SEO audit for a URL."""
    from districts.marketing.seo_specialist import SEOSpecialist
    agent = SEOSpecialist()
    result = await agent.run({"url": url}) if hasattr(agent, "run") else {"status": "seo_audit_running", "url": url}
    return result


@router.get("/keywords")
async def get_keyword_analysis(topic: str):
    """Analyze keywords for a topic."""
    from districts.marketing.seo_specialist import SEOSpecialist
    agent = SEOSpecialist()
    result = await agent.analyze_keywords(topic) if hasattr(agent, "analyze_keywords") else {"topic": topic, "status": "analysis_started"}
    return result


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ seo.py OK")
