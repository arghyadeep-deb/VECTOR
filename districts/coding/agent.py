"""
CodingSwarm — orchestrates coding district agents (.md prompts + Python agents).

Loads 10 .md prompt agents and wraps 14 Python AgentBase subclasses into
a unified dispatch. Routes tasks by keyword matching across all specialists.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.city.agent_base import AgentBase
from core.city.prompt_agent import PromptAgent
from core.city.agent_registry import get_registry
from core.config import CONFIG

DISTRICT = Path(__file__).parent.name

TASK_ROLE_MAP: dict[str, set[str]] = {
    "code_review": {"review", "reviewer", "code"},
    "architecture": {"architect", "design", "architecture"},
    "code_explore": {"explorer", "explore", "code"},
    "refactor": {"refactor", "cleaner", "clean"},
    "performance": {"performance", "optimizer", "optimize"},
    "test": {"test", "engineer", "qa"},
    "bug": {"bug", "hunter", "silent", "failure"},
    "frontend": {"frontend", "ui", "web"},
    "backend": {"backend", "api", "server"},
    "database": {"database", "optimizer", "sql"},
    "mlops": {"mlops", "ml", "model"},
    "git": {"git", "bot"},
    "rapid_prototype": {"prototyper", "rapid", "prototype"},
    "conductor": {"conductor", "orchestrator"},
    "code_intel": {"intel", "intelligence", "code"},
    "gui_automation": {"gui", "automation"},
    "developer_advocate": {"advocate", "developer"},
    "onboarding": {"onboarding", "codebase"},
    "minimal_change": {"minimal", "change", "surgical"},
    "default": {"code", "coder", "developer"},
}

# Python AgentBase classes to wrap (module: class_name)
PYTHON_AGENTS: list[tuple[str, str, str]] = [
    ("architect_bot", "ArchitectBot", "architect"),
    ("bug_hunter", "BugHunter", "bug-hunter"),
    ("codebase_onboarding_engineer", "CodebaseOnboardingEngineer", "onboarding"),
    ("code_conductor_agent", "CodeConductorAgent", "conductor"),
    ("code_intel_agent", "CodeIntelAgent", "code-intel"),
    ("code_reviewer", "CodeReviewer", "code-reviewer"),
    ("database_optimizer", "DatabaseOptimizer", "database-optimizer"),
    ("frontend_developer", "FrontendDeveloper", "frontend-developer"),
    ("git_bot", "GitBot", "git"),
    ("gui_automation_agent", "GUIAutomationAgent", "gui"),
    ("minimal_change_engineer", "MinimalChangeEngineer", "minimal-change"),
    ("mlops_agent", "MLOpsAgent", "mlops"),
    ("rapid_prototyper", "RapidPrototyper", "rapid-prototype"),
    ("test_writer", "TestWriter", "test-writer"),
]

class CodingSwarm(AgentBase):
    """Orchestrator for coding district — routes tasks across .md + Python agents."""

    def __init__(self):
        agent_id = "coding-swarm-001"
        name = "CodingSwarm"
        super().__init__(agent_id=agent_id, name=name, district=DISTRICT)
        # 2026-08-06: governor capability declarations — see architect_bot.py
        self.capabilities = [
            "code_review", "architecture", "code_explore", "refactor",
            "performance", "test", "bug", "frontend", "backend",
            "database", "mlops", "git", "rapid_prototype", "conductor",
            "code_intel", "gui_automation", "developer_advocate",
            "onboarding", "minimal_change", "research",
        ]
        self.health_points = 1000  # HP is capped at 1000 (was 1500); still far above the district's other agents
        self._agents: dict[str, AgentBase] = {}
        self._agent_roles: dict[str, str] = {}
        self._load_agents()

    def _load_agents(self) -> None:
        registry = get_registry()
        self._load_md_agents(registry)
        self._load_python_agents(registry)
        logger.info("[CodingSwarm] {} total agents loaded", len(self._agents))

    def _load_md_agents(self, registry) -> None:
        md_dir = Path(__file__).parent
        for md_file in sorted(md_dir.glob("vector-*.md")):
            stem = md_file.stem
            agent_id = f"coding_{stem.replace('-', '_').lower()}_swarm_001"

            if registry.get(agent_id):
                self._agents[agent_id] = registry.get(agent_id)
                self._agent_roles[agent_id] = stem
                continue

            try:
                md_path_str = str(md_file)
                role_name = stem.replace("vector-", "").replace("-", " ").title()
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
                self._agent_roles[agent_id] = stem.replace("vector-", "")
                logger.debug("[CodingSwarm] loaded .md agent: {} ({})", role_name, agent_id)
            except Exception as e:
                logger.warning("[CodingSwarm] failed to load .md {}: {}", md_file.name, e)

    def _load_python_agents(self, registry) -> None:
        for module_name, class_name, role_handle in PYTHON_AGENTS:
            agent_id = f"coding_{role_handle.replace('-', '_')}_swarm_001"

            if registry.get(agent_id):
                self._agents[agent_id] = registry.get(agent_id)
                self._agent_roles[agent_id] = f"coding-{role_handle}"
                continue

            try:
                import importlib
                full_module = f"districts.coding.{module_name}"
                mod = importlib.import_module(full_module)
                cls = getattr(mod, class_name)
                agent = cls()
                registry.register(agent)
                self._agents[agent_id] = agent
                self._agent_roles[agent_id] = f"coding-{role_handle}"
                logger.debug("[CodingSwarm] loaded Python agent: {} ({})", class_name, agent_id)
            except Exception as e:
                logger.warning("[CodingSwarm] failed to load {}: {}", class_name, e)

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
            logger.debug("[CodingSwarm] matched '{}' → {} (score={:.2f})", task_type, best_id, best_score)
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
                # 2026-09-24 (independent review finding -- HIGH): dict
                # literal order meant a caller-supplied params["type"]
                # silently OVERWROTE the real, Governor-authorized
                # task_type here (later key wins) -- e.g. an UNKNOWN outer
                # type could carry params={"type": "code_conduct", ...}
                # and CodeConductorAgent would read task["type"] ==
                # "code_conduct" (its own real, dangerous action) despite
                # never having been authorized as that action_type.
                # task_type must always win over anything in params.
                return await agent.run({**params, "type": task_type})
            except Exception as e:
                logger.warning("[CodingSwarm] agent {} failed: {} — falling back", agent.name, e)
        return await self._fallback_response(task_type, params)

    async def _fallback_response(self, task_type: str, params: dict[str, Any]) -> dict[str, Any]:
        from core.inference.vectorcode_llm import chat
        from core.loop.context_engine import ContextEngine
        query = params.get("query", params.get("prompt", f"Handle coding task: {task_type}"))
        context = params.get("context", "")
        # RULE 1: session_hydration_prompt() before every LLM call -- this
        # fallback built its own system message and called chat() directly
        # with no hydration at all.
        hydration = ContextEngine().session_hydration_prompt({"query": query})
        messages = [
            {"role": "system", "content": f"{hydration}\n\nYou are CodingSwarm, VECTOR's coding orchestrator. No specialist matched '{task_type}'. Handle it directly."},
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
        if task_type == "research":
            artifact = task.get("params") if isinstance(task.get("params"), dict) else {}
            sources = artifact.get("sources") if isinstance(artifact, dict) else None
            if artifact.get("artifact_type") != "trend_research_handoff" or not isinstance(sources, list):
                return {"status": "error", "agent": self.name, "reason": "valid trend research artifact is required"}
            self.know("latest_trend_research_handoff", artifact)
            return {
                "status": "ok", "agent": self.name, "accepted": True,
                "source_count": len(sources),
                "next_step": "convert one cited opportunity into a reversible build brief before implementation",
            }
        # 2026-07-29: governor._dispatch_to_district calls agent.run(task)
        # directly with the real user text nested at task["params"]["query"]
        # (or ["content"]) -- not at task["query"]. dispatch()/
        # _fallback_response() below read params.get("query", ...), so
        # passing `task` itself as `params` (the old behavior) left the
        # nested query invisible and every free-text chat message that
        # reached CodingSwarm this way fell to the generic
        # "Handle coding task: X" stub. Flatten the real query onto the
        # params dict dispatch() actually reads -- same precedence used by
        # every other district's fix this pass.
        real_query = (
            (task.get("params") or {}).get("query")
            or (task.get("params") or {}).get("content")
            or task.get("query")
            or task.get("prompt")
            or ""
        )
        params = dict(task.get("params") or {})
        params.setdefault("query", real_query)
        for k, v in task.items():
            if k not in ("type", "task_type", "params"):
                params.setdefault(k, v)
        return await self.dispatch(task_type, params)

if __name__ == "__main__":
    async def _smoke():
        import sys as _sys
        _sys.stdout.reconfigure(encoding="utf-8")
        swarm = CodingSwarm()
        for tt in ["code_review", "architecture", "refactor", "test", "frontend", "bug"]:
            agent = swarm._select_agent(tt)
            print(f"  {tt:20s} → {agent.name if agent else 'NONE'}")
        print(f"Loaded {len(swarm._agents)} coding agents")
        print("CodingSwarm OK")
    asyncio.run(_smoke())
