"""
Persistent cross-session mood/presence state for the Avatar layer.
Owns: valence, arousal, dominance, emotional_arc, presence_score.
Does NOT own: trust, intimacy, relationship_stage — those live in PersonModel.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

from loguru import logger
from core.config import CONFIG


_DB_PATH: Path = CONFIG.get("db_path", Path("vector_memory.db"))
_PRESENCE = CONFIG.get("presence", {})


@dataclass
class AvatarState:
    """Cross-session mood/presence snapshot. Single row in avatar_state table."""
    # Valence-Arousal-Dominance (PAD emotion model, -1..1)
    valence: float = 0.0     # pleasant (+) / unpleasant (-)
    arousal: float = 0.0     # activated (+) / calm (-)
    dominance: float = 0.1   # in control (+) / submissive (-)

    # Presence score: 0.0 = dormant, 1.0 = fully engaged
    presence_score: float = 0.5

    # Short emotional arc summary (last 5 interactions)
    emotional_arc: list[str] = field(default_factory=list)

    # Timestamp of last update
    updated_at: str = ""

    # ── derived helpers ──────────────────────────────────────────────────────
    @property
    def mood_label(self) -> str:
        if self.valence > 0.3 and self.arousal > 0.1:
            return "energised"
        if self.valence > 0.2:
            return "positive"
        if self.valence < -0.3:
            return "tense" if self.arousal > 0 else "subdued"
        return "neutral"

    @property
    def tone_hint(self) -> str:
        """Single-word hint consumed by AvatarVoice."""
        mapping = {
            "energised": "warm",
            "positive": "steady",
            "neutral": "precise",
            "subdued": "gentle",
            "tense": "calm",
        }
        return mapping.get(self.mood_label, "precise")

    # ── persistence ──────────────────────────────────────────────────────────
    @classmethod
    def _get_conn(cls) -> sqlite3.Connection:
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS avatar_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                valence REAL NOT NULL DEFAULT 0.0,
                arousal REAL NOT NULL DEFAULT 0.0,
                dominance REAL NOT NULL DEFAULT 0.1,
                presence_score REAL NOT NULL DEFAULT 0.5,
                emotional_arc TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.commit()
        return conn

    @classmethod
    def load(cls) -> "AvatarState":
        try:
            conn = cls._get_conn()
            row = conn.execute("SELECT * FROM avatar_state WHERE id = 1").fetchone()
            conn.close()
            if row is None:
                logger.debug("[VECTOR][avatar_state] no saved state, using defaults")
                return cls()
            return cls(
                valence=row[1],
                arousal=row[2],
                dominance=row[3],
                presence_score=row[4],
                emotional_arc=json.loads(row[5]),
                updated_at=row[6],
            )
        except Exception as e:
            logger.warning("[VECTOR][avatar_state] load failed ({}), using defaults", e)
            return cls()

    def save(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()
        try:
            conn = self._get_conn()
            conn.execute("""
                INSERT OR REPLACE INTO avatar_state
                (id, valence, arousal, dominance, presence_score, emotional_arc, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?)
            """, (
                round(self.valence, 4),
                round(self.arousal, 4),
                round(self.dominance, 4),
                round(self.presence_score, 4),
                json.dumps(self.emotional_arc[-10:]),  # keep last 10
                self.updated_at,
            ))
            conn.commit()
            conn.close()
            logger.debug("[VECTOR][avatar_state] saved (mood={})", self.mood_label)
        except Exception as e:
            logger.warning("[VECTOR][avatar_state] save failed: {}", e)

    # ── update helpers ───────────────────────────────────────────────────────
    def absorb_sentiment(self, emotion: str, intensity: float) -> None:
        """Blend a new sentiment observation into PAD state (EMA α=0.3)."""
        _EMOTION_PAD: dict[str, tuple[float, float, float]] = {
            "happy":      (0.8,  0.4,  0.3),
            "frustrated": (-0.6, 0.7, -0.2),
            "urgent":     (0.0,  0.9,  0.0),
            "curious":    (0.4,  0.3,  0.1),
            "sad":        (-0.5, -0.4, -0.3),
            "neutral":    (0.0,  0.0,  0.0),
        }
        pad = _EMOTION_PAD.get(emotion, (0.0, 0.0, 0.0))
        alpha = 0.3 * intensity
        self.valence   = self.valence   * (1 - alpha) + pad[0] * alpha
        self.arousal   = self.arousal   * (1 - alpha) + pad[1] * alpha
        self.dominance = self.dominance * (1 - alpha) + pad[2] * alpha
        self.emotional_arc.append(f"{emotion}:{intensity:.2f}")

    def boost_presence(self, delta: float = 0.1) -> None:
        self.presence_score = min(1.0, self.presence_score + delta)

    def decay_presence(self, delta: float = 0.02) -> None:
        self.presence_score = max(0.0, self.presence_score - delta)


if __name__ == "__main__":
    state = AvatarState.load()
    state.absorb_sentiment("happy", 0.7)
    state.save()
    loaded = AvatarState.load()
    assert loaded.valence > 0, "Expected positive valence after happy sentiment"
    print(f"✅ avatar_state OK — mood={loaded.mood_label} valence={loaded.valence:.3f}")
