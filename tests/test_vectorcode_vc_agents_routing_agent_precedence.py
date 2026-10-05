"""Regression for vectorcode/src/vc_agents/routing_agent.py's RoutingAgent.route():

`X or Y if C else Z` parses in Python as `(X or Y) if C else Z`, not the
intended `X or (Y if C else Z)`. The pre-fix code was
`task_type or task.split()[0] if task else "research"`, which parsed as
`(task_type or task.split()[0]) if task else "research"` -- so an
explicitly-passed task_type was silently discarded and replaced with the
hardcoded "research" default whenever task happened to be empty. A
whitespace-only task would also IndexError on task.split()[0] since
" ".split() == [] (empty), not [""].
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.vc_agents.routing_agent import RoutingAgent


def _agent_with_mock_governor():
    agent = RoutingAgent()
    mock_governor = MagicMock()
    mock_governor.route_task.side_effect = lambda task_type: task_type
    agent._governor = mock_governor
    return agent


def test_explicit_task_type_is_not_discarded_when_task_is_empty():
    agent = _agent_with_mock_governor()
    with patch.object(RoutingAgent, "_get_gnn_router", return_value=None):
        decision = agent.route(task="", task_type="code")
    assert decision["recommended_district"] == "code"


def test_task_first_word_used_when_task_type_omitted():
    agent = _agent_with_mock_governor()
    with patch.object(RoutingAgent, "_get_gnn_router", return_value=None):
        decision = agent.route(task="finance report please", task_type="")
    assert decision["recommended_district"] == "finance"


def test_research_default_when_both_empty():
    agent = _agent_with_mock_governor()
    with patch.object(RoutingAgent, "_get_gnn_router", return_value=None):
        decision = agent.route(task="", task_type="")
    assert decision["recommended_district"] == "research"


def test_whitespace_only_task_does_not_crash():
    agent = _agent_with_mock_governor()
    with patch.object(RoutingAgent, "_get_gnn_router", return_value=None):
        decision = agent.route(task="   ", task_type="")
    assert decision["recommended_district"] == "research"


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
