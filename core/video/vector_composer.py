"""
VECTOR VECTOR Video Composer
High-level orchestrator — 
Full render pipeline:
  HTML composition → frame capture → audio mix → video encode → final MP4

Supports:
  - Parametric rendering (inject variables into HTML templates)
  - Multi-track audio (TTS narration + background music)
  - Background removal overlay compositing
  - Parallel worker capture (multiple browser contexts)
  - GPU encoding (RTX 5070 Ti NVENC)
  - 4K supersampling
  - HDR output
  - PNG-sequence output for AE/Nuke/DaVinci

Quick usage (District 18 content generation):
    from core.video.vector_composer import VectorComposer, ComposerJob

    job = ComposerJob(
        composition_path="templates/youtube_intro.html",
        output_path="renders/intro.mp4",
        variables={"title": "AI News", "date": "2026-05-18"},
        narration="Welcome to VECTOR's weekly AI update...",
        fps=Fps(30, 1),
        resolution="landscape",
    )
    composer = VectorComposer()
    result = asyncio.run(composer.render(job))
"""
from __future__ import annotations

__all__ = [
    "ComposerJob",
    "ComposerResult",
    "CompositionTemplate",
    "render_html_to_video",
    "VectorComposer",
]


import asyncio
import html
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger

from core.video.composition_types import (
    Fps, FPS_30, OutputFormat, RenderQuality, HdrMode, BgRemovalQuality,
    canvas_size, QUALITY_CRF,
)
from core.video.html_renderer import HTMLFrameRenderer, RendererConfig
from core.video.video_encoder import VideoEncoder, EncodeOptions
from core.video.audio_mixer import AudioMixer, AudioTrack, NarrationPipeline


# ── Composer job ──────────────────────────────────────────────────────────────

@dataclass
class ComposerJob:
    """Full render specification — everything needed to produce a video."""
    composition_path: str = ""
    output_path: str = "output.mp4"

    # Composition settings
    fps: Fps = field(default_factory=lambda: Fps(30, 1))
    resolution: str = "landscape"
    duration_seconds: float = 10.0
    variables: dict[str, Any] = field(default_factory=dict)

    # Quality
    quality: RenderQuality = "standard"
    format: OutputFormat = "mp4"
    use_gpu: bool = False
    crf: Optional[int] = None
    video_bitrate: Optional[str] = None

    # Audio
    narration: Optional[str] = None          # TTS script
    narration_voice: str = "bm_george"
    narration_speed: float = 0.85
    bg_music_path: Optional[str] = None
    bg_music_volume: float = 0.15

    # Background removal
    remove_bg: bool = False
    bg_model: str = "u2net_human"
    bg_quality: BgRemovalQuality = "balanced"

    # Advanced
    workers: int = 1
    hdr_mode: HdrMode = "auto"
    device_scale_factor: int = 1     # 2 = 4K from 1080p composition


@dataclass
class ComposerResult:
    output_path: str
    duration_seconds: float
    frame_count: int
    file_size_bytes: int
    total_ms: float
    capture_avg_ms: float
    codec: str
    has_audio: bool


# ── VectorComposer ────────────────────────────────────────────────────────────

