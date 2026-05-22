import inspect
import pytest
from unittest.mock import patch, MagicMock


# ─── Agent Types ──────────────────────────────────────────────────────────────

def test_all_agent_types_inherit_base():
    from core.city.agent_base import AgentBase
    from vectorcode.src.agent_types import (
        CoderAgent, ReviewerAgent, TesterAgent, DebuggerAgent,
        ArchitectAgent, SecurityAuditorAgent, GitBotAgent,
        DocWriterAgent, OptimizerAgent, WebScoutAgent
    )
    for cls in [CoderAgent, ReviewerAgent, TesterAgent, DebuggerAgent,
                ArchitectAgent, SecurityAuditorAgent, GitBotAgent,
                DocWriterAgent, OptimizerAgent, WebScoutAgent]:
        assert issubclass(cls, AgentBase), f"{cls.__name__} must inherit AgentBase"

def test_agent_has_correct_model():
    from vectorcode.src.agent_types import CoderAgent, ReviewerAgent
    a = CoderAgent()
    assert a.model == "vector-coder"
    r = ReviewerAgent()
    assert r.model == "vector-dev"

def test_agent_has_domain():
    from vectorcode.src.agent_types import SecurityAuditorAgent
    a = SecurityAuditorAgent()
    assert a.domain in {"core", "security", "devops", "research", "support"}

def test_agent_count():
    from vectorcode.src import agent_types
    agents = [c for _, c in inspect.getmembers(agent_types, inspect.isclass)
              if c.__name__.endswith("Agent") and c.__name__ != "AgentBase"]
    assert len(agents) >= 20, f"Expected 20+ agent types, got {len(agents)}"


# ─── SwarmCoordinator ─────────────────────────────────────────────────────────

def test_swarm_init_hierarchical():
    from vectorcode.src.swarm import SwarmCoordinator, Topology
    sc = SwarmCoordinator(topology=Topology.HIERARCHICAL, max_agents=8)
    assert sc.topology == Topology.HIERARCHICAL
    assert sc.max_agents == 8

def test_swarm_spawn_agent():
    from vectorcode.src.swarm import SwarmCoordinator
    sc = SwarmCoordinator()
    agent = sc.spawn("coder")
    assert agent is not None
    assert agent.name == "CoderAgent"

def test_swarm_domain_routing():
    from vectorcode.src.swarm import SwarmCoordinator
    sc = SwarmCoordinator()
    domain = sc.route_to_domain("write a unit test")
    assert domain in {"core", "security", "devops", "research", "support"}

def test_swarm_topologies_exist():
    from vectorcode.src.swarm import Topology
    assert hasattr(Topology, "HIERARCHICAL")
    assert hasattr(Topology, "MESH")
    assert hasattr(Topology, "ADAPTIVE")

def test_swarm_max_agents_respected():
    from vectorcode.src.swarm import SwarmCoordinator
    sc = SwarmCoordinator(max_agents=3)
    for _ in range(3):
        sc.spawn("coder")
    with pytest.raises(RuntimeError):
        sc.spawn("coder")

def test_swarm_agent_list():
    from vectorcode.src.swarm import SwarmCoordinator
    sc = SwarmCoordinator(max_agents=5)
    sc.spawn("coder")
    sc.spawn("reviewer")
    agents = sc.list_agents()
    assert len(agents) == 2

def test_swarm_shutdown():
    from vectorcode.src.swarm import SwarmCoordinator
    sc = SwarmCoordinator()
    sc.spawn("coder")
    sc.shutdown()
    assert len(sc.list_agents()) == 0


# ─── QueenCoordinator ─────────────────────────────────────────────────────────

def test_queen_decomposes_task():
    with patch("vectorcode.src.queen.chat") as mock_chat:
        mock_chat.return_value = '{"subtasks": [{"task": "write function", "domain": "core"}, {"task": "write tests", "domain": "core"}]}'
        from vectorcode.src.queen import QueenCoordinator
        q = QueenCoordinator()
        subtasks = q.decompose("build a login endpoint")
        assert len(subtasks) >= 1
        assert all("task" in s and "domain" in s for s in subtasks)

