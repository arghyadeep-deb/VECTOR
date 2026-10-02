"""Regression for core/stealth_browser/transcripts.py's _extract_via_ytdlp()
passing a caller-supplied url as a bare positional argv to yt-dlp (Phase 3
whole-repo audit, 2026-10-02).

Reachable via Governor dispatch: districts/research/stealth_scout_agent.py's
youtube_transcript action passes params["url"] straight through with no
validation. _is_youtube_url()'s re.search() only checks substring presence
anywhere in the string, so a value like "--exec=<cmd> #youtube.com" both
passes that gate AND starts with "-" -- yt-dlp's real --exec flag runs an
arbitrary shell command after "download" (real RCE), a known argument-
injection vector for this exact CLI tool.
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.stealth_browser.transcripts import _extract_via_ytdlp, get_youtube_transcript


def _run(coro):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)


def test_option_like_url_rejected_before_subprocess():
    with patch("core.stealth_browser.transcripts.subprocess.run") as mock_run:
        result = _extract_via_ytdlp("--exec=touch /tmp/pwned #youtube.com/watch?v=x")
    assert result is None
    mock_run.assert_not_called()


def test_is_youtube_url_gate_alone_does_not_stop_option_like_value():
    # Documents the real gap this fix closes: the "contains youtube.com
    # somewhere" check does not require the string to start with a scheme.
    from core.stealth_browser.transcripts import _is_youtube_url
    assert _is_youtube_url("--exec=whatever #youtube.com") is True


def test_legitimate_url_still_reaches_subprocess_with_dash_dash_separator():
    fake_proc = MagicMock(returncode=0, stdout='{"id": "x", "title": "t", "requested_subtitles": null, "subtitles": null, "chapters": []}\n', stderr="")
    with patch("core.stealth_browser.transcripts.subprocess.run", return_value=fake_proc) as mock_run:
        result = _extract_via_ytdlp("https://youtu.be/dQw4w9WgXcQ")
    assert result is not None
    args = mock_run.call_args[0][0]
    assert args[-1] == "https://youtu.be/dQw4w9WgXcQ"
    assert args[-2] == "--"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
