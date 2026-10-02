"""WebhookChannel — generic outbound webhook adapter with HMAC-SHA256 signing."""

from __future__ import annotations

from loguru import logger
from typing import Any, Dict, List, Optional

from vectorcode.src.channels._abc import (
    BaseChannel,
    ChannelHandler,
    ChannelStatus,
)
from vectorcode.src.core.events import EventBus, EventType
from vectorcode.src.core.registry import ChannelRegistry


try:
    from core.engine.webhook.hmac_signer import WebhookSigner as _Signer
    _signer = _Signer()
except Exception:
    _signer = None  # type: ignore[assignment]


@ChannelRegistry.register("webhook")
class WebhookChannel(BaseChannel):
    """Generic outbound webhook channel (send-only).

    Parameters
    ----------
    url:
        Target webhook URL.
    secret:
        Optional shared secret sent in the ``X-Webhook-Secret`` header.
    method:
        HTTP method (default ``POST``).
    bus:
        Optional event bus for publishing channel events.
    """

    channel_id = "webhook"

    def __init__(
        self,
        url: str = "",
        *,
        secret: str = "",
        method: str = "POST",
        bus: Optional[EventBus] = None,
    ) -> None:
        self._url = url
        self._secret = secret
        self._method = method.upper()
        self._bus = bus
        self._handlers: List[ChannelHandler] = []
        self._status = ChannelStatus.DISCONNECTED

    # -- connection lifecycle ---------------------------------------------------

    def connect(self) -> None:
        """Mark as connected (send-only — no persistent connection)."""
        if not self._url:
            logger.warning("No webhook URL configured")
            self._status = ChannelStatus.ERROR
            return
        self._status = ChannelStatus.CONNECTED

    def disconnect(self) -> None:
        """Mark as disconnected."""
        self._status = ChannelStatus.DISCONNECTED

    # -- send / receive --------------------------------------------------------

    def send(
        self,
        channel: str,
        content: str,
        *,
        conversation_id: str = "",
        metadata: Dict[str, Any] | None = None,
    ) -> bool:
        """POST a JSON payload to the configured webhook URL."""
        if not self._url:
            logger.warning("Cannot send: no webhook URL configured")
            return False

        from core.security.ssrf_guard import SSRFGuard
        guard_result = SSRFGuard(resolve_dns=True).check_url(self._url)
        if not guard_result.safe:
            logger.warning("Webhook send blocked by SSRF guard: {}", guard_result.reason)
            return False

        try:
            import httpx

            payload: Dict[str, Any] = {
                "channel": channel,
                "content": content,
            }
            if conversation_id:
                payload["conversation_id"] = conversation_id
            if metadata:
                payload["metadata"] = metadata

            headers: Dict[str, str] = {}
            if self._secret and _signer is not None:
                # HMAC-SHA256 signed — receivers verify with their copy of the secret
                body_bytes = __import__("json").dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
                headers = _signer.signed_headers(body_bytes, self._secret)
            elif self._secret:
                # Fallback: plain secret header when signer unavailable
                headers["X-Webhook-Secret"] = self._secret

            resp = httpx.request(
                self._method,
                self._url,
                json=payload,
                headers=headers,
                timeout=10.0,
            )
            if resp.status_code < 300:
                self._publish_sent(channel, content, conversation_id)
                return True
            logger.warning(
                "Webhook returned status %d",
                resp.status_code,
            )
            return False
        except Exception:
            logger.debug("Webhook send failed", exc_info=True)
            return False

    def status(self) -> ChannelStatus:
        """Return the current connection status."""
        return self._status

    def list_channels(self) -> List[str]:
        """Return available channel identifiers."""
        return ["webhook"]

    def on_message(self, handler: ChannelHandler) -> None:
        """Register a callback for incoming messages (no-op for webhook)."""
        self._handlers.append(handler)

    # -- internal helpers -------------------------------------------------------

    def _publish_sent(self, channel: str, content: str, conversation_id: str) -> None:
        """Publish a CHANNEL_MESSAGE_SENT event on the bus."""
        if self._bus is not None:
            self._bus.publish(
                EventType.CHANNEL_MESSAGE_SENT,
                {
                    "channel": channel,
                    "content": content,
                    "conversation_id": conversation_id,
                },
            )


__all__ = ["WebhookChannel"]
