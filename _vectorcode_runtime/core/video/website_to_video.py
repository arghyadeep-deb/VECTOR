"""
VECTOR Website-to-Video Pipeline
assetDownloader.ts, mediaCapture.ts, assetCataloger.ts, scaffolding.ts)

Full 7-step pipeline:
  1. Fetch URL with VECTOR Scraper (stealth mode)
  2. Extract content: title, description, images, colors, fonts
  3. Capture screenshots (desktop + mobile + scroll)
  4. Download key assets (hero images, logos)
  5. Generate HTML composition from extracted content
  6. Render composition to video
  7. Add TTS narration (optional)

Use cases:
  - Capture competitor analysis as video report
  - Turn research articles into narrated video summaries
  - Generate YouTube thumbnails from any URL
  - Document website state for audit trail
"""
from __future__ import annotations

import html as _html

__all__ = [
    "build_composition_from_content",
    "CaptureOptions",
    "CaptureResult",
    "ExtractedContent",
    "url_to_video",
    "WebContentExtractor",
    "WebScreenshotter",
    "WebsiteToVideo",
]


import asyncio
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from core.video.composition_types import Fps, FPS_30, RenderQuality
from core.video.vector_composer import (
    VectorComposer, ComposerJob, ComposerResult, CompositionTemplate
)


# ── Capture types ──────────────────────────────────────────────────────────────

@dataclass
class ExtractedContent:
    url: str
    title: str = ""
    description: str = ""
    headline: str = ""
    body_text: str = ""
    images: list[str] = field(default_factory=list)    # URLs
    colors: list[str] = field(default_factory=list)    # hex colors
    fonts: list[str] = field(default_factory=list)
    og_image: Optional[str] = None
    screenshot_path: Optional[str] = None
    mobile_screenshot_path: Optional[str] = None


@dataclass
class CaptureOptions:
    url: str
    output_path: str
    fps: Fps = field(default_factory=lambda: Fps(30, 1))
    resolution: str = "landscape"
    quality: RenderQuality = "standard"
    duration_seconds: float = 8.0
    add_narration: bool = False
    narration_voice: str = "bm_george"
    use_stealth: bool = True
    take_screenshot: bool = True
    scroll_animation: bool = True    # animate page scroll in video


@dataclass
class CaptureResult:
    output_path: str
    url: str
    title: str
    screenshot_path: Optional[str]
    content: ExtractedContent
    composer_result: Optional[ComposerResult] = None


# ── Content extractor ─────────────────────────────────────────────────────────

class WebContentExtractor:
    """
    Extract structured content from a webpage.
        """

    async def extract(self, url: str, html: str = "") -> ExtractedContent:
        if not html:
            html = await self._fetch(url)

        content = ExtractedContent(url=url)

        # Title
        title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if title_m:
            content.title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip()

        # OG tags
        og_title = re.search(r'property=["\']og:title["\'][^>]*content=["\']([^"\']+)', html, re.I)
        og_desc  = re.search(r'property=["\']og:description["\'][^>]*content=["\']([^"\']+)', html, re.I)
        og_img   = re.search(r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)', html, re.I)

        if og_title:
            content.headline = og_title.group(1).strip()
        if og_desc:
            content.description = og_desc.group(1).strip()
        if og_img:
            content.og_image = og_img.group(1).strip()

        # Meta description
        if not content.description:
            meta_desc = re.search(r'name=["\']description["\'][^>]*content=["\']([^"\']+)', html, re.I)
            if meta_desc:
                content.description = meta_desc.group(1).strip()[:300]

        # Extract images
        img_srcs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.I)
        content.images = [s for s in img_srcs[:10] if s.startswith("http")]

        # Extract heading text
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.DOTALL)
        if h1:
            content.headline = content.headline or re.sub(r"<[^>]+>", "", h1.group(1)).strip()

        logger.info("[VECTOR][website_to_video] extracted: title='{}' desc={}chars url={}",
                    content.title, len(content.description), url)
        return content

    async def _fetch(self, url: str) -> str:
        try:
            from core.scraper.vector_scraper import get_scraper
            scraper = get_scraper()
            result = await scraper.smart_fetch(url, try_stealth_on_fail=True)
            return result.content
        except Exception as e:
            logger.warning("[VECTOR][website_to_video] fetch failed: {}", e)
            return ""


# ── Screenshot capture ─────────────────────────────────────────────────────────

