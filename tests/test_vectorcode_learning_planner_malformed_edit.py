"""Regression for vectorcode/src/learning/distillation/plan/planner.py's
LearningPlanner._parse_edits():

The except-block's diagnostic logging called `raw.get("id", "?")`
unconditionally -- but `raw` is untrusted teacher-LLM-produced JSON and
is not guaranteed to be a dict (the model could return a bare string,
number, or null as one "edit" entry). When it wasn't a dict, the
AttributeError from `.get()` propagated out of the except block itself,
crashing the whole _parse_edits() call over one malformed entry instead
of skipping it and continuing with the valid edits.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from learning.distillation.plan.planner import LearningPlanner


def _planner() -> LearningPlanner:
    return LearningPlanner.__new__(LearningPlanner)


def test_non_dict_edit_entries_are_skipped_not_crashed():
    planner = _planner()
    result = planner._parse_edits('{"edits": ["not_a_dict", 123, null]}')
    assert result == []


def test_mix_of_valid_and_malformed_edits_keeps_the_valid_ones():
    planner = _planner()
    valid_edit = {
        "id": "edit_001",
        "pillar": "agent",
        "op": "replace_system_prompt",
        "target": "agents.simple.system_prompt",
        "payload": {"new_content": "Be helpful."},
        "rationale": "test",
        "expected_improvement": "cluster_1",
        "risk_tier": "review",
        "references": [],
    }
    result = planner._parse_edits(
        '{"edits": [' + __import__("json").dumps(valid_edit) + ', "garbage"]}'
    )
    assert len(result) == 1
    assert result[0].id == "edit_001"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
