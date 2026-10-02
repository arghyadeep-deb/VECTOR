"""Regression: MissionPlanAdvisor._call_model() called its chat_fn with no
session_hydration_prompt() at all (RULE 1 gap) -- same class fixed dozens
of times this cycle. Reachable via core/runtime/plans.py's two real
MissionPlanAdvisor() construction sites, not dormant.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.runtime.missions import MissionPlanAdvisor


def test_call_model_hydrates_before_chat_fn():
    captured = {}

    def fake_chat_fn(model, messages, timeout, **kwargs):
        captured["messages"] = messages
        return '{"steps": []}'

    advisor = MissionPlanAdvisor(chat_fn=fake_chat_fn)
    advisor._call_model("test objective", max_steps=3)

    messages = captured["messages"]
    assert messages[0]["role"] == "system"
    assert len(messages[0]["content"]) > 0
    # the advisor's own fixed system prompt must still be present, just after hydration
    assert messages[1]["content"] == advisor.SYSTEM_PROMPT
    assert messages[2]["role"] == "user"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
