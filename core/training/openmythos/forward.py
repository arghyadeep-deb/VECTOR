"""
Module: core/training/openmythos/forward.py
Webhook forwarder - receives events and forwards to V.E.C.T.O.R.
"""

import sys

__all__ = [
    "main",
    "WebhookForwarder",
]


from core.config import CONFIG
from loguru import logger
import hmac
import hashlib
import json
import os
import secrets
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime

try:
    from fastapi import FastAPI, Request, HTTPException, Header
    from fastapi.responses import JSONResponse
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    FastAPI = None

try:
    from core.memory.episodic import EpisodicMemory
except ImportError:
    EpisodicMemory = None


class WebhookForwarder:
    """FastAPI webhook forwarder for GitHub, Gmail, Calendar, and custom events."""

    def __init__(self):
        self.config = CONFIG.get("openmythos", {})
        self.webhook_secret = (
            os.environ.get("OPENMYTHOS_WEBHOOK_SECRET", "").strip()
            or str(self.config.get("webhook_secret", "")).strip()
        )
        if not self.webhook_secret:
            if os.environ.get("VECTOR_ENV", "").strip().lower() in {"prod", "production", "vector"}:
                raise RuntimeError("OPENMYTHOS_WEBHOOK_SECRET is required in production")
            self.webhook_secret = secrets.token_urlsafe(32)
        self.host = self.config.get("forward_host", "0.0.0.0")
        self.port = self.config.get("forward_port", 8001)
        self.app: Optional[Any] = None
        self.episodic = None
        self.event_handlers: Dict[str, callable] = {}

        if FASTAPI_AVAILABLE:
            self.app = FastAPI(title="V.E.C.T.O.R Webhook Forwarder", version="1.0.0")
            self._setup_routes()
            if EpisodicMemory:
                self.episodic = EpisodicMemory()
                logger.info("[OpenMythos] Episodic memory initialized")
        else:
            logger.warning("[OpenMythos] FastAPI not available, webhook server disabled")

        logger.info("[OpenMythos] Webhook forwarder initialized")

    def _setup_routes(self):
        """Set up FastAPI routes."""
        if not self.app:
            return

        @self.app.get("/")
        async def root():
            return {"status": "ok", "service": "V.E.C.T.O.R Webhook Forwarder", "version": "1.0.0"}

        @self.app.get("/health")
        async def health():
            return {"status": "healthy", "episodic": self.episodic is not None}

        @self.app.post("/forward")
        async def forward_event(request: Request, x_hub_signature_256: Optional[str] = Header(None)):
            """
            Main webhook endpoint that routes events to V.E.C.T.O.R.

            Expected payload formats:
            - GitHub: {"event": "github", "action": "push|pull_request|issues", "data": {...}}
            - Gmail: {"event": "gmail", "messages": [...]}
            - Calendar: {"event": "calendar", "events": [...]}
            - Custom: {"event": "custom", "source": "...", "data": {...}}
            """
            try:
                payload = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON payload")

            signature_valid = self._validate_signature(await request.body(), x_hub_signature_256)
            if not signature_valid and self.config.get("require_signature", True):
                logger.warning("[OpenMythos] Invalid webhook signature")
                raise HTTPException(status_code=401, detail="Invalid signature")

            event_type = request.headers.get("X-Webhook-Event", payload.get("event", "custom"))
            logger.info(f"[OpenMythos] Received webhook event: {event_type}")

            result = await self._route_event(event_type, payload)

            if self.episodic:
                self.episodic.store(
                    event_type=f"webhook_{event_type}",
                    content=json.dumps({"event": event_type, "source": payload.get("source", "unknown")}),
                    tags=["webhook", event_type],
                    context=payload,
                    source="openmythos_forward",
                )

            return JSONResponse(content={"status": "acknowledged", "event": event_type, "processed": result})

        @self.app.post("/forward/github")
        async def github_webhook(request: Request):
            """Dedicated GitHub webhook endpoint."""
            try:
                payload = await request.json()
                event_type = request.headers.get("X-GitHub-Event", "push")
                logger.info(f"[OpenMythos] GitHub webhook: {event_type}")
                return await self._handle_github(event_type, payload)
            except Exception as e:
                logger.error(f"[OpenMythos] GitHub webhook error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/forward/gmail")
        async def gmail_webhook(request: Request):
            """Dedicated Gmail webhook endpoint."""
            try:
                payload = await request.json()
                logger.info("[OpenMythos] Gmail webhook received")
                return await self._handle_gmail(payload)
            except Exception as e:
                logger.error(f"[OpenMythos] Gmail webhook error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/forward/calendar")
        async def calendar_webhook(request: Request):
            """Dedicated Calendar webhook endpoint."""
            try:
                payload = await request.json()
                logger.info("[OpenMythos] Calendar webhook received")
                return await self._handle_calendar(payload)
            except Exception as e:
                logger.error(f"[OpenMythos] Calendar webhook error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/forward/custom")
        async def custom_webhook(request: Request):
            """Custom webhook endpoint for user-defined integrations."""
            try:
                payload = await request.json()
                source = payload.get("source", "unknown")
                logger.info(f"[OpenMythos] Custom webhook from: {source}")
                return await self._handle_custom(source, payload)
            except Exception as e:
                logger.error(f"[OpenMythos] Custom webhook error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

    def _validate_signature(self, body: bytes, signature: Optional[str]) -> bool:
        """Validate webhook signature using HMAC-SHA256."""
        if not signature:
            return False
        if signature.startswith("sha256="):
            signature = signature[7:]
        expected = hmac.new(self.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def _route_event(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Route incoming event to appropriate handler."""
        handlers = {
            "github": self._handle_github,
            "gmail": self._handle_gmail,
            "calendar": self._handle_calendar,
            "custom": lambda _, p: self._handle_custom(p.get("source", "unknown"), p),
        }

        handler = handlers.get(event_type, lambda _, p: {"status": "no_handler"})
        return await handler(event_type, payload)

    async def _handle_github(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process GitHub webhook events."""
        data = payload
        repo = data.get("repository", {}).get("full_name", "unknown")
        action = data.get("action", event_type)

        logger.info(f"[OpenMythos] GitHub event: {action} on {repo}")

        if event_type == "push":
            commits = data.get("commits", [])
            for commit in commits:
                logger.info(f"[OpenMythos] Commit: {commit.get('message', '')[:50]}")
        elif event_type == "pull_request":
            pr = data.get("pull_request", {})
            logger.info(f"[OpenMythos] PR: {pr.get('title', '')} - {pr.get('state', '')}")
        elif event_type == "issues":
            issue = data.get("issue", {})
            logger.info(f"[OpenMythos] Issue: {issue.get('title', '')}")

        return {
            "event": "github",
            "type": event_type,
            "repo": repo,
            "action": action,
            "processed": True,
            "timestamp": datetime.now().isoformat(),
        }

    async def _handle_gmail(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process Gmail webhook events."""
        messages = payload.get("messages", [])
        results = []

        for msg in messages:
            msg_id = msg.get("id", "")
            subject = msg.get("subject", "")
            sender = msg.get("from", "")
            snippet = msg.get("snippet", "")[:100]

            logger.info(f"[OpenMythos] Gmail: {sender} - {subject}")

            results.append({
                "id": msg_id,
                "subject": subject,
                "from": sender,
                "snippet": snippet,
            })

        return {
            "event": "gmail",
            "count": len(results),
            "messages": results,
            "processed": True,
            "timestamp": datetime.now().isoformat(),
        }

    async def _handle_calendar(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process Calendar webhook events."""
        events = payload.get("events", [])
        results = []

        for event in events:
            event_id = event.get("id", "")
            title = event.get("summary", "Untitled")
            start = event.get("start", {})
            end = event.get("end", {})

            logger.info(f"[OpenMythos] Calendar event: {title}")

            results.append({
                "id": event_id,
                "title": title,
                "start": start.get("dateTime", start.get("date", "")),
                "end": end.get("dateTime", end.get("date", "")),
            })

        return {
            "event": "calendar",
            "count": len(results),
            "events": results,
            "processed": True,
            "timestamp": datetime.now().isoformat(),
        }

    async def _handle_custom(self, source: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process custom webhook events."""
        logger.info(f"[OpenMythos] Custom event from {source}")

        if source in self.event_handlers:
            handler = self.event_handlers[source]
            result = await handler(payload)
            return {"event": "custom", "source": source, "processed": True, "result": result}

        return {
            "event": "custom",
            "source": source,
            "processed": True,
            "timestamp": datetime.now().isoformat(),
        }

    def register_event_handler(self, source: str, handler: callable):
        """Register a custom event handler for a specific source."""
        self.event_handlers[source] = handler
        logger.info(f"[OpenMythos] Registered custom handler for: {source}")

    def get_app(self) -> Optional[Any]:
        """Get the FastAPI app instance."""
        return self.app

    async def start_server(self):
        """Start the webhook server."""
        if not self.app:
            logger.error("[OpenMythos] FastAPI not available, cannot start server")
            return

        import uvicorn
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        logger.info(f"[OpenMythos] Starting webhook server on {self.host}:{self.port}")
        await server.serve()


async def main():
    """Test the webhook forwarder."""
    forwarder = WebhookForwarder()
    if forwarder.app:
        logger.info(f"FastAPI app available at: {forwarder.host}:{forwarder.port}")

        logger.info(f"Endpoints: /forward, /forward/github, /forward/gmail, /forward/calendar, /forward/custom")

    else:
        logger.info("FastAPI not available")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
    print("✅ forward.py OK")
