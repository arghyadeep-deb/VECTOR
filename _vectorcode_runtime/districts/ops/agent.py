"""
OpsSwarm — orchestrates ops district Python agents.

Wraps DevOpsAutomator, ErrorClassifier, IncidentCommander, SREMonitor
into a unified dispatch interface for the SwarmOrchestrator.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.city.agent_base import AgentBase
from core.city.agent_registry import get_registry
from core.config import CONFIG

DISTRICT = Path(__file__).parent.name

TASK_ROLE_MAP: dict[str, set[str]] = {
    "deploy": {"devops", "automator", "ci", "cd"},
    "devops": {"devops", "automator", "infra"},
    "restart": {"devops", "automator", "process"},
    "backup": {"devops", "automator", "backup"},
    "incident": {"incident", "commander", "response", "pager"},
    "post_mortem": {"incident", "commander", "postmortem"},
    "classify_error": {"error", "classifier", "diagnose", "log"},
    "slo": {"sre", "monitor", "sli", "alert"},
    "uptime": {"sre", "monitor", "health", "probe"},
    "monitor_system": {"sre", "monitor", "observability"},
    "default": {"devops"},
}

class OpsSwarm(AgentBase):
    """Orchestrator for ops district — wraps 4 Python agents into a unified dispatch."""

    def __init__(self):
        agent_id = "ops-swarm-001"
        name = "OpsSwarm"
        super().__init__(agent_id=agent_id, name=name, district=DISTRICT)
        self.capabilities = ["general", "type"]
        self.health_points = 1000  # HP is capped at 1000 (was 1200); still far above the district's other agents
        self._agents: dict[str, AgentBase] = {}
        self._agent_roles: dict[str, str] = {}
        self._load_agents()

    def _load_agents(self) -> None:
        registry = get_registry()

        agents_to_import: list[tuple[str, str, str]] = [
            ("DevOpsAutomator", "districts.ops.devops_automator", "devops-automator"),
            ("ErrorClassifier", "districts.ops.error_classifier", "error-classifier"),
            ("IncidentCommander", "districts.ops.incident_commander", "incident-commander"),
            ("SREMonitor", "districts.ops.sre_monitor", "sre-monitor"),
        ]

        for class_name, module_name, role_handle in agents_to_import:
            agent_id = f"ops_{role_handle.replace('-', '_')}_swarm_001"

            if registry.get(agent_id):
                self._agents[agent_id] = registry.get(agent_id)
                self._agent_roles[agent_id] = role_handle
                continue

            try:
                import importlib
                mod = importlib.import_module(module_name)
                cls = getattr(mod, class_name)
                agent = cls()
                registry.register(agent)
                self._agents[agent_id] = agent
                self._agent_roles[agent_id] = role_handle
                logger.debug("[OpsSwarm] loaded agent: {} ({})", class_name, agent_id)
            except Exception as e:
                logger.warning("[OpsSwarm] failed to load {}: {}", class_name, e)

        logger.info("[OpsSwarm] {} specialist agents loaded", len(self._agents))

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
            logger.debug("[OpsSwarm] matched '{}' → {} (score={:.2f})", task_type, best_id, best_score)
            return self._agents[best_id]
        return None

    async def dispatch(self, task_type: str, params: dict[str, Any]) -> dict[str, Any]:
        agent = self._select_agent(task_type)
        if agent:
            try:
                # 2026-09-24 (independent review finding -- HIGH): passing
                # `params` straight through let a caller's own nested
                # params["type"] silently BE the type the selected agent
                # reads, with the real, Governor-authorized `task_type`
                # never enforced at all -- e.g. task_type="incident" (a
                # harmless outer identity) could carry
                # params={"type": "cleanup_logs", ...} and reach
                # DevOpsAutomator.cleanup_logs() with zero relationship to
                # what was actually authorized. `task_type` must always
                # win over anything the caller put in params.
                return await agent.run({**params, "type": task_type})
            except Exception as e:
                logger.warning("[OpsSwarm] agent {} failed: {} — falling back", agent.name, e)
        return await self._fallback_response(task_type, params)

    async def _fallback_response(self, task_type: str, params: dict[str, Any]) -> dict[str, Any]:
        from core.inference.vectorcode_llm import chat
        query = params.get("query", params.get("prompt", f"Handle ops task: {task_type}"))
        context = params.get("context", "")
        messages = [
            {"role": "system", "content": (
                f"You are OpsSwarm, VECTOR's operations orchestrator. No specialist matched '{task_type}'. "
                f"Handle it directly. If asked about VECTOR's own configuration, tools, models, or settings "
                f"you don't have in front of you, say so plainly rather than inventing plausible-sounding details."
            )},
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
        # 2026-07-30 audit fix: same "empty query" bug class as
        # FinanceSwarm/ResearchSwarm (see districts/finance/agent.py) —
        # governor.dispatch() nests the real user text at
        # task["params"]["query"], not task["query"]; passing `task` itself
        # as `params` left it invisible to dispatch()'s
        # params.get("query", ...) read.
        task_type = task.get("type", task.get("task_type", "default"))
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
        swarm = OpsSwarm()
        for tt in ["deploy", "incident", "classify_error", "slo", "monitor_system"]:
            agent = swarm._select_agent(tt)
            print(f"  {tt:20s} → {agent.name if agent else 'NONE'}")
        print(f"Loaded {len(swarm._agents)} ops agents")
        print("OpsSwarm OK")
    asyncio.run(_smoke())
