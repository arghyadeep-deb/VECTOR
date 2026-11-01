"""Generic inbound webhook server — FastAPI-based, signature verification, event routing."""

import sys


from loguru import logger

import asyncio
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

try:
    from fastapi import FastAPI, Request, Response
    from fastapi.responses import JSONResponse
    _FASTAPI_AVAILABLE = True
except ImportError:
    FastAPI = None  # type: ignore[assignment,misc]
    Request = None  # type: ignore[assignment]
    Response = None  # type: ignore[assignment]
    JSONResponse = None  # type: ignore[assignment]
    _FASTAPI_AVAILABLE = False
    logger.warning("[VECTOR][webhook] fastapi not installed — webhook server unavailable")

try:
    import uvicorn
    _UVICORN_AVAILABLE = True
except ImportError:
    uvicorn = None  # type: ignore[assignment]
    _UVICORN_AVAILABLE = False
    logger.warning("[VECTOR][webhook] uvicorn not installed — webhook server unavailable")

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class WebhookEvent:
    platform: str       # "github", "gitlab", "custom", etc.
    event_type: str     # "push", "pull_request", "ping", etc.
    payload: dict
    headers: dict
    raw_body: bytes
    timestamp: str = ""

# ---------------------------------------------------------------------------
# WebhookServer
# ---------------------------------------------------------------------------

_ANY_EVENT = "__ANY__"

