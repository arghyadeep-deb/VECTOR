"""Regression: CodingSwarm._fallback_response() called the LLM with a bare
custom system message and no session_hydration_prompt() at all -- RULE 1
("before EVERY LLM call, no exceptions"). Same gap already fixed in
districts/marketing's amazon_ads_agent.py/attribution_agent.py/sgtm_agent.py
this cycle. Fixed by injecting hydration into the system message.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from districts.coding.agent import CodingSwarm


@pytest.mark.asyncio
async def test_fallback_response_injects_session_hydration():
    swarm = CodingSwarm()
    captured = {}

    def _fake_chat(model, messages, timeout=60.0):
        captured["messages"] = messages
        return "ok"

    with patch("core.inference.vectorcode_llm.chat", side_effect=_fake_chat):
        result = await swarm._fallback_response("unknown_task", {"query": "do something"})

    assert result["status"] == "ok"
    system_msg = captured["messages"][0]["content"]
    assert "CodingSwarm" in system_msg
    # The hydration block includes the configured owner name -- confirms a
    # real session_hydration_prompt() call happened, not just a static string.
    from core.config import CONFIG
    assert CONFIG["owner_name"] in system_msg


@pytest.mark.asyncio
async def test_fallback_response_still_reports_error_on_chat_failure():
    swarm = CodingSwarm()

    def _raise(*a, **k):
        raise RuntimeError("no provider available")

    with patch("core.inference.vectorcode_llm.chat", side_effect=_raise):
        result = await swarm._fallback_response("unknown_task", {"query": "x"})

    assert result["status"] == "error"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
