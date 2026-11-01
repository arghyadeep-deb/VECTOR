"""PersonalityEngine — orchestrates VECTOR's full personality pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from core.config import CONFIG
from core.personality.character_card import CharacterCard
from core.personality.consistency import ConsistencyEnforcer
from core.personality.memory_persona import MemoryPersona
from core.personality.sentiment import SentimentAnalyzer, SentimentResult
from core.personality.tone_adapter import ToneAdapter, ToneConfig


class PersonalityEngine:
    def __init__(self, card_path: str | Path | None = None):
        config = CONFIG.get("personality", {})
        card_path = card_path or config.get("character_card_path", "")
        if not card_path or not Path(card_path).exists():
            default_path = Path(__file__).parent / "characters" / "vector.json"
            if default_path.exists():
                card_path = str(default_path)

        self.card = CharacterCard.load(card_path) if card_path else CharacterCard()
        self.sentiment = SentimentAnalyzer()
        self.tone = ToneAdapter(self.card)
        self.enforcer = ConsistencyEnforcer(self.card)
        self.memory = MemoryPersona()
        self._enabled = config.get("enabled", True)

        logger.info("[PersonalityEngine] initialized (enabled={})", self._enabled)

    def process(self, user_text: str, context: str = "") -> dict[str, Any]:
        if not self._enabled:
            return {"response_hint": None, "tone_config": ToneConfig()}

        sentiment_result = self.sentiment.analyze(user_text)
        tone_config = self.tone.get_config(sentiment_result)

        preferences = self.memory.query_top_preferences(
            context=context,
            sentiment=sentiment_result.emotion,
        )
        if preferences:
            self.tone.inject_learned_preferences(preferences)

        feedback = self.memory.detect_feedback(user_text)
        if feedback:
            from datetime import datetime
            lesson_context = self.memory.get_context(user_text)
            from core.personality.memory_persona import PersonalityLesson
            lesson = PersonalityLesson(
                context=lesson_context,
                user_sentiment=sentiment_result.emotion,
                response_type=feedback["response_type"],
                outcome=feedback["outcome"],
                timestamp=datetime.now().isoformat(),
                source=feedback["source"],
            )
            self.memory.store_lesson(lesson)

        system_prompt = self.tone.compose_system_prompt(self.card, sentiment_result)

        return {
            "sentiment": sentiment_result,
            "tone_config": tone_config,
            "system_prompt": system_prompt,
            "preferences": preferences,
        }

    def validate_response(self, response: str, user_message: str | None = None, sentiment: str = "neutral") -> dict[str, Any]:
        if not self._enabled:
            return {"passed": True, "overall_score": 1.0}
        result = self.enforcer.check(response, user_message, sentiment)
        return {
            "passed": result.passed,
            "overall_score": result.overall_score,
            "issues": result.issues,
            "rewritten": result.rewritten,
            "consistency_result": result,
        }

    def process_with_personality(self, user_text: str, context: str = "") -> tuple[str | None, ToneConfig | None]:
        result = self.process(user_text, context)
        return result.get("system_prompt"), result.get("tone_config")

    def compose_prompt(self, user_text: str, context: str = "") -> str:
        result = self.process(user_text, context)
        return result.get("system_prompt", "")
