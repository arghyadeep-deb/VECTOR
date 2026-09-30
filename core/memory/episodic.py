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

# 2026-07-21: stopword list for recall()'s LIKE fallback — kept local to
# this module (rather than importing core.city.governor's copy) to avoid a
# core.memory <-> core.city circular import.
_RECALL_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "and", "or", "but", "not", "no", "yes", "of", "to", "in", "on", "at",
    "for", "with", "about", "what", "what's", "whats", "when", "where",
    "who", "whom", "whose", "why", "how", "which", "this", "that", "these",
    "those", "my", "your", "his", "her", "its", "our", "their", "me", "you",
    "him", "them", "us", "i", "he", "she", "it", "we", "they", "do", "does",
    "did", "can", "could", "will", "would", "shall", "should", "may",
    "might", "must", "have", "has", "had", "please", "tell", "let", "know",
    "just", "also", "some", "any", "all", "there", "here", "so", "if",
    "then", "than", "as", "by", "from", "up", "out", "into", "over",
})

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
    # Episodic memory operations are synchronous SQLite calls and always run
    # through the synchronous breaker path below (see the note before the return),
    # so there is no need to inspect the running event loop here. The previous
    # asyncio.get_event_loop() probe was dead code (its result was never read) and
    # used a deprecated API — removed.
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
    global _db_connection, _DB_KEY
    with _db_lock:
        if _db_connection is not None:
            try:
                _db_connection.close()
            except Exception as e:
                logger.warning(f"[VECTOR][episodic] singleton close failed: {e}")
            _db_connection = None
        # The resolved key is part of the singleton's identity, not just an
        # input to opening it once: _get_db_key() caches its result in
        # _DB_KEY and returns early on every later call, so it never re-reads
        # VECTOR_DB_KEY/CONFIG/keyring after the first resolution in this
        # process. If we clear _db_connection without also clearing _DB_KEY,
        # the next get_db_connection() opens a fresh connection but keys it
        # with a STALE key — e.g. a test that monkeypatches VECTOR_DB_KEY for
        # isolation, closes the connection at teardown, and lets monkeypatch
        # restore the real env var: the next connection (real production
        # vector_memory.db) would still be opened with the test's key and
        # fail with "hmac check failed" / "file is not a database". Clearing
        # both together inside the same lock keeps the pair in lockstep.
        _DB_KEY = None
    try:
        from core.resilience.circuit_breaker import CircuitState
        cb = get_registry().get("episodic_memory")
        if cb is not None:
            cb.state = CircuitState.CLOSED
            cb.failure_count = 0
    except Exception as e:
        logger.warning(f"[VECTOR][episodic] circuit breaker reset failed: {e}")
    try:
        # Resets the MemoryTree singleton in lockstep with the SQL singleton
        # so the next store() picks up whatever VECTOR_DB_PATH/
        # VECTOR_MEMORY_TREE_PATH is active — this is what makes the
        # existing isolated_db test fixture isolate MemoryTree too, with no
        # test-file edits required.
        from core.engine.memory_tree.tree_builder import close_shared_tree
        close_shared_tree()
    except Exception as e:
        logger.warning(f"[VECTOR][episodic] memory tree reset failed: {e}")


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
        # 2026-07-29: per-session rolling conversational buffer (core.memory.
        # session_buffer) — short-lived turn-by-turn recency, deliberately
        # NOT routed through the decay/tiering system: it's capped by row
        # count per session (rolling window), not Ebbinghaus stability, and
        # is never treated as durable long-term memory.
        """CREATE TABLE IF NOT EXISTS session_turns (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )""",
        """CREATE INDEX IF NOT EXISTS idx_session_turns_session
           ON session_turns(session_id, timestamp)""",
    ]
    for table in tables:
        try:
            conn.execute(table)
        except sqlite3.OperationalError as e:
            logger.error(f"Table creation failed: {e}")
    _ensure_decay_columns(conn)
    _ensure_policy_columns(conn)


