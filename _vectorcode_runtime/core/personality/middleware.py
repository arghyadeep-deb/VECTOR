"""Personality middleware — injects character prompt and validates responses.

Sits between callers and ProviderClient.  Every call that passes
``inject_personality=True`` to ``ProviderClient.chat()`` is routed through
here automatically (see how ``provider_client.py`` instantiates
``_PersonalityLayer``).

Direct use (advanced):
    from core.personality.middleware import PersonalityLayer
    layer = PersonalityLayer()
    messages = layer.inject(messages, user_text="Help me debug this")
    # ... call LLM ...
    content, validation = layer.validate(response_content, user_text)
"""
from __future__ import annotations

__all__ = ["PersonalityLayer", "get_personality_layer"]


from pathlib import Path

from loguru import logger
from core.personality import PersonalityEngine
from core.personality.character_card import CharacterCard


class PersonalityLayer:
    """Inject personality system prompt and validate LLM responses."""

    def __init__(self, card_path: str | Path | None = None) -> None:
        self._engine = PersonalityEngine(card_path=card_path)

    @property
    def card(self) -> CharacterCard:
        return self._engine.card

    # Style phrasing rules: (key, value) → instruction string
    _STYLE_RULES: dict[str, dict[str, str]] = {
        "formality": {
            "low": "Use casual, friendly language with the user.",
            "high": "Use formal, professional language with the user.",
        },
        "verbosity": {
            "low": "Be concise and brief in responses.",
            "high": "Provide detailed, thorough responses.",
        },
        "technicality": {
            "low": "Avoid jargon; explain concepts in plain language.",
            "high": "Use precise technical terminology appropriate for experts.",
        },
        "directness": {
            "low": "Frame suggestions gently and indirectly.",
            "high": "Be direct and to the point.",
        },
    }

    def _style_suffix(self, person_id: str) -> str:
        """Return a style-personalisation paragraph for the given person. Never raises."""
        try:
            from core.brain.person_model import PersonModel
            style = PersonModel().infer_communication_style(person_id)
            rules = []
            for key, val in style.items():
                rule = self._STYLE_RULES.get(key, {}).get(val, "")
                if rule:
                    rules.append(rule)
            if not rules:
                return ""
            return "\n\n## Personalisation\n" + " ".join(rules)
        except Exception as e:
            logger.debug("[VECTOR][personality] style lookup failed for {}: {}", person_id, e)
            return ""

    def inject(
        self,
        messages: list[dict],
        user_text: str | None = None,
        context: str = "",
        person_id: str | None = None,
    ) -> list[dict]:
        """Return a copy of *messages* with the personality system prompt prepended.

        If *user_text* is not supplied, it is extracted from the last user message
        in *messages*.  The system prompt is derived from the user's sentiment so
        the character adapts dynamically to each turn.

        If *person_id* is provided, PersonModel.infer_communication_style() is
        called and its output is appended to the system prompt as style rules so
        VECTOR adapts its voice to the addressed person.
        """
        if not user_text:
            for m in reversed(messages):
                if m.get("role") == "user":
                    user_text = m.get("content", "")
                    break
        user_text = user_text or ""

        process_result = self._engine.process(user_text, context=context)
        personality_prompt = process_result.get("system_prompt", "")
        if not personality_prompt:
            return list(messages)

        try:
            from core.persona import PersonaManager
            pm = PersonaManager.get()
            personality_prompt = pm.inject_persona(
                personality_prompt,
                person_id=person_id,
            )
            logger.debug("[VECTOR][personality] persona injected")
        except Exception as e:
            logger.debug("[VECTOR][personality] persona injection skipped: {}", e)

        if person_id:
            personality_prompt += self._style_suffix(person_id)
            logger.debug("[VECTOR][personality] style injected for person={}", person_id)

        new_messages = []
        system_found = False
        for m in messages:
            if m.get("role") == "system" and not system_found:
                merged = personality_prompt + "\n\n---\n\n" + m.get("content", "")
                new_messages.append({"role": "system", "content": merged})
                system_found = True
            else:
                new_messages.append(dict(m))

        if not system_found:
            new_messages.insert(0, {"role": "system", "content": personality_prompt})

        logger.debug(
            "[PersonalityLayer] injected personality for sentiment={}",
            process_result.get("sentiment", {}) and process_result["sentiment"].emotion,
        )
        return new_messages

    def validate(
        self,
        content: str,
        user_text: str | None = None,
        sentiment: str = "neutral",
    ) -> tuple[str, dict]:
        """Validate *content* against the character card.

        Returns ``(final_content, validation_dict)`` where *final_content* is
        the (possibly rewritten) response and *validation_dict* has:
        - passed: bool
        - overall_score: float
        - issues: list[str]
        - rewritten: str | None
        """
        validation = self._engine.validate_response(content, user_text, sentiment)
        final = validation.get("rewritten") or content
        if not validation.get("passed") and validation.get("issues"):
            logger.info(
                "[PersonalityLayer] consistency issues: {}",
                "; ".join(validation["issues"]),
            )
        return final, validation

    def get_system_prompt(self, user_text: str, context: str = "") -> str:
        """Return only the personality system prompt for *user_text*."""
        return self._engine.compose_prompt(user_text, context=context)

    def analyze_sentiment(self, text: str):
        """Expose sentiment analysis for testing and introspection."""
        return self._engine.sentiment.analyze(text)


# Module-level singleton (created lazily so tests can pass a custom card_path)
_layer: PersonalityLayer | None = None


def get_personality_layer(card_path: str | Path | None = None) -> PersonalityLayer:
    global _layer
    if _layer is None:
        _layer = PersonalityLayer(card_path=card_path)
    return _layer
