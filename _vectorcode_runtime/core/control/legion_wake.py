"""Configured Wake-on-LAN entrypoints for the Legion heavy node."""
from __future__ import annotations

from core.config import CONFIG
from core.control.wake_on_lan import WakeResult, send_magic_packet


def configured_legion_mac(prefer: str = "wifi") -> str:
    """Return the configured Legion MAC address, preferring WiFi by default."""
    wake_cfg = CONFIG.get("wake", {})
    wifi = wake_cfg.get("legion_wifi_mac", "")
    ethernet = wake_cfg.get("legion_ethernet_mac", "")
    if prefer == "ethernet":
        return ethernet or wifi
    return wifi or ethernet


def wake_legion(prefer: str = "wifi") -> WakeResult:
    """Wake the configured Legion node if a MAC address is available."""
    wake_cfg = CONFIG.get("wake", {})
    mac = configured_legion_mac(prefer=prefer)
    if not mac:
        return WakeResult(
            ok=False,
            mac="",
            broadcast=wake_cfg.get("legion_wake_broadcast", "255.255.255.255"),
            port=int(wake_cfg.get("legion_wake_port", 9)),
            error="LEGION_WIFI_MAC or LEGION_ETHERNET_MAC is not configured",
        )
    return send_magic_packet(
        mac,
        broadcast=wake_cfg.get("legion_wake_broadcast", "255.255.255.255"),
        port=int(wake_cfg.get("legion_wake_port", 9)),
    )

