"""
VECTOR Video Encoder
+ utils/runFfmpeg.ts + utils/gpuEncoder.ts

Encodes PNG frame sequences to MP4/WebM/MOV using FFmpeg.
Supports:
  - H.264/H.265 (MP4), VP9 with alpha (WebM), ProRes 4444 (MOV)
  - GPU acceleration via NVENC (RTX 5070 Ti)
  - CRF quality control and bitrate targeting
  - Audio track muxing
  - HDR pipeline (if source frames are HDR)
  - Streaming encode (frames piped to FFmpeg stdin)
  - PNG-sequence passthrough (no re-encode)
"""
from __future__ import annotations

__all__ = [
    "EncodeOptions",
    "EncodeResult",
    "find_ffmpeg",
    "find_ffprobe",
    "probe_dimensions",
    "probe_duration",
    "StreamingEncoder",
    "VideoEncoder",
]


import asyncio
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger

from core.video.composition_types import (
    Fps, OutputFormat, RenderQuality, QUALITY_CRF
)


@dataclass
class EncodeOptions:
    fps: Fps = field(default_factory=lambda: Fps(30, 1))
    quality: RenderQuality = "standard"
    format: OutputFormat = "mp4"
    use_gpu: bool = False
    crf: Optional[int] = None
    video_bitrate: Optional[str] = None
    audio_path: Optional[str] = None
    hdr: bool = False
    width: int = 1920
    height: int = 1080


@dataclass
class EncodeResult:
    output_path: str
    duration_ms: float
    file_size_bytes: int
    frames_encoded: int
    codec: str


def find_ffmpeg() -> Optional[str]:
    return shutil.which("ffmpeg")


def find_ffprobe() -> Optional[str]:
    return shutil.which("ffprobe")


def probe_duration(path: str) -> float:
    """Return media duration in seconds via ffprobe."""
    ffprobe = find_ffprobe()
    if not ffprobe:
        return 0.0
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=15,
        )
        return float(result.stdout.strip())
    except Exception as e:
        logger.warning("[VECTOR][video_encoder] probe_duration failed for {}: {}", path, e)
        return 0.0


def probe_dimensions(path: str) -> tuple[int, int]:
    """Return (width, height) of a media file."""
    ffprobe = find_ffprobe()
    if not ffprobe:
        return (0, 0)
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=15,
        )
        parts = result.stdout.strip().split(",")
        return (int(parts[0]), int(parts[1]))
    except Exception as e:
        logger.warning("[VECTOR][video_encoder] probe_dimensions failed for {}: {}", path, e)
        return (0, 0)


