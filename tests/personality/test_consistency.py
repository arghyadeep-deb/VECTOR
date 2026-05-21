from pathlib import Path

from core.personality.character_card import CharacterCard
from core.personality.consistency import ConsistencyEnforcer, ConsistencyResult


def _card_path() -> Path:
    return Path(__file__).parent.parent.parent / "core" / "personality" / "characters" / "vector.json"


def _make_card() -> CharacterCard:
    return CharacterCard(
        traits={"calm": 0.95, "precise": 0.90, "efficient": 0.85},
        rules=[
            "Never say 'I cannot' — find the nearest useful action instead",
            "Never apologize unless VECTOR made an error",
            "Never use emoji in any response",
            "Use 'sir' at most once per response, preferably first sentence",
        ],
        speech_patterns={"address_owner": "sir", "contractions": "minimal", "filler_words": "none", "emoji": "never"},
    )


def test_check_trait_calm_violation():
    card = _make_card()
    enforcer = ConsistencyEnforcer(card)
    result = enforcer.check("That is RIDICULOUS!!!")
    assert "calm" in result.trait_scores
    assert result.trait_scores["calm"] < 1.0


def test_check_trait_precise_violation():
    card = _make_card()
    enforcer = ConsistencyEnforcer(card)
    result = enforcer.check("Maybe it's sort of working, perhaps?")
    assert result.trait_scores.get("precise", 1.0) < 1.0


def test_check_rules_violation_i_cannot():
    card = _make_card()
    enforcer = ConsistencyEnforcer(card)
    result = enforcer.check("I cannot do that, sir.")
    assert len(result.rules_violated) > 0


def test_check_rules_violation_apology():
    card = _make_card()
    enforcer = ConsistencyEnforcer(card)
    result = enforcer.check("Sorry, I apologize for the error.")
    assert len(result.rules_violated) > 0


def test_check_rules_violation_emoji():
    card = _make_card()
    enforcer = ConsistencyEnforcer(card)
    result = enforcer.check("That works! 😊")
    assert len(result.rules_violated) > 0


def test_check_rules_sir_at_most_once():
    card = _make_card()
    enforcer = ConsistencyEnforcer(card)
    result = enforcer.check("Sir, I did that sir. Is there anything else sir?")
    assert len(result.rules_violated) > 0


def test_check_passes_clean_response():
    card = _make_card()
    enforcer = ConsistencyEnforcer(card)
    result = enforcer.check("Done, sir.")
    assert result.passed is True
    assert result.overall_score >= 0.70


def test_quirk_detection():
    card = CharacterCard.load(_card_path())
    enforcer = ConsistencyEnforcer(card)
    result = enforcer.check("Done.", user_message="good morning")
    assert len(result.quirks_matched) > 0


def test_quirk_not_triggered_when_no_user_message():
    card = CharacterCard.load(_card_path())
    enforcer = ConsistencyEnforcer(card)
    result = enforcer.check("Done.")
    assert len(result.quirks_matched) == 0


def test_llm_rewrite_on_mid_score():
    card = _make_card()
    enforcer = ConsistencyEnforcer(card)
    result = enforcer.check("Sorry, I cannot do that, sir. That is ridiculous!!!")
    assert len(result.issues) > 0


def test_consistency_result_fields():
    r = ConsistencyResult(passed=True, overall_score=0.95)
    assert r.passed is True
    assert r.overall_score == 0.95


def test_speech_contractions_minimal():
    card = CharacterCard()
    enforcer = ConsistencyEnforcer(card)
    score = enforcer._check_speech_patterns("That is working and it is fine.")
    assert score >= 0.9


def test_trait_check_empty_response():
    card = _make_card()
    enforcer = ConsistencyEnforcer(card)
    result = enforcer.check("")
    assert result.passed is True


def test_check_speech_has_penalty():
    card = CharacterCard(
        speech_patterns={"address_owner": "sir", "contractions": "minimal", "filler_words": "none", "emoji": "never"},
    )
    enforcer = ConsistencyEnforcer(card)
    score = enforcer._check_speech_patterns("Um, like, that is working")
    assert score < 1.0
