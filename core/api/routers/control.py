"""VECTOR control router - /control/* endpoints."""

__all__ = [
    "pc_click",
    "pc_launch_app",
    "pc_screenshot",
    "pc_type",
    "PcClickReq",
    "PcLaunchAppReq",
    "PcTypeReq",
    "phone_notifications",
    "phone_screenshot",
    "phone_status",
    "router",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/control", tags=["control"])


def _gateway_response(action_type: str, gate) -> dict:
    return {
        "status": "blocked" if not gate.approved else "not_executed",
        "action": action_type,
        "gateway": {
            "approved": gate.approved,
            "level": gate.level,
            "executed": gate.executed,
            "reason": gate.reason,
            "result": gate.result,
        },
    }


async def _dispatch_pc_action(action_type: str, params: dict) -> dict:
    from core.city.governor import GovernorCouncil
    from core.loop.permission_gateway import Action, PermissionGateway

    gate = await PermissionGateway().execute(
        Action(action_type=action_type, params=params, proposed_by="api.control")
    )
    if not gate.approved or not gate.executed:
        return _gateway_response(action_type, gate)

    gov = GovernorCouncil()
    return await gov.dispatch({"type": action_type, "params": params})


@router.get("/pc/screenshot")
async def pc_screenshot():
    """Capture current screen (YELLOW gate)."""
    try:
        return await _dispatch_pc_action("pc_screenshot", {})
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
        return await _dispatch_pc_action("pc_type", body.model_dump())
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
        return await _dispatch_pc_action("pc_click", body.model_dump())
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
        return await _dispatch_pc_action("pc_launch_app", body.model_dump())
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
