"""SwarmCoordinator — VectorCode VC-3. Manages pools of specialized agents."""
import sys
from enum import Enum
from pathlib import Path
from typing import List, Optional
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from loguru import logger


class Topology(Enum):
    HIERARCHICAL = "hierarchical"
    MESH = "mesh"
    ADAPTIVE = "adaptive"


_DOMAIN_KEYWORDS = {
    "security": ["security", "auth", "encrypt", "vuln", "threat", "audit", "crypto", "injection"],
    "devops":   ["deploy", "ci", "cd", "docker", "k8s", "infra", "git", "pipeline", "release"],
    "research": ["research", "analyze", "market", "paper", "data", "trend", "news", "summarize"],
    "support":  ["help", "onboard", "train", "feedback", "incident", "bug", "escalat", "report"],
}

_AGENT_MAP = {
    "coder":           "CoderAgent",
    "reviewer":        "ReviewerAgent",
    "tester":          "TesterAgent",
    "debugger":        "DebuggerAgent",
    "architect":       "ArchitectAgent",
    "security":        "SecurityAuditorAgent",
    "securityauditor": "SecurityAuditorAgent",
    "gitbot":          "GitBotAgent",
    "docwriter":       "DocWriterAgent",
    "optimizer":       "OptimizerAgent",
    "webscout":        "WebScoutAgent",
    "mleng":           "MLEngineerAgent",
}


class SwarmCoordinator:
    def __init__(
        self,
        topology: Topology = Topology.HIERARCHICAL,
        max_agents: int = 60,
    ) -> None:
        self.topology = topology
        self.max_agents = max_agents
        self._agents: List = []

    def spawn(self, agent_type: str):
        """Instantiate and register a named agent. Raises RuntimeError at capacity."""
        if len(self._agents) >= self.max_agents:
            raise RuntimeError(
                f"SwarmCoordinator at capacity ({self.max_agents} agents)"
            )
        from agents.districts.coding.vectorcode import agent_types as at
        key = agent_type.lower().replace("_", "").replace(" ", "")
        class_name = _AGENT_MAP.get(key, agent_type.capitalize() + "Agent")
        cls = getattr(at, class_name, None)
        if cls is None:
            logger.warning(f"[VECTOR][swarm] unknown agent type {agent_type!r}, defaulting to CoderAgent")
            cls = at.CoderAgent
        agent = cls()
        self._agents.append(agent)
        logger.info(f"[VECTOR][swarm] spawned {agent.name} (topology={self.topology.value})")
        return agent

    def route_to_domain(self, task: str) -> str:
        """Map a task description to a domain using keyword matching."""
        task_lower = task.lower()
        for domain, keywords in _DOMAIN_KEYWORDS.items():
            if any(kw in task_lower for kw in keywords):
                return domain
        return "core"

    def list_agents(self) -> List:
        return list(self._agents)

    def shutdown(self) -> None:
        logger.info(f"[VECTOR][swarm] shutdown — clearing {len(self._agents)} agents")
        self._agents.clear()

    def report(self) -> dict:
        return {
            "topology": self.topology.value,
            "max_agents": self.max_agents,
            "active": len(self._agents),
            "agents": [a.name for a in self._agents],
        }


if __name__ == "__main__":
    sc = SwarmCoordinator(max_agents=3)
    a = sc.spawn("coder")
    assert a.name == "CoderAgent"
    domain = sc.route_to_domain("write a unit test for security module")
    assert domain == "security", f"got {domain}"
    print("swarm.py OK")
