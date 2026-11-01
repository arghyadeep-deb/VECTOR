"""
V.E.C.T.O.R. PersonModel.
Gap 7: Theory of mind per person — tracks beliefs, preferences, and communication style
for every person VECTOR interacts with, enabling personalised responses.

Encryption (owner-decision backlog OD-19, 2026-10-07): this file stores real
third-party PII (name, email, relationship_type, trust_score, free-text
beliefs/preferences/interaction summaries) for every real person VECTOR
interacts with -- it was previously a plain, unencrypted sqlite3 database,
the only one of VECTOR's person-adjacent stores not protected the way the
main episodic/policy DB is. Now opens via SQLCipher (same AES-256 scheme,
same encryption key as core.memory.episodic, resolved through
core.security.secrets_manager's keyring-first lookup) when available, with
an automatic one-time migration of any pre-existing plaintext database.
The original plaintext file is NEVER deleted by the migration -- it is
renamed to a timestamped `.plaintext.bak.<timestamp>` sibling so the owner
can verify the migration and delete it manually once satisfied.
"""
from pathlib import Path

import json
import os
import shutil
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

import sqlite3
# SQLCipher: same AES-256 scheme and key as core.memory.episodic. Prefer
# sqlcipher3 (Python 3.13+); fall back to the legacy pysqlcipher3 package;
# fall back further to plain sqlite3 with a loud warning if neither is
# installed, matching core.memory.episodic's own graceful-degradation
# policy rather than hard-failing VECTOR's startup over a missing package.
try:
    import sqlcipher3 as sqlcipher
    _USE_SQLCIPHER = True
except ImportError:
    try:
        from pysqlcipher3 import dbapi2 as sqlcipher  # legacy package
        _USE_SQLCIPHER = True
    except ImportError:
        sqlcipher = None
        _USE_SQLCIPHER = False
        logger.warning(
            "[VECTOR][person_model] SQLCipher not available -- real third-party "
            "PII (names, emails, relationship data) will be stored UNENCRYPTED. "
            "Install sqlcipher3 to encrypt."
        )

_PERSON_MODEL_TABLES = (
    "persons", "person_beliefs", "person_preferences", "person_interactions",
)

# Module-level singleton for the DEFAULT (no explicit db_path) connection --
# every one of PersonModel's 20+ production call sites (context_engine.py,
# core/api/routers/brain.py, core/avatar/avatar_core.py, etc.) constructs
# `PersonModel()` fresh on every call with no db_path, so opening a new
# SQLCipher connection (PBKDF2 key derivation) in __init__ every time made
# every one of those call sites pay that cost repeatedly -- live-measured
# as the dominant cost in voice-turn session hydration. Mirrors
# core.memory.episodic.get_db_connection()'s singleton pattern exactly. A
# caller that passes an explicit db_path (every PersonModel test does, for
# isolation) still gets its own independent connection, unaffected by this.
_person_model_connection = None
_person_model_conn_lock = threading.Lock()


def get_person_model_connection():
    """Get or create the singleton default-path PersonModel DB connection."""
    global _person_model_connection
    with _person_model_conn_lock:
        if _person_model_connection is None:
            from core.runtime_paths import data_path
            base = data_path()
            base.mkdir(parents=True, exist_ok=True)
            db_path = str(base / "person_models.db")
            _person_model_connection = _open_person_model_connection(db_path)
        return _person_model_connection


def _open_person_model_connection(db_path: str):
    if _USE_SQLCIPHER:
        if os.path.exists(db_path) and _looks_like_plaintext_sqlite(db_path):
            conn = _migrate_plaintext_person_db_to_sqlcipher(db_path)
        else:
            conn = _open_sqlcipher_connection(db_path)
        conn.row_factory = sqlcipher.Row
    else:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
    PersonModel._create_tables_on(conn)
    logger.info("[VECTOR][person_model] PersonModel DB connection established (sqlcipher={})", _USE_SQLCIPHER)
    return conn


def _sql_literal(value: str) -> str:
    """Single-quoted SQL literal for a SQLCipher PRAGMA statement."""
    return "'" + value.replace("'", "''") + "'"


