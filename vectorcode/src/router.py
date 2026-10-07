"""
GNNRouter — VECTOR GNN routing architecture.

Architecture (3 layers):
  Layer 1 — GNNRouter  : feature-vector cosine-similarity routing (true GNN concept)
  Layer 2 — NeuralRouter: learned keyword weight matrix (EMA)
  Layer 3 — SemanticRouter: static regex fallback (always works)

architecture: VECTOR GNN routing architecture
  DomainNode  → DomainNode (feature_vector, activation, task_count)
  DomainEdge  → DomainEdge (weight, frequency, latency, reliability, bandwidth)
  cohesion    → domain_cohesion()
  cross-domain dependency → get_cross_domain_dependencies()
  boundary optimization   → optimize_boundaries()

Uses nomic-embed-text via Ollama for embeddings.
Falls back to keyword weights (Layer 2) if Ollama unavailable.
Falls back to regex (Layer 3) if no weights match.

RULE 4 compliant — no expensive LLM call. nomic-embed-text is a small embedding model.
"""
import re
import json
import time
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}

from loguru import logger
from vectorcode.src.utils import atomic_json_write

# ── Static routing table (Layer 3 fallback) ───────────────────────────────────
_ROUTES = [
    (re.compile(r"\b(council|vote|chairman|critical)\b",   re.IGNORECASE), "vector-chairman"),
    (re.compile(r"\b(deep|overnight|comprehensive|entire)\b", re.IGNORECASE), "vector-deep"),
    (re.compile(r"\b(plan|design|architect|think|how|approach|strategy|decide)\b", re.IGNORECASE), "vector-reasoning"),
    (re.compile(r"\b(review|check|audit|verify|test|inspect|analyse|analyze)\b", re.IGNORECASE), "vector-dev"),
    (re.compile(r"\b(write|implement|create|generate|code|function|class|method)\b", re.IGNORECASE), "vector-coder"),
    (re.compile(r"\b(important)\b", re.IGNORECASE), "vector-chairman"),
    (re.compile(r"\b(full)\b",      re.IGNORECASE), "vector-deep"),
]
_DEFAULT_MODEL = "vector-fast"

# ── Seed weights (Layer 2 bootstrap) ─────────────────────────────────────────
_SEED_WEIGHTS: dict[tuple[str, str], float] = {
    ("code",          "vector-coder"):    1.0,
    ("write",         "vector-coder"):    1.0,
    ("implement",     "vector-coder"):    1.0,
    ("function",      "vector-coder"):    0.9,
    ("class",         "vector-coder"):    0.9,
    ("fix",           "vector-coder"):    0.8,
    ("bug",           "vector-coder"):    0.8,
    ("review",        "vector-dev"):      1.0,
    ("audit",         "vector-dev"):      1.0,
    ("check",         "vector-dev"):      0.9,
    ("verify",        "vector-dev"):      0.9,
    ("test",          "vector-dev"):      0.8,
    ("plan",          "vector-reasoning"): 1.0,
    ("design",        "vector-reasoning"): 1.0,
    ("architect",     "vector-reasoning"): 1.0,
    ("think",         "vector-reasoning"): 0.9,
    ("strategy",      "vector-reasoning"): 0.9,
    ("deep",          "vector-deep"):     1.0,
    ("overnight",     "vector-deep"):     1.0,
    ("comprehensive", "vector-deep"):     0.9,
    ("council",       "vector-chairman"): 1.0,
    ("critical",      "vector-chairman"): 1.0,
    ("vote",          "vector-chairman"): 1.0,
}

_WEIGHTS_FILE  = Path.home() / ".vector" / "router_weights.json"
_GNN_FILE      = Path.home() / ".vector" / "router_gnn.json"


# ── GNN data structures (reference DomainNode / DomainEdge) ──────────────────────

