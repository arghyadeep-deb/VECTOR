"""VECTOR control router - /control/* endpoints."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/control", tags=["control"])




@router.get("/pc/screenshot")
async def pc_screenshot():
    """Capture current screen."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "pc_screenshot", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][control] pc_screenshot failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class PcTypeReq(BaseModel):
    text: str = ""
    delay_ms: int = 50

@router.post("/pc/type")
async def pc_type(body: PcTypeReq):
    """Type text via keyboard (YELLOW gate)."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "pc_type", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][control] pc_type failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class PcClickReq(BaseModel):
    x: int = 0
    y: int = 0
    button: str = "left"

@router.post("/pc/click")
async def pc_click(body: PcClickReq):
    """Click at screen coordinates (YELLOW gate)."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "pc_click", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][control] pc_click failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class PcLaunchAppReq(BaseModel):
    app_name: str = ""
    args: str = ""

@router.post("/pc/launch-app")
async def pc_launch_app(body: PcLaunchAppReq):
    """Launch application (YELLOW gate)."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "pc_launch_app", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][control] pc_launch_app failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/phone/status")
async def phone_status():
    """ADB bridge connection status."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "phone_status", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][control] phone_status failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/phone/notifications")
async def phone_notifications():
    """Read phone notifications via ADB."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "phone_notifications", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][control] phone_notifications failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/phone/screenshot")
async def phone_screenshot():
    """Capture phone screen via ADB."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "phone_screenshot", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][control] phone_screenshot failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
