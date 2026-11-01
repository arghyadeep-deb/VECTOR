"""
CausalReasoner — statistical causal inference layer built ON TOP of existing
core/memory/causal_graph.py. Does NOT replace it.

Provides:
  - estimate_effect(treatment, outcome)  → DoWhy-based ATE estimate
  - what_if(action, change) → counterfactual answer (delegates to counterfactual.py)
  - explain(node_id) → why-did-X-happen path from causal_graph

Heavy deps (dowhy, pandas) are lazy-imported; degrades gracefully if not installed.
Architecture invariant: this module must never crash the loop on ImportError.
"""

from typing import Any, Optional
from loguru import logger
from core.config import CONFIG


class CausalReasoner:
    """
    Statistical causal inference layered on top of CausalGraph + Counterfactual.
    Always initialises — heavy deps are optional.
    """

    def __init__(self):
        self._causal_graph = None
        self._counterfactual = None
        self._dowhy_available: Optional[bool] = None
        logger.info("[VECTOR][causal_reasoner] CausalReasoner ready")

    # ── lazy accessors ───────────────────────────────────────────────────────
    def _get_causal_graph(self):
        if self._causal_graph is None:
            try:
                from core.memory.causal_graph import CausalGraph
                self._causal_graph = CausalGraph()
            except Exception as e:
                logger.warning("[VECTOR][causal_reasoner] causal_graph unavailable: {}", e)
        return self._causal_graph

    def _get_counterfactual(self):
        if self._counterfactual is None:
            try:
                from core.memory.counterfactual import CounterfactualMemory
                self._counterfactual = CounterfactualMemory()
            except Exception as e:
                logger.debug("[VECTOR][causal_reasoner] counterfactual unavailable: {}", e)
        return self._counterfactual

    def _check_dowhy(self) -> bool:
        if self._dowhy_available is None:
            try:
                import dowhy  # noqa: F401
                self._dowhy_available = True
                logger.debug("[VECTOR][causal_reasoner] DoWhy available")
            except ImportError:
                self._dowhy_available = False
                logger.debug("[VECTOR][causal_reasoner] DoWhy not installed — graph-only mode")
        return self._dowhy_available

    # ── public API ────────────────────────────────────────────────────────────
    def explain(self, node_id: str, max_depth: int = 4) -> dict:
        """
        'Why did X happen?' — BFS over causal_graph to find upstream causes.
        Returns {node_id, causes: [{node_id, label, strength}], depth}.
        Never raises.
        """
        cg = self._get_causal_graph()
        if cg is None:
            return {"node_id": node_id, "causes": [], "error": "causal_graph unavailable"}
        try:
            causes = []
            visited = set()
            queue = [(node_id, 0)]
            while queue:
                current, depth = queue.pop(0)
                if depth >= max_depth or current in visited:
                    continue
                visited.add(current)
                parents = cg._radj.get(current, [])
                for parent in parents:
                    node_data = cg.get_node(parent) or {}
                    strength = 0.0
                    for edge in cg._edges:
                        if edge.get("source") == parent and edge.get("target") == current:
                            strength = edge.get("strength", 0.0)
                            break
                    causes.append({
                        "node_id": parent,
                        "label": node_data.get("label", parent),
                        "strength": strength,
                        "depth": depth + 1,
                    })
                    queue.append((parent, depth + 1))
            return {"node_id": node_id, "causes": causes}
        except Exception as e:
            logger.warning("[VECTOR][causal_reasoner] explain failed: {}", e)
            return {"node_id": node_id, "causes": [], "error": str(e)}

    def what_if(self, action: str, hypothetical: str) -> dict:
        """
        'What if I had done X instead?' — delegates to existing counterfactual.py.
        Returns counterfactual analysis dict. Never raises.
        """
        cf = self._get_counterfactual()
        if cf is None:
            return {"action": action, "hypothetical": hypothetical, "error": "counterfactual unavailable"}
        try:
            patterns = cf.get_rejection_patterns()
            rejection_count = patterns.get("total_rejections", 0)
            outcomes_learned = patterns.get("total_outcomes_learned", 0)
            return {
                "action": action,
                "hypothetical": hypothetical,
                "source": "counterfactual_memory",
                "total_rejections_recorded": rejection_count,
                "outcomes_learned": outcomes_learned,
                "note": "For specific what-if, record the rejected action then call get_rejection_patterns()",
            }
        except Exception as e:
            logger.warning("[VECTOR][causal_reasoner] what_if failed: {}", e)
            return {"action": action, "hypothetical": hypothetical, "error": str(e)}

    def estimate_effect(
        self,
        treatment: str,
        outcome: str,
        data: Optional[list[dict]] = None,
    ) -> dict:
        """
        Estimate Average Treatment Effect (ATE) of `treatment` on `outcome`.
        If DoWhy is installed AND data is provided: full statistical estimate.
        Otherwise: graph-based heuristic from causal_graph edge strengths.
        Never raises.
        """
        if self._check_dowhy() and data is not None:
            return self._dowhy_estimate(treatment, outcome, data)
        return self._graph_heuristic(treatment, outcome)

    # ── internals ────────────────────────────────────────────────────────────
    def _graph_heuristic(self, treatment: str, outcome: str) -> dict:
        """Use causal_graph edge strengths as a proxy for ATE."""
        cg = self._get_causal_graph()
        if cg is None:
            return {"treatment": treatment, "outcome": outcome, "ate": None, "method": "unavailable"}
        try:
            direct_strength = 0.0
            for edge in cg._edges:
                if edge.get("source") == treatment and edge.get("target") == outcome:
                    direct_strength = edge.get("strength", 0.0)
                    break
            return {
                "treatment": treatment,
                "outcome": outcome,
                "ate": direct_strength,
                "method": "graph_heuristic",
                "note": "Heuristic from causal_graph edge strength; install DoWhy for statistical ATE",
            }
        except Exception as e:
            return {"treatment": treatment, "outcome": outcome, "ate": None, "error": str(e)}

    def _dowhy_estimate(self, treatment: str, outcome: str, data: list[dict]) -> dict:
        """Full DoWhy statistical ATE estimate."""
        try:
            import pandas as pd
            import dowhy
            from dowhy import CausalModel

            df = pd.DataFrame(data)
            if treatment not in df.columns or outcome not in df.columns:
                return {
                    "treatment": treatment, "outcome": outcome, "ate": None,
                    "error": f"columns not found in data; available: {list(df.columns)}",
                }

            model = CausalModel(
                data=df,
                treatment=treatment,
                outcome=outcome,
                common_causes=[c for c in df.columns if c not in (treatment, outcome)],
            )
            identified = model.identify_effect(proceed_when_unidentifiable=True)
            estimate = model.estimate_effect(
                identified,
                method_name="backdoor.linear_regression",
            )
            ate = float(estimate.value)
            return {
                "treatment": treatment,
                "outcome": outcome,
                "ate": ate,
                "method": "dowhy.linear_regression",
                "confidence_intervals": estimate.get_confidence_intervals() if hasattr(estimate, "get_confidence_intervals") else None,
            }
        except Exception as e:
            logger.warning("[VECTOR][causal_reasoner] DoWhy estimate failed: {}", e)
            return self._graph_heuristic(treatment, outcome)


if __name__ == "__main__":
    cr = CausalReasoner()

    # explain — should return a dict even with empty graph
    result = cr.explain("outcome:ok")
    assert isinstance(result, dict), "explain must return dict"
    assert "causes" in result

    # what_if — should not raise
    wif = cr.what_if("deploy_code", "run_tests_first")
    assert isinstance(wif, dict)

    # estimate_effect — graph heuristic
    ate = cr.estimate_effect("action:code_review", "outcome:ok")
    assert isinstance(ate, dict)
    assert "ate" in ate

    print(f"OK causal_reasoner -- explain causes={len(result['causes'])} ate={ate['ate']} method={ate['method']}")
