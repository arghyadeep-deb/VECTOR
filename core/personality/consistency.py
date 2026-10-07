"""Validates every outgoing response against the character card."""

from __future__ import annotations

__all__ = [
    "ConsistencyEnforcer",
    "ConsistencyResult",
]


import json
import re
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from core.config import CONFIG
from core.personality.character_card import CharacterCard


class ConsistencyResult(BaseModel):
    passed: bool
    trait_scores: dict[str, float] = Field(default_factory=dict)
    rules_violated: list[str] = Field(default_factory=list)
    quirks_matched: list[str] = Field(default_factory=list)
    overall_score: float = 0.0
    issues: list[str] = Field(default_factory=list)
    rewritten: str | None = None


_TRAIT_CHECKS: dict[str, list[tuple[str, float, str]]] = {
    "calm": [
        (r"!+", 0.15, "exclamation marks"),
        (r"\b[A-Z]{3,}\b", 0.10, "ALL CAPS words"),
        (r"\b(ridiculous|outrageous|unbelievable)\b", 0.20, "extreme language"),
    ],
    "precise": [
        (r"\b(maybe|perhaps|sort of|kind of|basically|essentially)\b", 0.15, "vague language"),
        (r"\b(some|several|many|various)\b", 0.05, "imprecise quantifier"),
    ],
    "dry": [
        (r"(?:^|\.)\s*[A-Z][^.]*!{2,}", 0.20, "excessive humor/punchline"),
        (r"\b(lol|lmao|rofl|haha|hehe)\b", 0.30, "informal laughter"),
    ],
    "efficient": [
        (r"\b(in order to|due to the fact that|at this point in time)\b", 0.10, "verbose phrase"),
    ],
    "language": [
        (r"[\U0001F300-\U0001FAFF]", 0.50, "emoji usage"),
        (r"\b(um+|uh+|like|you know|i mean)\b", 0.20, "filler word"),
    ],
}

_FILLER_WORDS = {"um", "uh", "like", "you know", "i mean", "sort of", "kind of"}


