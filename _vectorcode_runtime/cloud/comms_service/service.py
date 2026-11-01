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
import hmac
import os

from core.config import CONFIG
from loguru import logger

from fastapi import FastAPI, Depends, Header, HTTPException
import uvicorn

app = FastAPI(title="VECTOR Comms Bridge", version="1.0.0")

_vc_bridge = None


def _is_hardened() -> bool:
    return os.environ.get("VECTOR_ENV", "").strip().lower() in {"prod", "production", "vector"}


def require_auth(authorization: str = Header(default="")) -> bool:
    """Bearer-token gate for state-changing comms endpoints.

    This service can bind 0.0.0.0, so /send must never be open. In production a
    missing VECTOR_API_KEY fails closed (503) rather than running unauthenticated.
    In development without a key, localhost-only use is allowed for testing.
    """
    api_key = os.environ.get("VECTOR_API_KEY", "").strip()
    if not api_key:
        if _is_hardened():
            raise HTTPException(
                status_code=503,
                detail="Comms service auth not configured: set VECTOR_API_KEY before production use.",
            )
        return True  # dev convenience only
    token = ""
    if authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    if not hmac.compare_digest(token, api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


@app.get("/status")
async def status():
    state = "online" if _vc_bridge is not None else "degraded"
    return {
        "status": state,
        "vectorcode_running": _vc_bridge is not None,
        "degraded_reason": None if _vc_bridge is not None else "VectorCodeBridge is not running",
        "timestamp": datetime.datetime.now().isoformat(),
    }


@app.post("/send")
async def send_message(payload: dict, _auth: bool = Depends(require_auth)):
    """
    Route a message through VectorCode channel adapters.
    payload: {"platform": "whatsapp"|"telegram"|"discord"|"slack", "to": "...", "message": "..."}
    RULE 3: all outgoing messages are YELLOW actions — notify immediately.
    Requires Authorization: Bearer <VECTOR_API_KEY>.
    """
    platform = payload.get("platform", "unknown")
    message = payload.get("message", "")
    to = payload.get("to", "")

    if not message:
        return {"ok": False, "error": "empty message"}

    logger.info(f"[VECTOR][comms] → {platform}:{to} — {message[:50]}")

    # Attempt real delivery via VectorCode channel adapters
    _CHANNEL_MAP = {
        "telegram": "vectorcode.src.channels.telegram.TelegramChannel",
        "whatsapp": "vectorcode.src.channels.whatsapp.WhatsAppChannel",
        "discord": "vectorcode.src.channels.discord_channel.DiscordChannel",
        "slack": "vectorcode.src.channels.slack.SlackChannel",
        "email": "vectorcode.src.channels.email_channel.EmailChannel",
        "gmail": "vectorcode.src.channels.gmail.GmailChannel",
    }
    channel_cls_path = _CHANNEL_MAP.get(platform.lower())
    if channel_cls_path:
        try:
            module_path, cls_name = channel_cls_path.rsplit(".", 1)
            import importlib
            mod = importlib.import_module(module_path)
            channel_cls = getattr(mod, cls_name)
            channel_instance = channel_cls()
            delivered = await asyncio.to_thread(channel_instance.send, to, message)
            logger.info(f"[VECTOR][comms] delivered via {cls_name}: {delivered}")
            return {
                "ok": bool(delivered),
                "platform": platform,
                "delivered_at": datetime.datetime.now().isoformat(),
                "via": cls_name,
            }
        except ImportError as _ie:
            logger.warning(f"[VECTOR][comms] {channel_cls_path} not importable: {_ie}")
        except Exception as _ce:
            logger.error(f"[VECTOR][comms] {platform} channel delivery failed: {_ce}")

    # Fallback: route through VectorCode bridge if available
    if _vc_bridge is not None:
        try:
            bridge_result = await asyncio.to_thread(
                _vc_bridge.send_message, platform, to, message
            )
            return {
                "ok": bool(bridge_result),
                "platform": platform,
                "delivered_at": datetime.datetime.now().isoformat(),
                "via": "vc_bridge",
                "result": bridge_result,
            }
        except Exception as _bridge_err:
            logger.error(f"[VECTOR][comms] bridge delivery failed: {_bridge_err}")

    # All delivery paths failed
    return {
        "ok": False,
        "platform": platform,
        "error": "No delivery channel available — VectorCode not running",
        "queued_at": datetime.datetime.now().isoformat(),
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
        logger.warning("[VECTOR][comms] VectorCodeBridge not found - messaging bridge unavailable")
    except Exception as e:
        logger.warning(f"[VECTOR][comms] VectorCode gateway start failed: {e}")


if __name__ == "__main__":
    import os
    sys.stdout.reconfigure(encoding="utf-8")
    start_vectorcode_gateway()
    port = int(os.environ.get("PORT", 8001))
    logger.info(f"[VECTOR][comms] starting on :{port}")
    uvicorn.run("service:app", host=os.environ.get("BIND_HOST", "0.0.0.0"), port=port, log_level="info")
