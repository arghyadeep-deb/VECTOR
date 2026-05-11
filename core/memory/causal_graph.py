"""
V.E.C.T.O.R. CausalGraph.
Tracks cause-effect relationships between V.E.C.T.O.R. actions and outcomes.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger
import uuid
from datetime import datetime
from collections import defaultdict


class CausalGraph:
    """
    Stores cause-effect chains: action -> outcome -> consequence.
    Enables V.E.C.T.O.R. to learn what actually works.
    """

    def __init__(self):
        self._nodes: dict[str, dict] = {}
        self._edges: list[dict] = []
        self._adj: dict[str, list[str]] = defaultdict(list)
        logger.info("[VECTOR][causal_graph] CausalGraph initialized")

    def add_node(self, node_id: str, node_type: str, label: str, metadata: dict | None = None) -> dict:
        """Add a causal node (action, event, outcome)."""
        node = {
            "id": node_id,
            "type": node_type,
            "label": label,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "weight": 0.0,
        }
        self._nodes[node_id] = node
        logger.info(f"[VECTOR][causal_graph] Node added: {node_id} ({node_type})")
        return node

    def add_edge(self, from_id: str, to_id: str, strength: float = 1.0, label: str = "") -> dict:
        """Add causal edge from -> to with strength (0-1)."""
        if from_id not in self._nodes or to_id not in self._nodes:
            return {"status": "error", "detail": "Node not found"}
        edge = {
            "from": from_id,
            "to": to_id,
            "strength": strength,
            "label": label,
            "created_at": datetime.utcnow().isoformat(),
        }
        self._edges.append(edge)
        self._adj[from_id].append(to_id)
        logger.info(f"[VECTOR][causal_graph] Edge: {from_id} -> {to_id} (strength={strength})")
        return edge

    def get_outcomes(self, action_id: str) -> list[dict]:
        """Get all outcomes of an action."""
        outcomes = []
        for edge in self._edges:
            if edge["from"] == action_id:
                node = self._nodes.get(edge["to"], {})
                outcomes.append({**edge, "outcome_node": node})
        return outcomes

    def get_causes(self, outcome_id: str) -> list[dict]:
        """Get all causes of an outcome."""
        causes = []
        for edge in self._edges:
            if edge["to"] == outcome_id:
                node = self._nodes.get(edge["from"], {})
                causes.append({**edge, "cause_node": node})
        return causes

    def update_edge_strength(self, from_id: str, to_id: str, new_strength: float):
        """Update the strength of a causal edge (learning)."""
        for edge in self._edges:
            if edge["from"] == from_id and edge["to"] == to_id:
                edge["strength"] = max(0.0, min(1.0, new_strength))
                logger.info(f"[VECTOR][causal_graph] Edge strength updated: {from_id}->{to_id} = {new_strength}")

    def strongest_causes(self, outcome_id: str, top_n: int = 3) -> list[dict]:
        """Return the top N strongest causes of an outcome."""
        causes = self.get_causes(outcome_id)
        return sorted(causes, key=lambda x: x["strength"], reverse=True)[:top_n]


if __name__ == "__main__":
    cg = CausalGraph()
    cg.add_node("code_commit", "action", "Commit code to repository")
    cg.add_node("bug_detected", "outcome", "Bug detected in production")
    cg.add_edge("code_commit", "bug_detected", 0.7, "caused")
    print(cg.get_outcomes("code_commit"))
    print(cg.strongest_causes("bug_detected"))