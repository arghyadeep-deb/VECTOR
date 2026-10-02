# DORMANT (2026-09-24, docs/design/core-module-triage.md): not imported by the running VECTOR.
# Superseded by the vectorcode channel gateway. Kept on purpose (personal-use build); do not add a second live path --
# route through the existing mechanism so the Governor and PermissionGateway stay the only way in.
"""
core/communications/hub.py — Unified CommsHub (Phase 3C).

Routes outbound messages to any configured platform adapter from
vectorcode.src.comms.*. Incoming messages are polled and published
to the VECTOR event bus as EventType.USER_INTERACTION events.

Usage:
    from core.communications.hub import CommsHub
    hub = CommsHub()
    await hub.send("telegram", recipient="@user", message="Hello sir")

Env vars (set in .env):
    TELEGRAM_BOT_TOKEN, DISCORD_TOKEN, SLACK_BOT_TOKEN, etc.
"""
from __future__ import annotations

import asyncio
import os
from loguru import logger


class CommsHub:
    """Unified send/receive across all VectorCode comms adapters."""

    # Channels enabled by default (comma-separated env var to override)
    ENABLED: list[str] = [
        c.strip() for c in os.environ.get("VECTOR_COMMS_ENABLED", "telegram,discord").split(",")
        if c.strip()
    ]

    def __init__(self):
        self._adapters: dict[str, object] = {}
        self._load_adapters()

    def _load_adapters(self) -> None:
        """Lazy-load only the enabled adapters."""
        for channel in self.ENABLED:
            try:
                adapter = self._make_adapter(channel)
                if adapter is not None:
                    self._adapters[channel] = adapter
                    logger.info(f"[VECTOR][comms] {channel} adapter loaded")
            except Exception as e:
                logger.debug(f"[VECTOR][comms] {channel} adapter unavailable: {e}")

    def _make_adapter(self, channel: str) -> object | None:
        """Instantiate the VectorCode comms adapter for a channel."""
        mapping = {
            "telegram":  ("vectorcode.src.comms.telegram_bot",   "TelegramBot"),
            "discord":   ("vectorcode.src.comms.discord_bot",    "DiscordBot"),
            "slack":     ("vectorcode.src.comms.slack_bot",      "SlackBot"),
            "whatsapp":  ("vectorcode.src.comms.whatsapp_bot",   "WhatsAppBot"),
            "email":     ("vectorcode.src.comms.email_client",   "EmailClient"),
            "signal":    ("vectorcode.src.comms.signal_bot",     "SignalBot"),
        }
        if channel not in mapping:
            return None
        module_path, class_name = mapping[channel]
        mod = __import__(module_path, fromlist=[class_name])
        cls = getattr(mod, class_name)
        return cls()

    async def send(self, channel: str, recipient: str, message: str) -> dict:
        """Send a message to a specific channel/recipient."""
        adapter = self._adapters.get(channel)
        if adapter is None:
            logger.warning(f"[VECTOR][comms] channel '{channel}' not available")
            return {"status": "unavailable", "channel": channel}
        try:
            for fn_name in ("send_message", "send", "reply"):
                fn = getattr(adapter, fn_name, None)
                if callable(fn):
                    result = fn(recipient=recipient, text=message)
                    if asyncio.iscoroutine(result):
                        result = await result
                    return {"status": "sent", "channel": channel}
            return {"status": "no_send_method", "channel": channel}
        except Exception as e:
            logger.warning(f"[VECTOR][comms] send to {channel} failed: {e}")
            return {"status": "error", "channel": channel, "error": str(e)}

    async def broadcast(self, message: str, channels: list[str] | None = None,
                        priority: str = "normal") -> dict:
        """Broadcast a message to multiple channels."""
        targets = channels or list(self._adapters.keys())
        results = {}
        for ch in targets:
            results[ch] = await self.send(ch, recipient="", message=message)
        return results

    async def listen(self, channel: str):
        """
        Async generator: yield incoming messages from a channel.
        Each yielded item is a dict with {sender, text, channel, ts}.
        Publishes to VECTOR event bus as USER_INTERACTION.
        """
        adapter = self._adapters.get(channel)
        if adapter is None:
            return
        poll_fn = getattr(adapter, "poll_messages", None) or getattr(adapter, "get_messages", None)
        if not callable(poll_fn):
            return
        while True:
            try:
                messages = poll_fn()
                if asyncio.iscoroutine(messages):
                    messages = await messages
                for msg in (messages or []):
                    payload = {
                        "sender": msg.get("sender", ""),
                        "text": msg.get("text", ""),
                        "channel": channel,
                        "ts": msg.get("ts", 0),
                    }
                    # Publish to VECTOR event bus
                    try:
                        from core.event_bus.bus import get_event_bus
                        from core.event_bus.types import Event, EventType
                        bus = await get_event_bus()
                        await bus.publish(Event(
                            event_type=EventType.USER_INTERACTION,
                            data=payload,
                            source=f"comms.{channel}",
                        ))
                    except Exception as _ev_err:
                        logger.debug(f"[VECTOR][comms] event publish failed: {_ev_err}")
                    yield payload
            except Exception as e:
                logger.debug(f"[VECTOR][comms] listen {channel} error: {e}")
            await asyncio.sleep(5.0)

    def get_pending_count(self) -> int:
        """Return total pending messages across all adapters (for context_engine)."""
        total = 0
        for adapter in self._adapters.values():
            try:
                fn = getattr(adapter, "pending_count", None) or getattr(adapter, "unread_count", None)
                if callable(fn):
                    total += int(fn() or 0)
            except Exception as e:
                logger.warning("[VECTOR][comms] pending-count check failed for adapter: {}", e)
        return total

    def get_comms_status(self) -> dict:
        return {
            "enabled_channels": list(self._adapters.keys()),
            "urgent": 0,
            "unread": self.get_pending_count(),
            "pending": self.get_pending_count(),
        }
