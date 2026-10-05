"""Regression for vectorcode/src/run_agent.py's AIAgent._fire_stream_delta():

The module-level docstring in vectorcode/src/agent/think_scrubber.py describes
a real, documented leak: MiniMax M2.7 (and similar providers) can stream a
<think> open tag as its own delta, with the reasoning body arriving in the
NEXT delta. _strip_think_blocks() is a stateless, regex-based helper -- fed
just "<think>" it matches its own "unterminated open tag at a boundary" case
and strips the whole delta to "", but has no way to remember, on the next
call, that it is still inside an open block. The following delta (the actual
reasoning text) then looks like ordinary content and is emitted straight to
the user -- the exact leak think_scrubber.py's docstring says it fixes.

Before this fix, _fire_stream_delta() called the stateless
_strip_think_blocks() directly per delta and StreamingThinkScrubber had zero
callers anywhere in the repo (confirmed via grep) despite its docstring
describing it as the intended fix. This test proves the per-delta pipeline
now uses the stateful scrubber and no longer leaks.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from run_agent import AIAgent
from agent.memory_manager import StreamingContextScrubber
from agent.think_scrubber import StreamingThinkScrubber


def _bare_agent() -> AIAgent:
    """An AIAgent with only the attributes _fire_stream_delta/_reset_stream_delivery_tracking touch.

    Constructing a real AIAgent requires provider/model/toolset wiring that
    is irrelevant to this pure text-pipeline bug, so we bypass __init__.
    """
    agent = AIAgent.__new__(AIAgent)
    agent._stream_needs_break = False
    agent._stream_think_scrubber = StreamingThinkScrubber()
    agent._stream_context_scrubber = StreamingContextScrubber()
    agent._current_streamed_assistant_text = ""
    agent.stream_delta_callback = None
    agent._stream_callback = None
    received: list[str] = []
    agent.stream_delta_callback = lambda text: received.append(text)
    return agent, received


def test_split_think_open_tag_does_not_leak_reasoning_body():
    agent, received = _bare_agent()

    # Simulate MiniMax M2.7 splitting the open tag from its body across deltas.
    agent._fire_stream_delta("<think>")
    agent._fire_stream_delta("Let me check their config")
    agent._fire_stream_delta("</think>")
    agent._fire_stream_delta("Here is the answer.")

    visible = "".join(received)
    assert "Let me check their config" not in visible, (
        "reasoning body leaked to the user after a split <think> open tag"
    )
    assert "Here is the answer." in visible


def test_fire_stream_delta_uses_stateful_think_scrubber_not_stateless_regex():
    agent, received = _bare_agent()
    scrubber = agent._stream_think_scrubber

    agent._fire_stream_delta("<think>")
    # The stateful scrubber must now be inside a block.
    assert scrubber._in_block is True

    agent._fire_stream_delta("hidden reasoning")
    assert "hidden reasoning" not in "".join(received)

    agent._fire_stream_delta("</think>visible text")
    assert scrubber._in_block is False
    assert "visible text" in "".join(received)


def test_reset_stream_delivery_tracking_resets_think_scrubber_for_next_turn():
    agent, received = _bare_agent()

    # Interrupted prior stream: left mid-block.
    agent._fire_stream_delta("<think>never closed")
    assert agent._stream_think_scrubber._in_block is True

    agent._reset_stream_delivery_tracking()

    # A hung block from the prior turn must not taint the next turn.
    assert agent._stream_think_scrubber._in_block is False
    received.clear()
    agent._fire_stream_delta("Fresh turn response.")
    assert "Fresh turn response." in "".join(received)
    assert "never closed" not in "".join(received)


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
