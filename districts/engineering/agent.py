"""
EngineeringSwarm — orchestrates 30+ engineering .md prompt agents.

Auto-discovers all engineering-*.md files in this directory, instantiates each
as a PromptAgent, and routes incoming tasks to the agent with the best role match.
Fallback chain: specialist agent → general engineering → district LLM.
"""
from __future__ import annotations

import sys
import uuid
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

# Role keywords map: task_type → set of keywords to match against .md agent names/roles
TASK_ROLE_MAP: dict[str, set[str]] = {
    "backend": {"backend", "architect", "api", "database", "scalable"},
    "frontend": {"frontend", "ui", "web", "react", "css"},
    "ai": {"ai", "engineer", "ml", "machine", "learning", "model", "llm"},
    "ml": {"ai", "engineer", "ml", "machine", "learning", "model"},
    "data": {"data", "engineer", "pipeline", "etl", "analytics"},
    "devops": {"devops", "automator", "ci", "cd", "deploy", "sre"},
    "sre": {"sre", "site", "reliability", "monitoring", "incident"},
    "security": {"security", "threat", "detection", "engineer"},
    "code_review": {"code", "reviewer", "review"},
    "architecture": {"architect", "software", "design", "system"},
    "mobile": {"mobile", "app", "ios", "android"},
    "embedded": {"embedded", "firmware"},
    "blockchain": {"solidity", "smart", "contract", "blockchain"},
    "rapid_prototype": {"rapid", "prototyper", "prototype"},
    "technical_writing": {"technical", "writer", "documentation"},
    "voice": {"voice", "ai", "integration"},
    "onboarding": {"onboarding", "codebase"},
    "email": {"email", "intelligence"},
    "git": {"git", "workflow", "version", "control"},
    "incident_response": {"incident", "response", "commander", "sre"},
    "senior_dev": {"senior", "developer"},
    "filament": {"filament", "optimization"},
    "feishu": {"feishu", "integration"},
    "wechat": {"wechat", "mini", "program"},
    "minimal_change": {"minimal", "change"},
    "cms": {"cms", "content", "management"},
    "memory": {"memory", "backend", "architect"},
    "data_remediation": {"data", "remediation", "engineer"},
    "autonomous": {"autonomous", "optimization", "architect"},
    "default": {"engineering"},  # catch-all
}


class EngineeringSwarm(AgentBase):
    """Orchestrator for engineering district — routes tasks to specialist .md agents."""

    def __init__(self):
        agent_id = "engineering-swarm-001"
        name = "EngineeringSwarm"
        super().__init__(agent_id=agent_id, name=name, district=DISTRICT)
        self.health_points = 800
        self._agents: dict[str, PromptAgent] = {}
        self._agent_roles: dict[str, str] = {}
        self._load_agents()

    def _load_agents(self) -> None:
        """Discover and instantiate all engineering-*.md files as PromptAgents."""
        md_dir = Path(__file__).parent
        registry = get_registry()

        for md_file in sorted(md_dir.glob("engineering-*.md")):
            stem = md_file.stem
            agent_id = f"{stem.replace('-', '_').lower()}_swarm_001"
            role_name = stem.replace("engineering-", "").replace("-", " ").title()

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
                logger.debug("[EngineeringSwarm] loaded .md agent: {} ({})", role_name, agent_id)
            except Exception as e:
                logger.warning("[EngineeringSwarm] failed to load {}: {}", md_file.name, e)

        logger.info("[EngineeringSwarm] {} specialist agents loaded", len(self._agents))

    def _score_agent_match(self, agent_id: str, task_type: str) -> float:
        """Score how well an agent matches a task type (0.0-1.0)."""
        role = self._agent_roles.get(agent_id, "")
        task_keywords = TASK_ROLE_MAP.get(task_type, TASK_ROLE_MAP["default"])

        if not task_keywords:
            return 0.0

        role_lower = role.lower()
        matched = sum(1 for kw in task_keywords if kw in role_lower)
        return min(matched / max(len(task_keywords), 1) * 2.0, 1.0)

    def _select_agent(self, task_type: str) -> PromptAgent | None:
        """Select the best-matching agent for a task type."""
        if not self._agents:
            return None

        scored = [
            (agent_id, self._score_agent_match(agent_id, task_type))
            for agent_id in self._agents
        ]
        scored.sort(key=lambda x: x[1], reverse=True)

        best_id, best_score = scored[0]
        if best_score > 0:
            logger.debug("[EngineeringSwarm] matched '{}' → {} (score={:.2f})", task_type, best_id, best_score)
            return self._agents[best_id]

        return None

    async def dispatch(self, task_type: str, params: dict[str, Any]) -> dict[str, Any]:
        """Route a task to the best specialist agent. Fallback chain if none matches."""
        agent = self._select_agent(task_type)

        if agent:
            try:
                result = await agent.run({
                    "query": params.get("query", params.get("prompt", "")),
                    "context": params.get("context", ""),
                    "timeout": params.get("timeout", 60.0),
                })
                return result
            except Exception as e:
                logger.warning("[EngineeringSwarm] agent {} failed: {} — falling back", agent.name, e)

        return await self._fallback_response(task_type, params)

    async def _fallback_response(self, task_type: str, params: dict[str, Any]) -> dict[str, Any]:
        """Fallback: use this swarm agent's own LLM when no specialist matches."""
        from core.inference.vectorcode_llm import chat

        query = params.get("query", params.get("prompt", f"Handle engineering task: {task_type}"))
        context = params.get("context", "")

        messages = [
            {"role": "system", "content": f"""You are EngineeringSwarm, the orchestrator for VECTOR's engineering district.
You have 30+ specialist engineering agents but none matched task type '{task_type}'.
Handle this task directly using your general engineering knowledge.
Be practical, give code or architecture, and note which specialist would be better suited."""},
        ]
        if context:
            messages.append({"role": "user", "content": f"[Context]\n{context}"})
        messages.append({"role": "user", "content": query})

        try:
            model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
            response = chat(model=model, messages=messages, timeout=60.0)
            return {"status": "ok", "response": response, "agent": self.name, "fallback": True}
        except Exception as e:
            logger.error("[EngineeringSwarm] fallback failed: {}", e)
            return {"status": "error", "error": str(e), "agent": self.name}

    async def run(self, task: dict) -> dict:
        """Main entry — accepts task dict, routes through dispatch."""
        task_type = task.get("type", task.get("task_type", "default"))
        return await self.dispatch(task_type, task)


if __name__ == "__main__":
    async def _smoke():
        import sys as _sys
        _sys.stdout.reconfigure(encoding="utf-8")

        swarm = EngineeringSwarm()
        result = await swarm.dispatch("backend", {"query": "Design a scalable microservice architecture"})
        print(f"[EngineeringSwarm] dispatch result: {result.get('status')}")
        if result.get("status") == "ok":
            print(f"[EngineeringSwarm] response length: {len(result.get('response', ''))} chars")
        print("EngineeringSwarm OK")

    asyncio.run(_smoke())