class VectorComposer:
    """
    Full render pipeline orchestrator.
        """

    def __init__(
        self,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> None:
        self._on_progress = on_progress

    def _progress(self, pct: float, msg: str) -> None:
        logger.info("[VECTOR][composer] {:.0f}% {}", pct * 100, msg)
        if self._on_progress:
            self._on_progress(pct, msg)

    async def render(self, job: ComposerJob) -> ComposerResult:
        """Full pipeline: lint → HTML → frames → audio → encode."""
        t0 = time.perf_counter()

        # Stage 0: Lint composition before spending render time
        if job.composition_path and os.path.exists(job.composition_path):
            try:
                from core.video.composition_linter import lint_file
                lint_result = lint_file(job.composition_path)
                if not lint_result.ok:
                    self._progress(0.0, f"Lint: {lint_result.error_count} errors")
                    for f in lint_result.errors:
                        logger.warning("[VECTOR][composer] lint ERROR {}: {}", f.code, f.message)
                elif lint_result.warning_count:
                    logger.info("[VECTOR][composer] lint: {} warnings", lint_result.warning_count)
            except Exception as e:
                logger.debug("[VECTOR][composer] lint skipped: {}", e)

        with tempfile.TemporaryDirectory(prefix="vector_render_") as tmp:
            frame_dir  = os.path.join(tmp, "frames")
            audio_path = os.path.join(tmp, "audio.aac")
            os.makedirs(frame_dir, exist_ok=True)

            # Stage 1: Capture HTML frames
            self._progress(0.0, "Capturing frames...")
            capture_result = await self._capture_frames(job, frame_dir)
            self._progress(0.4, f"Captured {capture_result.frame_count} frames")

            # Stage 2: Audio
            has_audio = False
            if job.narration or job.bg_music_path:
                self._progress(0.45, "Mixing audio...")
                has_audio = await self._mix_audio(job, audio_path, job.duration_seconds)
                self._progress(0.55, "Audio mixed")

            # Stage 3: Encode
            self._progress(0.55, "Encoding video...")
            frame_pattern = os.path.join(frame_dir, "frame_%08d.png")
            encode_opts = EncodeOptions(
                fps=job.fps,
                quality=job.quality,
                format=job.format,
                use_gpu=job.use_gpu,
                crf=job.crf,
                video_bitrate=job.video_bitrate,
                audio_path=audio_path if has_audio else None,
                width=capture_result.width,
                height=capture_result.height,
            )

            Path(job.output_path).parent.mkdir(parents=True, exist_ok=True)
            encoder = VideoEncoder()
            encode_result = encoder.encode(frame_pattern, job.output_path, encode_opts)
            self._progress(0.95, "Encode complete")

        # Stage 4: Optional background removal pass
        if job.remove_bg and Path(job.output_path).suffix.lower() == ".webm":
            self._progress(0.95, "Removing background...")
            bg_out = str(Path(job.output_path).with_stem(
                Path(job.output_path).stem + "_alpha"
            ).with_suffix(".webm"))
            from core.video.background_remover import BackgroundRemover
            remover = BackgroundRemover(model_id=job.bg_model, quality=job.bg_quality)
            remover.remove_video(job.output_path, bg_out)
            job.output_path = bg_out
            self._progress(1.0, "Background removed")

        total_ms = (time.perf_counter() - t0) * 1000
        file_size = os.path.getsize(job.output_path) if os.path.exists(job.output_path) else 0

        self._progress(1.0, f"Done in {total_ms/1000:.1f}s")
        logger.info(
            "[VECTOR][composer] render complete: {} ({:.1f}MB, {:.1f}s)",
            job.output_path, file_size / 1_048_576, total_ms / 1000,
        )

        return ComposerResult(
            output_path=job.output_path,
            duration_seconds=job.duration_seconds,
            frame_count=capture_result.frame_count,
            file_size_bytes=file_size,
            total_ms=total_ms,
            capture_avg_ms=capture_result.avg_capture_ms,
            codec=encode_result.codec,
            has_audio=has_audio,
        )

    async def _capture_frames(self, job: ComposerJob, frame_dir: str):
        config = RendererConfig(
            quality=job.quality,
            use_gpu=job.use_gpu,
            device_scale_factor=job.device_scale_factor,
        )
        renderer = HTMLFrameRenderer(config)
        return await renderer.capture(
            composition_path=job.composition_path,
            output_dir=frame_dir,
            fps=job.fps,
            duration_seconds=job.duration_seconds,
            resolution=job.resolution,
            variables=job.variables,
        )

    async def render_via_hyperframes(self, html_path: str, output_path: str,
                                      fps: int = 30, width: int = 1920, height: int = 1080) -> str:
        """Render HTML composition via hyperframes producer sidecar (port 7421)."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(
                    "http://localhost:7421/render",
                    json={
                        "compositionPath": str(html_path),
                        "outputPath": str(output_path),
                        "fps": fps,
                        "width": width,
                        "height": height,
                    },
                )
                if r.status_code == 200:
                    data = r.json()
                    logger.info("[VECTOR][composer] Rendered via hyperframes: {}", output_path)
                    return data.get("outputUrl", output_path)
                else:
                    raise RuntimeError(f"hyperframes returned {r.status_code}: {r.text[:200]}")
        except Exception as e:
            logger.warning("[VECTOR][composer] hyperframes unavailable ({}), falling back to html_renderer", e)
            # Fallback to VECTOR's own renderer
            job = ComposerJob(
                composition_path=html_path,
                output_path=output_path,
                fps=Fps(fps, 1),
            )
            result = await self.render(job)
            return result.output_path

    async def generate_video_from_prompt(
        self,
        prompt: str,
        image_path: str | None = None,
        audio_path: str | None = None,
        duration: int = 5,
        output_path: str | None = None,
    ) -> str | None:
        """
        Generate video from a text prompt via the LOCAL generative studio
        (Wan2GP). The old RunwayML/Pika stub registry was removed 2026-07-04 —
        free local only. Falls back gracefully to None (composer then uses
        image + narration instead of generated footage).
        """
        try:
            from core.media.generative_studio import GenerativeStudio
            studio = GenerativeStudio()
            if image_path:
                res = await studio.animate_image(image=image_path, prompt=prompt or "")
            else:
                res = await studio.generate_video(prompt=prompt or "")
            url = (res or {}).get("url") or (res or {}).get("video_path")
            if url:
                logger.info("[VECTOR][composer] video generated locally (Wan2GP): {}", url)
            return url
        except Exception as e:
            logger.warning("[VECTOR][composer] local video generation unavailable: {}", e)
            return None

    async def _mix_audio(
        self,
        job: ComposerJob,
        audio_path: str,
        target_duration: float,
    ) -> bool:
        try:
            pipeline = NarrationPipeline()
            pipeline.produce(
                narration_script=job.narration or "",
                bg_music_path=job.bg_music_path,
                output_path=audio_path,
                target_duration=target_duration,
                bg_volume=job.bg_music_volume,
            )
            return os.path.exists(audio_path) and os.path.getsize(audio_path) > 0
        except Exception as e:
            logger.warning("[VECTOR][composer] audio mix failed: {}", e)
            return False


# ── HTML template builder ─────────────────────────────────────────────────────

class CompositionTemplate:
    """
    Build HTML compositions from Python data.
        """

    @staticmethod
    def data_viz(
        title: str,
        data: dict[str, Any],
        style: str = "dark",
        output_path: str = "composition.html",
    ) -> str:
        """Generate a data visualization HTML composition."""
        bg_color  = "#020A14" if style == "dark" else "#f6f5f1"
        txt_color = "#00D4FF" if style == "dark" else "#0a0a0a"
        accent    = "#00D4FF" if style == "dark" else "#2563eb"
        safe_title = html.escape(title)

        bars_html = ""
        if isinstance(data, dict):
            max_val = max(data.values()) if data else 1
            for key, val in data.items():
                pct = (val / max_val) * 100
                bars_html += f"""
                <div class="bar-row">
                  <span class="label">{html.escape(str(key))}</span>
                  <div class="bar-bg">
                    <div class="bar-fill" style="width:{pct:.1f}%"></div>
                  </div>
                  <span class="value">{html.escape(str(val))}</span>
                </div>"""

        html_doc = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    width:1920px; height:1080px; overflow:hidden;
    background:{bg_color}; color:{txt_color};
    font-family:'Inter',sans-serif; display:flex;
    flex-direction:column; align-items:center; justify-content:center;
  }}
  h1 {{ font-size:64px; font-weight:300; margin-bottom:48px; letter-spacing:-0.02em; }}
  .chart {{ width:1400px; }}
  .bar-row {{
    display:flex; align-items:center; gap:24px;
    margin-bottom:24px;
  }}
  .label {{ width:240px; font-size:28px; text-align:right; opacity:0.8; }}
  .bar-bg {{
    flex:1; height:48px; background:rgba(255,255,255,0.05);
    border-radius:8px; overflow:hidden;
  }}
  .bar-fill {{
    height:100%; background:{accent};
    border-radius:8px; transition:width 1s ease-out;
  }}
  .value {{ width:120px; font-size:28px; font-weight:600; }}
</style>
</head>
<body>
<h1>{safe_title}</h1>
<div class="chart">{bars_html}</div>
<script>
  // VECTOR runtime contract
  window.__vector = {{
    enableRenderMode() {{ document.body.style.transition = 'none'; }},
    renderSeek(t) {{ /* static composition */ }},
    setVariables(vars) {{
      if (vars.title) document.querySelector('h1').textContent = vars.title;
    }},
  }};
</script>
</body>
</html>"""
        Path(output_path).write_text(html_doc, encoding="utf-8")
        return output_path

    @staticmethod
    def title_card(
        title: str,
        subtitle: str = "",
        style: str = "dark",
        output_path: str = "title.html",
    ) -> str:
        """Generate a title card HTML composition."""
        bg  = "#020A14" if style == "dark" else "#f6f5f1"
        fg  = "#00D4FF" if style == "dark" else "#0a0a0a"
        sub = "rgba(0,212,255,0.6)" if style == "dark" else "#6b6b6b"
        safe_title = html.escape(title)
        safe_subtitle = html.escape(subtitle)

        html_doc = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    width:1920px; height:1080px; overflow:hidden;
    background:{bg}; display:flex;
    flex-direction:column; align-items:center; justify-content:center;
    font-family:'Inter',sans-serif;
  }}
  .title {{
    font-size:96px; font-weight:300; color:{fg};
    letter-spacing:-0.03em; text-align:center;
    animation: fadeIn 0.8s ease-out forwards;
  }}
  .sub {{
    font-size:40px; color:{sub}; margin-top:24px;
    text-align:center; font-weight:300;
    animation: fadeIn 0.8s ease-out 0.3s both;
  }}
  @keyframes fadeIn {{
    from {{ opacity:0; transform:translateY(20px); }}
    to   {{ opacity:1; transform:translateY(0); }}
  }}
