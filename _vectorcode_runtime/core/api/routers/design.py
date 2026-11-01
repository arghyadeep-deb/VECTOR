"""VECTOR design router - /design/* endpoints."""

__all__ = [
    "generate_tokens",
    "GenerateTokensReq",
    "image_prompt",
    "ImagePromptReq",
    "router",
    "spec_component",
    "SpecComponentReq",
    "ux_research",
    "UxResearchReq",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/design", tags=["design"])


class SpecComponentReq(BaseModel):
    name: str = ""
    component_type: str = "button"
    requirements: str = ""

@router.post("/component-spec")
async def spec_component(body: SpecComponentReq):
    """Component specification with accessibility."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "spec_component", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][design] spec_component failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class ImagePromptReq(BaseModel):
    concept: str = ""
    style: str = "photorealistic"
    aspect: str = "16:9"

@router.post("/image-prompt")
async def image_prompt(body: ImagePromptReq):
    """Optimized AI image generation prompt."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "image_prompt", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][design] image_prompt failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class UxResearchReq(BaseModel):
    product: str = ""
    target_user: str = ""
    research_type: str = "journey_map"

@router.post("/ux-research")
async def ux_research(body: UxResearchReq):
    """UX research: journey mapping, persona generation."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "ux_research", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][design] ux_research failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class GenerateTokensReq(BaseModel):
    brand_name: str = ""
    primary_color: str = "#000000"
    style: str = "modern"

@router.post("/tokens")
async def generate_tokens(body: GenerateTokensReq):
    """Design system tokens: colors, spacing, typography."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "generate_tokens", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][design] generate_tokens failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
