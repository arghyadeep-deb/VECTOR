"""Regression for core/personality/consistency.py's _check_rules():

Two rule checks used unanchored substring/prefix matching instead of word
boundaries, the same bug class already fixed in memory_persona.py this
cycle:

1. "use 'sir' at most once" counted the substring "sir" anywhere in the
   response -- a reply containing "desirable"/"elixir"/"siren" (each
   contains the literal substring "sir") inflated the count and could
   falsely flag the rule as violated even when the actual address term
   "sir" appeared once or not at all.

2. "no greetings" matched `^(hi|hello|hey|greetings)` with no trailing
   word boundary -- any response starting with "History", "Hint",
   "Highway", etc. (each starts with "hi") was falsely flagged as an
   unwanted greeting.

This path is live: core/personality/__init__.py's validate_response() ->
ConsistencyEnforcer.check() -> _check_rules() is called on every voice
response via core/api/routers/voice.py, voice_ws.py, and
core/personality/middleware.py.
"""
from __future__ import annotations

from core.personality.character_card import CharacterCard
from core.personality.consistency import ConsistencyEnforcer


def _card_with_rules() -> CharacterCard:
    return CharacterCard(
        rules=[
            "Use 'sir' at most once per response, preferably first sentence",
            "No greetings at the start of a response",
        ],
    )


def test_sir_substring_in_other_words_not_counted_as_address_term():
    card = _card_with_rules()
    enforcer = ConsistencyEnforcer(card)
    # "desirable" and "siren" each contain the substring "sir" (2 total),
    # but the actual address term "sir" never appears as a standalone word.
    result = enforcer.check("That would be a desirable outcome; the alarm sounded like a siren.")
    assert not any("sir" in v.lower() for v in result.rules_violated)


def test_sir_used_twice_as_a_real_word_is_still_flagged():
    card = _card_with_rules()
    enforcer = ConsistencyEnforcer(card)
    result = enforcer.check("Sir, I did that. Anything else, sir?")
    assert any("sir" in v.lower() for v in result.rules_violated)


def test_response_starting_with_history_is_not_a_false_greeting():
    card = _card_with_rules()
    enforcer = ConsistencyEnforcer(card)
    result = enforcer.check("History shows this approach rarely works.")
    assert not any("greeting" in v.lower() for v in result.rules_violated)


def test_response_starting_with_hint_is_not_a_false_greeting():
    card = _card_with_rules()
    enforcer = ConsistencyEnforcer(card)
    result = enforcer.check("Hint: check the config file first.")
    assert not any("greeting" in v.lower() for v in result.rules_violated)


def test_response_starting_with_an_actual_greeting_is_still_flagged():
    card = _card_with_rules()
    enforcer = ConsistencyEnforcer(card)
    result = enforcer.check("Hi there, how can I help?")
    assert any("greeting" in v.lower() for v in result.rules_violated)
