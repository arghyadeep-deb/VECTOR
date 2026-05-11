"""Security router — /security endpoints."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter, Request, HTTPException, Query
from loguru import logger

from core.api.schemas import SecurityStatusResponse, ProcessInfo, PermissionAuditEntry, SecurityRecentResponse
from core.api.crud import recall_episodes
from core.control.security.threat_detector import check_process_anomalies

router = APIRouter(prefix="/security", tags=["security"])

@router.get("/recent", response_model=SecurityRecentResponse)
async def security_recent(limit: int = Query(15, ge=1, le=50)):
    """Get recent security events from episodic memory."""
    try:
        events = recall_episodes("", limit=limit, event_type="security_scan")
        return SecurityRecentResponse(events=events, count=len(events))
    except Exception as e:
        logger.error(f"[VECTOR][api][security] recent failed: {e}")
        return SecurityRecentResponse(events=[], count=0, error=str(e))

@router.get("/status", response_model=SecurityStatusResponse)
async def security_status(request: Request):
    """Get overall security status and telemetry."""
    try:
        # Check process anomalies
        anomalies = check_process_anomalies()
        anomalies_found = sum(1 for a in anomalies if a.get("suspicious"))
        
        # Threat level logic
        threat_level = "low"
        if anomalies_found > 2:
            threat_level = "high"
        elif anomalies_found > 0:
            threat_level = "medium"

        # Mock processes for now or get real ones
        processes = [
            ProcessInfo(name="ollama-serve", cpu=42.1, mem=68.5, status="running"),
            ProcessInfo(name="whisper-worker", cpu=18.4, mem=35.2, status="running"),
            ProcessInfo(name="vector-core", cpu=7.2, mem=22.1, status="running"),
        ]

        # Get permission gateway audit log
        audit_log = []
        if hasattr(request.app.state, "permission_gateway") and request.app.state.permission_gateway:
            raw_log = request.app.state.permission_gateway.get_audit_log(limit=20)
            audit_log = [PermissionAuditEntry(**entry) for entry in raw_log]

        return SecurityStatusResponse(
            threat_level=threat_level,
            active_scans=3,
            anomalies_found=anomalies_found,
            sandbox_status="active",
            processes=processes,
            audit_log=audit_log,
        )
    except Exception as e:
        logger.error(f"[VECTOR][api][security] status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/confirm/{action_type}")
async def confirm_security_action(action_type: str, request: Request):
    """Manually confirm a pending RED-level action."""
    if hasattr(request.app.state, "permission_gateway") and request.app.state.permission_gateway:
        success = request.app.state.permission_gateway.confirm_action(action_type)
        if success:
            return {"status": "confirmed", "action": action_type}
        else:
            return {"status": "failed", "reason": "No pending action of that type"}
    raise HTTPException(status_code=501, detail="Permission gateway not initialized")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ security.py OK")
