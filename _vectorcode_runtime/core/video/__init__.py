"""
VECTOR Video Engine

Packages:
  composition_types   — Timeline model, FPS rationals, canvas resolutions
  html_renderer       — Playwright frame capture (HTML → PNG sequences)
  video_encoder       — FFmpeg encode pipeline (frames → MP4/WebM/MOV)
  audio_mixer         — Multi-track audio mix, TTS narration pipeline
  background_remover  — AI background removal (ONNX/rembg → RGBA alpha)
  vector_composer     — High-level composer orchestrator
  website_to_video    — URL → video full pipeline
  composition_linter  — HTML composition validation (7 rule sets)
  studio_server       — VECTOR Studio backend API + file watcher
  dashboard/VectorPlayer — Embeddable web component for composition preview
  dashboard/studio       — Visual composition editor UI (React)
"""
__version__ = "1.1.0"

from core.video.composition_types import (
    Fps, FPS_24, FPS_25, FPS_30, FPS_60, FPS_NTSC, FPS_FILM,
    CANVAS_DIMENSIONS, canvas_size, normalize_resolution,
    RenderJob, RenderQuality, OutputFormat, HdrMode,
    TimelineMediaElement, TimelineTextElement, TimelineCompositionElement,
    QUALITY_CRF, BG_REMOVAL_CRF,
)
from core.video.vector_composer import (
    VectorComposer, ComposerJob, ComposerResult,
    CompositionTemplate, render_html_to_video,
)
from core.video.background_remover import (
    BackgroundRemover, remove_background, DEFAULT_MODEL,
)
from core.video.website_to_video import (
    WebsiteToVideo, url_to_video, CaptureOptions,
)
from core.video.composition_linter import (
    lint_composition, lint_file, lint_project,
    LintResult, LintFinding,
)
from core.video.provider_capabilities import (
    MediaModelCapability, MediaProviderCapability,
    get_media_provider, list_media_providers,
)
from core.video.workflow_resolver import WorkflowResolutionError, resolve_workflow

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
    # Linter
    "lint_composition", "lint_file", "lint_project",
    "LintResult", "LintFinding",
    # Media provider registry / workflow resolver
    "MediaModelCapability", "MediaProviderCapability",
    "get_media_provider", "list_media_providers",
    "WorkflowResolutionError", "resolve_workflow",
]
