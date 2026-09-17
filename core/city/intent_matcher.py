"""Embedding-based intent matcher for governor routing.

Uses nomic-embed-text (768-dim) via Ollama to compute cosine similarity
against stored example queries. Returns district + task_type for matches
above similarity threshold.

Pipeline position: Stage 2 (between regex pre-classifier and LLM fallback).
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

from loguru import logger

__all__ = ["IntentMatcher"]

# OWNER ROUTING CLOSURE (2026-09-17, F3): how long a single owner /command
# request will wait on a still-loading embedding bootstrap before falling
# through to the (already-bounded, 45s-ceiling) LLM classifier for THIS
# request only. The bootstrap itself is never cancelled by this — it keeps
# running as a shared background task (see _get_or_start_init_task), so a
# later request finds it ready (or further along) without paying the cost
# again. See governor.py's classify_chat_intent() Stage 2 call site, the
# only caller that passes this. Not sourced from core/config.py CONFIG —
# kept as a local literal with an explanatory comment, consistent with this
# file's sibling timeout constants in governor.py (12.0/45.0).
COMMAND_PATH_WAIT_SECONDS = 3.0


class IntentMatcher:
    """Embedding-based intent classification using cosine similarity."""

    def __init__(self, examples_path: str = "data/intent_examples.json"):
        """Initialize matcher with example queries.

        Args:
            examples_path: Path to JSON file with example queries.
                Format: [{"text": "...", "district": "...", "task_type": "..."}, ...]
        """
        self._examples_path = Path(examples_path)
        self._examples: list[dict] = []
        self._embeddings: Optional[list[list[float]]] = None
        self._embedding_cache: dict[str, list[float]] = {}
        self._similarity_threshold = 0.85
        self._model = "nomic-embed-text"
        self._ollama_host = "http://127.0.0.1:11434"
        # OWNER ROUTING CLOSURE (F3): the embedding bootstrap is a single
        # shared background Task, created lazily on first use (or via
        # prewarm()) and never re-created — see _get_or_start_init_task().
        self._init_task: Optional["asyncio.Task[bool]"] = None

        # Load examples on init
        self._load_examples()

    def _load_examples(self) -> None:
        """Load example queries from JSON file."""
        if not self._examples_path.exists():
            logger.warning(f"[IntentMatcher] Examples file not found: {self._examples_path}")
            return

        try:
            with open(self._examples_path, "r", encoding="utf-8") as f:
                self._examples = json.load(f)
            logger.info(f"[IntentMatcher] Loaded {len(self._examples)} example queries")
        except Exception as e:
            logger.error(f"[IntentMatcher] Failed to load examples: {e}")
            self._examples = []

    async def _embed(self, text: str) -> Optional[list[float]]:
        """Embed text using nomic-embed-text via Ollama.

        Args:
            text: Text to embed.

        Returns:
            768-dim embedding vector, or None on failure.
        """
        # Check cache first
        if text in self._embedding_cache:
            return self._embedding_cache[text]

        try:
            import ollama
            client = ollama.Client(host=self._ollama_host, timeout=10.0)
            response = client.embeddings(model=self._model, prompt=text)
            embedding = response.get("embedding", [])

            if len(embedding) != 768:
                logger.warning(f"[IntentMatcher] Embedding dimension mismatch: {len(embedding)} != 768")
                return None

            # Cache the embedding
            self._embedding_cache[text] = embedding
            return embedding

        except Exception as e:
            logger.error(f"[IntentMatcher] Embedding failed: {e}")
            return None

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors.

        Pure-Python implementation with numpy fallback if available.
        """
        try:
            import numpy as np
            va = np.array(a)
            vb = np.array(b)
            return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb)))
        except ImportError:
            # Pure-Python fallback
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = sum(x * x for x in a) ** 0.5
            norm_b = sum(x * x for x in b) ** 0.5
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)

    async def _do_load_embeddings(self) -> bool:
        """The actual one-time embedding bootstrap. Runs as a single shared
        background Task (see _get_or_start_init_task) — self._embeddings is
        published atomically only once the whole pass is complete.

        OWNER ROUTING CLOSURE (2026-09-17, F3): the original version set
        `self._embeddings = []` (non-None) BEFORE this loop started, so a
        second concurrent caller's `self._embeddings is not None` check
        could see "already loaded" while the list was still being filled —
        a real correctness bug (index into a still-partial list), not just
        the ~100s of unbounded latency RGC2R_RGD2_COMBINED_REALITY_GATE_
        REPORT.md Section 8 measured live (103.90s / 499 examples). Building
        into a local list and assigning self._embeddings only at the end
        closes both: nothing observes a non-None-but-incomplete state, and
        every caller during the load shares this same Task object (never a
        duplicate embedding pass) via _get_or_start_init_task()."""
        if not self._examples:
            logger.warning("[IntentMatcher] No examples loaded")
            return False

        logger.info(f"[IntentMatcher] Embedding {len(self._examples)} examples...")
        start = time.time()

        embeddings: list[list[float]] = []
        for example in self._examples:
            text = example.get("text", "")
            embedding = await self._embed(text)
            if embedding:
                embeddings.append(embedding)
            else:
                # If embedding fails, use zero vector (will never match)
                embeddings.append([0.0] * 768)

        elapsed = time.time() - start
        self._embeddings = embeddings
        logger.info(f"[IntentMatcher] Embedded {len(self._examples)} examples in {elapsed:.2f}s")
        return True

    def _get_or_start_init_task(self) -> "asyncio.Task[bool]":
        """Return the shared embedding-bootstrap Task, creating it on first
        call. Synchronous, no `await` between the check and the assignment,
        so this is race-free under asyncio's single-threaded cooperative
        scheduling even when called from multiple concurrently-gathered
        coroutines."""
        if self._init_task is None:
            self._init_task = asyncio.ensure_future(self._do_load_embeddings())
        return self._init_task

    async def prewarm(self) -> None:
        """Kick off the background embedding load without blocking the
        caller. Intended to be called once, at application startup
        (core/api/app.py's lifespan), via `asyncio.create_task(matcher.
        prewarm())` — safe to call more than once or concurrently with
        match(); all callers share the same underlying task."""
        self._get_or_start_init_task()

    async def _ensure_embeddings_loaded(self) -> bool:
        """Back-compat wrapper: waits out the full bootstrap unconditionally
        (equivalent to match()'s default wait_timeout=None behavior)."""
        if self._embeddings is not None:
            return True
        return await self._get_or_start_init_task()

    async def match(self, text: str, *, wait_timeout: Optional[float] = None) -> Optional[dict]:
        """Match query against example embeddings.

        Args:
            text: User query text.
            wait_timeout: OWNER ROUTING CLOSURE (F3). None (default)
                preserves the original behavior — wait out the full
                embedding bootstrap unconditionally, exactly as every
                existing caller (tests, scripts/calibrate_intent_
                threshold.py, this module's own __main__ demo) already
                relies on. A float bounds how long THIS call waits on a
                still-loading bootstrap before returning None gracefully —
                the shared background task is NOT cancelled (via
                asyncio.shield), so it keeps running and a later call
                reuses it. governor.py's real /command path is the only
                caller that passes a bound (COMMAND_PATH_WAIT_SECONDS).

        Returns:
            {"type": task_type, "district": district, "confidence": float, "source": "embedding_match"}
            or None if no match above threshold, or embeddings are not
            ready within wait_timeout, or the bootstrap itself failed.
        """
        if self._embeddings is None:
            task = self._get_or_start_init_task()
            if wait_timeout is None:
                try:
                    loaded = await task
                except Exception as e:
                    logger.warning(f"[IntentMatcher] embedding bootstrap failed: {e}")
                    return None
            else:
                try:
                    loaded = await asyncio.wait_for(asyncio.shield(task), timeout=wait_timeout)
                except asyncio.TimeoutError:
                    logger.info(
                        f"[IntentMatcher] embeddings still loading after "
                        f"{wait_timeout:.2f}s (background load continues) — "
                        f"skipping match for this request"
                    )
                    return None
                except Exception as e:
                    logger.warning(f"[IntentMatcher] embedding bootstrap failed: {e}")
                    return None
            if not loaded:
                return None

        # Embed the query
        query_embedding = await self._embed(text)
        if not query_embedding:
            logger.warning("[IntentMatcher] Failed to embed query")
            return None

        # Compute similarity against all examples
        best_match = None
        best_similarity = 0.0

        for i, example in enumerate(self._examples):
            example_embedding = self._embeddings[i]
            similarity = self._cosine_similarity(query_embedding, example_embedding)

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = example

        # Check threshold
        if best_similarity < self._similarity_threshold:
            logger.debug(f"[IntentMatcher] No match above threshold: {best_similarity:.3f} < {self._similarity_threshold}")
            return None

        # Return match
        result = {
            "type": best_match.get("task_type", ""),
            "district": best_match.get("district", ""),
            "confidence": best_similarity,
            "source": "embedding_match",
        }
        logger.info(f"[IntentMatcher] Match: {text!r} -> {result['district']}/{result['type']} (sim={best_similarity:.3f})")
        return result

    def set_threshold(self, threshold: float) -> None:
        """Set similarity threshold (0.0-1.0)."""
        self._similarity_threshold = max(0.0, min(1.0, threshold))
        logger.info(f"[IntentMatcher] Threshold set to {self._similarity_threshold}")

    def get_stats(self) -> dict:
        """Get matcher statistics."""
        return {
            "examples_loaded": len(self._examples),
            "embeddings_cached": len(self._embedding_cache),
            "similarity_threshold": self._similarity_threshold,
            "model": self._model,
        }


if __name__ == "__main__":
    """Test intent matcher."""
    import asyncio

    async def test():
        matcher = IntentMatcher("data/intent_examples.json")

        # Test queries
        test_queries = [
            "quiz me on french",
            "help me scope this startup",
            "what are my goals",
            "study transformers with me",
            "generate a performance report",
        ]

        print("\n=== Intent Matcher Test ===\n")
        for query in test_queries:
            result = await matcher.match(query)
            if result:
                print(f"✅ {query!r}")
                print(f"   -> {result['district']}/{result['type']} (conf={result['confidence']:.3f})")
            else:
                print(f"❌ {query!r}")
                print(f"   -> No match")
            print()

        print(f"Stats: {matcher.get_stats()}")

    asyncio.run(test())
