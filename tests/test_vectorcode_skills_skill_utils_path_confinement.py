"""Regression for vectorcode/src/skills/skill_utils.py's load_skill():

skill_name was interpolated directly into SKILLS_DIR / skill_name / "SKILL.md"
with zero confinement check -- a skill_name of "../../etc/passwd" (or similar)
could address a path outside SKILLS_DIR entirely (CWE-22). This module has
zero callers anywhere in the repo today (confirmed via grep -- the live
skill loader is the separate vectorcode/src/agent/skill_utils.py), but the
fix is applied anyway per this audit's "dormant doesn't mean low priority"
rule, matching the identical pattern already fixed in importer.py and
learning/distillation/pending_queue.py this cycle.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from skills import skill_utils


def test_load_skill_rejects_traversal_name(monkeypatch, tmp_path):
    monkeypatch.setattr(skill_utils, "SKILLS_DIR", tmp_path)
    # Put a real SKILL.md one level above SKILLS_DIR to prove escape would
    # have worked pre-fix.
    (tmp_path.parent / "secret.txt").write_text("outside")
    assert skill_utils.load_skill("../secret.txt") is None
    assert skill_utils.load_skill("..") is None
    assert skill_utils.load_skill("") is None


def test_load_skill_still_works_for_a_real_skill(monkeypatch, tmp_path):
    monkeypatch.setattr(skill_utils, "SKILLS_DIR", tmp_path)
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# My Skill\n")
    assert skill_utils.load_skill("my-skill") == "# My Skill\n"


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