class ConsistencyEnforcer:
    def __init__(self, card: CharacterCard):
        self._card = card
        weights = CONFIG.get("personality", {}).get("consistency_weights", {})
        self._w_trait = weights.get("trait", 0.40)
        self._w_rules = weights.get("rules", 0.35)
        self._w_quirks = weights.get("quirks", 0.15)
        self._w_speech = weights.get("speech", 0.10)
        self._threshold = CONFIG.get("personality", {}).get("consistency_threshold", 0.70)

    def check(self, response: str, user_message: str | None = None, sentiment: str = "neutral") -> ConsistencyResult:
        trait_scores = self._check_traits(response, sentiment)
        rules_violated = self._check_rules(response)
        quirks_matched = self._check_quirks(response, user_message) if user_message else []
        speech_score = self._check_speech_patterns(response)

        trait_score = sum(trait_scores.values()) / max(len(trait_scores), 1)
        rules_score = 1.0 - (len(rules_violated) / max(len(self._card.rules), 1))
        quirks_score = 1.0 if not quirks_matched else 1.0 - (len(quirks_matched) * 0.15)
        overall = (
            trait_score * self._w_trait
            + rules_score * self._w_rules
            + quirks_score * self._w_quirks
            + speech_score * self._w_speech
        )

        issues = []
        if trait_score < 0.7:
            issues.append(f"Low trait adherence ({trait_score:.2f})")
        if rules_violated:
            issues.append(f"Rules violated: {', '.join(rules_violated)}")
        if quirks_matched:
            issues.append(f"Missing quirk responses: {', '.join(quirks_matched)}")
        if speech_score < 0.7:
            issues.append(f"Speech pattern violations ({speech_score:.2f})")

        result = ConsistencyResult(
            passed=overall >= self._threshold,
            trait_scores=trait_scores,
            rules_violated=rules_violated,
            quirks_matched=quirks_matched,
            overall_score=overall,
            issues=issues,
        )

        if result.passed:
            logger.debug("[ConsistencyEnforcer] PASSED (score={:.2f})", overall)
        elif overall >= self._threshold * 0.72:
            logger.info("[ConsistencyEnforcer] REWRITING (score={:.2f})", overall)
            result.rewritten = self._llm_rewrite(response, issues)
        else:
            logger.warning("[ConsistencyEnforcer] FAILED (score={:.2f}) — logging violation", overall)

        return result

    def _check_traits(self, response: str, sentiment: str) -> dict[str, float]:
        scores = {}
        active_traits = self._card.get_traits_for(sentiment)
        for trait_name in active_traits:
            checks = _TRAIT_CHECKS.get(trait_name, [])
            if not checks:
                scores[trait_name] = 1.0
                continue
            penalties = 0.0
            for pattern, penalty, _ in checks:
                matches = re.findall(pattern, response)
                penalties += len(matches) * penalty
            scores[trait_name] = max(0.0, 1.0 - penalties)
        return scores

    def _check_rules(self, response: str) -> list[str]:
        violated = []
        for rule in self._card.rules:
            rule_lower = rule.lower()
            if "never say" in rule_lower and "i cannot" in rule_lower:
                if "i cannot" in response.lower() or "i can't" in response.lower():
                    violated.append(rule)
            if "never apologize" in rule_lower:
                if re.search(r"\b(sorry|my apologies|apologize)\b", response.lower()):
                    violated.append(rule)
            if "never use emoji" in rule_lower:
                if re.search(r"[\U0001F300-\U0001FAFF]", response):
                    violated.append(rule)
            if "use 'sir' at most once" in rule_lower:
                count = len(re.findall(r"\bsir\b", response.lower()))
                if count > 1:
                    violated.append(rule)
            if "no greetings" in rule_lower:
                if re.match(r"^(hi|hello|hey|greetings)\b", response.lower()):
                    violated.append(rule)
            if "one sentence maximum" in rule_lower:
                sentences = len(re.findall(r'[.!?]+', response))
                if sentences > 1:
                    violated.append(rule)
        return violated

    def _check_quirks(self, response: str, user_message: str | None) -> list[str]:
        if not user_message:
            return []
        unmatched = []
        lower_user = user_message.lower()
        lower_resp = response.lower()
        for quirk in self._card.quirks:
            if quirk.count == "never":
                continue
            trigger_words = quirk.trigger.replace("user says ", "").replace("'", "").split("|")
            if any(tw.strip() in lower_user for tw in trigger_words):
                quirk_resp = quirk.response.lower()[:20]
                if quirk_resp not in lower_resp:
                    unmatched.append(f"expected quirk for '{quirk.trigger}': '{quirk.response}'")
        return unmatched

    def _check_speech_patterns(self, response: str) -> float:
        penalties = 0.0
        patterns = self._card.speech_patterns

        if patterns.filler_words == "none":
            words = set(re.findall(r'\b\w+\b', response.lower()))
            fillers = words & _FILLER_WORDS
            penalties += len(fillers) * 0.15

        if patterns.emoji == "never":
            emoji = re.findall(r"[\U0001F300-\U0001FAFF]", response)
            penalties += len(emoji) * 0.25

        if patterns.contractions == "minimal":
            contractions = re.findall(r"\b\w+'\w+\b", response.lower())
            common = {"it's", "that's", "don't", "doesn't", "isn't", "won't", "can't", "i'm", "you're"}
            contraction_count = sum(1 for c in contractions if c in common)
            if contraction_count > len(response.split()) * 0.05:
                penalties += 0.10

        return max(0.0, 1.0 - penalties)

    def _llm_rewrite(self, response: str, issues: list[str]) -> str:
        try:
            import httpx
            prompt = (
                f"Rewrite this response to better match VECTOR's character. "
                f"Issues to fix: {'; '.join(issues)}\n\n"
                f"Keep the same information but adjust the tone, style, and wording. "
                f"Be concise. Use 'sir' appropriately.\n\nOriginal: {response}"
            )
            resp = httpx.post(
                f"{CONFIG['ollama_host']}/api/generate",
                json={
                    "model": CONFIG["models"]["focus"],
                    "prompt": prompt,
                    "stream": False,
                    "system": "You are VECTOR — calm, precise, efficient. Never use emoji. Use 'sir' at most once.",
                },
                timeout=10.0,
            )
            if resp.status_code == 200:
                rewritten = resp.json().get("response", "")
                if rewritten:
                    return rewritten.strip()
        except Exception as e:
            logger.debug("[ConsistencyEnforcer] rewrite failed: {}", e)
        return response