# Task 89 (D3, suppression/reward channel separation): policy_memory needs a
# veto_count column so a counterfactual-veto's suppression event can be
# recorded WITHOUT being blended into avg_reward — the cumulative mean real
# outcomes (5-factor reward, VectorCode reward) accumulate into. Historical
# rows (including the ~29,000-sample analyze_progress row) are untouched:
# ALTER TABLE ADD COLUMN only adds the column with existing rows getting
# veto_count=NULL, never rewriting avg_reward/sample_count/situation_hash on
# any existing row. See core/memory/policy.py::PolicyMemory.record_suppression().
def _ensure_policy_columns(conn) -> None:
    try:
        cols = {row[1] for row in conn.execute('PRAGMA table_info("policy_memory")').fetchall()}
    except sqlite3.OperationalError:
        return  # table doesn't exist yet on this connection — next create_tables pass adds it
    if not cols:
        return
    if "veto_count" not in cols:
        try:
            conn.execute('ALTER TABLE "policy_memory" ADD COLUMN veto_count INTEGER DEFAULT 0')
        except sqlite3.OperationalError as e:
            logger.warning(f"[VECTOR][memory] could not add veto_count to policy_memory: {e}")


# 2026-07-29: Ebbinghaus decay (core.memory.decay) needs two extra columns on
# each bulk table it manages — stability_days (S) and last_touch (resets on
# genuine recall, not just at write time). SQLite has no "ADD COLUMN IF NOT
# EXISTS", so check PRAGMA table_info first; safe to call on every startup.
_DECAY_TABLES = ("episodic_memory", "reasoning_chains")


def _ensure_decay_columns(conn) -> None:
    for table in _DECAY_TABLES:
        try:
            cols = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}
        except sqlite3.OperationalError:
            continue  # table doesn't exist yet on this connection — fine, next create_tables pass adds columns too
        if not cols:
            continue
        if "stability_days" not in cols:
            try:
                conn.execute(f'ALTER TABLE "{table}" ADD COLUMN stability_days REAL')
            except sqlite3.OperationalError as e:
                logger.warning(f"[VECTOR][memory] could not add stability_days to {table}: {e}")
        if "last_touch" not in cols:
            try:
                conn.execute(f'ALTER TABLE "{table}" ADD COLUMN last_touch TEXT')
            except sqlite3.OperationalError as e:
                logger.warning(f"[VECTOR][memory] could not add last_touch to {table}: {e}")


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


# Above this many rows, rebuild the FTS index in one pass instead of deleting
# row-by-row. Standalone FTS5 `DELETE ... WHERE id IN (...)` is O(index-size)
# per statement, so a large prune that way is pathologically slow (a 186k-row
# cleanup never finished inside a 10-min window); an INSERT…SELECT rebuild of
# the remaining rows is O(remaining) and finishes in seconds.
_FTS_REBUILD_THRESHOLD = 20000

# Column order shared by episodic_memory and episodic_memory_fts (the FTS table
# lists them in a different order, so the rebuild names them explicitly).
_EPISODIC_COLS = "id, event_type, content, tags, source, timestamp, context_snapshot"


