# VectorCode VC-3: Swarm + Queen + GSD Loop

**Goal:** Build the UnifiedSwarmCoordinator, QueenCoordinator, and GSD workflow loop that orchestrate 60+ specialized agents across hierarchical/mesh/adaptive topologies.
**Architecture:** SwarmCoordinator manages agent pools by domain (core/security/devops/research/support). Queen decomposes user tasks into subtasks and assigns to domains. GSDLoop implements discuss→plan→execute→verify using SemanticRouter model selection. All agents inherit from AgentBase. All LLM calls via ollama_safe. Pattern cache consulted before discuss phase.
**Files:**
- Create: `agents/districts/coding/vectorcode/swarm.py`
- Create: `agents/districts/coding/vectorcode/queen.py`
- Create: `agents/districts/coding/vectorcode/gsd_loop.py`
- Create: `agents/districts/coding/vectorcode/agent_types.py`
- Create: `tests/test_vectorcode_vc3.py`

---

### Task 1: Agent types — 60+ specialized agents

- [ ] Write failing test
  ```python
  from agents.districts.coding.vectorcode.agent_types import (
      CoderAgent, ReviewerAgent, TesterAgent, DebuggerAgent,
      ArchitectAgent, SecurityAuditorAgent, GitBotAgent,
      DocWriterAgent, OptimizerAgent, WebScoutAgent
  )
  def test_all_agent_types_inherit_base():
      from core.city.agent_base import AgentBase
      for cls in [CoderAgent, ReviewerAgent, TesterAgent, DebuggerAgent,
                  ArchitectAgent, SecurityAuditorAgent, GitBotAgent,
                  DocWriterAgent, OptimizerAgent, WebScoutAgent]:
          assert issubclass(cls, AgentBase)
  def test_agent_has_correct_model():
      a = CoderAgent()
      assert a.model == "vector-coder"
      r = ReviewerAgent()
      assert r.model == "vector-dev"
  def test_agent_has_domain():
      a = SecurityAuditorAgent()
      assert a.domain in {"core", "security", "devops", "research", "support"}
  def test_agent_count():
      from agents.districts.coding.vectorcode import agent_types
      import inspect
      agents = [c for _, c in inspect.getmembers(agent_types, inspect.isclass)
                if c.__name__.endswith("Agent") and c.__name__ != "AgentBase"]
      assert len(agents) >= 20
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc3.py -k "agent_type" -v` → expect FAIL
- [ ] Implement `agents/districts/coding/vectorcode/agent_types.py` (60+ agent classes)
- [ ] Run: `pytest tests/test_vectorcode_vc3.py -k "agent_type" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc3): 60+ specialized agent type definitions"`

---

### Task 2: UnifiedSwarmCoordinator

- [ ] Write failing test
  ```python
  from unittest.mock import patch, MagicMock
  from agents.districts.coding.vectorcode.swarm import SwarmCoordinator, Topology
  def test_swarm_init_hierarchical():
      sc = SwarmCoordinator(topology=Topology.HIERARCHICAL, max_agents=8)
      assert sc.topology == Topology.HIERARCHICAL
      assert sc.max_agents == 8
  def test_swarm_spawn_agent():
      sc = SwarmCoordinator()
      agent = sc.spawn("coder")
      assert agent is not None
      assert agent.name == "CoderAgent"
  def test_swarm_domain_routing():
      sc = SwarmCoordinator()
      domain = sc.route_to_domain("write a unit test")
      assert domain in {"core", "security", "devops", "research", "support"}
  def test_swarm_topologies_exist():
      assert hasattr(Topology, "HIERARCHICAL")
      assert hasattr(Topology, "MESH")
      assert hasattr(Topology, "ADAPTIVE")
  def test_swarm_max_agents_respected():
      sc = SwarmCoordinator(max_agents=3)
      for i in range(3):
          sc.spawn("coder")
      import pytest
      with pytest.raises(RuntimeError):
          sc.spawn("coder")
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc3.py -k "swarm" -v` → expect FAIL
- [ ] Implement `agents/districts/coding/vectorcode/swarm.py`
- [ ] Run: `pytest tests/test_vectorcode_vc3.py -k "swarm" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc3): UnifiedSwarmCoordinator hierarchical/mesh/adaptive"`

