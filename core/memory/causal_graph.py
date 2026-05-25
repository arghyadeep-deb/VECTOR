"""
V.E.C.T.O.R. CausalGraph.
Gap 6: Tracks cause-effect relationships between actions and outcomes.
Persisted to JSON. BFS path-finding. Influence scoring.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional

from loguru import logger


class CausalGraph:
    """
    Directed causal graph: action → outcome → consequence.
    Enables VECTOR to reason about what causes what.
    Persisted to data/causal_graph.json (append-on-save, load-on-init).
    """

    def __init__(self, json_path: Optional[str] = None):
        if json_path is None:
            base = Path(__file__).parent.parent.parent / "data"
            base.mkdir(parents=True, exist_ok=True)
            json_path = str(base / "causal_graph.json")
        self._json_path = json_path
        self._nodes: dict[str, dict] = {}
        self._edges: list[dict] = []
        self._adj: dict[str, list[str]] = defaultdict(list)
        self._radj: dict[str, list[str]] = defaultdict(list)  # reverse adjacency
        self._load()
        logger.info("[VECTOR][causal_graph] CausalGraph initialized")

    def _load(self):
        try:
            p = Path(self._json_path)
            if p.exists() and p.stat().st_size > 0:
                data = json.loads(p.read_text(encoding="utf-8"))
                self._nodes = data.get("nodes", {})
                self._edges = data.get("edges", [])
                self._rebuild_adj()
                logger.info(
                    f"[VECTOR][causal_graph] Loaded {len(self._nodes)} nodes, "
                    f"{len(self._edges)} edges"
                )
        except Exception as e:
            logger.warning(f"[VECTOR][causal_graph] Load failed: {e}")

    def _save(self):
        try:
            Path(self._json_path).write_text(
                json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"[VECTOR][causal_graph] Save failed: {e}")

    def _rebuild_adj(self):
        self._adj = defaultdict(list)
        self._radj = defaultdict(list)
        for edge in self._edges:
            self._adj[edge["from"]].append(edge["to"])
            self._radj[edge["to"]].append(edge["from"])

    # ── Node API ────────────────────────────────────────────────────────────

    def add_node(
        self,
        node_id: str,
        node_type: str,
        label: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        node = {
            "id": node_id,
            "type": node_type,
            "label": label,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "weight": 0.0,
        }
        self._nodes[node_id] = node
        self._save()
        logger.info(f"[VECTOR][causal_graph] Node added: {node_id} ({node_type})")
        return node

    def remove_node(self, node_id: str) -> bool:
        if node_id not in self._nodes:
            return False
        del self._nodes[node_id]
        self._edges = [e for e in self._edges if e["from"] != node_id and e["to"] != node_id]
        self._rebuild_adj()
        self._save()
        logger.info(f"[VECTOR][causal_graph] Node removed: {node_id}")
        return True

    def get_node(self, node_id: str) -> Optional[dict]:
        return self._nodes.get(node_id)

    def get_all_nodes(self) -> list[dict]:
        return list(self._nodes.values())

    # ── Edge API ────────────────────────────────────────────────────────────

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        strength: float = 1.0,
        label: str = "",
    ) -> dict:
        if from_id not in self._nodes or to_id not in self._nodes:
            return {"status": "error", "detail": "Node not found"}
        strength = max(0.0, min(1.0, strength))
        edge = {
            "from": from_id,
            "to": to_id,
            "strength": strength,
            "label": label,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._edges.append(edge)
        self._adj[from_id].append(to_id)
        self._radj[to_id].append(from_id)
        self._save()
        logger.info(f"[VECTOR][causal_graph] Edge: {from_id} → {to_id} (strength={strength:.2f})")
        return edge

    def get_all_edges(self) -> list[dict]:
        return list(self._edges)

    def update_edge_strength(self, from_id: str, to_id: str, new_strength: float) -> bool:
        updated = False
        for edge in self._edges:
            if edge["from"] == from_id and edge["to"] == to_id:
                edge["strength"] = max(0.0, min(1.0, new_strength))
                updated = True
                logger.info(f"[VECTOR][causal_graph] Edge strength: {from_id}→{to_id}={new_strength:.2f}")
        if updated:
            self._save()
        return updated

    # ── Traversal ───────────────────────────────────────────────────────────

    def get_outcomes(self, action_id: str) -> list[dict]:
        results = []
        for edge in self._edges:
            if edge["from"] == action_id:
                node = self._nodes.get(edge["to"], {})
                results.append({**edge, "outcome_node": node})
        return results

    def get_causes(self, outcome_id: str) -> list[dict]:
        results = []
        for edge in self._edges:
            if edge["to"] == outcome_id:
                node = self._nodes.get(edge["from"], {})
                results.append({**edge, "cause_node": node})
        return results

    def strongest_causes(self, outcome_id: str, top_n: int = 3) -> list[dict]:
        return sorted(self.get_causes(outcome_id), key=lambda x: x["strength"], reverse=True)[:top_n]

    def get_causal_chain(self, start_id: str, end_id: str) -> list[str]:
        """BFS path from start_id to end_id. Returns [] if no path."""
        if start_id not in self._nodes or end_id not in self._nodes:
            return []
        if start_id == end_id:
            return [start_id]
        visited = {start_id}
        queue: deque = deque([[start_id]])
        while queue:
            path = queue.popleft()
            current = path[-1]
            for neighbor in self._adj.get(current, []):
                if neighbor == end_id:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])
        return []

    def find_common_causes(self, node_a: str, node_b: str) -> list[str]:
        """Return nodes that are ancestors of both node_a and node_b."""
        def ancestors(nid: str) -> set[str]:
            seen: set[str] = set()
            q: deque = deque([nid])
            while q:
                cur = q.popleft()
                for parent in self._radj.get(cur, []):
                    if parent not in seen:
                        seen.add(parent)
                        q.append(parent)
            return seen

        anc_a = ancestors(node_a)
        anc_b = ancestors(node_b)
        return list(anc_a & anc_b)

    def get_influence_score(self, node_id: str) -> int:
        """Number of nodes reachable downstream from node_id (BFS)."""
        if node_id not in self._nodes:
            return 0
        visited: set[str] = set()
        q: deque = deque([node_id])
        while q:
            cur = q.popleft()
            for neighbor in self._adj.get(cur, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    q.append(neighbor)
        return len(visited)

    # ── Serialization ───────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "nodes": self._nodes,
            "edges": self._edges,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }

    def from_dict(self, data: dict):
        self._nodes = data.get("nodes", {})
        self._edges = data.get("edges", [])
        self._rebuild_adj()

    def get_graph_summary(self) -> dict:
        avg_strength = (
            sum(e["strength"] for e in self._edges) / len(self._edges)
            if self._edges else 0.0
        )
        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "avg_edge_strength": round(avg_strength, 3),
            "node_types": list({n["type"] for n in self._nodes.values()}),
        }


if __name__ == "__main__":
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        jp = f.name

    cg = CausalGraph(jp)
    cg.add_node("commit", "action", "Git commit")
    cg.add_node("test_fail", "outcome", "Tests fail")
    cg.add_node("deploy_blocked", "consequence", "Deploy blocked")
    cg.add_edge("commit", "test_fail", 0.7, "causes")
    cg.add_edge("test_fail", "deploy_blocked", 0.9, "blocks")

    chain = cg.get_causal_chain("commit", "deploy_blocked")
    assert chain == ["commit", "test_fail", "deploy_blocked"], chain

    score = cg.get_influence_score("commit")
    assert score == 2, score

    common = cg.find_common_causes("test_fail", "deploy_blocked")
    assert "commit" in common

    summary = cg.get_graph_summary()
    assert summary["total_nodes"] == 3
    assert summary["total_edges"] == 2

    cg2 = CausalGraph(jp)
    assert len(cg2.get_all_nodes()) == 3

    cg.remove_node("test_fail")
    assert cg.get_node("test_fail") is None
    assert all(e["from"] != "test_fail" and e["to"] != "test_fail" for e in cg.get_all_edges())

    os.unlink(jp)
    print("[OK] causal_graph.py")
