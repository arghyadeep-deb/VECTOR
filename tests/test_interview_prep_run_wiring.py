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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
