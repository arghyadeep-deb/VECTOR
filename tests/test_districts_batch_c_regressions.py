"""Regression coverage for genuine defects found in the districts Batch C audit."""

import importlib.util
import os
from pathlib import Path


def test_social_sim_wrapper_bootstraps_its_vendored_app_tree():
    """The wrapper's deferred ``from app...`` imports must be importable."""
    from districts.intelligence import social_sim_agent

    expected = Path(social_sim_agent.__file__).parent / "vector_social_sim"
    assert social_sim_agent._MIRO_DIR == expected
    assert social_sim_agent._MIRO_DIR.is_dir()
    assert importlib.util.find_spec("app") is not None


def test_venture_report_write_is_fsynced_and_atomically_replaced(tmp_path, monkeypatch):
    from districts.news_trends import venture_pipeline

    calls = {"fsync": 0, "replace": 0}
    real_fsync = os.fsync
    real_replace = os.replace

    def tracked_fsync(fd):
        calls["fsync"] += 1
        return real_fsync(fd)

    def tracked_replace(source, destination):
        calls["replace"] += 1
        return real_replace(source, destination)

    monkeypatch.setattr(venture_pipeline.os, "fsync", tracked_fsync)
    monkeypatch.setattr(venture_pipeline.os, "replace", tracked_replace)
    target = tmp_path / "shared-report.md"

    venture_pipeline._atomic_write_text(target, "complete report")

    assert target.read_text(encoding="utf-8") == "complete report"
    assert calls == {"fsync": 1, "replace": 1}
    assert list(tmp_path.glob("*.tmp")) == []
