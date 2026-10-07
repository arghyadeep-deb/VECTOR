"""Ads Intelligence router  --  /ads/* endpoints for the AdsOrchestratorAgent."""


from fastapi import APIRouter, HTTPException
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator
from loguru import logger

router = APIRouter(prefix="/ads", tags=["ads"])
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _confined_output(value: str, subdirectory: str, *, directory: bool) -> str:
    base = (_PROJECT_ROOT / "output" / subdirectory).resolve()
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = _PROJECT_ROOT / candidate
    candidate = candidate.resolve()
    if candidate != base and not candidate.is_relative_to(base):
        kind = "directory" if directory else "path"
        raise ValueError(f"Output {kind} must remain under {base}")
    return str(candidate)

_ads_agent = None


def _get_ads_agent():
    global _ads_agent
    if _ads_agent is None:
        from districts.marketing.ads_orchestrator_agent import AdsOrchestratorAgent
        _ads_agent = AdsOrchestratorAgent()
    return _ads_agent


#  --  Request models  -- 

class AdsAuditRequest(BaseModel):
    platforms: list[str] = ["google", "meta"]
    account_data: str = ""
    industry: str = "generic"

class AdsLandingRequest(BaseModel):
    url: str

class AdsBudgetRequest(BaseModel):
    budget_data: str = ""
    platforms: list[str] = ["google", "meta"]

class AdsPlanRequest(BaseModel):
    industry: str = "generic"
    business_data: str = ""

class AdsCompetitorRequest(BaseModel):
    competitor: str

class AdsMathRequest(BaseModel):
    budget: float = 0.0
    clicks: int = 0
    conversions: int = 0
    revenue: float = 0.0
    margin: float = 0.3

class AdsTestRequest(BaseModel):
    test_data: str

class AdsDnaRequest(BaseModel):
    url: str = ""
    html: str = ""

class AdsCreateRequest(BaseModel):
    brand_data: str = ""

class AdsGenerateRequest(BaseModel):
    model_config = ConfigDict(validate_default=True)

    prompt: str
    aspect_ratio: str = "1:1"
    output_dir: str = "output/ads_screenshots"

    @field_validator("prompt")
    @classmethod
    def _safe_positional_prompt(cls, value: str) -> str:
        if value.startswith("-"):
            raise ValueError("Prompt may not begin with '-' because it is passed as a CLI positional argument")
        return value

    @field_validator("output_dir")
    @classmethod
    def _safe_output_dir(cls, value: str) -> str:
        return _confined_output(value, "ads_screenshots", directory=True)

class AdsPhotoshootRequest(BaseModel):
    product: str
    style: str = "studio"

class AdsReportRequest(BaseModel):
    model_config = ConfigDict(validate_default=True)

    audit_markdown: str
    output_path: str = "output/ads_reports/audit_report.pdf"

    @field_validator("output_path")
    @classmethod
    def _safe_output_path(cls, value: str) -> str:
        return _confined_output(value, "ads_reports", directory=False)


#  --  Endpoints  -- 

@router.post("/audit")
async def ads_audit(body: AdsAuditRequest):
    """Run multi-platform paid ads audit (250+ checks across Google, Meta, LinkedIn, etc.)."""
    try:
        return await _get_ads_agent().run({"type": "ads_audit", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][ads] audit failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/landing")
async def ads_landing(body: AdsLandingRequest):
    """Analyze a landing page: Core Web Vitals, conversion signals, CTA, forms, trust."""
    try:
        return await _get_ads_agent().run({"type": "ads_landing", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][ads] landing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/budget")
async def ads_budget(body: AdsBudgetRequest):
    """Recommend optimal budget split and bidding strategies across platforms."""
    try:
        return await _get_ads_agent().run({"type": "ads_budget", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][ads] budget failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/plan")
async def ads_plan(body: AdsPlanRequest):
    """Generate a full paid advertising strategy for a specific industry."""
    try:
        return await _get_ads_agent().run({"type": "ads_plan", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][ads] plan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/competitor")
async def ads_competitor(body: AdsCompetitorRequest):
    """Research a competitor's ad strategy: platforms, spend signals, creative angles."""
    try:
        return await _get_ads_agent().run({"type": "ads_competitor", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][ads] competitor failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/math")
async def ads_math(body: AdsMathRequest):
    """Calculate PPC metrics: CPA, ROAS, break-even ROAS, CVR, CPC."""
    try:
        return await _get_ads_agent().run({"type": "ads_math", "params": {"metrics": body.model_dump()}})
    except Exception as e:
        logger.error(f"[VECTOR][api][ads] math failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test")
async def ads_test(body: AdsTestRequest):
    """Design an A/B test: hypothesis, sample size, duration, statistical significance."""
    try:
        return await _get_ads_agent().run({"type": "ads_test", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][ads] test failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dna")
async def ads_dna(body: AdsDnaRequest):
    """Extract brand DNA from a website: voice, palette, differentiators, ad angles."""
    try:
        return await _get_ads_agent().run({"type": "ads_dna", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][ads] dna failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create")
async def ads_create(body: AdsCreateRequest):
    """Generate campaign brief: headlines, copy variants, visual direction, platform adaptations."""
    try:
        return await _get_ads_agent().run({"type": "ads_create", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][ads] create failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate")
async def ads_generate(body: AdsGenerateRequest):
    """Generate ad images via AI (Gemini -> OpenAI -> Stability -> Replicate fallback)."""
    try:
        return await _get_ads_agent().run({"type": "ads_generate", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][ads] generate failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/photoshoot")
async def ads_photoshoot(body: AdsPhotoshootRequest):
    """Generate product photography in 5 styles: studio, floating, ingredient, in-use, lifestyle."""
    try:
        return await _get_ads_agent().run({"type": "ads_photoshoot", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][ads] photoshoot failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report")
async def ads_report(body: AdsReportRequest):
    """Generate a PDF audit report with health score charts and platform comparison."""
    try:
        return await _get_ads_agent().run({"type": "ads_report", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][ads] report failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/references")
async def ads_references():
    """List all available RAG knowledge references (platform specs, benchmarks, compliance)."""
    try:
        from districts.marketing.ads import list_references, list_templates
        return {"references": list_references(), "templates": list_templates()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    print("OK: ads.py router")
