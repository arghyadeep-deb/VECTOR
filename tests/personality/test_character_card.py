import tempfile
from pathlib import Path

from loguru import logger
from core.personality.character_card import CharacterCard


def _card_path() -> Path:
    return Path(__file__).parent.parent.parent / "core" / "personality" / "characters" / "vector.json"


def test_load_vector_json():
    card = CharacterCard.load(_card_path())
    assert card.name == "VECTOR"
    assert card.owner == "Arghyadeep Deb"
    assert card.creator == "Arghyadeep Deb"
    assert card.species == "Digital Intelligence"
    assert card.platform == "Legion Pro 5 (RTX 5070 Ti 12GB)"
    assert "calm" in card.traits
    assert card.traits["calm"] == 0.95
    # 2026-07-28 (issue #37): 2 rules added to the base array (English-only,
    # spoken-text-safety for voice mode) — 6 -> 8, a deliberate content
    # change, not a regression.
    assert len(card.rules) == 8
    assert len(card.quirks) == 7
    assert len(card.tone_mapping) == 6
    assert "knowledge_boundaries" in card.model_fields


def test_get_traits_for_neutral():
    card = CharacterCard.load(_card_path())
    traits = card.get_traits_for("neutral")
    assert len(traits) >= len(card.traits) - 1
    for t in card.traits:
        if t in traits:
            assert traits[t] >= card.traits[t]


def test_get_traits_for_happy():
    card = CharacterCard.load(_card_path())
    traits = card.get_traits_for("happy")
    suppressed = card.tone_mapping["happy"].traits_to_suppress
    for t in suppressed:
        assert t not in traits, f"trait {t} should be suppressed"
    emphasized = card.tone_mapping["happy"].traits_to_emphasize
    for t in emphasized:
        if t in card.traits:
            assert traits[t] >= card.traits[t], f"trait {t} should be emphasized"


def test_get_traits_for_unknown():
    card = CharacterCard()
    traits = card.get_traits_for("nonexistent")
    assert traits == dict(card.traits)


def test_save_load_round_trip():
    card = CharacterCard()
    card.name = "TestVECTOR"
    card.traits["calm"] = 0.99
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        path = f.name
    try:
        card.save(path)
        loaded = CharacterCard.load(path)
        assert loaded.name == "TestVECTOR"
        assert loaded.traits["calm"] == 0.99
    finally:
        Path(path).unlink(missing_ok=True)


def test_load_nonexistent_path():
    card = CharacterCard.load("/nonexistent/path.json")
    assert card.name == "VECTOR"


def test_validation_failure_on_bad_trait():
    import pydantic
    try:
        CharacterCard(traits={"calm": 1.5})
        assert False, "should have raised"
    except pydantic.ValidationError:
        logger.debug("[VECTOR] suppressed exception", exc_info=True)


def test_get_traits_summary():
    card = CharacterCard()
    summary = card.get_traits_summary()
    assert "calm" in summary
    assert "%" in summary


def test_get_rules_for_sentiment():
    card = CharacterCard.load(_card_path())
    rules = card.get_rules_for("frustrated")
    assert len(rules) >= len(card.rules)


def test_default_character_card():
    card = CharacterCard()
    assert card.knowledge_boundaries == {}
    assert card.creator == "Arghyadeep Deb"
    assert card.species == "Digital Intelligence"
    assert card.platform == "Legion Pro 5 (RTX 5070 Ti 12GB)"
