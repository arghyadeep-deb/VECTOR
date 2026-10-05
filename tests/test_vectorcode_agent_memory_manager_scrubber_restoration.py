"""Regression for a dropped class during a May 2026 "consolidation" refactor
(d18ec4130, "phase-1: consolidate duplicate infrastructure").

That commit shrank vectorcode/src/agent/memory_manager.py from 528 lines to
a 9-line thin re-export shim pointing at the new canonical
vectorcode/src/memory/manager.py, but only migrated MemoryManager /
sanitize_context / get_memory_manager / reset_memory_manager. It silently
dropped StreamingContextScrubber -- a real, security-relevant class that
prevents a streamed `<memory-context>` span from leaking its payload to the
UI when the open/close tags straddle two separate stream chunks (the
one-shot `sanitize_context` regex cannot see across chunk boundaries) --
and never carried over `build_memory_context_block`'s re-export either,
even though that function DID make it into the new canonical module.

run_agent.py's own module-level `from agent.memory_manager import
StreamingContextScrubber, build_memory_context_block, sanitize_context`
has been raising ImportError ever since, compounding the separate
context_engine.py deletion (see
test_vectorcode_agent_context_engine_restoration.py) to make the primary
agent entry point completely unimportable.

Restored StreamingContextScrubber into the canonical
vectorcode/src/memory/manager.py (byte-for-byte from git history,
d18ec4130^) and re-exported both missing symbols from the
agent/memory_manager.py shim.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))


def test_streaming_context_scrubber_importable_from_shim():
    from agent.memory_manager import StreamingContextScrubber

    assert StreamingContextScrubber is not None


def test_build_memory_context_block_importable_from_shim():
    from agent.memory_manager import build_memory_context_block

    assert build_memory_context_block is not None


def test_scrubber_passes_through_normal_text():
    from agent.memory_manager import StreamingContextScrubber

    s = StreamingContextScrubber()
    assert s.feed("hello world") == "hello world"
    assert s.flush() == ""


def test_scrubber_strips_memory_context_in_a_single_chunk():
    from agent.memory_manager import StreamingContextScrubber

    s = StreamingContextScrubber()
    out = s.feed("before <memory-context>SECRET PAYLOAD</memory-context> after")
    assert "SECRET PAYLOAD" not in out
    assert out == "before  after"


def test_scrubber_strips_memory_context_split_across_chunks():
    """The actual bug this class exists to fix: a one-shot regex can't see
    a tag whose open/close halves arrive in separate stream deltas."""
    from agent.memory_manager import StreamingContextScrubber

    s = StreamingContextScrubber()
    visible = []
    # Split the open tag itself across two chunks, and the payload/close
    # tag across two more -- the worst case the docstring describes.
    for chunk in ["before <memory-", "context>SEC", "RET PAYLOAD</memory-context> after"]:
        visible.append(s.feed(chunk))
    visible.append(s.flush())
    full = "".join(visible)
    assert "SECRET PAYLOAD" not in full
    assert "before" in full and "after" in full


def test_scrubber_discards_unterminated_span_on_flush():
    """An unterminated <memory-context> at end-of-stream must not leak its
    partial payload -- the docstring states this is a deliberate
    fail-closed choice ('leaking partial memory context is worse than a
    truncated answer')."""
    from agent.memory_manager import StreamingContextScrubber

    s = StreamingContextScrubber()
    visible = s.feed("before <memory-context>never closed")
    tail = s.flush()
    assert "never closed" not in (visible + tail)


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
