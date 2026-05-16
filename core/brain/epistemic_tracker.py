"""
V.E.C.T.O.R. EpistemicTracker.
Tracks what V.E.C.T.O.R. knows, how confident it is, and when knowledge becomes stale.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger
from datetime import datetime, timedelta
from core.config import CONFIG


class EpistemicTracker:
    """
    Manages V.E.C.T.O.R.'s knowledge state: beliefs, confidence levels,
    evidence sources, and knowledge staleness. Helps prevent acting on
    outdated information.
    """

    def __init__(self):
        self._beliefs: dict[str, dict] = {}
        self._confidence_decay_rate = CONFIG.get("epistemic", {}).get("decay_rate", 0.02)
        logger.info("[VECTOR][epistemic_tracker] EpistemicTracker initialized")

    def update_belief(self, key: str, value: str, confidence: float, source: str, ttl_hours: int = 72) -> dict:
        """Update a belief with confidence and TTL."""
        if not (0.0 <= confidence <= 1.0):
            confidence = max(0.0, min(1.0, confidence))

        now = datetime.now(datetime.timezone.utc).isoformat()
        self._beliefs[key] = {
            "value": value,
            "confidence": confidence,
            "source": source,
            "created_at": now,
            "ttl_hours": ttl_hours,
            "last_verified": now,
        }
        logger.info(f"[VECTOR][epistemic] Belief updated: {key} = {value[:50]}... (conf={confidence})")
        return self._beliefs[key]

    def get_belief(self, key: str) -> dict | None:
        """Get a belief and apply confidence decay."""
        if key not in self._beliefs:
            return None

        belief = self._beliefs[key].copy()
        created = datetime.fromisoformat(belief["created_at"])
        if created.tzinfo is None:
            created = created.replace(tzinfo=datetime.timezone.utc)
        age_hours = (datetime.now(datetime.timezone.utc) - created).total_seconds() / 3600

        if age_hours > belief["ttl_hours"]:
            belief["stale"] = True
            belief["current_confidence"] = 0.0
        else:
            decay = min(age_hours * self._confidence_decay_rate, belief["confidence"] * 0.5)
            belief["stale"] = False
            belief["current_confidence"] = round(max(0.0, belief["confidence"] - decay), 3)

        return belief

    def check_staleness(self) -> list[str]:
        """Return keys of all stale beliefs."""
        stale = []
        for key in self._beliefs:
            belief = self.get_belief(key)
            if belief and belief.get("stale"):
                stale.append(key)
        return stale

    def get_knowledge_summary(self) -> dict:
        """Get a summary of current knowledge state."""
        total = len(self._beliefs)
        stale = len(self.check_staleness())
        avg_confidence = (
            sum(b["confidence"] for b in self._beliefs.values()) / total if total > 0 else 0.0
        )
        return {
            "total_beliefs": total,
            "stale_beliefs": stale,
            "fresh_beliefs": total - stale,
            "avg_confidence": round(avg_confidence, 3),
        }

    def merge_belief(self, key: str, new_value: str, new_confidence: float, source: str):
        """Merge new evidence with existing belief (Bayesian-ish update)."""
        existing = self.get_belief(key)
        if existing:
            old_conf = existing.get("current_confidence", 0.5)
            merged_conf = (old_conf * 0.7) + (new_confidence * 0.3)
            self.update_belief(key, new_value, merged_conf, source)
        else:
            self.update_belief(key, new_value, new_confidence, source)


if __name__ == "__main__":
    et = EpistemicTracker()
    et.update_belief("user_name", "Arghyadeep", 0.9, "user_profile")
    et.update_belief("location", "KIIT Campus", 0.7, "calendar")
    print(et.get_knowledge_summary())
    print(et.check_staleness())