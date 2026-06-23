"""Node status model for the wake-before-dispatch orchestration seam.

docs/repo_analysis/_MASTER_TODO.md §4: "Node status model (online/asleep/
offline/unknown)". host/port are caller-supplied — VECTOR normally runs ON
the Legion machine itself, so this check is for a remote caller (a future
Termux poll, or a Cloudflare Worker heartbeat) asking "is the heavy node
reachable right now", not a fixed local config key.
"""
from __future__ import annotations

import socket
from enum import Enum
from typing import Any

from core.control.wake_on_lan import send_magic_packet

__all__ = ["NodeStatus", "check_node_status", "ensure_node_awake"]


class NodeStatus(str, Enum):
    ONLINE = "online"
    ASLEEP = "asleep"     # unreachable, but a MAC is known — wake is possible
    OFFLINE = "offline"   # unreachable, no MAC known — wake is not possible
    UNKNOWN = "unknown"   # no host configured at all


def check_node_status(host: str, port: int, *, mac: str = "", timeout: float = 2.0) -> NodeStatus:
    """Real, lightweight TCP probe — no live deployment needed to exercise
    this: a closed/refused local port is a real, observable network state."""
    if not host:
        return NodeStatus.UNKNOWN
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return NodeStatus.ONLINE
    except OSError:
        return NodeStatus.ASLEEP if mac else NodeStatus.OFFLINE


def ensure_node_awake(host: str, port: int, *, mac: str = "", timeout: float = 2.0,
                       broadcast: str = "255.255.255.255", wake_port: int = 9) -> dict[str, Any]:
    """Check status; if asleep, send a WoL magic packet. Never raises."""
    status = check_node_status(host, port, mac=mac, timeout=timeout)
    if status == NodeStatus.ONLINE:
        return {"status": "online", "wake_sent": False}
    if status == NodeStatus.ASLEEP:
        result = send_magic_packet(mac, broadcast=broadcast, port=wake_port)
        return {"status": "asleep", "wake_sent": True, "wake_ok": result.ok, "wake_error": result.error}
    if status == NodeStatus.OFFLINE:
        return {"status": "offline", "wake_sent": False, "error": "no MAC configured — cannot wake"}
    return {"status": "unknown", "wake_sent": False, "error": "no host configured"}
