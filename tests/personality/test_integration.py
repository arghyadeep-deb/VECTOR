from pathlib import Path

from core.personality import PersonalityEngine
from core.personality.sentiment import SentimentResult
from core.personality.tone_adapter import ToneConfig


def _card_path() -> Path:
    return Path(__file__).parent.parent.parent / "core" / "personality" / "characters" / "vector.json"


def test_full_pipeline_text_to_prompt():
    engine = PersonalityEngine(str(_card_path()))
    result = engine.process("That is great! Thanks!")
    assert "sentiment" in result
    assert isinstance(result["tone_config"], ToneConfig)
    assert isinstance(result["system_prompt"], str)
    assert "VECTOR" in result["system_prompt"]


def test_full_pipeline_frustrated():
    engine = PersonalityEngine(str(_card_path()))
    result = engine.process("This is broken and frustrating!")
    assert result["sentiment"].emotion in ("frustrated", "neutral")


def test_full_pipeline_neutral():
    engine = PersonalityEngine(str(_card_path()))
    result = engine.process("What is the time?")
    assert result["sentiment"].emotion in ("neutral", "curious")


def test_process_returns_all_keys():
    engine = PersonalityEngine(str(_card_path()))
    result = engine.process("Hello")
    assert "sentiment" in result
    assert "tone_config" in result
    assert "system_prompt" in result
    assert "preferences" in result


def test_validate_response_passes():
    engine = PersonalityEngine(str(_card_path()))
    result = engine.validate_response("Done, sir.")
    assert result["passed"] is True
    assert result["overall_score"] >= 0.70


def test_validate_response_contains_rewritten():
    engine = PersonalityEngine(str(_card_path()))
    result = engine.validate_response("Done, sir.", user_message="good morning")
    assert "rewritten" in result


def test_process_with_personality():
    engine = PersonalityEngine(str(_card_path()))
    system_prompt, tone_config = engine.process_with_personality("Explain quantum computing")
    assert system_prompt is not None
    assert "VECTOR" in system_prompt
    assert isinstance(tone_config, ToneConfig)


def test_compose_prompt():
    engine = PersonalityEngine(str(_card_path()))
    prompt = engine.compose_prompt("What is AI?")
    assert len(prompt) > 50
    assert "CORE TRAITS" in prompt


def test_orchestrator_full_cycle():
    engine = PersonalityEngine(str(_card_path()))
    result = engine.process("Tell me a joke")
    response = engine.validate_response("That is a terrible joke, sir.", user_message="Tell me a joke", sentiment="happy")
    assert "passed" in response
    assert result["tone_config"] is not None


def test_disabled_engine():
    import core.config
    old_enabled = core.config.CONFIG.get("personality", {}).get("enabled", True)
    try:
        core.config.CONFIG["personality"]["enabled"] = False
        engine = PersonalityEngine()
        result = engine.process("Hello")
        assert result["tone_config"].tone == "default_precise"
        response = engine.validate_response("anything")
        assert response["passed"] is True
    finally:
        core.config.CONFIG["personality"]["enabled"] = old_enabled
