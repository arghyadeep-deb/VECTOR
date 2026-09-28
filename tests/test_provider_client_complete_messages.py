"""ProviderClient.complete() must accept the chat-style `messages=` form its callers use (fixed 2026-09-26).

Before this, /command execution (vectorcode command_registry), four marketing agents and the subconscious loop all
raised "complete() missing 1 required positional argument: 'prompt'" on every call.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.inference.provider_client import CompletionResult, ProviderClient


class _Spy(ProviderClient):
    def __init__(self):  # no providers, no network: only the argument shaping is under test
        self.calls = []

    async def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return CompletionResult(content="ok", model="m", provider="p")


@pytest.mark.asyncio
async def test_prompt_form_is_unchanged():
    c = _Spy()
    await c.complete("hello", system="be brief", max_tokens=5, caller_id="x")
    msgs, kw = c.calls[0]
    assert msgs == [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hello"}]
    assert kw["max_tokens"] == 5 and kw["caller_id"] == "x"


@pytest.mark.asyncio
async def test_prompt_as_keyword_still_works():
    c = _Spy()
    await c.complete(prompt="hello", tier="coding")
    assert c.calls[0][0] == [{"role": "user", "content": "hello"}]


@pytest.mark.asyncio
async def test_messages_form_is_passed_through_untouched():
    c = _Spy()
    chat = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    r = await c.complete(model="vector-focus", messages=chat, max_tokens=100)
    assert r.content == "ok"
    msgs, kw = c.calls[0]
    assert msgs == chat and msgs is not chat and kw["model"] == "vector-focus" and kw["max_tokens"] == 100


@pytest.mark.asyncio
async def test_both_or_neither_is_a_clear_error():
    c = _Spy()
    with pytest.raises(TypeError):
        await c.complete("p", messages=[{"role": "user", "content": "u"}])
    with pytest.raises(TypeError):
        await c.complete()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
