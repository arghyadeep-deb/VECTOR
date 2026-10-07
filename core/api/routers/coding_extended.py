"""VECTOR coding router - /coding/* endpoints."""

__all__ = [
    "architect_advice",
    "ArchitectAdviceReq",
    "code_review",
    "CodeReviewReq",
    "db_optimize",
    "DbOptimizeReq",
    "rapid_prototype",
    "RapidPrototypeReq",
    "router",
    "write_tests",
    "WriteTestsReq",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from loguru import logger

router = APIRouter(prefix="/coding", tags=["coding"])


class CodeReviewReq(BaseModel):
    file_path: str = ""
    code: str = ""
    context: str = ""

@router.post("/review")
async def code_review(body: CodeReviewReq):
    """Full code review with metrics and recommendations."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "code_review", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][coding] code_review failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class ArchitectAdviceReq(BaseModel):
    description: str = ""
    constraints: str = ""

@router.post("/architect")
async def architect_advice(body: ArchitectAdviceReq):
    """Architecture advice and design patterns."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "architect_advice", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][coding] architect_advice failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class RapidPrototypeReq(BaseModel):
    feature: str = ""
    stack: str = "python"

@router.post("/rapid-prototype")
async def rapid_prototype(body: RapidPrototypeReq):
    """Generate rapid prototype for a described feature."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "rapid_prototype", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][coding] rapid_prototype failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class DbOptimizeReq(BaseModel):
    query: str = ""
    schema_text: str = Field("", alias="schema")

@router.post("/db-optimize")
async def db_optimize(body: DbOptimizeReq):
    """Database query optimization and indexing strategy."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "db_optimize", "params": body.model_dump(by_alias=True)})
    except Exception as e:
        logger.error("[VECTOR][coding] db_optimize failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class WriteTestsReq(BaseModel):
    code: str = ""
    test_type: str = "unit"

@router.post("/test-write")
async def write_tests(body: WriteTestsReq):
    """Generate tests for a function or class."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "write_tests", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][coding] write_tests failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
