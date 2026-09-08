"""Embedding-based intent matcher for governor routing.

Uses nomic-embed-text (768-dim) via Ollama to compute cosine similarity
against stored example queries. Returns district + task_type for matches
above similarity threshold.

Pipeline position: Stage 2 (between regex pre-classifier and LLM fallback).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from loguru import logger

__all__ = ["IntentMatcher"]


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

    async def _ensure_embeddings_loaded(self) -> bool:
        """Lazy-load embeddings for all examples on first call."""
        if self._embeddings is not None:
            return True

        if not self._examples:
            logger.warning("[IntentMatcher] No examples loaded")
            return False

        logger.info(f"[IntentMatcher] Embedding {len(self._examples)} examples...")
        start = time.time()

        self._embeddings = []
        for example in self._examples:
            text = example.get("text", "")
            embedding = await self._embed(text)
            if embedding:
                self._embeddings.append(embedding)
            else:
                # If embedding fails, use zero vector (will never match)
                self._embeddings.append([0.0] * 768)

        elapsed = time.time() - start
        logger.info(f"[IntentMatcher] Embedded {len(self._examples)} examples in {elapsed:.2f}s")
        return True

    async def match(self, text: str) -> Optional[dict]:
        """Match query against example embeddings.

        Args:
            text: User query text.

        Returns:
            {"type": task_type, "district": district, "confidence": float, "source": "embedding_match"}
            or None if no match above threshold.
        """
        if not await self._ensure_embeddings_loaded():
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
