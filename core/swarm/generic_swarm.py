"""
GenericSwarm — auto-discovers .md prompts + Python AgentBase subclasses for any district.

One class to rule them all: eliminates needing per-district agent.py files.
"""
from __future__ import annotations

__all__ = [
    "DISTRICTS_ROOT",
    "GenericSwarm",
]


import asyncio
import importlib
from pathlib import Path
from typing import Any


from loguru import logger
from core.city.agent_base import AgentBase
from core.city.prompt_agent import PromptAgent
from core.city.agent_registry import get_registry
from core.config import CONFIG

DISTRICTS_ROOT = Path(__file__).parent.parent.parent / "districts"


class GenericSwarm(AgentBase):
    """Auto-discovering swarm for any district. Finds all .md prompts + Python agents.

    Usage:
        swarm = GenericSwarm("security")
        await swarm.dispatch("security_audit", {"query": "..."})
    """

    def __init__(self, district: str):
        super().__init__(
            agent_id=f"{district}-swarm-auto-001",
            name=f"{district.title()}Swarm",
            district=district,
        )
        self.health_points = 600
        self._agents: dict[str, AgentBase] = {}
        self._agent_roles: dict[str, str] = {}
        self._district = district
        self._load_agents()

    def _load_agents(self) -> None:
        registry = get_registry()
        district_dir = DISTRICTS_ROOT / self._district

        if not district_dir.exists():
            logger.warning("[GenericSwarm] district '{}' not found", self._district)
            return

        self._load_md_agents(registry, district_dir)
        self._load_python_agents(registry, district_dir)
        logger.info("[GenericSwarm] {} district: {} agents loaded", self._district, len(self._agents))

    def _load_md_agents(self, registry, district_dir: Path) -> None:
        for md_file in sorted(district_dir.glob("*.md")):
            stem = md_file.stem
            lower = stem.lower()
            if lower in ("readme", "quickstart", "nexus-strategy", "executive-brief", "__init__"):
                continue
            agent_id = f"{self._district}_{stem.replace('-', '_').lower()}_swarm_001"
            if registry.get(agent_id):
                self._agents[agent_id] = registry.get(agent_id)
                self._agent_roles[agent_id] = stem
                continue
            try:
                md_path_str = str(md_file)
                class_name = "".join(w.capitalize() for w in stem.replace("-", " ").split())
                AgentClass = type(
                    class_name,
                    (PromptAgent,),
                    {"__init__": lambda self, _p=md_path_str, _i=agent_id, _d=self._district:
                        PromptAgent.__init__(self, _p, _i, _d)},
                )
                agent = AgentClass()
                registry.register(agent)
                self._agents[agent_id] = agent
                self._agent_roles[agent_id] = stem
                logger.debug("[GenericSwarm/{}.md] loaded: {}", self._district, md_file.name)
            except Exception as e:
                logger.warning("[GenericSwarm/{}.md] fail {}: {}", self._district, md_file.name, e)

    def _load_python_agents(self, registry, district_dir: Path) -> None:
        for py_file in sorted(district_dir.glob("*.py")):
            if py_file.name.startswith("__") or py_file.name == "agent.py":
                continue
            module_name = py_file.stem
            full_module = f"districts.{self._district}.{module_name}"
            try:
                mod = importlib.import_module(full_module)
            except Exception:
                continue
            for attr_name in dir(mod):
                try:
                    obj = getattr(mod, attr_name)
                    if (
                        isinstance(obj, type)
                        and issubclass(obj, AgentBase)
                        and obj is not AgentBase
                        and obj is not PromptAgent
                        and getattr(obj, "__module__", "") == full_module
                        and attr_name[0].isupper()
                    ):
                        agent_id = f"{self._district}_{module_name}_swarm_001"
                        if registry.get(agent_id):
                            self._agents[agent_id] = registry.get(agent_id)
                            self._agent_roles[agent_id] = module_name
                            continue
                        try:
                            agent = obj()
                            registry.register(agent)
                            self._agents[agent_id] = agent
                            self._agent_roles[agent_id] = module_name
                            logger.debug("[GenericSwarm/{}.py] loaded: {}", self._district, py_file.name)
                        except Exception as e:
                            logger.debug("[GenericSwarm/{}.py] skip {}: {}", self._district, py_file.name, e)
                except Exception:
                    continue

    def _score_match(self, agent_id: str, task_type: str) -> float:
        role = self._agent_roles.get(agent_id, "")
        role_lower = role.lower()
        task_lower = task_type.lower().replace("_", "-")
        role_words = set(role_lower.replace("-", " ").replace("_", " ").split())
        task_words = set(task_lower.replace("-", " ").replace("_", " ").split())
        intersection = role_words & task_words
        if not intersection:
            return 0.0
        return min(len(intersection) / max(len(task_words), 1) * 2.0, 1.0)

    def _select_agent(self, task_type: str) -> AgentBase | None:
        if not self._agents:
            return None
        scored = [(aid, self._score_match(aid, task_type)) for aid in self._agents]
        scored.sort(key=lambda x: x[1], reverse=True)
        best_id, best_score = scored[0]
        if best_score > 0:
            logger.debug("[GenericSwarm/{}] '{}' → {} (score={:.2f})", self._district, task_type, best_id, best_score)
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
                logger.warning("[GenericSwarm/{}] {} failed: {} — fallback", self._district, agent.name, e)
        return await self._fallback(task_type, params)

    async def _fallback(self, task_type: str, params: dict[str, Any]) -> dict[str, Any]:
        from core.inference.vectorcode_llm import chat
        from core.loop.context_engine import ContextEngine
        query = params.get("query", params.get("prompt", f"{self._district}: {task_type}"))
        context = params.get("context", "")
        # RULE 1: session_hydration_prompt() before every LLM call.
        hydration = ContextEngine().session_hydration_prompt({"query": query})
        messages = [
            {"role": "system", "content": hydration},
            {"role": "system", "content": f"You are {self._district.title()}Swarm. No specialist for '{task_type}'."},
        ]
        if context:
            messages.append({"role": "user", "content": f"[Context]\n{context}"})
        messages.append({"role": "user", "content": query})
        try:
            model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
            return {"status": "ok", "response": await chat(model=model, messages=messages, timeout=60), "agent": self.name, "fallback": True}
        except Exception as e:
            return {"status": "error", "error": str(e), "agent": self.name}

    async def run(self, task: dict) -> dict:
        return await self.dispatch(task.get("type", task.get("task_type", "default")), task)


if __name__ == "__main__":
    async def _test():
        import sys as _s; _s.stdout.reconfigure(encoding="utf-8")
        for d in ["security", "governance", "design", "marketing", "sales", "support", "project_management", "spatial_computing", "academic", "game_development", "paid_media", "communications"]:
            s = GenericSwarm(d)
            print(f"  {d:25s} → {len(s._agents)} agents")
    asyncio.run(_test())
