"""Phase-3 audit: districts/personal_growth honest-status / vault-safety fixes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import pytest

from districts.personal_growth import behavioral_nudge_engine as bne
from districts.personal_growth import feedback_synthesizer as fs
from districts.personal_growth import zk_steward as zk


def _zk(tmp_path):
    a = zk.ZKSteward()
    a._vault_path = tmp_path
    return a


def _note(tmp_path, name, body="x" * 80):
    p = tmp_path / f"{name}.md"
    p.write_text(body, encoding="utf-8")
    return p


# ── zk_steward ──────────────────────────────────────────────────────────
def test_backlinks_refuse_path_outside_vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    outside = tmp_path / "secret.md"
    outside.write_text("orig", encoding="utf-8")
    a = _zk(vault)
    assert a.insert_backlinks(str(outside), ["A"]) == 0
    assert outside.read_text(encoding="utf-8") == "orig"
    link = vault / "evil.md"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("no symlinks")
    assert a.insert_backlinks(str(link), ["A"]) == 0
    assert outside.read_text(encoding="utf-8") == "orig"


def test_backlinks_preserve_prior_zk_links(tmp_path):
    a = _zk(tmp_path)
    p = _note(tmp_path, "n", "body " * 20)
    assert a.insert_backlinks(str(p), ["A", "B"]) == 2
    assert a.insert_backlinks(str(p), ["A", "C"]) == 1
    text = p.read_text(encoding="utf-8")
    assert "[[A]]" in text and "[[B]]" in text and "[[C]]" in text
    assert text.count("*ZK connections:") == 1


def test_backlinks_alias_not_duplicated_and_injection_stripped(tmp_path):
    a = _zk(tmp_path)
    p = _note(tmp_path, "n", "see [[A|alias]] and [[B#Head]] " + "z" * 60)
    assert a.insert_backlinks(str(p), ["A", "B"]) == 0
    assert a.insert_backlinks(str(p), ["C]] [[evil\n", r"\1"]) == 2
    text = p.read_text(encoding="utf-8")
    assert a.extract_existing_links(text) == {"A", "B", "C evil", "\\1"}


@pytest.mark.asyncio
async def test_find_connections_drops_hallucinated_names(tmp_path, monkeypatch):
    a = _zk(tmp_path)
    monkeypatch.setattr(zk, "chat", lambda **k: "Real\n../../etc/passwd\nnot a note\n- real")
    class CE:
        def session_hydration_prompt(self, *x): return ""
    monkeypatch.setattr(zk, "ContextEngine", CE)
    notes = [{"name": "Self", "content": "a"}, {"name": "Real", "content": "b"}]
    assert await a.find_connections("Self", ["c"], notes) == ["Real"]


@pytest.mark.asyncio
async def test_run_missing_vault_is_error(tmp_path):
    a = _zk(tmp_path / "nope")
    r = await a.run({})
    assert r["status"] == "error"


@pytest.mark.asyncio
async def test_run_all_concept_failures_is_error(tmp_path, monkeypatch):
    a = _zk(tmp_path)
    _note(tmp_path, "n1")

    async def none(*x, **k): return []
    monkeypatch.setattr(a, "extract_concepts", none)
    r = await a.run({"params": None})
    assert r["status"] == "error"


# ── feedback_synthesizer ────────────────────────────────────────────────
def _fs(tmp_path):
    a = fs.FeedbackSynthesizer()
    a._vault_path = tmp_path
    return a


def test_obsidian_collection_ignores_own_reports(tmp_path):
    a = _fs(tmp_path)
    (tmp_path / "VECTOR Feedback 2026-01-01.md").write_text("# VECTOR Feedback Report\nVECTOR feedback x", encoding="utf-8")
    assert a.collect_from_obsidian() == []
    (tmp_path / "real.md").write_text("VECTOR should remember more", encoding="utf-8")
    assert len(a.collect_from_obsidian()) == 1


@pytest.mark.asyncio
async def test_synthesis_llm_failure_is_error_not_canned(tmp_path, monkeypatch):
    a = _fs(tmp_path)
    monkeypatch.setattr(a, "collect_from_memory", lambda days=7: ["[FAILURE] boom"])

    def boom(**k): raise RuntimeError("llm down")
    monkeypatch.setattr(fs, "chat", boom)
    r = await a.run({"params": None})
    assert r["status"] == "error"
    assert not list(tmp_path.glob("VECTOR Feedback*"))


@pytest.mark.asyncio
async def test_all_sources_unreadable_is_not_no_issues(tmp_path, monkeypatch):
    a = _fs(tmp_path / "missing")

    class Mem:
        def recall(self, *x, **k): raise RuntimeError("db down")
    a._memory = Mem()
    r = await a.run({})
    assert r["status"] == "error" and r["source_errors"]


def test_unparseable_timestamp_event_not_counted(tmp_path):
    a = _fs(tmp_path)

    class Mem:
        def recall(self, *x, **k):
            return [{"timestamp": "garbage", "content": "task failed", "event_type": "x"}]
    a._memory = Mem()
    assert a.collect_from_memory(days=7) == []


# ── behavioral_nudge_engine ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_nudge_run_errors_when_activity_store_unreadable(monkeypatch):
    e = bne.BehavioralNudgeEngine()

    class Boom:
        def __enter__(self): raise RuntimeError("db locked")
        def __exit__(self, *a): return False
    monkeypatch.setattr(bne, "get_temp_cursor", lambda: Boom())
    monkeypatch.setattr(bne.datetime, "datetime", bne.datetime.datetime)
    monkeypatch.setattr(e, "detect_procrastination_pattern",
                        lambda: {"detected": False, "idle_minutes": 0.0, "reason": "query_error: x"})
    r = await e.run({})
    assert r["status"] == "error" and r["nudge_sent"] is False


def test_nudge_blank_llm_reply_uses_fallback_and_is_labeled(monkeypatch):
    import core.inference.vectorcode_llm as v
    monkeypatch.setattr(v, "chat", lambda **k: "   ")
    e = bne.BehavioralNudgeEngine()
    text = e.generate_nudge({"energy_level": "high"})
    assert text and e._last_nudge_source == "fallback"
