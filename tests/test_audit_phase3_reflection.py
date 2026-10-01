"""Audit phase 3 (reflection): failures must not be reported/written as successful reflections.

All DB/vault state is tmp_path / in-memory; the real main DB and vault are never touched.
"""
import datetime
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.memory.obsidian_sync import ObsidianSync
from districts.reflection import daily_reviewer as dr_mod
from districts.reflection import growth_analyst as ga_mod
from districts.reflection import journal_writer as jw_mod


class FakeMemory:
    """Stand-in for EpisodicMemory: in-memory sqlite with the real column layout, records writes."""

    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE episodic_memory (id TEXT, event_type TEXT, content TEXT, tags TEXT, "
            "source TEXT, timestamp TEXT)"
        )
        self.conn.execute(
            "CREATE TABLE semantic_memory (key TEXT PRIMARY KEY, value TEXT, category TEXT, "
            "confidence REAL, updated_at TEXT)"
        )
        self.remembered, self.stored, self.chains = [], [], []

    def add_event(self, content="did a thing", tags=None, source="vector", hours_ago=1.0, event_type="x"):
        ts = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours_ago)).isoformat()
        self.conn.execute(
            "INSERT INTO episodic_memory VALUES (?,?,?,?,?,?)", ("i", event_type, content, tags, source, ts)
        )

    def add_semantic(self, key, value, category, days_ago=1.0):
        ts = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)).isoformat()
        self.conn.execute("INSERT INTO semantic_memory VALUES (?,?,?,?,?)", (key, value, category, 0.9, ts))

    def remember(self, **kw):
        self.remembered.append(kw)
        return True

    def store(self, **kw):
        self.stored.append(kw)
        return "id"

    def store_chain(self, **kw):
        self.chains.append(kw)
        return "cid"


class FakePolicy:
    def __init__(self):
        self.calls = []

    def update_from_outcome(self, **kw):
        self.calls.append(kw)


class FakeContext:
    def session_hydration_prompt(self):
        return "hydration"


