"""DB Guardian — auto-quarantine the cloud DB mesh on a security threat (Phase 2).

The owner's rule: "whenever a bug/malware/virus comes, disconnect the database
from VECTOR to keep it safe." This wires that as an automatic reflex:

  security district detects malware/corruption → publishes a SECURITY_ALERT /
  ANOMALY_DETECTED event → this guardian severs the cloud backends (Supabase,
  Turso, D1) via MultiDBManager.quarantine() and alerts the owner.

Local SQLite is never quarantined (it's the encrypted always-on fallback). The
owner re-enables backends manually with `db_reenable` once the threat is cleared.
Manual quarantine from any device goes through the MCP `db_quarantine` tool.
"""
from __future__ import annotations

from loguru import logger

from core.event_bus.types import Event, EventType

_SEVERE = {"critical", "high"}
_CLOUD_BACKENDS = ("supabase", "turso", "d1")


async def _alert_owner(msg: str) -> None:
    """Best-effort owner notification; always at least logs CRITICAL."""
    logger.critical(f"[VECTOR][db_guardian][ALERT] {msg}")
    try:
        from core.cloud.notify import notify_owner
        await notify_owner(msg, priority=2)
    except Exception:
        logger.exception("[VECTOR][db_guardian] notify_owner failed")


async def _on_security_event(event: Event) -> None:
    """Quarantine cloud backends when a severe security/anomaly event fires."""
    data = getattr(event, "data", None) or {}
    level = str(data.get("threat_level") or data.get("severity") or "").lower()
    if level not in _SEVERE:
        return
    try:
        from core.memory.multi_db_manager import get_manager
        mgr = get_manager()
        et = getattr(event.event_type, "value", event.event_type)
        reason = f"auto:{et}:level={level}:src={event.source or 'unknown'}"
        severed = [b for b in _CLOUD_BACKENDS if mgr.quarantine(b, reason)]
        await _alert_owner(
            f"Auto-quarantined cloud DBs {severed} after {level} security alert "
            f"from {event.source or 'unknown'}. Re-enable with db_reenable once safe."
        )
    except Exception as e:
        logger.error(f"[VECTOR][db_guardian] auto-quarantine failed: {e}")


async def publish_threat(
    threat_level: str,
    source: str,
    details: dict | None = None,
    bus=None,
) -> None:
    """Publish a SECURITY_ALERT so the guardian (and any other subscriber) reacts."""
    if bus is None:
        from core.event_bus.bus import get_event_bus
        bus = await get_event_bus()
    await bus.publish(Event(
        event_type=EventType.SECURITY_ALERT,
        data={"threat_level": threat_level, **(details or {})},
        source=source,
    ))


async def install_db_guardian(bus=None):
    """Subscribe the guardian to threat events. Call once at loop startup."""
    if bus is None:
        from core.event_bus.bus import get_event_bus
        bus = await get_event_bus()
    bus.subscribe(EventType.SECURITY_ALERT, _on_security_event)
    bus.subscribe(EventType.ANOMALY_DETECTED, _on_security_event)
    logger.info("[VECTOR][db_guardian] auto-quarantine subscriber installed")
    return bus