---

### Task 3: QueenCoordinator — task decomposition

- [ ] Write failing test
  ```python
  from unittest.mock import patch, MagicMock
  from agents.districts.coding.vectorcode.queen import QueenCoordinator
  def test_queen_decomposes_task():
      with patch("agents.districts.coding.vectorcode.queen.chat") as mock_chat:
          mock_chat.return_value = '{"subtasks": [{"task": "write function", "domain": "core"}, {"task": "write tests", "domain": "core"}]}'
          q = QueenCoordinator()
          subtasks = q.decompose("build a login endpoint")
          assert len(subtasks) >= 1
          assert all("task" in s and "domain" in s for s in subtasks)
  def test_queen_uses_reasoning_model():
      with patch("agents.districts.coding.vectorcode.queen.chat") as mock_chat:
          mock_chat.return_value = '{"subtasks": []}'
          q = QueenCoordinator()
          q.decompose("any task")
          call_args = mock_chat.call_args
          assert call_args[1]["model"] == "vector-reasoning" or call_args[0][0] == "vector-reasoning"
  def test_queen_fallback_on_bad_json():
      with patch("agents.districts.coding.vectorcode.queen.chat") as mock_chat:
          mock_chat.return_value = "not valid json"
          q = QueenCoordinator()
          subtasks = q.decompose("any task")
          assert isinstance(subtasks, list)
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc3.py -k "queen" -v` → expect FAIL
- [ ] Implement `agents/districts/coding/vectorcode/queen.py`
- [ ] Run: `pytest tests/test_vectorcode_vc3.py -k "queen" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc3): QueenCoordinator task decomposition"`

---

### Task 4: GSDLoop — discuss→plan→execute→verify

- [ ] Write failing test
  ```python
  from unittest.mock import patch, MagicMock, AsyncMock
  import asyncio
  from agents.districts.coding.vectorcode.gsd_loop import GSDLoop, GSDPhase
  def test_gsd_phases_exist():
      assert hasattr(GSDPhase, "DISCUSS")
      assert hasattr(GSDPhase, "PLAN")
      assert hasattr(GSDPhase, "EXECUTE")
      assert hasattr(GSDPhase, "VERIFY")
  def test_gsd_loop_instantiates():
      loop = GSDLoop(mode="auto")
      assert loop.mode == "auto"
      assert loop.current_phase == GSDPhase.DISCUSS
  def test_gsd_skips_discuss_on_pattern_hit():
      with patch("agents.districts.coding.vectorcode.gsd_loop.PatternStore") as MockPS:
          mock_ps = MagicMock()
          mock_ps.recall.return_value = {"plan": ["step1"], "reward": 0.9}
          MockPS.return_value = mock_ps
          loop = GSDLoop(mode="auto")
          assert loop.should_skip_discuss("write login") is True
  def test_gsd_does_not_skip_without_pattern():
      with patch("agents.districts.coding.vectorcode.gsd_loop.PatternStore") as MockPS:
          mock_ps = MagicMock()
          mock_ps.recall.return_value = None
          MockPS.return_value = mock_ps
          loop = GSDLoop(mode="auto")
          assert loop.should_skip_discuss("novel task never seen before") is False
  def test_gsd_max_retries():
      loop = GSDLoop(mode="auto")
      assert loop.MAX_VERIFY_RETRIES == 3
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc3.py -k "gsd" -v` → expect FAIL
- [ ] Implement `agents/districts/coding/vectorcode/gsd_loop.py`
- [ ] Run: `pytest tests/test_vectorcode_vc3.py -k "gsd" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc3): GSDLoop discuss→plan→execute→verify"`

---

### Task 5: Full VC-3 integration smoke

- [ ] Run: `pytest tests/test_vectorcode_vc3.py -v` → all pass
- [ ] Commit: `git commit -m "feat(vc3): swarm/queen/gsd complete — 60+ agents, 3 topologies"`
