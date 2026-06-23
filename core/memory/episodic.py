from core.memory.db_utils import apply_pragmas
import sys

__all__ = [
    "EpisodicMemory",
    "MemoryDatabaseUnavailable",
    "close_db_connection",
    "diagnose_memory_db",
    "get_db_connection",
    "get_db_write_lock",
    "get_temp_cursor",
    "repair_unreadable_memory_db",
]

from core.config import CONFIG
from core.resilience.circuit_breaker import CircuitBreakerOpenError
from core.breaker_registry import get_registry
from loguru import logger
import asyncio, uuid, json, os, sqlite3, datetime, threading, shutil
from contextlib import contextmanager
from pathlib import Path

# Try SQLCipher for AES-256 encryption; fall back to plain sqlite3
# Supports sqlcipher3 (preferred on Python 3.13+) and pysqlcipher3.
try:
    import sqlcipher3 as sqlcipher
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
        logger.warning("[VECTOR][memory] SQLCipher not available — using plain SQLite (install sqlcipher3 to encrypt)")

_DB_KEY = None  # resolved lazily below
_MIGRATABLE_TABLES = (
    "episodic_memory",
    "semantic_memory",
    "policy_memory",
    "reasoning_chains",
    "skill_memory",
    "agent_history",
    "episodic_embeddings",
)
_SQLITE_HEADER = b"SQLite format 3\x00"


class MemoryDatabaseUnavailable(RuntimeError):
    """Raised when the local memory DB cannot be opened safely."""


def _looks_like_plain_sqlite(path: str) -> bool:
    try:
        with open(path, "rb") as handle:
            return handle.read(len(_SQLITE_HEADER)) == _SQLITE_HEADER
    except OSError:
        return False


def _unreadable_db_backup_path(path: str) -> str:
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{path}.unreadable.bak.{stamp}"


def _unavailable_message(path: str) -> str:
    return (
        f"[VECTOR][memory] Local SQLCipher memory DB is unreadable: {path}. "
        "The file appears encrypted or corrupted and cannot be opened with the current DB key. "
        "If this DB has memories you need, restore the original VECTOR_DB_KEY/keyring entry. "
        "To start fresh without deleting the old file, run: python run_vector.py memory-repair"
    )

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
    # Priority 2: validated config loaded from .env. Pydantic Settings reads
    # .env without mutating os.environ, so checking os.environ alone misses it.
    key = str(CONFIG.get("db_key") or "")
    if key:
        _DB_KEY = key
        return _DB_KEY
    # Priority 3: OS keyring
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


def _sql_literal(value: str) -> str:
    """Return a single-quoted SQL literal for SQLCipher PRAGMA statements."""
    return "'" + value.replace("'", "''") + "'"


def _backup_path(path) -> str:
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{path}.plaintext.bak.{stamp}"


