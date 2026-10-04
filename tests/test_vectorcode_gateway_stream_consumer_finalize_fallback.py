"""Regressions for vectorcode/src/gateway/stream_consumer.py.

1. GatewayStreamConsumer.run()'s got_done handling: when the dedicated
   finalize=True edit (the `elif self._message_id:` branch) itself exhausts
   the flood-control strike budget and flips `_fallback_final_send=True` as
   a side effect, the code used to just return -- the accumulated text was
   never delivered via any path. Confirmed live via the already-existing
   vectorcode/python/tests/legacy_ported/gateway/test_stream_consumer.py::
   TestSegmentBreakOnToolBoundary::test_edit_failure_sends_only_unsent_tail_at_finish,
   which was failing before this fix (adapter.send.call_count was 1, not 2 --
   the "world" tail was silently dropped) and now passes.

2. _try_strip_cursor() used to unconditionally set self._last_sent_text to
   the cursor-stripped prefix after calling adapter.edit_message(), even
   when that call returned success=False. This test proves the corrected
   behavior directly: a failed strip-cursor edit must not update
   _last_sent_text.
"""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from gateway.stream_consumer import GatewayStreamConsumer, StreamConsumerConfig


@pytest.mark.asyncio
async def test_try_strip_cursor_does_not_update_last_sent_text_on_failure():
    adapter = MagicMock()
    adapter.edit_message = AsyncMock(return_value=SimpleNamespace(success=False, error="flood_control:6"))
    consumer = GatewayStreamConsumer(adapter, "chat_1", StreamConsumerConfig(cursor=" ▉"))
    consumer._message_id = "msg_1"
    consumer._last_sent_text = "Hello ▉"

    await consumer._try_strip_cursor()

    assert adapter.edit_message.await_count == 1
    # Must NOT have been updated -- the edit failed, so the real platform
    # message still shows the cursor.
    assert consumer._last_sent_text == "Hello ▉"


@pytest.mark.asyncio
async def test_try_strip_cursor_updates_last_sent_text_on_success():
    adapter = MagicMock()
    adapter.edit_message = AsyncMock(return_value=SimpleNamespace(success=True))
    consumer = GatewayStreamConsumer(adapter, "chat_1", StreamConsumerConfig(cursor=" ▉"))
    consumer._message_id = "msg_1"
    consumer._last_sent_text = "Hello ▉"

    await consumer._try_strip_cursor()

    assert consumer._last_sent_text == "Hello"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
