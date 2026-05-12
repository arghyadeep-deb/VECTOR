"""
MessageBus — Python port of Ruflo's v2/src/communication/message-bus.ts.

Lightweight in-process message broker for VectorCode agent coordination.
Supports: named channels, QoS 0/1, dead letter queue, channel statistics.
No external process required — pure Python, singleton per process.
"""
import uuid
import threading
import time
import sys
from collections import deque, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from loguru import logger


class ChannelType(Enum):
    BROADCAST = "broadcast"    # all subscribers receive
    DIRECT    = "direct"       # one-to-one
    TOPIC     = "topic"        # pub/sub by topic pattern
    QUEUE     = "queue"        # round-robin delivery


class QoS(Enum):
    FIRE_AND_FORGET  = 0   # no ack required
    AT_LEAST_ONCE    = 1   # retried until acked


@dataclass
class Message:
    id:          str      = field(default_factory=lambda: str(uuid.uuid4())[:12])
    channel:     str      = ""
    sender:      str      = "vector"
    content:     object   = None
    qos:         QoS      = QoS.FIRE_AND_FORGET
    priority:    int      = 1       # 0=low … 4=critical
    expires_at:  float    = 0.0     # epoch; 0 = never
    correlation_id: str   = ""
    reply_to:    str      = ""
    sent_at:     float    = field(default_factory=time.time)
    _acked_by:   set      = field(default_factory=set)


@dataclass
class ChannelStats:
    sent:      int   = 0
    delivered: int   = 0
    failed:    int   = 0
    dead_letters: int = 0
    bytes_transferred: int = 0

    @property
    def success_rate(self) -> float:
        total = self.sent
        return round(self.delivered / total, 3) if total > 0 else 1.0


