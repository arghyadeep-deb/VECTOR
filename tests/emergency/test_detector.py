import asyncio
import time
import pytest
from districts.emergency.detector import EmergencyDetector, EmergencyEvent


@pytest.fixture
def detector():
    return EmergencyDetector()


@pytest.mark.asyncio
async def test_rule_registration(detector):
    rules = detector.get_rules()
    assert len(rules) >= 19
    domains = {r["domain"] for r in rules}
    assert "health" in domains
    assert "system" in domains
    assert "network" in domains
    assert "security" in domains
    assert "disk" in domains
    assert "battery" in domains


@pytest.mark.asyncio
async def test_signal_processing_triggers_event(detector):
    event = await detector.process_signal("system", "high_cpu", 95)
    assert event is not None
    assert event.domain == "system"
    assert event.signal_name == "high_cpu"
    assert event.raw_value == 95


@pytest.mark.asyncio
async def test_signal_processing_no_match(detector):
    event = await detector.process_signal("system", "high_cpu", 50)
    assert event is None


@pytest.mark.asyncio
async def test_dedup_same_signal(detector):
    event1 = await detector.process_signal("system", "high_cpu", 95, source="test")
    assert event1 is not None
    event2 = await detector.process_signal("system", "high_cpu", 95, source="test")
    assert event2 is None


@pytest.mark.asyncio
async def test_dedup_different_source(detector):
    event1 = await detector.process_signal("system", "high_cpu", 95, source="source_a")
    assert event1 is not None
    event2 = await detector.process_signal("system", "high_cpu", 95, source="source_b")
    assert event2 is not None


@pytest.mark.asyncio
async def test_dedup_key_format(detector):
    await detector.process_signal("health", "heart_rate_stopped", 0, source="test_src")
    key = "health:heart_rate_stopped:test_src"
    assert key in detector._debounce


@pytest.mark.asyncio
async def test_compound_event_batching(detector):
    event1 = await detector.process_signal("system", "high_cpu", 95)
    assert event1 is not None
    await asyncio.sleep(0.05)
    event2 = await detector.process_signal("system", "high_ram", 95)
    assert event2 is not None

    buffer = [e for e in detector._event_buffer if e.detected_at >= time.time() - 10]
    assert len(buffer) >= 2


@pytest.mark.asyncio
async def test_subscribe_signal_queue(detector):
    queue = detector.subscribe_signal("health")
    assert queue is not None
    assert detector._queues["health"] is queue


@pytest.mark.asyncio
async def test_subscribe_signal_receives_events(detector):
    queue = detector.subscribe_signal("system")
    task = asyncio.create_task(queue.get())
    await asyncio.sleep(0.05)
    await detector.process_signal("system", "high_cpu", 95)
    event = await asyncio.wait_for(task, timeout=2.0)
    assert event is not None
    assert event.signal_name == "high_cpu"


@pytest.mark.asyncio
async def test_context_field(detector):
    ctx = {"user": "test", "session": "abc123"}
    event = await detector.process_signal("system", "high_cpu", 95, context=ctx)
    assert event is not None
    assert event.context == ctx


@pytest.mark.asyncio
async def test_per_rule_dedup_window(detector):
    rules = detector.get_rules()
    for r in rules:
        assert "dedup_window" in r
    no_movement = [r for r in rules if r["signal_name"] == "no_movement"][0]
    assert no_movement["dedup_window"] == 300.0
    high_cpu = [r for r in rules if r["signal_name"] == "high_cpu"][0]
    assert high_cpu["dedup_window"] == 30.0


@pytest.mark.asyncio
async def test_handler_callback(detector):
    received = []

    def handler(event):
        received.append(event)

    detector.on_event(handler)
    await detector.process_signal("system", "high_cpu", 95)
    assert len(received) == 1
    assert received[0].signal_name == "high_cpu"
