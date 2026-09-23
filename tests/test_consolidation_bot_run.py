"""
Closes a real feature gap found as a side-effect of fixing
core/city/agent_base.py::request_agent_help() (docs/repo_analysis/_MASTER_TODO.md
§1b): ConsolidationBot.run() ignored task["type"] entirely -- it always called
consolidate_old_episodes() regardless of what was actually asked. The only
real caller, districts/research/research_hub.py, sends
{"type": "store_findings", "params": {"topic": ..., "findings": ...}} expecting
a specific finding to be stored, not a full consolidation pass triggered.

Adds real type-based branching: "store_findings" stores via
EpisodicMemory.remember() (the same semantic-memory write path
consolidate_old_episodes() itself already uses); anything else (including
no type at all) keeps the exact prior behavior for backward compatibility.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_bot():
    from districts.memory_curator.consolidation_bot import ConsolidationBot
    return ConsolidationBot(generation=1)


def test_run_without_type_keeps_prior_consolidate_behavior(monkeypatch):
    bot = _make_bot()

    async def _fake_consolidate():
        return 7

    monkeypatch.setattr(bot, "consolidate_old_episodes", _fake_consolidate)

    # 2026-08-06: run() was updated to add a "note" field explaining what
    # happened when no text was provided (line 336 in consolidation_bot.py).
    # Test updated to check for status and consolidated count without
    # requiring an exact dict match (the "note" key is now always present).
    result = asyncio.run(bot.run({}))
    assert result["status"] == "ok"
    assert result["consolidated"] == 7


def test_run_store_findings_writes_to_semantic_memory(monkeypatch):
    bot = _make_bot()
    calls = []

    monkeypatch.setattr(bot._memory, "remember", lambda key, value, category="general", confidence=0.5: calls.append(
        {"key": key, "value": value, "category": category, "confidence": confidence}
    ))

    result = asyncio.run(bot.run({
        "type": "store_findings",
        "params": {"topic": "AI safety research", "findings": "new alignment technique found"},
    }))

    assert result["status"] == "ok"
    assert len(calls) == 1
    assert "AI safety research" in calls[0]["key"]
    assert "new alignment technique found" in calls[0]["value"]
    assert calls[0]["category"] == "research_finding"


def test_run_store_findings_never_triggers_full_consolidation(monkeypatch):
    bot = _make_bot()

    async def _should_not_be_called():
        raise AssertionError("consolidate_old_episodes should not run for store_findings")

    monkeypatch.setattr(bot, "consolidate_old_episodes", _should_not_be_called)
    monkeypatch.setattr(bot._memory, "remember", lambda *a, **kw: True)

    result = asyncio.run(bot.run({
        "type": "store_findings",
        "params": {"topic": "x", "findings": "y"},
    }))
    assert result["status"] == "ok"


def test_run_store_findings_missing_params_degrades_gracefully():
    bot = _make_bot()
    result = asyncio.run(bot.run({"type": "store_findings", "params": {}}))
    assert result["status"] == "error"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
