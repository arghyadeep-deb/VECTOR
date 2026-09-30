"""VECTOR qa router - /qa/* endpoints."""

__all__ = [
    "accessibility_audit",
    "AccessibilityAuditReq",
    "analyze_test_results",
    "AnalyzeTestResultsReq",
    "api_test",
    "ApiTestReq",
    "qa_write_tests",
    "QaWriteTestsReq",
    "reality_check",
    "RealityCheckReq",
    "router",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/qa", tags=["qa"])


class QaWriteTestsReq(BaseModel):
    code: str = ""
    coverage_target: int = 80

@router.post("/write-tests")
async def qa_write_tests(body: QaWriteTestsReq):
    """Generate comprehensive test suite."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "qa_write_tests", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][qa] qa_write_tests failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class AnalyzeTestResultsReq(BaseModel):
    results: str = ""
    baseline: str = ""

@router.post("/analyze-results")
async def analyze_test_results(body: AnalyzeTestResultsReq):
    """Analyze test results: flakiness, regressions."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "analyze_test_results", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][qa] analyze_test_results failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class AccessibilityAuditReq(BaseModel):
    url: str = ""
    html: str = ""

@router.post("/accessibility-audit")
async def accessibility_audit(body: AccessibilityAuditReq):
    """WCAG accessibility audit."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "accessibility_audit", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][qa] accessibility_audit failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class ApiTestReq(BaseModel):
    endpoint: str = ""
    method: str = "GET"
    expected_status: int = 200

@router.post("/api-test")
async def api_test(body: ApiTestReq):
    """Validate API endpoint correctness."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "api_test", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][qa] api_test failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class RealityCheckReq(BaseModel):
    claim: str = ""
    context: str = ""

@router.post("/reality-check")
async def reality_check(body: RealityCheckReq):
    """Fact-check LLM output against evidence."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "reality_check", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][qa] reality_check failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
