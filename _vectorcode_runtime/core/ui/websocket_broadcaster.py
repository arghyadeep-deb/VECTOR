"""BroadcastSystem — publishes city_update, agent_movement, and event_particle
events to all connected WebSocket dashboard clients.

Integrates with the existing ConnectionManager in core/api/routers/websocket.py.
Safe to import from anywhere in VECTOR (never raises, RULE 2 compliant).
"""

import datetime

__all__ = [
    "broadcast",
    "BroadcastSystem",
]

import json
from typing import Optional

from loguru import logger

try:
    from core.api.routers.websocket import broadcast_event
except ImportError:
    broadcast_event = None
    logger.warning("[BroadcastSystem] websocket router not available — events will be no-ops")

# Also publish through the event_bus so /ws/state carries the same events
# to the JARVIS HUD frontend (which only listens on /ws/state for state_event types).
try:
    from core.event_bus.bus import get_event_bus as _get_bus, Event as _Event
    _event_bus_ok = True
except ImportError:
    _event_bus_ok = False


class BroadcastSystem:
    """Publishes structured events to dashboard WebSocket clients."""

    @staticmethod
    async def city_update(
        districts: list[dict],
    ) -> None:
        """Broadcast district HP/status changes to main /ws and /ws/state."""
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        district_list = [
            {
                "name": d.get("name", "unknown"),
                "hp": d.get("hp", 500),
                "color": d.get("color", "#00CFFF"),
                "position": d.get("position", [0, 0, 0]),
                "agents": d.get("agents", []),
            }
            for d in districts
        ]

        # Main /ws channel (consumed by old React dashboard)
        if broadcast_event is not None:
            try:
                await broadcast_event({"type": "city_update", "timestamp": ts, "districts": district_list})
            except Exception as e:
                logger.debug(f"[BroadcastSystem] city_update broadcast failed: {e}")

        # Also emit CITY_UPDATE through event_bus so /ws/state forwards it to HUD frontend
        if _event_bus_ok:
            try:
                bus = _get_bus()
                await bus.emit(_Event(
                    event_type="CITY_UPDATE",
                    data={"districts": district_list},
                    source="websocket_broadcaster",
                ))
            except Exception as e:
                logger.debug(f"[BroadcastSystem] city_update event_bus emit failed: {e}")

    @staticmethod
    async def agent_movement(
        agent_id: str,
        agent_name: str,
        district: str,
        status: str,
    ) -> None:
        """Broadcast agent state transition."""
        if broadcast_event is None:
            return
        payload = {
            "type": "agent_movement",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "agentId": agent_id,
            "agentName": agent_name,
            "district": district,
            "status": status,
        }
        try:
            await broadcast_event(payload)
        except Exception as e:
            logger.debug(f"[BroadcastSystem] agent_movement failed: {e}")

    @staticmethod
    async def event_particle(
        source_district: str,
        target_district: str,
        event_type: str = "communication",
    ) -> None:
        """Broadcast cross-district event for particle visualization."""
        if broadcast_event is None:
            return
        payload = {
            "type": "event_particle",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "from": source_district,
            "to": target_district,
            "timestamp_ts": datetime.datetime.now(datetime.timezone.utc).timestamp(),
            "eventType": event_type,
        }
        try:
            await broadcast_event(payload)
        except Exception as e:
            logger.debug(f"[BroadcastSystem] event_particle failed: {e}")

    @staticmethod
    async def globe_update(
        arcs: Optional[list[dict]] = None,
        pulses: Optional[list[dict]] = None,
    ) -> None:
        """Broadcast globe visualization data (flight arcs, earthquake pulses)."""
        if broadcast_event is None:
            return
        payload: dict = {
            "type": "globe_update",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        if arcs:
            payload["arcs"] = [
                {
                    "fromLat": a.get("fromLat", 0),
                    "fromLng": a.get("fromLng", 0),
                    "toLat": a.get("toLat", 0),
                    "toLng": a.get("toLng", 0),
                    "color": a.get("color", "#00CFFF"),
                }
                for a in arcs
            ]
        if pulses:
            payload["pulses"] = [
                {
                    "lat": p.get("lat", 0),
                    "lng": p.get("lng", 0),
                    "magnitude": p.get("magnitude", 1),
                }
                for p in pulses
            ]
        try:
            await broadcast_event(payload)
        except Exception as e:
            logger.debug(f"[BroadcastSystem] globe_update failed: {e}")


broadcast = BroadcastSystem()
