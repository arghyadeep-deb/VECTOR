"""FL-027 — ChannelAgent must not promise an unretrievable report URI.

Deep/long responses used to be escalated through _ESCALATION_TEMPLATE,
which appended "vector://research/{session_id}" and claimed "Full report
ready" -- but a repo-wide search found no producer, store, or consumer for
that URI anywhere. Fixed to truncate honestly instead.
"""
from __future__ import annotations

import pytest

from vectorcode.src.vc_agents.channel_agent import ChannelAgent


class _LongAgent:
    def run(self, content: str):
        return "x" * 600  # over _LONG_RESPONSE_THRESHOLD (500)


class _ShortAgent:
    def run(self, content: str):
        return "short answer"


@pytest.mark.asyncio
async def test_long_response_does_not_reference_vector_research_uri():
    agent = ChannelAgent(channel=None, agent=_LongAgent())
    response = await agent.process_text("summarize the whole project")
    assert "vector://research" not in response
    assert "Full report ready" not in response


@pytest.mark.asyncio
async def test_long_response_is_truncated_with_an_honest_note():
    agent = ChannelAgent(channel=None, agent=_LongAgent())
    response = await agent.process_text("summarize the whole project")
    assert response.startswith("x" * 500)
    assert "not retrievable" in response or "isn't retrievable" in response


@pytest.mark.asyncio
async def test_short_response_passes_through_unescalated():
    agent = ChannelAgent(channel=None, agent=_ShortAgent())
    response = await agent.process_text("hi")
    assert response == "short answer"
    assert "vector://research" not in response


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
