"""VECTOR documentation router - /documentation/* endpoints."""

__all__ = [
    "api_reference",
    "ApiReferenceReq",
    "generate_changelog",
    "generate_docs",
    "GenerateChangelogReq",
    "GenerateDocsReq",
    "router",
    "weekly_summary",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/documentation", tags=["documentation"])


class ApiReferenceReq(BaseModel):
    file_path: str = ""
    format: str = "markdown"

@router.post("/api-reference")
async def api_reference(body: ApiReferenceReq):
    """Auto-generate API reference from code."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "api_reference", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][documentation] api_reference failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class GenerateDocsReq(BaseModel):
    topic: str = ""
    doc_type: str = "architecture"
    depth: str = "detailed"

@router.post("/generate")
async def generate_docs(body: GenerateDocsReq):
    """Generate technical documentation."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "generate_docs", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][documentation] generate_docs failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class GenerateChangelogReq(BaseModel):
    version: str = ""
    since_tag: str = ""

@router.post("/changelog")
async def generate_changelog(body: GenerateChangelogReq):
    """Generate changelog from git history."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "generate_changelog", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][documentation] generate_changelog failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/weekly-summary")
async def weekly_summary():
    """Generate weekly progress summary."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "weekly_summary", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][documentation] weekly_summary failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
