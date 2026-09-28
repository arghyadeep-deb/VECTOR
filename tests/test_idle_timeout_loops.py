"""Idle-tick timeouts in background loops are normal, not errors.

Found 2026-09-25: an automated "no silent swallow" cleanup turned three idle
`except asyncio.TimeoutError: pass` handlers into
`logger.warning("suppressed exception (degraded mode)", exc_info=True)`.
  * obsidian_sync.start_watching  -> a warning + full traceback EVERY second
  * IngestionQueue.run_forever    -> the same, every poll interval
    (5,654 such lines / 4.9 MB in one live vector_api.log)
  * ChannelRuntime.start          -> worse: the try/except sat OUTSIDE the while
    loop, so the "run until cancelled" dispatch loop exited after the first
    quiet second and every later message was never dispatched.
"""
import asyncio
from unittest.mock import MagicMock

import pytest
from loguru import logger

from core.engine.channels.runtime import ChannelMessage, ChannelRuntime
from core.engine.memory_tree.ingestion_queue import IngestionQueue
from core.memory.obsidian_sync import ObsidianSync


@pytest.fixture
def warnings():
    records = []
    sink = logger.add(lambda m: records.append(m.record["message"]), level="WARNING")
    yield records
    logger.remove(sink)


def _noise(records):
    return [r for r in records if "suppressed exception" in r]


async def test_obsidian_watcher_is_quiet_when_the_vault_is_idle(tmp_path, warnings):
    sync = ObsidianSync(vault_path=tmp_path)
    task = asyncio.create_task(sync.start_watching())
    await asyncio.sleep(2.6)            # at least two 1s idle ticks
    sync._watching = False
    await asyncio.wait_for(task, timeout=5)
    assert _noise(warnings) == []


async def test_ingestion_queue_is_quiet_when_idle(warnings):
    queue = IngestionQueue(tree=MagicMock())
    task = asyncio.create_task(queue.run_forever(poll_interval=0.05))
    await asyncio.sleep(0.4)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)   # run_forever exits cleanly on cancel
    assert _noise(warnings) == []


async def test_channel_runtime_keeps_dispatching_after_an_idle_second():
    runtime = ChannelRuntime()
    seen = asyncio.Event()

    async def fake_dispatch(msg):
        seen.set()

    runtime._dispatch = fake_dispatch
    task = asyncio.create_task(runtime.start())
    try:
        await asyncio.sleep(1.5)        # longer than the 1s idle timeout
        assert not task.done(), "dispatch loop exited after an idle second"
        await runtime.submit(ChannelMessage.new("owner", "hello", "telegram"))
        await asyncio.wait_for(seen.wait(), timeout=3)
    finally:
        runtime._running = False
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
