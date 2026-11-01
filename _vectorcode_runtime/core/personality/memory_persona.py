"""Personality that learns from user interaction over time."""

from __future__ import annotations

__all__ = [
    "MemoryPersona",
    "PersonalityLesson",
]


import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from core.config import CONFIG
from core.memory.db_utils import configured_db_path


@dataclass
class PersonalityLesson:
    context: str = ""
    user_sentiment: str = "neutral"
    response_type: str = "concise"  # concise | detailed | humorous | direct
    outcome: float = 0.5
    timestamp: str = ""
    source: str = "implicit"  # explicit_feedback | implicit | pattern
    confidence: float = 1.0


_FEEDBACK_POSITIVE = {
    "perfect", "great", "thanks", "better", "good", "nice",
    "exactly", "that's it", "correct", "yes",
}
_FEEDBACK_NEGATIVE = {
    "too verbose", "too long", "too formal", "too casual",
    "too much", "be more concise", "be more direct",
    "shorter", "that's not what i meant", "no", "wrong",
    "stop", "cancel", "never mind",
}
_FEEDBACK_NEUTRAL = {
    "ok", "okay", "fine", "alright", "sure",
}


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    """Word-boundary regex for a feedback phrase.

    A plain substring check (``phrase in lower``) false-positives constantly
    on short, common phrases: "no" matches inside "know"/"now"/"not"/"noon",
    "yes" matches inside "yesterday", "ok" matches inside "book"/"broken",
    "sure" matches inside "ensure"/"assure". Every such match silently wrote
    a wrong-polarity PersonalityLesson, corrupting the learned-preference
    signal this engine uses to adapt VECTOR's responses.
    """
    return re.compile(r"\b" + re.escape(phrase) + r"\b")


_FEEDBACK_NEGATIVE_PATTERNS = {p: _phrase_pattern(p) for p in _FEEDBACK_NEGATIVE}
_FEEDBACK_POSITIVE_PATTERNS = {p: _phrase_pattern(p) for p in _FEEDBACK_POSITIVE}
_FEEDBACK_NEUTRAL_PATTERNS = {p: _phrase_pattern(p) for p in _FEEDBACK_NEUTRAL}


