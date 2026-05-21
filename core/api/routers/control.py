"""VECTOR control router - /control/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/control", tags=["control"])


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


@router.get("/pc/screenshot")
async def pc_screenshot():
    """Capture current screen."""
    try:
        return _run("pc_screenshot", {})
    except Exception as e:
        logger.error("[VECTOR][control] pc_screenshot failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class PcTypeReq(BaseModel):
    text: str = ""
    delay_ms: int = 50

@router.post("/pc/type")
async def pc_type(body: PcTypeReq):
    """Type text via keyboard (YELLOW gate)."""
    try:
        return _run("pc_type", body.model_dump())
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
    try:
        return _run("pc_click", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][control] pc_click failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class PcLaunchAppReq(BaseModel):
    app_name: str = ""
    args: str = ""

@router.post("/pc/launch-app")
async def pc_launch_app(body: PcLaunchAppReq):
    """Launch application (YELLOW gate)."""
    try:
        return _run("pc_launch_app", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][control] pc_launch_app failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/phone/status")
async def phone_status():
    """ADB bridge connection status."""
    try:
        return _run("phone_status", {})
    except Exception as e:
        logger.error("[VECTOR][control] phone_status failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/phone/notifications")
async def phone_notifications():
    """Read phone notifications via ADB."""
    try:
        return _run("phone_notifications", {})
    except Exception as e:
        logger.error("[VECTOR][control] phone_notifications failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/phone/screenshot")
async def phone_screenshot():
    """Capture phone screen via ADB."""
    try:
        return _run("phone_screenshot", {})
    except Exception as e:
        logger.error("[VECTOR][control] phone_screenshot failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
