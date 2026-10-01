"""Regression test for EntityMatcher._score()/match() failing to resolve a
voice phrase that starts with a stop word ("the"/"a"/"an"), found while
investigating a full-suite failure surfaced after merging the Phase 3
whole-repo audit's cloud-session districts batch (2026-10-01).

Not a regression from that batch: EntityMatcher.match("the fan", ...)
already returned no match against entity "switch.fan" (friendly_name
"Bedroom Fan") on the pre-batch code too -- verified directly in an
isolated git worktree at the pre-merge commit. The batch's
districts/home_assistant/voice_bridge.py fix correctly stopped executing a
service call when entity resolution fails (closing a real "phantom
success" bug: the old code fired a Home Assistant service call using the
unresolved raw text "the fan" as a fake entity_id, which the old
tests/integration/test_spec08_home_assistant.py::test_turn_off_entity only
verified as "a call happened", not "the right entity was found"). That
correctness fix surfaced this separate, pre-existing matcher bug as a test
failure.

Fixed by stripping a leading stop word before scoring, so "turn off the
fan" can resolve to "Bedroom Fan" when it's the only candidate.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.home_assistant.entity_manager import EntityManager, HAEntity


def _manager_with_fan() -> EntityManager:
    mgr = EntityManager()
    mgr.registry.add(HAEntity(
        "switch.fan", "on",
        attributes={"friendly_name": "Bedroom Fan", "area": "bedroom"},
    ))
    return mgr


def test_the_prefix_resolves_against_friendly_name():
    mgr = _manager_with_fan()
    matches = mgr.matcher.match("the fan")
    assert matches, "expected at least one match for 'the fan' against 'Bedroom Fan'"
    entity, score = matches[0]
    assert entity.entity_id == "switch.fan"
    assert score > 0


def test_a_and_an_prefixes_also_stripped():
    mgr = _manager_with_fan()
    assert mgr.matcher.match("a fan")
    assert mgr.matcher.match("an fan")  # grammatically odd but must not crash / must still strip


def test_bare_phrase_without_stopword_still_works():
    mgr = _manager_with_fan()
    matches = mgr.matcher.match("fan")
    assert matches
    assert matches[0][0].entity_id == "switch.fan"


def test_exact_name_match_unaffected_by_stopword_stripping():
    mgr = _manager_with_fan()
    matches = mgr.matcher.match("bedroom fan")
    assert matches
    entity, score = matches[0]
    assert entity.entity_id == "switch.fan"
    assert score == 1.0  # exact friendly_name match, highest possible score


def test_no_false_positive_on_unrelated_phrase():
    mgr = _manager_with_fan()
    matches = mgr.matcher.match("the kitchen light")
    assert not matches or matches[0][1] <= 0.3  # no strong match for an unrelated entity


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
