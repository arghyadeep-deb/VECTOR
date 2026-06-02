"""Gateway router — /gateway/* endpoints for the HUD Approvals Panel (A16).

Exposes pending YELLOW/RED actions that require human approval and lets the
owner approve or reject them directly from the HUD.

Endpoints:
  GET  /gateway/pending          — list all actions awaiting owner decision
  POST /gateway/approve/{id}     — approve a pending action
  POST /gateway/reject/{id}      — reject (block) a pending action
"""

import sys

__all__ = ["router"]

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

router = APIRouter(prefix="/gateway", tags=["gateway"])


def _get_gw(request: Request):
    """Retrieve the shared PermissionGateway from app state, or create a
    transient one if the app hasn't initialised it yet (graceful fallback)."""
    gw = getattr(request.app.state, "permission_gateway", None)
    if gw is None:
        from core.loop.permission_gateway import PermissionGateway
        gw = PermissionGateway()
    return gw


@router.get("/pending")
async def get_pending_approvals(request: Request):
    """Return all YELLOW/RED actions currently awaiting owner approval."""
    try:
        gw = _get_gw(request)
        pending = gw.get_pending() if hasattr(gw, "get_pending") else []
        return {"pending": pending, "count": len(pending)}
    except Exception as e:
        logger.error(f"[VECTOR][api][gateway] get_pending failed: {e}")
        return {"pending": [], "count": 0, "error": str(e)}


@router.post("/approve/{action_id}")
async def approve_action(action_id: str, request: Request):
    """Approve a pending RED/YELLOW action by its action_type ID."""
    try:
        gw = _get_gw(request)
        result = gw.approve(action_id) if hasattr(gw, "approve") else {"status": "approved", "id": action_id}
        return result
    except Exception as e:
        logger.error(f"[VECTOR][api][gateway] approve failed for {action_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reject/{action_id}")
async def reject_action(action_id: str, request: Request):
    """Reject (block) a pending RED/YELLOW action by its action_type ID."""
    try:
        gw = _get_gw(request)
        result = gw.reject(action_id) if hasattr(gw, "reject") else {"status": "rejected", "id": action_id}
        return result
    except Exception as e:
        logger.error(f"[VECTOR][api][gateway] reject failed for {action_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("OK: gateway.py router")
