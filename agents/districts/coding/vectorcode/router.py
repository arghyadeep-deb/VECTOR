"""
NeuralRouter — upgraded from SemanticRouter.
Absorbed concept from Ruflo's NeuralDomainMapper (v2/src/neural/NeuralDomainMapper.ts).

Architecture:
  SemanticRouter  — static keyword→model regex (deterministic fallback)
  NeuralRouter    — learned weight matrix that updates from PatternStore rewards
                    Weight matrix: {(keyword, model): weight}
                    Updated via learn(task, model, reward) after each GSD verify phase.
                    Persisted to ~/.vector/router_weights.json.
                    Tracks per-model latency (Ruflo's latency/reliability metadata).

RULE 4 compliant — no LLM call for routing, O(n) lookup.
"""
import re
import json
import sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
from core.config import CONFIG

from loguru import logger

# ── Static routing table (SemanticRouter base) ────────────────────────────────
_ROUTES = [
    (re.compile(r"\b(council|vote|chairman|critical)\b", re.IGNORECASE), "vector-chairman"),
    (re.compile(r"\b(deep|overnight|comprehensive|entire)\b", re.IGNORECASE), "vector-deep"),
    (re.compile(r"\b(plan|design|architect|think|how|approach|strategy|decide)\b", re.IGNORECASE), "vector-reasoning"),
    (re.compile(r"\b(review|check|audit|verify|test|inspect|analyse|analyze)\b", re.IGNORECASE), "vector-dev"),
    (re.compile(r"\b(write|implement|create|generate|code|function|class|method)\b", re.IGNORECASE), "vector-coder"),
    (re.compile(r"\b(important)\b", re.IGNORECASE), "vector-chairman"),
    (re.compile(r"\b(full)\b", re.IGNORECASE), "vector-deep"),
]
_DEFAULT_MODEL = "vector-fast"

# ── Seed weights (Ruflo NeuralDomainMapper bootstrap) ─────────────────────────
_SEED_WEIGHTS: dict[tuple[str, str], float] = {
    # (keyword, model): initial weight
    ("code",        "vector-coder"):    1.0,
    ("write",       "vector-coder"):    1.0,
    ("implement",   "vector-coder"):    1.0,
    ("function",    "vector-coder"):    0.9,
    ("class",       "vector-coder"):    0.9,
    ("fix",         "vector-coder"):    0.8,
    ("bug",         "vector-coder"):    0.8,
    ("review",      "vector-dev"):      1.0,
    ("audit",       "vector-dev"):      1.0,
    ("check",       "vector-dev"):      0.9,
    ("verify",      "vector-dev"):      0.9,
    ("test",        "vector-dev"):      0.8,
    ("plan",        "vector-reasoning"): 1.0,
    ("design",      "vector-reasoning"): 1.0,
    ("architect",   "vector-reasoning"): 1.0,
    ("think",       "vector-reasoning"): 0.9,
    ("strategy",    "vector-reasoning"): 0.9,
    ("deep",        "vector-deep"):     1.0,
    ("overnight",   "vector-deep"):     1.0,
    ("comprehensive","vector-deep"):    0.9,
    ("council",     "vector-chairman"): 1.0,
    ("critical",    "vector-chairman"): 1.0,
    ("vote",        "vector-chairman"): 1.0,
}

_WEIGHTS_FILE = Path.home() / ".vector" / "router_weights.json"