class Channel:
    """A named channel with subscriber management, QoS, and stats."""

    MAX_RETRIES = 3
    RETRY_DELAY = 0.5  # seconds

    def __init__(self, name: str, channel_type: ChannelType = ChannelType.BROADCAST, max_size: int = 1000):
        self.name         = name
        self.type         = channel_type
        self.stats        = ChannelStats()
        self._subscribers: dict[str, Callable] = {}
        self._messages    = deque(maxlen=max_size)
        self._dead_letters = deque(maxlen=100)
        self._pending_ack: dict[str, tuple[Message, list[str]]] = {}  # msg_id -> (msg, remaining_subs)
        self._lock        = threading.Lock()
        self._rr_index    = 0  # round-robin cursor

    def subscribe(self, callback: Callable, subscriber_id: str = "") -> str:
        sid = subscriber_id or str(uuid.uuid4())[:8]
        with self._lock:
            self._subscribers[sid] = callback
        return sid

    def unsubscribe(self, subscriber_id: str) -> bool:
        with self._lock:
            return bool(self._subscribers.pop(subscriber_id, None))

    def publish(self, message: Message) -> int:
        """Deliver message to subscribers. Returns delivery count."""
        with self._lock:
            subs = dict(self._subscribers)
            self._messages.append(message)
        self.stats.sent += 1

        if not subs:
            self._dead_letters.append(message)
            self.stats.dead_letters += 1
            logger.debug(f"[VECTOR][bus] dead letter on '{self.name}': no subscribers")
            return 0

        if self.type == ChannelType.QUEUE:
            # Round-robin — deliver to exactly one subscriber
            keys = list(subs.keys())
            idx = self._rr_index % len(keys)
            self._rr_index += 1
            subs = {keys[idx]: subs[keys[idx]]}

        delivered = 0
        remaining_acks = []

        for sid, callback in subs.items():
            success = self._deliver_to(message, sid, callback)
            if success:
                delivered += 1
                self.stats.delivered += 1
                self.stats.bytes_transferred += len(str(message.content))
                if message.qos == QoS.AT_LEAST_ONCE:
                    remaining_acks.append(sid)

        if message.qos == QoS.AT_LEAST_ONCE and remaining_acks:
            self._pending_ack[message.id] = (message, remaining_acks)

        if delivered == 0:
            self._dead_letters.append(message)
            self.stats.failed += 1
            self.stats.dead_letters += 1

        return delivered

    def _deliver_to(self, message: Message, sid: str, callback: Callable) -> bool:
        # Check expiry
        if message.expires_at > 0 and time.time() > message.expires_at:
            return False

        for attempt in range(self.MAX_RETRIES):
            try:
                callback(message)
                return True
            except Exception as e:
                logger.warning(f"[VECTOR][bus] delivery failed sid={sid} attempt={attempt+1}: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY * (2 ** attempt))
        return False

    def acknowledge(self, message_id: str, subscriber_id: str) -> bool:
        if message_id not in self._pending_ack:
            return False
        msg, remaining = self._pending_ack[message_id]
        if subscriber_id in remaining:
            remaining.remove(subscriber_id)
        if not remaining:
            del self._pending_ack[message_id]
            logger.debug(f"[VECTOR][bus] message {message_id} fully acknowledged")
            return True
        return False

    def get_dead_letters(self, limit: int = 10) -> list:
        return list(self._dead_letters)[-limit:]

    def get_history(self, limit: int = 20) -> list:
        return list(self._messages)[-limit:]


class MessageBus:
    """
    Singleton in-process message broker.
    Python port of Ruflo's MessageBus concept — adapted for VectorCode's local architecture.

    Usage:
        bus = MessageBus.get()
        bus.create_channel("tasks", ChannelType.BROADCAST)
        sub_id = bus.subscribe("tasks", my_callback)
        bus.publish("tasks", {"action": "review", "file": "foo.py"}, sender="coder")
        bus.acknowledge("tasks", msg_id, sub_id)
    """

    _instance: Optional["MessageBus"] = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> "MessageBus":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._channels: dict[str, Channel] = {}
        self._global_stats: dict[str, ChannelStats] = {}
        self._middleware: list[Callable] = []
        self._filters: dict[str, list[Callable]] = defaultdict(list)
        # Create default system channels
        for ch, ct in [
            ("tasks",    ChannelType.BROADCAST),
            ("events",   ChannelType.BROADCAST),
            ("commands", ChannelType.QUEUE),
            ("logs",     ChannelType.BROADCAST),
        ]:
            self.create_channel(ch, ct)

    # ── Channel management ─────────────────────────────────────────────────────

    def create_channel(
        self,
        name: str,
        channel_type: ChannelType = ChannelType.BROADCAST,
        max_size: int = 1000,
    ) -> Channel:
        if name not in self._channels:
            self._channels[name] = Channel(name, channel_type, max_size)
            logger.debug(f"[VECTOR][bus] channel created: {name} ({channel_type.value})")
        return self._channels[name]

    def get_channel(self, name: str) -> Channel | None:
        return self._channels.get(name)

    def list_channels(self) -> list[str]:
        return list(self._channels.keys())

    # ── Pub/Sub ────────────────────────────────────────────────────────────────

    def subscribe(self, channel: str, callback: Callable, subscriber_id: str = "") -> str:
        ch = self._channels.get(channel)
        if ch is None:
            ch = self.create_channel(channel)
        return ch.subscribe(callback, subscriber_id)

    def unsubscribe(self, channel: str, subscriber_id: str) -> bool:
        ch = self._channels.get(channel)
        return ch.unsubscribe(subscriber_id) if ch else False

    def publish(
        self,
        channel: str,
        content: object,
        *,
        sender: str = "vector",
        qos: QoS = QoS.FIRE_AND_FORGET,
        priority: int = 1,
        ttl_seconds: float = 0.0,
        correlation_id: str = "",
        reply_to: str = "",
    ) -> Message:
        """Create and deliver a message. Returns the Message object."""
        ch = self._channels.get(channel)
        if ch is None:
            ch = self.create_channel(channel)

        msg = Message(
            channel=channel,
            sender=sender,
            content=content,
            qos=qos,
            priority=priority,
            expires_at=time.time() + ttl_seconds if ttl_seconds > 0 else 0.0,
            correlation_id=correlation_id,
            reply_to=reply_to,
        )

        # Run global middleware
        for mw in self._middleware:
            try:
                mw(msg)
            except Exception as e:
                logger.warning(f"[VECTOR][bus] middleware error: {e}")

        # Run channel filters
        for filt in self._filters.get(channel, []):
            try:
                if not filt(msg):
                    logger.debug(f"[VECTOR][bus] message filtered on '{channel}'")
                    return msg
            except Exception as e:
                logger.warning(f"[VECTOR][bus] filter error: {e}")

        ch.publish(msg)
        return msg

    def broadcast(
        self, content: object, *, sender: str = "vector", exclude: list[str] | None = None
    ) -> int:
        """Broadcast to all channels except excluded ones."""
        exclude = exclude or []
        count = 0
        for name, ch in self._channels.items():
            if name not in exclude:
                msg = Message(channel=name, sender=sender, content=content)
                count += ch.publish(msg)
        return count

    def acknowledge(self, channel: str, message_id: str, subscriber_id: str) -> bool:
        ch = self._channels.get(channel)
        return ch.acknowledge(message_id, subscriber_id) if ch else False

    # ── Middleware & Filters ───────────────────────────────────────────────────

    def add_middleware(self, fn: Callable) -> None:
        """Global middleware — called on every message before delivery."""
        self._middleware.append(fn)

    def add_filter(self, channel: str, fn: Callable) -> None:
        """Per-channel filter — return False to drop message."""
        self._filters[channel].append(fn)

    # ── Stats ──────────────────────────────────────────────────────────────────

    def get_stats(self, channel: str | None = None) -> dict:
        if channel:
            ch = self._channels.get(channel)
            if not ch: return {}
            s = ch.stats
            return {
                "channel": channel,
                "sent": s.sent, "delivered": s.delivered,
                "failed": s.failed, "dead_letters": s.dead_letters,
                "bytes_transferred": s.bytes_transferred,
                "success_rate": s.success_rate,
            }
        return {
            name: {
                "sent": ch.stats.sent, "delivered": ch.stats.delivered,
                "success_rate": ch.stats.success_rate,
            }
            for name, ch in self._channels.items()
        }


if __name__ == "__main__":
    bus = MessageBus.get()

    # Create channel
    bus.create_channel("test_channel", ChannelType.BROADCAST)
    received = []

    # Subscribe
    sub_id = bus.subscribe("test_channel", lambda m: received.append(m.content))

    # Publish
    msg = bus.publish("test_channel", {"action": "test"}, sender="unit_test")
    assert len(received) == 1, f"expected 1 delivery, got {len(received)}"
    assert received[0]["action"] == "test"

    # Stats
    stats = bus.get_stats("test_channel")
    assert stats["sent"] == 1
    assert stats["delivered"] == 1
    assert stats["success_rate"] == 1.0

    # Dead letter (no subscribers on new channel)
    bus.create_channel("empty_channel")
    bus.publish("empty_channel", "orphan")
    dl = bus.get_channel("empty_channel").get_dead_letters()
    assert len(dl) == 1

    # Default channels exist
    assert "tasks" in bus.list_channels()
    assert "commands" in bus.list_channels()

    print("message_bus.py OK")
