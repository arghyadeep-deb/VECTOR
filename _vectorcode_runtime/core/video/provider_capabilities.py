"""Media provider capability registry for VECTOR video/content planning."""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["MediaModelCapability", "MediaProviderCapability", "get_media_provider", "list_media_providers"]


@dataclass(frozen=True)
class MediaModelCapability:
    name: str
    modalities: tuple[str, ...]
    min_duration_sec: float = 1.0
    max_duration_sec: float = 12.0
    aspect_ratios: tuple[str, ...] = ("9:16", "16:9", "1:1")
    fps: tuple[int, ...] = (24, 30)
    input_requirements: tuple[str, ...] = field(default_factory=tuple)
    safety_notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MediaProviderCapability:
    provider: str
    configured: bool
    local: bool
    models: tuple[MediaModelCapability, ...]
    notes: str = ""


def list_media_providers() -> list[MediaProviderCapability]:
    try:
        from core.config import CONFIG
        comfy_path = CONFIG.get("sidecars", {}).get("comfyui_path") or CONFIG.get("COMFYUI_PATH", "")
    except Exception:
        comfy_path = ""
    return [
        MediaProviderCapability(
            provider="vector_composer",
            configured=True,
            local=True,
            models=(MediaModelCapability(
                name="html_timeline",
                modalities=("text", "image", "audio", "video"),
                min_duration_sec=1,
                max_duration_sec=3600,
                aspect_ratios=("9:16", "16:9", "1:1", "4:5"),
                fps=(24, 25, 30, 60),
                input_requirements=("storyboard",),
                safety_notes=("renders through VECTOR-owned Playwright/ffmpeg pipeline",),
            ),),
        ),
        MediaProviderCapability(
            provider="comfyui",
            configured=bool(comfy_path),
            local=True,
            models=(MediaModelCapability(
                name="local_image_workflow",
                modalities=("image",),
                min_duration_sec=0,
                max_duration_sec=0,
                input_requirements=("workflow_json", "prompt"),
                safety_notes=("optional sidecar; unavailable must not block storyboard generation",),
            ),),
            notes="optional local image provider",
        ),
        MediaProviderCapability(
            provider="longcat_external",
            configured=False,
            local=False,
            models=(MediaModelCapability(
                name="long_video_or_avatar_sidecar",
                modalities=("video", "audio_to_avatar"),
                min_duration_sec=5,
                max_duration_sec=600,
                aspect_ratios=("9:16", "16:9"),
                fps=(24, 30),
                input_requirements=("external_endpoint", "verified_model_license", "gpu_or_cloud_budget"),
                safety_notes=("disabled by default; model weights/license must be verified before use",),
            ),),
            notes="placeholder for optional external long-video/avatar sidecar",
        ),
    ]


def get_media_provider(name: str) -> MediaProviderCapability | None:
    for provider in list_media_providers():
        if provider.provider == name:
            return provider
    return None
