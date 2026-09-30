"""VECTOR news router - /news/* endpoints."""

__all__ = [
    "daily_brief",
    "fetch_news",
    "FetchNewsReq",
    "market_trends",
    "MarketTrendsReq",
    "router",
    "spot_opportunities",
    "SpotOpportunitiesReq",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/news", tags=["news"])


class FetchNewsReq(BaseModel):
    topics: str = "AI"
    limit: int = 10

@router.post("/fetch")
async def fetch_news(body: FetchNewsReq):
    """Fetch latest AI and tech news."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "fetch_news", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][news] fetch_news failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class SpotOpportunitiesReq(BaseModel):
    domain: str = ""
    timeframe: str = "7d"

@router.post("/spot-opportunities")
async def spot_opportunities(body: SpotOpportunitiesReq):
    """Analyze trends for business opportunities."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "spot_opportunities", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][news] spot_opportunities failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class MarketTrendsReq(BaseModel):
    sector: str = "technology"
    depth: str = "summary"

@router.post("/market-trends")
async def market_trends(body: MarketTrendsReq):
    """Sector sentiment and market trend analysis."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "market_trends", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][news] market_trends failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/daily-brief")
async def daily_brief():
    """Get the daily trending summary brief."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "daily_brief", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][news] daily_brief failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
