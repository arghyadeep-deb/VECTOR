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
    from core.loop.permission_gateway import Action, PermissionGateway

    gate = await PermissionGateway().execute(
        Action(action_type=action_type, params=params, proposed_by="api.control")
    )
    if not gate.approved or not gate.executed:
        return _gateway_response(action_type, gate)

    # 2026-09-23 (fix, item 6 -- independent review finding): this used
    # to ALSO call Governor.dispatch({"type": action_type, ...}) here,
    # discarding `gate.result` entirely -- but Governor has no real
    # handler for pc_screenshot/pc_click/pc_type/pc_launch_app (no
    # DISTRICT_TASK_MAP entry, no agent-manifest capability, and the task
    # dict never carried the "action" field GUIAutomationAgent's run()
    # requires), so that second call silently did nothing real and could
    # return a misleading fallback-agent result or an apparent success
    # with no real click/type/launch/screenshot having occurred.
    # PermissionGateway._execute_action() now has real, dedicated
    # branches for all four of these action types (mirroring the
    # existing launch_app/run_shell_command pattern) that call
    # PCController directly -- `gate.result` IS the real result.
    return gate.result


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
    """ADB bridge connection status.

    Calls PhoneController directly: no district implements a "phone_status"
    task type, so dispatching through the Governor keyword-routed these
    requests to unrelated districts (2026-07-19 browser dogfood: /phone/status
    returned the communications district's EMAIL summary).
    """
    import asyncio
    from core.control.phone_controller import PhoneController
    try:
        pc = PhoneController()
        connected = await asyncio.to_thread(pc.is_connected)
        result = {"status": "ok", "connected": connected}
        if connected:
            result["current_app"] = await asyncio.to_thread(pc.current_app)
        else:
            # Diagnostics (2026-07-21): the API-process adb server and the
            # interactive-shell adb server can drift out of sync (different
            # process context spawns a fresh daemon). Surface exactly what
            # this process sees so the mismatch is debuggable without
            # restarting the whole API for every probe.
            ok, raw = await asyncio.to_thread(pc._run_adb, "devices", timeout=5)
            result["debug"] = {"adb_path": pc._adb_path, "run_ok": ok, "raw": raw}
        return result
    except Exception as e:
        logger.error("[VECTOR][control] phone_status failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/phone/notifications")
async def phone_notifications():
    """Read phone notifications via ADB (direct PhoneController call)."""
    import asyncio
    from core.control.phone_controller import PhoneController
    try:
        pc = PhoneController()
        if not await asyncio.to_thread(pc.is_connected):
            return {"status": "error", "reason": "phone not connected"}
        notes = await asyncio.to_thread(pc.get_notifications)
        return {"status": "ok", "notifications": notes}
    except Exception as e:
        logger.error("[VECTOR][control] phone_notifications failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/phone/screenshot")
async def phone_screenshot():
    """Capture phone screen via ADB (direct PhoneController call)."""
    import asyncio
    from core.control.phone_controller import PhoneController
    try:
        pc = PhoneController()
        if not await asyncio.to_thread(pc.is_connected):
            return {"status": "error", "reason": "phone not connected"}
        path = "./data/phone_screenshot.png"
        ok = await asyncio.to_thread(pc.take_screenshot, path)
        return {"status": "ok" if ok else "error", "path": path if ok else None}
    except Exception as e:
        logger.error("[VECTOR][control] phone_screenshot failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
# end of phone endpoints (2026-07-19 direct PhoneController wiring)
