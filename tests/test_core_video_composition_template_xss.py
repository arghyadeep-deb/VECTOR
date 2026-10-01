"""Regression for core/video/vector_composer.py's CompositionTemplate XSS gap
(Phase 3 whole-repo audit, 2026-10-02).

data_viz(), title_card(), and youtube_video() interpolated caller-supplied
text (title, subtitle, dict keys/values, section heading/body, channel_name)
directly into generated HTML with no escaping -- youtube_video() had an
*incomplete* escape (only replaced `"`, not `<`/`>`/`&`) that looked like
protection but wasn't. These templates reach a real headless browser via
core/video/html_renderer.py's capture pipeline (same render path the
already-fixed website_to_video.py XSS used), and the title/data/sections
args are real Governor-dispatchable task parameters
(districts/content/website_to_video.py's render_title_card/render_data_viz,
districts/content/video_pipeline.py's youtube_video calls) -- not internal
constants.

Fixed with html.escape() on every interpolated field. Also required
renaming each method's local `html` variable (the generated-HTML string) to
`html_doc`, since it shadowed the `html` module import for the whole
function scope.
"""
from __future__ import annotations

import os
import tempfile

from core.video.vector_composer import CompositionTemplate

_PAYLOAD = "</script><script>alert(1)</script>"


def test_title_card_escapes_title_and_subtitle():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.html")
        CompositionTemplate.title_card(_PAYLOAD, _PAYLOAD, output_path=path)
        content = open(path, encoding="utf-8").read()
        assert "<script>alert(1)</script>" not in content
        assert "&lt;script&gt;" in content


def test_data_viz_escapes_title_and_dict_keys_values():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "v.html")
        CompositionTemplate.data_viz(_PAYLOAD, {_PAYLOAD: 5}, output_path=path)
        content = open(path, encoding="utf-8").read()
        assert "<script>alert(1)</script>" not in content


def test_youtube_video_escapes_title_sections_and_channel_name():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "y.html")
        CompositionTemplate.youtube_video(
            title=_PAYLOAD,
            sections=[{"heading": _PAYLOAD, "body": _PAYLOAD, "duration": 1.0}],
            channel_name=_PAYLOAD,
            output_path=path,
        )
        content = open(path, encoding="utf-8").read()
        assert "<script>alert(1)</script>" not in content
        # 3 interpolation sites (title, section heading+body, channel_name x2)
        assert content.count("&lt;script&gt;") >= 3


def test_youtube_video_quote_only_escape_is_gone():
    """The old safe_title = title.replace('"', '&quot;') only escaped quotes --
    a </div><script> payload with no quotes at all still broke out. Confirm
    real html.escape() is used now, not the quote-only replace."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "y2.html")
        CompositionTemplate.youtube_video(
            title="</div><script>alert(2)</script>",
            sections=[],
            output_path=path,
        )
        content = open(path, encoding="utf-8").read()
        assert "<script>alert(2)</script>" not in content


def test_normal_content_still_renders_correctly():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "n.html")
        CompositionTemplate.title_card("VECTOR AI System", "Autonomous Intelligence", output_path=path)
        content = open(path, encoding="utf-8").read()
        assert "VECTOR AI System" in content
        assert "Autonomous Intelligence" in content


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
