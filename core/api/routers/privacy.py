"""VECTOR privacy router - /privacy/* endpoints."""

__all__ = [
    "audit_data_flow",
    "AuditDataFlowReq",
    "gdpr_check",
    "GdprCheckReq",
    "redact_data",
    "RedactDataReq",
    "router",
    "scan_data_sharing",
    "ScanDataSharingReq",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/privacy", tags=["privacy"])


class ScanDataSharingReq(BaseModel):
    scope: str = "full"
    data_types: str = "all"

@router.post("/scan-sharing")
async def scan_data_sharing(body: ScanDataSharingReq):
    """Detect PII leaks and unauthorized data sharing."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "scan_data_sharing", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][privacy] scan_data_sharing failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class GdprCheckReq(BaseModel):
    data_category: str = ""
    processing_purpose: str = ""

@router.post("/gdpr-check")
async def gdpr_check(body: GdprCheckReq):
    """GDPR compliance check."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "gdpr_check", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][privacy] gdpr_check failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class RedactDataReq(BaseModel):
    text: str = ""
    types: str = "all"

@router.post("/redact")
async def redact_data(body: RedactDataReq):
    """Redact sensitive PII from text."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "redact_data", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][privacy] redact_data failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class AuditDataFlowReq(BaseModel):
    system: str = "all"
    depth: int = 2

@router.post("/audit-flow")
async def audit_data_flow(body: AuditDataFlowReq):
    """Audit what data flows where across VECTOR."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "audit_data_flow", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][privacy] audit_data_flow failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
