import sys

__all__ = [
    "EpisodicMemory",
    "get_db_connection",
    "get_temp_cursor",
]

from core.config import CONFIG
from core.resilience.circuit_breaker import CircuitBreakerOpenError
from core.breaker_registry import get_registry
from loguru import logger
import asyncio, uuid, json, os, sqlite3, datetime, threading
from contextlib import contextmanager

# Try SQLCipher for AES-256 encryption; fall back to plain sqlite3
# Supports both sqlcipher3-binary (pip install sqlcipher3-binary) and pysqlcipher3
try:
    import sqlcipher3 as sqlcipher  # sqlcipher3-binary package
    _USE_SQLCIPHER = True
    logger.info("[VECTOR][memory] SQLCipher (sqlcipher3) available — AES-256 encryption enabled")
except ImportError:
    try:
        from pysqlcipher3 import dbapi2 as sqlcipher  # legacy package
        _USE_SQLCIPHER = True
        logger.info("[VECTOR][memory] SQLCipher (pysqlcipher3) available — AES-256 encryption enabled")
    except ImportError:
        sqlcipher = None
        _USE_SQLCIPHER = False
        logger.warning("[VECTOR][memory] SQLCipher not available — using plain SQLite (install sqlcipher3-binary to encrypt)")

_DB_KEY = None  # resolved lazily below

def _get_db_key() -> str:
    """Derive encryption key from env var or OS keyring. Never hardcoded."""
    global _DB_KEY
    if _DB_KEY is not None:
        return _DB_KEY
    # Priority 1: environment variable
    key = os.environ.get("VECTOR_DB_KEY", "")
    if key:
        _DB_KEY = key
        return _DB_KEY
    # Priority 2: OS keyring
    try:
        import keyring
        stored = keyring.get_password("vector", "db_key")
        if stored:
            _DB_KEY = stored
            return _DB_KEY
        # First run: generate and store
        import secrets
        new_key = secrets.token_hex(32)
        keyring.set_password("vector", "db_key", new_key)
        _DB_KEY = new_key
        logger.info("[VECTOR][memory] Generated and stored new DB key in OS keyring")
        return _DB_KEY
    except Exception:
        logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
    # No key found — fail-fast if SQLCipher is active to prevent silent use of a hardcoded key
    if _USE_SQLCIPHER:
        raise RuntimeError(
            "[VECTOR][memory] DB encryption key unavailable: VECTOR_DB_KEY env var not set and OS keyring failed. "
            "Set VECTOR_DB_KEY in your .env file before starting VECTOR."
        )
    # Plain SQLite — no encryption key needed
    _DB_KEY = ""
    return _DB_KEY

# In-memory buffer for writes when circuit breaker is open
_memory_buffer: list[dict] = []
_buffer_lock = threading.Lock()

def _replay_buffer():
    with _buffer_lock:
        if not _memory_buffer:
            return
        items = list(_memory_buffer)
        _memory_buffer.clear()
    conn = get_db_connection()
    for item in items:
        try:
            with conn:
                conn.execute(
                    "INSERT INTO episodic_memory (id, event_type, content, tags, context_snapshot, timestamp, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (item["id"], item["event_type"], item["content"], item.get("tags"), item.get("context_snapshot"), item["timestamp"], item["source"]),
                )
        except Exception as e:
            logger.warning("[VECTOR][episodic] buffer replay failed: {}", e)

