"""VECTOR FlashAttention — block-wise tiled attention for O(N) memory complexity."""
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

import time
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
from loguru import logger


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class FlashAttentionConfig:
    block_size: int = 32          # tile size (32-64 optimal for CPU L1 cache)
    dimensions: int = 64           # embedding dimensions
    temperature: float = 1.0       # softmax scaling (multiplied with 1/sqrt(dim))
    use_stable_mode: bool = True   # online softmax for numerical stability


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _softmax(x: np.ndarray) -> np.ndarray:
    """Numerically stable softmax along last axis."""
    x_shifted = x - np.max(x, axis=-1, keepdims=True)
    exp_x = np.exp(x_shifted)
    return exp_x / (np.sum(exp_x, axis=-1, keepdims=True) + 1e-9)


def _naive_attention(
    queries: np.ndarray,
    keys: np.ndarray,
    values: np.ndarray,
    scale: float,
) -> np.ndarray:
    """Standard O(N²) attention for correctness comparison."""
    scores = (queries @ keys.T) * scale          # (N, M)
    weights = _softmax(scores)                   # (N, M)
    return weights @ values                       # (N, D)


# ---------------------------------------------------------------------------
# FlashAttention
# ---------------------------------------------------------------------------

class FlashAttention:
    """Block-wise tiled attention: O(N) memory vs O(N²) naive.

    Algorithm:
    1. Split Q, K, V into blocks of block_size
    2. For each Q-block: iterate K/V blocks, accumulate online softmax
    3. Online softmax: track running max and sum, update output incrementally
    4. Result: same as full attention but never materialises N×N score matrix

    Methods:
    - compute(queries, keys, values) -> np.ndarray     main entry point
    - compute_single(query, keys, values) -> np.ndarray  single query vs all keys
    - benchmark(num_vectors, warmup=3, runs=10) -> dict   speedup vs naive
    """

    def __init__(self, config: Optional[FlashAttentionConfig] = None) -> None:
        self.config = config or FlashAttentionConfig()
        self._scale = 1.0 / (
            np.sqrt(self.config.dimensions) * self.config.temperature
        )
        logger.debug(
            f"[VECTOR][flash_attention] init: block_size={self.config.block_size} "
            f"dim={self.config.dimensions} scale={self._scale:.4f}"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute(
        self,
        queries: np.ndarray,
        keys: np.ndarray,
        values: np.ndarray,
    ) -> np.ndarray:
        """Flash attention over all queries.

        Args:
            queries: shape (N, D)
            keys:    shape (M, D)
            values:  shape (M, D)

        Returns:
            output:  shape (N, D)
        """
        queries = np.atleast_2d(queries).astype(np.float64)
        keys = np.atleast_2d(keys).astype(np.float64)
        values = np.atleast_2d(values).astype(np.float64)

        N, D = queries.shape
        M = keys.shape[0]
        block_size = self.config.block_size

        output = np.zeros((N, D), dtype=np.float64)

        # Iterate over Q blocks
        for q_start in range(0, N, block_size):
            q_end = min(q_start + block_size, N)
            Q_block = queries[q_start:q_end]           # (Bq, D)
            Bq = q_end - q_start

            # Per-row running state for online softmax
            running_max = np.full(Bq, -np.inf, dtype=np.float64)   # (Bq,)
            running_sum = np.zeros(Bq, dtype=np.float64)            # (Bq,)
            acc = np.zeros((Bq, D), dtype=np.float64)               # (Bq, D)

            # Iterate over K/V blocks
            for kv_start in range(0, M, block_size):
                kv_end = min(kv_start + block_size, M)
                K_block = keys[kv_start:kv_end]         # (Bk, D)
                V_block = values[kv_start:kv_end]       # (Bk, D)

                # Attention scores for this tile: (Bq, Bk)
                scores = (Q_block @ K_block.T) * self._scale

                # block max per query row
                block_max = np.max(scores, axis=1)      # (Bq,)

                # Update running max
                new_max = np.maximum(running_max, block_max)    # (Bq,)

                # Correction factor for previously accumulated values
                correction = np.exp(running_max - new_max)      # (Bq,)

                # Block attention weights (unnormalised, shifted by new_max)
                block_weights = np.exp(
                    scores - new_max[:, np.newaxis]
                )                                                # (Bq, Bk)
                block_sum = np.sum(block_weights, axis=1)        # (Bq,)

                # Update accumulator:
                #   acc = acc * correction * running_sum + block_weights @ V_block
                # (applied per-row — correction and running_sum are per-row scalars)
                acc = (
                    acc * (correction * running_sum)[:, np.newaxis]
                    + block_weights @ V_block
                )

                # Update running sum
                running_sum = running_sum * correction + block_sum  # (Bq,)

                # Update running max
                running_max = new_max

            # Normalise accumulated output
            safe_sum = np.where(running_sum > 0, running_sum, 1.0)
            output[q_start:q_end] = acc / safe_sum[:, np.newaxis]

        return output

    def compute_single(
        self,
        query: np.ndarray,
        keys: np.ndarray,
        values: np.ndarray,
    ) -> np.ndarray:
        """Flash attention for a single query vector.

        Args:
            query:  shape (D,) or (1, D)
            keys:   shape (M, D)
            values: shape (M, D)

        Returns:
            output: shape (D,)
        """
        query_2d = np.atleast_2d(query).astype(np.float64)
        result = self.compute(query_2d, keys, values)
        return result[0]

    def benchmark(
        self,
        num_vectors: int = 128,
        warmup: int = 3,
        runs: int = 10,
    ) -> dict:
        """Time flash attention vs naive attention.

        Args:
            num_vectors: sequence length N (same for Q, K, V)
            warmup:      number of warmup iterations (not timed)
            runs:        number of timed iterations

        Returns:
            dict with keys: flash_ms, naive_ms, speedup, correct
        """
        dim = self.config.dimensions
        rng = np.random.default_rng(42)

        Q = rng.standard_normal((num_vectors, dim))
        K = rng.standard_normal((num_vectors, dim))
        V = rng.standard_normal((num_vectors, dim))

        # --- Warmup ---
        for _ in range(warmup):
            _ = self.compute(Q, K, V)
            _ = _naive_attention(Q, K, V, self._scale)

        # --- Time flash ---
        flash_times: List[float] = []
        for _ in range(runs):
            t0 = time.perf_counter()
            flash_out = self.compute(Q, K, V)
            flash_times.append(time.perf_counter() - t0)

        # --- Time naive ---
        naive_times: List[float] = []
        for _ in range(runs):
            t0 = time.perf_counter()
            naive_out = _naive_attention(Q, K, V, self._scale)
            naive_times.append(time.perf_counter() - t0)

        flash_ms = float(np.median(flash_times) * 1000)
        naive_ms = float(np.median(naive_times) * 1000)
        speedup = naive_ms / flash_ms if flash_ms > 0 else float("inf")

        # Correctness check: max absolute difference
        max_diff = float(np.max(np.abs(flash_out - naive_out)))
        correct = max_diff < 1e-6

        result = {
            "flash_ms": round(flash_ms, 4),
            "naive_ms": round(naive_ms, 4),
            "speedup": round(speedup, 4),
            "correct": correct,
            "max_diff": max_diff,
            "num_vectors": num_vectors,
            "block_size": self.config.block_size,
            "dimensions": dim,
        }
        logger.info(
            f"[VECTOR][flash_attention] benchmark N={num_vectors}: "
            f"flash={flash_ms:.2f}ms naive={naive_ms:.2f}ms "
            f"speedup={speedup:.2f}x correct={correct}"
        )
        return result


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logger.remove()
    logger.add(sys.stderr, level="DEBUG")

    cfg = FlashAttentionConfig(block_size=32, dimensions=64, temperature=1.0)
    fa = FlashAttention(cfg)

    # Basic correctness: compare to naive
    rng = np.random.default_rng(0)
    Q = rng.standard_normal((64, 64))
    K = rng.standard_normal((64, 64))
    V = rng.standard_normal((64, 64))
    scale = 1.0 / np.sqrt(64)

    flash_out = fa.compute(Q, K, V)
    naive_out = _naive_attention(Q, K, V, scale)
    diff = np.max(np.abs(flash_out - naive_out))
    assert diff < 1e-6, f"Output mismatch: max_diff={diff}"

    # compute_single
    single = fa.compute_single(Q[0], K, V)
    assert single.shape == (64,), f"Bad shape: {single.shape}"

    # benchmark
    bm = fa.benchmark(num_vectors=64, warmup=2, runs=5)
    assert bm["correct"], f"Benchmark correctness failed: diff={bm['max_diff']}"
    assert "flash_ms" in bm and "naive_ms" in bm and "speedup" in bm

    print("✅ neural_flash_attention OK")
