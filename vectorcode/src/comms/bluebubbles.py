"""BlueBubblesChannel — BlueBubbles (iMessage bridge) adapter."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from loguru import logger

from vectorcode.src.comms._abc import (
    BaseChannel,
    ChannelHandler,
    ChannelStatus,
)
from vectorcode.src.vc_core.events import EventBus, EventType
from vectorcode.src.vc_core.registry import ChannelRegistry

@ChannelRegistry.register("bluebubbles")
class BlueBubblesChannel(BaseChannel):
    """BlueBubbles (iMessage bridge) channel adapter.

    Parameters
    ----------
    url:
        BlueBubbles server URL.  Falls back to ``BLUEBUBBLES_URL`` env var.
    password:
        BlueBubbles server password.  Falls back to ``BLUEBUBBLES_PASSWORD``
        env var.
    bus:
        Optional event bus for publishing channel events.
    """

    channel_id = "bluebubbles"

    def __init__(
        self,
        url: str = "",
        *,
        password: str = "",
        bus: Optional[EventBus] = None,
    ) -> None:
        self._url = url or os.environ.get("BLUEBUBBLES_URL", "")
        self._password = password or os.environ.get("BLUEBUBBLES_PASSWORD", "")
        self._bus = bus
        self._handlers: List[ChannelHandler] = []
        self._status = ChannelStatus.DISCONNECTED

    # -- connection lifecycle ---------------------------------------------------

    def connect(self) -> None:
        """Mark as connected (send-only — no persistent connection)."""
        if not self._url or not self._password:
            logger.warning("No BlueBubbles URL or password configured")
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
        """Send an iMessage via the BlueBubbles API."""
        if not self._url or not self._password:
            logger.warning("Cannot send: no BlueBubbles credentials configured")
            return False

        try:
            import httpx

            url = f"{self._url}/api/v1/message/text"
            payload: Dict[str, Any] = {
                "chatGuid": channel,
                "message": content,
                "method": "private-api",
            }

            # FLAG FOR OWNER (not changed here): password sent as a URL query
            # param, same shape as this cycle's other "credentials in URL"
            # findings -- but BlueBubbles' private-api method documents this
            # exact ?password= convention with no header alternative, so
            # unlike those other instances this may be a vendor requirement,
            # not VECTOR choosing the weaker option. Confirm before changing.
            resp = httpx.post(
                url,
                params={"password": self._password},
                json=payload,
                timeout=10.0,
            )
            if resp.status_code < 300:
                self._publish_sent(channel, content, conversation_id)
                return True
            logger.warning(
                "BlueBubbles API returned status {}",
                resp.status_code,
            )
            return False
        except Exception as e:
            logger.debug("BlueBubbles send failed: {}", e)
            return False

    def status(self) -> ChannelStatus:
        """Return the current connection status."""
        return self._status

    def list_channels(self) -> List[str]:
        """Return available channel identifiers."""
        return ["bluebubbles"]

    def on_message(self, handler: ChannelHandler) -> None:
        """Register a callback for incoming messages."""
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

__all__ = ["BlueBubblesChannel"]
