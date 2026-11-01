"""Digest evaluator agent."""
from __future__ import annotations

import re
from typing import Any

class DigestEvaluator:
    """Evaluates the quality of generated digests."""

    def __init__(self, engine: Any | None = None, model: str | None = None) -> None:
        self._engine = engine
        self._model = model

    def evaluate(self, collected_data: Any, digest: str | None = None, **kw: Any) -> tuple[float, str]:
        """Return a 0-10 quality score plus actionable feedback.

        This deterministic evaluator is intentionally lightweight so morning
        digest generation can run even when an LLM judge is unavailable.
        """
        if digest is None:
            digest = str(collected_data or "")
            collected_data = kw.get("collected_data")

        text = (digest or "").strip()
        feedback: list[str] = []
        if not text:
            return 0.0, "Digest is empty."

        score = 5.0
        words = re.findall(r"\b[\w'-]+\b", text)
        word_count = len(words)
        sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]

        if 80 <= word_count <= 280:
            score += 1.5
        elif word_count < 40:
            feedback.append("Add enough detail to make the briefing useful.")
            score -= 1.5
        elif word_count > 350:
            feedback.append("Tighten the briefing; it is too long.")
            score -= 1.0

        data_text = str(collected_data or "").lower()
        if data_text and any(word.lower() in data_text for word in words[:80]):
            score += 1.0
        elif collected_data:
            feedback.append("Ground the briefing more clearly in the collected data.")
            score -= 0.5

        if len(sentences) >= 3:
            score += 1.0
        else:
            feedback.append("Use a few clear sentences instead of a fragment.")

        if re.search(r"\b(today|schedule|priority|reminder|message|weather|task|meeting)\b", text, re.I):
            score += 1.0
        else:
            feedback.append("Mention concrete priorities, schedule items, or action points.")

        if re.search(r"\b(unknown|n/a|placeholder|lorem ipsum|todo)\b", text, re.I):
            score -= 1.0
            feedback.append("Remove placeholder or uncertain filler.")

        score = max(0.0, min(10.0, round(score, 1)))
        if score >= 8.0 and not feedback:
            feedback.append("Briefing is concise, grounded, and actionable.")
        return score, " ".join(feedback)