def test_queen_uses_reasoning_model():
    with patch("vectorcode.src.queen.chat") as mock_chat:
        mock_chat.return_value = '{"subtasks": []}'
        from vectorcode.src.queen import QueenCoordinator
        q = QueenCoordinator()
        q.decompose("any task")
        call_args = mock_chat.call_args
        model_arg = call_args[0][0] if call_args[0] else call_args[1].get("model")
        assert model_arg == "vector-reasoning"

def test_queen_fallback_on_bad_json():
    with patch("vectorcode.src.queen.chat") as mock_chat:
        mock_chat.return_value = "not valid json"
        from vectorcode.src.queen import QueenCoordinator
        q = QueenCoordinator()
        subtasks = q.decompose("any task")
        assert isinstance(subtasks, list)

def test_queen_fallback_subtask_structure():
    with patch("vectorcode.src.queen.chat") as mock_chat:
        mock_chat.return_value = "broken"
        from vectorcode.src.queen import QueenCoordinator
        q = QueenCoordinator()
        subtasks = q.decompose("build something")
        assert len(subtasks) >= 1
        assert "task" in subtasks[0]


# ─── GSDLoop ──────────────────────────────────────────────────────────────────

def test_gsd_phases_exist():
    from vectorcode.src.gsd_loop import GSDPhase
    assert hasattr(GSDPhase, "DISCUSS")
    assert hasattr(GSDPhase, "PLAN")
    assert hasattr(GSDPhase, "EXECUTE")
    assert hasattr(GSDPhase, "VERIFY")

def test_gsd_loop_instantiates():
    from vectorcode.src.gsd_loop import GSDLoop, GSDPhase
    loop = GSDLoop(mode="auto")
    assert loop.mode == "auto"
    assert loop.current_phase == GSDPhase.DISCUSS

def test_gsd_skips_discuss_on_pattern_hit():
    with patch("vectorcode.src.gsd_loop.PatternStore") as MockPS:
        mock_ps = MagicMock()
        mock_ps.recall.return_value = {"plan": ["step1"], "reward": 0.9}
        MockPS.return_value = mock_ps
        from vectorcode.src.gsd_loop import GSDLoop
        loop = GSDLoop(mode="auto")
        assert loop.should_skip_discuss("write login") is True

def test_gsd_does_not_skip_without_pattern():
    with patch("vectorcode.src.gsd_loop.PatternStore") as MockPS:
        mock_ps = MagicMock()
        mock_ps.recall.return_value = None
        MockPS.return_value = mock_ps
        from vectorcode.src.gsd_loop import GSDLoop
        loop = GSDLoop(mode="auto")
        assert loop.should_skip_discuss("novel task never seen before") is False

def test_gsd_max_retries():
    from vectorcode.src.gsd_loop import GSDLoop
    loop = GSDLoop(mode="auto")
    assert loop.MAX_VERIFY_RETRIES == 3

def test_gsd_advance_phase():
    from vectorcode.src.gsd_loop import GSDLoop, GSDPhase
    loop = GSDLoop(mode="auto")
    assert loop.current_phase == GSDPhase.DISCUSS
    loop.advance()
    assert loop.current_phase == GSDPhase.PLAN
    loop.advance()
    assert loop.current_phase == GSDPhase.EXECUTE
    loop.advance()
    assert loop.current_phase == GSDPhase.VERIFY

def test_gsd_reset():
    from vectorcode.src.gsd_loop import GSDLoop, GSDPhase
    loop = GSDLoop(mode="auto")
    loop.advance()
    loop.advance()
    loop.reset()
    assert loop.current_phase == GSDPhase.DISCUSS
    assert loop.verify_retries == 0
