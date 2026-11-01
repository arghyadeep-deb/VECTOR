"""
MessageBus — Python port of reference v2/src/communication/message-bus.ts.

Absorbed:
  - Named channels, QoS 0/1, dead letter queue, channel statistics
  - ChannelACL: allowedSenders, allowedReceivers, bannedAgents, read/write perms
  - 7 filter operators: eq, ne, gt, lt, contains, matches, in
  - Full reference MessageBus ACL enforcement on every publish/subscribe
"""
import uuid
import re
import threading
import time
from collections import deque, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from loguru import logger


class ChannelType(Enum):
    BROADCAST = "broadcast"    # all subscribers receive
    DIRECT    = "direct"       # one-to-one
    TOPIC     = "topic"        # pub/sub by topic pattern
    QUEUE     = "queue"        # round-robin delivery


class QoS(Enum):
    FIRE_AND_FORGET  = 0   # no ack required
    AT_LEAST_ONCE    = 1   # retried until acked


# ── 7 filter operators (reference ACL filter system) ─────────────────────────────

class FilterOp(Enum):
    EQ       = "eq"        # exact match
    NE       = "ne"        # not equal
    GT       = "gt"        # greater than (numeric)
    LT       = "lt"        # less than (numeric)
    CONTAINS = "contains"  # string/list contains value
    MATCHES  = "matches"   # regex match
    IN       = "in"        # value in a set


@dataclass
class FilterRule:
    """A single ACL filter rule using one of 7 operators."""
    field:    str       # dot-path into Message (e.g. "sender", "priority", "content.type")
    op:       FilterOp
    value:    object    # comparison value

    def evaluate(self, msg: "Message") -> bool:
        actual = self._extract_field(msg, self.field)
        try:
            if self.op == FilterOp.EQ:       return actual == self.value
            if self.op == FilterOp.NE:       return actual != self.value
            if self.op == FilterOp.GT:       return float(actual) > float(self.value)
            if self.op == FilterOp.LT:       return float(actual) < float(self.value)
            if self.op == FilterOp.CONTAINS: return self.value in actual
            if self.op == FilterOp.MATCHES:  return bool(re.search(str(self.value), str(actual)))
            if self.op == FilterOp.IN:       return actual in self.value
        except Exception:
            return False
        return True

    @staticmethod
    def _extract_field(msg: "Message", path: str) -> object:
        parts = path.split(".")
        obj = msg
        for p in parts:
            if isinstance(obj, dict):
                obj = obj.get(p)
            else:
                obj = getattr(obj, p, None)
            if obj is None:
                return None
        return obj


@dataclass
class ChannelACL:
    """
    reference MessageBus ACL — allowedSenders, allowedReceivers, bannedAgents,
    read/write permissions, and composable filter rules.
    Empty sets mean 'allow all'.
    """
    allowed_senders:   set = field(default_factory=set)    # empty = allow all
    allowed_receivers: set = field(default_factory=set)    # empty = allow all
    banned_agents:     set = field(default_factory=set)    # always denied
    read_permission:   bool = True    # subscribers can read
    write_permission:  bool = True    # publishers can write
    filter_rules:      list = field(default_factory=list)  # [FilterRule]

    def can_publish(self, sender: str) -> bool:
        if not self.write_permission: return False
        if sender in self.banned_agents: return False
        if self.allowed_senders and sender not in self.allowed_senders: return False
        return True

    def can_subscribe(self, subscriber_id: str) -> bool:
        if not self.read_permission: return False
        if subscriber_id in self.banned_agents: return False
        if self.allowed_receivers and subscriber_id not in self.allowed_receivers: return False
        return True

    def passes_filters(self, msg: "Message") -> bool:
        """All filter rules must pass (AND semantics)."""
        return all(rule.evaluate(msg) for rule in self.filter_rules)

    def add_filter(self, field: str, op: FilterOp, value: object) -> None:
        self.filter_rules.append(FilterRule(field=field, op=op, value=value))


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
    acl_denied: int  = 0   # messages denied by ACL

    @property
    def success_rate(self) -> float:
        total = self.sent
        return round(self.delivered / total, 3) if total > 0 else 1.0