</style>
</head>
<body>
  <div class="title" id="title">{safe_title}</div>
  <div class="sub"   id="subtitle">{safe_subtitle}</div>
<script>
  window.__vector = {{
    enableRenderMode() {{ document.body.style.animation='none'; }},
    renderSeek(t) {{ /* static */ }},
    setVariables(v) {{
      if (v.title)    document.getElementById('title').textContent=v.title;
      if (v.subtitle) document.getElementById('subtitle').textContent=v.subtitle;
    }},
  }};
</script>
</body>
</html>"""
        Path(output_path).write_text(html_doc, encoding="utf-8")
        return output_path

    @staticmethod
    def youtube_video(
        title: str,
        sections: list[dict],
        channel_name: str = "VECTOR AI",
        niche: str = "AI",
        output_path: str = "youtube_video.html",
    ) -> str:
        """
        Branded YouTube video composition template.
        sections = [{"heading": str, "body": str, "duration": float}, ...]
        Each section is shown for its duration seconds sequentially.
        Total duration = 3s intro + sum(section durations) + 5s outro
        """
        NICHE_COLORS = {
            "AI":      ("#020A14", "#00D4FF", "#0066CC"),
            "finance": ("#021008", "#00FF88", "#007A44"),
            "tech":    ("#07020A", "#C084FC", "#6D28D9"),
            "health":  ("#020A06", "#34D399", "#059669"),
        }
        bg, accent, btn = NICHE_COLORS.get(niche, NICHE_COLORS["AI"])

        # Build timed section HTML with data-start/data-duration
        intro_dur = 3.0
        current_time = intro_dur
        sections_html = ""
        for i, sec in enumerate(sections):
            dur = float(sec.get("duration", 8.0))
            heading = html.escape(str(sec.get("heading", "")))
            body = html.escape(str(sec.get("body", "")))
            sections_html += f"""
  <div data-start="{current_time:.2f}" data-duration="{dur:.2f}" class="section" id="sec{i}"
       style="visibility:hidden">
    <div class="sec-num">{i+1:02d}</div>
    <div class="sec-heading">{heading}</div>
    <div class="sec-body">{body}</div>
  </div>"""
            current_time += dur

        outro_start = current_time
        total_dur = current_time + 5.0

        safe_title = html.escape(title)
        safe_channel_name = html.escape(channel_name)

        html_doc = f"""<!DOCTYPE html>
