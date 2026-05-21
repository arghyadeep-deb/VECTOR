"""VECTOR design router - /design/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/design", tags=["design"])


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


class SpecComponentReq(BaseModel):
    name: str = ""
    component_type: str = "button"
    requirements: str = ""

@router.post("/component-spec")
async def spec_component(body: SpecComponentReq):
    """Component specification with accessibility."""
    try:
        return _run("spec_component", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][design] spec_component failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class ImagePromptReq(BaseModel):
    concept: str = ""
    style: str = "photorealistic"
    aspect: str = "16:9"

@router.post("/image-prompt")
async def image_prompt(body: ImagePromptReq):
    """Optimized AI image generation prompt."""
    try:
        return _run("image_prompt", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][design] image_prompt failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class UxResearchReq(BaseModel):
    product: str = ""
    target_user: str = ""
    research_type: str = "journey_map"

@router.post("/ux-research")
async def ux_research(body: UxResearchReq):
    """UX research: journey mapping, persona generation."""
    try:
        return _run("ux_research", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][design] ux_research failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class GenerateTokensReq(BaseModel):
    brand_name: str = ""
    primary_color: str = "#000000"
    style: str = "modern"

@router.post("/tokens")
async def generate_tokens(body: GenerateTokensReq):
    """Design system tokens: colors, spacing, typography."""
    try:
        return _run("generate_tokens", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][design] generate_tokens failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
