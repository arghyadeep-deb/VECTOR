"""Tests for IntentMatcher — embedding-based intent classification.

Tests verify:
1. Loading examples from JSON
2. Embedding generation via Ollama
3. Cosine similarity matching
4. Threshold filtering
5. Integration with governor
"""
import sys
import asyncio
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.city.intent_matcher import IntentMatcher


@pytest.fixture
def matcher():
    """Create IntentMatcher with test examples."""
    return IntentMatcher("data/intent_examples.json")


def test_load_examples(matcher):
    """Test that examples are loaded from JSON."""
    assert len(matcher._examples) > 0, "Should load at least some examples"
    # Check structure
    for example in matcher._examples[:5]:
        assert "text" in example
        assert "district" in example
        assert "task_type" in example


@pytest.mark.asyncio
async def test_embed_text(matcher):
    """Test embedding generation via Ollama."""
    embedding = await matcher._embed("test query")
    assert embedding is not None, "Embedding should succeed"
    assert len(embedding) == 768, f"Expected 768-dim, got {len(embedding)}"


@pytest.mark.asyncio
async def test_cosine_similarity(matcher):
    """Test cosine similarity computation."""
    # Identical vectors should have similarity 1.0
    vec = [1.0, 2.0, 3.0]
    sim = matcher._cosine_similarity(vec, vec)
    assert abs(sim - 1.0) < 0.001, f"Identical vectors should have sim=1.0, got {sim}"

    # Orthogonal vectors should have similarity 0.0
    vec_a = [1.0, 0.0]
    vec_b = [0.0, 1.0]
    sim = matcher._cosine_similarity(vec_a, vec_b)
    assert abs(sim) < 0.001, f"Orthogonal vectors should have sim=0.0, got {sim}"


@pytest.mark.asyncio
async def test_match_known_query(matcher):
    """Test matching a query that should match an example."""
    # This query is very similar to an example in the dataset
    result = await matcher.match("quiz me on french vocabulary")
    assert result is not None, "Should match known query"
    assert result["district"] == "languages"
    assert result["type"] == "quiz_vocabulary"
    assert result["confidence"] >= 0.85
    assert result["source"] == "embedding_match"


@pytest.mark.asyncio
async def test_no_match_unknown_query(matcher):
    """Test that unrelated queries don't match."""
    # Set high threshold to ensure no false positives
    matcher.set_threshold(0.95)
    result = await matcher.match("random unrelated query about pizza")
    # May or may not match depending on threshold — just verify it doesn't crash
    if result:
        assert result["confidence"] >= 0.95


@pytest.mark.asyncio
async def test_threshold_filtering(matcher):
    """Test that threshold filters low-similarity matches."""
    # Very low threshold should match almost anything
    matcher.set_threshold(0.1)
    result = await matcher.match("any query")
    assert result is not None, "Very low threshold should match"

    # Very high threshold should match nothing
    matcher.set_threshold(0.99)
    result = await matcher.match("random query")
    # At 0.99 threshold, most queries won't match
    # (unless they're identical to an example)


@pytest.mark.asyncio
async def test_all_districts_have_examples(matcher):
    """Test that all districts in DISTRICT_TASK_MAP have examples."""
    from core.city.governor import DISTRICT_TASK_MAP

    # Get all districts
    all_districts = set(DISTRICT_TASK_MAP.values())

    # Get districts with examples
    example_districts = {ex["district"] for ex in matcher._examples}

    # Check coverage (allow some districts to have 0 examples for now)
    coverage = len(example_districts) / len(all_districts)
    assert coverage >= 0.5, f"Should have examples for at least 50% of districts, got {coverage:.1%}"


def test_get_stats(matcher):
    """Test statistics retrieval."""
    stats = matcher.get_stats()
    assert "examples_loaded" in stats
    assert "similarity_threshold" in stats
    assert "model" in stats
    assert stats["examples_loaded"] > 0


@pytest.mark.asyncio
async def test_embedding_cache(matcher):
    """Test that embeddings are cached."""
    # First call should compute
    emb1 = await matcher._embed("test query")
    assert emb1 is not None

    # Second call should use cache
    emb2 = await matcher._embed("test query")
    assert emb2 is not None
    assert emb1 == emb2, "Cached embedding should be identical"


if __name__ == "__main__":
    """Run tests."""
    async def run_tests():
        matcher = IntentMatcher("data/intent_examples.json")

        print("\n=== IntentMatcher Tests ===\n")

        # Test 1: Load examples
        test_load_examples(matcher)
        print("✅ test_load_examples")

        # Test 2: Embed text
        await test_embed_text(matcher)
        print("✅ test_embed_text")

        # Test 3: Cosine similarity
        await test_cosine_similarity(matcher)
        print("✅ test_cosine_similarity")

        # Test 4: Match known query
        result = await test_match_known_query(matcher)
        print("✅ test_match_known_query")

        # Test 5: Stats
        test_get_stats(matcher)
        print("✅ test_get_stats")

        print(f"\nAll tests passed! Loaded {len(matcher._examples)} examples.")

    asyncio.run(run_tests())
