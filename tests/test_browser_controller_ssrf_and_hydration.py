"""Regression for 2 real bugs found in core/vision_control/browser_controller.py
during the Phase 3 whole-repo audit (2026-10-02):

1. execute_browser_action()'s "navigate" branch called page.goto(url) with
   zero SSRF validation -- governance.classify() above it is a
   permission-tier check (who/what), not an SSRF check (where). Same
   unguarded shape already fixed in core/browser/playwright_mcp_client.py's
   navigate() this cycle.

2. _call_vlm() called core.inference.vectorcode_llm.chat() directly with no
   session_hydration_prompt() -- same RULE 1 gap fixed in the sibling
   core/vision_control/gui_agent.py this same session.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.vision_control.browser_controller import BrowserController


def _run(coro):
    return asyncio.run(coro)


def _fake_page(url="https://example.com"):
    page = AsyncMock()
    page.url = url
    page.goto = AsyncMock()
    return page


def test_navigate_to_metadata_endpoint_is_blocked():
    ctrl = BrowserController()
    page = _fake_page()
    action = {"action_type": "navigate", "action_inputs": {"url": "http://169.254.169.254/latest/meta-data/"}}
    result = _run(ctrl.execute_browser_action(page, action))
    assert result["status"] == "error"
    assert "SSRF" in result["error"]
    page.goto.assert_not_called()


def test_navigate_to_public_url_still_works():
    ctrl = BrowserController()
    page = _fake_page()
    action = {"action_type": "navigate", "action_inputs": {"url": "https://www.google.com"}}
    with patch("core.security.ssrf_guard.SSRFGuard.check_url") as mock_check:
        mock_check.return_value = MagicMock(safe=True, reason="")
        result = _run(ctrl.execute_browser_action(page, action))
    assert result["status"] == "ok"
    page.goto.assert_called_once()


def test_call_vlm_hydrates_before_chat():
    ctrl = BrowserController()
    with patch("core.inference.vectorcode_llm.chat", return_value="Thought: ok\nAction: finished()") as mock_chat:
        _run(ctrl._call_vlm("browser system prompt", "fakebase64", []))
    messages = mock_chat.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert len(messages[0]["content"]) > 0
    assert messages[1]["content"] == "browser system prompt"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
