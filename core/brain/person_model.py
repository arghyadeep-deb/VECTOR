"""
V.E.C.T.O.R. PersonModel.
Gap 7: Theory of mind per person — tracks beliefs, preferences, and communication style
for every person VECTOR interacts with, enabling personalised responses.
"""
from pathlib import Path

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from loguru import logger


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
            from core.runtime_paths import data_path
            base = data_path()
            base.mkdir(parents=True, exist_ok=True)
            db_path = str(base / "person_models.db")
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()
        logger.info("[VECTOR][person_model] PersonModel initialized")

    def _create_tables(self):
        with self.__class__._db_lock:
            self._conn.executescript("""
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
            self._conn.commit()

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