@pytest.fixture
def make(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    mem = FakeMemory()
    for mod in (dr_mod, jw_mod, ga_mod):
        monkeypatch.setattr(mod, "EpisodicMemory", lambda: mem)
        monkeypatch.setattr(mod, "ObsidianSync", lambda: ObsidianSync(vault))
        monkeypatch.setattr(mod, "ContextEngine", FakeContext)
    pol = FakePolicy()
    monkeypatch.setattr(dr_mod, "PolicyMemory", lambda: pol)
    return mem, pol, vault


def _set_llm(monkeypatch, fn):
    import core.inference.vectorcode_llm as llm

    monkeypatch.setattr(llm, "chat", fn)


def _notes(vault):
    return sorted(p.name for p in vault.rglob("*.md"))


# ---- DailyReviewer -------------------------------------------------------------------------

REVIEW = (
    "## WINS\nshipped\n## PATTERNS\nx\n## IMPROVEMENTS\ny\n"
    "## POLICY_UPDATES\nIf tired then always rest\n## GROWTH_SCORE\n7/10 solid day\n"
)


async def test_review_llm_down_is_failure_not_canned_journal(make, monkeypatch):
    mem, pol, vault = make
    mem.add_event()
    _set_llm(monkeypatch, lambda **kw: "")
    bot = dr_mod.DailyReviewer()
    hp = bot.health_points
    assert await bot.review() is False
    assert _notes(vault) == []
    assert mem.chains == [] and mem.stored == [] and pol.calls == []
    assert bot.health_points == hp  # no +50 HP for a canned placeholder


async def test_review_db_fetch_failure_is_not_a_quiet_day(make, monkeypatch):
    mem, pol, vault = make
    mem.conn.execute("DROP TABLE episodic_memory")  # fetch now raises
    calls = []
    _set_llm(monkeypatch, lambda **kw: calls.append(kw) or REVIEW)
    bot = dr_mod.DailyReviewer()
    assert await bot.review() is False
    assert calls == []  # never asked the LLM to review "no data"
    assert _notes(vault) == []


async def test_review_empty_day_has_no_invented_rules_or_score(make, monkeypatch):
    mem, pol, vault = make
    calls = []
    _set_llm(monkeypatch, lambda **kw: calls.append(kw) or REVIEW)
    bot = dr_mod.DailyReviewer()
    assert await bot.review() is True
    assert calls == []
    assert pol.calls == [] and mem.remembered == []
    note = next(vault.rglob("*.md")).read_text(encoding="utf-8")
    assert "No activity was recorded" in note


async def test_growth_score_is_the_number_not_the_heading(make, monkeypatch):
    mem, pol, vault = make
    mem.add_event()
    _set_llm(monkeypatch, lambda **kw: REVIEW)
    bot = dr_mod.DailyReviewer()
    assert await bot.review() is True
    scores = [r for r in mem.remembered if r["category"] == "growth"]
    assert len(scores) == 1 and "7/10" in scores[0]["value"]
    assert not scores[0]["value"].startswith("##")


async def test_review_without_score_stores_no_score(make, monkeypatch):
    mem, pol, vault = make
    mem.add_event()
    _set_llm(monkeypatch, lambda **kw: "## WINS\nok\n## GROWTH_SCORE\n(not rated)\n")
    bot = dr_mod.DailyReviewer()
    assert await bot.review() is True
    assert [r for r in mem.remembered if r["category"] == "growth"] == []


async def test_vault_write_failure_not_recorded_as_success(make, monkeypatch):
    mem, pol, vault = make
    mem.add_event()
    _set_llm(monkeypatch, lambda **kw: REVIEW)
    bot = dr_mod.DailyReviewer()

    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(bot._obsidian, "write_note", boom)
    assert await bot.review() is False
    assert [c for c in mem.chains if c["reward"] > 0.7] == []
    assert [s for s in mem.stored if s["event_type"] == "daily_review"] == []


def test_fetch_includes_untagged_events_and_excludes_test_rows(make):
    mem, pol, vault = make
    mem.add_event(content="untagged", tags=None, source="vector")
    mem.add_event(content="tagged", tags='["work"]')
    mem.add_event(content="seeded", tags='["test"]')
    mem.add_event(content="from_test_src", source="pytest_test")
    bot = dr_mod.DailyReviewer()
    got = {e["content"] for e in bot._fetch_today()}
    assert got == {"untagged", "tagged"}


def test_fetch_cutoff_is_aware_utc(make):
    mem, pol, vault = make
    seen = []

    class Cur:
        description = [("event_type",)]

        def execute(self, sql, params):
            seen.append(params[0])

        def fetchall(self):
            return []

    class Conn:
        def cursor(self):
            return Cur()

    mem.conn = Conn()
    dr_mod.DailyReviewer()._fetch_today()
    jw_mod.JournalWriter()._fetch_events()
    ga_mod.GrowthAnalyst()._fetch_recent_events()
    assert len(seen) == 3
    for c in seen:
        assert datetime.datetime.fromisoformat(c).tzinfo is not None  # same basis as stored UTC rows


async def test_event_triggered_review_runs_once_per_day(make, monkeypatch):
    mem, pol, vault = make
    mem.add_event()
    n = []
    _set_llm(monkeypatch, lambda **kw: n.append(1) or REVIEW)

    class FakeDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime(2026, 10, 1, 23, 0, tzinfo=tz)

    monkeypatch.setattr(dr_mod.datetime, "datetime", FakeDT)
    bot = dr_mod.DailyReviewer()
    for _ in range(3):
        await bot.handle_event({"event_type": "task_completed"})
    assert len(n) == 1


async def test_run_params_none_is_safe(make):
    bot = dr_mod.DailyReviewer()
    r = await bot.run({"type": "x", "params": None})
    assert r["status"] == "ok"


# ---- JournalWriter -------------------------------------------------------------------------

async def test_journal_llm_down_writes_nothing(make, monkeypatch):
    mem, pol, vault = make
    mem.add_event()
    _set_llm(monkeypatch, lambda **kw: "")
    bot = jw_mod.JournalWriter()
    assert await bot.write_daily() is False
    assert await bot.write_weekly() is False
    assert _notes(vault) == []
    assert mem.chains == [] and mem.stored == []


async def test_journal_fetch_failure_writes_nothing(make, monkeypatch):
    mem, pol, vault = make
    mem.conn.execute("DROP TABLE episodic_memory")
    calls = []
    _set_llm(monkeypatch, lambda **kw: calls.append(1) or "narrative")
    bot = jw_mod.JournalWriter()
    assert await bot.write_daily() is False
    assert calls == [] and _notes(vault) == []


async def test_journal_empty_day_is_factual_not_llm_invented(make, monkeypatch):
    mem, pol, vault = make
    calls = []
    _set_llm(monkeypatch, lambda **kw: calls.append(1) or "I had a lovely day")
    bot = jw_mod.JournalWriter()
    assert await bot.write_daily() is True
    assert calls == []
    assert "No activity was logged" in next(vault.rglob("*.md")).read_text(encoding="utf-8")


async def test_weekly_label_uses_iso_year(make, monkeypatch):
    mem, pol, vault = make
    mem.add_event()
    _set_llm(monkeypatch, lambda **kw: "week narrative")

    class FakeDate(datetime.date):
        @classmethod
        def today(cls):
            return cls(2025, 12, 29)  # ISO week 1 of 2026

    monkeypatch.setattr(jw_mod.datetime, "date", FakeDate)
    bot = jw_mod.JournalWriter()
    assert await bot.write_weekly() is True
    assert _notes(vault) == ["Weekly Review — W01-2026.md"]


# ---- GrowthAnalyst -------------------------------------------------------------------------

async def test_growth_reads_real_semantic_scores(make, monkeypatch):
    mem, pol, vault = make
    mem.add_semantic("growth_score:a", "6/10", "growth", days_ago=3)
    mem.add_semantic("growth_score:b", "8/10", "growth", days_ago=2)
    mem.add_semantic("policy_rule:x", "If X then Y", "behavioral_policy", days_ago=1)
    mem.add_event()
    prompts = []
    _set_llm(monkeypatch, lambda **kw: prompts.append(kw["messages"][1]["content"]) or "## TREND\nup")
    bot = ga_mod.GrowthAnalyst()
    assert len(bot._fetch_growth_scores()) == 2
    assert len(bot._fetch_policy_updates()) == 1
    assert await bot.analyse() is True
    assert "6/10" in prompts[0] and "8/10" in prompts[0]
    assert "NO trend data" not in prompts[0]


async def test_growth_without_scores_forbids_invented_trend(make, monkeypatch):
    mem, pol, vault = make
    mem.add_event()
    prompts = []
    _set_llm(monkeypatch, lambda **kw: prompts.append(kw["messages"][1]["content"]) or "## TREND\ninsufficient data")
    bot = ga_mod.GrowthAnalyst()
    assert await bot.analyse() is True
    assert "NO trend data" in prompts[0]


async def test_growth_llm_down_and_fetch_failure_are_failures(make, monkeypatch):
    mem, pol, vault = make
    mem.add_event()
    _set_llm(monkeypatch, lambda **kw: "")
    bot = ga_mod.GrowthAnalyst()
    assert await bot.analyse() is False
    assert _notes(vault) == [] and mem.chains == [] and mem.remembered == []

    mem.conn.execute("DROP TABLE semantic_memory")
    _set_llm(monkeypatch, lambda **kw: "## TREND\nx")
    assert await bot.analyse() is False
    assert _notes(vault) == []


async def test_growth_write_failure_records_no_success_chain(make, monkeypatch):
    mem, pol, vault = make
    mem.add_event()
    _set_llm(monkeypatch, lambda **kw: "## TREND\nflat")
    bot = ga_mod.GrowthAnalyst()

    def boom(*a, **kw):
        raise OSError("ro")

    monkeypatch.setattr(bot._obsidian, "write_note", boom)
    assert await bot.analyse() is False
    assert mem.chains == []
