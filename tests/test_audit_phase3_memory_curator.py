"""Phase 3 audit: memory_curator data-loss / silent-failure fixes (temp DB only)."""
import asyncio
import datetime

import pytest


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "audit_mc.db"))
    monkeypatch.setenv("VECTOR_DB_KEY", "test_key_isolated")
    monkeypatch.delenv("VECTOR_MEMORY_CURATOR_LLM", raising=False)
    import core.memory.episodic as ep
    ep.close_db_connection()
    yield
    ep.close_db_connection()


def _bot():
    from districts.memory_curator.consolidation_bot import ConsolidationBot
    return ConsolidationBot()


def _seed_old(bot, days=200):
    ts = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
    from core.memory.episodic import get_temp_cursor
    with get_temp_cursor() as cur:
        cur.execute(
            "INSERT INTO episodic_memory (id, event_type, content, tags, context_snapshot, timestamp, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("old-1", "task", "old event", None, None, ts, "test"),
        )


def _count():
    from core.memory.episodic import get_temp_cursor
    with get_temp_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM episodic_memory")
        return cur.fetchone()[0]


def test_failed_summary_write_does_not_prune_episodes(monkeypatch):
    bot = _bot()
    _seed_old(bot)
    monkeypatch.setattr(bot._memory, "remember", lambda *a, **k: False)
    pruned = []
    monkeypatch.setattr(bot._memory, "prune_old_episodes", lambda *a, **k: pruned.append(1) or 1)
    n = asyncio.run(bot.consolidate_old_episodes())
    assert n == 0
    assert pruned == []
    assert _count() == 1
    assert bot._last_consolidation_date is None


def test_run_consolidate_reports_error_on_failed_write(monkeypatch):
    bot = _bot()
    _seed_old(bot)
    monkeypatch.setattr(bot._memory, "remember", lambda *a, **k: False)
    res = asyncio.run(bot.run({"type": "consolidate"}))
    assert res["status"] == "error"


def test_note_fact_findings_report_failed_write(monkeypatch):
    bot = _bot()
    monkeypatch.setattr(bot._memory, "remember", lambda *a, **k: False)
    assert bot._save_note({"content": "x"})["status"] == "error"
    assert bot._remember_fact({"content": "x"})["status"] == "error"
    assert bot._store_findings({"topic": "t", "findings": "f"})["status"] == "error"


def test_run_tolerates_null_params():
    bot = _bot()
    for t in ("save_note", "remember", "recall", "store_findings", "knowledge_query"):
        res = asyncio.run(bot.run({"type": t, "params": None}))
        assert res["status"] == "error"


def test_pattern_finder_run_reads_params_window(monkeypatch):
    from districts.memory_curator.pattern_finder import PatternFinder
    pf = PatternFinder()
    seen = {}

    async def fake(window_hours=None):
        seen["w"] = window_hours
        return []

    monkeypatch.setattr(pf, "find_patterns", fake)
    asyncio.run(pf.run({"type": "pattern", "params": {"window_hours": 12}}))
    assert seen["w"] == 12
    asyncio.run(pf.run({"type": "pattern", "params": None}))
    assert seen["w"] is None


def test_pattern_finder_bad_timestamp_not_silent_swallow():
    from loguru import logger
    from districts.memory_curator.pattern_finder import PatternFinder
    pf = PatternFinder()
    msgs = []
    hid = logger.add(lambda m: msgs.append(str(m)), level="DEBUG")
    try:
        pf._hour_distribution([{"timestamp": "bad"}, {"timestamp": None}])
    finally:
        logger.remove(hid)
    assert not any("suppressed exception" in m for m in msgs)
    assert any("bad episode timestamp" in m for m in msgs)
