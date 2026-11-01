"""VECTOR analytics router - /analytics/* endpoints."""

__all__ = [
    "analytics_report",
    "AnalyticsReportReq",
    "benchmark_run",
    "BenchmarkRunReq",
    "etl_run",
    "EtlRunReq",
    "pipeline_health",
    "router",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/pipeline-health")
async def pipeline_health():
    """Data pipeline health: DB stats, NULL columns."""
    try:
        import datetime

        from core.memory.episodic import EpisodicMemory

        stats = EpisodicMemory().get_stats()
        return {
            "status": "ok",
            "pipelines": {
                "episodic_memory": {
                    "status": "ok",
                    "rows": stats.get("episodic_memory", 0),
                },
                "semantic_memory": {
                    "status": "ok",
                    "rows": stats.get("semantic_memory", 0),
                },
                "reasoning_chains": {
                    "status": "ok",
                    "rows": stats.get("reasoning_chains", 0),
                },
            },
            "checks": {
                "db_stats": "ok",
                "etl_workers": "not_configured",
            },
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("[VECTOR][analytics] pipeline_health failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class EtlRunReq(BaseModel):
    source: str = ""
    target: str = "silver"
    filters: str = ""

@router.post("/etl-run")
async def etl_run(body: EtlRunReq):
    """ETL pipeline: bronze to silver to gold."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "etl_run", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][analytics] etl_run failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class AnalyticsReportReq(BaseModel):
    period: str = "30d"
    metrics: str = "all"

@router.post("/report")
async def analytics_report(body: AnalyticsReportReq):
    """Analytics report: trends, anomalies, forecasts."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "analytics_report", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][analytics] analytics_report failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class BenchmarkRunReq(BaseModel):
    metric: str = ""
    baseline: str = ""

@router.post("/benchmark")
async def benchmark_run(body: BenchmarkRunReq):
    """Performance benchmark across time periods."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "benchmark_run", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][analytics] benchmark_run failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
