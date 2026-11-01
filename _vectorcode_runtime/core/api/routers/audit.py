"""Audit router — /audit/recent + /audit/verify."""

from pathlib import Path
import sys

__all__ = [
    "audit_recent",
    "audit_verify",
    "router",
]

import json

from fastapi import APIRouter, Query
from loguru import logger

router = APIRouter(prefix="/audit", tags=["audit"])

@router.get("/recent")
async def audit_recent(limit: int = Query(10, ge=1, le=100)):
    """Get recent audit chain entries."""
    try:
        chain_path = Path.home() / ".vector_ca" / "audit" / "chain.jsonl"
        if not chain_path.exists():
            return {"total": 0, "verified": False, "entries": []}
        lines = chain_path.read_text(encoding="utf-8").strip().splitlines()
        entries = [json.loads(l) for l in lines[-limit:]]
        return {"total": len(entries), "verified": True, "entries": entries}
    except Exception as e:
        logger.warning(f"[VECTOR][api][audit] recent failed: {e}")
        return {"total": 0, "verified": False, "entries": []}


@router.get("/verify")
async def audit_verify():
    """Verify the integrity of the Merkle audit chain (Phase 1E)."""
    try:
        from core.audit.merkle_chain import get_audit_chain
        chain = get_audit_chain()
        result = chain.verify()
        if not result.valid:
            # Publish security alert on chain break
            try:
                from core.event_bus.bus import get_event_bus
                from core.event_bus.types import Event, EventType
                import asyncio
                bus = await get_event_bus()
                await bus.publish(Event(
                    event_type=EventType.SECURITY_ALERT,
                    data={"reason": "audit_chain_broken", "broken_at": result.broken_at,
                          "detail": result.reason},
                    source="audit.verify",
                ))
            except Exception as _ev_err:
                logger.warning(f"[VECTOR][audit] event publish failed: {_ev_err}")
        return {
            "valid": result.valid,
            "chain_length": result.total_entries,
            "broken_at": result.broken_at,
            "reason": result.reason,
        }
    except Exception as e:
        logger.error(f"[VECTOR][api][audit] verify failed: {e}")
        return {"valid": False, "chain_length": 0, "error": str(e)}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ audit.py OK")
