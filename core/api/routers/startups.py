"""VECTOR startups router - /startups/* endpoints."""

__all__ = [
    "competitor_analysis",
    "CompetitorAnalysisReq",
    "market_scan",
    "MarketScanReq",
    "revenue_model",
    "RevenueModelReq",
    "router",
    "validate_idea",
    "ValidateIdeaReq",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/startups", tags=["startups"])


@router.get("/ventures/latest")
async def ventures_latest():
    """Latest venture-pipeline output for the HUD ventures widget.

    Returns the newest clusters_*.json (ranked problem clusters) plus the
    newest venture_report_*.md filename from data/venture/. Empty payload
    (status: none) when the pipeline hasn't run yet.
    """
    import json
    from pathlib import Path
    from core.config import CONFIG
    try:
        d = Path(CONFIG.get("venture", {}).get("data_dir", "data/venture"))
        clusters_files = sorted(d.glob("clusters_*.json"))
        report_files = sorted(d.glob("venture_report_*.md"))
        if not clusters_files:
            return {"status": "none", "clusters": [], "report": ""}
        data = json.loads(clusters_files[-1].read_text(encoding="utf-8"))
        return {
            "status": "ok",
            "analyzed_at": data.get("analyzed_at", ""),
            "total_posts": data.get("total_posts", 0),
            "clusters": data.get("clusters", []),
            "report": report_files[-1].name if report_files else "",
        }
    except Exception as e:
        logger.error("[VECTOR][startups] ventures_latest failed: {}", e)
        return {"status": "error", "clusters": [], "report": ""}


@router.post("/ventures/run")
async def ventures_run():
    """Kick a full venture-pipeline run now (same path as the weekly cron)."""
    try:
        from districts.news_trends.venture_pipeline import VenturePipeline
        return await VenturePipeline().execute()
    except Exception as e:
        logger.error("[VECTOR][startups] ventures_run failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


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
        logger.error("[VECTOR][startups] validate_idea failed: {}", e)
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
        logger.error("[VECTOR][startups] market_scan failed: {}", e)
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
        logger.error("[VECTOR][startups] competitor_analysis failed: {}", e)
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
        logger.error("[VECTOR][startups] revenue_model failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
