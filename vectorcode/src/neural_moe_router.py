"""VECTOR MoE Router — Mixture of Experts for dynamic agent routing."""
from __future__ import annotations
# --- Windows console UTF-8 safety (VECTOR codemod) ---
import sys as _vsys  # noqa: E402
for _vstream in (_vsys.stdout, _vsys.stderr):
    try:
        if _vstream is not None and hasattr(_vstream, "reconfigure") and (getattr(_vstream, "encoding", "") or "").lower() not in ("utf-8", "utf8"):
            _vstream.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
# ---------------------------------------------------------------------------

# VECTOR module — neural intelligence subsystem
# Owner: Arghyadeep Deb | Ingested: 2026-05-16

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from loguru import logger
from vectorcode.src.utils import atomic_json_write


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPERTS: List[str] = [
    "coder",
    "tester",
    "reviewer",
    "architect",
    "security",
    "performance",
    "researcher",
    "coordinator",
]
NUM_EXPERTS: int = 8
INPUT_DIM: int = 384
HIDDEN_DIM: int = 128

_DEFAULT_WEIGHTS_PATH = Path.home() / ".vector" / "moe-weights.json"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class MoERouterConfig:
    num_experts: int = NUM_EXPERTS
    input_dim: int = INPUT_DIM
    hidden_dim: int = HIDDEN_DIM
    top_k: int = 2                          # select top-k experts
    noise_std: float = 0.01                 # jitter noise for exploration
    lr: float = 0.01
    lr_decay: float = 0.999
    load_balance_coef: float = 0.01
    weights_path: Optional[str] = None      # persist to ~/.vector/moe-weights.json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(0.0, x)


def _softmax(x: np.ndarray) -> np.ndarray:
    """Numerically stable softmax."""
    shifted = x - np.max(x)
    exp_x = np.exp(shifted)
    return exp_x / (exp_x.sum() + 1e-9)


def _xavier_init(out_dim: int, in_dim: int, rng: np.random.Generator) -> np.ndarray:
    """Xavier uniform initialisation."""
    limit = math.sqrt(6.0 / (in_dim + out_dim))
    return rng.uniform(-limit, limit, size=(out_dim, in_dim))


def _gini(probs: np.ndarray) -> float:
    """Gini coefficient — 0 = perfectly equal load, 1 = fully concentrated."""
    sorted_p = np.sort(probs)
    n = len(sorted_p)
    cumsum = np.cumsum(sorted_p)
    return float(1.0 - 2.0 * cumsum.sum() / (n * sorted_p.sum() + 1e-9) + 1.0 / n)


