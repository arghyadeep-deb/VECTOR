"""Regression: core/swarm/orchestrator.py's SwarmOrchestrator.dispatch()
fallback loop ("try all swarms in order") only advanced to the next swarm
when a call RAISED -- but every real swarm/agent in this codebase reports
failure via a returned {"status": "error", ...} dict rather than raising,
so the loop accepted the first swarm's error dict and returned immediately,
never actually trying the rest despite its own stated purpose.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.swarm.orchestrator import SwarmOrchestrator


def test_fallback_skips_error_dict_and_tries_next_swarm():
    orch = SwarmOrchestrator.__new__(SwarmOrchestrator)
    orch._loaded = True

    failing_swarm = AsyncMock()
    failing_swarm.dispatch = AsyncMock(return_value={"status": "error", "error": "no match"})
    working_swarm = AsyncMock()
    working_swarm.dispatch = AsyncMock(return_value={"status": "ok", "response": "handled"})

    orch._swarms = {"failing": failing_swarm, "working": working_swarm}

    result = asyncio.get_event_loop().run_until_complete(
        orch.dispatch("totally_unknown_task_type", {"query": "x"})
    )

    assert result == {"status": "ok", "response": "handled"}
    failing_swarm.dispatch.assert_awaited_once()
    working_swarm.dispatch.assert_awaited_once()


def test_fallback_returns_last_error_if_every_swarm_fails():
    orch = SwarmOrchestrator.__new__(SwarmOrchestrator)
    orch._loaded = True

    swarm_a = AsyncMock()
    swarm_a.dispatch = AsyncMock(return_value={"status": "error", "error": "a failed"})
    swarm_b = AsyncMock()
    swarm_b.dispatch = AsyncMock(return_value={"status": "error", "error": "b failed"})

    orch._swarms = {"a": swarm_a, "b": swarm_b}

    result = asyncio.get_event_loop().run_until_complete(
        orch.dispatch("totally_unknown_task_type", {"query": "x"})
    )

    assert result["status"] == "error"
    assert "No swarm handled" in result["error"]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
