"""SEO router — /seo/status."""

import sys

__all__ = [
    "router",
    "seo_status",
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

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ seo.py OK")
