import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import asyncio
import tempfile


# ── ConsolidationBot ──────────────────────────────────────────────────────────

def test_consolidation_bot_init():
    from agents.districts.memory_curator.consolidation_bot import ConsolidationBot
    bot = ConsolidationBot()
    assert bot.health_points == 500
    assert bot.name == "ConsolidationBot"
    assert bot.district == "memory_curator"
    assert bot.is_alive


def test_consolidation_bot_inherits_ghost():
    from agents.districts.memory_curator.consolidation_bot import ConsolidationBot
    ghost = {
        "lessons_learned": ["always verify before writing"],
        "best_decisions": [],
        "personality_traits": {"careful": True},
        "generation": 1,
    }
    bot = ConsolidationBot(generation=2, ghost=ghost)
    assert "always verify before writing" in bot.lessons


def test_write_daily_reflection_creates_vault_note():
    from agents.districts.memory_curator.consolidation_bot import ConsolidationBot
    bot = ConsolidationBot()
    bot._memory.store(
        event_type="task",
        content="test event for daily reflection",
        tags=["test"],
        source="test",
    )

    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Reflections").mkdir()
        bot._obsidian._vault = vault

        result = asyncio.run(bot.write_daily_reflection())
        assert result is True
        notes = list((vault / "Reflections").glob("Daily Reflection*.md"))
        assert notes, "No reflection note created"
        content = notes[0].read_text(encoding="utf-8")
        assert "source: vector" in content
        assert "---" in content  # frontmatter present


def test_write_daily_reflection_awards_hp():
    from agents.districts.memory_curator.consolidation_bot import ConsolidationBot
    bot = ConsolidationBot()
    initial_hp = bot.health_points

    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Reflections").mkdir()
        bot._obsidian._vault = vault

        asyncio.run(bot.write_daily_reflection())
        assert bot.health_points > initial_hp


def test_consolidate_old_episodes_stores_summary():
    from agents.districts.memory_curator.consolidation_bot import ConsolidationBot
    import datetime
    bot = ConsolidationBot()

    # Insert an episode with an old timestamp so it passes the cutoff filter
    old_ts = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=35)
    ).isoformat()
    episode_id = f"old-episode-smoke-{datetime.datetime.now(datetime.timezone.utc).timestamp()}"
    bot._memory.conn.execute(
        "INSERT INTO episodic_memory (id, event_type, content, tags, context_snapshot, timestamp, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (episode_id, "task", "very old smoke test event", None, None, old_ts, "test"),
    )
    bot._memory.conn.commit()

    count = asyncio.run(bot.consolidate_old_episodes())
    assert count >= 1

    # Verify stored in semantic_memory
    import datetime as dt
    key = f"consolidation:{dt.date.today().isoformat()}"
    fact = bot._memory.recall_fact(key)
    assert fact is not None


# ── PatternFinder ─────────────────────────────────────────────────────────────

def test_pattern_finder_init():
    from agents.districts.memory_curator.pattern_finder import PatternFinder
    bot = PatternFinder()
    assert bot.health_points == 500
    assert bot.name == "PatternFinder"
    assert bot.district == "memory_curator"
    assert bot.is_alive


def test_pattern_finder_inherits_ghost():
    from agents.districts.memory_curator.pattern_finder import PatternFinder
    ghost = {
        "lessons_learned": ["look for weekly cycles"],
        "best_decisions": [],
        "personality_traits": {},
        "generation": 1,
    }
    bot = PatternFinder(generation=2, ghost=ghost)
    assert "look for weekly cycles" in bot.lessons


def test_find_patterns_returns_list():
    from agents.districts.memory_curator.pattern_finder import PatternFinder
    bot = PatternFinder()

    for i in range(10):
        bot._memory.store(
            event_type=["task", "observe", "reflect", "vault_write"][i % 4],
            content=f"pattern smoke test event {i}",
            tags=["smoke"],
            source="test",
        )

    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Reflections").mkdir()
        bot._obsidian._vault = vault

        patterns = asyncio.run(bot.find_patterns(window_hours=8760))
        assert isinstance(patterns, list)


def test_find_patterns_too_few_episodes():
    from agents.districts.memory_curator.pattern_finder import PatternFinder
    from unittest.mock import patch
    bot = PatternFinder()
    # Force _fetch_window to return fewer than MIN_EPISODES (5) episodes
    with patch.object(bot, "_fetch_window", return_value=[{"event_type": "task", "content": "x", "timestamp": "2026-01-01T00:00:00"}]):
        patterns = asyncio.run(bot.find_patterns(window_hours=1))
    assert patterns == []


def test_find_patterns_changes_hp():
    from agents.districts.memory_curator.pattern_finder import PatternFinder
    bot = PatternFinder()
    initial_hp = bot.health_points

    for i in range(8):
        bot._memory.store(
            event_type="task",
            content=f"hp change test event {i}",
            tags=["test"],
            source="test",
        )

    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Reflections").mkdir()
        bot._obsidian._vault = vault

        asyncio.run(bot.find_patterns(window_hours=8760))
        assert bot.health_points != initial_hp


def test_find_patterns_writes_vault_note():
    from agents.districts.memory_curator.pattern_finder import PatternFinder
    bot = PatternFinder()

    for i in range(8):
        bot._memory.store(
            event_type="observe",
            content=f"vault note test event {i}",
            tags=["test"],
            source="test",
        )

    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Reflections").mkdir()
        bot._obsidian._vault = vault

        asyncio.run(bot.find_patterns(window_hours=8760))
        notes = list((vault / "Reflections").glob("Pattern Report*.md"))
        assert notes, "No pattern report written"


def test_get_stored_patterns_returns_list():
    from agents.districts.memory_curator.pattern_finder import PatternFinder
    bot = PatternFinder()
    result = bot.get_stored_patterns(days=30)
    assert isinstance(result, list)


def test_parse_patterns_structured():
    from agents.districts.memory_curator.pattern_finder import PatternFinder
    bot = PatternFinder()
    text = (
        "PATTERN: Late Night Coding\nOBSERVATION: Most commits after 10PM\nIMPACT: Sleep debt\n\n"
        "PATTERN: Context Switch\nOBSERVATION: YouTube after hard tasks\nIMPACT: 2h distraction\n"
    )
    patterns = bot._parse_patterns(text)
    assert "Late Night Coding" in patterns
    assert "Context Switch" in patterns


def test_parse_patterns_fallback():
    from agents.districts.memory_curator.pattern_finder import PatternFinder
    bot = PatternFinder()
    text = "Line one\nLine two\nLine three\nLine four"
    patterns = bot._parse_patterns(text)
    assert len(patterns) == 3  # fallback returns first 3 lines
