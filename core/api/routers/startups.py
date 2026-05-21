"""VECTOR startups router - /startups/* endpoints."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/startups", tags=["startups"])




class ValidateIdeaReq(BaseModel):
    idea: str = ""
    market: str = ""
    differentiator: str = ""

@router.post("/validate-idea")
async def validate_idea(body: ValidateIdeaReq):
    """Market viability scoring for a startup idea."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "validate_idea", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][startups] validate_idea failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class MarketScanReq(BaseModel):
    market: str = ""
    geography: str = "global"

@router.post("/market-scan")
async def market_scan(body: MarketScanReq):
    """TAM/SAM/SOM analysis for a market."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "market_scan", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][startups] market_scan failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class CompetitorAnalysisReq(BaseModel):
    product: str = ""
    competitors: str = ""

@router.post("/competitor-analysis")
async def competitor_analysis(body: CompetitorAnalysisReq):
    """Competitive landscape analysis."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "competitor_analysis", "params": body.model_dump()})
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
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "revenue_model", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][startups] revenue_model failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
