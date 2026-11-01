"""Pydantic character card schema + loader for VECTOR's personality."""

from __future__ import annotations

__all__ = [
    "CharacterCard",
    "Quirk",
    "SpeechPatterns",
    "ToneProfile",
]


import json
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field, model_validator


class ToneProfile(BaseModel):
    tone: str
    speed: float = Field(ge=0.5, le=1.5)
    traits_to_emphasize: list[str] = Field(default_factory=list)
    traits_to_suppress: list[str] = Field(default_factory=list)
    rules_to_activate: list[str] = Field(default_factory=list)


class Quirk(BaseModel):
    trigger: str
    response: str
    count: str = "sometimes"  # always | sometimes | never


class SpeechPatterns(BaseModel):
    address_owner: str = "sir"
    contractions: str = "minimal"  # minimal | none | relaxed
    filler_words: str = "none"
    emoji: str = "never"


class CharacterCard(BaseModel):
    name: str = "VECTOR"
    full_name: str = "Virtual Entity for Cognitive Tasks & Operational Reasoning"
    owner: str = "Arghyadeep Deb"
    creator: str = "Arghyadeep Deb"
    species: str = "Digital Intelligence"
    platform: str = "Legion Pro 5 (RTX 5070 Ti 12GB)"
    backstory: str = ""
    version: str = "1.0"
    knowledge_boundaries: dict[str, str] = Field(default_factory=dict)

    traits: dict[str, float] = Field(default_factory=lambda: {
        "calm": 0.95, "precise": 0.90, "dry": 0.75, "efficient": 0.85,
        "attentive": 0.80, "loyal": 0.95, "curious": 0.70,
        "patient": 0.85, "protective": 0.60, "witty": 0.40,
    })
    speech_patterns: SpeechPatterns = Field(default_factory=SpeechPatterns)
    rules: list[str] = Field(default_factory=list)
    boundaries: list[str] = Field(default_factory=list)
    tone_mapping: dict[str, ToneProfile] = Field(default_factory=dict)
    quirks: list[Quirk] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_traits(self):
        for name, score in self.traits.items():
            if not 0.0 <= score <= 1.0:
                raise ValueError(f"Trait '{name}' score {score} out of range [0, 1]")
        return self

    def get_traits_for(self, sentiment: str) -> dict[str, float]:
        profile = self.tone_mapping.get(sentiment)
        if not profile:
            return dict(self.traits)
        result = dict(self.traits)
        for t in profile.traits_to_suppress:
            result.pop(t, None)
        for t in profile.traits_to_emphasize:
            if t in self.traits:
                result[t] = min(1.0, result.get(t, 0) + 0.10)
        return result

    def get_rules_for(self, sentiment: str) -> list[str]:
        profile = self.tone_mapping.get(sentiment)
        if not profile:
            return list(self.rules)
        active = list(self.rules)
        active.extend(profile.rules_to_activate)
        return active

    @classmethod
    def load(cls, path: str | Path) -> CharacterCard:
        path = Path(path)
        if not path.exists():
            logger.warning("[CharacterCard] not found at {}, using defaults", path)
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        card = cls.model_validate(data)
        logger.info("[CharacterCard] loaded from {} (v{})", path, card.version)
        return card

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        logger.info("[CharacterCard] saved to {}", path)

    def get_traits_summary(self) -> str:
        sorted_traits = sorted(self.traits.items(), key=lambda x: -x[1])
        return "; ".join(f"{t}: {s:.0%}" for t, s in sorted_traits)
