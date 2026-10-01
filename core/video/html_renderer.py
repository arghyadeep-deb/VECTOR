"""
VECTOR HTML Frame Renderer

Captures an HTML composition as a sequence of PNG frames using Playwright.
Pipeline:
  1. Serve the HTML file via a local HTTP server (avoids file:// CORS)
  2. Launch headless Chromium with correct viewport/DPR for target resolution
  3. Seek the VECTOR runtime to each frame's timestamp
  4. Capture screenshot as PNG
  5. Write frames to temp directory for FFmpeg ingestion

Supports:
  - Variable injection via window.__vector.setVariables(vars)
  - Parallel frame capture across multiple browser contexts
  - GPU/software rendering toggle (hardware vs SwiftShader)
  - 4K supersampling via deviceScaleFactor
"""
from __future__ import annotations

__all__ = [
    "capture_screenshot",
    "FrameCaptureResult",
    "HTMLFrameRenderer",
    "RendererConfig",
]


import asyncio
import base64
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger

from core.video.composition_types import Fps, canvas_size, QUALITY_CRF, RenderQuality

# â”€â”€ Load inline runtime JS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_RUNTIME_JS_PATH = Path(__file__).parent / "runtime" / "vector_runtime.js"
_RUNTIME_JS: str = ""
try:
    _RUNTIME_JS = _RUNTIME_JS_PATH.read_text(encoding="utf-8")
except Exception: logger.debug("[VECTOR][video] exception suppressed")  # runtime optional — compositions with window.__vector already set work fine


# â”€â”€ Local file server â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class _SilentHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        return None


def _start_file_server(directory: str, port: int) -> HTTPServer:
    """Serve composition files over HTTP to avoid CORS issues."""
    # `directory` must be a constructor argument: SimpleHTTPRequestHandler.__init__ sets
    # self.directory = os.getcwd() when it is not passed, which shadowed the old class attribute
    # and made the server serve the process's cwd instead of the composition's folder (404s).
    server = HTTPServer(("127.0.0.1", port), partial(_SilentHandler, directory=directory))
    # 2026-09-23: deliberate exception to "never use threading, use
    # asyncio" (.claude/rules/libraries.md) -- `http.server.HTTPServer`
    # is a synchronous, blocking stdlib server with no asyncio-native
    # equivalent; `serve_forever()` never returns, so it must run in a
    # dedicated thread to avoid blocking whatever called this function.
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _find_free_port(start: int = 51000) -> int:
    import socket
    for port in range(start, start + 1000):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free port found in range 51000-52000")


# â”€â”€ Frame capture result â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@dataclass
class FrameCaptureResult:
    frame_dir: str
    frame_count: int
    width: int
    height: int
    fps: Fps
    duration_seconds: float
    avg_capture_ms: float
    frames: list[str] = field(default_factory=list)  # sorted PNG paths


@dataclass
class RendererConfig:
    """VECTOR Video render configuration."""
    quality: RenderQuality = "standard"
    use_gpu: bool = False
    device_scale_factor: int = 1  # >1 = supersampling for 4K
    timeout_ms: int = 30_000
    warmup_frames: int = 2       # discard first N frames (JS warmup)
    on_progress: Optional[Callable[[int, int, float], None]] = None  # (frame, total, ms)