def _text_to_embedding(text: str, dim: int = INPUT_DIM) -> np.ndarray:
    """Deterministic hash embedding: sha256(text) → `dim` floats in [-1, 1]."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()  # 32 bytes
    # Tile digest bytes to fill dim
    num_tiles = math.ceil(dim / len(digest))
    extended = (digest * num_tiles)[:dim]
    arr = np.frombuffer(bytes(extended), dtype=np.uint8).astype(np.float64)
    return arr / 127.5 - 1.0   # map [0,255] → [-1, 1]


# ---------------------------------------------------------------------------
# MoERouter
# ---------------------------------------------------------------------------

class MoERouter:
    """2-layer gating network: input→128→ReLU→8→softmax, top-k selection.

    Architecture (from TS):
    - W1: [HIDDEN_DIM × INPUT_DIM], b1: [HIDDEN_DIM]
    - W2: [NUM_EXPERTS × HIDDEN_DIM], b2: [NUM_EXPERTS]
    - Xavier init, SGD with momentum + load-balance auxiliary loss

    Methods:
    - route(embedding, top_k=2) -> List[str]           expert names
    - route_with_weights(embedding) -> dict             {expert: weight}
    - update(embedding, selected_experts, reward) -> None
    - get_routing_stats() -> dict                       expert load distribution
    - load(path) -> None
    - save(path) -> None

    VECTOR wiring: used by GNNRouter.route() as the backend routing mechanism.
    Text routing: embed via hash → route → return expert name as domain string.
    """

    def __init__(
        self,
        config: Optional[MoERouterConfig] = None,
        experts: Optional[List[str]] = None,
    ) -> None:
        self.config = config or MoERouterConfig()
        self.experts: List[str] = experts or EXPERTS[: self.config.num_experts]
        assert len(self.experts) == self.config.num_experts, (
            f"Expert list length {len(self.experts)} != num_experts {self.config.num_experts}"
        )

        self._step: int = 0
        self._lr: float = self.config.lr

        # Expert usage counters for load-balance stats
        self._usage: np.ndarray = np.zeros(self.config.num_experts, dtype=np.float64)

        # SGD momentum buffers
        self._vW2: np.ndarray | None = None
        self._vb2: np.ndarray | None = None

        # Last forward-pass cache (for backward)
        self._last_h: Optional[np.ndarray] = None
        self._last_probs: Optional[np.ndarray] = None
        self._last_embedding: Optional[np.ndarray] = None

        rng = np.random.default_rng(42)
        self.W1: np.ndarray = _xavier_init(
            self.config.hidden_dim, self.config.input_dim, rng
        )
        self.b1: np.ndarray = np.zeros(self.config.hidden_dim, dtype=np.float64)
        self.W2: np.ndarray = _xavier_init(
            self.config.num_experts, self.config.hidden_dim, rng
        )
        self.b2: np.ndarray = np.zeros(self.config.num_experts, dtype=np.float64)

        self._vW2 = np.zeros_like(self.W2)
        self._vb2 = np.zeros_like(self.b2)

        # Auto-load weights if path provided
        if self.config.weights_path:
            p = Path(self.config.weights_path)
            if p.exists():
                self.load(p)

        logger.debug(
            f"[VECTOR][moe_router] init: {self.config.num_experts} experts "
            f"input_dim={self.config.input_dim} hidden={self.config.hidden_dim}"
        )

    # ------------------------------------------------------------------
    # Forward pass
    # ------------------------------------------------------------------

    def _forward(self, embedding: np.ndarray) -> np.ndarray:
        """Run gating network, return expert probabilities."""
        x = embedding.astype(np.float64)
        if x.ndim != 1 or len(x) != self.config.input_dim:
            # Resize: truncate or zero-pad to input_dim
            tmp = np.zeros(self.config.input_dim, dtype=np.float64)
            n = min(len(x), self.config.input_dim)
            tmp[:n] = x[:n]
            x = tmp

        h = _relu(self.W1 @ x + self.b1)          # (hidden_dim,)
        logits = self.W2 @ h + self.b2             # (num_experts,)

        # Optional jitter noise for exploration
        if self.config.noise_std > 0:
            noise = np.random.normal(0, self.config.noise_std, size=logits.shape)
            logits = logits + noise

        probs = _softmax(logits)                   # (num_experts,)

        # Cache for backward
        self._last_h = h
        self._last_probs = probs
        self._last_embedding = x
        return probs

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(
        self,
        embedding: np.ndarray,
        top_k: Optional[int] = None,
    ) -> List[str]:
        """Select top-k expert names for a given embedding.

        Args:
            embedding: float array of shape (input_dim,) — or any length (auto-padded)
            top_k:     number of experts to select (defaults to config.top_k)

        Returns:
            List of expert name strings, ordered by descending weight.
        """
        k = top_k if top_k is not None else self.config.top_k
        k = max(1, min(k, self.config.num_experts))
        probs = self._forward(embedding)
        top_indices = np.argsort(probs)[-k:][::-1]
        selected = [self.experts[i] for i in top_indices]
        # Update usage stats
        for i in top_indices:
            self._usage[i] += 1.0
        logger.debug(f"[VECTOR][moe_router] routed top-{k}: {selected}")
        return selected

    def route_with_weights(self, embedding: np.ndarray) -> Dict[str, float]:
        """Route and return a dict of {expert_name: weight} for all experts.

        The weights are the softmax probabilities (sum to ~1.0).
        """
        probs = self._forward(embedding)
        result = {name: float(probs[i]) for i, name in enumerate(self.experts)}
        # Still update usage for top-k
        k = self.config.top_k
        top_indices = np.argsort(probs)[-k:]
        for i in top_indices:
            self._usage[i] += 1.0
        return result

    def route_text(self, text: str, top_k: Optional[int] = None) -> List[str]:
        """Convenience: embed text via hash, then route.

        Args:
            text: any string (task description, query, etc.)
            top_k: experts to select

        Returns:
            List of expert name strings.
        """
        embedding = _text_to_embedding(text, self.config.input_dim)
        return self.route(embedding, top_k)

    def update(
        self,
        embedding: np.ndarray,
        selected_experts: List[str],
        reward: float,
    ) -> None:
        """Update gating network weights via policy gradient + load-balance loss.

        Args:
            embedding:        the embedding used during routing
            selected_experts: list of expert names that were selected
            reward:           scalar reward signal [0.0, 1.0]
        """
        # Re-run forward to get fresh probs (or use cached if same embedding)
        probs = self._forward(embedding)
        h = self._last_h

        # Build selected indicator vector
        selected_mask = np.zeros(self.config.num_experts, dtype=np.float64)
        for name in selected_experts:
            if name in self.experts:
                idx = self.experts.index(name)
                selected_mask[idx] = 1.0

        # Load balance auxiliary gradient: penalise unequal usage
        # Approximate usage distribution from running counts
        usage_norm = self._usage / (self._usage.sum() + 1e-9)
        load_grad = self.config.load_balance_coef * (usage_norm - 1.0 / self.config.num_experts)

        # Policy gradient: grad proportional to reward * (selected - probs)
        policy_grad = reward * (selected_mask - probs)

        # Total gradient on logits layer (W2 output)
        delta = policy_grad - load_grad   # (num_experts,)

        # Gradient for W2 and b2
        grad_W2 = np.outer(delta, h)     # (num_experts, hidden_dim)
        grad_b2 = delta                   # (num_experts,)

        # SGD with momentum (beta=0.9)
        beta = 0.9
        self._vW2 = beta * self._vW2 + (1 - beta) * grad_W2
        self._vb2 = beta * self._vb2 + (1 - beta) * grad_b2

        # Apply update
        self.W2 += self._lr * self._vW2
        self.b2 += self._lr * self._vb2

        # Decay learning rate
        self._step += 1
        self._lr = self.config.lr * (self.config.lr_decay ** self._step)

        logger.debug(
            f"[VECTOR][moe_router] update step={self._step} "
            f"reward={reward:.3f} lr={self._lr:.6f}"
        )

        # Auto-save if weights path configured
        if self.config.weights_path:
            self.save(Path(self.config.weights_path))

    def get_routing_stats(self) -> Dict:
        """Return expert load distribution statistics."""
        total = self._usage.sum()
        if total == 0:
            fracs = np.ones(self.config.num_experts) / self.config.num_experts
        else:
            fracs = self._usage / total

        return {
            "expert_usage": {
                name: {
                    "count": int(self._usage[i]),
                    "fraction": round(float(fracs[i]), 4),
                }
                for i, name in enumerate(self.experts)
            },
            "total_routes": int(total),
            "gini_coefficient": round(_gini(fracs), 4),
            "load_balance_score": round(1.0 - _gini(fracs), 4),
            "lr": round(self._lr, 8),
            "step": self._step,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Optional[Path | str] = None) -> None:
        """Save weights to JSON file."""
        save_path = Path(path) if path else _DEFAULT_WEIGHTS_PATH
        save_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "W1": self.W1.tolist(),
            "b1": self.b1.tolist(),
            "W2": self.W2.tolist(),
            "b2": self.b2.tolist(),
            "vW2": self._vW2.tolist() if self._vW2 is not None else None,
            "vb2": self._vb2.tolist() if self._vb2 is not None else None,
            "usage": self._usage.tolist(),
            "step": self._step,
            "lr": self._lr,
            "experts": self.experts,
            "config": {
                "num_experts": self.config.num_experts,
                "input_dim": self.config.input_dim,
                "hidden_dim": self.config.hidden_dim,
                "top_k": self.config.top_k,
                "noise_std": self.config.noise_std,
                "lr": self.config.lr,
                "lr_decay": self.config.lr_decay,
                "load_balance_coef": self.config.load_balance_coef,
            },
        }
        atomic_json_write(save_path, payload)
        logger.debug(f"[VECTOR][moe_router] saved weights to {save_path}")

    def load(self, path: Optional[Path | str] = None) -> None:
        """Load weights from JSON file."""
        load_path = Path(path) if path else _DEFAULT_WEIGHTS_PATH
        if not load_path.exists():
            logger.warning(f"[VECTOR][moe_router] weights file not found: {load_path}")
            return
        payload = json.loads(load_path.read_text(encoding="utf-8"))
        self.W1 = np.array(payload["W1"], dtype=np.float64)
        self.b1 = np.array(payload["b1"], dtype=np.float64)
        self.W2 = np.array(payload["W2"], dtype=np.float64)
        self.b2 = np.array(payload["b2"], dtype=np.float64)
        if payload.get("vW2") is not None:
            self._vW2 = np.array(payload["vW2"], dtype=np.float64)
        if payload.get("vb2") is not None:
            self._vb2 = np.array(payload["vb2"], dtype=np.float64)
        self._usage = np.array(payload.get("usage", [0.0] * self.config.num_experts), dtype=np.float64)
        self._step = payload.get("step", 0)
        self._lr = payload.get("lr", self.config.lr)
        if "experts" in payload:
            self.experts = payload["experts"]
        logger.info(f"[VECTOR][moe_router] loaded weights from {load_path} (step={self._step})")


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import tempfile

    logger.remove()
    logger.add(sys.stderr, level="DEBUG")

    cfg = MoERouterConfig(num_experts=8, input_dim=384, hidden_dim=128, top_k=2, noise_std=0.0)
    router = MoERouter(config=cfg)

    # Basic routing
    rng = np.random.default_rng(7)
    emb = rng.standard_normal(384)
    experts_selected = router.route(emb, top_k=2)
    assert len(experts_selected) == 2, f"Expected 2 experts, got {len(experts_selected)}"
    assert all(e in EXPERTS for e in experts_selected), f"Unknown expert in {experts_selected}"

    # route_with_weights
    weights = router.route_with_weights(emb)
    assert len(weights) == 8
    assert abs(sum(weights.values()) - 1.0) < 1e-6, f"Weights don't sum to 1: {sum(weights.values())}"

    # route_text
    text_experts = router.route_text("fix the authentication bug")
    assert len(text_experts) == 2

    # update
    router.update(emb, experts_selected, reward=0.8)
    assert router._step == 1

    # stats
    stats = router.get_routing_stats()
    assert "expert_usage" in stats
    assert "gini_coefficient" in stats

    # save/load round-trip
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "moe-weights.json"
        router.save(path)
        assert path.exists()

        router2 = MoERouter(config=cfg)
        router2.load(path)
        assert router2._step == 1
        assert np.allclose(router2.W2, router.W2)

    print("✅ neural_moe_router OK")
