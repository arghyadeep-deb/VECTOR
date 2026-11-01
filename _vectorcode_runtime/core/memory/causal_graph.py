"""
V.E.C.T.O.R. CausalGraph.
Gap 6: Tracks cause-effect relationships between actions and outcomes.
Persisted to the shared episodic SQLite DB (causal_nodes + causal_edges tables).
BFS path-finding. Influence scoring.
"""
import json
import sqlite3
import threading
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from loguru import logger


def causal_state_key(context_snapshot: Optional[dict]) -> str:
    """R24 — the single, shared antecedent-state key both the real
    production causal-edge WRITER (autonomous_loop.py's post-outcome
    Gap-6 block) and the real production causal-edge READER
    (decision_engine.py's `_causal_factor()`) must use, so a causal edge
    genuinely means "under state S, action A produced outcome B" rather
    than an unscoped "A produced B in general" correlation-log entry.

    Deliberately reuses `context_snapshot["presence"]` -- the SAME real,
    already-proven-real field R22's `_situational_factor()` already
    consumes (sourced from the real FaceDetector via ContextEngine's
    sense cache) -- not a new sensor, not a new state dimension. Any
    malformed/missing snapshot fails safe to the honest "unknown" state
    rather than crashing or guessing.
    """
    if not isinstance(context_snapshot, dict):
        return "unknown"
    presence = context_snapshot.get("presence")
    if presence not in ("present", "absent", "unknown"):
        return "unknown"
    return presence


