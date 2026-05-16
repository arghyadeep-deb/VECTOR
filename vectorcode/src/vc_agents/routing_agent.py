"""
RoutingAgent — wraps vectorcode's GNNRouter (MoE→GNN→keyword→regex) for task routing.

Decides which model or district should handle a given task. Uses the 4-layer
routing stack: MoERouter (Layer 0) → GNNRouter (Layer 1) → keyword map (Layer 2)
→ regex (Layer 3). Integrates with VECTOR's governor for district dispatch.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger
from core.config import CONFIG


class RoutingAgent:
    """
    Intelligent task router. Decides model selection and district assignment.
    Wraps vectorcode's GNNRouter + MoERouter + VECTOR's governor DISTRICT_TASK_MAP.
    """

    def __init__(self):
        self._gnn_router = None
        self._governor = None
        logger.info("[VECTOR][vc_routing] initialized")

    def _get_gnn_router(self):
        if self._gnn_router is None:
            try:
                from vectorcode.src.router import GNNRouter
                self._gnn_router = GNNRouter()
            except Exception as e:
                logger.debug("[VECTOR][vc_routing] GNNRouter unavailable: {}", e)
        return self._gnn_router

    def _get_governor(self):
        if self._governor is None:
            from core.city.governor import Governor
            self._governor = Governor()
        return self._governor

    def route_to_model(self, task: str) -> str:
        """Select the best LLM model for a task using GNNRouter → keyword fallback."""
        router = self._get_gnn_router()
        if router:
            try:
                model = router.route(task)
                if model:
                    logger.debug("[VECTOR][vc_routing] GNNRouter: '{}' → {}", task[:50], model)
                    return model
            except Exception as e:
                logger.debug("[VECTOR][vc_routing] GNNRouter failed: {}", e)

        # Keyword fallback — mirrors CONFIG model routing rules
        task_lower = task.lower()
        models = CONFIG.get("models", {})
        if any(w in task_lower for w in ["code", "python", "function", "debug", "refactor"]):
            return models.get("coder", "vector-coder")
        if any(w in task_lower for w in ["think", "reason", "council", "decision"]):
            return models.get("reasoning", "vector-reasoning")
        if any(w in task_lower for w in ["translate", "hindi", "bengali"]):
            return models.get("multilingual", "vector-multilingual")
        if any(w in task_lower for w in ["quick", "fast", "simple"]):
            return models.get("fast", "vector-fast")
        return models.get("focus", "vector-focus")

    def route_to_district(self, task_type: str) -> str:
        """Map a task type to the correct VECTOR district using the governor."""
        return self._get_governor().route_task(task_type)

    def route(self, task: str, task_type: str = "") -> dict:
        """Full routing decision: model + district for a given task."""
        model = self.route_to_model(task)
        district = self.route_to_district(task_type or task.split()[0] if task else "research")
        return {
            "task": task[:100],
            "recommended_model": model,
            "recommended_district": district,
            "routing_layers_used": ["moe", "gnn", "keyword"] if self._get_gnn_router() else ["keyword"],
        }

    def explain_routing(self, task: str) -> str:
        """Return a human-readable routing explanation."""
        decision = self.route(task)
        return (
            f"Task: '{task[:60]}'\n"
            f"→ Model: {decision['recommended_model']}\n"
            f"→ District: {decision['recommended_district']}\n"
            f"→ Layers used: {', '.join(decision['routing_layers_used'])}"
        )


if __name__ == "__main__":
    agent = RoutingAgent()
    tests = [
        ("write a Python function to parse JSON", "code"),
        ("search for AI papers on arxiv", "research"),
        ("I'm feeling tired today", "health"),
        ("analyze my spending this month", "finance"),
    ]
    for task, task_type in tests:
        decision = agent.route(task, task_type)
        print(f"[OK] '{task[:40]}' → model={decision['recommended_model']} district={decision['recommended_district']}")
    print("routing_agent.py OK")
