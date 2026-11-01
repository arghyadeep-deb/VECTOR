"""Embedding-based intent matcher for governor routing.

Uses nomic-embed-text (768-dim) via Ollama to compute cosine similarity
against stored example queries. Returns district + task_type for matches
above similarity threshold.

Pipeline position: Stage 2 (between regex pre-classifier and LLM fallback).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

from loguru import logger

from core.config import CONFIG
from core.runtime_paths import data_path, get_project_root

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
# One retry pass bounds bootstrap work while recovering isolated transient
# failures. Each example is attempted at most 1 + EMBED_RETRY_PASSES times.
EMBED_RETRY_PASSES = 1
# Total wall-clock budget for ONE bootstrap attempt. The live healthy run took
# ~104s for 499 examples, so 180s leaves headroom while still ending a hung
# Ollama (10s per-call client timeout) long before 23+ timeouts pile up. The
# budget is checked between embedding calls, so an attempt can overrun it by at
# most one call.
BOOTSTRAP_BUDGET_SECONDS = 180.0
# Consecutive failed embeddings (within one pass) that abort the whole attempt:
# an unreachable Ollama fails every call, so there is no point trying the rest.
# Must stay above the transient-failure runs the retry pass is meant to absorb.
EMBED_ABORT_CONSECUTIVE_FAILURES = 5


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
        self._embeddings: Optional[list[Optional[list[float]]]] = None
        self._embedding_cache: dict[str, list[float]] = {}
        self._embedded_count = 0
        self._failed_count = 0
        self._bootstrap_state = "idle"
        # Per-attempt bounds (instance attributes so tests can shrink them) and
        # the outcome of the last attempt: how long it ran and why it stopped
        # ("complete", "budget", "abort" or "no_examples").
        self._bootstrap_budget_seconds = BOOTSTRAP_BUDGET_SECONDS
        self._abort_after_failures = EMBED_ABORT_CONSECUTIVE_FAILURES
        self._bootstrap_elapsed_seconds: Optional[float] = None
        self._bootstrap_stop_reason: Optional[str] = None
        self._similarity_threshold = 0.85
        self._model = "nomic-embed-text"
        self._ollama_host = "http://127.0.0.1:11434"
        # OWNER ROUTING CLOSURE (F3): the embedding bootstrap is a single
        # shared background Task, created lazily on first use (or via
        # prewarm()) and never re-created — see _get_or_start_init_task().
        self._init_task: Optional["asyncio.Task[bool]"] = None
        # One ollama client per matcher, built lazily by _get_client() (no
        # ollama call at construction time) and reused for every embedding.
        self._client = None
        self._client_lock = threading.Lock()

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

    def _get_client(self):
        """Return this matcher's single ollama client, building it on first use.

        _embed_sync runs in asyncio.to_thread workers, so the bootstrap and a
        query embed can reach here from different threads at once; the lock
        (the one place this module needs a cross-thread primitive — asyncio
        primitives are not thread-safe) guarantees exactly one construction.
        A constructor exception propagates without setting self._client, so
        the next embedding call retries instead of caching the failure."""
        client = self._client
        if client is not None:
            return client
        with self._client_lock:
            if self._client is None:
                import ollama
                self._client = ollama.Client(host=self._ollama_host, timeout=10.0)
            return self._client

    def _embed_sync(self, text: str) -> Optional[list[float]]:
        """Blocking ollama embedding call — run via asyncio.to_thread, never on the loop."""
        client = self._get_client()
        response = client.embeddings(model=self._model, prompt=text)
        embedding = response.get("embedding", [])
        if len(embedding) != 768:
            logger.warning(f"[IntentMatcher] Embedding dimension mismatch: {len(embedding)} != 768")
            return None
        return embedding

    async def _embed(self, text: str) -> Optional[list[float]]:
        """Embed text using nomic-embed-text via Ollama.

        Args:
            text: Text to embed.

        Returns:
            768-dim embedding vector, or None on failure.
        """
        # Check cache first
        if text in self._embedding_cache:
            cached = self._embedding_cache[text]
            if self._is_usable_embedding(cached):
                return cached
            # Defensive cleanup for stale or externally injected invalid cache
            # entries. Production failures never reach the cache below.
            del self._embedding_cache[text]

        try:
            # ollama.Client is synchronous: called directly inside `async def` it
            # blocks the whole event loop for the duration of the HTTP call (the
            # ~100 s prewarm froze uvicorn until it finished). Run it in a worker
            # thread; embeddings are still issued one at a time by the caller.
            embedding = await asyncio.to_thread(self._embed_sync, text)
            if not self._is_usable_embedding(embedding):
                if embedding is not None:
                    logger.warning("[IntentMatcher] Rejecting zero-norm or non-finite embedding")
                return None

            # Cache the embedding
            self._embedding_cache[text] = embedding
            return embedding

        except Exception as e:
            logger.error(f"[IntentMatcher] Embedding failed: {e}")
            return None

    @staticmethod
    def _is_usable_embedding(embedding: Optional[list[float]]) -> bool:
        """Return whether an embedding is finite and has a non-zero norm."""
        return bool(embedding) and all(math.isfinite(value) for value in embedding) and any(
            value != 0.0 for value in embedding
        )

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors.

        Pure-Python implementation with numpy fallback if available.
        """
        try:
            import numpy as np
            va = np.array(a)
            vb = np.array(b)
            norm_a = np.linalg.norm(va)
            norm_b = np.linalg.norm(vb)
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return float(np.dot(va, vb) / (norm_a * norm_b))
        except ImportError:
            # Pure-Python fallback
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = sum(x * x for x in a) ** 0.5
            norm_b = sum(x * x for x in b) ** 0.5
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)

    def _disk_cache_path(self) -> Path | None:
        settings = CONFIG["intent_matcher"]
        if not settings.get("cache_embeddings") or not settings.get("cache_path"):
            return None
        path = Path(settings["cache_path"])
        if path.is_absolute():
            return path
        if path.parts[0] == "data":
            return data_path(*path.parts[1:])
        return get_project_root() / path

    def _disk_cache_identity(self) -> dict | None:
        try:
            response = self._get_client().list()
            model_name = self._model if ":" in self._model.rsplit("/", 1)[-1] else f"{self._model}:latest"
            for model in response.get("models", []):
                if model.get("model", model.get("name")) != model_name:
                    continue
                digest = model.get("digest")
                if not isinstance(digest, str) or not digest:
                    return None
                examples_json = json.dumps(self._examples, sort_keys=True, ensure_ascii=False)
                return {
                    "version": 1,
                    "host": self._ollama_host,
                    "model": self._model,
                    "digest": digest,
                    "dimensions": 768,
                    "examples_sha256": hashlib.sha256(examples_json.encode("utf-8")).hexdigest(),
                }
        except Exception as exc:
            logger.debug("[IntentMatcher] Disk cache model identity unavailable: {}", exc)
        return None

    @staticmethod
    def _valid_disk_vector(vector) -> bool:
        return (
            isinstance(vector, list)
            and len(vector) == 768
            and all(type(value) in (int, float) and math.isfinite(value) for value in vector)
            and any(value != 0.0 for value in vector)
        )

    def _read_disk_cache(self, path: Path, identity: dict) -> list | None:
        try:
            maximum = int(CONFIG["intent_matcher"]["cache_max_bytes"])
            if maximum <= 0 or path.stat().st_size > maximum:
                return None
            with path.open("rb") as handle:
                content = handle.read(maximum + 1)
            if len(content) > maximum:
                return None
            payload = json.loads(content)
            if not isinstance(payload, dict) or payload.get("identity") != identity:
                return None
            vectors = payload.get("vectors")
            if not isinstance(vectors, list) or len(vectors) != len(self._examples):
                return None
            if not all(vector is None or self._valid_disk_vector(vector) for vector in vectors):
                return None
            return vectors
        except FileNotFoundError:
            return None
        except Exception as exc:
            logger.warning("[IntentMatcher] Ignoring invalid example embedding cache: {}", exc)
            return None

    async def _cache_io_before(self, deadline: float, function, *args):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            return await asyncio.wait_for(asyncio.to_thread(function, *args), timeout=remaining)
        except TimeoutError:
            logger.debug("[IntentMatcher] Skipping disk cache work after bootstrap budget expired")
            return None

    def _write_disk_cache(self, path: Path, identity: dict, embeddings: list, deadline: float) -> None:
        temporary_path = None
        try:
            if time.monotonic() >= deadline:
                return
            vectors = [vector if self._valid_disk_vector(vector) else None for vector in embeddings]
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
                temporary_path = Path(handle.name)
                json.dump({"identity": identity, "vectors": vectors}, handle, allow_nan=False, separators=(",", ":"))
            if (
                time.monotonic() < deadline
                and temporary_path.stat().st_size <= int(CONFIG["intent_matcher"]["cache_max_bytes"])
            ):
                temporary_path.replace(path)
        except Exception as exc:
            logger.warning("[IntentMatcher] Could not persist example embeddings: {}", exc)
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError as exc:
                    logger.debug("[IntentMatcher] Could not remove temporary embedding cache: {}", exc)

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
            self._embedded_count = 0
            self._failed_count = 0
            self._bootstrap_elapsed_seconds = 0.0
            self._bootstrap_stop_reason = "no_examples"
            self._bootstrap_state = "failed"
            logger.warning(
                "[IntentMatcher] No examples loaded; embedding bootstrap failed: "
                "embedded=0 failed=0 elapsed=0.00s stop=no_examples"
            )
            return False

        logger.info(f"[IntentMatcher] Embedding {len(self._examples)} examples...")
        self._bootstrap_state = "loading"
        start = time.monotonic()
        budget = self._bootstrap_budget_seconds
        deadline = start + budget
        abort_after = self._abort_after_failures
        stop_reason = "complete"

        # Bounded work: the budget is checked before every embedding call and a
        # run of `abort_after` consecutive failures ends the whole attempt. Both
        # stops leave the unattempted examples in `pending`, i.e. counted failed.
        embeddings: list[Optional[list[float]]] = [None] * len(self._examples)
        cache_path = self._disk_cache_path()
        cache_identity = None
        if cache_path is not None:
            cache_identity = await self._cache_io_before(deadline, self._disk_cache_identity)
            if cache_identity is not None:
                restored = await self._cache_io_before(deadline, self._read_disk_cache, cache_path, cache_identity)
                if restored is not None:
                    embeddings = restored
                    for example, vector in zip(self._examples, embeddings):
                        if vector is not None:
                            self._embedding_cache[example.get("text", "")] = vector
                    logger.info(
                        "[IntentMatcher] Restored {} cached example embeddings",
                        sum(vector is not None for vector in embeddings),
                    )
        pending = [index for index, vector in enumerate(embeddings) if vector is None]
        missing_count = len(pending)
        from core.inference.ollama_priority import has_interactive_demand

        poll_seconds = float(CONFIG["intent_matcher"]["interactive_poll_seconds"])
        quiet_seconds = float(CONFIG["intent_matcher"]["interactive_quiet_seconds"])
        quiet_until = 0.0
        for attempt in range(1 + EMBED_RETRY_PASSES):
            failed: list[int] = []
            consecutive_failures = 0
            for position, index in enumerate(pending):
                while time.monotonic() - start < budget:
                    if await has_interactive_demand():
                        quiet_until = time.monotonic() + quiet_seconds
                    elif time.monotonic() >= quiet_until:
                        break
                    remaining = max(0.0, budget - (time.monotonic() - start))
                    await asyncio.sleep(min(poll_seconds, remaining))
                if time.monotonic() - start >= budget:
                    stop_reason = "budget"
                    failed.extend(pending[position:])
                    break
                text = self._examples[index].get("text", "")
                embedding = await self._embed(text)
                if embedding is not None:
                    embeddings[index] = embedding
                    consecutive_failures = 0
                    continue
                failed.append(index)
                consecutive_failures += 1
                if consecutive_failures >= abort_after:
                    stop_reason = "abort"
                    failed.extend(pending[position + 1:])
                    break
            pending = failed
            if not pending or stop_reason != "complete":
                break
            if attempt < EMBED_RETRY_PASSES:
                logger.warning(
                    f"[IntentMatcher] Retrying {len(pending)} failed example embeddings "
                    f"(pass {attempt + 1}/{EMBED_RETRY_PASSES})"
                )

        embedded_count = len(embeddings) - len(pending)
        failed_count = len(pending)
        if (
            cache_path is not None
            and cache_identity is not None
            and embedded_count > len(embeddings) - missing_count
            and await self._cache_io_before(deadline, self._disk_cache_identity) == cache_identity
        ):
            await self._cache_io_before(
                deadline, self._write_disk_cache, cache_path, cache_identity, embeddings, deadline,
            )
        elapsed = time.monotonic() - start
        self._embedded_count = embedded_count
        self._failed_count = failed_count
        self._bootstrap_elapsed_seconds = elapsed
        self._bootstrap_stop_reason = stop_reason
        # The one summary line for this attempt (each branch below emits exactly one).
        summary = (
            f"embedded={embedded_count} failed={failed_count} "
            f"elapsed={elapsed:.2f}s stop={stop_reason}"
        )

        if embedded_count == 0:
            self._bootstrap_state = "failed"
            logger.warning(f"[IntentMatcher] Embedding bootstrap failed: {summary}")
            return False

        # Publish once, after all attempts and counters are complete. None marks
        # failed examples and is always skipped by match().
        self._embeddings = embeddings
        if failed_count:
            self._bootstrap_state = "degraded"
            logger.warning(f"[IntentMatcher] Embedding bootstrap degraded: {summary}")
        else:
            self._bootstrap_state = "ready"
            logger.info(f"[IntentMatcher] Embedding bootstrap ready: {summary}")
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

        # Incoming queries skip optional embedding work during voice demand;
        # the shared example bootstrap above pauses between examples.
        from core.inference.ollama_priority import has_interactive_demand
        if await has_interactive_demand():
            return None

        # Embed the query
        query_embedding = await self._embed(text)
        if query_embedding is None:
            logger.warning("[IntentMatcher] Failed to embed query")
            return None

        # Compute similarity against all examples
        best_match = None
        best_similarity = 0.0

        for i, example in enumerate(self._examples):
            example_embedding = self._embeddings[i]
            if example_embedding is None:
                continue
            similarity = self._cosine_similarity(query_embedding, example_embedding)

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = example

        # Check threshold
        if best_match is None or best_similarity < self._similarity_threshold:
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
            "ready": self._embeddings is not None,
            "degraded": self._failed_count > 0,
            "embedded_count": self._embedded_count,
            "failed_count": self._failed_count,
            "bootstrap_state": self._bootstrap_state,
            "bootstrap_elapsed_seconds": self._bootstrap_elapsed_seconds,
            "bootstrap_stop_reason": self._bootstrap_stop_reason,
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
