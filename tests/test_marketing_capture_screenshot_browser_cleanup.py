"""Regression: districts/marketing/ads/scripts/capture_screenshot.py's
capture_screenshot() only called browser.close() on the success path --
any exception from page.goto()/page.screenshot() (a navigation timeout,
for example) left the launched chromium process running. Fixed with
try/finally around the browser lifetime.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_SCRIPT_DIR = Path(__file__).resolve().parents[1] / "districts" / "marketing" / "ads" / "scripts"
sys.path.insert(0, str(_SCRIPT_DIR))

import capture_screenshot  # noqa: E402


def _mock_playwright(page_goto_side_effect=None):
    mock_browser = MagicMock()
    mock_page = MagicMock()
    if page_goto_side_effect is not None:
        mock_page.goto.side_effect = page_goto_side_effect
    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page
    mock_browser.new_context.return_value = mock_context
    mock_chromium = MagicMock()
    mock_chromium.launch.return_value = mock_browser
    mock_p = MagicMock()
    mock_p.chromium = mock_chromium
    mock_sync_playwright = MagicMock()
    mock_sync_playwright.return_value.__enter__.return_value = mock_p
    return mock_sync_playwright, mock_browser


def test_browser_closed_on_success():
    mock_sync_playwright, mock_browser = _mock_playwright()
    with patch.object(capture_screenshot, "sync_playwright", mock_sync_playwright), \
         patch.object(capture_screenshot, "validate_url", lambda u: u):
        result = capture_screenshot.capture_screenshot("https://example.com", "out.png")
    assert result["success"] is True
    mock_browser.close.assert_called_once()


def test_browser_closed_on_goto_exception():
    mock_sync_playwright, mock_browser = _mock_playwright(
        page_goto_side_effect=RuntimeError("navigation failed")
    )
    with patch.object(capture_screenshot, "sync_playwright", mock_sync_playwright), \
         patch.object(capture_screenshot, "validate_url", lambda u: u):
        result = capture_screenshot.capture_screenshot("https://example.com", "out.png")
    assert result["success"] is False
    assert "navigation failed" in result["error"]
    mock_browser.close.assert_called_once()


if __name__ == "__main__":
    test_browser_closed_on_success()
    test_browser_closed_on_goto_exception()
    print("OK test_marketing_capture_screenshot_browser_cleanup.py")
