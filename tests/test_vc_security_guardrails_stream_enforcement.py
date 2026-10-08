"""VCSEC-2 regressions: streamed sensitive text is scanned before release."""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from vectorcode.src.vc_core.types import Message
from vectorcode.src.vc_engine._abc import InferenceEngine, StreamChunk
from vectorcode.src.vc_security.guardrails import GuardrailsEngine, SecurityBlockError
from vectorcode.src.vc_security.types import RedactionMode


class _StreamingEngine(InferenceEngine):
    engine_id = "test"

    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.seen_messages = None

    def generate(self, messages, *, model, **kwargs):
        return {"content": ""}

    async def stream(self, messages, *, model, **kwargs) -> AsyncIterator[str]:
        self.seen_messages = messages
        for token in self.tokens:
            yield token

    async def stream_full(self, messages, *, model, **kwargs) -> AsyncIterator[StreamChunk]:
        self.seen_messages = messages
        for token in self.tokens:
            yield StreamChunk(content=token)
        yield StreamChunk(tool_calls=[{"name": "done"}], finish_reason="stop")

    def list_models(self):
        return ["test"]

    def health(self):
        return True


async def _collect(iterator):
    return [item async for item in iterator]


@pytest.mark.asyncio
async def test_block_mode_releases_nothing_when_secret_spans_chunks() -> None:
    engine = GuardrailsEngine(
        _StreamingEngine(["prefix sk-abcdefghij", "klmnopqrstuvwxyz suffix"]),
        mode=RedactionMode.BLOCK,
    )
    released = []
    with pytest.raises(SecurityBlockError):
        async for token in engine.stream([], model="test"):
            released.append(token)
    assert released == []


@pytest.mark.asyncio
async def test_redact_mode_never_releases_split_secret() -> None:
    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    engine = GuardrailsEngine(
        _StreamingEngine(["before ", secret[:12], secret[12:], " after"]),
        mode=RedactionMode.REDACT,
    )
    output = "".join(await _collect(engine.stream([], model="test")))
    assert secret not in output
    assert "[REDACTED:openai_key]" in output


@pytest.mark.asyncio
async def test_stream_full_preserves_metadata_but_redacts_before_release() -> None:
    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    engine = GuardrailsEngine(
        _StreamingEngine(["value=", secret]), mode=RedactionMode.REDACT
    )
    chunks = await _collect(engine.stream_full([], model="test"))
    assert secret not in "".join(chunk.content or "" for chunk in chunks)
    assert chunks[-1].tool_calls == [{"name": "done"}]
    assert chunks[-1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_secure_stream_fails_closed_when_buffer_limit_is_exceeded() -> None:
    engine = GuardrailsEngine(
        _StreamingEngine(["1234", "5678"]),
        mode=RedactionMode.REDACT,
        max_stream_buffer_chars=5,
    )
    with pytest.raises(SecurityBlockError, match="buffer limit"):
        await _collect(engine.stream([], model="test"))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
