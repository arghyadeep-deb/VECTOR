"""VECTOR coding router - /coding/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/coding", tags=["coding"])


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


class CodeReviewReq(BaseModel):
    file_path: str = ""
    code: str = ""
    context: str = ""

@router.post("/review")
async def code_review(body: CodeReviewReq):
    """Full code review with metrics and recommendations."""
    try:
        return _run("code_review", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][coding] code_review failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class ArchitectAdviceReq(BaseModel):
    description: str = ""
    constraints: str = ""

@router.post("/architect")
async def architect_advice(body: ArchitectAdviceReq):
    """Architecture advice and design patterns."""
    try:
        return _run("architect_advice", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][coding] architect_advice failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class RapidPrototypeReq(BaseModel):
    feature: str = ""
    stack: str = "python"

@router.post("/rapid-prototype")
async def rapid_prototype(body: RapidPrototypeReq):
    """Generate rapid prototype for a described feature."""
    try:
        return _run("rapid_prototype", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][coding] rapid_prototype failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class DbOptimizeReq(BaseModel):
    query: str = ""
    schema: str = ""

@router.post("/db-optimize")
async def db_optimize(body: DbOptimizeReq):
    """Database query optimization and indexing strategy."""
    try:
        return _run("db_optimize", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][coding] db_optimize failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class WriteTestsReq(BaseModel):
    code: str = ""
    test_type: str = "unit"

@router.post("/test-write")
async def write_tests(body: WriteTestsReq):
    """Generate tests for a function or class."""
    try:
        return _run("write_tests", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][coding] write_tests failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
