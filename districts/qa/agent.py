"""
QASwarm — orchestrates QA district Python agents.

Wraps 11 Python agents (accessibility_auditor, api_tester, evidence_collector,
model_qa_specialist, reality_checker, silent_failure_hunter, test_engineer,
test_results_analyzer, tool_evaluator, workflow_architect, workflow_optimizer).
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
    "qa": {"qa", "test", "quality"},
    "accessibility": {"accessibility", "wcag", "a11y"},
    "api_testing": {"api", "tester"},
    "evidence": {"evidence", "collector"},
    "model_qa": {"model", "qa"},
    "reality_check": {"reality", "checker"},
    "silent_failure": {"silent", "failure", "hunter"},
    "test_engineer": {"test", "engineer"},
    "test_results": {"test", "results", "analyzer"},
    "tool_evaluation": {"tool", "evaluator"},
    "workflow_architect": {"workflow", "architect"},
    "workflow_optimizer": {"workflow", "optimizer"},
    "default": {"qa", "test"},
}

PYTHON_AGENTS: list[tuple[str, str]] = [
    ("accessibility_auditor", "AccessibilityAuditor"),
    ("api_tester", "APITester"),
    ("evidence_collector", "EvidenceCollector"),
    ("model_qa_specialist", "ModelQASpecialist"),
    ("reality_checker", "RealityChecker"),
    ("silent_failure_hunter", "SilentFailureHunter"),
    ("test_engineer", "TestEngineer"),
    ("test_results_analyzer", "TestResultsAnalyzer"),
    ("tool_evaluator", "ToolEvaluator"),
    ("workflow_architect", "WorkflowArchitect"),
    ("workflow_optimizer", "WorkflowOptimizer"),
]

class QASwarm(AgentBase):
    """Orchestrator for QA district — routes tasks across 11 Python agents."""

    def __init__(self):
        agent_id = "qa-swarm-001"
        name = "QASwarm"
        super().__init__(agent_id=agent_id, name=name, district=DISTRICT)
        self.capabilities = ["general", "type"]
        self.health_points = 1000
        self._agents: dict[str, AgentBase] = {}
        self._agent_roles: dict[str, str] = {}
        self._load_agents()

    def _load_agents(self) -> None:
        # 2026-09-29: this used to dedup-check registry.get(f"qa_{role}_swarm_001") -- a key
        # no agent is ever actually registered under (each specialist class sets its OWN
        # agent.id internally: a fixed string for some, uuid.uuid4() for others; none of them
        # match this swarm-invented naming scheme). The check therefore always missed, so every
        # QASwarm() construction created and registered 11 brand-new specialist instances into
        # the shared AgentRegistry -- accumulating duplicates across repeated instantiations,
        # and making these agents unreachable via A2A under the id an external caller would
        # reasonably guess. Fixed: dedup by real class+district match already in the registry,
        # and key self._agents/_agent_roles by the agent's own real .id, not a guessed string.
        registry = get_registry()
        for module_name, class_name in PYTHON_AGENTS:
            role_handle = module_name
            try:
                import importlib
                full_module = f"districts.qa.{module_name}"
                mod = importlib.import_module(full_module)
                cls = getattr(mod, class_name)

                existing = next(
                    (
                        a for a in registry.get_all_agents()
                        if type(a).__name__ == class_name and getattr(a, "district", None) == DISTRICT
                    ),
                    None,
                )
                agent = existing if existing is not None else cls()
                if existing is None:
                    registry.register(agent)

                self._agents[agent.id] = agent
                self._agent_roles[agent.id] = role_handle
                logger.debug("[QASwarm] loaded agent: {} ({})", class_name, agent.id)
            except Exception as e:
                logger.warning("[QASwarm] failed to load {}: {}", class_name, e)

        logger.info("[QASwarm] {} agents loaded", len(self._agents))

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
            logger.debug("[QASwarm] matched '{}' → {} (score={:.2f})", task_type, best_id, best_score)
            return self._agents[best_id]
        return None

    async def dispatch(self, task_type: str, params: dict[str, Any]) -> dict[str, Any]:
        agent = self._select_agent(task_type)
        if agent:
            try:
                # 2026-09-24 (independent review finding -- HIGH, same
                # class found in CodingSwarm): task_type must always win
                # over anything the caller put in params, never the
                # reverse.
                return await agent.run({**params, "type": task_type})
            except Exception as e:
                logger.warning("[QASwarm] agent {} failed: {} — falling back", agent.name, e)
        return await self._fallback_response(task_type, params)

    async def _fallback_response(self, task_type: str, params: dict[str, Any]) -> dict[str, Any]:
        from core.inference.vectorcode_llm import chat
        query = params.get("query", params.get("prompt", f"Handle QA task: {task_type}"))
        context = params.get("context", "")
        messages = [
            {"role": "system", "content": f"You are QASwarm, VECTOR's QA orchestrator. No specialist matched '{task_type}'. Handle it directly."},
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
        # FinanceSwarm/ResearchSwarm/OpsSwarm (see districts/finance/agent.py)
        # — governor.dispatch() nests the real user text at
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
        swarm = QASwarm()
        for tt in ["accessibility", "api_testing", "reality_check", "silent_failure", "model_qa"]:
            agent = swarm._select_agent(tt)
            print(f"  {tt:20s} → {agent.name if agent else 'NONE'}")
        print(f"Loaded {len(swarm._agents)} QA agents")
        print("QASwarm OK")
    asyncio.run(_smoke())
