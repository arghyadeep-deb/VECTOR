"""
VECTOR Video Engine
Ported from hyperframes — HTML-to-video rendering pipeline.

Packages:
  composition_types   — Timeline model, FPS rationals, canvas resolutions
  html_renderer       — Playwright frame capture (HTML → PNG sequences)
  video_encoder       — FFmpeg encode pipeline (frames → MP4/WebM/MOV)
  audio_mixer         — Multi-track audio mix, TTS narration pipeline
  background_remover  — AI background removal (ONNX/rembg → RGBA alpha)
  hyperframes_composer— High-level composer orchestrator
  website_to_video    — URL → video full pipeline
"""
__version__ = "1.0.0"

from core.video.composition_types import (
    Fps, FPS_24, FPS_25, FPS_30, FPS_60, FPS_NTSC, FPS_FILM,
    CANVAS_DIMENSIONS, canvas_size, normalize_resolution,
    RenderJob, RenderQuality, OutputFormat, HdrMode,
    TimelineMediaElement, TimelineTextElement, TimelineCompositionElement,
    QUALITY_CRF, BG_REMOVAL_CRF,
)
from core.video.hyperframes_composer import (
    VectorComposer, ComposerJob, ComposerResult,
    CompositionTemplate, render_html_to_video,
)
from core.video.background_remover import (
    BackgroundRemover, remove_background, DEFAULT_MODEL,
)
from core.video.website_to_video import (
    WebsiteToVideo, url_to_video, CaptureOptions,
)

__all__ = [
    # Types
    "Fps", "FPS_24", "FPS_25", "FPS_30", "FPS_60", "FPS_NTSC", "FPS_FILM",
    "CANVAS_DIMENSIONS", "canvas_size", "normalize_resolution",
    "RenderJob", "RenderQuality", "OutputFormat", "HdrMode",
    "TimelineMediaElement", "TimelineTextElement", "TimelineCompositionElement",
    "QUALITY_CRF", "BG_REMOVAL_CRF",
    # Composer
    "VectorComposer", "ComposerJob", "ComposerResult",
    "CompositionTemplate", "render_html_to_video",
    # Background removal
    "BackgroundRemover", "remove_background", "DEFAULT_MODEL",
    # Website to video
    "WebsiteToVideo", "url_to_video", "CaptureOptions",
]
