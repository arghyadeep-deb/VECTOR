"""
VECTOR Background Remover

AI-based background removal using ONNX runtime + OpenCV.
Outputs transparent RGBA video/images for overlay compositing.

Supported output formats:
  .webm → VP9 with alpha (HTML5-native, ~1MB/4s @ 1080p)
  .mov  → ProRes 4444 with alpha (editing round-trip)
  .png  → single RGBA still

Models (auto-downloaded):
  u2net       — general purpose (best quality)
  u2net_human — optimized for people (faster + better for portraits)
  isnet-dis   — DIS (Highly Accurate Dichotomous Image Segmentation, newer)

RTX 5070 Ti: uses CUDA execution provider for ~10x speedup.
"""
from __future__ import annotations

__all__ = [
    "BackgroundRemover",
    "BGSession",
    "DEFAULT_MODEL",
    "ProgressEvent",
    "remove_background",
    "RemoveResult",
    "VECTOR_MODELS_DIR",
]


import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from loguru import logger

from core.video.video_encoder import find_ffmpeg, find_ffprobe, probe_duration, probe_dimensions
from core.video.composition_types import BG_REMOVAL_CRF, BgRemovalQuality


# â”€â”€ ONNX model registry â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

MODEL_URLS: dict[str, str] = {
    "u2net":       "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx",
    "u2net_human": "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_human_seg.onnx",
    "isnet-dis":   "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-dis.onnx",
}

MODEL_INPUT_SIZE: dict[str, int] = {
    "u2net":       320,
    "u2net_human": 320,
    "isnet-dis":   1024,
}

DEFAULT_MODEL = "u2net_human"
VECTOR_MODELS_DIR = Path.home() / ".vector" / "models" / "bg_removal"


@dataclass
class ProgressEvent:
    kind: str  # "info" | "metadata" | "frame"
    message: str = ""
    frame_index: int = 0
    total_frames: int = 0
    avg_ms_per_frame: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0


@dataclass
class RemoveResult:
    output_path: str
    bg_plate_path: Optional[str] = None     # inverse-alpha background plate
    frames_processed: int = 0
    duration_seconds: float = 0.0
    avg_ms_per_frame: float = 0.0
    provider: str = "cpu"
    format: str = "webm"


class BGSession:
    """
    ONNX inference session for background removal.
        """

    def __init__(self, model_id: str = DEFAULT_MODEL) -> None:
        self._model_id = model_id
        self._session = None
        self._input_size = MODEL_INPUT_SIZE.get(model_id, 320)
        self._provider = "cpu"

    def load(self) -> None:
        """Load or download ONNX model and create inference session."""
        model_path = self._ensure_model()
        try:
            import onnxruntime as ort
            # Prefer CUDA (RTX 5070 Ti) → CPU fallback
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            self._session = ort.InferenceSession(str(model_path), providers=providers)
            active = self._session.get_providers()[0]
            self._provider = "cuda" if "CUDA" in active else "cpu"
            logger.info("[VECTOR][bg_remover] model={} provider={}", self._model_id, self._provider)
        except ImportError:
            raise RuntimeError(
                "onnxruntime not installed. Run: pip install onnxruntime-gpu"
            )

    def predict(self, frame_rgb: np.ndarray) -> np.ndarray:
        """
        Run inference on an RGB frame. Returns alpha mask (H, W) float32 in [0, 1].
        """
        if self._session is None:
            self.load()

        h, w = frame_rgb.shape[:2]
        size = self._input_size

        # Resize and normalize (ImageNet mean/std)
        import cv2
        resized = cv2.resize(frame_rgb, (size, size), interpolation=cv2.INTER_AREA)
        tensor = resized.astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std  = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        tensor = (tensor - mean) / std
        tensor = tensor.transpose(2, 0, 1)[np.newaxis]  # (1, 3, H, W)

        input_name = self._session.get_inputs()[0].name
        outputs = self._session.run(None, {input_name: tensor})
        mask = outputs[0][0, 0]  # (H, W)
        mask = (mask - mask.min()) / (mask.max() - mask.min() + 1e-8)

        # Resize mask back to original resolution
        mask_resized = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)
        return mask_resized.astype(np.float32)

    def apply_mask(
        self,
        frame_rgb: np.ndarray,
        alpha: np.ndarray,
    ) -> np.ndarray:
        """Combine RGB frame with alpha mask → RGBA uint8."""
        alpha_u8 = (alpha * 255).astype(np.uint8)
        rgba = np.dstack([frame_rgb, alpha_u8])
        return rgba

    def _ensure_model(self) -> Path:
        VECTOR_MODELS_DIR.mkdir(parents=True, exist_ok=True)
        model_path = VECTOR_MODELS_DIR / f"{self._model_id}.onnx"
        if model_path.exists():
            return model_path

        url = MODEL_URLS.get(self._model_id)
        if not url:
            raise RuntimeError(f"Unknown background removal model: {self._model_id!r}")

        # Try rembg (easiest) first
        try:
            import rembg  # type: ignore  # noqa: F401
            logger.info("[VECTOR][bg_remover] using rembg models (auto-managed)")
            return model_path  # rembg handles its own models
        except ImportError:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

        logger.info("[VECTOR][bg_remover] downloading {} from {}", self._model_id, url)
        import httpx
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as r:
            with open(model_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=65536):
                    f.write(chunk)
        return model_path


