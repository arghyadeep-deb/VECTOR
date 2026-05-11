"""
V.E.C.T.O.R. MetaCognition.
Self-awareness and reflection engine for V.E.C.T.O.R.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger
from datetime import datetime
from core.config import CONFIG


class MetaCognition:
    """
    Self-reflection: monitors V.E.C.T.O.R.'s own reasoning quality,
    detects blind spots, generates improvement hypotheses.
    RULE 1: session_hydration_prompt() before every LLM call.
    """

    def __init__(self):
        self._self_model = CONFIG["models"]["reasoning"]
        self._observations: list[dict] = []
        self._blind_spot_log: list[dict] = []
        logger.info("[VECTOR][meta_cognition] MetaCognition initialized")

    def observe(self, thought: str, confidence: float, outcome: str | None = None):
        """Record a thought and its outcome for self-analysis."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "thought": thought,
            "confidence": confidence,
            "outcome": outcome,
            "accuracy": None if outcome is None else None,
        }
        self._observations.append(entry)

    def detect_blind_spot(self, missed_signal: str, context: str) -> dict:
        """Log a missed signal (blind spot) for later analysis."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "missed_signal": missed_signal,
            "context": context,
            "resolved": False,
        }
        self._blind_spot_log.append(entry)
        logger.warning(f"[VECTOR][meta_cognition] Blind spot detected: {missed_signal}")
        return entry

    def resolve_blind_spot(self, missed_signal: str, resolution: str):
        """Mark a blind spot as resolved."""
        for entry in self._blind_spot_log:
            if entry["missed_signal"] == missed_signal and not entry["resolved"]:
                entry["resolved"] = True
                entry["resolution"] = resolution
                logger.info(f"[VECTOR][meta_cognition] Blind spot resolved: {missed_signal}")
                return
        logger.warning(f"[VECTOR][meta_cognition] Blind spot not found: {missed_signal}")

    def get_self_report(self) -> dict:
        """Generate a self-awareness report."""
        total = len(self._observations)
        blind_spots = len(self._blind_spot_log)
        resolved = sum(1 for b in self._blind_spot_log if b.get("resolved"))
        avg_confidence = (
            sum(o["confidence"] for o in self._observations) / total
            if total > 0 else 0.0
        )
        return {
            "total_thoughts": total,
            "avg_confidence": round(avg_confidence, 3),
            "blind_spots": blind_spots,
            "blind_spots_resolved": resolved,
            "resolution_rate": round(resolved / blind_spots, 2) if blind_spots > 0 else 1.0,
        }


if __name__ == "__main__":
    mc = MetaCognition()
    mc.observe("The user's tone suggests urgency", 0.8, "User confirmed urgent")
    mc.detect_blind_spot("Missed KIIT exam reminder", "Calendar check was incomplete")
    print(mc.get_self_report())