def _with_cb(op, *args, **kwargs):
    import time
    cb = get_registry().get("episodic_memory")
    if cb is None:
        return op(*args, **kwargs)
    # Detect whether we are already inside a running event loop.
    # asyncio.run() raises RuntimeError in that context, so we skip the coroutine
    # path entirely and call the synchronous operation directly with manual CB bookkeeping.
    _in_async = False
    try:
        loop = asyncio.get_event_loop()
        _in_async = loop.is_running()
    except RuntimeError:
        pass
    from core.resilience.circuit_breaker import CircuitState

    def _run_sync_with_cb() -> object:
        """Execute op() with manual CB bookkeeping (used when asyncio.run is unavailable)."""
        _t = time.time()
        if cb.state == CircuitState.OPEN:
            if _t - cb.last_failure_time < cb.config.recovery_timeout:
                raise CircuitBreakerOpenError("circuit breaker 'episodic_memory' is open")
            cb.state = CircuitState.HALF_OPEN
            cb.success_count = 0
            cb._half_open_retries = 0
        if cb.state == CircuitState.HALF_OPEN and cb._half_open_retries >= cb.config.half_open_max_retries:
            raise CircuitBreakerOpenError("circuit breaker 'episodic_memory' half-open retries exhausted")
        if cb.state == CircuitState.HALF_OPEN:
            cb._half_open_retries += 1
        try:
            result = op(*args, **kwargs)
            if cb.state == CircuitState.HALF_OPEN:
                cb.success_count += 1
                if cb.success_count >= cb.config.success_threshold:
                    cb.state = CircuitState.CLOSED
                    cb.failure_count = 0
                    _replay_buffer()
            elif cb.state == CircuitState.CLOSED:
                cb.failure_count = 0
            return result
        except Exception:
            _t2 = time.time()
            cb.failure_count += 1
            cb.last_failure_time = _t2
            if cb.state == CircuitState.CLOSED and cb.failure_count >= cb.config.failure_threshold:
                cb.state = CircuitState.OPEN
            elif cb.state == CircuitState.HALF_OPEN:
                cb.state = CircuitState.OPEN
            raise

    if _in_async:
        # Async context: asyncio.run() would raise "This event loop is already running".
        # Skip the coroutine wrapper entirely and apply CB bookkeeping synchronously.
        return _run_sync_with_cb()
    else:
        # Sync context: use the coroutine-based CB path (original behaviour).
        _coro = cb.call(lambda: op(*args, **kwargs))
        try:
            return asyncio.run(_coro)
        except RuntimeError:
            # asyncio.run failed (e.g. nested loop detected at runtime despite _in_async check).
            # Close the stale coroutine and fall back to sync CB path.
            _coro.close()
            return _run_sync_with_cb()

# Singleton database connection with thread-safe access
_db_connection = None
_db_lock = threading.Lock()


def get_db_connection():
    """Get or create singleton DB connection with thread-safe initialization."""
    global _db_connection
    with _db_lock:
        if _db_connection is None:
            if _USE_SQLCIPHER:
                _db_connection = sqlcipher.connect(str(CONFIG['db_path']), check_same_thread=False)
                # Use parameterized-style key setting (no f-string SQL)
                db_key = _get_db_key()
                _db_connection.execute("PRAGMA key=?", (db_key,))
            else:
                _db_connection = sqlite3.connect(CONFIG['db_path'], check_same_thread=False)
            _db_connection.execute("PRAGMA journal_mode=WAL")
            _db_connection.execute("PRAGMA busy_timeout=5000")
            _db_connection.execute("PRAGMA synchronous=NORMAL")
            _create_tables(_db_connection)
            logger.info("[VECTOR][memory] Episodic memory DB connection established")
        return _db_connection


def _create_tables(conn):
    """Create memory tables if they don't exist, using FTS5 for episodic search."""
    tables = [
        # FTS5 virtual table for full-text search on episodic memory
        """CREATE VIRTUAL TABLE IF NOT EXISTS episodic_memory_fts
           USING fts5(id, event_type, content, tags, source, timestamp UNINDEXED, context_snapshot UNINDEXED)""",
        # Backing table for non-FTS queries and metadata
        """CREATE TABLE IF NOT EXISTS episodic_memory (
            id TEXT PRIMARY KEY,
            event_type TEXT,
            content TEXT,
            tags TEXT,
            context_snapshot TEXT,
            timestamp TEXT,
            source TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS semantic_memory (
            key TEXT PRIMARY KEY,
            value TEXT,
            category TEXT,
            confidence REAL DEFAULT 0.5,
            updated_at TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS policy_memory (
            action_type TEXT,
            situation_hash TEXT,
            avg_reward REAL,
            sample_count INTEGER DEFAULT 0,
            last_updated TEXT,
            PRIMARY KEY (action_type, situation_hash)
        )""",
        """CREATE TABLE IF NOT EXISTS reasoning_chains (
            chain_id TEXT PRIMARY KEY,
            situation TEXT,
            goal_ids TEXT,
            steps TEXT,
            action_taken TEXT,
            outcome TEXT,
            reward REAL DEFAULT 0.0,
            is_training_data INTEGER DEFAULT 0,
            timestamp TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS skill_memory (
            skill_name TEXT PRIMARY KEY,
            confidence REAL DEFAULT 0.5,
            last_practiced TEXT,
            evidence TEXT,
            related_skills TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS agent_history (
            agent_id TEXT,
            agent_name TEXT,
            district TEXT,
            generation INTEGER,
            final_hp INTEGER,
            ghost_memory TEXT,
            died_at TEXT,
            PRIMARY KEY (agent_id, generation)
        )""",
        # C2: semantic embeddings for hybrid search (backfilled on first use)
        """CREATE TABLE IF NOT EXISTS episodic_embeddings (
            id TEXT PRIMARY KEY,
            embedding BLOB NOT NULL,
            model TEXT NOT NULL DEFAULT 'all-MiniLM-L6-v2',
            created_at TEXT
        )""",
    ]
    for table in tables:
        try:
            conn.execute(table)
        except sqlite3.OperationalError as e:
            logger.error(f"Table creation failed: {e}")


