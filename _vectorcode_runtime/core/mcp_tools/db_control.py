"""Multi-DB mesh control MCP tools (Phase 2 quarantine kill-switch).

Exposes the quarantine kill-switch + mesh status as MCP tools so the owner can
sever or restore a database from ANY device (phone/remote) via the command relay.
"""

from __future__ import annotations

from core.mcp_tools.error_handling import safe_json as _safe_json


def add_db_control_tools(mcp) -> None:
    """Register db_status / db_quarantine / db_reenable MCP tools."""

    @mcp.tool
    def db_status() -> str:
        """Show the multi-DB mesh: per-backend quarantine state, queue, last sync."""
        try:
            from core.memory.multi_db_manager import get_manager
            mgr = get_manager()
            return _safe_json({
                "backends": mgr.backend_status(),
                "quarantined": sorted(mgr._quarantined),
                **mgr.get_stats(),
            })
        except Exception as exc:
            return _safe_json({"error": str(exc)})

    @mcp.tool
    def db_quarantine(backend: str, reason: str = "manual") -> str:
        """Disconnect a cloud DB (supabase|turso|d1) from VECTOR. Writes/pulls skip it
        until db_reenable. Use when malware/corruption is suspected."""
        try:
            from core.memory.multi_db_manager import get_manager
            ok = get_manager().quarantine(backend, reason)
            return _safe_json({
                "quarantined": ok, "backend": backend, "reason": reason,
                "note": None if ok else "backend must be one of supabase|turso|d1 (local cannot be severed)",
            })
        except Exception as exc:
            return _safe_json({"error": str(exc)})

    @mcp.tool
    def db_reenable(backend: str) -> str:
        """Reconnect a previously quarantined cloud DB once the threat is cleared."""
        try:
            from core.memory.multi_db_manager import get_manager
            restored = get_manager().reenable(backend)
            return _safe_json({"reenabled": restored, "backend": backend})
        except Exception as exc:
            return _safe_json({"error": str(exc)})
