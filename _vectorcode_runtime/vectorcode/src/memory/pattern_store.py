"""
PatternStore — SONA port for VectorCode.

Stores successful task execution patterns in FAISSIndex and writes
reasoning chains to EpisodicMemory (RULE 8).

RULE 11: no Claude API — embeddings via Ollama nomic-embed-text.
RULE 8:  every save_pattern call stores in reasoning_chains.
"""
import sys
import uuid
import json
import math
import random

from core.config import CONFIG  # noqa: F401
from loguru import logger
from core.memory.episodic import EpisodicMemory
from .faiss_index import FAISSIndex

# ── Embedding helpers ─────────────────────────────────────────────────────────

_EMBED_MODEL = "nomic-embed-text"
_EMBED_DIM = 768


def _unit_random_vector(dim: int) -> list[float]:
    """Return a random unit vector of given dimension (fallback embedding)."""
    vec = [random.gauss(0, 1) for _ in range(dim)]
    mag = math.sqrt(sum(x * x for x in vec))
    if mag == 0.0:
        return [1.0 / math.sqrt(dim)] * dim
    return [x / mag for x in vec]


def _embed_via_ollama(text: str) -> list[float] | None:
    """
    Call Ollama nomic-embed-text to get a 768-dim embedding.
    Returns None on failure so the caller can fall back.
    """
    try:
        import ollama
        client = ollama.Client(host=CONFIG["ollama_host"], timeout=10.0)
        response = client.embeddings(model=_EMBED_MODEL, prompt=text)
        embedding = response.get("embedding", [])
        if len(embedding) == _EMBED_DIM:
            return embedding
        if embedding:
            logger.warning(
                f"[VECTOR][pattern_store] unexpected embedding dim={len(embedding)}, expected {_EMBED_DIM}"
            )
        return None
    except Exception as e:
        logger.warning(f"[VECTOR][pattern_store] Ollama embed unavailable: {e}")
        return None


# ── PatternStore ──────────────────────────────────────────────────────────────

class PatternStore:
    """
    Stores and retrieves task execution patterns using vector similarity.

    save_pattern() — embeds the task description, stores in FAISS + reasoning_chains.
    recall()       — embeds the query, finds the most similar stored pattern.
    update_reward() — updates avg_reward in the SQLite metadata for a pattern.
    """

    def __init__(self, index_path: str, similarity_threshold: float = 0.85) -> None:
        self._index_path = str(index_path)
        self._threshold = similarity_threshold
        self._faiss = FAISSIndex(index_path=index_path, dim=_EMBED_DIM)
        self._memory = EpisodicMemory()
        logger.info(
            f"[VECTOR][pattern_store] ready path={index_path} threshold={similarity_threshold}"
        )

    # ── Embedding ─────────────────────────────────────────────────────────────

    def _embed(self, text: str) -> list[float]:
        """
        Return 768-dim embedding for text.
        Uses Ollama nomic-embed-text; falls back to random unit vector with warning.
        """
        vec = _embed_via_ollama(text)
        if vec is not None:
            return vec
        logger.warning(
            "[VECTOR][pattern_store] Ollama unavailable — using random unit vector fallback"
        )
        return _unit_random_vector(_EMBED_DIM)

    # ── Public API ────────────────────────────────────────────────────────────

    def save_pattern(
        self,
        task: str,
        plan: list[str],
        outcome: str,
        reward: float,
    ) -> str:
        """
        Embed task, store in FAISS, and write to reasoning_chains (RULE 8).
        Returns pattern_id (UUID hex).
        """
        pattern_id = uuid.uuid4().hex
        vector = self._embed(task)

        metadata = {
            "pattern_id": pattern_id,
            "task": task,
            "plan": ",".join(plan),
            "outcome": outcome,
            "reward": reward,
        }
        self._faiss.add(pattern_id, vector, metadata)

        # RULE 8 — persist to reasoning_chains via EpisodicMemory
        self._memory.store_chain(
            situation=task,
            goal_ids=["vectorcode"],
            steps=plan,
            action="pattern_stored",
            outcome=outcome,
            reward=reward,
        )

        logger.info(
            f"[VECTOR][pattern_store] saved pattern_id={pattern_id} task={task!r} reward={reward}"
        )
        return pattern_id

    def recall(self, task: str) -> dict | None:
        """
        Embed the task query and return the best matching pattern if its
        cosine similarity meets self._threshold, else None.

        Returns dict with keys: pattern_id, task, plan, outcome, reward, score.
        """
        vector = self._embed(task)
        results = self._faiss.search(vector, k=1)

        if not results:
            return None

        best = results[0]
        if best["score"] < self._threshold:
            logger.debug(
                f"[VECTOR][pattern_store] recall miss score={best['score']:.3f} < {self._threshold}"
            )
            return None

        meta = best.get("meta", {})
        return {
            "pattern_id": meta.get("pattern_id", best["id"]),
            "task": meta.get("task", ""),
            "plan": meta.get("plan", "").split(",") if meta.get("plan") else [],
            "outcome": meta.get("outcome", ""),
            "reward": float(meta.get("reward", 0.0)),
            "score": best["score"],
        }

    def update_reward(self, pattern_id: str, reward: float) -> None:
        """
        Update the stored reward for a pattern by rewriting its metadata.
        The pattern must already exist in the FAISS metadata DB.
        """
        try:
            conn = self._faiss._meta_conn
            conn.execute(
                """
                UPDATE vectors
                SET metadata = json_set(metadata, '$.reward', ?)
                WHERE id = ?
                """,
                (reward, pattern_id),
            )
            conn.commit()
            logger.info(f"[VECTOR][pattern_store] updated reward pattern_id={pattern_id} reward={reward}")
        except Exception as e:
            logger.error(f"[VECTOR][pattern_store] update_reward failed: {e}")


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile
    sys.stdout.reconfigure(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        ps = PatternStore(index_path=f"{tmp}/patterns", similarity_threshold=0.5)

        pid = ps.save_pattern(
            task="write a FastAPI login endpoint",
            plan=["create router", "add POST /login", "hash password", "return JWT"],
            outcome="success",
            reward=0.9,
        )
        assert pid, "expected pattern_id"

        # With random fallback vectors, recall may not find the pattern above
        # threshold — just test that the API doesn't crash.
        result = ps.recall(task="build a login API")
        print(f"   recall result: {result}")

        ps.update_reward(pid, 0.95)

    print("✅ pattern_store.py OK")