class MemoryPersona:
    def __init__(self, db_path: str | None = None):
        # Explicit db_path (tests) → private plain-sqlite connections.
        # Default → the main DB, which may be SQLCipher-encrypted, so it MUST
        # go through episodic's singleton connector (plain sqlite3.connect
        # fails with "file is not a database").
        self._private_db_path = db_path
        self._db_path = db_path or str(configured_db_path())
        self._ensure_table()
        self._enabled = CONFIG.get("personality", {}).get("learning_enabled", True)
        logger.info("[MemoryPersona] initialized (enabled={})", self._enabled)

    @contextmanager
    def _conn(self):
        if self._private_db_path is not None:
            conn = sqlite3.connect(self._private_db_path, check_same_thread=False)
            try:
                yield conn
            finally:
                conn.close()
        else:
            from core.memory.episodic import get_db_connection
            yield get_db_connection()   # shared singleton — never close it here

    def _ensure_table(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS personality_lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    context TEXT,
                    user_sentiment TEXT,
                    response_type TEXT,
                    outcome REAL,
                    timestamp TEXT,
                    source TEXT,
                    confidence REAL DEFAULT 1.0
                )
            """)
            conn.commit()

    def detect_feedback(self, user_text: str) -> dict[str, Any] | None:
        lower = user_text.lower().strip()
        for phrase, pattern in _FEEDBACK_NEGATIVE_PATTERNS.items():
            if pattern.search(lower):
                outcome = 0.2 if "too" in phrase or "be more" in phrase else 0.1
                return {"response_type": self._infer_target(phrase), "outcome": outcome, "source": "explicit_feedback"}
        for phrase, pattern in _FEEDBACK_POSITIVE_PATTERNS.items():
            if pattern.search(lower):
                return {"response_type": self._infer_target(phrase), "outcome": 0.9, "source": "explicit_feedback"}
        for phrase, pattern in _FEEDBACK_NEUTRAL_PATTERNS.items():
            if pattern.search(lower):
                return {"response_type": "neutral", "outcome": 0.6, "source": "explicit_feedback"}
        return None

    def store_lesson(self, lesson: PersonalityLesson) -> None:
        if not self._enabled:
            return
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO personality_lessons (context, user_sentiment, response_type, outcome, timestamp, source, confidence) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (lesson.context, lesson.user_sentiment, lesson.response_type,
                 lesson.outcome, lesson.timestamp or str(time.time()),
                 lesson.source, lesson.confidence),
            )
            conn.commit()
        logger.debug("[MemoryPersona] stored lesson: {} in '{}' (outcome={})", lesson.response_type, lesson.context, lesson.outcome)

    def query_top_preferences(self, context: str = "", sentiment: str = "") -> list[dict[str, Any]]:
        with self._conn() as conn:
            like_ctx = f"%{context}%" if context else "%"
            params: list[Any] = [like_ctx]
            where_sentiment = ""
            if sentiment:
                where_sentiment = "OR user_sentiment = ?"
                params.append(sentiment)
            rows = conn.execute(
                f"""
                SELECT response_type, AVG(outcome * confidence) as avg_outcome, COUNT(*) as count
                FROM personality_lessons
                WHERE (context LIKE ? {where_sentiment})
                GROUP BY response_type
                ORDER BY avg_outcome DESC
                LIMIT 3
                """,
                params,
            ).fetchall()
            results = []
            for rt, avg, cnt in rows:
                if avg and avg >= 0.6 and cnt >= 2:
                    results.append({
                        "response_type": rt,
                        "confidence": round(avg, 3),
                        "count": cnt,
                        "context": context,
                    })
            return results

    def infer_implicit_feedback(self, user_text_before: str, user_text_after: str) -> PersonalityLesson | None:
        if not user_text_after:
            return None
        before_lower = user_text_before.lower() if user_text_before else ""
        after_lower = user_text_after.lower()

        reprased = (
            len(after_lower.split()) > len(before_lower.split()) * 0.8
            and any(w in before_lower for w in after_lower.split()[:3])
        )
        if reprased:
            return PersonalityLesson(context="general", outcome=0.3, source="implicit", confidence=0.5)

        brief_ok = after_lower.strip() in _FEEDBACK_NEUTRAL or after_lower.strip() in _FEEDBACK_POSITIVE
        if brief_ok:
            return PersonalityLesson(context="general", outcome=0.7, source="implicit", confidence=0.4)

        attention_needed = "vector" in after_lower or "hey" in after_lower
        if attention_needed:
            return PersonalityLesson(context="general", outcome=0.4, source="implicit", confidence=0.3)

        return None

    def get_context(self, user_text: str) -> str:
        lower = user_text.lower()
        contexts = {
            "debugging": r"\b(debug|bug|error|crash|fix|broken|issue|trace)\b",
            "morning": r"\b(good morning|morning|wake up)\b",
            "research": r"\b(research|search|find|look up|investigate)\b",
            "coding": r"\b(code|write|implement|function|class|api)\b",
            "writing": r"\b(write|draft|compose|create|edit)\b",
            "planning": r"\b(plan|schedule|organize|todo|task)\b",
        }
        for ctx, pattern in contexts.items():
            if re.search(pattern, lower):
                return ctx
        return "general"

    def _infer_target(self, phrase: str) -> str:
        if "verbose" in phrase or "long" in phrase or "concise" in phrase or "shorter" in phrase:
            return "concise"
        if "direct" in phrase:
            return "direct"
        if "formal" in phrase:
            return "casual" if "too" in phrase else "formal"
        if "casual" in phrase:
            return "formal" if "too" in phrase else "casual"
        return "neutral"
