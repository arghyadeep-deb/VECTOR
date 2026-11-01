from __future__ import annotations

__all__ = [
    "force_relinquish",
    "force_takeover",
    "get_failover_instance",
    "get_failover_status",
    "receive_heartbeat",
    "reset_missed_heartbeats",
    "router",
]


import time
from typing import Any

from fastapi import APIRouter
from loguru import logger

from core.config import CONFIG
from core.resilience.hot_failover import HotFailover

router = APIRouter(prefix="/api/v1/failover", tags=["failover"])

_failover = HotFailover(is_primary=True)
_last_heartbeat: float = 0.0
_last_digest: dict[str, Any] = {}

@router.post("/heartbeat")
async def receive_heartbeat(data: dict) -> dict:
    global _last_heartbeat, _last_digest
    _last_heartbeat = time.time()
    _last_digest = data
    await _failover.receive_heartbeat(data)
    logger.debug("[HotFailover] heartbeat received (generation={})", data.get("generation", 0))
    return {"status": "ok", "timestamp": _last_heartbeat}

@router.get("/status")
async def get_failover_status() -> dict:
    now = time.time()
    missed = 0
    if _last_heartbeat > 0:
        interval = CONFIG.get("resilience", {}).get("failover", {}).get("heartbeat_interval", 5.0)
        max_missed = CONFIG.get("resilience", {}).get("failover", {}).get("max_missed_heartbeats", 3)
        missed = int((now - _last_heartbeat) / max(interval, 1))
    return {
        "is_primary": _failover.is_primary,
        "primary_active": _last_heartbeat > 0,
        "missed_heartbeats": max(0, missed),
        "max_missed_heartbeats": CONFIG.get("resilience", {}).get("failover", {}).get("max_missed_heartbeats", 3),
        "last_heartbeat": _last_heartbeat,
        "seconds_since_last_heartbeat": round(now - _last_heartbeat, 1) if _last_heartbeat > 0 else None,
        "last_generation": _last_digest.get("generation", 0),
        "timestamp": now,
    }

@router.post("/takeover")
async def force_takeover() -> dict:
    await _failover.take_over()
    logger.warning("[HotFailover] manual takeover initiated")
    return {"status": "ok", "message": "failover completed", "is_primary": _failover.is_primary}

@router.post("/relinquish")
async def force_relinquish() -> dict:
    await _failover.relinquish()
    logger.info("[HotFailover] manual relinquish initiated")
    return {"status": "ok", "message": "relinquished primary role", "is_primary": _failover.is_primary}

@router.post("/reset")
async def reset_missed_heartbeats() -> dict:
    global _last_heartbeat
    _last_heartbeat = time.time()
    _failover.missed_heartbeats = 0
    return {"status": "ok", "message": "heartbeat counter reset"}

def get_failover_instance() -> HotFailover:
    return _failover