class WebScreenshotter:
    """
    Captures screenshots and scroll videos of websites.
        """

    async def screenshot(
        self,
        url: str,
        output_path: str,
        width: int = 1920,
        height: int = 1080,
    ) -> Optional[str]:
        try:
            from core.video.html_renderer import capture_screenshot
            return await capture_screenshot(url, output_path, width, height)
        except Exception as e:
            logger.warning("[VECTOR][website_to_video] screenshot failed: {}", e)
            return None

    async def capture_scroll_video(
        self,
        url: str,
        output_path: str,
        duration: float = 8.0,
        fps: Fps = FPS_30,
        width: int = 1920,
        height: int = 1080,
    ) -> Optional[str]:
        """Capture a smooth scroll-through of a webpage as video."""
        try:
            from playwright.async_api import async_playwright
            from core.video.video_encoder import VideoEncoder, EncodeOptions, find_ffmpeg
            import subprocess
        except ImportError:
            logger.warning("[VECTOR][website_to_video] playwright/ffmpeg not available")
            return None

        if not find_ffmpeg():
            return None

        with tempfile.TemporaryDirectory() as tmp:
            frame_dir = os.path.join(tmp, "frames")
            os.makedirs(frame_dir)

            total_frames = int(duration * fps.to_float())
            frame_idx = 0

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
                context = await browser.new_context(
                    viewport={"width": width, "height": height},
                )
                page = await context.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30_000)

                # Get page height for scroll calculation
                page_height = await page.evaluate("document.documentElement.scrollHeight")
                max_scroll = max(0, page_height - height)

                for i in range(total_frames):
                    scroll_y = int((i / total_frames) * max_scroll)
                    await page.evaluate(f"window.scrollTo(0, {scroll_y})")
                    frame_path = os.path.join(frame_dir, f"frame_{i:08d}.png")
                    await page.screenshot(path=frame_path)
                    frame_idx += 1

                await browser.close()

            # Encode frames → video
            encoder = VideoEncoder()
            encode_opts = EncodeOptions(fps=fps, quality="standard", format="mp4")
            encoder.encode(
                os.path.join(frame_dir, "frame_%08d.png"),
                output_path, encode_opts,
            )

        return output_path if os.path.exists(output_path) else None


# ── HTML composition from extracted content ────────────────────────────────────

def build_composition_from_content(
    content: ExtractedContent,
    screenshot_path: Optional[str],
    output_path: str,
    scroll_animation: bool = True,
) -> str:
    """
    Build a VECTOR HTML composition from extracted web content.
        """
    # content.title/.headline/.description were extracted via regex from a
    # SCRAPED, attacker-controlled webpage's <title>/og:*/<h1> tags -- this
    # HTML is then rendered by a real headless browser (capture_screenshot),
    # so an unescaped </div><script> in a malicious page's title/og tags
    # executed arbitrary JS in that render context. Escape everything
    # interpolated into the generated composition, including the
    # caller-supplied url (defense in depth, lower risk but still rendered).
    title    = _html.escape(content.title or "Website Overview")
    headline = _html.escape(content.headline or (content.title or "Website Overview"))
    desc     = _html.escape(content.description[:200] if content.description else "")
    url      = _html.escape(content.url)
    domain   = _html.escape(re.sub(r"https?://(www\.)?", "", content.url).split("/")[0])

    screenshot_css = ""
    screenshot_html = ""
    if screenshot_path and os.path.exists(screenshot_path):
        import base64
        with open(screenshot_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        screenshot_css = """
  .screenshot-panel {
    position:absolute; right:80px; top:50%;
    transform:translateY(-50%);
    width:800px; height:500px; object-fit:cover;
    border-radius:12px; border:1px solid rgba(0,212,255,0.2);
    box-shadow:0 0 60px rgba(0,212,255,0.1);
    animation: slideIn 0.8s ease-out forwards;
  }
  @keyframes slideIn {
    from { opacity:0; transform:translateY(-50%) translateX(40px); }
    to   { opacity:1; transform:translateY(-50%) translateX(0); }
  }"""
        screenshot_html = f'<img class="screenshot-panel" src="data:image/png;base64,{b64}" />'

    scroll_script = ""
    if scroll_animation and screenshot_path:
        scroll_script = """
  setInterval(() => {
    const el = document.querySelector('.screenshot-panel');
    if (el) {
      const t = (Date.now() / 5000) % 1;
      el.style.objectPosition = `center ${t * 100}%`;
    }
  }, 50);"""

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    width:1920px; height:1080px; overflow:hidden;
    background:#020A14; color:#e5e5e5;
    font-family:'Inter',sans-serif; position:relative;
  }}
  .left-panel {{
    position:absolute; left:80px; top:50%;
    transform:translateY(-50%);
    width:900px;
  }}
  .domain {{
    font-size:22px; color:rgba(0,212,255,0.6);
    letter-spacing:0.08em; text-transform:uppercase;
    margin-bottom:24px;
    animation: fadeUp 0.6s ease-out forwards;
  }}
  .headline {{
    font-size:56px; font-weight:300; color:#00D4FF;
    line-height:1.15; letter-spacing:-0.02em;
    margin-bottom:32px;
    animation: fadeUp 0.6s ease-out 0.2s both;
  }}
  .description {{
    font-size:26px; color:rgba(229,229,229,0.7);
    line-height:1.6; max-width:800px;
    animation: fadeUp 0.6s ease-out 0.4s both;
  }}
  .url-bar {{
    position:absolute; bottom:48px; left:80px;
    font-size:18px; color:rgba(0,212,255,0.4);
    font-family:'IBM Plex Mono', monospace;
    animation: fadeUp 0.6s ease-out 0.6s both;
  }}
  @keyframes fadeUp {{
    from {{ opacity:0; transform:translateY(16px); }}
    to   {{ opacity:1; transform:translateY(0); }}
  }}
  {screenshot_css}
