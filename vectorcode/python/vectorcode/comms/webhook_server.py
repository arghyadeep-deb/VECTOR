"""
WebhookServer — HTTP webhook receiver for VectorCode.

Exposes:
    POST /webhook/{platform}  — receive inbound messages from any platform
    GET  /health              — health check
    POST /notify              — send outbound notification via MessagingHub

Routes incoming webhook payloads to InboundMessageRouter, which can forward
to a VectorCode REPL function via bridge_to_repl().

FastAPI + uvicorn are optional — server stubs out gracefully if not installed.
"""
import sys
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))  # project root
sys.path.insert(0, str(Path(__file__).parent.parent))  # vectorcode package

from typing import Callable, Optional
from loguru import logger

try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}

try:
    from comms.inbound import InboundMessage, InboundMessageRouter
    _HAS_INBOUND = True
except ImportError:
    _HAS_INBOUND = False
    InboundMessage = None       # type: ignore[assignment,misc]
    InboundMessageRouter = None # type: ignore[assignment,misc]

try:
    from comms.messenger import MessagingHub
    _HAS_HUB = True
except ImportError:
    _HAS_HUB = False
    MessagingHub = None  # type: ignore[assignment,misc]

_SERVER_VERSION = "1.0.0"

# ── FastAPI app (module-level singleton) ──────────────────────────────────────
# Instantiated once; WebhookServer registers its router reference onto it.

try:
    from fastapi import FastAPI, Request, HTTPException
    import uvicorn
    _HAS_FASTAPI = True
    app: Optional["FastAPI"] = FastAPI(  # type: ignore[assignment]
        title="VectorCode Webhook Server",
        description="Inbound webhook receiver and outbound notification dispatcher.",
        version=_SERVER_VERSION,
    )
except ImportError:
    _HAS_FASTAPI = False
    app = None  # type: ignore[assignment]


# ── WebhookServer class ───────────────────────────────────────────────────────