def _get_db_key() -> str:
    """Resolve the same encryption key core.memory.episodic uses, so both
    stores are protected by one key the owner manages in one place."""
    from core.memory.episodic import _get_db_key as _episodic_get_db_key
    return _episodic_get_db_key()


def _looks_like_plaintext_sqlite(path: str) -> bool:
    """A plain SQLite file starts with the literal header "SQLite format 3".
    A SQLCipher-encrypted file does not (its header is ciphertext)."""
    try:
        with open(path, "rb") as f:
            return f.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _open_sqlcipher_connection(path: str):
    conn = sqlcipher.connect(path, check_same_thread=False)
    try:
        db_key = _get_db_key()
        conn.execute("PRAGMA key = " + _sql_literal(db_key))
        conn.execute("PRAGMA cipher_page_size = 4096")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("SELECT count(*) FROM sqlite_master")
        return conn
    except Exception:
        conn.close()
        raise


def _migrate_plaintext_person_db_to_sqlcipher(path: str):
    """One-time migration: rename the existing plaintext DB to a timestamped
    backup (never deleted), copy every row from its 4 tables into a fresh
    SQLCipher-encrypted file at the original path, and return the open
    encrypted connection. The backup is left in place for the owner to
    verify and delete manually -- this function never deletes real data."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    backup_path = f"{path}.plaintext.bak.{stamp}"
    shutil.copy2(path, backup_path)
    os.remove(path)
    logger.warning(
        "[VECTOR][person_model] Migrating plaintext person-model DB to SQLCipher; "
        "plaintext backup kept at {}", backup_path,
    )
    conn = sqlcipher.connect(path, check_same_thread=False)
    try:
        db_key = _get_db_key()
        conn.execute("PRAGMA key = " + _sql_literal(db_key))
        conn.execute("PRAGMA cipher_page_size = 4096")
        PersonModel._create_tables_on(conn)
        plain_conn = sqlite3.connect(backup_path, check_same_thread=False)
        try:
            existing = {
                row[0] for row in plain_conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            for table in _PERSON_MODEL_TABLES:
                if table not in existing:
                    continue
                columns = [
                    row[1] for row in plain_conn.execute(f'PRAGMA table_info("{table}")').fetchall()
                ]
                if not columns:
                    continue
                quoted_cols = ", ".join(f'"{c}"' for c in columns)
                placeholders = ", ".join("?" for _ in columns)
                rows = plain_conn.execute(f'SELECT {quoted_cols} FROM "{table}"').fetchall()
                if rows:
                    conn.executemany(
                        f'INSERT OR REPLACE INTO "{table}" ({quoted_cols}) VALUES ({placeholders})',
                        rows,
                    )
            conn.commit()
        finally:
            plain_conn.close()
        logger.info("[VECTOR][person_model] SQLCipher migration completed, backup={}", backup_path)
        return conn
    except Exception:
        conn.close()
        if os.path.exists(path):
            os.remove(path)
        shutil.copy2(backup_path, path)
        raise


class PersonModel:
    """
    Maintains a mental model for each person VECTOR interacts with.
    Persisted to SQLite. Supports belief/preference tracking, interaction
    history, trust scoring, and communication-style inference.
    """

    RELATIONSHIP_TYPES = {"owner", "colleague", "friend", "acquaintance", "unknown"}
    STYLE_KEYS = ("formality", "verbosity", "technicality", "directness")

    _db_lock = threading.Lock()

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default path -- share the one module-level connection every
            # default-constructed PersonModel() uses (see
            # get_person_model_connection() above) instead of paying a
            # fresh SQLCipher key-derivation cost per call site per call.
            # close() must not tear down a connection every other default
            # PersonModel() is also using -- only an explicit-db_path
            # instance owns (and may close) its connection.
            self._conn = get_person_model_connection()
            self._owns_conn = False
            from core.runtime_paths import data_path
            self._db_path = str(data_path() / "person_models.db")
            return

        self._db_path = db_path
        self._owns_conn = True

        if _USE_SQLCIPHER:
            if os.path.exists(db_path) and _looks_like_plaintext_sqlite(db_path):
                self._conn = _migrate_plaintext_person_db_to_sqlcipher(db_path)
            else:
                self._conn = _open_sqlcipher_connection(db_path)
            # sqlcipher3 is a separate module from stdlib sqlite3 -- its
            # Cursor type is NOT compatible with sqlite3.Row, so the row
            # factory must come from the same module as the connection.
            self._conn.row_factory = sqlcipher.Row
            self._create_tables()
        else:
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._create_tables()
        logger.info("[VECTOR][person_model] PersonModel initialized (sqlcipher={})", _USE_SQLCIPHER)

    def _create_tables(self):
        with self.__class__._db_lock:
            self.__class__._create_tables_on(self._conn)

    @staticmethod
    def _create_tables_on(conn) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS persons (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT DEFAULT '',
                relationship_type TEXT NOT NULL DEFAULT 'unknown',
                trust_score REAL NOT NULL DEFAULT 0.5,
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS person_beliefs (
                id TEXT PRIMARY KEY,
                person_id TEXT NOT NULL,
                topic TEXT NOT NULL,
                belief TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.5,
                updated_at TEXT NOT NULL,
                UNIQUE(person_id, topic) ON CONFLICT REPLACE
            );

            CREATE TABLE IF NOT EXISTS person_preferences (
                id TEXT PRIMARY KEY,
                person_id TEXT NOT NULL,
                pref_key TEXT NOT NULL,
                pref_value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(person_id, pref_key) ON CONFLICT REPLACE
            );

            CREATE TABLE IF NOT EXISTS person_interactions (
                id TEXT PRIMARY KEY,
                person_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                sentiment TEXT NOT NULL DEFAULT 'neutral',
                channel TEXT NOT NULL DEFAULT 'unknown',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_beliefs_person ON person_beliefs(person_id);
            CREATE INDEX IF NOT EXISTS idx_prefs_person ON person_preferences(person_id);
            CREATE INDEX IF NOT EXISTS idx_interactions_person ON person_interactions(person_id);
            CREATE INDEX IF NOT EXISTS idx_interactions_created ON person_interactions(created_at);
        """)
        conn.commit()

    # ── Person CRUD ──────────────────────────────────────────────────────────

    def add_person(
        self,
        person_id: str,
        name: str,
        relationship_type: str = "unknown",
        metadata: Optional[dict] = None,
        email: str = "",
    ) -> dict:
        if relationship_type not in self.RELATIONSHIP_TYPES:
            relationship_type = "unknown"
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self.__class__._db_lock:
                self._conn.execute(
                    """INSERT OR REPLACE INTO persons
                       (id, name, email, relationship_type, trust_score, metadata, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 0.5, ?, ?, ?)""",
                    (person_id, name, email, relationship_type, json.dumps(metadata or {}), now, now),
                )
                self._conn.commit()
        except Exception as e:
            logger.warning(f"[VECTOR][person_model] add_person failed: {e}")
        person = {"id": person_id, "name": name, "relationship_type": relationship_type,
                  "email": email, "trust_score": 0.5, "metadata": metadata or {}, "created_at": now}
        logger.info(f"[VECTOR][person_model] Person added: {name} ({relationship_type})")
        return person

    def get_model(self, person_id: str) -> Optional[dict]:
        try:
            row = self._conn.execute(
                "SELECT * FROM persons WHERE id=?", (person_id,)
            ).fetchone()
            if not row:
                return None
            model = dict(row)
            model["metadata"] = json.loads(model["metadata"])
            model["beliefs"] = self._get_beliefs(person_id)
            model["preferences"] = self._get_preferences(person_id)
            model["recent_interactions"] = self.get_interaction_history(person_id, limit=5)
            return model
        except Exception as e:
            logger.warning(f"[VECTOR][person_model] get_model failed: {e}")
            return None

    def get_all_persons(self) -> list[dict]:
        try:
            rows = self._conn.execute(
                "SELECT id, name, relationship_type, trust_score FROM persons ORDER BY name"
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"[VECTOR][person_model] get_all_persons failed: {e}")
            return []

    def person_exists(self, person_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM persons WHERE id=?", (person_id,)
        ).fetchone()
        return row is not None

    # ── Beliefs ──────────────────────────────────────────────────────────────

    def update_belief(
        self,
        person_id: str,
        topic: str,
        belief: str,
        confidence: float = 0.7,
    ) -> bool:
        if not self.person_exists(person_id):
            logger.warning(f"[VECTOR][person_model] update_belief: unknown person {person_id}")
            return False
        confidence = max(0.0, min(1.0, confidence))
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self.__class__._db_lock:
                self._conn.execute(
                    """INSERT OR REPLACE INTO person_beliefs (id, person_id, topic, belief, confidence, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (str(uuid.uuid4()), person_id, topic, belief, confidence, now),
                )
                self._conn.commit()
            return True
        except Exception as e:
            logger.warning(f"[VECTOR][person_model] update_belief failed: {e}")
            return False

    def _get_beliefs(self, person_id: str) -> dict:
        try:
            rows = self._conn.execute(
                "SELECT topic, belief, confidence FROM person_beliefs WHERE person_id=?",
                (person_id,),
            ).fetchall()
            return {r["topic"]: {"belief": r["belief"], "confidence": r["confidence"]} for r in rows}
        except Exception:
            return {}

    # ── Preferences ──────────────────────────────────────────────────────────

    def update_preference(self, person_id: str, key: str, value: str) -> bool:
        if not self.person_exists(person_id):
            return False
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self.__class__._db_lock:
                self._conn.execute(
                    """INSERT OR REPLACE INTO person_preferences (id, person_id, pref_key, pref_value, updated_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (str(uuid.uuid4()), person_id, key, value, now),
                )
                self._conn.commit()
            return True
        except Exception as e:
            logger.warning(f"[VECTOR][person_model] update_preference failed: {e}")
            return False

    def _get_preferences(self, person_id: str) -> dict:
        try:
            rows = self._conn.execute(
                "SELECT pref_key, pref_value FROM person_preferences WHERE person_id=?",
                (person_id,),
            ).fetchall()
            return {r["pref_key"]: r["pref_value"] for r in rows}
        except Exception:
            return {}

    # ── Interactions ─────────────────────────────────────────────────────────

    def record_interaction(
        self,
        person_id: str,
        summary: str,
        sentiment: str = "neutral",
        channel: str = "unknown",
    ) -> Optional[str]:
        if not self.person_exists(person_id):
            logger.warning(f"[VECTOR][person_model] record_interaction: unknown person {person_id}")
            return None
        iid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self.__class__._db_lock:
                self._conn.execute(
                    """INSERT INTO person_interactions (id, person_id, summary, sentiment, channel, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (iid, person_id, summary, sentiment, channel, now),
                )
                self._conn.commit()
        except Exception as e:
            logger.warning(f"[VECTOR][person_model] record_interaction failed: {e}")
            return None
        logger.info(f"[VECTOR][person_model] Interaction recorded: {person_id} ({sentiment})")
        return iid

    def get_interaction_history(self, person_id: str, limit: int = 10) -> list[dict]:
        try:
            rows = self._conn.execute(
                """SELECT * FROM person_interactions WHERE person_id=?
                   ORDER BY created_at DESC LIMIT ?""",
                (person_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"[VECTOR][person_model] get_interaction_history failed: {e}")
            return []

    # ── Trust ────────────────────────────────────────────────────────────────

    def update_trust(self, person_id: str, delta: float) -> float:
        """Adjust trust score by delta. Clamped to [0, 1]. Returns new score."""
        try:
            with self.__class__._db_lock:
                row = self._conn.execute(
                    "SELECT trust_score FROM persons WHERE id=?", (person_id,)
                ).fetchone()
                if not row:
                    return 0.5
                new_score = max(0.0, min(1.0, row["trust_score"] + delta))
                now = datetime.now(timezone.utc).isoformat()
                self._conn.execute(
                    "UPDATE persons SET trust_score=?, updated_at=? WHERE id=?",
                    (new_score, now, person_id),
                )
                self._conn.commit()
            logger.info(f"[VECTOR][person_model] Trust for {person_id}: {row['trust_score']:.2f} → {new_score:.2f}")
            return round(new_score, 3)
        except Exception as e:
            logger.warning(f"[VECTOR][person_model] update_trust failed: {e}")
            return 0.5

    def get_trust(self, person_id: str) -> float:
        try:
            row = self._conn.execute(
                "SELECT trust_score FROM persons WHERE id=?", (person_id,)
            ).fetchone()
            return round(float(row["trust_score"]), 3) if row else 0.5
        except Exception:
            return 0.5

    # ── Inference ────────────────────────────────────────────────────────────

    def infer_communication_style(self, person_id: str) -> dict:
        """
        Infer communication style from stored preferences and interaction history.
        Returns {formality, verbosity, technicality, directness} each as 'low'/'medium'/'high'.
        """
        prefs = self._get_preferences(person_id)
        history = self.get_interaction_history(person_id, limit=20)

        formality = prefs.get("formality", "medium")
        verbosity = prefs.get("verbosity", "medium")
        technicality = prefs.get("technicality", "medium")
        directness = prefs.get("directness", "medium")

        # Infer from interaction sentiments if preferences not set
        if history and "formality" not in prefs:
            formal_signals = sum(1 for h in history if h.get("sentiment") in ("formal", "professional"))
            if formal_signals > len(history) * 0.5:
                formality = "high"
            elif formal_signals < len(history) * 0.2:
                formality = "low"

        return {
            "formality": formality,
            "verbosity": verbosity,
            "technicality": technicality,
            "directness": directness,
        }

    def predict_response(self, person_id: str, message_topic: str) -> str:
        """
        Predict how this person might respond to a message on the given topic.
        Uses stored beliefs and interaction history.
        """
        beliefs = self._get_beliefs(person_id)
        history = self.get_interaction_history(person_id, limit=10)
        trust = self.get_trust(person_id)

        belief_on_topic = beliefs.get(message_topic, {}).get("belief", "")
        recent_sentiments = [h.get("sentiment", "neutral") for h in history[:3]]
        dominant = max(set(recent_sentiments), key=recent_sentiments.count) if recent_sentiments else "neutral"

        if trust >= 0.7:
            stance = "receptive"
        elif trust <= 0.3:
            stance = "sceptical"
        else:
            stance = "neutral"

        parts = [f"Likely {stance} response to '{message_topic}'."]
        if belief_on_topic:
            parts.append(f"Known belief: {belief_on_topic}")
        parts.append(f"Recent sentiment pattern: {dominant}.")
        return " ".join(parts)

    def get_model_summary(self) -> dict:
        """Summary across all tracked persons."""
        try:
            persons = self.get_all_persons()
            total = len(persons)
            avg_trust = (
                sum(p["trust_score"] for p in persons) / total if total > 0 else 0.5
            )
            by_type = {}
            for p in persons:
                rt = p["relationship_type"]
                by_type[rt] = by_type.get(rt, 0) + 1
            return {
                "total_persons": total,
                "avg_trust": round(avg_trust, 3),
                "by_relationship_type": by_type,
            }
        except Exception as e:
            logger.warning(f"[VECTOR][person_model] get_model_summary failed: {e}")
            return {}

    def close(self):
        if not self._owns_conn:
            return  # shared default-path singleton -- other instances still use it
        try:
            self._conn.close()
        except Exception as e:
            logger.warning("[VECTOR][person_model] close failed: {}", e)


if __name__ == "__main__":
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = f.name

    pm = PersonModel(db)
    p = pm.add_person("arghyadeep", "Arghyadeep Deb", "owner", {"kiit": True})
    assert p["id"] == "arghyadeep"

    pm.update_belief("arghyadeep", "AI", "believes AI is transformative", 0.9)
    pm.update_preference("arghyadeep", "formality", "low")
    pm.record_interaction("arghyadeep", "Discussed VECTOR roadmap", "positive", "cli")

    model = pm.get_model("arghyadeep")
    assert model is not None
    assert "beliefs" in model
    assert "AI" in model["beliefs"]
    assert model["preferences"]["formality"] == "low"
    assert len(model["recent_interactions"]) == 1

    style = pm.infer_communication_style("arghyadeep")
    assert "formality" in style

    trust = pm.update_trust("arghyadeep", 0.2)
    assert trust > 0.5

    pred = pm.predict_response("arghyadeep", "AI")
    assert isinstance(pred, str) and len(pred) > 0

    summary = pm.get_model_summary()
    assert summary["total_persons"] == 1

    pm.close()
    Path(db).unlink(missing_ok=True)
    print("[OK] person_model.py")
