"""Wake-on-LAN helpers for waking the Legion heavy node.

This module is intentionally small and side-effect free: importing it never sends
packets, and the public function returns structured status for callers/tests.
"""
from __future__ import annotations

import re
import socket
from dataclasses import dataclass


_MAC_RE = re.compile(r"^[0-9a-fA-F]{12}$")


@dataclass(frozen=True)
class WakeResult:
    ok: bool
    mac: str
    broadcast: str
    port: int
    error: str = ""


def normalize_mac(mac: str) -> str:
    """Return a 12-hex-digit MAC string or raise ValueError."""
    cleaned = re.sub(r"[^0-9a-fA-F]", "", mac or "")
    if not _MAC_RE.match(cleaned):
        raise ValueError("invalid MAC address")
    return cleaned.lower()


def build_magic_packet(mac: str) -> bytes:
    """Build the standard Wake-on-LAN magic packet for a MAC address."""
    clean = normalize_mac(mac)
    mac_bytes = bytes.fromhex(clean)
    return b"\xff" * 6 + mac_bytes * 16


def send_magic_packet(
    mac: str,
    *,
    broadcast: str = "255.255.255.255",
    port: int = 9,
    timeout_sec: float = 2.0,
) -> WakeResult:
    """Send a Wake-on-LAN magic packet over UDP broadcast.

    Returns a WakeResult instead of raising so command routers can degrade
    cleanly when WiFi/BIOS/network conditions do not support waking.
    """
    try:
        packet = build_magic_packet(mac)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout_sec)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(packet, (broadcast, int(port)))
        return WakeResult(ok=True, mac=normalize_mac(mac), broadcast=broadcast, port=int(port))
    except Exception as exc:
        return WakeResult(
            ok=False,
            mac=re.sub(r"[^0-9a-fA-F]", "", mac or "").lower(),
            broadcast=broadcast,
            port=int(port),
            error=str(exc),
        )