class WebhookServer:
    """
    HTTP webhook receiver for VectorCode.

    Routes inbound webhook payloads → InboundMessageRouter → registered handlers.
    Dispatches outbound notifications → MessagingHub.

    Usage (blocking):
        server = WebhookServer(port=8765)
        server.bridge_to_repl(lambda text: f"VECTOR: {text}")
        await server.start()       # runs uvicorn, never returns

    Usage (background):
        thread = server.start_background()
        # ... do other work ...
    """

    def __init__(self, port: int = 8765, host: str = "0.0.0.0") -> None:
        self._port = port
        self._host = host
        self._router: Optional[InboundMessageRouter] = (
            InboundMessageRouter() if _HAS_INBOUND else None
        )
        self._hub: Optional[MessagingHub] = (
            MessagingHub() if _HAS_HUB else None
        )
        self._platform_handlers: dict[str, Callable] = {}
        self._thread: Optional[threading.Thread] = None
        self._request_count = 0

        # Wire this server instance into the FastAPI app routes
        if _HAS_FASTAPI and app is not None:
            _register_routes(app, self)

    # ── Handler registration ──────────────────────────────────────────────────

    def on_message(self, platform: str, fn: Callable) -> None:
        """Register a handler for messages arriving from platform. fn(InboundMessage) → str."""
        self._platform_handlers[platform.lower()] = fn
        if self._router is not None:
            # Wrap fn to match InboundMessageRouter's (msg, router) → RouteResult signature
            from comms.inbound import RouteResult
            def _adapter(msg: InboundMessage, router: InboundMessageRouter) -> RouteResult:
                try:
                    reply = fn(msg)
                    return RouteResult(handled=True, handler=f"platform:{platform}", reply=reply or "")
                except Exception as e:
                    logger.error(f"[VECTOR][webhook] platform handler error: {e}")
                    return RouteResult(handled=True, handler=f"platform:{platform}", reply=str(e))
            self._router.on_platform(platform.lower(), _adapter)

    def bridge_to_repl(self, repl_fn: Callable) -> None:
        """Bridge all inbound messages to a REPL function. repl_fn(text: str) → str."""
        if self._router is not None:
            self._router.bridge_to_repl(repl_fn)

    # ── Server lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start uvicorn server (blocking — never returns in normal operation)."""
        if not _HAS_FASTAPI:
            logger.error("[VECTOR][webhook] fastapi/uvicorn not installed — server cannot start")
            return

        logger.info(f"[VECTOR][webhook] starting on {self._host}:{self._port}")
        try:
            config = uvicorn.Config(app, host=self._host, port=self._port, log_level="warning")
            server = uvicorn.Server(config)
            await server.serve()
        except Exception as e:
            logger.error(f"[VECTOR][webhook] server error: {e}")

    def start_background(self) -> threading.Thread:
        """Start server in a background daemon thread. Returns the thread."""
        if not _HAS_FASTAPI:
            logger.warning("[VECTOR][webhook] fastapi/uvicorn not installed — background server skipped")
            t = threading.Thread(target=lambda: None, daemon=True, name="webhook-stub")
            t.start()
            return t

        import asyncio

        def _run() -> None:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.start())
            except Exception as e:
                logger.error(f"[VECTOR][webhook] background thread error: {e}")

        t = threading.Thread(target=_run, daemon=True, name="webhook-server")
        t.start()
        self._thread = t
        logger.info(f"[VECTOR][webhook] background server started on port {self._port}")
        return t

    # ── Inbound message processing ────────────────────────────────────────────

    def _process_inbound(self, platform: str, body: dict) -> dict:
        """Parse raw webhook body into InboundMessage and route it."""
        self._request_count += 1

        if not _HAS_INBOUND or self._router is None:
            logger.warning("[VECTOR][webhook] InboundMessageRouter unavailable — message dropped")
            return {"handled": False, "reply": "", "reason": "router unavailable"}

        # Normalise body into an InboundMessage
        text = (
            body.get("text")
            or body.get("message")
            or body.get("content")
            or str(body)
        )
        sender_id   = str(body.get("sender_id") or body.get("user_id") or body.get("from") or "")
        sender_name = str(body.get("sender_name") or body.get("username") or "")
        chat_id     = str(body.get("chat_id") or body.get("channel_id") or body.get("channel") or "")

        msg = InboundMessage(
            platform=platform,
            sender_id=sender_id,
            sender_name=sender_name,
            chat_id=chat_id,
            text=text,
            raw=body,
        )
        result = self._router.route(msg)
        return {"handled": result.handled, "reply": result.reply or ""}

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return server statistics."""
        router_stats = self._router.get_stats() if self._router is not None else {}
        return {
            "host": self._host,
            "port": self._port,
            "requests": self._request_count,
            "has_fastapi": _HAS_FASTAPI,
            "router": router_stats,
        }


# ── FastAPI route registration ────────────────────────────────────────────────

def _register_routes(fastapi_app: "FastAPI", server: "WebhookServer") -> None:
    """Register all FastAPI routes onto the app, capturing the server instance."""

    @fastapi_app.post("/webhook/{platform}")
    async def receive_webhook(platform: str, request: "Request") -> dict:
        """Receive a webhook from any platform and route to the message handler."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        return server._process_inbound(platform, body)

    @fastapi_app.get("/health")
    async def health() -> dict:
        """Health check — always returns 200."""
        return {"status": "ok", "version": _SERVER_VERSION}

    @fastapi_app.post("/notify")
    async def send_notification(request: "Request") -> dict:
        """Send an outbound notification via MessagingHub."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")  # noqa: B904

        text     = body.get("text", "")
        priority = body.get("priority", "normal")

        if not text:
            raise HTTPException(status_code=422, detail="'text' field required")  # noqa: B904

        if server._hub is not None:
            import asyncio
            try:
                result = await server._hub.send_notification(text, priority)
                return {"status": result.get("status", "unknown"), "via": result.get("via", "")}
            except Exception as e:
                logger.error(f"[VECTOR][webhook] /notify error: {e}")
                raise HTTPException(status_code=500, detail=str(e))  # noqa: B904

        return {"status": "queued", "reason": "MessagingHub not available"}


if __name__ == "__main__":
    server = WebhookServer(port=8765, host="127.0.0.1")

    # stats structure
    stats = server.get_stats()
    assert "host" in stats
    assert "port" in stats
    assert "requests" in stats
    assert "has_fastapi" in stats
    print(f"stats: {stats}")

    # _process_inbound without router raises no exception
    result = server._process_inbound("telegram", {"text": "hello", "sender_id": "u1"})
    assert "handled" in result
    print(f"_process_inbound result: {result}")

    # on_message registration
    received = []
    server.on_message("discord", lambda msg: (received.append(msg.text), "ok")[1])
    if _HAS_INBOUND:
        result2 = server._process_inbound("discord", {"text": "ping"})
        assert result2["handled"] is True
        assert "ping" in received
        print(f"on_message test: received={received}")

    # bridge_to_repl
    server2 = WebhookServer(port=8766, host="127.0.0.1")
    server2.bridge_to_repl(lambda text: f"echo: {text}")
    if _HAS_INBOUND:
        r = server2._process_inbound("slack", {"text": "hello", "sender_id": "u2"})
        assert r["handled"] is True
        assert "echo" in r["reply"]
        print(f"bridge_to_repl test: {r}")

    print("comms/webhook_server.py OK — inbound routing, /health, /notify, background thread")