<html data-composition-variables='[]'>
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    width:1920px; height:1080px; overflow:hidden;
    background:{bg}; color:#e5e5e5;
    font-family:'Inter',-apple-system,sans-serif;
    position:relative;
  }}
  /* ── Persistent brand bar ── */
  .brand-bar {{
    position:absolute; bottom:0; left:0; right:0;
    height:6px; background:{accent};
  }}
  .channel-tag {{
    position:absolute; top:40px; right:60px;
    font-size:22px; color:rgba(229,229,229,0.4);
    letter-spacing:0.1em; text-transform:uppercase;
  }}
  /* ── Intro card (0 – 3s) ── */
  .intro {{
    position:absolute; inset:0;
    display:flex; flex-direction:column;
    align-items:center; justify-content:center;
    animation: fadeOut 0.6s ease-in {intro_dur - 0.6:.2f}s forwards;
  }}
  .intro-title {{
    font-size:88px; font-weight:300; color:{accent};
    letter-spacing:-0.03em; text-align:center;
    animation: slideUp 0.7s ease-out forwards;
  }}
  .intro-channel {{
    font-size:28px; color:rgba(229,229,229,0.5);
    margin-top:20px;
    animation: slideUp 0.7s ease-out 0.2s both;
  }}
  /* ── Content sections ── */
  .section {{
    position:absolute; inset:0;
    display:flex; align-items:center; padding:120px;
  }}
  .sec-num {{
    font-size:180px; font-weight:800; color:rgba(229,229,229,0.04);
    position:absolute; right:80px; bottom:-20px;
    line-height:1; user-select:none;
  }}
  .sec-heading {{
    font-size:68px; font-weight:300; color:{accent};
    line-height:1.2; letter-spacing:-0.02em;
    margin-bottom:32px;
  }}
  .sec-body {{
    font-size:34px; color:rgba(229,229,229,0.75);
    line-height:1.65; max-width:1300px;
  }}
  .section > div:not(.sec-num) {{ display:flex; flex-direction:column; }}
  /* ── Outro ── */
  .outro {{
    position:absolute; inset:0;
    display:flex; flex-direction:column;
    align-items:center; justify-content:center;
    visibility:hidden;
  }}
  .sub-btn {{
    background:{btn}; color:#fff;
    font-size:36px; font-weight:600; padding:22px 60px;
    border-radius:50px; margin-top:32px;
    animation: pulse 1.5s ease-in-out infinite;
  }}
  @keyframes slideUp {{
    from {{ opacity:0; transform:translateY(24px); }}
    to   {{ opacity:1; transform:translateY(0); }}
  }}
  @keyframes fadeOut {{
    to {{ opacity:0; pointer-events:none; }}
  }}
  @keyframes pulse {{
    0%,100% {{ transform:scale(1); }}
    50%     {{ transform:scale(1.04); }}
  }}
