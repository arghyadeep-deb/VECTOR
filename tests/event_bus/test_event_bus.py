
import asyncio
import pytest

from core.event_bus.types import Event, EventType
from core.event_bus.bus import AsyncEventBus, reset_event_bus


@pytest.fixture
async def bus():
    b = AsyncEventBus(max_queue_size=100)
    await b.start()
    yield b
    await b.stop()


@pytest.mark.asyncio
class TestAsyncEventBus:

    async def test_publish_subscribe(self, bus):
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(EventType.HEALTH_ALERT, handler)
        event = Event(event_type=EventType.HEALTH_ALERT, data={"msg": "test"})
        await bus.publish(event)
        await asyncio.sleep(0.1)
        assert len(received) == 1
        assert received[0].event_type == EventType.HEALTH_ALERT
        assert received[0].data == {"msg": "test"}

    async def test_multiple_subscribers(self, bus):
        received1 = []
        received2 = []

        async def handler1(event):
            received1.append(event)

        async def handler2(event):
            received2.append(event)

        bus.subscribe(EventType.TASK_COMPLETED, handler1)
        bus.subscribe(EventType.TASK_COMPLETED, handler2)
        await bus.publish(Event(event_type=EventType.TASK_COMPLETED))
        await asyncio.sleep(0.1)
        assert len(received1) == 1
        assert len(received2) == 1

    async def test_unsubscribe(self, bus):
        received = []

        async def handler(event):
            received.append(event)

        sub = bus.subscribe(EventType.SYSTEM_ERROR, handler)
        bus.unsubscribe(sub)
        await bus.publish(Event(event_type=EventType.SYSTEM_ERROR))
        await asyncio.sleep(0.1)
        assert len(received) == 0

    async def test_event_filtering_by_type(self, bus):
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(EventType.DECISION_MADE, handler)
        await bus.publish(Event(event_type=EventType.HEALTH_ALERT))
        await bus.publish(Event(event_type=EventType.DECISION_MADE))
        await bus.publish(Event(event_type=EventType.SYSTEM_ERROR))
        await asyncio.sleep(0.1)
        assert len(received) == 1
        assert received[0].event_type == EventType.DECISION_MADE

    async def test_sync_handler(self, bus):
        received = []

        def handler(event):
            received.append(event)

        bus.subscribe(EventType.CONFIG_CHANGED, handler)
        await bus.publish(Event(event_type=EventType.CONFIG_CHANGED))
        await asyncio.sleep(0.1)
        assert len(received) == 1

    async def test_get_stats(self, bus):
        stats = bus.get_stats()
        assert "subscribers" in stats
        assert "events_published" in stats
        assert "events_delivered" in stats
        assert "queues" in stats

    async def test_publish_after_unsubscribe(self, bus):
        received = []

        async def handler(event):
            received.append(event)

        sub = bus.subscribe(EventType.VOICE_INPUT, handler)
        bus.unsubscribe(sub)
        await bus.publish(Event(event_type=EventType.VOICE_INPUT))
        await asyncio.sleep(0.1)
        assert len(received) == 0

    async def test_stats_tracking(self, bus):
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(EventType.MEMORY_STORED, handler)
        await bus.publish(Event(event_type=EventType.MEMORY_STORED))
        await bus.publish(Event(event_type=EventType.MEMORY_STORED))
        await asyncio.sleep(0.1)
        stats = bus.get_stats()
        assert stats["events_published"] >= 2
        assert stats["events_delivered"] >= 2


@pytest.mark.asyncio
class TestEventBusSingleton:

    async def test_get_event_bus(self):
        from core.event_bus.bus import get_event_bus, reset_event_bus

        await reset_event_bus()
        bus1 = await get_event_bus()
        bus2 = await get_event_bus()
        assert bus1 is bus2
        await reset_event_bus()

    async def test_reset_creates_new_instance(self):
        from core.event_bus.bus import get_event_bus, reset_event_bus

        await reset_event_bus()
        bus1 = await get_event_bus()
        await reset_event_bus()
        bus2 = await get_event_bus()
        assert bus2 is not bus1
        await reset_event_bus()