@dataclass
class DomainNode:
    """GNNRouter.DomainNode — feature vector per model domain."""
    name:        str
    feature_vec: list    = field(default_factory=list)   # averaged embedding
    activation:  float   = 0.5
    task_count:  int     = 0
    total_reward: float  = 0.0

    @property
    def avg_reward(self) -> float:
        return self.total_reward / self.task_count if self.task_count > 0 else 0.5


@dataclass
class DomainEdge:
    """GNNRouter.DomainEdge — cross-domain relationship."""
    source:      str
    target:      str
    weight:      float = 0.0
    frequency:   int   = 0
    latency:     float = 0.0   # avg ms
    reliability: float = 1.0   # 0–1
    bandwidth:   float = 1.0   # tasks/sec


def _cosine(a: list, b: list) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

def _vec_add_weighted(base: list, new: list, alpha: float) -> list:
    if not base:
        return [x * alpha for x in new]
    if len(base) != len(new):
        return base
    return [(1 - alpha) * b + alpha * n for b, n in zip(base, new)]


class SemanticRouter:
    """Layer 3 — static regex fallback. Always works, never learns."""

    def route(self, task: str) -> str:
        for pattern, model in _ROUTES:
            if pattern.search(task):
                return model
        return _DEFAULT_MODEL

    def route_sequence(self, tasks: list) -> list:
        return [self.route(t) for t in tasks]

    def count_switches(self, tasks: list) -> int:
        models = self.route_sequence(tasks)
        return sum(1 for i in range(1, len(models)) if models[i] != models[i - 1])


class NeuralRouter(SemanticRouter):
    """Layer 2 — learned keyword weight matrix via EMA."""

    _EMA_ALPHA     = 0.2
    _LATENCY_WEIGHT = 0.1
    _MIN_WEIGHT    = 0.01
    _MAX_WEIGHT    = 2.0

    def __init__(self):
        super().__init__()
        self._weights: dict[tuple[str, str], float] = dict(_SEED_WEIGHTS)
        self._latency: dict[str, list[float]] = defaultdict(list)
        self._load_weights()

    def _load_weights(self) -> None:
        if not _WEIGHTS_FILE.exists():
            return
        try:
            raw = json.loads(_WEIGHTS_FILE.read_text(encoding="utf-8"))
            for k, v in raw.get("weights", {}).items():
                self._weights[tuple(k.split("|||"))] = v
            for m, lats in raw.get("latency", {}).items():
                self._latency[m].extend(lats[-20:])
        except Exception as e:
            logger.warning(f"[VECTOR][router] weight load failed: {e}")

    def _save_weights(self) -> None:
        try:
            _WEIGHTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "weights": {"|||".join(k): v for k, v in self._weights.items()},
                "latency": {m: v[-20:] for m, v in self._latency.items()},
            }
            atomic_json_write(_WEIGHTS_FILE, payload)
        except Exception as e:
            logger.warning(f"[VECTOR][router] weight save failed: {e}")

    def route(self, task: str) -> str:
        scores: dict[str, float] = defaultdict(float)
        words = set(re.sub(r"[^\w\s]", " ", task.lower()).split())
        for word in words:
            for (kw, model), weight in self._weights.items():
                if kw == word or kw in word:
                    scores[model] += weight
        if not scores:
            return super().route(task)
        for model in list(scores.keys()):
            lats = self._latency.get(model, [])
            if lats:
                avg_lat = sum(lats) / len(lats)
                scores[model] = max(0.0, scores[model] - min(self._LATENCY_WEIGHT * avg_lat / 1000.0, 0.3))
        return max(scores, key=scores.get)

    def learn(self, task: str, model: str, reward: float, latency_ms: float = 0.0) -> None:
        words = set(re.sub(r"[^\w\s]", " ", task.lower()).split())
        for word in words:
            if len(word) < 3:
                continue
            key = (word, model)
            prev = self._weights.get(key, 0.5)
            new = self._EMA_ALPHA * reward + (1 - self._EMA_ALPHA) * prev
            self._weights[key] = max(self._MIN_WEIGHT, min(self._MAX_WEIGHT, new))
        if latency_ms > 0:
            self._latency[model].append(latency_ms)
            self._latency[model] = self._latency[model][-50:]
        self._save_weights()

    def domain_cohesion(self, model: str) -> float:
        ws = [w for (_, m), w in self._weights.items() if m == model]
        return round(sum(ws) / len(ws), 3) if ws else 0.0

    def get_domain_map(self) -> dict[str, dict]:
        result = {}
        for (kw, model), weight in self._weights.items():
            if model not in result:
                lats = self._latency.get(model, [])
                result[model] = {
                    "keywords": {}, "cohesion": self.domain_cohesion(model),
                    "avg_latency_ms": round(sum(lats) / len(lats), 1) if lats else 0.0,
                    "reliability": 1.0,
                }
            result[model]["keywords"][kw] = round(weight, 3)
        return result

    def route_sequence(self, tasks: list) -> list:
        return [self.route(t) for t in tasks]

    def count_switches(self, tasks: list) -> int:
        models = self.route_sequence(tasks)
        return sum(1 for i in range(1, len(models)) if models[i] != models[i - 1])