def _copy_plaintext_rows(plain_path: str, encrypted_conn) -> None:
    plain_conn = sqlite3.connect(plain_path, check_same_thread=False)
    try:
        existing = {
            row[0]
            for row in plain_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        for table in _MIGRATABLE_TABLES:
            if table not in existing:
                continue
            columns = [row[1] for row in plain_conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
            if not columns:
                continue
            quoted_cols = ", ".join(f'"{col}"' for col in columns)
            placeholders = ", ".join("?" for _ in columns)
            rows = plain_conn.execute(f'SELECT {quoted_cols} FROM "{table}"').fetchall()
            if rows:
                encrypted_conn.executemany(
                    f'INSERT OR IGNORE INTO "{table}" ({quoted_cols}) VALUES ({placeholders})',
                    rows,
                )
        encrypted_conn.execute("DELETE FROM episodic_memory_fts")
        encrypted_conn.execute(
            """
            INSERT INTO episodic_memory_fts
            (id, event_type, content, tags, source, timestamp, context_snapshot)
            SELECT id, event_type, content, tags, source, timestamp, context_snapshot
            FROM episodic_memory
            """
        )
        encrypted_conn.commit()
    finally:
        plain_conn.close()


def _open_sqlcipher_connection(path: str):
    conn = sqlcipher.connect(path, check_same_thread=False)
    try:
        db_key = _get_db_key()
        conn.execute("PRAGMA key = " + _sql_literal(db_key))
        # Explicit, defensive: vector_memory.db was created under SQLCipher 4's
        # stock defaults (4096-byte pages). Without this, a HMAC-check failure
        # is possible if anything else in the same process changed the
        # PROCESS-WIDE `cipher_default_page_size` pragma before this connection
        # opened — confirmed real: core/research_engine/database/sqlcipher_utils.py
        # sets `PRAGMA cipher_default_page_size = 16384` globally for its own,
        # separate database. cipher_default_* pragmas are process-wide in
        # SQLCipher, not scoped to one connection, so importing research_engine
        # anywhere earlier in the same process silently broke this DB's HMAC
        # verification. Setting our own page size explicitly makes this
        # connection immune regardless of what else has run in the process.
        conn.execute("PRAGMA cipher_page_size = 4096")
        # busy_timeout: a second connection to this file (another VECTOR
        # process, accidental or a future multi-process deployment) waits up
        # to 5s for the lock instead of failing immediately. journal_mode=WAL
        # lets readers and a writer proceed concurrently. Neither pragma was
        # set before — Phase 0 of plans/wire-absorbed-repos-autonomy.md hit
        # exactly the hard-fail this is meant to soften (a leftover process
        # holding the file made every other process's open() raise instead
        # of just waiting).
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("SELECT count(*) FROM sqlite_master")
        return conn
    except Exception:
        conn.close()
        raise


def _migrate_plaintext_db_to_sqlcipher(path: str):
    backup = _backup_path(path)
    shutil.copy2(path, backup)
    os.replace(path, backup + ".active")
    active_backup = backup + ".active"
    logger.warning(
        "[VECTOR][memory] Migrating plaintext SQLite memory DB to SQLCipher; plaintext backup={}",
        active_backup,
    )
    conn = sqlcipher.connect(path, check_same_thread=False)
    try:
        db_key = _get_db_key()
        conn.execute("PRAGMA key = " + _sql_literal(db_key))
        _create_tables(conn)
        _copy_plaintext_rows(active_backup, conn)
        logger.info("[VECTOR][memory] SQLCipher migration completed")
        return conn
    except Exception:
        conn.close()
        if os.path.exists(path):
            os.remove(path)
        os.replace(active_backup, path)
        raise

# In-memory buffer for writes when circuit breaker is open.
# Bounded so a long circuit-open window cannot grow memory without limit
# (oldest cached writes are dropped first).
from collections import deque as _deque
_MEMORY_BUFFER_MAX = 10000
_memory_buffer: "_deque[dict]" = _deque(maxlen=_MEMORY_BUFFER_MAX)
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

    # Episodic memory operations are synchronous SQLite calls. Running them
    # through asyncio.run(cb.call(...)) creates a fresh Windows socketpair per
    # memory operation, which exhausts buffers in large test runs. Use the
    # synchronous breaker path consistently and keep async CBs for async work.
    return _run_sync_with_cb()

# Singleton database connection with thread-safe access
_db_connection = None
_db_lock = threading.Lock()
# Serializes operations on the shared single SQLite connection. A reentrant
# lock so nested cursor use within one thread does not deadlock. Prevents
# concurrent threads racing the shared connection ("database is locked",
# cross-thread cursor corruption).
_write_lock = threading.RLock()


def _memory_db_path() -> str:
    """Resolve the memory DB path with a safe fallback for partial configs."""
    from core.memory.db_utils import configured_db_path

    path = configured_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def _is_connection_closed(conn) -> bool:
    try:
        conn.execute("SELECT 1")
        return False
    except Exception as e:
        # sqlcipher3's ProgrammingError is NOT a subclass of sqlite3's — match
        # by name, or a closed singleton is reported healthy forever and every
        # memory op fails until process restart.
        if type(e).__name__ == "ProgrammingError":
            return "closed" in str(e).lower()
        return False


def close_db_connection() -> None:
    """Intentional shutdown of the singleton: close, clear, and reset the
    episodic circuit breaker so a later get_db_connection() starts clean
    (an intentional close is not a failure)."""
    global _db_connection
    with _db_lock:
        if _db_connection is not None:
            try:
                _db_connection.close()
            except Exception:
                logger.warning("[VECTOR] silent swallow")
                pass
            _db_connection = None
    try:
        from core.resilience.circuit_breaker import CircuitState
        cb = get_registry().get("episodic_memory")
        if cb is not None:
            cb.state = CircuitState.CLOSED
            cb.failure_count = 0
    except Exception:
        logger.warning("[VECTOR] silent swallow")
        pass


def get_db_write_lock() -> threading.RLock:
    """Expose the shared DB write lock for modules that reuse the singleton."""
    return _write_lock


def diagnose_memory_db() -> dict:
    """Return a safe diagnostic summary for the local memory database.

    Does not expose the encryption key. Used by production checks and repair
    commands so failures are actionable instead of surfacing as generic SQLite
    errors.
    """
    db_path = _memory_db_path()
    report = {
        "path": db_path,
        "exists": os.path.exists(db_path),
        "sqlcipher": _USE_SQLCIPHER,
        "plain_sqlite_header": False,
        "can_open": False,
        "status": "missing",
        "detail": "",
    }
    if not report["exists"]:
        report["detail"] = "Database file does not exist yet; startup will create it."
        return report
    report["plain_sqlite_header"] = _looks_like_plain_sqlite(db_path)
    try:
        conn = _open_sqlcipher_connection(db_path) if _USE_SQLCIPHER else sqlite3.connect(db_path, check_same_thread=False)
        try:
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        finally:
            conn.close()
        report["can_open"] = True
        report["status"] = "ok"
        report["detail"] = "Database opens with the current configuration."
    except Exception as exc:
        if _USE_SQLCIPHER and not report["plain_sqlite_header"]:
            report["status"] = "key_mismatch_or_corrupt"
            report["detail"] = _unavailable_message(db_path)
        elif report["plain_sqlite_header"]:
            report["status"] = "plaintext_migration_needed"
            report["detail"] = "Plain SQLite memory DB found; startup can migrate it to SQLCipher."
        else:
            report["status"] = "unreadable"
            report["detail"] = f"Database could not be opened: {type(exc).__name__}"
    return report


def repair_unreadable_memory_db() -> dict:
    """Quarantine an unreadable encrypted memory DB and create a fresh one."""
    global _db_connection
    db_path = _memory_db_path()
    before = diagnose_memory_db()
    if before.get("can_open"):
        return {"status": "ok", "detail": "Memory DB already opens.", "path": db_path}
    if not os.path.exists(db_path):
        get_db_connection()
        return {"status": "created", "detail": "Memory DB created.", "path": db_path}
    if before.get("plain_sqlite_header"):
        get_db_connection()
        return {"status": "migrated", "detail": "Plain SQLite DB migrated to SQLCipher.", "path": db_path}

    backup = _unreadable_db_backup_path(db_path)
    close_db_connection()
    with _db_lock:
        _db_connection = None
        os.replace(db_path, backup)
    try:
        get_db_connection()
    except Exception:
        if os.path.exists(db_path):
            os.remove(db_path)
        os.replace(backup, db_path)
        raise
    return {
        "status": "recreated",
        "path": db_path,
        "backup": backup,
        "detail": "Unreadable memory DB was moved aside and a fresh encrypted DB was created.",
    }


def get_db_connection():
    """Get or create singleton DB connection with thread-safe initialization."""
    global _db_connection
    with _db_lock:
        if _db_connection is not None and _is_connection_closed(_db_connection):
            logger.warning("[VECTOR][memory] Episodic DB connection was closed; reopening")
            _db_connection = None
        if _db_connection is None:
            if _USE_SQLCIPHER:
                db_path = _memory_db_path()
                try:
                    _db_connection = _open_sqlcipher_connection(db_path)
                except Exception as exc:
                    if os.path.exists(db_path):
                        if not _looks_like_plain_sqlite(db_path):
                            raise MemoryDatabaseUnavailable(_unavailable_message(db_path)) from exc
                        try:
                            plain_conn = sqlite3.connect(db_path, check_same_thread=False)
                            plain_conn.execute("SELECT count(*) FROM sqlite_master")
                            plain_conn.close()
                            _db_connection = _migrate_plaintext_db_to_sqlcipher(db_path)
                        except Exception as exc:
                            logger.error("[VECTOR][memory] SQLCipher migration failed: {}", exc)
                            raise
                    else:
                        raise
            else:
                _db_connection = sqlite3.connect(_memory_db_path(), check_same_thread=False)
            apply_pragmas(_db_connection)
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
    """Context manager for temporary cursor with automatic cleanup.

    Holds _write_lock for the whole operation so concurrent threads serialize
    on the shared single SQLite connection instead of racing it.
    """
    conn = get_db_connection()
    with _write_lock:
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
        self._semantic_fallback: dict[str, dict] = {}
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

    # Event types that must never be force-forgotten by decay (raw provenance
    # that summaries can't fully reconstruct). Ghost memory lives in
    # agent_history, not here, so it is unaffected regardless.
    _PROTECTED_EVENT_TYPES = frozenset({"council", "consolidation", "ghost", "death"})

    def prune_old_episodes(
        self,
        retention_days: int = 90,
        protect_event_types: "set[str] | None" = None,
    ) -> int:
        """Forget raw episodes older than ``retention_days``.

        Decay/forgetting (roadmap #7): once ConsolidationBot has summarized old
        episodes into semantic_memory + mem0, the raw rows are redundant and
        otherwise grow the DB unbounded in 24/7 operation. Deletes from all
        three backing stores (episodic_memory, the FTS index, embeddings) in one
        transaction. Protected event types are kept. Returns rows deleted.
        """
        if retention_days <= 0:
            return 0
        try:
            from core.memory import tiering as _tiering
            protected = set(_tiering.protected_event_types())
        except Exception:
            protected = set(self._PROTECTED_EVENT_TYPES)
        if protect_event_types:
            protected |= set(protect_event_types)
        cutoff = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=retention_days)
        ).isoformat()  # ISO-8601 sorts lexicographically → safe string compare

        def _do_prune() -> int:
            with get_temp_cursor() as cursor:
                if protected:
                    placeholders = ",".join("?" for _ in protected)
                    sel = (
                        "SELECT id FROM episodic_memory "
                        f"WHERE timestamp < ? AND event_type NOT IN ({placeholders})"
                    )
                    cursor.execute(sel, (cutoff, *protected))
                else:
                    cursor.execute(
                        "SELECT id FROM episodic_memory WHERE timestamp < ?", (cutoff,)
                    )
                ids = [r[0] for r in cursor.fetchall()]
                if not ids:
                    return 0
                qs = ",".join("?" for _ in ids)
                cursor.execute(f"DELETE FROM episodic_memory WHERE id IN ({qs})", ids)
                cursor.execute(f"DELETE FROM episodic_memory_fts WHERE id IN ({qs})", ids)
                cursor.execute(f"DELETE FROM episodic_embeddings WHERE id IN ({qs})", ids)
                return len(ids)

        try:
            deleted = _with_cb(_do_prune)
            if deleted:
                logger.info(
                    f"[VECTOR][episodic] forgot {deleted} episodes older than "
                    f"{retention_days}d (protected: {sorted(protected)})"
                )
            return deleted
        except Exception as e:
            logger.error(f"[VECTOR][episodic] prune_old_episodes failed: {e}")
            return 0

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
        updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._semantic_fallback[key] = {
            "key": key,
            "value": value,
            "category": category,
            "confidence": confidence,
            "updated_at": updated_at,
        }
        try:
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
            logger.warning("[VECTOR][episodic] circuit open — semantic fact cached in memory: {}", key)
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
            return self._semantic_fallback.get(key)
        except Exception as e:
            logger.error(f"Recall fact failed: {e}")
            return self._semantic_fallback.get(key)
    
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
            except Exception as e:
                # FTS is a best-effort recall booster; semantic scores still
                # carry the search. Log so silent FTS rot is visible.
                logger.debug(f"[VECTOR][episodic] FTS hybrid lookup skipped: {e}")

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
    print(f"✅ episodic.py OK — {stats}")