</style>
</head>
<body>
  <div class="left-panel">
    <div class="domain">{domain}</div>
    <div class="headline" id="headline">{headline}</div>
    <div class="description" id="description">{desc}</div>
  </div>
  {screenshot_html}
  <div class="url-bar">{url[:80]}</div>
<script>
  window.__vector = {{
    enableRenderMode() {{}},
    renderSeek(t) {{}},
    setVariables(v) {{
      if (v.headline) document.getElementById('headline').textContent = v.headline;
      if (v.description) document.getElementById('description').textContent = v.description;
    }},
  }};
  {scroll_script}
</script>
</body>
</html>"""
    Path(output_path).write_text(html, encoding="utf-8")
    return output_path


# ── Main pipeline ─────────────────────────────────────────────────────────────

class WebsiteToVideo:
    """
    Complete website-to-video pipeline.
        """

    def __init__(self) -> None:
        self._extractor  = WebContentExtractor()
        self._screenshotter = WebScreenshotter()
        self._composer   = VectorComposer(
            on_progress=lambda p, m: logger.info("[VECTOR][w2v] {:.0f}% {}", p*100, m)
        )

    async def capture(self, opts: CaptureOptions) -> CaptureResult:
        """Full 7-step pipeline: URL → video."""
        t0 = time.perf_counter()
        logger.info("[VECTOR][website_to_video] starting capture: {}", opts.url)

        with tempfile.TemporaryDirectory(prefix="vector_w2v_") as tmp:
            # Step 1-2: Fetch + extract content
            content = await self._extractor.extract(opts.url)

            # Step 3: Screenshot
            screenshot_path = None
            if opts.take_screenshot:
                ss_path = os.path.join(tmp, "screenshot.png")
                screenshot_path = await self._screenshotter.screenshot(
                    opts.url, ss_path,
                    width=1920 if opts.resolution == "landscape" else 1080,
                    height=1080 if opts.resolution == "landscape" else 1920,
                )
                content.screenshot_path = screenshot_path

            # Step 4-5: Build HTML composition
            comp_path = os.path.join(tmp, "composition.html")
            build_composition_from_content(
                content, screenshot_path, comp_path,
                scroll_animation=opts.scroll_animation,
            )

            # Step 6: Render composition → video
            narration_script = None
            if opts.add_narration and content.description:
                narration_script = (
                    f"{content.headline or content.title}. "
                    f"{content.description}"
                )

            composer_result = await self._composer.render(ComposerJob(
                composition_path=comp_path,
                output_path=opts.output_path,
                fps=opts.fps,
                resolution=opts.resolution,
                duration_seconds=opts.duration_seconds,
                quality=opts.quality,
                narration=narration_script,
                narration_voice=opts.narration_voice,
            ))

        elapsed = time.perf_counter() - t0
        logger.info("[VECTOR][website_to_video] done in {:.1f}s: {}", elapsed, opts.output_path)

        return CaptureResult(
            output_path=opts.output_path,
            url=opts.url,
            title=content.title,
            screenshot_path=screenshot_path,
            content=content,
            composer_result=composer_result,
        )


# ── Quick API ─────────────────────────────────────────────────────────────────

async def url_to_video(
    url: str,
    output_path: str,
    duration: float = 8.0,
    quality: RenderQuality = "standard",
    add_narration: bool = False,
) -> CaptureResult:
    """One-call website-to-video for agents."""
    pipeline = WebsiteToVideo()
    opts = CaptureOptions(
        url=url,
        output_path=output_path,
        duration_seconds=duration,
        quality=quality,
        add_narration=add_narration,
    )
    return await pipeline.capture(opts)


if __name__ == "__main__":
    # Smoke test: content extraction from static HTML
    import asyncio

    extractor = WebContentExtractor()
    html = """
    <html><head>
    <title>VECTOR AI System</title>
    <meta property="og:description" content="Autonomous multi-agent AI platform">
    </head><body><h1>VECTOR Intelligence</h1></body></html>
    """

    async def _test():
        content = await extractor.extract("https://example.com", html=html)
        assert content.title == "VECTOR AI System"
        assert "Autonomous" in content.description
        assert content.headline == "VECTOR Intelligence"
        print(f"Extracted: title={content.title!r} desc={content.description!r}")

        # Test composition builder
        with tempfile.TemporaryDirectory() as tmp:
            comp_path = os.path.join(tmp, "comp.html")
            build_composition_from_content(content, None, comp_path)
            comp_html = Path(comp_path).read_text()
            assert "VECTOR AI System" in comp_html
            assert "window.__vector" in comp_html
            print(f"Composition HTML: {len(comp_html)} chars")

        print("OK website_to_video.py")

    asyncio.run(_test())
