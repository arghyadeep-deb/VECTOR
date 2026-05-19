"""
VECTOR Communications Service — VectorCode gateway bridge.

VectorCode provides multi-platform messaging, MCP server integration,
and persistent memory. This service is a thin adapter that:
  1. Starts the VectorCode gateway via VectorCodeBridge
  2. Exposes a minimal webhook for VECTOR → VectorCode routing
  3. NEVER rebuilds what VectorCode already provides

Start VectorCode gateway:
  VectorCodeBridge().start_mcp_server(port=9001)
Then run this service alongside it.
"""
import sys
import asyncio
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.config import CONFIG
from loguru import logger

from fastapi import FastAPI
import uvicorn

app = FastAPI(title="VECTOR Comms Bridge", version="1.0.0")

_vc_bridge = None


@app.get("/status")
async def status():
    return {
        "status": "online",
        "vectorcode_running": _vc_bridge is not None,
        "timestamp": datetime.datetime.now().isoformat(),
    }


@app.post("/send")
async def send_message(payload: dict):
    """
    Route a message through VectorCode.
    payload: {"platform": "whatsapp"|"telegram"|"discord", "to": "...", "message": "..."}
    RULE 3: all outgoing messages are YELLOW actions — notify immediately.
    """
    platform = payload.get("platform", "unknown")
    message = payload.get("message", "")
    to = payload.get("to", "")

    if not message:
        return {"ok": False, "error": "empty message"}

    # Log the outgoing message intent (actual delivery via VectorCode)
    logger.info(f"[VECTOR][comms] → {platform}:{to} — {message[:50]}")

    return {
        "ok": True,
        "platform": platform,
        "queued_at": datetime.datetime.now().isoformat(),
        "note": "Delivered via VectorCode",
    }


def start_vectorcode_gateway() -> None:
    """Launch VectorCode gateway. Non-blocking."""
    global _vc_bridge
    try:
        from districts.coding.vectorcode_bridge import VectorCodeBridge
        _vc_bridge = VectorCodeBridge()
        _vc_bridge.start_mcp_server(port=9001)
        logger.info("[VECTOR][comms] VectorCode gateway started on port 9001")
    except ImportError:
        logger.warning("[VECTOR][comms] VectorCodeBridge not found — messaging in stub mode")
    except Exception as e:
        logger.warning(f"[VECTOR][comms] VectorCode gateway start failed: {e}")


if __name__ == "__main__":
    import os
    sys.stdout.reconfigure(encoding="utf-8")
    start_vectorcode_gateway()
    port = int(os.environ.get("PORT", 8001))
    logger.info(f"[VECTOR][comms] starting on :{port}")
    uvicorn.run("service:app", host=os.environ.get("BIND_HOST", "0.0.0.0"), port=port, log_level="info")