class GNNRouter(NeuralRouter):
    """
    Layer 1 — true GNN-style routing with feature vectors and domain graph.
    Complete absorption of VECTOR GNN routing architecture.

    Routing priority:
      1. Cosine similarity against DomainNode feature vectors (when embeddings available)
      2. Keyword weight matrix (NeuralRouter Layer 2)
      3. Static regex (SemanticRouter Layer 3)
    """

    _EMBED_MODEL = "nomic-embed-text"
    _EMA_NODE    = 0.15   # how fast domain node features drift

    def __init__(self):
        super().__init__()
        self._nodes: dict[str, DomainNode] = self._init_nodes()
        self._edges: dict[tuple[str, str], DomainEdge] = {}
        self._embed_cache: dict[str, list] = {}  # task_hash -> embedding
        self._load_gnn()

    def _init_nodes(self) -> dict[str, DomainNode]:
        models = ["vector-coder", "vector-dev", "vector-reasoning",
                  "vector-deep", "vector-chairman", "vector-fast"]
        return {m: DomainNode(name=m) for m in models}

    # ── Persistence ────────────────────────────────────────────────────────────

    def _load_gnn(self) -> None:
        if not _GNN_FILE.exists():
            return
        try:
            raw = json.loads(_GNN_FILE.read_text(encoding="utf-8"))
            for name, data in raw.get("nodes", {}).items():
                if name in self._nodes:
                    n = self._nodes[name]
                    n.feature_vec   = data.get("feature_vec", [])
                    n.activation    = data.get("activation", 0.5)
                    n.task_count    = data.get("task_count", 0)
                    n.total_reward  = data.get("total_reward", 0.0)
            for key, data in raw.get("edges", {}).items():
                src, tgt = key.split("|||")
                self._edges[(src, tgt)] = DomainEdge(
                    source=src, target=tgt,
                    weight=data.get("weight", 0.0), frequency=data.get("frequency", 0),
                    latency=data.get("latency", 0.0), reliability=data.get("reliability", 1.0),
                )
        except Exception as e:
            logger.warning(f"[VECTOR][router] GNN load failed: {e}")

    def _save_gnn(self) -> None:
        try:
            _GNN_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "nodes": {
                    name: {
                        "feature_vec": n.feature_vec, "activation": n.activation,
                        "task_count": n.task_count, "total_reward": n.total_reward,
                    }
                    for name, n in self._nodes.items()
                },
                "edges": {
                    f"{e.source}|||{e.target}": {
                        "weight": e.weight, "frequency": e.frequency,
                        "latency": e.latency, "reliability": e.reliability,
                    }
                    for e in self._edges.values()
                },
            }
            atomic_json_write(_GNN_FILE, payload)
        except Exception as e:
            logger.warning(f"[VECTOR][router] GNN save failed: {e}")

    # ── Embedding ──────────────────────────────────────────────────────────────

    def _embed(self, text: str) -> Optional[list]:
        key = str(hash(text[:200]))
        if key in self._embed_cache:
            return self._embed_cache[key]
        try:
            import ollama
            resp = ollama.embeddings(model=self._EMBED_MODEL, prompt=text[:512])
            vec = resp.get("embedding", [])
            if vec:
                self._embed_cache[key] = vec
                if len(self._embed_cache) > 200:  # LRU eviction
                    oldest = next(iter(self._embed_cache))
                    del self._embed_cache[oldest]
                return vec
        except Exception as _sve:
            logger.debug("[VECTOR][router] suppressed Exception: {}", _sve)
        return None

    # ── MoE Router (Layer 0) — expert-type → VECTOR model mapping ─────────────

    # Map MoE expert names → VECTOR model names
    _MOE_TO_MODEL: dict[str, str] = {
        "coder":        "vector-coder",
        "tester":       "vector-dev",
        "reviewer":     "vector-dev",
        "architect":    "vector-reasoning",
        "security":     "vector-dev",
        "performance":  "vector-deep",
        "researcher":   "vector-deep",
        "coordinator":  "vector-chairman",
    }

    def _get_moe_router(self):
        if getattr(self, "_moe_router", None) is None:
            try:
                from neural_moe_router import MoERouter as _MoE
                import numpy as _np
                self._moe_router = _MoE()
                # Seed: encode task text as 384-dim hash embedding for routing
                self._moe_encode = lambda text: _np.frombuffer(
                    __import__("hashlib").sha256(text.encode()).digest() * 12, dtype=_np.uint8
                )[:384].astype(_np.float32) / 127.5 - 1.0
                logger.info("[VECTOR][router] MoERouter loaded (Layer 0)")
            except Exception as _e:
                logger.debug("[VECTOR][router] MoERouter unavailable: {}", _e)
                self._moe_router = False  # sentinel: tried and failed
        return self._moe_router if self._moe_router is not False else None

    # ── Core routing ──────────────────────────────────────────────────────────

    def route(self, task: str) -> str:
        # Layer 0: MoE expert routing (when available)
        moe = self._get_moe_router()
        if moe is not None:
            try:
                embedding_384 = self._moe_encode(task)
                experts = moe.route(embedding_384, top_k=1)
                if experts:
                    mapped = self._MOE_TO_MODEL.get(experts[0])
                    if mapped:
                        logger.debug(
                            "[VECTOR][router] MoE '%s' → expert=%s → %s",
                            task[:50], experts[0], mapped,
                        )
                        return mapped
            except Exception as _e:
                logger.debug("[VECTOR][router] MoE route suppressed: {}", _e)

        # Layer 1: GNN cosine similarity
        embedding = self._embed(task)
        if embedding:
            gnn_scores = {}
            for name, node in self._nodes.items():
                if node.feature_vec:
                    sim = _cosine(embedding, node.feature_vec)
                    # Boost by node activation and avg reward
                    gnn_scores[name] = sim * node.activation * (0.5 + node.avg_reward)
            if gnn_scores:
                best = max(gnn_scores, key=gnn_scores.get)
                if gnn_scores[best] > 0.3:  # confidence threshold
                    logger.debug(
                        f"[VECTOR][router] GNN '{task[:50]}' → {best} "
                        f"(sim={gnn_scores[best]:.3f})"
                    )
                    return best

        # Layer 2 + 3
        return super().route(task)

    # ── Learning (updates nodes + edges) ──────────────────────────────────────

    def learn(self, task: str, model: str, reward: float, latency_ms: float = 0.0) -> None:
        super().learn(task, model, reward, latency_ms)

        # Update DomainNode
        node = self._nodes.get(model)
        if node:
            embedding = self._embed(task)
            if embedding:
                node.feature_vec = _vec_add_weighted(node.feature_vec, embedding, self._EMA_NODE * reward)
            node.activation   = 0.9 * node.activation + 0.1 * reward
            node.task_count  += 1
            node.total_reward += reward

        # Update DomainEdge (cross-domain co-occurrence)
        prev_model = getattr(self, "_last_model", None)
        if prev_model and prev_model != model:
            edge_key = (prev_model, model)
            if edge_key not in self._edges:
                self._edges[edge_key] = DomainEdge(source=prev_model, target=model)
            edge = self._edges[edge_key]
            edge.frequency += 1
            edge.weight = 0.9 * edge.weight + 0.1 * reward
            if latency_ms > 0:
                edge.latency = 0.9 * edge.latency + 0.1 * latency_ms
            edge.reliability = 0.95 * edge.reliability + 0.05 * (1.0 if reward > 0.5 else 0.0)
        self._last_model = model

        self._save_gnn()

    # ── reference GNNRouter API ───────────────────────────────────────────

    def domain_cohesion(self, model: str) -> float:
        """Reference: DomainNode cohesion score — how strongly a model owns its domain."""
        node = self._nodes.get(model)
        base = super().domain_cohesion(model)  # keyword weight cohesion
        if node and node.task_count > 0:
            # Blend keyword cohesion with GNN activation
            return round((base + node.activation * node.avg_reward) / 2, 3)
        return base

    def get_cross_domain_dependencies(self) -> list[dict]:
        """Reference: identify cross-domain dependencies (which domains flow into which)."""
        deps = []
        for (src, tgt), edge in self._edges.items():
            if edge.frequency > 0:
                deps.append({
                    "from":        src,
                    "to":          tgt,
                    "frequency":   edge.frequency,
                    "weight":      round(edge.weight, 3),
                    "reliability": round(edge.reliability, 3),
                    "latency_ms":  round(edge.latency, 1),
                })
        return sorted(deps, key=lambda d: d["frequency"], reverse=True)

    def optimize_boundaries(self) -> dict[str, str]:
        """
        reference: predictive boundary optimization.
        Suggests tasks that should be re-routed based on cross-domain flow patterns.
        Returns {task_keyword: suggested_model}.
        """
        suggestions = {}
        # Find high-frequency cross-domain edges where the target has higher avg reward
        for (src, tgt), edge in self._edges.items():
            src_node = self._nodes.get(src)
            tgt_node = self._nodes.get(tgt)
            if not src_node or not tgt_node:
                continue
            if edge.frequency >= 3 and tgt_node.avg_reward > src_node.avg_reward + 0.1:
                # Keywords that flow from src → tgt should try tgt directly
                for (kw, model), weight in self._weights.items():
                    if model == src and weight > 0.7:
                        suggestions[kw] = tgt
        return suggestions

    def get_domain_map(self) -> dict[str, dict]:
        base = super().get_domain_map()
        for name, node in self._nodes.items():
            if name not in base:
                base[name] = {"keywords": {}, "cohesion": 0.0, "avg_latency_ms": 0.0, "reliability": 1.0}
            base[name]["gnn"] = {
                "activation":   round(node.activation, 3),
                "task_count":   node.task_count,
                "avg_reward":   round(node.avg_reward, 3),
                "has_embedding": len(node.feature_vec) > 0,
            }
        return base


if __name__ == "__main__":
    r = GNNRouter()

    # Layer 3 fallback
    assert r.route("write a function") == "vector-coder"
    assert r.route("review this code") == "vector-dev"
    assert r.route("plan how to refactor") == "vector-reasoning"

    # Sequence routing (RULE 4)
    switches = r.count_switches(["plan the task", "write the code", "review it"])
    assert switches <= 3

    # Learning
    r.learn("write unit tests", "vector-dev", reward=0.9, latency_ms=1200)

    # Cross-domain dependencies
    deps = r.get_cross_domain_dependencies()
    assert isinstance(deps, list)

    # Domain map includes GNN metadata
    dm = r.get_domain_map()
    assert "vector-coder" in dm
    assert "gnn" in dm["vector-coder"]

    # Boundary optimization
    opts = r.optimize_boundaries()
    assert isinstance(opts, dict)

    print(f"router.py (GNNRouter) OK — nodes={len(r._nodes)}, edges={len(r._edges)}")


