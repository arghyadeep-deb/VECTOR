"""
VECTOR Video Composition Types
timeline model: FPS rationals, canvas resolutions, timeline elements,
composition variables, keyframes, and render options.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Union


# ── FPS Rational ──────────────────────────────────────────────────────────────

@dataclass
class Fps:
    """Exact rational framerate (avoids decimal round-trip for NTSC/drop-frame)."""
    num: int
    den: int = 1

    def to_float(self) -> float:
        return self.num / self.den

    def to_ffmpeg_arg(self) -> str:
        return str(self.num) if self.den == 1 else f"{self.num}/{self.den}"

    @classmethod
    def from_value(cls, value: Union[int, float, str]) -> "Fps":
        if isinstance(value, int):
            return cls(num=value, den=1)
        if isinstance(value, float):
            # Convert common decimals to rationals
            if abs(value - 29.97) < 0.01:
                return cls(30000, 1001)
            if abs(value - 23.976) < 0.01:
                return cls(24000, 1001)
            if abs(value - 59.94) < 0.01:
                return cls(60000, 1001)
            return cls(num=int(round(value)), den=1)
        if isinstance(value, str):
            if "/" in value:
                n, d = value.split("/")
                return cls(int(n), int(d))
            return cls(int(value), 1)
        raise ValueError(f"Cannot parse FPS from {value!r}")


# Common presets
FPS_24   = Fps(24, 1)
FPS_25   = Fps(25, 1)
FPS_30   = Fps(30, 1)
FPS_60   = Fps(60, 1)
FPS_NTSC = Fps(30000, 1001)  # 29.97
FPS_FILM = Fps(24000, 1001)  # 23.976


# ── Canvas Resolutions ────────────────────────────────────────────────────────

CANVAS_DIMENSIONS: dict[str, tuple[int, int]] = {
    "landscape":    (1920, 1080),
    "portrait":     (1080, 1920),
    "landscape-4k": (3840, 2160),
    "portrait-4k":  (2160, 3840),
    "square":       (1080, 1080),
    "square-4k":    (2160, 2160),
}

RESOLUTION_ALIASES: dict[str, str] = {
    "1080p":         "landscape",
    "hd":            "landscape",
    "1080p-portrait":"portrait",
    "4k":            "landscape-4k",
    "uhd":           "landscape-4k",
    "4k-portrait":   "portrait-4k",
    "square-1080p":  "square",
    "4k-square":     "square-4k",
}

CanvasResolution = Literal[
    "landscape", "portrait", "landscape-4k", "portrait-4k",
    "square", "square-4k"
]


def normalize_resolution(input_str: str) -> Optional[str]:
    lower = input_str.lower()
    if lower in CANVAS_DIMENSIONS:
        return lower
    return RESOLUTION_ALIASES.get(lower)


def canvas_size(resolution: str) -> tuple[int, int]:
    canonical = normalize_resolution(resolution) or resolution
    if canonical not in CANVAS_DIMENSIONS:
        raise ValueError(f"Unknown resolution: {resolution!r}")
    return CANVAS_DIMENSIONS[canonical]


# ── Timeline Element Types ────────────────────────────────────────────────────

TimelineElementType = Literal["video", "image", "text", "audio", "composition"]
MediaElementType    = Literal["video", "image", "audio"]
OutputFormat        = Literal["mp4", "webm", "mov", "png-sequence"]
RenderQuality       = Literal["draft", "standard", "high"]
HdrMode             = Literal["auto", "force-hdr", "force-sdr"]
BgRemovalQuality    = Literal["fast", "balanced", "best"]


@dataclass
class TimelineElementBase:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = "video"
    name: str = ""
    start_time: float = 0.0
    duration: float = 5.0
    z_index: int = 0
    x: Optional[float] = None
    y: Optional[float] = None
    scale: Optional[float] = None
    opacity: Optional[float] = None


@dataclass
class TimelineMediaElement(TimelineElementBase):
    type: str = "video"
    src: str = ""
    media_start_time: float = 0.0
    source_duration: Optional[float] = None
    is_aroll: bool = False
    source_width: Optional[int] = None
    source_height: Optional[int] = None
    volume: float = 1.0
    has_audio: bool = False


@dataclass
class TimelineTextElement(TimelineElementBase):
    type: str = "text"
    content: str = ""
    color: str = "#ffffff"
    font_size: int = 48
    text_shadow: bool = False
    font_family: str = "Inter"
    font_weight: int = 400
    text_outline: bool = False
    text_outline_color: str = "#000000"
    text_outline_width: int = 2
    text_highlight: bool = False
    text_highlight_color: str = "#ffff00"
    text_highlight_padding: int = 4
    text_highlight_radius: int = 4


@dataclass
class TimelineCompositionElement(TimelineElementBase):
    type: str = "composition"
    src: str = ""
    composition_id: str = ""
    source_duration: Optional[float] = None
    variable_values: dict[str, Any] = field(default_factory=dict)
    source_width: Optional[int] = None
    source_height: Optional[int] = None


TimelineElement = Union[TimelineMediaElement, TimelineTextElement, TimelineCompositionElement]


# ── Composition Variables ─────────────────────────────────────────────────────

@dataclass
class StringVariable:
    id: str
    type: str = "string"
    label: str = ""
    description: str = ""
    default: str = ""
    placeholder: str = ""
    max_length: Optional[int] = None


@dataclass
class NumberVariable:
    id: str
    type: str = "number"
    label: str = ""
    description: str = ""
    default: float = 0.0
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    unit: str = ""


@dataclass
class ColorVariable:
    id: str
    type: str = "color"
    label: str = ""
    description: str = ""
    default: str = "#ffffff"


@dataclass
class BooleanVariable:
    id: str
    type: str = "boolean"
    label: str = ""
    description: str = ""
    default: bool = False


@dataclass
class EnumVariable:
    id: str
    type: str = "enum"
    label: str = ""
    description: str = ""
    default: str = ""
    options: list[dict[str, str]] = field(default_factory=list)


CompositionVariable = Union[StringVariable, NumberVariable, ColorVariable, BooleanVariable, EnumVariable]


# ── Keyframes ─────────────────────────────────────────────────────────────────

@dataclass
class KeyframeProperties:
    x: Optional[float] = None
    y: Optional[float] = None
    opacity: Optional[float] = None
    scale: Optional[float] = None
    scale_x: Optional[float] = None
    scale_y: Optional[float] = None
    rotation: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None


@dataclass
class Keyframe:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    time: float = 0.0
    properties: KeyframeProperties = field(default_factory=KeyframeProperties)
    ease: str = "ease"


@dataclass
class StageZoom:
    scale: float = 1.0
    focus_x: float = 960.0
    focus_y: float = 540.0


# ── Render Job ────────────────────────────────────────────────────────────────

@dataclass
class RenderJob:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    composition_path: str = ""
    output_path: str = ""
    fps: Fps = field(default_factory=lambda: Fps(30, 1))
    resolution: str = "landscape"
    quality: RenderQuality = "standard"
    format: OutputFormat = "mp4"
    workers: int = 1
    use_gpu: bool = False
    hdr_mode: HdrMode = "auto"
    crf: Optional[int] = None
    video_bitrate: Optional[str] = None
    variables: dict[str, Any] = field(default_factory=dict)
    # Perf tracking
    total_frames: int = 0
    capture_avg_ms: float = 0.0
    encode_ms: float = 0.0


# ── Asset ─────────────────────────────────────────────────────────────────────

@dataclass
class VideoAsset:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    url: str = ""
    type: str = "video"
    is_reference: bool = False
    duration: Optional[float] = None


@dataclass
class WaveformData:
    peaks: list[float] = field(default_factory=list)
    duration: float = 0.0
    sample_rate: int = 44100


# ── Quality CRF map ───────────────────────────────────────────────────────────

QUALITY_CRF: dict[RenderQuality, int] = {
    "draft":    35,
    "standard": 23,
    "high":     18,
}

BG_REMOVAL_CRF: dict[BgRemovalQuality, int] = {
    "fast":     30,
    "balanced": 18,
    "best":     12,
}

DEFAULT_DURATIONS: dict[str, float] = {
    "video":       5.0,
    "image":       5.0,
    "text":        2.0,
    "audio":       5.0,
    "composition": 5.0,
}


if __name__ == "__main__":
    fps = Fps.from_value("30000/1001")
    assert fps.to_ffmpeg_arg() == "30000/1001"
    assert abs(fps.to_float() - 29.97) < 0.01

    fps2 = Fps.from_value(30)
    assert fps2.to_ffmpeg_arg() == "30"

    w, h = canvas_size("4k")
    assert w == 3840 and h == 2160

    w2, h2 = canvas_size("portrait")
    assert w2 == 1080 and h2 == 1920

    job = RenderJob(composition_path="test.html", output_path="out.mp4")
    assert job.fps.to_ffmpeg_arg() == "30"

    print("OK composition_types.py")
