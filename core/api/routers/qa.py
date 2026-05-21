"""VECTOR qa router - /qa/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/qa", tags=["qa"])


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


class QaWriteTestsReq(BaseModel):
    code: str = ""
    coverage_target: int = 80

@router.post("/write-tests")
async def qa_write_tests(body: QaWriteTestsReq):
    """Generate comprehensive test suite."""
    try:
        return _run("qa_write_tests", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][qa] qa_write_tests failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class AnalyzeTestResultsReq(BaseModel):
    results: str = ""
    baseline: str = ""

@router.post("/analyze-results")
async def analyze_test_results(body: AnalyzeTestResultsReq):
    """Analyze test results: flakiness, regressions."""
    try:
        return _run("analyze_test_results", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][qa] analyze_test_results failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class AccessibilityAuditReq(BaseModel):
    url: str = ""
    html: str = ""

@router.post("/accessibility-audit")
async def accessibility_audit(body: AccessibilityAuditReq):
    """WCAG accessibility audit."""
    try:
        return _run("accessibility_audit", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][qa] accessibility_audit failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class ApiTestReq(BaseModel):
    endpoint: str = ""
    method: str = "GET"
    expected_status: int = 200

@router.post("/api-test")
async def api_test(body: ApiTestReq):
    """Validate API endpoint correctness."""
    try:
        return _run("api_test", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][qa] api_test failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class RealityCheckReq(BaseModel):
    claim: str = ""
    context: str = ""

@router.post("/reality-check")
async def reality_check(body: RealityCheckReq):
    """Fact-check LLM output against evidence."""
    try:
        return _run("reality_check", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][qa] reality_check failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
