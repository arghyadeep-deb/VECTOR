"""
SpecializedSwarm — orchestrates specialized domain .md prompt agents.

Auto-discovers all specialized-*.md files in this directory, instantiates each
as a PromptAgent, and routes domain-specific tasks to the best-matching specialist.
Fallback chain: specialist agent → GenericSwarm → district LLM.
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
    "blockchain": {"blockchain", "smart", "contract", "audit"},
    "legal": {"legal", "document", "review", "compliance"},
    "healthcare": {"healthcare", "medical", "patient", "compliance"},
    "hr": {"hr", "onboarding", "recruitment", "employee"},
    "real_estate": {"real", "estate", "property", "valuation"},
    "default": {"specialized"},
}


class SpecializedSwarm(AgentBase):
    """Orchestrator for specialized district — routes domain tasks to specialist .md agents."""

    def __init__(self):
        agent_id = "specialized-swarm-001"
        name = "SpecializedSwarm"
        super().__init__(agent_id=agent_id, name=name, district=DISTRICT)
        self.health_points = 800
        self._agents: dict[str, PromptAgent] = {}
        self._agent_roles: dict[str, str] = {}
        self._load_agents()

    def _load_agents(self) -> None:
        """Discover and instantiate all specialized-*.md files as PromptAgents."""
        md_dir = Path(__file__).parent
        registry = get_registry()

        for md_file in sorted(md_dir.glob("specialized-*.md")):
            stem = md_file.stem
            agent_id = f"{stem.replace('-', '_').lower()}_swarm_001"
            role_name = stem.replace("specialized-", "").replace("-", " ").title()

            if registry.get(agent_id):
                continue

            try:
                md_path_str = str(md_file)
                AgentClass = type(
                    role_name.replace(" ", ""),
                    (PromptAgent,),
                    {
                        "__init__": lambda self, _p=md_path_str, _i=agent_id, _d=DISTRICT:
                            PromptAgent.__init__(self, _p, _i, _d)
                    },
                )
                agent = AgentClass()
                registry.register(agent)
                self._agents[agent_id] = agent
                self._agent_roles[agent_id] = stem
                logger.debug("[SpecializedSwarm] loaded .md agent: {} ({})", role_name, agent_id)
            except Exception as e:
                logger.warning("[SpecializedSwarm] failed to load {}: {}", md_file.name, e)

        logger.info("[SpecializedSwarm] {} specialist agents loaded", len(self._agents))

    def _score_agent_match(self, agent_id: str, task_type: str) -> float:
        role = self._agent_roles.get(agent_id, "")
        task_keywords = TASK_ROLE_MAP.get(task_type, TASK_ROLE_MAP["default"])
        if not task_keywords:
            return 0.0
        role_lower = role.lower()
        matched = sum(1 for kw in task_keywords if kw in role_lower)
        return min(matched / max(len(task_keywords), 1) * 2.0, 1.0)

    def _select_agent(self, task_type: str) -> PromptAgent | None:
        if not self._agents:
            return None
        scored = [(aid, self._score_agent_match(aid, task_type)) for aid in self._agents]
        scored.sort(key=lambda x: x[1], reverse=True)
        best_id, best_score = scored[0]
        if best_score > 0:
            logger.debug("[SpecializedSwarm] matched '{}' → {} (score={:.2f})", task_type, best_id, best_score)
            return self._agents[best_id]
        return None

    async def dispatch(self, task_type: str, params: dict[str, Any]) -> dict[str, Any]:
        agent = self._select_agent(task_type)
        if agent:
            try:
                return await agent.run({
                    "query": params.get("query", params.get("prompt", "")),
                    "context": params.get("context", ""),
                    "timeout": params.get("timeout", 60.0),
                })
            except Exception as e:
                logger.warning("[SpecializedSwarm] agent {} failed: {} — falling back", agent.name, e)
        return await self._fallback_response(task_type, params)

    async def _fallback_response(self, task_type: str, params: dict[str, Any]) -> dict[str, Any]:
        from core.inference.vectorcode_llm import chat
        query = params.get("query", params.get("prompt", f"Handle specialized task: {task_type}"))
        context = params.get("context", "")
        messages = [
            {"role": "system", "content": f"You are SpecializedSwarm, VECTOR's domain specialist orchestrator. No specialist matched '{task_type}'. Handle it directly."},
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
        swarm = SpecializedSwarm()
        for tt in ["blockchain", "legal", "healthcare", "hr", "real_estate"]:
            agent = swarm._select_agent(tt)
            print(f"  {tt:20s} → {agent.name if agent else 'NONE'}")
        print(f"Loaded {len(swarm._agents)} specialized agents")
        print("SpecializedSwarm OK")
    asyncio.run(_smoke())
