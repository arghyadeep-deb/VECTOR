"""VECTOR startups router - /startups/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/startups", tags=["startups"])


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


class ValidateIdeaReq(BaseModel):
    idea: str = ""
    market: str = ""
    differentiator: str = ""

@router.post("/validate-idea")
async def validate_idea(body: ValidateIdeaReq):
    """Market viability scoring for a startup idea."""
    try:
        return _run("validate_idea", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][startups] validate_idea failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class MarketScanReq(BaseModel):
    market: str = ""
    geography: str = "global"

@router.post("/market-scan")
async def market_scan(body: MarketScanReq):
    """TAM/SAM/SOM analysis for a market."""
    try:
        return _run("market_scan", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][startups] market_scan failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class CompetitorAnalysisReq(BaseModel):
    product: str = ""
    competitors: str = ""

@router.post("/competitor-analysis")
async def competitor_analysis(body: CompetitorAnalysisReq):
    """Competitive landscape analysis."""
    try:
        return _run("competitor_analysis", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][startups] competitor_analysis failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class RevenueModelReq(BaseModel):
    business_type: str = ""
    price_point: float = 0.0
    target_customers: int = 1000

@router.post("/revenue-model")
async def revenue_model(body: RevenueModelReq):
    """Build financial projections."""
    try:
        return _run("revenue_model", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][startups] revenue_model failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
