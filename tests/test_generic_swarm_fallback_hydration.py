"""Regression: core/swarm/generic_swarm.py's GenericSwarm._fallback() called
core.inference.vectorcode_llm.chat() directly with no
session_hydration_prompt() -- RULE 1 gap, same class fixed 10+ times this
cycle. GenericSwarm is live (real callers: core/mcp_tools/expansion_modules/
swarm.py, districts/growth/growth_orchestrator.py via
core/swarm/orchestrator.py's SwarmOrchestrator).
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.swarm.generic_swarm import GenericSwarm


def test_fallback_hydrates_before_chat():
    swarm = GenericSwarm.__new__(GenericSwarm)
    swarm._district = "governance"
    swarm._agents = {}
    swarm.name = "GovernanceSwarm"

    with patch("core.inference.vectorcode_llm.chat", new=AsyncMock(return_value="answer")) as mock_chat:
        asyncio.run(
            swarm._fallback("unknown_task", {"query": "what is the status?"})
        )
    messages = mock_chat.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert len(messages[0]["content"]) > 0


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
