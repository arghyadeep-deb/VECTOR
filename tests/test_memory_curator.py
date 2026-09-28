from pathlib import Path

import pytest
import asyncio
import tempfile


@pytest.fixture(autouse=True)
def _isolated_curator_db(tmp_path, monkeypatch):
    """Never let these tests touch the owner's real memory DB.

    2026-08-06: this file was the SEVENTH found writing into production. It
    escaped the earlier isolation sweep (commits 730136d08, 60a707302)
    because it never names EpisodicMemory or get_db_connection — it writes
    through `ConsolidationBot()._memory.store(...)`, so a grep for the
    obvious symbols missed it. Caught by watching the live row count instead:
    `source='test'` went 28,083 -> 28,111 during a test run, and the new rows
    were literally "vault note test event N" / "hp change test event N" from
    the cases below.

    Same pattern as tests/unit/test_memory_decay.py::isolated_episodic. The
    bots build their own EpisodicMemory lazily at construction time, which is
    inside each test, so redirecting the env here is enough to catch them.
    """
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "curator_test.db"))
    monkeypatch.setenv("VECTOR_DB_KEY", "test_key_isolated")
    import core.memory.episodic as ep
    ep.close_db_connection()
    yield
    ep.close_db_connection()


# ── ConsolidationBot ──────────────────────────────────────────────────────────

def test_consolidation_bot_init():
    from districts.memory_curator.consolidation_bot import ConsolidationBot
    bot = ConsolidationBot()
    assert bot.health_points == 500
    assert bot.name == "ConsolidationBot"
    assert bot.district == "memory_curator"
    assert bot.is_alive


def test_consolidation_bot_inherits_ghost():
    from districts.memory_curator.consolidation_bot import ConsolidationBot
    ghost = {
        "lessons_learned": ["always verify before writing"],
        "best_decisions": [],
        "personality_traits": {"careful": True},
        "generation": 1,
    }
    bot = ConsolidationBot(generation=2, ghost=ghost)
    assert "always verify before writing" in bot.lessons


def test_write_daily_reflection_creates_vault_note():
    from districts.memory_curator.consolidation_bot import ConsolidationBot
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
    from districts.memory_curator.consolidation_bot import ConsolidationBot
    bot = ConsolidationBot()
    initial_hp = bot.health_points

    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Reflections").mkdir()
        bot._obsidian._vault = vault

        asyncio.run(bot.write_daily_reflection())
        assert bot.health_points > initial_hp


def test_consolidate_old_episodes_stores_summary():
    from districts.memory_curator.consolidation_bot import ConsolidationBot
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
    from districts.memory_curator.pattern_finder import PatternFinder
    bot = PatternFinder()
    assert bot.health_points == 500
    assert bot.name == "PatternFinder"
    assert bot.district == "memory_curator"
    assert bot.is_alive


def test_pattern_finder_inherits_ghost():
    from districts.memory_curator.pattern_finder import PatternFinder
    ghost = {
        "lessons_learned": ["look for weekly cycles"],
        "best_decisions": [],
        "personality_traits": {},
        "generation": 1,
    }
    bot = PatternFinder(generation=2, ghost=ghost)
    assert "look for weekly cycles" in bot.lessons


def test_find_patterns_returns_list():
    from districts.memory_curator.pattern_finder import PatternFinder
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
    from districts.memory_curator.pattern_finder import PatternFinder
    from unittest.mock import patch
    bot = PatternFinder()
    # Force _fetch_window to return fewer than MIN_EPISODES (5) episodes
    with patch.object(bot, "_fetch_window", return_value=[{"event_type": "task", "content": "x", "timestamp": "2026-01-01T00:00:00"}]):
        patterns = asyncio.run(bot.find_patterns(window_hours=1))
    assert patterns == []


def test_find_patterns_changes_hp():
    from districts.memory_curator.pattern_finder import PatternFinder
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
    from districts.memory_curator.pattern_finder import PatternFinder
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
    from districts.memory_curator.pattern_finder import PatternFinder
    bot = PatternFinder()
    result = bot.get_stored_patterns(days=30)
    assert isinstance(result, list)


def test_parse_patterns_structured():
    from districts.memory_curator.pattern_finder import PatternFinder
    bot = PatternFinder()
    text = (
        "PATTERN: Late Night Coding\nOBSERVATION: Most commits after 10PM\nIMPACT: Sleep debt\n\n"
        "PATTERN: Context Switch\nOBSERVATION: YouTube after hard tasks\nIMPACT: 2h distraction\n"
    )
    patterns = bot._parse_patterns(text)
    assert "Late Night Coding" in patterns
    assert "Context Switch" in patterns


def test_parse_patterns_fallback():
    from districts.memory_curator.pattern_finder import PatternFinder
    bot = PatternFinder()
    text = "Line one\nLine two\nLine three\nLine four"
    patterns = bot._parse_patterns(text)
    assert len(patterns) == 3  # fallback returns first 3 lines


# ── SELF_DEV_P8_MEMORY_FINANCE_OPS: IdentityGraphOperator / LSPIndexEngineer ─────────────────

