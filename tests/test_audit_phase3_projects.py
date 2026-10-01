"""Audit phase 3 — districts/projects regression tests.

Each test fails on the pre-audit code and passes on the fixed code.
"""
from __future__ import annotations

import asyncio
import datetime
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from districts.projects.deadline_watcher import DeadlineWatcher
from districts.projects.doc_writer import DocWriter
from districts.projects.experiment_tracker import ExperimentTracker
from districts.projects.progress_tracker import ProgressTracker
from districts.projects.project_planner import ProjectPlanner


def _run(c):
    return asyncio.run(c)


@pytest.fixture
def vault(tmp_path):
    (tmp_path / "vault" / "Projects").mkdir(parents=True)
    return tmp_path / "vault"


class _BrokenConn:
    def cursor(self):
        raise RuntimeError("db locked")


# ── DeadlineWatcher ──────────────────────────────────────────────────────────

def test_deadline_store_failure_is_error_not_no_deadlines():
    bot = DeadlineWatcher()
    with patch("districts.projects.deadline_watcher.EpisodicMemory") as em:
        em.return_value.conn = _BrokenConn()
        res = _run(bot.run({"type": "check"}))
    assert res["status"] == "error"
    assert res["count"] == 0


def test_add_deadline_rejects_unparseable_date():
    bot = DeadlineWatcher()
    with pytest.raises(ValueError):
        bot.add_deadline("Thesis", "next friday")
    res = _run(bot.run({"type": "add_deadline", "params": {"name": "Thesis", "date": "31/12/2026"}}))
    assert res["status"] == "error"


def test_add_deadline_rejects_empty_name():
    res = _run(DeadlineWatcher().run({"type": "add_deadline", "params": {"name": " ", "date": "2026-12-01"}}))
    assert res["status"] == "error"


def test_deadline_run_params_none_does_not_crash():
    with patch("districts.projects.deadline_watcher.EpisodicMemory") as em:
        em.return_value.conn = _BrokenConn()
        res = _run(DeadlineWatcher().run({"type": "check", "params": None}))
    assert res["status"] == "error"


# ── DocWriter ────────────────────────────────────────────────────────────────

def test_doc_writer_llm_failure_not_written_as_real_doc(vault):
    bot = DocWriter()
    bot._obsidian._vault = vault
    with patch("core.inference.vectorcode_llm.chat", side_effect=RuntimeError("offline")):
        ok = bot.write_doc("Alpha", "readme")
    assert ok is False
    assert list((vault / "Projects").glob("*.md")) == []


def test_doc_writer_project_name_cannot_escape_vault(vault):
    bot = DocWriter()
    bot._obsidian._vault = vault
    with patch("core.inference.vectorcode_llm.chat", return_value="## Overview\nreal"):
        ok = bot.write_doc("../../../escaped", "readme")
    assert ok is True
    outside = [p for p in vault.parent.rglob("*.md") if vault not in p.parents]
    assert outside == []
    assert len(list((vault / "Projects").glob("*.md"))) == 1


def test_doc_writer_run_params_none():
    res = _run(DocWriter().run({"type": "write_doc", "params": None}))
    assert "status" in res


# ── ProjectPlanner ───────────────────────────────────────────────────────────

def test_planner_name_cannot_escape_vault(vault):
    bot = ProjectPlanner()
    bot._obsidian._vault = vault
    with patch("core.inference.vectorcode_llm.chat", return_value="## Objective\nx"):
        proj = bot.create_project("../../evil", "g", "2026-12-01")
    assert proj["note_written"] is True
    assert [p for p in vault.parent.rglob("*.md") if vault not in p.parents] == []


def test_planner_llm_failure_is_not_plain_ok(vault):
    bot = ProjectPlanner()
    bot._obsidian._vault = vault
    with patch("core.inference.vectorcode_llm.chat", side_effect=RuntimeError("offline")):
        res = _run(bot.run({"type": "create_project", "params": {"name": "P", "goal": "g", "deadline": "2026-12-01"}}))
    assert res["status"] == "partial"
    assert res["plan_generated"] is False