class Channel:
    """A named channel with ACL, subscriber management, QoS, and stats."""

    MAX_RETRIES = 3
    RETRY_DELAY = 0.5

    def __init__(
        self,
        name: str,
        channel_type: ChannelType = ChannelType.BROADCAST,
        max_size: int = 1000,
        acl: Optional[ChannelACL] = None,
    ):
        self.name         = name
        self.type         = channel_type
        self.acl          = acl or ChannelACL()
        self.stats        = ChannelStats()
        self._subscribers: dict[str, Callable] = {}
        self._messages    = deque(maxlen=max_size)
        self._dead_letters = deque(maxlen=100)
        self._pending_ack: dict[str, tuple[Message, list[str]]] = {}
        self._lock        = threading.Lock()
        self._rr_index    = 0

    def subscribe(self, callback: Callable, subscriber_id: str = "") -> str | None:
        sid = subscriber_id or str(uuid.uuid4())[:8]
        if not self.acl.can_subscribe(sid):
            logger.warning(f"[VECTOR][bus] ACL denied subscribe: {sid} → '{self.name}'")
            self.stats.acl_denied += 1
            return None
        with self._lock:
            self._subscribers[sid] = callback
        return sid

    def unsubscribe(self, subscriber_id: str) -> bool:
        with self._lock:
            return bool(self._subscribers.pop(subscriber_id, None))

    def publish(self, message: Message) -> int:
        """Deliver message to subscribers. ACL-checked. Returns delivery count."""
        if not self.acl.can_publish(message.sender):
            logger.warning(f"[VECTOR][bus] ACL denied publish: '{message.sender}' → '{self.name}'")
            self.stats.acl_denied += 1
            return 0

        if not self.acl.passes_filters(message):
            logger.debug(f"[VECTOR][bus] ACL filter blocked message on '{self.name}'")
            self.stats.acl_denied += 1
            return 0

        with self._lock:
            subs = dict(self._subscribers)
            self._messages.append(message)
        self.stats.sent += 1

        if not subs:
            self._dead_letters.append(message)
            self.stats.dead_letters += 1
            return 0

        if self.type == ChannelType.QUEUE:
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
            return True
        return False

    def get_dead_letters(self, limit: int = 10) -> list:
        return list(self._dead_letters)[-limit:]

    def get_history(self, limit: int = 20) -> list:
        return list(self._messages)[-limit:]


