"""Scraper router — /scraper/status."""

import sys

__all__ = [
    "router",
    "scraper_status",
]


from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/scraper", tags=["scraper"])

@router.get("/status")
async def scraper_status():
    """Report available fetcher types in VectorScraper."""
    fetcher_types = []
    stealth_available = False
    dynamic_available = False
    try:
        from core.scraper.vector_scraper import VectorScraper
        fetcher_types = ["http"]
        try:
            from core.scraper.fetchers.stealth_chrome import StealthChromeFetcher
            stealth_available = True
            fetcher_types.append("stealth")
        except ImportError:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
        try:
            from core.scraper.fetchers.chrome import ChromeFetcher
            dynamic_available = True
            fetcher_types.append("dynamic")
        except ImportError:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
    except Exception as e:
        logger.warning(f"[VECTOR][api][scraper] status failed: {e}")

    return {
        "fetcher_types": fetcher_types,
        "stealth_available": stealth_available,
        "dynamic_available": dynamic_available,
    }

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ scraper.py OK")
