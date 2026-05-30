from core.event_bus.types import DirectMessage, DirectMessagePriority
from core.event_bus.bus import AsyncEventBus


def test_direct_message_priority_values():
    assert DirectMessagePriority.LOW.value == 0
    assert DirectMessagePriority.NORMAL.value == 1
    assert DirectMessagePriority.HIGH.value == 2
    assert DirectMessagePriority.CRITICAL.value == 3


def test_direct_message_defaults():
    msg = DirectMessage(recipient="agent_b", sender="agent_a")
    assert msg.recipient == "agent_b"
    assert msg.sender == "agent_a"
    assert msg.message_type == "direct"
    assert msg.payload == {}
    assert msg.reply_to is None
    assert msg.ttl == 30


def test_direct_message_with_all_fields():
    msg = DirectMessage(
        recipient="agent_b",
        sender="agent_a",
        message_type="request",
        payload={"action": "ping", "seq": 1},
        reply_to="msg_abc",
        ttl=60,
    )
    assert msg.message_type == "request"
    assert msg.payload == {"action": "ping", "seq": 1}
    assert msg.reply_to == "msg_abc"
    assert msg.ttl == 60


def test_direct_message_delivery():
    bus = AsyncEventBus(max_queue_size=100)
    received = []

    def handler(msg):
        received.append(msg)

    bus.register_direct_handler("agent_b", handler)
    msg = DirectMessage(recipient="agent_b", sender="agent_a", payload={"text": "hello"})
    result = bus.deliver_direct(msg)
    assert result is True
    assert len(received) == 1
    assert received[0].payload["text"] == "hello"
    assert received[0].sender == "agent_a"


def test_direct_message_not_broadcast():
    bus = AsyncEventBus(max_queue_size=100)
    received = []

    def handler(msg):
        received.append(msg)

    bus.register_direct_handler("agent_b", handler)
    msg = DirectMessage(recipient="agent_b", sender="agent_a", payload={"text": "hello"})
    msg_wrong = DirectMessage(recipient="agent_c", sender="agent_a", payload={"text": "nope"})
    bus.deliver_direct(msg)
    bus.deliver_direct(msg_wrong)
    assert len(received) == 1


def test_direct_message_unregistered_recipient():
    bus = AsyncEventBus(max_queue_size=100)
    msg = DirectMessage(recipient="ghost", sender="agent_a")
    result = bus.deliver_direct(msg)
    assert result is False


def test_multiple_recipients():
    bus = AsyncEventBus(max_queue_size=100)
    received_b = []
    received_c = []

    def handler_b(msg):
        received_b.append(msg)

    def handler_c(msg):
        received_c.append(msg)

    bus.register_direct_handler("agent_b", handler_b)
    bus.register_direct_handler("agent_c", handler_c)

    bus.deliver_direct(DirectMessage(recipient="agent_b", sender="agent_a"))
    bus.deliver_direct(DirectMessage(recipient="agent_c", sender="agent_a"))
    bus.deliver_direct(DirectMessage(recipient="agent_c", sender="agent_a"))

    assert len(received_b) == 1
    assert len(received_c) == 2


def test_unregister_handler():
    bus = AsyncEventBus(max_queue_size=100)
    received = []

    def handler(msg):
        received.append(msg)

    bus.register_direct_handler("agent_b", handler)
    bus.unregister_direct_handler("agent_b")
    bus.deliver_direct(DirectMessage(recipient="agent_b", sender="agent_a"))
    assert len(received) == 0


def test_handler_exception_does_not_raise():
    bus = AsyncEventBus(max_queue_size=100)

    def handler(msg):
        raise ValueError("oops")

    bus.register_direct_handler("agent_b", handler)
    result = bus.deliver_direct(DirectMessage(recipient="agent_b", sender="agent_a"))
    assert result is False


def test_get_stats_includes_direct_handlers():
    bus = AsyncEventBus(max_queue_size=100)
    stats = bus.get_stats()
    assert "direct_handlers" in stats
    assert stats["direct_handlers"] == 0

    def handler(msg):
        pass

    bus.register_direct_handler("agent_x", handler)
    stats = bus.get_stats()
    assert stats["direct_handlers"] == 1


def test_get_stats_includes_direct_messages_sent():
    bus = AsyncEventBus(max_queue_size=100)
    stats = bus.get_stats()
    assert "direct_messages_sent" in stats
    assert stats["direct_messages_sent"] == 0