class WebhookServer:
    """FastAPI-based inbound webhook server with HMAC signature verification."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        *,
        path_prefix: str = "/webhook",
    ) -> None:
        self.host = host
        self.port = port
        self.path_prefix = path_prefix.rstrip("/")
        self._handlers: dict[str, list[Callable]] = {}   # event_type -> callbacks
        self._secrets: dict[str, str] = {}               # platform -> secret
        self._app: Optional[Any] = None                  # FastAPI instance
        self._server_task: Optional[asyncio.Task] = None
        self._uvicorn_server: Optional[Any] = None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_secret(self, platform: str, secret: str) -> None:
        """Register an HMAC secret for *platform* (e.g. "github")."""
        self._secrets[platform.lower()] = secret
        logger.debug(f"[VECTOR][webhook] Registered secret for platform '{platform}'")

    def on_event(self, event_type: str | list[str], callback: Callable) -> None:
        """Register *callback* for one or more event type strings.

        callback signature: async (event: WebhookEvent) -> None
        """
        types = [event_type] if isinstance(event_type, str) else list(event_type)
        for et in types:
            self._handlers.setdefault(et, []).append(callback)
            logger.debug(f"[VECTOR][webhook] Handler registered for event '{et}'")

    def on_any(self, callback: Callable) -> None:
        """Register *callback* for every event regardless of type."""
        self._handlers.setdefault(_ANY_EVENT, []).append(callback)
        logger.debug("[VECTOR][webhook] Catch-all handler registered")

    # ------------------------------------------------------------------
    # App builder
    # ------------------------------------------------------------------

    def build_app(self) -> Any:
        """Build and return the FastAPI app.  Registers all routes."""
        if not _FASTAPI_AVAILABLE:
            logger.error("[VECTOR][webhook] fastapi not available — cannot build app")
            return None

        app = FastAPI(title="VectorCode Webhook Server", version="1.0")

        # ------ health check ------
        @app.get("/health")
        async def health() -> dict:
            return {"status": "ok", "version": "1.0"}

        # ------ notify shortcut ------
        @app.post("/notify")
        async def notify(request: Request) -> Response:
            try:
                body = await request.body()
                payload = json.loads(body) if body else {}
            except Exception:
                payload = {}
            event = WebhookEvent(
                platform="internal",
                event_type="notify",
                payload=payload,
                headers=dict(request.headers),
                raw_body=body if body else b"",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            await self._dispatch(event)
            return JSONResponse({"status": "dispatched"})

        # ------ per-platform endpoint ------
        @app.post(f"{self.path_prefix}/{{platform}}")
        async def receive_webhook(platform: str, request: Request) -> Response:
            body = await request.body()
            headers = dict(request.headers)

            # Signature verification
            if not self._verify_signature(platform, body, headers):
                logger.warning(
                    f"[VECTOR][webhook] Signature mismatch for platform '{platform}'"
                )
                return JSONResponse({"error": "invalid signature"}, status_code=403)

            # Parse JSON
            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError as exc:
                logger.warning(f"[VECTOR][webhook] JSON parse error: {exc}")
                return JSONResponse({"error": "invalid JSON"}, status_code=400)

            detected_platform = self._detect_platform(headers) or platform
            event_type = self._detect_event_type(detected_platform, headers, payload)

            event = WebhookEvent(
                platform=detected_platform,
                event_type=event_type,
                payload=payload,
                headers=headers,
                raw_body=body,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            await self._dispatch(event)
            return JSONResponse({"status": "ok"})

        self._app = app
        return app

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the uvicorn server in a background asyncio task."""
        if not _FASTAPI_AVAILABLE or not _UVICORN_AVAILABLE:
            logger.error(
                "[VECTOR][webhook] fastapi or uvicorn not installed — "
                "run: pip install fastapi uvicorn"
            )
            return

        if self._app is None:
            self.build_app()

        config = uvicorn.Config(
            self._app,
            host=self.host,
            port=self.port,
            log_level="warning",  # suppress uvicorn's own noisy access logs
        )
        self._uvicorn_server = uvicorn.Server(config)

        self._server_task = asyncio.create_task(
            self._uvicorn_server.serve(),
            name="webhook-server",
        )
        logger.info(
            f"[VECTOR][webhook] Server started -> http://{self.host}:{self.port}"
            f"{self.path_prefix}/{{platform}}"
        )

    async def stop(self) -> None:
        """Gracefully stop the uvicorn server."""
        if self._uvicorn_server is not None:
            self._uvicorn_server.should_exit = True
        if self._server_task is not None:
            try:
                await asyncio.wait_for(self._server_task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._server_task.cancel()
            self._server_task = None
        logger.info("[VECTOR][webhook] Server stopped")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _verify_signature(self, platform: str, body: bytes, headers: dict) -> bool:
        """
        Verify the request signature for *platform*.

        GitHub  -> X-Hub-Signature-256 = "sha256=<hex>"  (HMAC-SHA256)
        GitLab  -> X-Gitlab-Token = plain secret token
        Others  -> skip if no secret registered for the platform
        """
        platform_key = platform.lower()
        secret = self._secrets.get(platform_key, "")
        if not secret:
            # No secret registered — accept all
            return True

        plat = self._detect_platform(headers) or platform_key

        if plat == "github":
            sig_header = headers.get("x-hub-signature-256", "")
            if not sig_header.startswith("sha256="):
                return False
            received = sig_header[len("sha256="):]
            expected = hmac.new(
                secret.encode(), body, hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(received, expected)

        if plat == "gitlab":
            received_token = headers.get("x-gitlab-token", "")
            return hmac.compare_digest(received_token, secret)

        # Generic HMAC-SHA256 fallback
        sig_header = (
            headers.get("x-hub-signature-256", "")
            or headers.get("x-signature-256", "")
        )
        if sig_header.startswith("sha256="):
            received = sig_header[len("sha256="):]
            expected = hmac.new(
                secret.encode(), body, hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(received, expected)

        # No signature header found — reject if secret is set
        return False

    def _detect_platform(self, headers: dict) -> str:
        """Infer the originating platform from request headers."""
        # GitHub
        if "x-github-event" in headers or "x-github-delivery" in headers:
            return "github"
        # GitLab
        if "x-gitlab-event" in headers or "x-gitlab-token" in headers:
            return "gitlab"
        # Jira
        if "x-atlassian-token" in headers:
            return "jira"
        # Bitbucket
        if "x-event-key" in headers and "bitbucket" in headers.get("user-agent", "").lower():
            return "bitbucket"
        # Stripe
        if "stripe-signature" in headers:
            return "stripe"
        return "custom"

    def _detect_event_type(self, platform: str, headers: dict, payload: dict) -> str:
        """Extract the event type string from platform-specific headers / payload."""
        if platform == "github":
            return headers.get("x-github-event", "unknown")
        if platform == "gitlab":
            return headers.get("x-gitlab-event", payload.get("object_kind", "unknown"))
        if platform == "jira":
            return payload.get("webhookEvent", "unknown")
        if platform == "bitbucket":
            return headers.get("x-event-key", "unknown")
        if platform == "stripe":
            return payload.get("type", "unknown")
        # Generic: look for common keys
        for key in ("event", "event_type", "type", "action"):
            if key in payload:
                return str(payload[key])
        return "unknown"

    async def _dispatch(self, event: WebhookEvent) -> None:
        """Call all registered handlers that match *event.event_type* + catch-all handlers."""
        handlers: list[Callable] = []
        # Specific handlers
        handlers.extend(self._handlers.get(event.event_type, []))
        # Catch-all handlers
        handlers.extend(self._handlers.get(_ANY_EVENT, []))

        if not handlers:
            logger.debug(
                f"[VECTOR][webhook] No handlers for event "
                f"'{event.platform}/{event.event_type}'"
            )
            return

        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.error(
                    f"[VECTOR][webhook] Handler error for "
                    f"'{event.platform}/{event.event_type}': {exc}"
                )

# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_server_singleton: Optional[WebhookServer] = None

def get_webhook_server(port: int = 8765) -> WebhookServer:
    """Return a module-level singleton WebhookServer on *port*."""
    global _server_singleton
    if _server_singleton is None:
        _server_singleton = WebhookServer(port=port)
    return _server_singleton

# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("[VECTOR][webhook] Running smoke test…")

    # Test 1: create WebhookServer — no crash
    server = WebhookServer(host="127.0.0.1", port=19999)
    assert server.host == "127.0.0.1"
    assert server.port == 19999
    logger.info("[VECTOR][webhook] WebhookServer init ✅")

    # Test 2: build_app() — _app is not None (if fastapi available)
    app = server.build_app()
    if _FASTAPI_AVAILABLE:
        assert app is not None, "build_app() returned None despite fastapi being available"
        assert server._app is not None
        logger.info("[VECTOR][webhook] build_app() -> FastAPI app created ✅")
    else:
        logger.warning("[VECTOR][webhook] fastapi not installed — build_app() returned None (expected)")

    # Test 3: register_secret and _verify_signature
    server.register_secret("github", "mysecret")
    body = b'{"test": true}'
    import hmac as _hmac
    import hashlib as _hashlib
    good_sig = "sha256=" + _hmac.new(b"mysecret", body, _hashlib.sha256).hexdigest()
    headers_good = {"x-github-event": "push", "x-hub-signature-256": good_sig}
    headers_bad = {"x-github-event": "push", "x-hub-signature-256": "sha256=badhex"}

    assert server._verify_signature("github", body, headers_good) is True
    assert server._verify_signature("github", body, headers_bad) is False
    logger.info("[VECTOR][webhook] _verify_signature GitHub HMAC ✅")

    # Test 4: _detect_platform
    assert server._detect_platform({"x-github-event": "push"}) == "github"
    assert server._detect_platform({"x-gitlab-event": "push"}) == "gitlab"
    assert server._detect_platform({"stripe-signature": "t=..."}) == "stripe"
    assert server._detect_platform({}) == "custom"
    logger.info("[VECTOR][webhook] _detect_platform ✅")

    # Test 5: _detect_event_type
    assert server._detect_event_type("github", {"x-github-event": "pull_request"}, {}) == "pull_request"
    assert server._detect_event_type("gitlab", {"x-gitlab-event": "Push Hook"}, {}) == "Push Hook"
    assert server._detect_event_type("custom", {}, {"event_type": "deploy"}) == "deploy"
    logger.info("[VECTOR][webhook] _detect_event_type ✅")

    # Test 6: on_event + _dispatch
    received_events: list[WebhookEvent] = []

    async def handler(event: WebhookEvent) -> None:
        received_events.append(event)

    server.on_event("push", handler)
    server.on_any(handler)

    async def _dispatch_test() -> None:
        evt = WebhookEvent(
            platform="github",
            event_type="push",
            payload={"ref": "refs/heads/main"},
            headers={},
            raw_body=b"{}",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        await server._dispatch(evt)

    asyncio.run(_dispatch_test())
    assert len(received_events) == 2, f"Expected 2 handler calls, got {len(received_events)}"
    logger.info("[VECTOR][webhook] on_event + _dispatch ✅")

    # Test 7: singleton factory
    s1 = get_webhook_server()
    s2 = get_webhook_server()
    assert s1 is s2, "Singleton not returning same instance"
    logger.info("[VECTOR][webhook] get_webhook_server() singleton ✅")

    logger.info("[VECTOR][webhook] All smoke tests passed")
    sys.stdout.buffer.write(b"[OK] webhook_server.py OK\n")