@contextmanager
def get_temp_cursor():
    """Context manager for temporary cursor with automatic cleanup."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database operation failed: {e}")
        raise
    finally:
        cursor.close()


class EpisodicMemory:
    """Thread-safe SQLite-backed episodic memory with connection pooling."""
    
    def __init__(self):
        self.conn = get_db_connection()
        logger.info("Episodic memory initialized (singleton connection)")

    def store(self, event_type, content, tags=None, context=None, source='vector') -> str:
        event_id = str(uuid.uuid4())
        tags_json = json.dumps(tags) if tags else None
        context_json = json.dumps(context) if context else None
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        try:
            def _do_store():
                with get_temp_cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO episodic_memory
                        (id, event_type, content, tags, context_snapshot, timestamp, source)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (event_id, event_type, content, tags_json, context_json, timestamp, source))
                    cursor.execute("""
                        INSERT INTO episodic_memory_fts
                        (id, event_type, content, tags, source, timestamp, context_snapshot)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (event_id, event_type, content, tags_json or '', source, timestamp, context_json or ''))
            _with_cb(_do_store)

            try:
                from core.engine.memory_tree.tree_builder import MemoryTree
                _tree = MemoryTree()
                _tree.ingest(
                    source_kind="episodic",
                    source_id=source,
                    content=content,
                    topic=event_type,
                    tags=tags or [],
                    score=0.8,
                )
            except Exception as _tree_err:
                logger.debug(f"[VECTOR][episodic] MemoryTree ingestion skipped: {_tree_err}")

            return event_id
        except CircuitBreakerOpenError:
            with _buffer_lock:
                _memory_buffer.append({
                    "id": event_id, "event_type": event_type, "content": content,
                    "tags": tags_json, "context_snapshot": context_json,
                    "timestamp": timestamp, "source": source,
                })
            logger.warning("[VECTOR][episodic] circuit open — buffered event {}", event_id[:8])
            return event_id
        except Exception as e:
            logger.error(f"[VECTOR][episodic] store() failed — event lost: {e}")
            raise RuntimeError(f"Episodic store failed: {e}") from e

    def recall(self, query, limit=5, event_type=None) -> list[dict]:
        try:
            def _do_recall():
                with get_temp_cursor() as cursor:
                    try:
                        if event_type:
                            cursor.execute(
                                """
                                SELECT f.id, f.event_type, f.content, f.tags, f.context_snapshot, f.timestamp, f.source
                                FROM episodic_memory_fts f
                                WHERE episodic_memory_fts MATCH ? AND f.event_type = ?
                                ORDER BY rank
                                LIMIT ?
                                """,
                                (query, event_type, limit),
                            )
                        else:
                            cursor.execute(
                                """
                                SELECT f.id, f.event_type, f.content, f.tags, f.context_snapshot, f.timestamp, f.source
                                FROM episodic_memory_fts f
                                WHERE episodic_memory_fts MATCH ?
                                ORDER BY rank
                                LIMIT ?
                                """,
                                (query, limit),
                            )
                        rows = cursor.fetchall()
                    except Exception:
                        query_pattern = f"%{query}%"
                        if event_type:
                            cursor.execute(
                                """SELECT id, event_type, content, tags, context_snapshot, timestamp, source
                                FROM episodic_memory WHERE content LIKE ? AND event_type = ?
                                ORDER BY timestamp DESC LIMIT ?""",
                                (query_pattern, event_type, limit),
                            )
                        else:
                            cursor.execute(
                                """SELECT id, event_type, content, tags, context_snapshot, timestamp, source
                                FROM episodic_memory WHERE content LIKE ?
                                ORDER BY timestamp DESC LIMIT ?""",
                                (query_pattern, limit),
                            )
                        rows = cursor.fetchall()
                    return rows
            rows = _with_cb(_do_recall)

            result = []
            for row in rows:
                result.append({
                    "id": row[0],
                    "event_type": row[1],
                    "content": row[2],
                    "tags": json.loads(row[3]) if row[3] else None,
                    "context": json.loads(row[4]) if row[4] else None,
                    "timestamp": row[5],
                    "source": row[6],
                })
            return result
        except CircuitBreakerOpenError:
            logger.warning("[VECTOR][episodic] circuit open — recall returning empty")
            return []
        except Exception as e:
            logger.error(f"Recall failed: {e}")
            return []
    
    def remember(self, key, value, category='general', confidence=0.5) -> bool:
        try:
            updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            def _do():
                with get_temp_cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO semantic_memory (key, value, category, confidence, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(key) DO UPDATE SET
                            value=excluded.value,
                            category=excluded.category,
                            confidence=excluded.confidence,
                            updated_at=excluded.updated_at
                    """, (key, value, category, confidence, updated_at))
                return True
            return _with_cb(_do)
        except CircuitBreakerOpenError:
            return False
        except Exception as e:
            logger.error(f"Remember failed: {e}")
            return False

    def recall_fact(self, key) -> dict | None:
        try:
            def _do():
                with get_temp_cursor() as cursor:
                    cursor.execute("""
                        SELECT * FROM semantic_memory
                        WHERE key = ?
                    """, (key,))
                    row = cursor.fetchone()
                    if row:
                        columns = [desc[0] for desc in cursor.description]
                        return dict(zip(columns, row))
                    return None
            return _with_cb(_do)
        except CircuitBreakerOpenError:
            return None
        except Exception as e:
            logger.error(f"Recall fact failed: {e}")
            return None
    
    def store_chain(self, situation, goal_ids, steps, action, outcome, reward) -> str:
        try:
            chain_id = str(uuid.uuid4())
            goal_ids_json = json.dumps(goal_ids)
            steps_json = json.dumps(steps)
            is_training = 1 if reward > 0.7 else 0
            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
            def _do():
                with get_temp_cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO reasoning_chains
                        (chain_id, situation, goal_ids, steps, action_taken, outcome, reward, is_training_data, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (chain_id, situation, goal_ids_json, steps_json, action, outcome, reward, is_training, timestamp))
                return chain_id
            return _with_cb(_do)
        except CircuitBreakerOpenError:
            return ""
        except Exception as e:
            logger.error(f"Store chain failed: {e}")
            return ""

    def get_training_data(self, limit=100) -> list[dict]:
        try:
            def _do():
                with get_temp_cursor() as cursor:
                    cursor.execute("""
                        SELECT * FROM reasoning_chains
                        WHERE is_training_data = 1
                        ORDER BY reward DESC
                        LIMIT ?
                    """, (limit,))
                    columns = [desc[0] for desc in cursor.description]
                    return [dict(zip(columns, row)) for row in cursor.fetchall()]
            return _with_cb(_do)
        except CircuitBreakerOpenError:
            return []
        except Exception as e:
            logger.error(f"Get training data failed: {e}")
            return []

    def update_skill(self, skill_name, confidence, evidence=None) -> bool:
        try:
            evidence_json = json.dumps(evidence) if evidence else None
            def _do():
                with get_temp_cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO skill_memory (skill_name, confidence, evidence)
                        VALUES (?, ?, ?)
                        ON CONFLICT(skill_name) DO UPDATE SET
                            confidence=excluded.confidence,
                            evidence=COALESCE(excluded.evidence, skill_memory.evidence)
                    """, (skill_name, confidence, evidence_json))
                return True
            return _with_cb(_do)
        except CircuitBreakerOpenError:
            return False
        except Exception as e:
            logger.error(f"Update skill failed: {e}")
            return False

    def get_skill(self, skill_name) -> dict | None:
        try:
            def _do():
                with get_temp_cursor() as cursor:
                    cursor.execute("""
                        SELECT * FROM skill_memory
                        WHERE skill_name = ?
                    """, (skill_name,))
                    row = cursor.fetchone()
                    if row:
                        columns = [desc[0] for desc in cursor.description]
                        return dict(zip(columns, row))
                    return None
            return _with_cb(_do)
        except CircuitBreakerOpenError:
            return None
        except Exception as e:
            logger.error(f"Get skill failed: {e}")
            return None

    def get_recent_events(self, limit: int = 20) -> list[dict]:
        """Return the most recent episodic memory entries (used by 2AM synthesis)."""
        try:
            def _do():
                with get_temp_cursor() as cursor:
                    cursor.execute(
                        """SELECT id, event_type, content, tags, context_snapshot, timestamp, source
                           FROM episodic_memory
                           ORDER BY timestamp DESC
                           LIMIT ?""",
                        (limit,)
                    )
                    rows = cursor.fetchall()
                    return [
                        {
                            "id": r[0],
                            "event_type": r[1],
                            "content": r[2],
                            "tags": json.loads(r[3]) if r[3] else None,
                            "metadata": json.loads(r[4]) if r[4] else None,
                            "timestamp": r[5],
                            "source": r[6],
                        }
                        for r in rows
                    ]
            return _with_cb(_do)
        except CircuitBreakerOpenError:
            logger.warning("[VECTOR][episodic] get_recent_events: circuit open — returning empty")
            return []
        except Exception as e:
            logger.warning("[VECTOR][episodic] get_recent_events error: {}", e)
            return []

    def get_stats(self) -> dict:
        _TABLES = ("episodic_memory", "semantic_memory", "policy_memory",
                   "reasoning_chains", "skill_memory", "agent_history")
        try:
            def _do():
                stats = {}
                with get_temp_cursor() as cursor:
                    for table in _TABLES:
                        cursor.execute(f"SELECT COUNT(*) FROM {table}")
                        stats[table] = cursor.fetchone()[0]
                return stats
            return _with_cb(_do)
        except CircuitBreakerOpenError:
            return {}
        except Exception as e:
            logger.error(f"Get stats failed: {e}")
            return {}
    
    # ── C2: Semantic search ───────────────────────────────────────────────────

    _EMBED_MODEL = "all-MiniLM-L6-v2"
    _EMBED_DIM = 384

    def search_semantic(self, query: str, top_k: int = 10) -> list[dict]:
        """Hybrid semantic + FTS5 search (70% semantic / 30% keyword).

        Falls back to FTS5-only `recall()` when:
          - sentence-transformers is not installed
          - the embeddings table is empty (first run before backfill)
          - query is empty string
        """
        if not query:
            return self.recall("", limit=top_k)

        try:
            import numpy as np
            from sentence_transformers import SentenceTransformer  # type: ignore[import]
        except ImportError:
            logger.debug("[VECTOR][episodic] sentence-transformers unavailable — FTS5 fallback")
            return self.recall(query, limit=top_k)

        try:
            model = SentenceTransformer(self._EMBED_MODEL)
            query_vec = model.encode(query, normalize_embeddings=True).astype("float32")

            # Lazily backfill embeddings for all un-embedded episodes
            self._ensure_embeddings(model)

            # Fetch all stored embeddings
            with get_temp_cursor() as cursor:
                cursor.execute(
                    "SELECT id, embedding FROM episodic_embeddings WHERE model = ?",
                    (self._EMBED_MODEL,),
                )
                rows = cursor.fetchall()

            if not rows:
                return self.recall(query, limit=top_k)

            # Cosine similarity (embeddings are L2-normalised)
            ids = [r[0] for r in rows]
            matrix = np.frombuffer(b"".join(r[1] for r in rows), dtype="float32").reshape(
                len(rows), self._EMBED_DIM
            )
            sem_scores = (matrix @ query_vec).tolist()  # shape (N,)

            # FTS5 scores — best effort, ignore on failure
            fts_map: dict[str, float] = {}
            try:
                with get_temp_cursor() as cursor:
                    cursor.execute(
                        "SELECT id, rank FROM episodic_memory_fts WHERE episodic_memory_fts MATCH ? LIMIT 200",
                        (query,),
                    )
                    fts_rows = cursor.fetchall()
                if fts_rows:
                    raw_ranks = [abs(r[1]) for r in fts_rows]
                    max_rank = max(raw_ranks) or 1.0
                    fts_map = {r[0]: abs(r[1]) / max_rank for r in fts_rows}
            except Exception:
                pass

            # Hybrid score
            scored = [
                (ids[i], 0.7 * sem_scores[i] + 0.3 * fts_map.get(ids[i], 0.0))
                for i in range(len(ids))
            ]
            scored.sort(key=lambda x: x[1], reverse=True)
            top_ids = [s[0] for s in scored[:top_k]]

            # Fetch full records ordered by score
            results = []
            for ep_id in top_ids:
                with get_temp_cursor() as cursor:
                    cursor.execute(
                        "SELECT id, event_type, content, tags, context_snapshot, timestamp, source "
                        "FROM episodic_memory WHERE id = ?",
                        (ep_id,),
                    )
                    row = cursor.fetchone()
                if row:
                    results.append({
                        "id": row[0],
                        "event_type": row[1],
                        "content": row[2],
                        "tags": json.loads(row[3]) if row[3] else None,
                        "context": json.loads(row[4]) if row[4] else None,
                        "timestamp": row[5],
                        "source": row[6],
                    })
            return results

        except Exception as e:
            logger.warning("[VECTOR][episodic] search_semantic failed, FTS5 fallback: {}", e)
            return self.recall(query, limit=top_k)

    def _ensure_embeddings(self, model: object) -> None:
        """Backfill embeddings for episodic_memory rows not yet embedded."""
        import numpy as np
        import datetime as _dt

        try:
            with get_temp_cursor() as cursor:
                cursor.execute(
                    """SELECT e.id, e.content FROM episodic_memory e
                       LEFT JOIN episodic_embeddings emb ON e.id = emb.id
                       WHERE emb.id IS NULL LIMIT 500"""
                )
                missing = cursor.fetchall()

            if not missing:
                return

            logger.debug("[VECTOR][episodic] backfilling {} embeddings", len(missing))
            texts = [row[1] or "" for row in missing]
            vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

            now = _dt.datetime.now(_dt.timezone.utc).isoformat()
            with get_temp_cursor() as cursor:
                for (ep_id, _), vec in zip(missing, vectors):
                    cursor.execute(
                        "INSERT OR IGNORE INTO episodic_embeddings (id, embedding, model, created_at) VALUES (?, ?, ?, ?)",
                        (ep_id, vec.astype("float32").tobytes(), self._EMBED_MODEL, now),
                    )
        except Exception as e:
            logger.debug("[VECTOR][episodic] embedding backfill error: {}", e)

    def close(self):
        self.conn.close()
        logger.info("Episodic memory connection closed")

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding="utf-8")
    mem = EpisodicMemory()
    id1 = mem.store('test', 'VECTOR started for first time', ['init','test'])
    id2 = mem.store('task', 'Checked KIIT attendance', ['kiit','attendance'])
    results = mem.recall('KIIT')
    assert len(results) >= 1, 'recall failed'
    mem.remember('owner_name', 'Arghyadeep', 'identity', 1.0)
    fact = mem.recall_fact('owner_name')
    assert fact is not None, 'recall_fact failed'
    chain_id = mem.store_chain('exam tomorrow', ['study'], ['opened notes','read chapter'], 'set reminder', 'reminder set', 0.9)
    training = mem.get_training_data()
    assert len(training) >= 1, 'training data failed'
    stats = mem.get_stats()
    mem.close()
    print(f"âœ… episodic.py OK — {stats}")