def test_planner_run_uses_api_description_as_goal(vault):
    bot = ProjectPlanner()
    bot._obsidian._vault = vault
    with patch("core.inference.vectorcode_llm.chat", return_value="plan"):
        res = _run(bot.run({"type": "create_project",
                            "params": {"name": "P", "description": "ship the thing", "deadline": "2026-12-01"}}))
    assert res["goal"] == "ship the thing"


def test_planner_empty_name_rejected():
    res = _run(ProjectPlanner().run({"type": "create_project", "params": {"name": "  ", "goal": "g"}}))
    assert res["status"] == "error"


def test_planner_unreadable_store_not_reported_as_no_projects():
    bot = ProjectPlanner()
    bot._memory = type("M", (), {"conn": _BrokenConn()})()
    with patch.object(ProjectPlanner, "vchat", side_effect=RuntimeError("x")):
        answer = _run(bot.answer_projects_question("what projects?"))
    assert "No active projects" not in answer
    assert "unavailable" in answer


# ── ProgressTracker ──────────────────────────────────────────────────────────

def test_weekly_report_aborts_when_data_unreadable(vault):
    bot = ProgressTracker()
    bot._obsidian._vault = vault
    bot._memory = type("M", (), {"conn": _BrokenConn()})()
    ok = _run(bot.weekly_report())
    assert ok is False
    assert list((vault / "Projects").glob("*.md")) == []


# ── ExperimentTracker ────────────────────────────────────────────────────────

@pytest.fixture
def tracker(tmp_path):
    t = ExperimentTracker()
    t._EXPERIMENTS_FILE = tmp_path / "experiments.json"
    return t


def test_analyze_missing_arm_is_insufficient_not_adopt(tracker):
    exp = tracker.create_experiment("h", "c", "v", "m")
    tracker.add_observation(exp["id"], "variant", 0.9)
    tracker.add_observation(exp["id"], "variant", 0.8)
    exp = tracker._load_experiments()["experiments"][0]
    res = _run(tracker.analyze_experiment(exp))
    assert res["conclusion"] == "insufficient_data"


def test_analyze_insufficient_does_not_close_experiment(tracker):
    exp = tracker.create_experiment("h", "c", "v", "m")
    tracker.add_observation(exp["id"], "control", 0.5)
    res = _run(tracker.run({"type": "analyze", "params": {"exp_id": exp["id"]}}))
    assert res["status"] == "insufficient_data"
    assert tracker._load_experiments()["experiments"][0]["status"] == "running"


def test_llm_failure_fallback_is_labelled(tracker):
    exp = tracker.create_experiment("h", "c", "v", "m")
    for v, o in [("control", 0.5), ("control", 0.5), ("variant", 0.9), ("variant", 0.9)]:
        tracker.add_observation(exp["id"], v, o)
    exp = tracker._load_experiments()["experiments"][0]
    with patch("districts.projects.experiment_tracker.chat", side_effect=RuntimeError("offline")):
        res = _run(tracker.analyze_experiment(exp))
    assert res["source"] == "heuristic_fallback"


def test_observe_invalid_variant_rejected(tracker):
    exp = tracker.create_experiment("h", "c", "v", "m")
    assert tracker.add_observation(exp["id"], "B", 1.0) is False
    res = _run(tracker.run({"type": "observe", "params": {"exp_id": exp["id"], "variant": "B", "outcome": 1}}))
    assert res["status"] == "error"


def test_observe_unknown_experiment_is_error(tracker):
    res = _run(tracker.run({"type": "observe", "params": {"exp_id": "EXP-999", "variant": "control", "outcome": 1}}))
    assert res["status"] == "error"


def test_save_failure_not_reported_as_created(tracker):
    with patch.object(ExperimentTracker, "_save_experiments", return_value=False):
        res = _run(tracker.run({"type": "create", "params": {"hypothesis": "h", "control": "c", "variant": "v"}}))
    assert res["status"] == "error"


def test_corrupt_registry_is_backed_up(tracker):
    tracker._EXPERIMENTS_FILE.write_text("{not json", encoding="utf-8")
    data = tracker._load_experiments()
    assert data["experiments"] == []
    assert tracker._EXPERIMENTS_FILE.with_suffix(".corrupt.json").read_text() == "{not json"
