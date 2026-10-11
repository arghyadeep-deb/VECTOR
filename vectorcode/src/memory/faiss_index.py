"""
FAISSIndex — HNSW vector index with SQLite metadata.

Uses faiss.IndexHNSWFlat for ANN search. Falls back to numpy dot-product
similarity if faiss is not installed.

RULE 11: no Claude API. Local inference only.
RULE 8:  patterns → reasoning_chains via EpisodicMemory (handled in PatternStore).
"""
from core.memory.db_utils import apply_pragmas
import sys
import json
import math
import sqlite3
import threading
import datetime
import os
import tempfile
from pathlib import Path
from typing import Any

from core.config import CONFIG  # noqa: F401 — required by every file
from loguru import logger


def _atomic_json_dump(path: str, value: Any) -> None:
    """Replace a JSON persistence file only after a flushed complete write."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as temp_file:
            json.dump(value, temp_file)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise

# ── FAISS availability check (once per process) ───────────────────────────────
_FAISS_WARNED = False
try:
    import faiss as _faiss
    _FAISS_AVAILABLE = True
except ImportError:
    _FAISS_AVAILABLE = False


def _warn_faiss_missing_once() -> None:
    global _FAISS_WARNED
    if not _FAISS_WARNED:
        logger.debug(
            "[VECTOR][faiss_index] faiss not installed — falling back to numpy "
            "cosine similarity."
        )
        _FAISS_WARNED = True


# ── Numpy cosine similarity fallback ─────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two equal-length vectors."""
    try:
        import numpy as np
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        norm_a = float(np.linalg.norm(va))
        norm_b = float(np.linalg.norm(vb))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return float(np.dot(va, vb) / (norm_a * norm_b))
    except ImportError:
        # Pure-Python fallback (slow but correct)
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(x * x for x in b))
        if mag_a == 0.0 or mag_b == 0.0:
            return 0.0
        return dot / (mag_a * mag_b)


# ── FAISSIndex ────────────────────────────────────────────────────────────────