# â”€â”€ Playwright frame capture â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class HTMLFrameRenderer:
    """
    Captures an HTML composition as PNG frames using Playwright.
        """

    def __init__(self, config: Optional[RendererConfig] = None) -> None:
        self._config = config or RendererConfig()

    async def capture(
        self,
        composition_path: str,
        output_dir: str,
        fps: Fps,
        duration_seconds: float,
        resolution: str = "landscape",
        variables: Optional[dict[str, Any]] = None,
    ) -> FrameCaptureResult:
        """
        Capture all frames for a composition.
        Returns FrameCaptureResult with sorted PNG paths.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                "playwright not installed. Run: pip install playwright && playwright install chromium"
            )

        width, height = canvas_size(resolution)
        real_width  = width  * self._config.device_scale_factor
        real_height = height * self._config.device_scale_factor

        total_frames = int(duration_seconds * fps.to_float())
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Serve composition files over local HTTP
        comp_path    = Path(composition_path).resolve()
        project_dir  = str(comp_path.parent)
        file_name    = comp_path.name
        port         = _find_free_port()
        server       = _start_file_server(project_dir, port)
        base_url     = f"http://127.0.0.1:{port}/{file_name}"

        logger.info(
            "[VECTOR][html_renderer] Capturing {} frames at {}x{} from {}",
            total_frames, real_width, real_height, comp_path.name,
        )

        frames_written: list[str] = []
        capture_times: list[float] = []

        try:
            async with async_playwright() as pw:
                launch_args = self._browser_args()
                browser = await pw.chromium.launch(
                    headless=True,
                    args=launch_args,
                )
                context = await browser.new_context(
                    viewport={"width": real_width, "height": real_height},
                    device_scale_factor=self._config.device_scale_factor,
                )
                page = await context.new_page()

                # Navigate and wait for composition runtime to signal ready
                await page.goto(base_url, wait_until="networkidle",
                                timeout=self._config.timeout_ms)

                # Inject VECTOR runtime (GSAP/anime.js/CSS/WAAPI adapters + renderSeek)
                if _RUNTIME_JS:
                    await page.evaluate(_RUNTIME_JS)
                    logger.debug("[VECTOR][html_renderer] runtime injected ({} chars)", len(_RUNTIME_JS))

                # Inject variables if provided
                if variables:
                    vars_json = json.dumps(variables)
                    await page.evaluate(
                        f"window.__vector && window.__vector.setVariables({vars_json})"
                    )

                # Enable render mode: pauses all animation engines, enables deterministic seeking
                await page.evaluate(
                    "window.__vector && window.__vector.enableRenderMode()"
                )

                frame_time_step = 1.0 / fps.to_float()
                warmup = self._config.warmup_frames

                for i in range(-warmup, total_frames):
                    t_start = time.perf_counter()
                    frame_time = max(0.0, i * frame_time_step)

                    # Seek all animation engines to this frame timestamp
                    await page.evaluate(
                        f"window.__vector && window.__vector.renderSeek({frame_time:.6f})"
                    )

                    # Skip warmup frames
                    if i < 0:
                        continue

                    # Capture PNG frame
                    frame_name = f"frame_{i:08d}.png"
                    frame_path = os.path.join(output_dir, frame_name)
                    await page.screenshot(path=frame_path, full_page=False)

                    elapsed_ms = (time.perf_counter() - t_start) * 1000
                    capture_times.append(elapsed_ms)
                    frames_written.append(frame_path)

                    if self._config.on_progress:
                        avg = sum(capture_times) / len(capture_times)
                        self._config.on_progress(i, total_frames, avg)

                await browser.close()
        finally:
            # shutdown() only stops serve_forever()'s loop -- it does not
            # release the listening socket. Without server_close(), every
            # capture() call leaked a bound port/file descriptor forever
            # (each call picks a fresh port via _find_free_port(), so this
            # was invisible until enough renders ran to exhaust the range or
            # hit the OS file-descriptor limit).
            server.shutdown()
            server.server_close()

        avg_ms = sum(capture_times) / len(capture_times) if capture_times else 0.0
        frames_written.sort()

        logger.info(
            "[VECTOR][html_renderer] Captured {} frames, avg {:.1f}ms/frame",
            len(frames_written), avg_ms,
        )

        return FrameCaptureResult(
            frame_dir=output_dir,
            frame_count=len(frames_written),
            width=real_width,
            height=real_height,
            fps=fps,
            duration_seconds=duration_seconds,
            avg_capture_ms=avg_ms,
            frames=frames_written,
        )

    def _browser_args(self) -> list[str]:
        args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--font-render-hinting=none",    # deterministic fonts
            "--disable-lcd-text",
            "--disable-font-subpixel-positioning",
            "--disable-extensions",
            "--hide-scrollbars",
            "--mute-audio",
        ]
        if not self._config.use_gpu:
            args += [
                "--disable-gpu",
                "--use-gl=swiftshader",
                "--disable-software-rasterizer",
            ]
        return args


# â”€â”€ Screenshot capture (single frame) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def capture_screenshot(
    url: str,
    output_path: str,
    width: int = 1920,
    height: int = 1080,
    wait_for: str = "networkidle",
    full_page: bool = False,
) -> str:
    """Capture a single screenshot of any URL. Used by website_to_video."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError("playwright not installed")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            viewport={"width": width, "height": height},
        )
        page = await context.new_page()
        await page.goto(url, wait_until=wait_for, timeout=30_000)
        await page.screenshot(path=output_path, full_page=full_page)
        await browser.close()

    logger.info("[VECTOR][html_renderer] screenshot saved: {}", output_path)
    return output_path


if __name__ == "__main__":
    import tempfile
    # Smoke test: composition types
    fps = Fps(30, 1)
    assert fps.to_ffmpeg_arg() == "30"

    w, h = canvas_size("landscape")
    assert w == 1920 and h == 1080

    config = RendererConfig(quality="standard")
    renderer = HTMLFrameRenderer(config)
    assert renderer._config.quality == "standard"

    print("OK html_renderer.py — config + types OK (Playwright requires install for live test)")
