"""Audit phase 3 regression tests for districts/interview_prep."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import districts.interview_prep.company_researcher as cr
import districts.interview_prep.mock_interviewer as mi
import districts.interview_prep.recruitment_bot as rb
import districts.interview_prep.report_generator as rg


# ---------------- CompanyResearcher ----------------

def _researcher(tmp_path):
    r = cr.CompanyResearcher()
    r._obsidian._vault = tmp_path / "vault"
    return r


@pytest.mark.asyncio
async def test_research_save_confined_to_vault(tmp_path, monkeypatch):
    monkeypatch.setattr(cr, "_llm", lambda *a, **k: "# Overview\nstuff")
    r = _researcher(tmp_path)
    await r.research_company("../../../evil")
    assert not (tmp_path / "evil.md").exists()
    assert not list(tmp_path.glob("*.md"))
    saved = list((tmp_path / "vault" / "Research" / "CompanyResearch").glob("*.md"))
    assert len(saved) == 1
    assert saved[0].resolve().is_relative_to((tmp_path / "vault").resolve())


@pytest.mark.asyncio
async def test_run_failed_research_not_reported_ok(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("provider down")
    monkeypatch.setattr(cr, "_llm", boom)
    r = _researcher(tmp_path)
    res = await r.run({"params": {"company": "Acme"}})
    assert res["status"] == "error"
    assert "provider down" in res["error"]


# ---------------- ReportGenerator ----------------

def _gen(tmp_path):
    g = rg.ReportGenerator()
    g._reports_dir = tmp_path / "reports"
    g._reports_dir.mkdir()
    return g


def test_export_rejects_output_path_outside_reports_dir(tmp_path):
    g = _gen(tmp_path)
    outside = tmp_path / "outside.md"
    res = g.export_report({"title": "t", "content": "c"}, "markdown", str(outside))
    assert res["status"] == "error"
    assert not outside.exists()
    res = g.export_report({"title": "t", "content": "c"}, "markdown", "../escape.md")
    assert res["status"] == "error"
    assert not (tmp_path / "escape.md").exists()


def test_export_default_name_cannot_traverse(tmp_path):
    g = _gen(tmp_path)
    res = g.export_report({"title": "../../pwned", "content": "c"}, "markdown")
    assert res["status"] == "success"
    assert Path(res["output_path"]).resolve().is_relative_to((tmp_path / "reports").resolve())
    assert not (tmp_path / "pwned.markdown").exists()


def test_export_inside_reports_dir_ok(tmp_path):
    g = _gen(tmp_path)
    res = g.export_report({"title": "t", "content": "c"}, "json", "sub/r.json")
    assert res["status"] == "success"
    assert (tmp_path / "reports" / "sub" / "r.json").exists()


def test_html_export_escapes_markup(tmp_path):
    g = _gen(tmp_path)
    html = g._convert_to_html({"title": "<script>x</script>", "content": "<img src=x onerror=1>",
                               "metadata": {"sections": ["<b>s</b>"]}})
    assert "<script>x" not in html and "<img src" not in html and "<b>s" not in html


# ---------------- MockInterviewer ----------------

def test_start_interview_records_first_question(monkeypatch):
    monkeypatch.setattr(mi, "_llm", lambda *a, **k: "Describe a hard bug you fixed.")
    m = mi.MockInterviewer()
    start = m.start_interview("SWE")
    iv = m._active_interviews[start["interview_id"]]
    assert len(iv["questions"]) == 1 and iv["current_question"] == 1
    nxt = m.get_next_question(start["interview_id"])
    assert nxt["question_number"] == 2


def test_start_interview_llm_failure_not_started(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(mi, "_llm", boom)
    m = mi.MockInterviewer()
    res = m.start_interview("SWE")
    assert res["status"] == "error"
    assert m._active_interviews == {}


@pytest.mark.asyncio
async def test_mock_run_failure_not_ok(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(mi, "_llm", boom)
    res = await mi.MockInterviewer().run({"params": {"topic": "ml"}})
    assert res["status"] == "error"


# ---------------- RecruitmentBot ----------------

@pytest.mark.asyncio
async def test_jd_analysis_failure_is_not_fabricated_success(monkeypatch):
    def boom(**k):
        raise RuntimeError("llm down")
    monkeypatch.setattr(rb, "chat", boom)
    bot = rb.RecruitmentBot()
    res = await bot.run({"type": "analyze_jd", "jd": "x", "company": "Y"})
    assert res["status"] == "error"
    assert "analysis" not in res


@pytest.mark.asyncio
async def test_jd_analysis_unparseable_is_error(monkeypatch):
    monkeypatch.setattr(rb, "chat", lambda **k: "no json here")
    res = await rb.RecruitmentBot().run({"type": "analyze_jd", "jd": "x"})
    assert res["status"] == "error"


@pytest.mark.asyncio
async def test_failed_brief_not_written_to_obsidian(monkeypatch):
    def boom(**k):
        raise RuntimeError("llm down")
    monkeypatch.setattr(rb, "chat", boom)
    bot = rb.RecruitmentBot()
    notes = []

    class FakeObs:
        def write_note(self, *a):
            notes.append(a)
    bot._obsidian = FakeObs()
    res = await bot.run({"type": "brief"})
    assert res["status"] == "error"
    assert notes == []


@pytest.mark.asyncio
async def test_failed_resume_review_and_outreach_are_errors(monkeypatch):
    def boom(**k):
        raise RuntimeError("llm down")
    monkeypatch.setattr(rb, "chat", boom)
    bot = rb.RecruitmentBot()
    assert (await bot.run({"type": "review_resume"}))["status"] == "error"
    assert (await bot.run({"type": "outreach"}))["status"] == "error"
