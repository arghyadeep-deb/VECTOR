"""OAuth router — /oauth/integrations."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/oauth", tags=["oauth"])

@router.get("/integrations")
async def oauth_integrations():
    """Get OAuth integration registry stats."""
    try:
        from core.engine.oauth.registry import OAuthRegistry
        reg = OAuthRegistry()
        categories = {}
        for cat in reg.categories():
            categories[cat] = len(reg.list_by_category(cat))
        return {
            "total_integrations": reg.count(),
            "categories": categories,
            "available": len(reg.available()),
        }
    except Exception as e:
        logger.warning(f"[VECTOR][api][oauth] integrations failed: {e}")
        return {"total_integrations": 0, "categories": {}, "available": 0}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ oauth.py OK")
