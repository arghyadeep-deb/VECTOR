"""Gateway router — /gateway/* endpoints for the HUD Approvals Panel (A16).

Exposes pending YELLOW/RED actions that require human approval and lets the
owner approve or reject them directly from the HUD.

Endpoints:
  GET  /gateway/pending          — list all actions awaiting owner decision
  POST /gateway/approve/{id}     — approve a pending action
  POST /gateway/reject/{id}      — reject (block) a pending action
  GET  /gateway/trust                     — trust-ladder state per action type
  POST /gateway/trust/{action}/promote    — manually grant auto-execution
  POST /gateway/trust/{action}/demote     — revoke auto-execution
"""

import sys

__all__ = ["router"]

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from loguru import logger

router = APIRouter(prefix="/gateway", tags=["gateway"])

# Module-level singleton so all callers share the same instance even if
# app.state hasn't been wired (e.g. unit tests or alternative entry points).
_gw_singleton: "PermissionGateway | None" = None  # type: ignore[name-defined]


def _get_gw(request: Request):
    """Retrieve the shared PermissionGateway from app state, or fall back to
    a module-level singleton so all callers always share the same instance."""
    gw = getattr(request.app.state, "permission_gateway", None)
    if gw is None:
        global _gw_singleton
        if _gw_singleton is None:
            from core.loop.permission_gateway import PermissionGateway
            _gw_singleton = PermissionGateway()
        return _gw_singleton
    return gw


@router.get("/pending")
async def get_pending_approvals(request: Request):
    """Return all YELLOW/RED actions currently awaiting owner approval."""
    try:
        gw = _get_gw(request)
        pending = gw.get_pending() if hasattr(gw, "get_pending") else []
        return {"pending": pending, "count": len(pending)}
    except Exception as e:
        logger.error("[VECTOR][api][gateway] get_pending failed: {}", e)
        return {"pending": [], "count": 0, "error": "Internal server error"}


@router.post("/approve/{action_id}")
async def approve_action(action_id: str, request: Request):
    """Approve a pending RED/YELLOW action by its action_type ID."""
    try:
        gw = _get_gw(request)
        result = gw.approve(action_id) if hasattr(gw, "approve") else {"status": "approved", "id": action_id}
        return result
    except Exception as e:
        logger.error("[VECTOR][api][gateway] approve failed for {}: {}", action_id, e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/reject/{action_id}")
async def reject_action(action_id: str, request: Request):
    """Reject (block) a pending RED/YELLOW action by its action_type ID."""
    try:
        gw = _get_gw(request)
        result = gw.reject(action_id) if hasattr(gw, "reject") else {"status": "rejected", "id": action_id}
        return result
    except Exception as e:
        logger.error("[VECTOR][api][gateway] reject failed for {}: {}", action_id, e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/approve/{action_id}", response_class=HTMLResponse)
async def approve_action_get(action_id: str, request: Request):
    """Tap-to-approve from Pushover notification link (GET)."""
    try:
        gw = _get_gw(request)
        result = gw.approve(action_id) if hasattr(gw, "approve") else {"status": "approved"}
        status = result.get("status", "approved")
        if status == "approved":
            return HTMLResponse(
                "<html><body style='font-family:sans-serif;text-align:center;padding:40px'>"
                "<h1 style='color:green'>✅ Approved</h1>"
                f"<p>Action <b>{action_id}</b> has been approved.</p>"
                "<p>VECTOR will proceed.</p></body></html>"
            )
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;text-align:center;padding:40px'>"
            f"<h2>Status: {status}</h2><p>Action: {action_id}</p></body></html>"
        )
    except Exception as e:
        logger.error("[VECTOR][api][gateway] GET approve failed for {}: {}", action_id, e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/reject/{action_id}", response_class=HTMLResponse)
async def reject_action_get(action_id: str, request: Request):
    """Tap-to-reject from Pushover notification link (GET)."""
    try:
        gw = _get_gw(request)
        result = gw.reject(action_id) if hasattr(gw, "reject") else {"status": "rejected"}
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;text-align:center;padding:40px'>"
            "<h1 style='color:red'>❌ Rejected</h1>"
            f"<p>Action <b>{action_id}</b> has been blocked.</p>"
            "<p>VECTOR will not proceed.</p></body></html>"
        )
    except Exception as e:
        logger.error("[VECTOR][api][gateway] GET reject failed for {}: {}", action_id, e)
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Trust ladder (earned autonomy) ──────────────────────────────────────────

def _get_trust():
    from core.loop.trust_ladder import get_trust_ladder
    return get_trust_ladder()


@router.get("/trust")
async def trust_status():
    """Trust-ladder state per action type: streaks, promotions, auto-exec counts."""
    try:
        ladder = _get_trust()
        rows = ladder.status()
        return {
            "actions": rows,
            "promoted_count": sum(1 for r in rows if r.get("promoted")),
            "recent": ladder.recent_changes(days=7),
        }
    except Exception as e:
        logger.error("[VECTOR][api][gateway] trust status failed: {}", e)
        return {"actions": [], "promoted_count": 0, "error": "Internal server error"}


@router.post("/trust/{action_type}/promote")
async def trust_promote(action_type: str, request: Request):
    """Manually grant auto-execution to a YELLOW action type (owner override).
    RED/FORBIDDEN actions never participate — the gateway ignores trust for them."""
    try:
        gw = _get_gw(request)
        tier = gw.classify(action_type) if hasattr(gw, "classify") else "UNKNOWN"
        if tier != "YELLOW":
            raise HTTPException(
                status_code=400,
                detail=f"Only YELLOW actions can be promoted (this is {tier})")
        _get_trust().promote(action_type)
        return {"status": "promoted", "action_type": action_type}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[VECTOR][api][gateway] trust promote failed for {}: {}", action_type, e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/trust/{action_type}/demote")
async def trust_demote(action_type: str):
    """Revoke auto-execution — action returns to owner-gated YELLOW flow."""
    try:
        _get_trust().demote(action_type, "owner via API")
        return {"status": "demoted", "action_type": action_type}
    except Exception as e:
        logger.error("[VECTOR][api][gateway] trust demote failed for {}: {}", action_type, e)
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("OK: gateway.py router")
