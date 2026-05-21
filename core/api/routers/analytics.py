"""VECTOR analytics router - /analytics/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/analytics", tags=["analytics"])


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


@router.get("/pipeline-health")
async def pipeline_health():
    """Data pipeline health: DB stats, NULL columns."""
    try:
        return _run("pipeline_health", {})
    except Exception as e:
        logger.error("[VECTOR][analytics] pipeline_health failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class EtlRunReq(BaseModel):
    source: str = ""
    target: str = "silver"
    filters: str = ""

@router.post("/etl-run")
async def etl_run(body: EtlRunReq):
    """ETL pipeline: bronze to silver to gold."""
    try:
        return _run("etl_run", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][analytics] etl_run failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class AnalyticsReportReq(BaseModel):
    period: str = "30d"
    metrics: str = "all"

@router.post("/report")
async def analytics_report(body: AnalyticsReportReq):
    """Analytics report: trends, anomalies, forecasts."""
    try:
        return _run("analytics_report", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][analytics] analytics_report failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class BenchmarkRunReq(BaseModel):
    metric: str = ""
    baseline: str = ""

@router.post("/benchmark")
async def benchmark_run(body: BenchmarkRunReq):
    """Performance benchmark across time periods."""
    try:
        return _run("benchmark_run", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][analytics] benchmark_run failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
