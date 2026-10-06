"""IRCChannel — IRC adapter using stdlib socket."""

from __future__ import annotations

from loguru import logger
import os
import socket
import ssl
from typing import Any, Dict, List, Optional

from vectorcode.src.channels._abc import (
    BaseChannel,
    ChannelHandler,
    ChannelStatus,
)
from vectorcode.src.core.events import EventBus, EventType
from vectorcode.src.core.registry import ChannelRegistry


def _irc_value(value: str) -> str:
    """Reject values that could inject additional IRC protocol commands."""
    if "\r" in value or "\n" in value:
        raise ValueError("IRC values must not contain CR or LF")
    return value



@ChannelRegistry.register("irc")
class IRCChannel(BaseChannel):
    """IRC channel adapter using stdlib socket (send-only).

    Parameters
    ----------
    server:
        IRC server hostname.  Falls back to ``IRC_SERVER`` env var.
    port:
        IRC server port (default 6667).  Falls back to ``IRC_PORT`` env var.
    nick:
        IRC nickname.  Falls back to ``IRC_NICK`` env var.
    password:
        Optional server password.  Falls back to ``IRC_PASSWORD`` env var.
    use_tls:
        Whether to use TLS for the connection (default ``False``).
    bus:
        Optional event bus for publishing channel events.
    """

    channel_id = "irc"

    def __init__(
        self,
        server: str = "",
        *,
        port: int = 6667,
        nick: str = "",
        password: str = "",
        use_tls: bool = False,
        bus: Optional[EventBus] = None,
    ) -> None:
        self._server = server or os.environ.get("IRC_SERVER", "")
        self._port = int(os.environ.get("IRC_PORT", str(port)))
        self._nick = nick or os.environ.get("IRC_NICK", "")
        self._password = password or os.environ.get("IRC_PASSWORD", "")
        self._use_tls = use_tls
        self._bus = bus
        self._handlers: List[ChannelHandler] = []
        self._status = ChannelStatus.DISCONNECTED

    # -- connection lifecycle ---------------------------------------------------

    def connect(self) -> None:
        """Mark as connected (send-only — no persistent connection)."""
        if not self._server:
            logger.warning("No IRC server configured")
            self._status = ChannelStatus.ERROR
            return
        if not self._nick:
            logger.warning("No IRC nick configured")
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
        """Send a PRIVMSG to an IRC channel via a new socket connection."""
        if not self._server or not self._nick:
            logger.warning("Cannot send: IRC server or nick not configured")
            return False

        try:
            server = _irc_value(self._server)
            nick = _irc_value(self._nick)
            password = _irc_value(self._password)
            channel = _irc_value(channel)
            content = _irc_value(content)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if self._use_tls:
                ctx = ssl.create_default_context()
                sock = ctx.wrap_socket(sock, server_hostname=server)

            sock.connect((server, self._port))

            if password:
                sock.sendall(f"PASS {password}\r\n".encode())
            sock.sendall(f"NICK {nick}\r\n".encode())
            sock.sendall(f"USER {nick} 0 * :{nick}\r\n".encode())
            sock.sendall(f"PRIVMSG {channel} :{content}\r\n".encode())
            sock.sendall(b"QUIT\r\n")
            sock.close()

            self._publish_sent(channel, content, conversation_id)
            return True
        except Exception as _e:
            logger.debug("IRC send failed: {}", _e)
            return False

    def status(self) -> ChannelStatus:
        """Return the current connection status."""
        return self._status

    def list_channels(self) -> List[str]:
        """Return available channel identifiers."""
        return ["irc"]

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


__all__ = ["IRCChannel"]
