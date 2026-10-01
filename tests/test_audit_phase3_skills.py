"""Audit phase 3 regressions for districts/skills (no network, no real DB)."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class FakeMem:
    skills: dict = {}
    events: list = []
    stored: list = []
    update_ok = True

    def __init__(self, *a, **k):
        pass

    def recall(self, q, limit=5, event_type=None):
        return list(FakeMem.events)

    def store(self, **kw):
        FakeMem.stored.append(kw)

    def get_skill(self, name):
        return FakeMem.skills.get(name)

    def update_skill(self, name, conf, evidence=None):
        if not FakeMem.update_ok:
            return False
        FakeMem.skills[name] = {"skill_name": name, "confidence": conf}
        return True


@pytest.fixture(autouse=True)
def fake_mem(monkeypatch):
    FakeMem.skills, FakeMem.events, FakeMem.stored, FakeMem.update_ok = {}, [], [], True
    import core.memory.episodic as ep
    import districts.skills.skill_mapper as sm
    import districts.skills.mastery_tracker as mt
    import districts.skills.gap_analyst as ga
    for m in (ep, sm, mt, ga):
        monkeypatch.setattr(m, "EpisodicMemory", FakeMem)
    return FakeMem


def _mapper(monkeypatch, llm_text):
    from districts.skills.skill_mapper import SkillMapper
    a = SkillMapper()
    monkeypatch.setattr(a, "_call_ollama", lambda *x, **k: llm_text)
    return a


def test_map_skills_llm_failure_not_canned(monkeypatch, fake_mem):
    fake_mem.events = [{"content": "wrote python"}]
    a = _mapper(monkeypatch, "")
    r = a.map_skills("bob")
    assert r["status"] == "error"
    assert r["skills"] == [] and r["total_skills"] == 0
    assert "bob" not in a.skill_maps
    assert not fake_mem.stored


def test_map_skills_no_history_is_no_data(monkeypatch, fake_mem):
    called = []
    a = _mapper(monkeypatch, '{"skills":[{"name":"x"}]}')
    monkeypatch.setattr(a, "_call_ollama", lambda *x, **k: called.append(1) or "{}")
    r = a.map_skills("bob")
    assert r["status"] == "no_data" and r["skills"] == []
    assert not called


def test_map_skills_ok(monkeypatch, fake_mem):
    fake_mem.events = [{"content": "wrote python"}]
    a = _mapper(monkeypatch, '{"skills":[{"name":"python","category":"technical"}]}')
    r = a.map_skills("bob")
    assert r["status"] == "ok" and r["total_skills"] == 1


def test_suggest_gaps_no_skills_is_error(monkeypatch, fake_mem):
    a = _mapper(monkeypatch, "")
    r = a.suggest_skill_gaps("bob")
    assert r["status"] == "error" and r["skill_gaps"] == []


def test_suggest_gaps_llm_garbage_not_canned(monkeypatch, fake_mem):
    a = _mapper(monkeypatch, "")
    a.skill_maps["bob"] = {"skills": [{"name": "python"}]}
    r = a.suggest_skill_gaps("bob")
    assert r["status"] == "error" and r["gaps_count"] == 0


def test_track_progress_unknown_skill_not_fabricated(monkeypatch, fake_mem):
    a = _mapper(monkeypatch, "")
    r = a.track_skill_progress("rust")
    assert r["level"] == "Not tracked" and r["confidence"] == 0.0
    assert "rust" not in fake_mem.skills  # nothing written


def test_skill_mapper_run_params_none(monkeypatch, fake_mem):
    a = _mapper(monkeypatch, "")
    r = asyncio.run(a.run({"type": "learn", "params": None}))
    assert r["status"] == "ok"


# ---- mastery
def _tracker():
    from districts.skills.mastery_tracker import MasteryTracker
    return MasteryTracker()


def test_mastery_nan_rejected(fake_mem):
    t = _tracker()
    with pytest.raises(ValueError):
        t.track_mastery("py", float("nan"))
    assert "py" not in fake_mem.skills


def test_mastery_reports_unpersisted(fake_mem):
    t = _tracker()
    fake_mem.update_ok = False
    assert t.track_mastery("py", 0.5)["persisted"] is False
    fake_mem.update_ok = True
    assert t.track_mastery("py", 0.6)["persisted"] is True


def test_mastery_zero_confidence_is_tracked(fake_mem):
    fake_mem.skills["py"] = {"confidence": 0.0}
    r = _tracker().get_mastery_level("py")
    assert r["level"] == "Novice"


def test_next_steps_uses_persisted_score(monkeypatch, fake_mem):
    fake_mem.skills["py"] = {"confidence": 0.7}
    t = _tracker()
    monkeypatch.setattr(t, "_call_ollama", lambda *a, **k: '{"next_steps":[{"action":"a"}]}')
    r = t.suggest_next_steps("py")
    assert r["status"] == "ok"
    assert r["current_score"] == 0.7 and r["current_level"] == "Proficient"


def test_next_steps_llm_failure_not_canned(monkeypatch, fake_mem):
    t = _tracker()
    monkeypatch.setattr(t, "_call_ollama", lambda *a, **k: "")
    r = t.suggest_next_steps("py")
    assert r["status"] == "error" and r["next_steps"] == []


def test_mastery_run_params_none(fake_mem):
    r = asyncio.run(_tracker().run({"params": None}))
    assert r["status"] == "ok"


# ---- gap analyst
def _gap():
    from districts.skills.gap_analyst import GapAnalyst
    return GapAnalyst()


def test_gap_run_empty_required_is_error(fake_mem):
    r = asyncio.run(_gap().run({"type": "analyze_gaps", "params": {"required_skills": [], "current_skills": ["a"]}}))
    assert r["status"] == "error"


def test_gap_run_params_none(fake_mem):
    r = asyncio.run(_gap().run({"type": "analyze_gaps", "params": None}))
    assert r["status"] == "error"


def test_gap_run_string_not_split_into_chars(fake_mem):
    r = asyncio.run(_gap().run({"type": "analyze_gaps",
                                "params": {"required_skills": "python", "current_skills": []}}))
    assert r["status"] == "ok" and r["critical_gaps"] == 1


def test_gap_llm_missing_score_uses_computed(monkeypatch, fake_mem):
    g = _gap()
    monkeypatch.setattr(g, "_call_ollama", lambda *a, **k: '{"gap_analysis": []}')
    r = g.analyze_gaps(["a", "b"], ["a"])
    assert r["overall_gap_score"] == 0.5 and r["gap_analysis"]  # not empty although gaps exist
    r = g.analyze_gaps(["a", "b", "c", "d"], [])
    assert r["overall_gap_score"] == 1.0  # old code: flat 0.5


def test_gap_fallback_marked(monkeypatch, fake_mem):
    g = _gap()
    monkeypatch.setattr(g, "_call_ollama", lambda *a, **k: "")
    assert g.prioritize_gaps([{"skill": "x"}])["source"] == "fallback"
    assert g.suggest_learning_path({"skill": "x"})["source"] == "fallback"


def test_track_mastery_milestones_no_typeerror(fake_mem):
    t = _tracker()
    r1 = t.track_mastery("py", 0.3)
    assert r1["level"] == "Beginner" and r1["milestones_passed"] == ["Beginner"]
    r2 = t.track_mastery("py", 0.65)
    assert r2["level"] == "Proficient"
    assert r2["milestones_passed"] == ["Intermediate", "Proficient"]
    assert r2["progress_delta"] > 0
