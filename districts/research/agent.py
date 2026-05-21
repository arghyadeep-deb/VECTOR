"""
ResearchSwarm — orchestrates research district agents (.md prompts + Python agents).

Loads 1 .md prompt agent and wraps 8 Python AgentBase subclasses.
"""
from __future__ import annotations

import sys
import asyncio
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.city.agent_base import AgentBase
from core.city.prompt_agent import PromptAgent
from core.city.agent_registry import get_registry
from core.config import CONFIG

DISTRICT = Path(__file__).parent.name

TASK_ROLE_MAP: dict[str, set[str]] = {
    "research": {"researcher", "research", "hub"},
    "deep_research": {"deep", "researcher", "research"},
    "news": {"news", "aggregator"},
    "paper": {"paper", "reader", "academic"},
    "reddit": {"reddit", "miner", "social"},
    "web_scout": {"web", "scout", "crawl"},
    "stealth": {"stealth", "scout", "intel"},
    "cli_adapter": {"cli", "adapter", "opencli"},
    "default": {"research", "researcher"},
}

PYTHON_AGENTS: list[tuple[str, str, str]] = [
    ("deep_researcher", "DeepResearcher", "deep-research"),
    ("news_aggregator", "NewsAggregator", "news"),
    ("paper_reader", "PaperReader", "paper"),
    ("reddit_miner", "RedditMiner", "reddit"),
    ("research_hub", "ResearchHub", "hub"),
    ("stealth_scout_agent", "StealthScoutAgent", "stealth"),
    ("web_scout", "WebScout", "web-scout"),
    ("opencli_adapter", "OpenCLIAdapter", "cli-adapter"),
]


class ResearchSwarm(AgentBase):
    """Orchestrator for research district."""

    def __init__(self):
        agent_id = "research-swarm-001"
        name = "ResearchSwarm"
        super().__init__(agent_id=agent_id, name=name, district=DISTRICT)
        self.health_points = 900
        self._agents: dict[str, AgentBase] = {}
        self._agent_roles: dict[str, str] = {}
        self._load_agents()

    def _load_agents(self) -> None:
        registry = get_registry()
        self._load_md_agents(registry)
        self._load_python_agents(registry)
        logger.info("[ResearchSwarm] {} agents loaded", len(self._agents))

    def _load_md_agents(self, registry) -> None:
        md_path = Path(__file__).parent / "vector-researcher.md"
        if not md_path.exists():
            return
        agent_id = "research_vector_researcher_swarm_001"
        if registry.get(agent_id):
            self._agents[agent_id] = registry.get(agent_id)
            self._agent_roles[agent_id] = "researcher"
            return
        try:
            md_path_str = str(md_path)
            AgentClass = type(
                "VectorResearcher",
                (PromptAgent,),
                {"__init__": lambda self, _p=md_path_str, _i=agent_id, _d=DISTRICT: PromptAgent.__init__(self, _p, _i, _d)},
            )
            agent = AgentClass()
            registry.register(agent)
            self._agents[agent_id] = agent
            self._agent_roles[agent_id] = "researcher"
            logger.debug("[ResearchSwarm] loaded .md agent: VectorResearcher")
        except Exception as e:
            logger.warning("[ResearchSwarm] failed to load .md: {}", e)

    def _load_python_agents(self, registry) -> None:
        for module_name, class_name, role_handle in PYTHON_AGENTS:
            agent_id = f"research_{role_handle.replace('-', '_')}_swarm_001"
            if registry.get(agent_id):
                self._agents[agent_id] = registry.get(agent_id)
                self._agent_roles[agent_id] = role_handle
                continue
            try:
                import importlib
                mod = importlib.import_module(f"districts.research.{module_name}")
                cls = getattr(mod, class_name)
                agent = cls()
                registry.register(agent)
                self._agents[agent_id] = agent
                self._agent_roles[agent_id] = role_handle
                logger.debug("[ResearchSwarm] loaded agent: {} ({})", class_name, agent_id)
            except Exception as e:
                logger.warning("[ResearchSwarm] failed to load {}: {}", class_name, e)

    def _score_agent_match(self, agent_id: str, task_type: str) -> float:
        role = self._agent_roles.get(agent_id, "")
        task_keywords = TASK_ROLE_MAP.get(task_type, TASK_ROLE_MAP["default"])
        role_lower = role.lower()
        matched = sum(1 for kw in task_keywords if kw in role_lower)
        return min(matched / max(len(task_keywords), 1) * 2.0, 1.0)

    def _select_agent(self, task_type: str) -> AgentBase | None:
        if not self._agents:
            return None
        scored = [(aid, self._score_agent_match(aid, task_type)) for aid in self._agents]
        scored.sort(key=lambda x: x[1], reverse=True)
        best_id, best_score = scored[0]
        if best_score > 0:
            return self._agents[best_id]
        return None

    async def dispatch(self, task_type: str, params: dict[str, Any]) -> dict[str, Any]:
        agent = self._select_agent(task_type)
        if agent:
            try:
                if isinstance(agent, PromptAgent):
                    return await agent.run({
                        "query": params.get("query", params.get("prompt", "")),
                        "context": params.get("context", ""),
                        "timeout": params.get("timeout", 60.0),
                    })
                return await agent.run({"type": task_type, **params})
            except Exception as e:
                logger.warning("[ResearchSwarm] agent {} failed: {} — falling back", agent.name, e)
        return await self._fallback_response(task_type, params)

    async def _fallback_response(self, task_type: str, params: dict[str, Any]) -> dict[str, Any]:
        from core.inference.vectorcode_llm import chat
        query = params.get("query", params.get("prompt", f"Handle research task: {task_type}"))
        context = params.get("context", "")
        messages = [
            {"role": "system", "content": f"You are ResearchSwarm, VECTOR's research orchestrator. No specialist matched '{task_type}'. Handle it directly."},
        ]
        if context:
            messages.append({"role": "user", "content": f"[Context]\n{context}"})
        messages.append({"role": "user", "content": query})
        try:
            model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
            response = chat(model=model, messages=messages, timeout=60.0)
            return {"status": "ok", "response": response, "agent": self.name, "fallback": True}
        except Exception as e:
            return {"status": "error", "error": str(e), "agent": self.name}

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", task.get("task_type", "default"))
        return await self.dispatch(task_type, task)


if __name__ == "__main__":
    async def _smoke():
        import sys as _sys
        _sys.stdout.reconfigure(encoding="utf-8")
        swarm = ResearchSwarm()
        for tt in ["deep_research", "news", "paper", "reddit", "stealth"]:
            agent = swarm._select_agent(tt)
            print(f"  {tt:20s} → {agent.name if agent else 'NONE'}")
        print(f"Loaded {len(swarm._agents)} research agents")
        print("ResearchSwarm OK")
    asyncio.run(_smoke())