class VideoEncoder:
    """
    Encodes PNG frame sequences to video.
        """

    def __init__(self) -> None:
        self._ffmpeg = find_ffmpeg()

    def encode(
        self,
        frame_pattern: str,
        output_path: str,
        options: EncodeOptions,
    ) -> EncodeResult:
        """
        Encode frames matching pattern (e.g. /tmp/frames/frame_%08d.png) to video.
        Blocks until encode completes.
        """
        if not self._ffmpeg:
            raise RuntimeError(
                "FFmpeg not found. Install: winget install Gyan.FFmpeg "
                "or download from ffmpeg.org"
            )

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Handle PNG-sequence output — just move frames, no encode
        if options.format == "png-sequence":
            return self._passthrough_sequence(frame_pattern, output_path, options)

        cmd = self._build_cmd(frame_pattern, output_path, options)

        logger.info("[VECTOR][video_encoder] Encoding {} -> {}", frame_pattern, output_path)
        logger.debug("[VECTOR][video_encoder] cmd: {}", " ".join(cmd))

        t0 = time.perf_counter()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        if result.returncode != 0:
            logger.error("[VECTOR][video_encoder] FFmpeg failed:\n{}", result.stderr[-2000:])
            raise RuntimeError(f"FFmpeg encode failed: {result.stderr[-500:]}")

        file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        codec = self._codec_name(options)

        # Count frames from pattern dir
        frame_dir = str(Path(frame_pattern).parent)
        frames = len([f for f in os.listdir(frame_dir) if f.endswith(".png")])

        logger.info(
            "[VECTOR][video_encoder] Done: {:.1f}s, {:.1f}MB, {} frames, codec={}",
            elapsed_ms / 1000, file_size / 1_048_576, frames, codec,
        )

        return EncodeResult(
            output_path=output_path,
            duration_ms=elapsed_ms,
            file_size_bytes=file_size,
            frames_encoded=frames,
            codec=codec,
        )

    def _build_cmd(
        self,
        frame_pattern: str,
        output_path: str,
        opts: EncodeOptions,
    ) -> list[str]:
        fps_arg = opts.fps.to_ffmpeg_arg()
        crf = opts.crf if opts.crf is not None else QUALITY_CRF[opts.quality]

        cmd = [self._ffmpeg, "-y"]

        # Input: PNG frame sequence
        cmd += ["-framerate", fps_arg, "-i", frame_pattern]

        # Audio input
        if opts.audio_path and os.path.exists(opts.audio_path):
            cmd += ["-i", opts.audio_path]

        if opts.format == "mp4":
            cmd += self._h264_args(opts, crf)
        elif opts.format == "webm":
            cmd += self._vp9_args(opts, crf)
        elif opts.format == "mov":
            cmd += self._prores_args(opts)

        # Audio encode
        if opts.audio_path and os.path.exists(opts.audio_path):
            cmd += ["-c:a", "aac", "-b:a", "192k"]

        cmd += ["-movflags", "+faststart", output_path]
        return cmd

    def _h264_args(self, opts: EncodeOptions, crf: int) -> list[str]:
        if opts.use_gpu:
            # NVENC H.264 — RTX 5070 Ti hardware encode
            args = ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr"]
            if opts.video_bitrate:
                args += ["-b:v", opts.video_bitrate]
            else:
                args += ["-cq", str(crf)]
        else:
            args = ["-c:v", "libx264", "-preset", "faster"]
            if opts.video_bitrate:
                args += ["-b:v", opts.video_bitrate]
            else:
                args += ["-crf", str(crf)]

        args += ["-pix_fmt", "yuv420p", "-profile:v", "high"]
        return args

    def _vp9_args(self, opts: EncodeOptions, crf: int) -> list[str]:
        # VP9 with alpha channel support (transparent WebM)
        # The "-b:v" value is 0 for CRF mode, or the real bitrate when
        # opts.video_bitrate is set -- built directly (not found-and-replaced
        # by searching for the literal "0") because str(crf) == "0" is a real
        # VP9 near-lossless setting, which previously made args.index("0")
        # match the earlier -crf value instead of the -b:v placeholder.
        bitrate_value = opts.video_bitrate if opts.video_bitrate else "0"
        return [
            "-c:v", "libvpx-vp9",
            "-pix_fmt", "yuva420p",
            "-crf", str(crf), "-b:v", bitrate_value,
            "-metadata:s:v:0", "alpha_mode=1",
        ]

    def _prores_args(self, opts: EncodeOptions) -> list[str]:
        # ProRes 4444 with alpha — for editing round-trips
        return [
            "-c:v", "prores_ks",
            "-profile:v", "4444",
            "-pix_fmt", "yuva444p10le",
        ]

    def _passthrough_sequence(
        self,
        frame_pattern: str,
        output_dir: str,
        opts: EncodeOptions,
    ) -> EncodeResult:
        """Copy PNG frames to output directory (no re-encode)."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        frame_dir = str(Path(frame_pattern).parent)
        frames = sorted(f for f in os.listdir(frame_dir) if f.endswith(".png"))

        for f in frames:
            src = os.path.join(frame_dir, f)
            dst = os.path.join(output_dir, f)
            shutil.copy2(src, dst)

        total_size = sum(
            os.path.getsize(os.path.join(output_dir, f)) for f in frames
        )
        return EncodeResult(
            output_path=output_dir,
            duration_ms=0,
            file_size_bytes=total_size,
            frames_encoded=len(frames),
            codec="png",
        )

    def _codec_name(self, opts: EncodeOptions) -> str:
        if opts.format == "mp4":
            return "h264_nvenc" if opts.use_gpu else "libx264"
        if opts.format == "webm":
            return "libvpx-vp9"
        if opts.format == "mov":
            return "prores_ks"
        return "png"


# ── Streaming encoder (pipes frames to FFmpeg stdin) ─────────────────────────

class StreamingEncoder:
    """
    Pipes raw PNG bytes to FFmpeg stdin for zero-disk-write rendering.
        """

    def __init__(self, opts: EncodeOptions, output_path: str) -> None:
        self._opts = opts
        self._output_path = output_path
        self._proc: Optional[subprocess.Popen] = None

    def start(self) -> None:
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            raise RuntimeError("FFmpeg not found")
        fps_arg = self._opts.fps.to_ffmpeg_arg()
        crf = self._opts.crf if self._opts.crf is not None else QUALITY_CRF[self._opts.quality]
        cmd = [
            ffmpeg, "-y",
            "-f", "image2pipe",
            "-framerate", fps_arg,
            "-i", "pipe:0",
            "-c:v", "libx264",
            "-crf", str(crf),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            self._output_path,
        ]
        self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def write_frame(self, png_bytes: bytes) -> None:
        if self._proc and self._proc.stdin:
            self._proc.stdin.write(png_bytes)

    def finish(self) -> None:
        if self._proc:
            if self._proc.stdin:
                self._proc.stdin.close()
            self._proc.wait()


if __name__ == "__main__":
    enc = VideoEncoder()
    ffmpeg = find_ffmpeg()
    print(f"FFmpeg: {ffmpeg or 'NOT FOUND'}")

    opts = EncodeOptions(fps=Fps(30, 1), quality="standard", format="mp4")
    codec = enc._codec_name(opts)
    assert codec == "libx264"

    opts_gpu = EncodeOptions(fps=Fps(30, 1), quality="high", format="mp4", use_gpu=True)
    assert enc._codec_name(opts_gpu) == "h264_nvenc"

    print("OK video_encoder.py")
