"""HUD screen-video recorder for ARM A brand reels.

Records VECTOR's polished HUD (``frontend/VECTOR.html``) as a 9:16 video
while a real task runs, then muxes the Kokoro narration over it. Uses Playwright
page-video recording (clean, headless-capable, no desktop/gdigrab mess, no
private-screen risk) → webm, then ffmpeg → mp4.

The hard part is *liveness*: the recorder triggers a real task and lets the HUD
reflect it via its websocket/event feed during the capture window, rather than
recording an idle HUD. Sync model is narration-over-broll (v1) — the voice
describes activity generally; no frame-accurate alignment.

Degrades gracefully: returns ``None`` (never raises) when Playwright/ffmpeg are
unavailable, so the never-die ARM A loop keeps running.
"""
from __future__ import annotations

import sys
import tempfile
import uuid
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger

from core.config import CONFIG

try:
    from playwright.sync_api import sync_playwright  # noqa: F401
    _PLAYWRIGHT_OK = True
except Exception:
    _PLAYWRIGHT_OK = False

_RENDER_DIR = Path(__file__).parent.parent.parent / "renders" / "growth"


def _hud_url() -> str:
    """Where the HUD is served. Defaults to the local API's /hud/ route; override
    via CONFIG["growth"]["hud_url"] or fall back to the file:// path."""
    g = CONFIG.get("growth", {})
    if g.get("hud_url"):
        return g["hud_url"]
    served = "http://127.0.0.1:8000/hud/"
    return served


def _playwright_capture(url: str, vp: tuple, dur: float, on_ready: Callable[[], object]) -> "str | None":
    """Record the HUD page at the given vertical viewport for ``dur`` seconds.
    Calls ``on_ready`` once the page has loaded so the caller can fire the live
    task. Returns the webm path, or None on failure."""
    from playwright.sync_api import sync_playwright

    width, height = int(vp[0]), int(vp[1])
    out_dir = Path(tempfile.mkdtemp(prefix="vector_hud_"))
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": width, "height": height},
                record_video_dir=str(out_dir),
                record_video_size={"width": width, "height": height},
            )
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            try:
                on_ready()  # fire the real task now that the HUD is live
            except Exception as exc:
                logger.warning("[VECTOR][growth][hud] trigger_task failed: {}", exc)
            page.wait_for_timeout(int(dur * 1000))
            video = page.video
            video_path = video.path() if video else None
            context.close()  # finalizes/flushes the recording
            browser.close()
            return video_path
    except Exception as exc:
        logger.error("[VECTOR][growth][hud] playwright capture failed: {}", exc)
        return None


def _ffmpeg_mux(video: str, audio: str, out: str, captions: "str | None" = None) -> "str | None":
    """Mux the narration audio over the HUD video → mp4. Optionally burns an
    .srt caption file. Returns out path, or None on failure."""
    import subprocess

    cmd = ["ffmpeg", "-y", "-i", video, "-i", audio]
    if captions:
        # An absolute Windows path (C:\...\x.srt) breaks ffmpeg's filter-graph parser: the drive colon splits the option
        # and backslashes are escapes, so burning captions failed on every call (verified with a real ffmpeg 2026-09-26).
        # Forward slashes plus an escaped colon and quotes is the documented form.
        fpath = str(captions).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        cmd += ["-vf", f"subtitles='{fpath}'"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", "-map", "0:v:0", "-map", "1:a:0", out]
    try:
        subprocess.run(cmd, capture_output=True, timeout=600, check=True)
        return out
    except subprocess.CalledProcessError as exc:
        tail = (exc.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-4:]
        logger.error("[VECTOR][growth][hud] ffmpeg mux failed (exit {}): {}", exc.returncode, " | ".join(tail))
        return None
    except Exception as exc:
        logger.error("[VECTOR][growth][hud] ffmpeg mux failed: {}", exc)
        return None


class HUDRecorder:
    """Records a 9:16 HUD reel with synced narration. Never raises."""

    def record(
        self,
        narration_wav: str,
        duration_s: float,
        trigger_task: Callable[[], object],
        captions: "str | None" = None,
    ) -> "str | None":
        if not _PLAYWRIGHT_OK:
            logger.warning("[VECTOR][growth][hud] Playwright unavailable — skipping reel capture")
            return None
        try:
            vp = tuple(CONFIG["growth"]["hud_viewport"])  # (1080, 1920)
            webm = _playwright_capture(_hud_url(), vp, duration_s, on_ready=trigger_task)
            if not webm:
                return None
            _RENDER_DIR.mkdir(parents=True, exist_ok=True)
            out = str(_RENDER_DIR / f"reel_{uuid.uuid4().hex[:12]}.mp4")
            return _ffmpeg_mux(webm, narration_wav, out, captions)
        except Exception as exc:
            logger.error("[VECTOR][growth][hud] record failed: {}", exc)
            return None


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    r = HUDRecorder()
    print("hud_recorder OK", "(playwright available)" if _PLAYWRIGHT_OK else "(playwright absent — graceful)")