</style>
</head>
<body>
  <!-- Intro -->
  <div class="intro" data-start="0" data-duration="{intro_dur:.1f}" id="intro">
    <div class="intro-title" id="vid-title">{safe_title}</div>
    <div class="intro-channel">{safe_channel_name}</div>
  </div>

  <!-- Sections -->
  {sections_html}

  <!-- Outro -->
  <div class="outro" data-start="{outro_start:.2f}" data-duration="5" id="outro">
    <div class="intro-title" style="font-size:56px">If this helped, subscribe!</div>
    <div class="sub-btn">SUBSCRIBE</div>
  </div>

  <div class="brand-bar"></div>
  <div class="channel-tag">{safe_channel_name}</div>

<script>
  window.__timelines = window.__timelines || {{}};
  window.__vector = {{
    enableRenderMode() {{}},
    renderSeek(t) {{
      document.querySelectorAll('[data-start]').forEach(el => {{
        var s = parseFloat(el.getAttribute('data-start') || 0);
        var d = parseFloat(el.getAttribute('data-duration') || 0);
        el.style.visibility = (t >= s && t < s + d) ? 'visible' : 'hidden';
      }});
    }},
    setVariables(v) {{
      if (v.title) document.getElementById('vid-title').textContent = v.title;
    }},
    getVariables() {{ return {{}}; }},
  }};
</script>
</body>
</html>"""
        Path(output_path).write_text(html_doc, encoding="utf-8")
        return output_path


# ── Convenience render functions ──────────────────────────────────────────────

async def render_html_to_video(
    html_path: str,
    output_path: str,
    duration: float = 10.0,
    fps: Fps = FPS_30,
    resolution: str = "landscape",
    variables: Optional[dict[str, Any]] = None,
    narration: Optional[str] = None,
    use_gpu: bool = False,
    quality: RenderQuality = "standard",
) -> ComposerResult:
    """One-call HTML → video for VECTOR agents."""
    composer = VectorComposer()
    job = ComposerJob(
        composition_path=html_path,
        output_path=output_path,
        fps=fps,
        resolution=resolution,
        duration_seconds=duration,
        variables=variables or {},
        narration=narration,
        use_gpu=use_gpu,
        quality=quality,
    )
    return await composer.render(job)


if __name__ == "__main__":
    import sys

    # Smoke test: template generation
    with tempfile.TemporaryDirectory() as tmp:
        html_path = os.path.join(tmp, "test.html")
        CompositionTemplate.title_card(
            title="VECTOR AI System",
            subtitle="Autonomous Intelligence",
            output_path=html_path,
        )
        content = Path(html_path).read_text()
        assert "VECTOR AI System" in content
        assert "window.__vector" in content
        print(f"Title card HTML: {len(content)} chars")

        # Data viz
        viz_path = os.path.join(tmp, "viz.html")
        CompositionTemplate.data_viz(
            title="District Performance",
            data={"Research": 92, "Coding": 88, "Security": 95, "Memory": 79},
            output_path=viz_path,
        )
        assert "District Performance" in Path(viz_path).read_text()
        print("Data viz HTML generated")

    composer = VectorComposer()
    assert composer._on_progress is None

    print("OK vector_composer.py")