def _delete_episodes_by_ids(cursor, ids: list) -> int:
    """Delete the given episode ids from all three backing stores
    (episodic_memory, episodic_embeddings, episodic_memory_fts), keeping them in
    lockstep. Chunks base-table deletes to stay under SQLite's bound-variable
    limit, and rebuilds the FTS index in one pass when the batch is large.
    Caller is responsible for the surrounding transaction/commit.
    """
    if not ids:
        return 0
    CHUNK = 500
    for i in range(0, len(ids), CHUNK):
        batch = ids[i:i + CHUNK]
        qs = ",".join("?" for _ in batch)
        cursor.execute(f"DELETE FROM episodic_memory WHERE id IN ({qs})", batch)
        cursor.execute(f"DELETE FROM episodic_embeddings WHERE id IN ({qs})", batch)
    if len(ids) >= _FTS_REBUILD_THRESHOLD:
        # Rebuild FTS from the (already-pruned) base table — far faster than
        # row-by-row deletion for large batches. NOTE: a plain
        # `DELETE FROM <fts5>` does NOT free the index — FTS5 appends tombstone
        # markers, so the index keeps growing. DROP + CREATE physically removes
        # the shadow tables, giving a genuinely fresh, compact index. We read the
        # live CREATE statement so this stays correct if the schema ever changes.
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE name='episodic_memory_fts' AND type='table'"
        )
        row = cursor.fetchone()
        create_sql = row[0] if row else None
        if create_sql:
            cursor.execute("DROP TABLE episodic_memory_fts")
            cursor.execute(create_sql)
            cursor.execute(
                f"INSERT INTO episodic_memory_fts ({_EPISODIC_COLS}) "
                f"SELECT {_EPISODIC_COLS} FROM episodic_memory"
            )
        else:  # schema not found — fall back to per-row delete
            CHUNK = 500
            for i in range(0, len(ids), CHUNK):
                batch = ids[i:i + CHUNK]
                qs = ",".join("?" for _ in batch)
                cursor.execute(f"DELETE FROM episodic_memory_fts WHERE id IN ({qs})", batch)
    else:
        for i in range(0, len(ids), CHUNK):
            batch = ids[i:i + CHUNK]
            qs = ",".join("?" for _ in batch)
            cursor.execute(f"DELETE FROM episodic_memory_fts WHERE id IN ({qs})", batch)
    return len(ids)


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

        # Ebbinghaus decay (core.memory.decay): every row starts with a
        # stability (S) appropriate to its event type — ephemeral telemetry
        # decays fast unless reinforced, everything else decays slower.
        # last_touch starts equal to timestamp and moves forward on genuine
        # recall (see recall()/search_semantic()).
        try:
            from core.memory import tiering as _tiering
            from core.memory.decay import initial_stability_days
            _is_ephemeral = event_type in _tiering.ephemeral_event_types()
            stability_days = initial_stability_days(_is_ephemeral)
        except Exception:
            stability_days = 30.0

        try:
            def _do_store():
                with get_temp_cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO episodic_memory
                        (id, event_type, content, tags, context_snapshot, timestamp, source, stability_days, last_touch)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (event_id, event_type, content, tags_json, context_json, timestamp, source, stability_days, timestamp))
                    cursor.execute("""
                        INSERT INTO episodic_memory_fts
                        (id, event_type, content, tags, source, timestamp, context_snapshot)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (event_id, event_type, content, tags_json or '', source, timestamp, context_json or ''))
            _with_cb(_do_store)

            try:
                from core.engine.memory_tree.tree_builder import get_shared_tree
                _tree = get_shared_tree()
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

    # Run VACUUM from prune only when at least this many rows were forgotten —
    # VACUUM rewrites the whole file, so it isn't worth it for a handful of rows.
    _VACUUM_ROW_THRESHOLD = 2000

    def prune_old_episodes(
        self,
        retention_days: int = 90,
        protect_event_types: "set[str] | None" = None,
        vacuum: "bool | None" = None,
    ) -> int:
        """Forget episodes whose Ebbinghaus retention has decayed below
        ``decay.EVICTION_THRESHOLD`` (core.memory.decay: R = e^(-t/S)).

        2026-07-29: replaced the previous fixed-calendar-day cliff. Owner's
        framing: "when decay ≈ 0 we can evict that data — not based on a
        fixed N days." A row's clock (``last_touch``) resets and its
        stability (``stability_days``, S) grows every time it's genuinely
        recalled (see ``_touch_episodes``/``recall()``/``search_semantic()``),
        so a frequently-reused row can legitimately outlive
        ``retention_days`` — only truly-forgotten rows (never revisited) get
        pruned on schedule.

        ``retention_days`` is kept for backward compatibility with existing
        callers (ConsolidationBot, db_maintenance.py, tests): it still gates
        the initial SQL candidate scan (by original ``timestamp``, a cheap
        over-inclusive net — a row can only be evicted by the decay check
        below, never purely by this scan) and still supplies the bulk-tier
        fallback stability (retention_days/3, so R hits the eviction
        threshold at roughly the same day retention_days used to be a hard
        cutoff) for legacy rows written before this migration that have no
        stored ``stability_days``. ``retention_days<=0`` remains a no-op, as
        before.

        Deletes from all three backing stores (episodic_memory, the FTS
        index, embeddings). Protected event types are kept forever
        regardless of decay. Returns rows deleted.

        ``vacuum`` reclaims freed pages back to the OS (plain ``VACUUM`` —
        SQLCipher-safe, unlike ``VACUUM INTO`` which writes a plaintext
        copy). Default (None) → auto-VACUUM only when ≥
        ``_VACUUM_ROW_THRESHOLD`` rows were forgotten.
        """
        if retention_days <= 0:
            return 0
        from core.memory.decay import should_evict, DEFAULT_STABILITY_DAYS
        try:
            from core.memory import tiering as _tiering
            protected = set(_tiering.protected_event_types())
            ephemeral = set(_tiering.ephemeral_event_types()) - protected
            ephemeral_stability = float(getattr(_tiering, "EPHEMERAL_STABILITY_DAYS", 5.0))
        except Exception:
            protected = set(self._PROTECTED_EVENT_TYPES)
            ephemeral = set()
            ephemeral_stability = 5.0
        if protect_event_types:
            protected |= set(protect_event_types)
            ephemeral -= set(protect_event_types)
        bulk_fallback_stability = max(retention_days / 3.0, 1.0)

        now = datetime.datetime.now(datetime.timezone.utc)
        # ISO-8601 sorts lexicographically -> safe string compare. This is a
        # cheap, deliberately over-inclusive candidate net — it only needs to
        # NOT exclude anything the decay check below would evict, not to
        # decide eviction itself. Everything younger than this can't have
        # decayed below threshold under any stability this module assigns,
        # so skipping it is safe and keeps the scan cheap on a large table.
        candidate_cutoff = (now - datetime.timedelta(days=retention_days)).isoformat()

        def _elapsed_days(last_touch: str | None, timestamp: str) -> float:
            ref = last_touch or timestamp
            try:
                ref_dt = datetime.datetime.fromisoformat(ref)
                if ref_dt.tzinfo is None:
                    ref_dt = ref_dt.replace(tzinfo=datetime.timezone.utc)
                return (now - ref_dt).total_seconds() / 86400.0
            except Exception:
                return float(retention_days) + 1.0  # unparsable -> treat as stale, evict

        def _do_prune() -> int:
            with get_temp_cursor() as cursor:
                skip = protected
                ph = ",".join("?" for _ in skip) if skip else ""
                where_skip = f"AND event_type NOT IN ({ph})" if skip else ""
                cursor.execute(
                    "SELECT id, event_type, timestamp, last_touch, stability_days "
                    f"FROM episodic_memory WHERE timestamp < ? {where_skip}",
                    (candidate_cutoff, *skip),
                )
                rows = cursor.fetchall()

                ids: list[str] = []
                for eid, event_type, timestamp, last_touch, stability_days in rows:
                    if stability_days is None:
                        stability_days = (
                            ephemeral_stability if event_type in ephemeral
                            else bulk_fallback_stability
                        )
                    elapsed = _elapsed_days(last_touch, timestamp)
                    if should_evict(elapsed, stability_days):
                        ids.append(eid)

                if not ids:
                    return 0
                # Shared helper: chunks base deletes under the bound-variable
                # limit and rebuilds FTS in one pass for large batches.
                return _delete_episodes_by_ids(cursor, ids)

        try:
            deleted = _with_cb(_do_prune)
            if deleted:
                logger.info(
                    f"[VECTOR][episodic] forgot {deleted} episodes "
                    f"(Ebbinghaus decay, candidate scan>{retention_days}d; "
                    f"protected: {sorted(protected)})"
                )
                should_vacuum = vacuum if vacuum is not None else (deleted >= self._VACUUM_ROW_THRESHOLD)
                if should_vacuum:
                    self.vacuum()
            return deleted
        except Exception as e:
            logger.error(f"[VECTOR][episodic] prune_old_episodes failed: {e}")
            return 0

    def vacuum(self) -> bool:
        """Reclaim freed pages back to the OS after large deletes.

        Plain ``VACUUM`` preserves SQLCipher encryption (the page cipher is
        reapplied as the file is rewritten); ``VACUUM INTO`` does NOT — it emits
        a plaintext copy, so it must never be used here. VACUUM cannot run inside
        a transaction, so we commit and drop to autocommit first. Rewrites the
        whole file (needs transient free disk ≈ DB size); cheap once the DB is
        small.
        """
        try:
            conn = get_db_connection()
            try:
                conn.commit()
            except Exception:
                pass
            old_iso = getattr(conn, "isolation_level", None)
            try:
                conn.isolation_level = None  # autocommit — VACUUM can't be in a txn
            except Exception:
                pass
            try:
                conn.execute("VACUUM")
            finally:
                try:
                    conn.isolation_level = old_iso
                except Exception:
                    pass
            logger.info("[VECTOR][episodic] VACUUM complete — freed pages returned to OS")
            return True
        except Exception as e:
            logger.warning(f"[VECTOR][episodic] VACUUM skipped: {e}")
            return False

    def _touch_episodes(self, ids: list[str]) -> None:
        """Reinforce genuinely-recalled rows (Ebbinghaus decay, core.memory.decay):
        reset last_touch=now and grow stability_days multiplicatively, so
        memories that keep getting reused decay slower and can outlive a
        fixed-day cutoff, while unused ones fade on schedule. Best-effort —
        never lets a reinforcement failure break the caller's actual recall."""
        if not ids:
            return
        try:
            from core.memory.decay import reinforce
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            with get_temp_cursor() as cursor:
                qs = ",".join("?" for _ in ids)
                cursor.execute(
                    f"SELECT id, stability_days FROM episodic_memory WHERE id IN ({qs})",
                    ids,
                )
                current = {r[0]: r[1] for r in cursor.fetchall()}
                for eid in ids:
                    new_stability = reinforce(current.get(eid))
                    cursor.execute(
                        "UPDATE episodic_memory SET stability_days = ?, last_touch = ? WHERE id = ?",
                        (new_stability, now, eid),
                    )
        except Exception as e:
            logger.debug(f"[VECTOR][episodic] reinforcement touch skipped: {e}")

    def recall(self, query, limit=5, event_type=None) -> list[dict]:
        try:
            def _do_recall():
                with get_temp_cursor() as cursor:
                    rows = []
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
                        rows = []
                    if not rows:
                        # 2026-07-21: fall through to a LIKE-based search
                        # whenever FTS5 either errors out (bad query syntax)
                        # OR simply returns zero rows — which happens for
                        # basically any natural-language question, since FTS5
                        # bareword MATCH implicitly ANDs every token,
                        # including stopwords the stored content never
                        # contains. This used to LIKE-match the *entire*
                        # query string as one substring (f"%{query}%"). For
                        # any natural-language question ("What is my cat's
                        # name...") that requires the stored content to
                        # contain that exact phrase verbatim, in that exact
                        # word order — which it essentially never does, since
                        # the fact was stored in different words. Confirmed
                        # via a write-then-read memory test that came back
                        # completely empty even after content was persisted
                        # successfully. Fixed by requiring each significant
                        # word to independently appear (AND of per-word LIKEs)
                        # instead of the whole string as one substring.
                        #
                        # 2026-07-21 (round 2): the first version of this fix
                        # still required EVERY word from the raw question —
                        # including question words like "what"/"and"/"what's"
                        # that never appear in the stored content — to match
                        # (AND across all words), so it still returned zero
                        # rows. Fixed by (a) stripping common English
                        # stopwords/question words before building the LIKE
                        # clauses, same idea as governor._extract_keywords but
                        # duplicated here to avoid a core.city <-> core.memory
                        # circular import, and (b) matching if enough of the
                        # remaining significant words hit rather than
                        # requiring literally all of them.
                        import re as _re
                        _stop = _RECALL_STOPWORDS
                        raw_words = _re.findall(r"[A-Za-z0-9']+", query)
                        words = [w for w in raw_words if len(w) > 2 and w.lower() not in _stop]
                        if not words:
                            words = [w for w in raw_words if len(w) > 2]
                        if not words:
                            words = [query] if query.strip() else []
                        if words:
                            # require at least half (rounded up) of the
                            # significant words to appear, not literally all —
                            # tolerates paraphrase/word-order differences.
                            need = max(1, (len(words) + 1) // 2)
                            case_clauses = " + ".join(
                                "(CASE WHEN content LIKE ? THEN 1 ELSE 0 END)" for _ in words
                            )
                            clauses = f"({case_clauses}) >= ?"
                            params = [f"%{w}%" for w in words] + [need]
                        else:
                            clauses = "1=1"
                            params = []
                        if event_type:
                            cursor.execute(
                                f"""SELECT id, event_type, content, tags, context_snapshot, timestamp, source
                                FROM episodic_memory WHERE {clauses} AND event_type = ?
                                ORDER BY timestamp DESC LIMIT ?""",
                                (*params, event_type, limit),
                            )
                        else:
                            cursor.execute(
                                f"""SELECT id, event_type, content, tags, context_snapshot, timestamp, source
                                FROM episodic_memory WHERE {clauses}
                                ORDER BY timestamp DESC LIMIT ?""",
                                (*params, limit),
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
            self._touch_episodes([r["id"] for r in result])
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
            # Ebbinghaus decay: reasoning_chains is a bulk table (not in
            # tiering.CRITICAL_TABLES), so it starts at the standard bulk
            # stability and decays like episodic_memory unless reinforced by
            # inject_past_reasoning() actually reusing it.
            try:
                from core.memory import tiering as _tiering
                stability_days = _tiering.BULK_STABILITY_DAYS
            except Exception:
                stability_days = 30.0
            def _do():
                with get_temp_cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO reasoning_chains
                        (chain_id, situation, goal_ids, steps, action_taken, outcome, reward, is_training_data, timestamp, stability_days, last_touch)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (chain_id, situation, goal_ids_json, steps_json, action, outcome, reward, is_training, timestamp, stability_days, timestamp))
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
            self._touch_episodes([r["id"] for r in results])
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
    import tempfile

    sys.stdout.reconfigure(encoding="utf-8")

    # P0-B remediation (M1c/M1d, 2026-09-09): this self-test used to
    # construct a real EpisodicMemory() with no isolation at all -- not even
    # a broken guard -- and its store()/remember()/store_chain() calls below
    # ran for real: overwriting the real "owner_name" semantic-memory fact
    # with a hardcoded value, inserting a fabricated "Checked KIIT
    # attendance" episodic row, and writing fabricated content into
    # `reasoning_chains` -- one of the five memory tables
    # .claude/rules/memory.md documents as becoming REAL LLM training data
    # and marks "never touch". See
    # VECTOR_TECHNICAL_KNOWLEDGE/M1c_DEVELOPMENT_TEST_ISOLATION_SAFETY_AUDIT.md
    # (finding P0-B) for the full history.
    #
    # This self-test still needs a REAL EpisodicMemory instance (it exists
    # to test this module's own logic, so mocking would defeat its purpose)
    # -- but now against an explicit, disposable temp DB, following the same
    # unconditional-override + hard-assert-before-construction pattern
    # established in core/brain/goal_system.py's own P0 fix (a conditional
    # "if not already set" guard is NOT safe here: core.config's
    # module-level dotenv load, triggered by the `from core.config import
    # CONFIG` at the top of this file, already sets os.environ
    # ["VECTOR_DB_PATH"] from .env's real production default before this
    # block ever runs).
    _tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    _tmp_db.close()
    os.environ["VECTOR_DB_PATH"] = _tmp_db.name
    os.environ["VECTOR_DB_KEY"] = "self-test-only-key-not-for-production"

    from core.memory.db_utils import configured_db_path
    assert str(configured_db_path()) == _tmp_db.name, (
        "isolation override did not take effect -- refusing to construct "
        "EpisodicMemory() against a possibly-real DB path"
    )

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
