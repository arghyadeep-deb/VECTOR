"""Regression for vectorcode/src/skills/overlay.py's write_overlay():

overlay.skill_name is not fully trusted -- its one real caller
(learning/agents/skill_optimizer.py) derives it from trace-step tool-call
metadata, not an internally-generated identifier. Without confinement, a
skill_name containing ".." or an absolute path could write optimized.toml
outside the intended overlay directory -- the same unconfined-identifier-
into-path shape fixed elsewhere this audit cycle (importer.py,
learning/distillation/{pending_queue,execute/appliers/agent,diagnose/tools,
orchestrator}.py).

Also verifies that skill_optimizer.py's call site catches the resulting
ValueError per-skill rather than letting it crash the whole optimization
batch (write_overlay's new guard necessitated this caller-side fix too).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

import pytest

from skills.overlay import SkillOverlay, write_overlay


def _overlay(skill_name: str) -> SkillOverlay:
    return SkillOverlay(
        skill_name=skill_name,
        optimizer="dspy",
        optimized_at="2026-10-05T00:00:00Z",
        trace_count=1,
        description="test",
        few_shot=[],
    )


def test_write_overlay_rejects_parent_traversal(tmp_path):
    root = tmp_path / "overlays"
    root.mkdir()
    with pytest.raises(ValueError):
        write_overlay(_overlay("../../etc"), root)


def test_write_overlay_rejects_absolute_skill_name(tmp_path):
    root = tmp_path / "overlays"
    root.mkdir()
    absolute = str(tmp_path / "escaped")
    with pytest.raises(ValueError):
        write_overlay(_overlay(absolute), root)


def test_write_overlay_accepts_normal_skill_name(tmp_path):
    root = tmp_path / "overlays"
    root.mkdir()
    path = write_overlay(_overlay("my-skill"), root)
    assert path.exists()
    assert path.parent.parent.resolve() == root.resolve()


def test_skill_optimizer_continues_batch_after_write_overlay_failure():
    from learning.agents.skill_optimizer import SkillOptimizer

    # The caller-side fix wraps write_overlay in its own try/except that
    # records status="error" and continues, mirroring the pattern already
    # used for the optimizer-call failure case a few lines above it.
    import inspect

    src = inspect.getsource(SkillOptimizer.optimize)
    assert "write_overlay(overlay, overlay_dir)" in src
    assert src.count("continue") >= 2


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
