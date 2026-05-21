"""VECTOR news router - /news/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/news", tags=["news"])


def _run(task_type: str, params: dict) -> dict:
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(
            gov.dispatch({"type": task_type, "params": params})
        )
    finally:
        loop.close()
    return result


class FetchNewsReq(BaseModel):
    topics: str = "AI"
    limit: int = 10

@router.post("/fetch")
async def fetch_news(body: FetchNewsReq):
    """Fetch latest AI and tech news."""
    try:
        return _run("fetch_news", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][news] fetch_news failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class SpotOpportunitiesReq(BaseModel):
    domain: str = ""
    timeframe: str = "7d"

@router.post("/spot-opportunities")
async def spot_opportunities(body: SpotOpportunitiesReq):
    """Analyze trends for business opportunities."""
    try:
        return _run("spot_opportunities", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][news] spot_opportunities failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class MarketTrendsReq(BaseModel):
    sector: str = "technology"
    depth: str = "summary"

@router.post("/market-trends")
async def market_trends(body: MarketTrendsReq):
    """Sector sentiment and market trend analysis."""
    try:
        return _run("market_trends", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][news] market_trends failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/daily-brief")
async def daily_brief():
    """Get the daily trending summary brief."""
    try:
        return _run("daily_brief", {})
    except Exception as e:
        logger.error("[VECTOR][news] daily_brief failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
