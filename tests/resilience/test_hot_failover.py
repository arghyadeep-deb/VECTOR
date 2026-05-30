
import asyncio
import time
import pytest

from core.resilience.hot_failover import HotFailover, StateDigest


@pytest.fixture
def primary():
    hf = HotFailover(is_primary=True)
    return hf


@pytest.fixture
def secondary():
    hf = HotFailover(is_primary=False)
    hf.heartbeat_interval = 0.1
    hf.max_missed_heartbeats = 2
    return hf


@pytest.mark.asyncio
async def test_heartbeat_send_receive(primary, secondary):
    await primary.start_primary()
    await secondary.start_secondary()
    digest = StateDigest(timestamp=time.time(), generation=1)
    received = await secondary.receive_heartbeat(digest.__dict__)
    assert received is True
    assert secondary.last_digest is not None
    assert secondary.last_digest.generation == 1


@pytest.mark.asyncio
async def test_missed_heartbeat_detection(secondary):
    await secondary.start_secondary()
    secondary._primary_active = True
    for _ in range(secondary.max_missed_heartbeats):
        await secondary.check_heartbeat()
    assert secondary.is_primary is True


@pytest.mark.asyncio
async def test_take_over(secondary):
    await secondary.start_secondary()
    secondary._primary_active = True
    assert secondary.is_primary is False
    await secondary.take_over()
    assert secondary.is_primary is True
    assert secondary._primary_active is False


@pytest.mark.asyncio
async def test_relinquish(primary):
    await primary.start_primary()
    assert primary.is_primary is True
    await primary.relinquish()
    assert primary.is_primary is False


@pytest.mark.asyncio
async def test_takeover_callbacks(secondary):
    callback_triggered = False
    async def on_takeover(digest):
        nonlocal callback_triggered
        callback_triggered = True

    secondary.on_takeover(on_takeover)
    await secondary.start_secondary()
    await secondary.take_over()
    assert callback_triggered is True


@pytest.mark.asyncio
async def test_primary_sends_heartbeat(primary):
    sent = await primary.send_heartbeat()
    await primary.stop()
    assert sent is False


@pytest.mark.asyncio
async def test_state_digest_serialization():
    digest = StateDigest(
        timestamp=time.time(),
        generation=5,
        loop_state={"tick": 100},
        active_sessions=["sess_1"],
        memory_pending=3,
    )
    d = digest.__dict__
    assert d["generation"] == 5
    assert d["memory_pending"] == 3
    restored = StateDigest(**d)
    assert restored.generation == 5


@pytest.mark.asyncio
async def test_heartbeat_loop_lifecycle(primary):
    await primary.start_primary()
    loop_task = asyncio.create_task(primary.heartbeat_loop())
    await asyncio.sleep(0.2)
    await primary.stop()
    await asyncio.sleep(0.05)
    assert loop_task.done() or not primary._running