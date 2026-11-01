"""MCP router — /mcp/status."""

import sys

__all__ = [
    "mcp_status",
    "router",
]


from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/mcp", tags=["mcp"])

@router.get("/status")
async def mcp_status():
    """Check MCP server availability."""
    fastmcp_available = False
    vc_mcp_available = False
    transport = "unknown"
    try:
        try:
            import fastmcp
            fastmcp_available = True
        except ImportError:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

        try:
            from vectorcode.src.core.config import VCConfig
            vc_cfg = VCConfig()
            vc_mcp_available = True
            transport = getattr(vc_cfg, "mcp_transport", "unknown")
        except ImportError:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

        status = "ok" if fastmcp_available else "fastmcp_unavailable"
        if not fastmcp_available and not vc_mcp_available:
            status = "unavailable"
    except Exception as e:
        logger.warning(f"[VECTOR][api][mcp] status failed: {e}")
        status = "error"

    return {"fastmcp_available": fastmcp_available, "vc_mcp_available": vc_mcp_available, "status": status}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ mcp.py OK")
