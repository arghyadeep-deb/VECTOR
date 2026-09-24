"""
V.E.C.T.O.R. EpistemicTracker.
Tracks what V.E.C.T.O.R. knows, how confident it is, and when knowledge becomes stale.
SQLite-backed so confidence values survive restarts (A8).
"""
from __future__ import annotations

from core.memory.db_utils import apply_pragmas
__all__ = ["EpistemicTracker"]

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


from loguru import logger
from core.config import CONFIG

from core.runtime_paths import data_path

_DEFAULT_DB = data_path("epistemic.db")


class EpistemicTracker:
    """
    Manages V.E.C.T.O.R.'s knowledge state: beliefs, confidence levels,
    evidence sources, and knowledge staleness.  All state is persisted to
    SQLite so confidence values survive restart.
    """

    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB
        self._confidence_decay_rate: float = CONFIG.get("epistemic", {}).get("decay_rate", 0.02)
        self._beliefs: dict[str, dict] = {}
        self._conn = self._init_db()
        self._load_from_db()
        logger.info("[VECTOR][epistemic_tracker] EpistemicTracker initialized (db={})", self._db_path)

    # ------------------------------------------------------------------
    # DB init
    # ------------------------------------------------------------------

    def _init_db(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        apply_pragmas(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS claims (
                id            TEXT PRIMARY KEY,
                claim         TEXT NOT NULL,
                confidence    REAL NOT NULL,
                last_seen_at  TEXT NOT NULL,
                decay_rate    REAL NOT NULL DEFAULT 0.02,
                source        TEXT NOT NULL DEFAULT 'vector',
                ttl_hours     INTEGER NOT NULL DEFAULT 72,
                created_at    TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS staleness_events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_id   TEXT NOT NULL,
                detected_at TEXT NOT NULL,
                reason     TEXT
            )
        """)
        conn.commit()
        return conn

    def _load_from_db(self) -> None:
        """Populate in-memory cache from DB on startup."""
        rows = self._conn.execute("SELECT * FROM claims").fetchall()
        for r in rows:
            self._beliefs[r["id"]] = {
                "value": r["claim"],
                "confidence": r["confidence"],
                "source": r["source"],
                "created_at": r["created_at"],
                "ttl_hours": r["ttl_hours"],
                "last_verified": r["last_seen_at"],
                "decay_rate": r["decay_rate"],
            }

    def _persist_belief(self, key: str, belief: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO claims (id, claim, confidence, last_seen_at, decay_rate, source, ttl_hours, created_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 claim=excluded.claim, confidence=excluded.confidence,
                 last_seen_at=excluded.last_seen_at, decay_rate=excluded.decay_rate,
                 source=excluded.source, ttl_hours=excluded.ttl_hours""",
            (key, belief["value"], belief["confidence"], now,
             belief.get("decay_rate", self._confidence_decay_rate),
             belief["source"], belief.get("ttl_hours", 72), belief.get("created_at", now)),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Original API (kept stable)
    # ------------------------------------------------------------------

    def update_belief(self, key: str, value: str, confidence: float, source: str, ttl_hours: int = 72) -> dict:
        """Update a belief with confidence and TTL. Persists to SQLite."""
        confidence = max(0.0, min(1.0, confidence))
        now = datetime.now(timezone.utc).isoformat()
        belief = {
            "value": value,
            "confidence": confidence,
            "source": source,
            "created_at": now,
            "ttl_hours": ttl_hours,
            "last_verified": now,
            "decay_rate": self._confidence_decay_rate,
        }
        self._beliefs[key] = belief
        try:
            self._persist_belief(key, belief)
        except Exception as e:
            logger.debug("[VECTOR][epistemic_tracker] persist failed: {}", e)
        logger.info("[VECTOR][epistemic] Belief updated: {} = {}... (conf={:.2f})", key, value[:40], confidence)
        return belief

    def get_belief(self, key: str) -> dict | None:
        """Get a belief and apply confidence decay based on age."""
        if key not in self._beliefs:
            return None
        belief = self._beliefs[key].copy()
        created_str = belief.get("created_at", belief.get("last_verified", ""))
        try:
            created = datetime.fromisoformat(created_str)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
        except Exception:
            created = datetime.now(timezone.utc)
        age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
        ttl = belief.get("ttl_hours", 72)
        if age_hours > ttl:
            belief["stale"] = True
            belief["current_confidence"] = 0.0
            self._log_staleness(key, "ttl_expired")
        else:
            dr = belief.get("decay_rate", self._confidence_decay_rate)
            decay = min(age_hours * dr, belief["confidence"] * 0.5)
            belief["stale"] = False
            belief["current_confidence"] = round(max(0.0, belief["confidence"] - decay), 3)
        return belief

    def check_staleness(self) -> list[str]:
        """Return keys of all stale beliefs."""
        return [k for k in self._beliefs if (self.get_belief(k) or {}).get("stale")]

    def get_knowledge_summary(self) -> dict:
        """Get a summary of current knowledge state."""
        total = len(self._beliefs)
        stale = len(self.check_staleness())
        avg_conf = sum(b["confidence"] for b in self._beliefs.values()) / total if total else 0.0
        return {
            "total_beliefs": total,
            "stale_beliefs": stale,
            "fresh_beliefs": total - stale,
            "avg_confidence": round(avg_conf, 3),
        }

    def merge_belief(self, key: str, new_value: str, new_confidence: float, source: str) -> None:
        """Merge new evidence with existing belief (Bayesian-ish update)."""
        existing = self.get_belief(key)
        if existing:
            old_conf = existing.get("current_confidence", 0.5)
            merged_conf = (old_conf * 0.7) + (new_confidence * 0.3)
            self.update_belief(key, new_value, merged_conf, source)
        else:
            self.update_belief(key, new_value, new_confidence, source)

    # ------------------------------------------------------------------
    # New A8 API
    # ------------------------------------------------------------------

    def record_claim(self, claim_id: str, claim_text: str, confidence: float,
                     decay_rate: float | None = None, source: str = "vector") -> str:
        """Alias of update_belief for the spec's 'record_claim()' interface."""
        dr = decay_rate if decay_rate is not None else self._confidence_decay_rate
        self._confidence_decay_rate = dr
        self.update_belief(claim_id, claim_text, confidence, source)
        self._confidence_decay_rate = CONFIG.get("epistemic", {}).get("decay_rate", 0.02)
        return claim_id

    def decay_all(self) -> int:
        """Apply confidence decay to all DB-backed beliefs; returns number of claims updated."""
        now = datetime.now(timezone.utc)
        updated = 0
        for key, belief in list(self._beliefs.items()):
            b = self.get_belief(key)
            if b is None:
                continue
            new_conf = b.get("current_confidence", 0.0)
            if abs(new_conf - belief["confidence"]) > 0.001:
                self._beliefs[key]["confidence"] = new_conf
                try:
                    self._conn.execute(
                        "UPDATE claims SET confidence=?, last_seen_at=? WHERE id=?",
                        (new_conf, now.isoformat(), key),
                    )
                    self._conn.commit()
                    updated += 1
                except Exception as e:
                    logger.debug("[VECTOR][epistemic_tracker] decay_all update failed: {}", e)
        return updated

    def get_confidence(self, claim_id: str) -> float:
        """Return current (decayed) confidence for a claim. 0.0 if unknown."""
        b = self.get_belief(claim_id)
        if b is None:
            return 0.0
        return b.get("current_confidence", 0.0)

    def get_stale_claims(self, age_hours: float = 72.0) -> list[dict]:
        """Return all claims older than age_hours or marked stale."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat()
        rows = self._conn.execute(
            "SELECT * FROM claims WHERE last_seen_at < ? OR confidence <= 0.0",
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]

    def _log_staleness(self, claim_id: str, reason: str) -> None:
        try:
            self._conn.execute(
                "INSERT INTO staleness_events (claim_id, detected_at, reason) VALUES (?,?,?)",
                (claim_id, datetime.now(timezone.utc).isoformat(), reason),
            )
            self._conn.commit()
        except Exception:
            logger.warning("[VECTOR] silent swallow")
            pass

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            logger.warning("[VECTOR] silent swallow")
            pass


if __name__ == "__main__":
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = f.name
    et = EpistemicTracker(db_path=db)
    et.update_belief("user_name", "Arghyadeep", 0.9, "user_profile")
    et.update_belief("location", "KIIT Campus", 0.7, "calendar")
    print(et.get_knowledge_summary())
    print("get_confidence user_name:", et.get_confidence("user_name"))

    # Simulate restart
    et.close()
    et2 = EpistemicTracker(db_path=db)
    print("After restart:", et2.get_knowledge_summary())
    print("user_name belief:", et2.get_belief("user_name")["confidence"])
    et2.close()
    Path(db).unlink(missing_ok=True)
    print("OK: epistemic_tracker")