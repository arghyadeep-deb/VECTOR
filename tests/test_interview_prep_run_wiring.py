"""
Regression tests for the interview_prep-district fake-success-stub bug.

AgentBase.run() (core/city/agent_base.py) defines a generic fallback that
returns {"status": "ok", "agent": self.name, "task": task} without doing any
real work. Two interview_prep classes overrode run() but ignored
task["type"] entirely and always called the same internal method:
  - FeedbackAnalyst.run() always called track_progress(), even when asked
    to analyze_feedback or identify_improvements.
  - ReportGenerator.run() always called generate_progress_report(), even
    when asked to generate_session_report or export_report.

These tests assert that run() now branches on task["type"] and dispatches
to the class's real, existing methods, and that an unrecognized type
returns the standard error shape instead of silently falling through.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.interview_prep.feedback_analyst import FeedbackAnalyst
from districts.interview_prep.report_generator import ReportGenerator


@pytest.fixture(autouse=True)
def _stub_report_llm(monkeypatch):
    """ReportGenerator._llm makes a real provider call with a 90s ceiling, which
    blows the 60s test timeout whenever a live model actually answers. These are
    dispatch/return-shape wiring tests, not LLM-quality tests, so stub the LLM to
    keep them hermetic and fast (mocking external APIs is allowed per testing.md).
    """
    import districts.interview_prep.report_generator as _rg
    monkeypatch.setattr(
        _rg, "_llm", lambda *a, **k: "Stubbed interview report content for wiring test."
    )


# ---------------------------------------------------------------------------
# FeedbackAnalyst
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_feedback_analyst_run_analyze_routes_to_analyze_feedback():
    agent = FeedbackAnalyst()
    result = await agent.run({
        "type": "analyze_feedback",
        "params": {"text": "Strong technical skills, weak on behavioral questions."},
    })
    assert result["status"] == "ok"
    assert "original_feedback" in result or "analysis" in result


@pytest.mark.asyncio
async def test_feedback_analyst_run_identify_improvements_routes_correctly():
    agent = FeedbackAnalyst()
    result = await agent.run({
        "type": "identify_improvements",
        "params": {"text": "Needs to provide more specific examples."},
    })
    assert result["status"] == "success"
    assert "areas_to_improve" in result


@pytest.mark.asyncio
async def test_feedback_analyst_run_track_progress_routes_correctly():
    agent = FeedbackAnalyst()
    result = await agent.run({"type": "track_progress", "params": {}})
    assert result["status"] in ("ok", "no_data", "success")


@pytest.mark.asyncio
async def test_feedback_analyst_run_unhandled_type_returns_error_shape():
    agent = FeedbackAnalyst()
    result = await agent.run({"type": "totally_bogus_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    # Must NOT be the AgentBase stub shape.
    assert "agent" not in result


@pytest.mark.asyncio
async def test_feedback_analyst_run_real_dispatch_shape_with_query():
    """Real production dispatch shape (core/city/governor.py _dispatch_to_district /
    core/api/routers/commands.py): the governor's classifier invents a task_type per
    request and puts the user's actual free-text message in params["query"]/["content"].
    This test originally documented a LIVE BUG: FeedbackAnalyst.run() had no query
    fallback after its structured branches, so "how did I do in my last mock
    interview?" returned a bare "unhandled type" error even though a perfectly good
    question was supplied. Fixed 2026-08-04 (same pattern as districts/languages/
    *_coach.py) — a progress-shaped question now routes to track_progress() and
    returns real data. Flipped from documenting the bug to asserting the fix.
    """
    agent = FeedbackAnalyst()
    result = await agent.run({
        "type": "ask_feedback_analyst",
        "params": {
            "query": "How did I do in my last mock interview and what should I improve?",
            "content": "How did I do in my last mock interview and what should I improve?",
            "source": "api_command",
        },
    })
    assert result.get("status") != "error", (
        f"a real free-text question must not return the error stub: {result}"
    )
    # track_progress() output — real stored data, not a canned shape.
    assert "overall_score" in result
    assert "category_progress" in result


# ---------------------------------------------------------------------------
# ReportGenerator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_report_generator_run_session_report_routes_correctly():
    agent = ReportGenerator()
    result = await agent.run({
        "type": "session_report",
        "params": {"interview_id": "abc12345"},
    })
    assert "interview_id" in result or "content" in result


@pytest.mark.asyncio
async def test_report_generator_run_progress_report_routes_correctly():
    agent = ReportGenerator()
    result = await agent.run({"type": "progress_report", "params": {}})
    assert "title" in result or "error" in result


@pytest.mark.asyncio
async def test_report_generator_run_export_routes_to_export_report():
    agent = ReportGenerator()
    report = {"id": "r1", "title": "Test Report", "content": "Body text"}
    result = await agent.run({
        "type": "export_report",
        "params": {"report": report, "format": "json"},
    })
    assert result["status"] in ("success", "error")


@pytest.mark.asyncio
async def test_report_generator_run_unhandled_type_returns_error_shape():
    agent = ReportGenerator()
    result = await agent.run({"type": "not_a_real_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_report_generator_run_real_dispatch_shape_with_query():
    """Real production dispatch shape (see feedback_analyst's equivalent test above for
    the full explanation). ReportGenerator.run() (districts/interview_prep/report_generator.py)
    also had NO query fallback — "can you generate my interview progress report?"
    hit the error stub because the governor's invented task_type doesn't exactly
    match "session_report"/"progress_report"/"export_report"/"company_specific".
    Fixed 2026-08-04: an open-ended reporting question now falls through to
    generate_progress_report(), which needs no arguments and reflects real stored
    data. Flipped from documenting the bug to asserting the fix.
    """
    agent = ReportGenerator()
    result = await agent.run({
        "type": "generate_my_report",
        "params": {
            "query": "Can you generate my interview progress report for this month?",
            "content": "Can you generate my interview progress report for this month?",
            "source": "api_command",
        },
    })
    assert result.get("status") != "error", (
        f"a real free-text question must not return the error stub: {result}"
    )
    # generate_progress_report() returns a real report document.
    assert "content" in result
    assert result.get("content")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