class BackgroundRemover:
    """
    Full background removal pipeline for images and videos.
        """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL,
        quality: BgRemovalQuality = "balanced",
    ) -> None:
        self._model_id = model_id
        self._quality = quality
        self._session: Optional[BGSession] = None

    def _get_session(self) -> BGSession:
        if self._session is None:
            self._session = BGSession(self._model_id)
            self._session.load()
        return self._session

    def remove_image(
        self,
        input_path: str,
        output_path: str,
    ) -> RemoveResult:
        """Remove background from a single image → PNG with alpha."""
        import cv2

        # Try rembg shortcut first (simpler)
        try:
            from rembg import remove as rembg_remove  # type: ignore
            from PIL import Image
            inp = Image.open(input_path)
            out = rembg_remove(inp)
            out.save(output_path)
            logger.info("[VECTOR][bg_remover] rembg image: {}", output_path)
            return RemoveResult(output_path=output_path, frames_processed=1,
                                provider="rembg", format="png")
        except ImportError:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

        frame_bgr = cv2.imread(input_path)
        if frame_bgr is None:
            raise RuntimeError(f"Cannot read image: {input_path}")
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

        session = self._get_session()
        alpha = session.predict(frame_rgb)
        rgba = session.apply_mask(frame_rgb, alpha)

        rgba_bgra = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA)
        cv2.imwrite(output_path, rgba_bgra)

        return RemoveResult(
            output_path=output_path,
            frames_processed=1,
            provider=session._provider,
            format="png",
        )

    def remove_video(
        self,
        input_path: str,
        output_path: str,
        bg_plate_path: Optional[str] = None,
        on_progress: Optional[Callable[[ProgressEvent], None]] = None,
    ) -> RemoveResult:
        """
        Remove background from a video → WebM/MOV with alpha channel.
        Optionally also produce an inverse alpha background plate.
        """
        try:
            import cv2
        except ImportError:
            raise RuntimeError("opencv-python not installed. Run: pip install opencv-python")

        # Try rembg video pipeline
        try:
            return self._remove_video_rembg(input_path, output_path, bg_plate_path, on_progress)
        except ImportError:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

        return self._remove_video_manual(input_path, output_path, bg_plate_path, on_progress)

    def _remove_video_rembg(
        self,
        input_path: str,
        output_path: str,
        bg_plate_path: Optional[str],
        on_progress: Optional[Callable],
    ) -> RemoveResult:
        """Use rembg for video (frame-by-frame via OpenCV)."""
        from rembg import remove as rembg_remove, new_session  # type: ignore
        import cv2

        if bg_plate_path:
            logger.warning(
                "[VECTOR][bg_remover] bg_plate_path={} requested but the inverse-alpha "
                "background plate is not implemented in this method -- ignored",
                bg_plate_path,
            )

        rembg_session = new_session(self._model_id)
        cap = cv2.VideoCapture(input_path)

        fps     = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total   = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w       = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        dur     = total / fps

        if on_progress:
            on_progress(ProgressEvent(kind="metadata", width=w, height=h, fps=fps,
                                      total_frames=total))

        crf = BG_REMOVAL_CRF[self._quality]
        ext = Path(output_path).suffix.lower()

        # Write RGBA frames via FFmpeg pipe
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            raise RuntimeError("FFmpeg not found")

        if ext == ".webm":
            vcodec_args = ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                           "-crf", str(crf), "-b:v", "0",
                           "-metadata:s:v:0", "alpha_mode=1"]
        elif ext == ".mov":
            vcodec_args = ["-c:v", "prores_ks", "-profile:v", "4444",
                           "-pix_fmt", "yuva444p10le"]
        else:
            vcodec_args = ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                           "-crf", str(crf), "-b:v", "0"]
            output_path = str(Path(output_path).with_suffix(".webm"))

        cmd = [ffmpeg, "-y",
               "-f", "rawvideo", "-vcodec", "rawvideo",
               "-s", f"{w}x{h}", "-pix_fmt", "rgba",
               "-r", str(fps), "-i", "pipe:0"] + vcodec_args + [output_path]

        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        times: list[float] = []
        frame_idx = 0

        while True:
            ret, frame_bgr = cap.read()
            if not ret:
                break
            t0 = time.perf_counter()
            from PIL import Image
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(frame_rgb)
            out_pil = rembg_remove(pil_img, session=rembg_session)
            rgba = np.array(out_pil)

            if proc.stdin:
                proc.stdin.write(rgba.tobytes())

            elapsed = (time.perf_counter() - t0) * 1000
            times.append(elapsed)
            avg_ms = sum(times) / len(times)

            if on_progress:
                on_progress(ProgressEvent(
                    kind="frame", frame_index=frame_idx,
                    total_frames=total, avg_ms_per_frame=avg_ms
                ))
            frame_idx += 1

        cap.release()
        if proc.stdin:
            proc.stdin.close()
        proc.wait()

        return RemoveResult(
            output_path=output_path,
            frames_processed=frame_idx,
            duration_seconds=dur,
            avg_ms_per_frame=sum(times) / len(times) if times else 0.0,
            provider="rembg",
            format=Path(output_path).suffix.lstrip("."),
        )

    def _remove_video_manual(
        self,
        input_path: str,
        output_path: str,
        bg_plate_path: Optional[str],
        on_progress: Optional[Callable],
    ) -> RemoveResult:
        """Manual ONNX pipeline without rembg."""
        import cv2
        if bg_plate_path:
            logger.warning(
                "[VECTOR][bg_remover] bg_plate_path={} requested but the inverse-alpha "
                "background plate is not implemented in this method -- ignored",
                bg_plate_path,
            )
        session = self._get_session()
        cap = cv2.VideoCapture(input_path)
        fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        dur   = total / fps

        if on_progress:
            on_progress(ProgressEvent(kind="metadata", width=w, height=h, fps=fps,
                                      total_frames=total))

        crf = BG_REMOVAL_CRF[self._quality]
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            raise RuntimeError("FFmpeg not found")

        cmd = [ffmpeg, "-y",
               "-f", "rawvideo", "-vcodec", "rawvideo",
               "-s", f"{w}x{h}", "-pix_fmt", "rgba",
               "-r", str(fps), "-i", "pipe:0",
               "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
               "-crf", str(crf), "-b:v", "0",
               "-metadata:s:v:0", "alpha_mode=1",
               output_path]

        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        times: list[float] = []
        idx = 0

        while True:
            ret, frame_bgr = cap.read()
            if not ret:
                break
            t0 = time.perf_counter()
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            alpha = session.predict(frame_rgb)
            rgba = session.apply_mask(frame_rgb, alpha)

            if proc.stdin:
                proc.stdin.write(rgba.tobytes())

            elapsed = (time.perf_counter() - t0) * 1000
            times.append(elapsed)
            if on_progress:
                on_progress(ProgressEvent(
                    kind="frame", frame_index=idx, total_frames=total,
                    avg_ms_per_frame=sum(times) / len(times)
                ))
            idx += 1

        cap.release()
        if proc.stdin:
            proc.stdin.close()
        proc.wait()

        return RemoveResult(
            output_path=output_path,
            frames_processed=idx,
            duration_seconds=dur,
            avg_ms_per_frame=sum(times) / len(times) if times else 0.0,
            provider=session._provider,
            format="webm",
        )


# â”€â”€ Quick API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def remove_background(
    input_path: str,
    output_path: str,
    model: str = DEFAULT_MODEL,
    quality: BgRemovalQuality = "balanced",
) -> RemoveResult:
    """One-call background removal for images or videos."""
    remover = BackgroundRemover(model_id=model, quality=quality)
    ext = Path(input_path).suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        return remover.remove_image(input_path, output_path)
    return remover.remove_video(input_path, output_path)


if __name__ == "__main__":
    import sys

    remover = BackgroundRemover()
    print(f"BackgroundRemover ready, model={remover._model_id}")

    try:
        import cv2
        print("cv2 available")
    except ImportError:
        print("cv2 NOT installed (pip install opencv-python)")

    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        print(f"onnxruntime providers: {providers}")
    except ImportError:
        print("onnxruntime NOT installed (pip install onnxruntime-gpu)")

    try:
        import rembg  # type: ignore
        print("rembg available (will be used as primary backend)")
    except ImportError:
        print("rembg NOT installed (pip install rembg) — will use manual ONNX")

    print("OK background_remover.py")