class FAISSIndex:
    """
    HNSW vector index with SQLite metadata store.

    Persistence:
        {index_path}.faiss  — FAISS binary index
        {index_path}.meta.db — SQLite metadata (id, json metadata, added_at)

    Fallback:
        When faiss is unavailable, vectors are stored in-memory as a list and
        searched via cosine similarity (O(n) scan). A single warning is emitted.
    """

    def __init__(self, index_path: str, dim: int = 768, encrypted: bool = False) -> None:
        self._path = str(index_path)
        self._dim = dim
        self._encrypted = encrypted
        self._faiss_path = f"{self._path}.faiss"
        self._meta_path = f"{self._path}.meta.db"
        self._lock = threading.RLock()

        # id → int position mapping (needed for FAISS lookup by id)
        self._id_to_pos: dict[str, int] = {}
        # pos → id mapping
        self._pos_to_id: list[str] = []

        # Numpy fallback store: {id: vector}
        self._np_store: dict[str, list[float]] = {}

        if _FAISS_AVAILABLE:
            self._index = _faiss.IndexHNSWFlat(dim, 32)
        else:
            _warn_faiss_missing_once()
            self._index = None

        self._meta_conn = self._init_meta_db()
        logger.debug(f"[VECTOR][faiss_index] ready path={self._path} dim={dim} faiss={_FAISS_AVAILABLE}")

    # ── SQLite metadata ───────────────────────────────────────────────────────

    def _init_meta_db(self):
        conn = self._open_encrypted_meta_db() if self._encrypted else self._open_plain_meta_db()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vectors (
                id       TEXT PRIMARY KEY,
                metadata TEXT,
                added_at TEXT
            )
        """)
        conn.commit()
        return conn

    def _open_plain_meta_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._meta_path, check_same_thread=False)
        apply_pragmas(conn)
        return conn

    def _open_encrypted_meta_db(self):
        """AES-256 (SQLCipher) connection, reusing episodic memory's shared
        key derivation (FL-023: callers that want "the same encryption
        VECTOR's other memory already uses" get exactly that, not a
        second, separate key). Fails closed -- raises rather than silently
        falling back to plaintext -- if SQLCipher isn't installed."""
        try:
            import sqlcipher3 as sqlcipher
        except ImportError:
            try:
                from pysqlcipher3 import dbapi2 as sqlcipher
            except ImportError as exc:
                raise RuntimeError(
                    "FAISSIndex(encrypted=True) requires sqlcipher3 or pysqlcipher3; "
                    "neither is installed. Install one of them or construct with "
                    "encrypted=False."
                ) from exc

        from core.memory.episodic import _get_db_key, _sql_literal

        conn = sqlcipher.connect(self._meta_path, check_same_thread=False)
        try:
            conn.execute("PRAGMA key = " + _sql_literal(_get_db_key()))
            conn.execute("PRAGMA cipher_page_size = 4096")
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("SELECT count(*) FROM sqlite_master")
        except Exception:
            conn.close()
            raise
        return conn

    def _meta_insert(self, doc_id: str, metadata: dict) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock:
            self._meta_conn.execute(
                "INSERT OR REPLACE INTO vectors (id, metadata, added_at) VALUES (?, ?, ?)",
                (doc_id, json.dumps(metadata), now),
            )
            self._meta_conn.commit()

    def _meta_get(self, doc_id: str) -> dict:
        with self._lock:
            cur = self._meta_conn.cursor()
            cur.execute("SELECT metadata FROM vectors WHERE id = ?", (doc_id,))
            row = cur.fetchone()
        if row:
            return json.loads(row[0])
        return {}

    def _meta_delete(self, doc_id: str) -> None:
        with self._lock:
            self._meta_conn.execute("DELETE FROM vectors WHERE id = ?", (doc_id,))
            self._meta_conn.commit()

    def _meta_all_ids(self) -> list[str]:
        with self._lock:
            cur = self._meta_conn.cursor()
            cur.execute("SELECT id FROM vectors ORDER BY added_at")
            return [row[0] for row in cur.fetchall()]

    # ── Public API ────────────────────────────────────────────────────────────

    def add(self, doc_id: str, vector: list[float], metadata: dict) -> None:
        """Add a vector with associated metadata. Duplicate ids are replaced."""
        if doc_id in self._id_to_pos or doc_id in self._np_store:
            self.delete(doc_id)

        if _FAISS_AVAILABLE and self._index is not None:
            import numpy as np
            v = np.array([vector], dtype=np.float32)
            pos = len(self._pos_to_id)
            self._index.add(v)
            self._id_to_pos[doc_id] = pos
            self._pos_to_id.append(doc_id)
        else:
            self._np_store[doc_id] = list(vector)

        self._meta_insert(doc_id, metadata)
        logger.debug(f"[VECTOR][faiss_index] added id={doc_id}")

    def search(
        self,
        query_vector: list[float],
        k: int = 5,
        min_score: float = 0.0,
    ) -> list[dict]:
        """
        Return top-k matches as [{id, score, meta}] sorted by descending score.
        Scores are cosine similarities in [0, 1].
        """
        if _FAISS_AVAILABLE and self._index is not None:
            results = self._search_faiss(query_vector, k)
        else:
            results = self._search_numpy(query_vector, k)

        filtered = [r for r in results if r["score"] >= min_score]
        return filtered

    def _search_faiss(self, query_vector: list[float], k: int) -> list[dict]:
        """FAISS HNSW inner-product search converted to cosine via L2-norm."""
        if len(self._pos_to_id) == 0:
            return []

        import numpy as np
        # Normalise query for cosine approximation via inner product
        qv = np.array([query_vector], dtype=np.float32)
        norm = float(np.linalg.norm(qv))
        if norm > 0:
            qv_norm = qv / norm
        else:
            qv_norm = qv

        effective_k = min(k, len(self._pos_to_id))
        # HNSW does not support direct cosine — we store raw vectors and
        # post-process with cosine similarity for correctness.
        distances, indices = self._index.search(qv_norm, effective_k)

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self._pos_to_id):
                continue
            doc_id = self._pos_to_id[idx]
            if doc_id.startswith("__deleted__"):
                continue
            # Compute true cosine similarity for score
            stored_vec = self._get_stored_vector_faiss(idx)
            if stored_vec is not None:
                score = _cosine_similarity(query_vector, stored_vec)
            else:
                # Fall back to distance as approximate score
                score = max(0.0, float(1.0 - abs(float(dist))))
            meta = self._meta_get(doc_id)
            results.append({"id": doc_id, "score": round(score, 6), "meta": meta})

        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def _get_stored_vector_faiss(self, pos: int) -> list[float] | None:
        """Reconstruct vector from FAISS index at position pos."""
        try:
            import numpy as np
            # IndexHNSWFlat supports reconstruct
            vec = np.zeros(self._dim, dtype=np.float32)
            self._index.reconstruct(pos, vec)
            return vec.tolist()
        except Exception:
            return None

    def _search_numpy(self, query_vector: list[float], k: int) -> list[dict]:
        """O(n) cosine similarity scan."""
        if not self._np_store:
            return []

        scored = []
        for doc_id, vec in self._np_store.items():
            score = _cosine_similarity(query_vector, vec)
            meta = self._meta_get(doc_id)
            scored.append({"id": doc_id, "score": round(score, 6), "meta": meta})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:k]

    def save(self) -> None:
        """Persist the FAISS index and id mappings to disk."""
        if _FAISS_AVAILABLE and self._index is not None:
            _faiss.write_index(self._index, self._faiss_path)
            # Persist id ↔ pos mappings alongside index
            mapping_path = f"{self._path}.ids.json"
            _atomic_json_dump(mapping_path, self._pos_to_id)
            logger.info(f"[VECTOR][faiss_index] saved {len(self._pos_to_id)} vectors → {self._faiss_path}")
        else:
            # Save numpy store
            np_path = f"{self._path}.np.json"
            _atomic_json_dump(np_path, self._np_store)
            logger.info(f"[VECTOR][faiss_index] saved {len(self._np_store)} vectors (numpy) → {np_path}")

    def load(self) -> None:
        """Load index from disk if it exists."""
        if _FAISS_AVAILABLE:
            if Path(self._faiss_path).exists():
                self._index = _faiss.read_index(self._faiss_path)
                mapping_path = f"{self._path}.ids.json"
                if Path(mapping_path).exists():
                    with open(mapping_path, "r", encoding="utf-8") as f:
                        self._pos_to_id = json.load(f)
                    self._id_to_pos = {doc_id: i for i, doc_id in enumerate(self._pos_to_id)}
                logger.info(f"[VECTOR][faiss_index] loaded {len(self._pos_to_id)} vectors from {self._faiss_path}")
        else:
            np_path = f"{self._path}.np.json"
            if Path(np_path).exists():
                with open(np_path, "r", encoding="utf-8") as f:
                    self._np_store = json.load(f)
                logger.info(f"[VECTOR][faiss_index] loaded {len(self._np_store)} vectors (numpy) from {np_path}")

    def delete(self, doc_id: str) -> None:
        """
        Remove a vector by id. FAISS HNSW does not support deletion directly,
        so the position is tombstoned and excluded from future results via metadata.
        The numpy fallback deletes cleanly.
        """
        if doc_id in self._np_store:
            del self._np_store[doc_id]
        elif doc_id in self._id_to_pos:
            # Mark as deleted in metadata — FAISS position remains but won't be found
            pos = self._id_to_pos.pop(doc_id)
            if pos < len(self._pos_to_id):
                self._pos_to_id[pos] = f"__deleted__{doc_id}"
        self._meta_delete(doc_id)
        logger.debug(f"[VECTOR][faiss_index] deleted id={doc_id}")

    def contains(self, doc_id: str) -> bool:
        """Return True if doc_id is currently present (added and not deleted)."""
        return doc_id in self._np_store or doc_id in self._id_to_pos

    def size(self) -> int:
        """Return number of live (non-deleted) vectors."""
        if _FAISS_AVAILABLE and self._index is not None:
            return len(self._id_to_pos)
        return len(self._np_store)


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile
    sys.stdout.reconfigure(encoding="utf-8")

    tmp = tempfile.mkdtemp()
    try:
        idx = FAISSIndex(index_path=f"{tmp}/smoke", dim=4)

        idx.add("a", [1.0, 0.0, 0.0, 0.0], {"label": "A"})
        idx.add("b", [0.0, 1.0, 0.0, 0.0], {"label": "B"})
        idx.add("c", [1.0, 0.1, 0.0, 0.0], {"label": "C — similar to A"})

        results = idx.search([1.0, 0.0, 0.0, 0.0], k=2)
        assert len(results) == 2, f"expected 2, got {len(results)}"
        assert results[0]["id"] in ("a", "c"), f"expected a or c first, got {results[0]['id']}"

        idx.save()
        idx2 = FAISSIndex(index_path=f"{tmp}/smoke", dim=4)
        idx2.load()
        r2 = idx2.search([1.0, 0.0, 0.0, 0.0], k=1)
        assert r2[0]["id"] in ("a", "c"), f"reload failed: {r2}"

        assert idx.size() == 3
        idx.delete("b")
        assert idx.size() == 2

        idx._meta_conn.close()
        idx2._meta_conn.close()
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print("faiss_index.py OK")


