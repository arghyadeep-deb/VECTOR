"""VECTOR privacy router - /privacy/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/privacy", tags=["privacy"])


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


class ScanDataSharingReq(BaseModel):
    scope: str = "full"
    data_types: str = "all"

@router.post("/scan-sharing")
async def scan_data_sharing(body: ScanDataSharingReq):
    """Detect PII leaks and unauthorized data sharing."""
    try:
        return _run("scan_data_sharing", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][privacy] scan_data_sharing failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class GdprCheckReq(BaseModel):
    data_category: str = ""
    processing_purpose: str = ""

@router.post("/gdpr-check")
async def gdpr_check(body: GdprCheckReq):
    """GDPR compliance check."""
    try:
        return _run("gdpr_check", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][privacy] gdpr_check failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class RedactDataReq(BaseModel):
    text: str = ""
    types: str = "all"

@router.post("/redact")
async def redact_data(body: RedactDataReq):
    """Redact sensitive PII from text."""
    try:
        return _run("redact_data", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][privacy] redact_data failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class AuditDataFlowReq(BaseModel):
    system: str = "all"
    depth: int = 2

@router.post("/audit-flow")
async def audit_data_flow(body: AuditDataFlowReq):
    """Audit what data flows where across VECTOR."""
    try:
        return _run("audit_data_flow", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][privacy] audit_data_flow failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