class CausalGraph:
    """
    Directed causal graph: action → outcome → consequence.
    Enables VECTOR to reason about what causes what.
    Persisted to causal_nodes / causal_edges tables in the shared episodic SQLite DB.
    """

    def __init__(self, json_path: Optional[str] = None):
        # A supplied json_path represents an isolated graph namespace. Production
        # callers without a path continue to use the shared episodic SQLite DB.
        self._json_path = str(json_path) if json_path else None
        self._local_conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()
        self._nodes: dict[str, dict] = {}
        self._edges: list[dict] = []
        self._adj: dict[str, list[str]] = defaultdict(list)
        self._radj: dict[str, list[str]] = defaultdict(list)
        self._init_db()
        self._load()
        # One-time migration: import existing JSON if present
        if json_path and Path(json_path).exists():
            self._migrate_from_json(json_path)
        logger.info("[VECTOR][causal_graph] CausalGraph initialized (SQLite)")

    # ── DB setup ────────────────────────────────────────────────────────────

    def _conn(self):
        if self._json_path:
            with self._lock:
                if self._local_conn is None:
                    namespace = quote(str(Path(self._json_path).resolve()), safe="")
                    self._local_conn = sqlite3.connect(
                        f"file:vector_causal_graph_{namespace}?mode=memory&cache=shared",
                        uri=True,
                        check_same_thread=False,
                    )
                    self._local_conn.execute("PRAGMA busy_timeout=5000")
            return self._local_conn
        from core.memory.episodic import get_db_connection
        return get_db_connection()

    def _shared_write_lock(self):
        """episodic._write_lock is the only thing that serializes concurrent
        threads against the shared singleton SQLite connection (see
        episodic.get_temp_cursor()'s docstring) — every conn.execute() below
        against the shared DB (self._json_path is None) used to bypass it
        entirely, same class of bug as core.memory.policy's lost-update race.
        self._lock alone only serializes within one CausalGraph instance, not
        across other threads/instances/modules sharing the singleton
        connection. No-op for the isolated json_path (private in-memory,
        per-instance) mode, where there is no shared connection to race."""
        if self._json_path:
            from contextlib import nullcontext
            return nullcontext()
        from core.memory.episodic import get_db_write_lock
        return get_db_write_lock()

    def _init_db(self):
        try:
            with self._lock, self._shared_write_lock():
                conn = self._conn()
                with conn:
                    conn.execute("""
                    CREATE TABLE IF NOT EXISTS causal_nodes (
                        id       TEXT PRIMARY KEY,
                        type     TEXT NOT NULL,
                        label    TEXT NOT NULL,
                        metadata TEXT DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        weight   REAL DEFAULT 0.0
                    )
                """)
                    conn.execute("""
                    CREATE TABLE IF NOT EXISTS causal_edges (
                        from_id    TEXT NOT NULL,
                        to_id      TEXT NOT NULL,
                        strength   REAL DEFAULT 1.0,
                        label      TEXT DEFAULT '',
                        created_at TEXT NOT NULL,
                        hit_count  INTEGER DEFAULT 1,
                        PRIMARY KEY (from_id, to_id)
                    )
                """)
                    # R24: additive migration for any pre-existing causal_edges
                    # table created before hit_count existed (this repo's own
                    # convention: "adding columns is OK, never rename/drop").
                    # Pre-existing rows get the honest floor of 1 observation
                    # (their real, single prior strength write), never a
                    # fabricated higher count.
                    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(causal_edges)").fetchall()}
                    if "hit_count" not in existing_cols:
                        conn.execute("ALTER TABLE causal_edges ADD COLUMN hit_count INTEGER DEFAULT 1")
        except Exception as e:
            logger.warning("[VECTOR][causal_graph] DB init failed: {}", e)

    def _load(self):
        try:
            with self._lock, self._shared_write_lock():
                conn = self._conn()
                cursor = conn.execute("SELECT id, type, label, metadata, created_at, weight FROM causal_nodes")
                for row in cursor.fetchall():
                    node_id, ntype, label, metadata_json, created_at, weight = row
                    self._nodes[node_id] = {
                        "id": node_id, "type": ntype, "label": label,
                        "metadata": json.loads(metadata_json or "{}"),
                        "created_at": created_at, "weight": weight,
                    }
                cursor = conn.execute("SELECT from_id, to_id, strength, label, created_at, hit_count FROM causal_edges")
                for row in cursor.fetchall():
                    from_id, to_id, strength, label, created_at, hit_count = row
                    self._edges.append({
                        "from": from_id, "to": to_id,
                        "strength": strength, "label": label, "created_at": created_at,
                        "hit_count": hit_count if hit_count is not None else 1,
                    })
                self._rebuild_adj()
            logger.info("[VECTOR][causal_graph] Loaded {} nodes, {} edges",
                        len(self._nodes), len(self._edges))
        except Exception as e:
            logger.warning("[VECTOR][causal_graph] Load failed: {}", e)

    def _migrate_from_json(self, json_path: str):
        """One-time import of legacy JSON file into SQLite."""
        try:
            p = Path(json_path)
            if not p.exists() or p.stat().st_size == 0:
                return
            data = json.loads(p.read_text(encoding="utf-8"))
            imported = 0
            for node_id, node in data.get("nodes", {}).items():
                if node_id not in self._nodes:
                    self._upsert_node_db(node)
                    self._nodes[node_id] = node
                    imported += 1
            for edge in data.get("edges", []):
                key = (edge["from"], edge["to"])
                if not any(e["from"] == edge["from"] and e["to"] == edge["to"] for e in self._edges):
                    edge.setdefault("hit_count", 1)  # honest floor: 1 real prior legacy observation
                    self._insert_edge_db(edge)
                    self._edges.append(edge)
            self._rebuild_adj()
            p.rename(json_path + ".migrated")
            logger.info("[VECTOR][causal_graph] Migrated {} nodes from JSON → SQLite", imported)
        except Exception as e:
            logger.warning("[VECTOR][causal_graph] JSON migration failed: {}", e)

    def _upsert_node_db(self, node: dict):
        try:
            with self._lock, self._shared_write_lock():
                conn = self._conn()
                with conn:
                    conn.execute(
                    "INSERT OR REPLACE INTO causal_nodes (id, type, label, metadata, created_at, weight) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (node["id"], node["type"], node["label"],
                     json.dumps(node.get("metadata", {})),
                     node["created_at"], node.get("weight", 0.0)),
                )
        except Exception as e:
            logger.warning("[VECTOR][causal_graph] Node DB write failed: {}", e)

    def _delete_node_db(self, node_id: str):
        try:
            with self._lock, self._shared_write_lock():
                conn = self._conn()
                with conn:
                    conn.execute("DELETE FROM causal_nodes WHERE id = ?", (node_id,))
                    conn.execute("DELETE FROM causal_edges WHERE from_id = ? OR to_id = ?", (node_id, node_id))
        except Exception as e:
            logger.warning("[VECTOR][causal_graph] Node DB delete failed: {}", e)

    def _insert_edge_db(self, edge: dict):
        try:
            with self._lock, self._shared_write_lock():
                conn = self._conn()
                with conn:
                    conn.execute(
                    "INSERT OR REPLACE INTO causal_edges (from_id, to_id, strength, label, created_at, hit_count) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (edge["from"], edge["to"], edge["strength"],
                     edge.get("label", ""), edge["created_at"], edge.get("hit_count", 1)),
                )
        except Exception as e:
            logger.warning("[VECTOR][causal_graph] Edge DB write failed: {}", e)

    def _update_edge_strength_db(self, from_id: str, to_id: str, strength: float):
        try:
            with self._lock, self._shared_write_lock():
                conn = self._conn()
                with conn:
                    conn.execute(
                    "UPDATE causal_edges SET strength = ? WHERE from_id = ? AND to_id = ?",
                    (strength, from_id, to_id),
                )
        except Exception as e:
            logger.warning("[VECTOR][causal_graph] Edge strength DB update failed: {}", e)

    def _rebuild_adj(self):
        self._adj = defaultdict(list)
        self._radj = defaultdict(list)
        for edge in self._edges:
            self._adj[edge["from"]].append(edge["to"])
            self._radj[edge["to"]].append(edge["from"])

    # ── Node API ────────────────────────────────────────────────────────────

    def add_node(self, node_id: str, node_type: str, label: str,
                 metadata: Optional[dict] = None) -> dict:
        node = {
            "id": node_id, "type": node_type, "label": label,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "weight": 0.0,
        }
        with self._lock:
            self._nodes[node_id] = node
            self._upsert_node_db(node)
        logger.info("[VECTOR][causal_graph] Node added: {} ({})", node_id, node_type)
        return node

    def remove_node(self, node_id: str) -> bool:
        with self._lock:
            if node_id not in self._nodes:
                return False
            del self._nodes[node_id]
            self._edges = [e for e in self._edges if e["from"] != node_id and e["to"] != node_id]
            self._rebuild_adj()
            self._delete_node_db(node_id)
        logger.info("[VECTOR][causal_graph] Node removed: {}", node_id)
        return True

    def get_node(self, node_id: str) -> Optional[dict]:
        return self._nodes.get(node_id)

    def get_all_nodes(self) -> list[dict]:
        return list(self._nodes.values())

    # ── Edge API ────────────────────────────────────────────────────────────

    def add_edge(self, from_id: str, to_id: str,
                 strength: float = 1.0, label: str = "") -> dict:
        """R24: a repeat observation of the SAME (from_id, to_id) edge now
        ACCUMULATES (real running average + real observation count) rather
        than overwriting the prior strength with only the latest one. This
        is what makes `strength` an honest, growing-confidence signal
        derived from real repeated experience instead of "whatever the
        most recent single reward happened to be" -- the exact gap this
        session's Phase A investigators (independently, including a fresh
        adversarial reviewer) identified as the reason this graph could
        not previously support any genuine confidence claim. See
        `_causal_factor()` in decision_engine.py for the real consumer
        that relies on `hit_count` to gate against fabricated confidence."""
        if from_id not in self._nodes or to_id not in self._nodes:
            return {"status": "error", "detail": "Node not found"}
        strength = max(0.0, min(1.0, strength))
        with self._lock:
            existing = next((e for e in self._edges if e["from"] == from_id and e["to"] == to_id), None)
            if existing is not None:
                prior_count = existing.get("hit_count", 1)
                new_count = prior_count + 1
                new_strength = (existing["strength"] * prior_count + strength) / new_count
                existing["strength"] = new_strength
                existing["hit_count"] = new_count
                existing["created_at"] = datetime.now(timezone.utc).isoformat()
                if label:
                    existing["label"] = label
                edge = existing
            else:
                edge = {
                    "from": from_id, "to": to_id,
                    "strength": strength, "label": label,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "hit_count": 1,
                }
                self._edges.append(edge)
                self._adj[from_id].append(to_id)
                self._radj[to_id].append(from_id)
            self._insert_edge_db(edge)
        logger.info("[VECTOR][causal_graph] Edge: {} → {} (strength={:.2f}, hit_count={})",
                    from_id, to_id, edge["strength"], edge["hit_count"])
        return edge

    def get_all_edges(self) -> list[dict]:
        return list(self._edges)

    def update_edge_strength(self, from_id: str, to_id: str, new_strength: float) -> bool:
        updated = False
        with self._lock:
            for edge in self._edges:
                if edge["from"] == from_id and edge["to"] == to_id:
                    edge["strength"] = max(0.0, min(1.0, new_strength))
                    updated = True
                    logger.info("[VECTOR][causal_graph] Edge strength: {}→{}={:.2f}",
                                from_id, to_id, new_strength)
            if updated:
                self._update_edge_strength_db(from_id, to_id, max(0.0, min(1.0, new_strength)))
        return updated

    # ── Traversal ───────────────────────────────────────────────────────────

    def get_outcomes(self, action_id: str) -> list[dict]:
        return [{**e, "outcome_node": self._nodes.get(e["to"], {})}
                for e in self._edges if e["from"] == action_id]

    def get_causes(self, outcome_id: str) -> list[dict]:
        return [{**e, "cause_node": self._nodes.get(e["from"], {})}
                for e in self._edges if e["to"] == outcome_id]

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
        return list(ancestors(node_a) & ancestors(node_b))

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

    # ── Serialization (kept for API compatibility) ───────────────────────────

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

    def get_stats(self) -> dict:
        return self.get_graph_summary()


if __name__ == "__main__":
    import tempfile, os
    # Test with a temporary DB path
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

    cg.remove_node("test_fail")
    assert cg.get_node("test_fail") is None
    assert all(e["from"] != "test_fail" and e["to"] != "test_fail" for e in cg.get_all_edges())

    # R24: repeat observations accumulate (running average + real hit_count),
    # never silently overwrite the prior strength with only the latest one.
    cg.add_node("a24", "action", "probe action")
    cg.add_node("b24", "outcome", "probe outcome")
    cg.add_edge("a24", "b24", 1.0)
    cg.add_edge("a24", "b24", 0.0)
    e = next(e for e in cg.get_all_edges() if e["from"] == "a24" and e["to"] == "b24")
    assert e["hit_count"] == 2, e
    assert abs(e["strength"] - 0.5) < 1e-9, e

    assert causal_state_key({"presence": "absent"}) == "absent"
    assert causal_state_key({}) == "unknown"
    assert causal_state_key(None) == "unknown"
    assert causal_state_key({"presence": "bogus"}) == "unknown"

    os.unlink(jp)
    print("OK causal_graph.py (SQLite)")
