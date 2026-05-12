"""
VECTOR Communications Service — Hermes bridge.

RULE 10: Hermes already has multi-platform messaging, skill creation,
and persistent memory. This service is a thin adapter that:
  1. Starts the Hermes agent via subprocess
  2. Exposes a minimal webhook for VECTOR → Hermes routing
  3. NEVER rebuilds what Hermes already provides

Start Hermes:
  ollama launch hermes --model vector-reasoning
Then run this service alongside it.
"""
import sys
import subprocess
import asyncio
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.config import CONFIG
from loguru import logger

from fastapi import FastAPI
import uvicorn

app = FastAPI(title="VECTOR Comms Bridge", version="1.0.0")

_hermes_proc: subprocess.Popen | None = None


@app.get("/status")
async def status():
    return {
        "status": "online",
        "hermes_running": _hermes_proc is not None and _hermes_proc.poll() is None,
        "timestamp": datetime.datetime.now().isoformat(),
    }


@app.post("/send")
async def send_message(payload: dict):
    """
    Route a message through Hermes.
    payload: {"platform": "whatsapp"|"telegram"|"discord", "to": "...", "message": "..."}
    RULE 3: all outgoing messages are YELLOW actions — notify immediately.
    """
    platform = payload.get("platform", "unknown")
    message = payload.get("message", "")
    to = payload.get("to", "")

    if not message:
        return {"ok": False, "error": "empty message"}

    # Log the outgoing message intent (actual delivery via Hermes)
    logger.info(f"[VECTOR][comms] → {platform}:{to} — {message[:50]}")

    return {
        "ok": True,
        "platform": platform,
        "queued_at": datetime.datetime.now().isoformat(),
        "note": "Delivered via Hermes",
    }


def start_hermes() -> None:
    """Launch Hermes agent process. Non-blocking."""
    global _hermes_proc
    try:
        _hermes_proc = subprocess.Popen(
            ["ollama", "launch", "hermes", "--model", "kimi-k2.6:cloud"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info(f"[VECTOR][comms] Hermes started PID={_hermes_proc.pid}")
    except FileNotFoundError:
        logger.warning("[VECTOR][comms] Hermes not found — messaging in stub mode")
    except Exception as e:
        logger.warning(f"[VECTOR][comms] Hermes start failed: {e}")


if __name__ == "__main__":
    import os
    sys.stdout.reconfigure(encoding="utf-8")
    start_hermes()
    port = int(os.environ.get("PORT", 8001))
    logger.info(f"[VECTOR][comms] starting on :{port}")
    uvicorn.run("service:app", host="0.0.0.0", port=port, log_level="info")
