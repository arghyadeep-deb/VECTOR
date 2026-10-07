"""Regression for districts/projects/experiment_tracker.py:

_save_experiments() wrote experiments.json directly via write_text(), with
no atomicity guarantee. A crash mid-write left a truncated/corrupt registry
-- _load_experiments() already defends against an unreadable file by
backing it up, but did nothing to prevent the write path itself from
causing that corruption. Fixed via tempfile+fsync+os.replace.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from districts.projects.experiment_tracker import ExperimentTracker


def _tracker(tmp_path):
    agent = object.__new__(ExperimentTracker)
    agent._EXPERIMENTS_FILE = tmp_path / "experiments.json"
    return agent


def test_save_failure_leaves_no_partial_file(tmp_path):
    agent = _tracker(tmp_path)
    good = {"experiments": [{"id": "EXP-001"}], "next_id": 2}
    assert agent._save_experiments(good) is True
    assert json.loads(agent._EXPERIMENTS_FILE.read_text(encoding="utf-8")) == good

    with patch("json.dump", side_effect=OSError("disk full mid-write")):
        ok = agent._save_experiments({"experiments": [], "next_id": 99})
    assert ok is False

    # prior good content must survive an interrupted write
    assert json.loads(agent._EXPERIMENTS_FILE.read_text(encoding="utf-8")) == good
    # no leaked .tmp sibling
    leaked = list(tmp_path.glob(".experiments.*.tmp"))
    assert leaked == [], f"leaked temp file(s): {leaked}"


def test_save_round_trips(tmp_path):
    agent = _tracker(tmp_path)
    data = {"experiments": [{"id": "EXP-002", "status": "running"}], "next_id": 3}
    assert agent._save_experiments(data) is True
    assert json.loads(agent._EXPERIMENTS_FILE.read_text(encoding="utf-8")) == data