class MessageBus:
    """
    Singleton in-process message broker with full reference ACL.

    Usage:
        bus = MessageBus.get()
        acl = ChannelACL(allowed_senders={"coder", "reviewer"})
        acl.add_filter("priority", FilterOp.GT, 0)
        bus.create_channel("tasks", ChannelType.BROADCAST, acl=acl)
        sub_id = bus.subscribe("tasks", my_callback, "worker-1")
        bus.publish("tasks", {"action": "review"}, sender="coder")
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
        self._middleware: list[Callable] = []
        self._filters: dict[str, list[Callable]] = defaultdict(list)
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
        acl: Optional[ChannelACL] = None,
    ) -> Channel:
        if name not in self._channels:
            self._channels[name] = Channel(name, channel_type, max_size, acl)
            logger.debug(f"[VECTOR][bus] channel created: {name} ({channel_type.value})")
        return self._channels[name]

    def set_acl(self, channel: str, acl: ChannelACL) -> None:
        ch = self._channels.get(channel)
        if ch:
            ch.acl = acl

    def get_channel(self, name: str) -> Channel | None:
        return self._channels.get(name)

    def list_channels(self) -> list[str]:
        return list(self._channels.keys())

    # ── Pub/Sub ────────────────────────────────────────────────────────────────

    def subscribe(self, channel: str, callback: Callable, subscriber_id: str = "") -> str | None:
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

        for mw in self._middleware:
            try:
                mw(msg)
            except Exception as e:
                logger.warning(f"[VECTOR][bus] middleware error: {e}")

        for filt in self._filters.get(channel, []):
            try:
                if not filt(msg):
                    return msg
            except Exception as e:
                logger.warning(f"[VECTOR][bus] filter error: {e}")

        ch.publish(msg)
        return msg

    def broadcast(
        self, content: object, *, sender: str = "vector", exclude: list[str] | None = None
    ) -> int:
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
        self._middleware.append(fn)

    def add_filter(self, channel: str, fn: Callable) -> None:
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
                "acl_denied": s.acl_denied,
            }
        return {
            name: {
                "sent": ch.stats.sent, "delivered": ch.stats.delivered,
                "success_rate": ch.stats.success_rate,
                "acl_denied": ch.stats.acl_denied,
            }
            for name, ch in self._channels.items()
        }


if __name__ == "__main__":
    bus = MessageBus.get()

    # Basic publish/subscribe
    bus.create_channel("test_ch", ChannelType.BROADCAST)
    received = []
    sub_id = bus.subscribe("test_ch", lambda m: received.append(m.content))
    bus.publish("test_ch", {"action": "test"}, sender="unit_test")
    assert len(received) == 1 and received[0]["action"] == "test"

    # ACL: only allow "coder" sender
    acl = ChannelACL(allowed_senders={"coder"})
    bus.create_channel("acl_ch", ChannelType.BROADCAST, acl=acl)
    acl_received = []
    bus.subscribe("acl_ch", lambda m: acl_received.append(m.content), "worker-1")
    bus.publish("acl_ch", "allowed", sender="coder")
    bus.publish("acl_ch", "blocked", sender="unknown")
    assert len(acl_received) == 1 and acl_received[0] == "allowed"

    # Filter operator: priority > 1
    acl2 = ChannelACL()
    acl2.add_filter("priority", FilterOp.GT, 1)
    bus.create_channel("filter_ch", ChannelType.BROADCAST, acl=acl2)
    filter_received = []
    bus.subscribe("filter_ch", lambda m: filter_received.append(m.priority))
    bus.publish("filter_ch", "low", priority=1, sender="vector")
    bus.publish("filter_ch", "high", priority=2, sender="vector")
    assert filter_received == [2]

    # FilterOp.CONTAINS
    fr = FilterRule(field="sender", op=FilterOp.CONTAINS, value="cod")
    assert fr.evaluate(Message(sender="coder"))
    assert not fr.evaluate(Message(sender="tester"))

    # FilterOp.MATCHES
    fr2 = FilterRule(field="sender", op=FilterOp.MATCHES, value=r"^cod")
    assert fr2.evaluate(Message(sender="coder"))

    # FilterOp.IN
    fr3 = FilterRule(field="priority", op=FilterOp.IN, value={1, 2, 3})
    assert fr3.evaluate(Message(priority=2))
    assert not fr3.evaluate(Message(priority=5))

    # Banned agent
    acl3 = ChannelACL(banned_agents={"bad-actor"})
    bus.create_channel("ban_ch", ChannelType.BROADCAST, acl=acl3)
    ban_received = []
    bus.subscribe("ban_ch", lambda m: ban_received.append(m.content))
    bus.publish("ban_ch", "ok", sender="good")
    bus.publish("ban_ch", "evil", sender="bad-actor")
    assert len(ban_received) == 1 and ban_received[0] == "ok"

    # Dead letter
    bus.create_channel("empty_ch")
    bus.publish("empty_ch", "orphan")
    dl = bus.get_channel("empty_ch").get_dead_letters()
    assert len(dl) == 1

    # Default channels
    assert "tasks" in bus.list_channels()
    assert "commands" in bus.list_channels()

    print(f"message_bus.py OK — ACL + 7 filter operators working")


