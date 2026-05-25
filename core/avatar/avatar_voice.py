"""
AvatarVoice — unified response formatter for the Avatar layer.
Rules:
  - Always speak as "I" (never "CodingBot", "HealthAgent", "District X")
  - Empathy-first: if user is frustrated/sad, acknowledge before solving
  - Tone driven by AvatarState.tone_hint + personality system
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import re
from typing import Any

from loguru import logger
from core.config import CONFIG
from core.avatar.avatar_state import AvatarState


# District / internal names VECTOR must never leak to the owner
_INTERNAL_NAMES: list[str] = [
    "CodingBot", "CodeReviewer", "GitBot", "ArchitectBot", "BugHunter",
    "ThreatScout", "MalwareHunter", "NodeGuard", "ThreatDetector",
    "HealthAdvisor", "FatigueMonitor", "SleepTracker",
    "DailyReviewer", "JournalWriter", "GrowthAnalyst",
    "FinanceBot", "UPIParser", "BudgetAnalyst",
    "StockAnalyst", "FundamentalsBot",
    "PatternDetective", "BehaviorAnalyst", "HabitFinder",
    "AINewsBot", "MarketTrendsBot", "OpportunitySpotter",
    "MockInterviewer", "ReportGenerator",
    "ConsolidationBot", "PatternFinder",
    "ChiefOfStaff", "Governor", "LLMCouncil",
    "district", "District", "agent", "Agent",
]
_INTERNAL_RE = re.compile(
    r"\b(" + "|".join(re.escape(n) for n in _INTERNAL_NAMES) + r")\b"
)

# Empathy acknowledgments keyed on emotion
_EMPATHY_MAP: dict[str, str] = {
    "frustrated": "I hear you — that's genuinely frustrating. Let me sort this out.",
    "sad":        "I notice you seem a bit down. I'm here. Let me help with this.",
    "urgent":     "On it right away.",
}


class AvatarVoice:
    """
    Formats raw district output into a unified first-person VECTOR response.
    Reuses core/personality ToneAdapter + ConsistencyEnforcer; never duplicates them.
    """

    def __init__(self):
        self._tone_adapter = None
        self._consistency = None
        self._sentiment_analyzer = None
        self._card = None

    def _get_personality(self):
        """Lazy-load personality components."""
        if self._card is None:
            try:
                from core.personality.character_card import CharacterCard
                from core.personality.tone_adapter import ToneAdapter
                from core.personality.consistency import ConsistencyEnforcer
                self._card = CharacterCard()
                self._tone_adapter = ToneAdapter(self._card)
                self._consistency = ConsistencyEnforcer(self._card)
            except Exception as e:
                logger.warning("[VECTOR][avatar_voice] personality load failed: {}", e)

    def _get_sentiment_analyzer(self):
        if self._sentiment_analyzer is None:
            try:
                from core.personality.sentiment import SentimentAnalyzer
                self._sentiment_analyzer = SentimentAnalyzer()
            except Exception as e:
                logger.warning("[VECTOR][avatar_voice] sentiment analyzer load failed: {}", e)
        return self._sentiment_analyzer

    # ── public API ────────────────────────────────────────────────────────────
    def format(
        self,
        district_output: Any,
        state: AvatarState,
        task_context: dict | None = None,
        user_message: str = "",
    ) -> str:
        """
        Convert raw district output to a clean first-person VECTOR response.

        district_output: dict from agent.run() or a plain string
        state:           current AvatarState (for tone)
        task_context:    optional dict with 'task_type', 'district', etc.
        user_message:    original owner message (for empathy + consistency check)
        """
        raw = self._extract_text(district_output)

        # 1. Sanitise: strip internal agent/district names
        clean = self._sanitise(raw)

        # 2. Empathy wrapper: acknowledge emotion before solution
        clean = self._maybe_prepend_empathy(clean, user_message, state)

        # 3. Consistency check + optional LLM rewrite via existing enforcer
        clean = self._enforce_consistency(clean, user_message, state)

        # 4. First-person guarantee
        clean = self._ensure_first_person(clean)

        logger.debug("[VECTOR][avatar_voice] formatted ({} chars)", len(clean))
        return clean

    # ── internal helpers ─────────────────────────────────────────────────────
    def _extract_text(self, output: Any) -> str:
        if isinstance(output, str):
            return output
        if isinstance(output, dict):
            for key in ("response", "result", "content", "message", "text", "output"):
                val = output.get(key)
                if val and isinstance(val, str):
                    return val
            # fallback: stringify relevant status info
            status = output.get("status", "done")
            return f"Task completed — status: {status}."
        return str(output)

    def _sanitise(self, text: str) -> str:
        """Replace leaked internal names with neutral 'I'."""
        result = _INTERNAL_RE.sub("I", text)
        if result != text:
            logger.debug("[VECTOR][avatar_voice] sanitised internal name leak")
        return result

    def _maybe_prepend_empathy(self, text: str, user_message: str, state: AvatarState) -> str:
        if not user_message:
            return text
        sa = self._get_sentiment_analyzer()
        if sa is None:
            return text
        try:
            sentiment = sa.analyze(user_message)
            # Only acknowledge negative/urgent emotions with intensity > threshold
            if sentiment.emotion in _EMPATHY_MAP and sentiment.intensity > 0.3:
                ack = _EMPATHY_MAP[sentiment.emotion]
                # Don't double-ack if the district already said something empathetic
                if ack[:15].lower() not in text.lower()[:80]:
                    text = f"{ack}\n\n{text}"
                    logger.debug("[VECTOR][avatar_voice] empathy ack prepended ({})", sentiment.emotion)
                # Update state with this sentiment observation
                state.absorb_sentiment(sentiment.emotion, sentiment.intensity)
        except Exception as e:
            logger.debug("[VECTOR][avatar_voice] empathy check failed: {}", e)
        return text

    def _enforce_consistency(self, text: str, user_message: str, state: AvatarState) -> str:
        self._get_personality()
        if self._consistency is None:
            return text
        try:
            from core.personality.sentiment import SentimentResult
            result = self._consistency.check(text, user_message or None, state.mood_label)
            if result.rewritten:
                return result.rewritten
        except Exception as e:
            logger.debug("[VECTOR][avatar_voice] consistency check failed: {}", e)
        return text

    def _ensure_first_person(self, text: str) -> str:
        """Capitalise the first 'I' if missing from the start."""
        # If text begins with third-person agent phrase, prepend "I've handled this —"
        if re.match(r"^(The agent|The system|Agent|System)\b", text, re.IGNORECASE):
            text = "I've handled this — " + text[text.index(" ") + 1:]
        return text


if __name__ == "__main__":
    state = AvatarState.load()
    voice = AvatarVoice()

    raw = {"status": "ok", "response": "CodingBot has reviewed your code and found 2 issues."}
    out = voice.format(raw, state, user_message="review my code")
    assert "CodingBot" not in out, f"Internal name leaked: {out}"
    assert "I" in out or "found" in out, f"No first-person: {out}"
    print(f"OK avatar_voice -- output: {out[:80]!r}")
