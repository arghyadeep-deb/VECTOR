"""Security router — /security endpoints."""

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

__all__ = [
    "confirm_security_action",
    "router",
    "security_recent",
    "security_status",
]


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

_SNAPSHOT_SCRIPT = Path(__file__).resolve().parents[2] / "control" / "security" / "process_snapshot.py"
_TABLE_TTL_S = 120.0        # the per-process table is expensive even out of process; 2 minutes is fresh enough for a HUD
_SNAPSHOT_TIMEOUT_S = 90.0
_table: dict = {"rows": [], "anomalies": 0, "at": 0.0}
_refresh_task: asyncio.Task | None = None


def _run_snapshot_blocking() -> tuple[int, list[ProcessInfo]] | None:
    """Anomaly count + top-process table, both computed in child processes. None on any failure (caller keeps what it had)."""
    try:
        out = subprocess.run(
            [sys.executable, str(_SNAPSHOT_SCRIPT), "table", "20"],
            capture_output=True, text=True, timeout=_SNAPSHOT_TIMEOUT_S, check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
        rows = [ProcessInfo(**row) for row in json.loads(out)]
        anomalies = sum(1 for a in check_process_anomalies() if a.get("suspicious"))   # also a child process
        return anomalies, rows
    except Exception as e:  # noqa: BLE001 -- a failed scan must never take the endpoint down
        logger.warning("[VECTOR][api][security] process snapshot failed: {}", e)
        return None


async def _refresh_table() -> None:
    global _refresh_task
    try:
        got = await asyncio.to_thread(_run_snapshot_blocking)
        if got is not None:
            _table["anomalies"], _table["rows"], _table["at"] = got[0], got[1], time.monotonic()
    finally:
        _refresh_task = None


async def _process_table() -> list[ProcessInfo]:
    """Top processes by CPU, served stale-while-revalidate from a child-process scan.

    2026-09-27: the scan used to run in-process (worker thread since 2026-09-26). psutil on Windows holds the GIL for
    ~10 s per sweep, so a thread only moved the freeze around: /agents measured 15-27 s every ~30 s. The child process
    keeps the API's GIL free, and the table is refreshed at most every _TABLE_TTL_S instead of every cache miss.
    """
    global _refresh_task
    fresh = _table["rows"] and (time.monotonic() - _table["at"]) < _TABLE_TTL_S
    if not fresh and _refresh_task is None:
        _refresh_task = asyncio.create_task(_refresh_table())
    if not _table["rows"] and _refresh_task is not None:
        await asyncio.shield(_refresh_task)      # first ever call: nothing to serve yet, wait (without blocking the loop)
    return list(_table["rows"])


@router.get("/status", response_model=SecurityStatusResponse)
async def security_status(request: Request):
    """Get overall security status and telemetry."""
    cached = security_cache.get("status")
    if cached:
        return cached
    try:
        processes = await _process_table()
        anomalies_found = _table["anomalies"]

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
