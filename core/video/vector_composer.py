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

import asyncio
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
    narration_voice: str = "bf_emma"
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

        bars_html = ""
        if isinstance(data, dict):
            max_val = max(data.values()) if data else 1
            for key, val in data.items():
                pct = (val / max_val) * 100
                bars_html += f"""
                <div class="bar-row">
                  <span class="label">{key}</span>
                  <div class="bar-bg">
                    <div class="bar-fill" style="width:{pct:.1f}%"></div>
                  </div>
                  <span class="value">{val}</span>
                </div>"""

        html = f"""<!DOCTYPE html>
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
<h1>{title}</h1>
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
        Path(output_path).write_text(html, encoding="utf-8")
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

        html = f"""<!DOCTYPE html>
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
  <div class="title" id="title">{title}</div>
  <div class="sub"   id="subtitle">{subtitle}</div>
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
        Path(output_path).write_text(html, encoding="utf-8")
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