def test_identity_graph_operator_init():
    from districts.memory_curator.memory_curator_specialists import IdentityGraphOperator
    agent = IdentityGraphOperator()
    assert agent.health_points == 500
    assert agent.name == "IdentityGraphOperator"
    assert agent.district == "memory_curator"
    assert agent.is_alive


def test_identity_graph_operator_brief_reports_missing_evidence():
    from districts.memory_curator.memory_curator_specialists import IdentityGraphOperator
    agent = IdentityGraphOperator()
    result = asyncio.run(agent.run({"type": "identity_graph_brief", "evidence": {}}))
    assert result["status"] == "ok"
    assert result["report"]["status"] == "needs_human"
    assert set(result["report"]["missing_evidence"]) == {"entity_records", "match_fields"}


def test_identity_graph_operator_check_finds_duplicate_cluster():
    from districts.memory_curator.memory_curator_specialists import IdentityGraphOperator
    agent = IdentityGraphOperator()
    result = asyncio.run(agent.run({
        "type": "identity_dedup_check",
        "evidence": {
            "match_fields": ["email"],
            "entity_records": [
                {"id": "a1", "email": "Same@Example.com"},
                {"id": "a2", "email": "same@example.com"},
                {"id": "a3", "email": "different@example.com"},
            ],
        },
    }))
    v = result["verification"]
    assert v["verified"] is True
    assert v["duplicate_cluster_count"] == 1
    assert sorted(v["duplicate_clusters"][0]["record_ids"]) == ["a1", "a2"]


def test_identity_graph_operator_check_null_match_field_is_skipped_not_clustered():
    """Review finding, fixed by Claude 2026-09-29: an explicit null match field (present but
    None, not merely absent) used to normalize to the literal string "none" and false-positive
    cluster with any other record missing the same field the same way."""
    from districts.memory_curator.memory_curator_specialists import IdentityGraphOperator
    agent = IdentityGraphOperator()
    result = asyncio.run(agent.run({
        "type": "identity_dedup_check",
        "evidence": {
            "match_fields": ["email"],
            "entity_records": [
                {"id": "b1", "email": None},
                {"id": "b2", "email": None},
                {"id": "b3", "email": "real@example.com"},
            ],
        },
    }))
    v = result["verification"]
    assert v["verified"] is True
    assert v["duplicate_cluster_count"] == 0
    assert v["records_skipped"] == 2


def test_identity_graph_operator_check_no_evidence_not_verified():
    from districts.memory_curator.memory_curator_specialists import IdentityGraphOperator
    agent = IdentityGraphOperator()
    result = asyncio.run(agent.run({"type": "identity_dedup_check", "evidence": {}}))
    assert result["verification"]["verified"] is False


def test_lsp_index_engineer_init():
    from districts.memory_curator.memory_curator_specialists import LSPIndexEngineer
    agent = LSPIndexEngineer()
    assert agent.health_points == 500
    assert agent.name == "LSPIndexEngineer"
    assert agent.district == "memory_curator"
    assert agent.is_alive


def test_lsp_index_engineer_indexes_real_ast_symbols():
    from districts.memory_curator.memory_curator_specialists import LSPIndexEngineer
    agent = LSPIndexEngineer()
    result = asyncio.run(agent.run({
        "type": "lsp_symbol_check",
        "evidence": {
            "source_files": [
                {"path": "m.py", "source": "def foo():\n    pass\n\nclass Bar:\n    pass\n"},
            ],
            "expected_symbols": ["foo", "baz"],
        },
    }))
    v = result["verification"]
    assert v["verified"] is True
    assert v["verified_by"] == "ast_static_parse"
    assert v["missing_symbols"] == ["baz"]
    assert v["extra_symbols"] == ["Bar"]
    assert v["passed"] is False


def test_lsp_index_engineer_reports_real_syntax_error():
    from districts.memory_curator.memory_curator_specialists import LSPIndexEngineer
    agent = LSPIndexEngineer()
    result = asyncio.run(agent.run({
        "type": "lsp_symbol_check",
        "evidence": {"source_files": [{"path": "broken.py", "source": "def (:"}]},
    }))
    v = result["verification"]
    assert v["verified"] is True
    assert v["parse_errors"] and v["parse_errors"][0]["path"] == "broken.py"
    assert v["files_indexed"] == 0
    assert v["passed"] is False


def test_lsp_index_engineer_failed_check_earns_no_hp():
    from districts.memory_curator.memory_curator_specialists import LSPIndexEngineer
    agent = LSPIndexEngineer()
    hp = agent.health_points
    asyncio.run(agent.run({
        "type": "lsp_symbol_check",
        "evidence": {"source_files": [{"path": "m.py", "source": "def foo():\n    pass\n"}],
                     "expected_symbols": ["baz"]},
    }))
    assert agent.health_points == hp
    asyncio.run(agent.run({
        "type": "lsp_symbol_check",
        "evidence": {"source_files": [{"path": "m.py", "source": "def foo():\n    pass\n"}],
                     "expected_symbols": ["foo"]},
    }))
    assert agent.health_points > hp