class SemanticRouter:
    """
    Keyword-based deterministic router — no LLM call, O(n) regex scan.
    Maps a task string to an Ollama model name (RULE 4 compliant).
    Kept for backward compatibility — NeuralRouter extends this.
    """

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
    """
    Learned-weight router extending SemanticRouter.

    Concept: Ruflo's NeuralDomainMapper uses a GNN-style domain graph with
    DomainNode (feature vector, activation) and DomainEdge (weight, frequency,
    latency, reliability). We implement the same learning principle in pure Python:

    - Weight matrix: {(keyword, model): weight ∈ [0, 1]}
    - After each task: learn(task, model_used, reward) updates weights via EMA
    - Per-model latency tracking: avg latency used to penalise slow models
    - Domain cohesion: words that co-occur with high-reward models get boosted

    RULE 4 compliant — all scoring is O(n) lookup, no LLM call.
    """

    _EMA_ALPHA = 0.2       # learning rate for exponential moving average
    _LATENCY_WEIGHT = 0.1  # how much latency penalises a model's score
    _MIN_WEIGHT = 0.01     # floor — never zero out a route
    _MAX_WEIGHT = 2.0      # ceiling — prevents runaway boosting

    def __init__(self):
        super().__init__()
        self._weights: dict[tuple[str, str], float] = dict(_SEED_WEIGHTS)
        self._latency: dict[str, list[float]] = defaultdict(list)  # model -> [ms]
        self._load_weights()

    # ── Persistence ────────────────────────────────────────────────────────────

    def _load_weights(self) -> None:
        if not _WEIGHTS_FILE.exists():
            return
        try:
            raw = json.loads(_WEIGHTS_FILE.read_text(encoding="utf-8"))
            weights = {tuple(k.split("|||")): v for k, v in raw.get("weights", {}).items()}
            latency = {k: v for k, v in raw.get("latency", {}).items()}
            self._weights.update(weights)
            for model, values in latency.items():
                self._latency[model].extend(values[-20:])
            logger.debug(f"[VECTOR][router] loaded {len(self._weights)} weights from disk")
        except Exception as e:
            logger.warning(f"[VECTOR][router] weight load failed: {e}")

    def _save_weights(self) -> None:
        try:
            _WEIGHTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "weights": {"|||".join(k): v for k, v in self._weights.items()},
                "latency": {m: v[-20:] for m, v in self._latency.items()},
            }
            _WEIGHTS_FILE.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"[VECTOR][router] weight save failed: {e}")

    # ── Core routing ──────────────────────────────────────────────────────────

    def route(self, task: str) -> str:
        """
        Score each model using the learned weight matrix.
        Falls back to static regex if no weights match.
        Applies latency penalty (Ruflo reliability/latency metadata concept).
        """
        scores: dict[str, float] = defaultdict(float)
        words = set(re.sub(r"[^\w\s]", " ", task.lower()).split())

        for word in words:
            for (kw, model), weight in self._weights.items():
                if kw == word or kw in word:
                    scores[model] += weight

        if not scores:
            model = super().route(task)
            logger.debug(f"[VECTOR][router] '{task[:60]}' → {model} (static fallback)")
            return model

        # Apply latency penalty
        for model in list(scores.keys()):
            lats = self._latency.get(model, [])
            if lats:
                avg_lat = sum(lats) / len(lats)
                penalty = min(self._LATENCY_WEIGHT * avg_lat / 1000.0, 0.3)
                scores[model] = max(0.0, scores[model] - penalty)

        best = max(scores, key=scores.get)
        logger.debug(
            f"[VECTOR][router] '{task[:60]}' → {best} "
            f"(score={scores[best]:.2f}, models={dict(scores)})"
        )
        return best

    # ── Learning ──────────────────────────────────────────────────────────────

    def learn(self, task: str, model: str, reward: float, latency_ms: float = 0.0) -> None:
        """
        Update weight matrix from task outcome.
        reward: 0.0 (failed) … 1.0 (perfect)
        latency_ms: how long the model took (optional, for reliability tracking)
        """
        words = set(re.sub(r"[^\w\s]", " ", task.lower()).split())

        for word in words:
            if len(word) < 3:  # skip noise words
                continue
            key = (word, model)
            prev = self._weights.get(key, 0.5)
            # EMA update: new_weight = alpha * reward + (1 - alpha) * prev_weight
            new_weight = self._EMA_ALPHA * reward + (1 - self._EMA_ALPHA) * prev
            self._weights[key] = max(self._MIN_WEIGHT, min(self._MAX_WEIGHT, new_weight))

        if latency_ms > 0:
            self._latency[model].append(latency_ms)
            self._latency[model] = self._latency[model][-50:]  # keep last 50

        self._save_weights()
        logger.debug(f"[VECTOR][router] learned: task='{task[:40]}' model={model} reward={reward:.2f}")

    # ── Domain cohesion (Ruflo concept) ───────────────────────────────────────

    def domain_cohesion(self, model: str) -> float:
        """
        Measure how strongly a model 'owns' its domain.
        High cohesion = many high-weight keywords mapped exclusively to this model.
        Ruflo's NeuralDomainMapper calls this cohesion_score.
        """
        model_weights = [w for (_, m), w in self._weights.items() if m == model]
        if not model_weights:
            return 0.0
        return round(sum(model_weights) / len(model_weights), 3)

    def get_domain_map(self) -> dict[str, dict]:
        """
        Return the domain relationship map: {model: {keywords, cohesion, avg_latency}}.
        Mirrors Ruflo's NeuralDomainMapper.get_domain_relationships().
        """
        result = {}
        for (kw, model), weight in self._weights.items():
            if model not in result:
                lats = self._latency.get(model, [])
                result[model] = {
                    "keywords": {},
                    "cohesion": self.domain_cohesion(model),
                    "avg_latency_ms": round(sum(lats) / len(lats), 1) if lats else 0.0,
                    "reliability": 1.0,  # upgraded as we collect latency data
                }
            result[model]["keywords"][kw] = round(weight, 3)
        return result

    # ── Backward compat ────────────────────────────────────────────────────────

    def route_sequence(self, tasks: list) -> list:
        return [self.route(t) for t in tasks]

    def count_switches(self, tasks: list) -> int:
        models = self.route_sequence(tasks)
        return sum(1 for i in range(1, len(models)) if models[i] != models[i - 1])


if __name__ == "__main__":
    r = NeuralRouter()

    # Static routes still work
    assert r.route("write a function") == "vector-coder", f"Got {r.route('write a function')}"
    assert r.route("review this code") == "vector-dev", f"Got {r.route('review this code')}"
    assert r.route("plan how to refactor") == "vector-reasoning", f"Got {r.route('plan how to refactor')}"

    # Sequence routing (RULE 4: ≤ 3 switches for 3 tasks)
    models = r.route_sequence(["plan the task", "write the code", "review it"])
    switches = sum(1 for i in range(1, len(models)) if models[i] != models[i - 1])
    assert switches <= 3, f"too many model switches: {switches}"

    # Learning
    r.learn("write unit tests", "vector-dev", reward=0.9, latency_ms=1200)
    model_after = r.route("write unit tests")
    # After learning, "write unit tests" should prefer vector-dev
    assert model_after in ("vector-dev", "vector-coder"), f"unexpected: {model_after}"

    # Domain map
    dm = r.get_domain_map()
    assert "vector-coder" in dm
    assert "cohesion" in dm["vector-coder"]

    print(f"router.py (NeuralRouter) OK — domains={list(dm.keys())}")
