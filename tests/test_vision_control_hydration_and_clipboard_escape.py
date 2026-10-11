"""Regression for 2 real bugs found in core/vision_control/ during the
Phase 3 whole-repo audit (2026-10-02):

1. gui_agent.py's GUIAgent._call_vlm() called core.inference.vectorcode_llm.chat()
   directly with no session_hydration_prompt() -- same RULE 1 gap already
   fixed in districts/coding/gui_automation_agent.py (the sibling district
   agent built on top of this same module) and 8+ other files this cycle.

2. vision_operator.py's VisionOperator._type_text() escaped a caller-
   supplied clipboard string for PowerShell's single-quoted string literal
   by substituting every single quote with a double quote. That neutralizes
   the one real breakout vector (a single quote is PowerShell's only
   special character inside '...'), but it also silently corrupts every
   legitimate apostrophe in typed text (e.g. "don't" -> "don"t"). The
   correct PowerShell escape is to double the single quote ('' inside
   '...'), which is equally safe and preserves the real character.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.vision_control.gui_agent import GUIAgent
from core.vision_control.vision_operator import VisionOperator


def _run(coro):
    return asyncio.run(coro)


def test_call_vlm_hydrates_before_chat():
    agent = GUIAgent()
    with patch("core.inference.vectorcode_llm.chat", return_value="Thought: ok\nAction: finished()") as mock_chat:
        _run(agent._call_vlm("system prompt", "fakebase64", []))
    messages = mock_chat.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert len(messages[0]["content"]) > 0
    assert messages[1]["content"] == "system prompt"


def test_type_text_preserves_apostrophe_via_doubling():
    op = VisionOperator()
    op._is_windows = True
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        result = MagicMock()
        result.stdout = ""
        return result

    with patch("core.vision_control.vision_operator.subprocess.run", side_effect=fake_run), \
         patch("core.vision_control.vision_operator.pyautogui", MagicMock(), create=True), \
         patch("core.vision_control.vision_operator.time.sleep"):
        op._type_text("don't")

    set_clip_calls = [c for c in calls if len(c) > 2 and "Set-Clipboard" in c[2]]
    assert set_clip_calls, "Set-Clipboard was never invoked"
    # The real apostrophe must survive as a doubled single quote, not be
    # replaced with a different character.
    assert "don''t" in set_clip_calls[0][2]
    assert "don\"t" not in set_clip_calls[0][2]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
