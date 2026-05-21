from pathlib import Path

from core.personality.character_card import CharacterCard
from core.personality.sentiment import SentimentResult
from core.personality.tone_adapter import ToneAdapter, ToneConfig


def _card_path() -> Path:
    return Path(__file__).parent.parent.parent / "core" / "personality" / "characters" / "vector.json"


def _loaded_card() -> CharacterCard:
    return CharacterCard.load(_card_path())


def test_neutral_sentiment_returns_default_config():
    card = CharacterCard()
    adapter = ToneAdapter(card)
    sentiment = SentimentResult(emotion="neutral", intensity=0.0, urgency=0.0, confidence=0.0)
    config = adapter.get_config(sentiment)
    assert config.tone == "default_precise"
    assert config.speed == 0.85


def test_happy_sentiment_mapping():
    card = _loaded_card()
    adapter = ToneAdapter(card)
    sentiment = SentimentResult(emotion="happy", intensity=0.7, urgency=0.0, confidence=0.8)
    config = adapter.get_config(sentiment)
    assert config.tone == "crisp_efficient"
    assert "efficient" in config.emphasized_traits


def test_frustrated_sentiment_mapping():
    card = _loaded_card()
    adapter = ToneAdapter(card)
    sentiment = SentimentResult(emotion="frustrated", intensity=0.8, urgency=0.0, confidence=0.9)
    config = adapter.get_config(sentiment)
    assert "patient" in config.emphasized_traits
    assert "witty" in config.suppressed_traits


def test_urgent_speed_boost():
    card = _loaded_card()
    adapter = ToneAdapter(card)
    sentiment = SentimentResult(emotion="urgent", intensity=0.9, urgency=0.8, confidence=0.9)
    config = adapter.get_config(sentiment)
    assert config.speed > 0.85


def test_compose_system_prompt_contains_character_info():
    card = _loaded_card()
    adapter = ToneAdapter(card)
    sentiment = SentimentResult(emotion="neutral", intensity=0.0, urgency=0.0, confidence=0.0)
    prompt = adapter.compose_system_prompt(card, sentiment)
    assert "VECTOR" in prompt
    assert "Arghyadeep" in prompt
    assert "CORE TRAITS" in prompt
    assert "RULES" in prompt


def test_compose_system_prompt_emotion_section():
    card = _loaded_card()
    adapter = ToneAdapter(card)
    sentiment = SentimentResult(emotion="frustrated", intensity=0.8, urgency=0.0, confidence=0.9)
    prompt = adapter.compose_system_prompt(card, sentiment)
    assert "FRUSTRATED" in prompt
    assert "EMPHASIZED TRAITS" in prompt


def test_compose_system_prompt_speech_patterns():
    card = _loaded_card()
    adapter = ToneAdapter(card)
    sentiment = SentimentResult(emotion="neutral", intensity=0.0, urgency=0.0, confidence=0.0)
    prompt = adapter.compose_system_prompt(card, sentiment)
    assert "sir" in prompt
    assert "emoji" in prompt


def test_inject_learned_preferences():
    card = _loaded_card()
    adapter = ToneAdapter(card)
    preferences = [
        {"context": "debugging", "response_type": "concise", "confidence": 0.85},
    ]
    adapter.inject_learned_preferences(preferences)
    sentiment = SentimentResult(emotion="frustrated", intensity=0.7, urgency=0.0, confidence=0.8)
    config = adapter.get_config(sentiment)
    expected_rules = len(card.tone_mapping["frustrated"].rules_to_activate)
    assert len(config.active_rules) >= expected_rules


def test_inject_learned_preferences_in_prompt():
    card = _loaded_card()
    adapter = ToneAdapter(card)
    preferences = [
        {"context": "debugging", "response_type": "concise", "confidence": 0.85},
    ]
    adapter.inject_learned_preferences(preferences)
    sentiment = SentimentResult(emotion="frustrated", intensity=0.7, urgency=0.0, confidence=0.8)
    prompt = adapter.compose_system_prompt(card, sentiment)
    assert "LEARNED PREFERENCES" in prompt


def test_unknown_emotion_falls_back():
    card = CharacterCard()
    adapter = ToneAdapter(card)
    sentiment = SentimentResult(emotion="nonexistent", intensity=0.0, urgency=0.0, confidence=0.0)
    config = adapter.get_config(sentiment)
    assert config.tone == "default_precise"


def test_tone_config_model():
    config = ToneConfig(tone="test", speed=1.2, emphasized_traits=["calm"])
    assert config.tone == "test"
    assert config.speed == 1.2
    assert config.emphasized_traits == ["calm"]
