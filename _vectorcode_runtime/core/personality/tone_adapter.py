"""Maps user sentiment to VECTOR response personality configuration."""

from __future__ import annotations

__all__ = [
    "ToneAdapter",
    "ToneConfig",
]


import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from core.personality.character_card import CharacterCard
from core.personality.sentiment import SentimentResult


class ToneConfig(BaseModel):
    tone: str = "default_precise"
    speed: float = Field(default=0.85, ge=0.5, le=1.5)
    emphasized_traits: list[str] = Field(default_factory=list)
    suppressed_traits: list[str] = Field(default_factory=list)
    active_rules: list[str] = Field(default_factory=list)
    system_prompt_override: str | None = None
    greeting_required: bool = False


class ToneAdapter:
    def __init__(self, card: CharacterCard):
        self._card = card
        self._learned_preferences: list[dict[str, Any]] = []

    def get_config(self, sentiment: SentimentResult) -> ToneConfig:
        profile = self._card.tone_mapping.get(sentiment.emotion)
        if not profile:
            return ToneConfig()

        config = ToneConfig(
            tone=profile.tone,
            speed=profile.speed,
            emphasized_traits=profile.traits_to_emphasize,
            suppressed_traits=profile.traits_to_suppress,
            active_rules=list(profile.rules_to_activate),
        )

        learned_hints = self._get_learned_hints(sentiment)
        if learned_hints:
            for hint in learned_hints[:2]:
                config.active_rules.insert(0, hint)

        if sentiment.urgency > 0.7:
            config.speed = min(1.5, config.speed * 1.1)

        return config

    def compose_system_prompt(self, card: CharacterCard, sentiment: SentimentResult) -> str:
        lines: list[str] = []
        lines.append(f"You are {card.name} — {card.full_name}.")
        lines.append(f"You were created by and belong to {card.owner}.")
        lines.append("")

        sorted_traits = sorted(card.traits.items(), key=lambda x: -x[1])
        lines.append("CORE TRAITS:")
        for trait, score in sorted_traits:
            desc = self._trait_description(trait, score)
            lines.append(f"- {desc}")
        lines.append("")

        config = self.get_config(sentiment)
        if config.emphasized_traits:
            lines.append("EMPHASIZED TRAITS (respond with these foremost):")
            for t in config.emphasized_traits:
                score = card.traits.get(t, 0.5)
                lines.append(f"- {t.title()} ({score:.0%})")
            lines.append("")

        if config.suppressed_traits:
            lines.append("SUPPRESSED TRAITS (avoid showing these):")
            for t in config.suppressed_traits:
                lines.append(f"- {t.title()}")
            lines.append("")

        lines.append(f"The user is feeling {sentiment.emotion.upper()} (intensity: {sentiment.intensity:.2f}).")
        lines.append("")

        all_rules = list(card.rules) + config.active_rules
        if all_rules:
            lines.append("RULES:")
            for r in all_rules:
                lines.append(f"- {r}")
            lines.append("")

        if card.speech_patterns:
            lines.append("SPEECH:")
            lines.append(f"- Address owner as '{card.speech_patterns.address_owner}'")
            if card.speech_patterns.contractions != "relaxed":
                lines.append(f"- Contractions: {card.speech_patterns.contractions}")
            if card.speech_patterns.filler_words == "none":
                lines.append("- No filler words: no 'um', 'uh', 'like', 'you know'")
            if card.speech_patterns.emoji == "never":
                lines.append("- Never use emoji")

        profile = card.tone_mapping.get(sentiment.emotion)
        if profile:
            lines.append("")
            lines.append(f"Tone: {profile.tone}")

        learned = self._get_learned_hints(sentiment)
        if learned:
            lines.append("")
            lines.append("LEARNED PREFERENCES (from previous interactions):")
            for h in learned:
                lines.append(f"- {h}")

        return "\n".join(lines)

    def inject_learned_preferences(self, preferences: list[dict[str, Any]]) -> None:
        self._learned_preferences = preferences

    def _get_learned_hints(self, sentiment: SentimentResult) -> list[str]:
        if not self._learned_preferences:
            return []
        hints = []
        for p in self._learned_preferences:
            context = p.get("context", "")
            response_type = p.get("response_type", "")
            confidence = p.get("confidence", 0.5)
            if confidence >= 0.7:
                hints.append(f"In '{context}' contexts, {response_type} responses work best (confidence: {confidence:.2f})")
        return hints

    @staticmethod
    def _trait_description(trait: str, score: float) -> str:
        intensity = "extremely" if score >= 0.9 else "very" if score >= 0.75 else "moderately" if score >= 0.5 else "slightly"
        descriptions = {
            "calm": "Stay composed. No exclamation marks. No extreme language.",
            "precise": "Choose exact words. Avoid 'maybe', 'sort of', 'kind of'.",
            "dry": "Subtle deadpan humor. No punchlines or jokes.",
            "efficient": "Minimize words while maximizing information.",
            "attentive": "Reference details sir has shared in this conversation.",
            "loyal": "Always act in sir's best interest.",
            "curious": "Show interest in learning and exploration.",
            "patient": "Extra patience. Never rush the user.",
            "protective": "Watch for security risks and user safety.",
            "witty": "Quick, intelligent humor when appropriate.",
        }
        desc = descriptions.get(trait, "")
        return f"{intensity.title()} {trait} ({score:.0%}): {desc}"
