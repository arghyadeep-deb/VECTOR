"""
Regression tests for the learning-district fake-success-stub bug.

AgentBase.run() (core/city/agent_base.py) defines a generic fallback that
returns {"status": "ok", "agent": self.name, "task": task} without doing any
real work. Two learning-district classes overrode run() with a broken
hasattr() guard checking for a method name that doesn't exist on the class
at all (a typo/placeholder that always evaluates False), so run() always
fell through to the AgentBase stub shape regardless of task content:
  - ConceptExtractor.run() checked hasattr(self, "extract") — the real
    method is extract_concepts(); "extract" never exists, so the branch
    was always dead code.
  - NoteOrganizer.run() checked hasattr(self, "organise") — the real
    method is organize_notes() (American spelling); "organise" never
    exists, so the branch was always dead code.

These tests assert that run() now branches on task["type"] and dispatches
to the class's real, existing methods, and that an unrecognized type
returns the standard error shape instead of silently falling through.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.learning.concept_extractor import ConceptExtractor
from districts.learning.note_organizer import NoteOrganizer


# ---------------------------------------------------------------------------
# ConceptExtractor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concept_extractor_run_extract_concepts_routes_correctly():
    agent = ConceptExtractor()
    result = await agent.run({
        "type": "extract_concepts",
        "params": {"text": "Neural networks are a subset of machine learning."},
    })
    assert result["status"] == "ok"
    assert "concepts" in result or "count" in result


@pytest.mark.asyncio
async def test_concept_extractor_run_suggest_prerequisites_routes_correctly():
    agent = ConceptExtractor()
    result = await agent.run({
        "type": "suggest_prerequisites",
        "params": {"concept": "deep learning"},
    })
    assert result["status"] == "ok"
    assert "concept" in result
    assert result["concept"] == "deep learning"


@pytest.mark.asyncio
async def test_concept_extractor_run_unhandled_type_returns_error_shape():
    agent = ConceptExtractor()
    result = await agent.run({"type": "totally_bogus_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


# ---------------------------------------------------------------------------
# NoteOrganizer
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_note_organizer_run_link_notes_routes_correctly():
    agent = NoteOrganizer()
    result = await agent.run({
        "type": "link_notes",
        "params": {"concept_a": "machine learning", "concept_b": "statistics"},
    })
    assert result["status"] == "ok"
    assert "relationship" in result
    assert result["bidirectional"] is True


@pytest.mark.asyncio
async def test_note_organizer_run_summarize_notes_routes_correctly():
    agent = NoteOrganizer()
    result = await agent.run({
        "type": "summarize_notes",
        "params": {"topic": "config"},
    })
    assert result["status"] == "ok"
    assert "summary" in result


@pytest.mark.asyncio
async def test_note_organizer_run_unhandled_type_returns_error_shape():
    agent = NoteOrganizer()
    result = await agent.run({"type": "not_a_real_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
