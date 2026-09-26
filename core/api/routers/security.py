"""Security router — /security endpoints."""

import asyncio
import sys

__all__ = [
    "confirm_security_action",
    "router",
    "security_recent",
    "security_status",
]


import psutil

from fastapi import APIRouter, Request, HTTPException, Query
from loguru import logger

from core.api.schemas import SecurityStatusResponse, ProcessInfo, PermissionAuditEntry, SecurityRecentResponse
from core.api.crud import recall_episodes
from core.control.security.threat_detector import check_process_anomalies
from core.api.cache import security_cache

router = APIRouter(prefix="/security", tags=["security"])

@router.get("/recent", response_model=SecurityRecentResponse)
async def security_recent(limit: int = Query(15, ge=1, le=50)):
    """Get recent security events from episodic memory."""
    cache_key = f"recent_{limit}"
    cached = security_cache.get(cache_key)
    if cached:
        return cached
    try:
        events = recall_episodes("", limit=limit, event_type="security_scan")
        result = SecurityRecentResponse(events=events, count=len(events))
        security_cache.set(cache_key, result)
        return result
    except Exception as e:
        logger.error("[VECTOR][api][security] recent failed: {}", e)
        return SecurityRecentResponse(events=[], count=0, error="Internal server error")

def _collect_process_status() -> tuple[int, list[ProcessInfo]]:
    """Blocking work behind /security/status: the process-anomaly scan and the process table.

    2026-09-26: this used to run inline inside an `async def`, so every cache miss froze the whole event loop for ~8 s
    (measured: /loop/status waited 7.7 s behind it). The API process also runs the autonomous loop and the HUD's
    websockets, so all of them stalled together. It now runs in a worker thread (see security_status).
    """
    anomalies = check_process_anomalies()
    anomalies_found = sum(1 for a in anomalies if a.get("suspicious"))

    ncpu = psutil.cpu_count(logical=True) or 1
    processes: list[ProcessInfo] = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
        try:
            info = proc.info
            name = info.get('name') or 'unknown'
            if info.get('pid') == 0 or name == 'System Idle Process':
                continue  # the idle pseudo-process reports (idle x cores) percent -- it is not load
            processes.append(ProcessInfo(
                name=name[:50],
                # psutil's per-process cpu_percent is summed over cores (a busy process can read several hundred %);
                # normalise to share of the whole machine so the number means what a reader assumes.
                cpu=round(min(100.0, (info.get('cpu_percent') or 0.0) / ncpu), 1),
                mem=round(info.get('memory_percent') or 0.0, 1),
                status=info.get('status') or 'unknown',
            ))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    # Show top 20 by CPU
    processes.sort(key=lambda p: p.cpu, reverse=True)
    return anomalies_found, processes[:20]


@router.get("/status", response_model=SecurityStatusResponse)
async def security_status(request: Request):
    """Get overall security status and telemetry."""
    cached = security_cache.get("status")
    if cached:
        return cached
    try:
        anomalies_found, processes = await asyncio.to_thread(_collect_process_status)

        # Threat level logic
        threat_level = "low"
        if anomalies_found > 2:
            threat_level = "high"
        elif anomalies_found > 0:
            threat_level = "medium"

        # Get permission gateway audit log
        audit_log = []
        if hasattr(request.app.state, "permission_gateway") and request.app.state.permission_gateway:
            raw_log = request.app.state.permission_gateway.get_audit_log(limit=20)
            audit_log = [PermissionAuditEntry(**entry) for entry in raw_log]

        result = SecurityStatusResponse(
            threat_level=threat_level,
            active_scans=3,
            anomalies_found=anomalies_found,
            sandbox_status="active",
            processes=processes,
            audit_log=audit_log,
        )
        security_cache.set("status", result)
        return result
    except Exception as e:
        logger.error("[VECTOR][api][security] status failed: {}", e)
        raise HTTPException(status_code=500, detail="Internal server error")

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
