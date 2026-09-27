"""MediaPipe Tasks API helpers.

mediapipe >= 0.10.2x removed the legacy `mp.solutions.*` API; hand tracking now goes through `mediapipe.tasks.python.vision.HandLandmarker`,
which needs a model bundle. The bundle is fetched once from Google's public model bucket into models/mediapipe/ (gitignored) on first use.
"""
from __future__ import annotations

__all__ = ["HAND_MODEL_URL", "ModelUnavailable", "ensure_model", "create_hand_landmarker", "model_dir"]

import os
from pathlib import Path

from loguru import logger

HAND_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
_MIN_MODEL_BYTES = 1_000_000


class ModelUnavailable(RuntimeError):
    """The model bundle is missing and could not be downloaded."""


def model_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "models" / "mediapipe"


def ensure_model(filename: str, url: str, *, min_bytes: int = _MIN_MODEL_BYTES) -> Path:
    """Path to the model bundle, downloading it once if absent (atomic: temp file, size check, rename)."""
    dest = model_dir() / filename
    if dest.exists() and dest.stat().st_size >= min_bytes:
        return dest
    try:
        import httpx

        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with httpx.stream("GET", url, timeout=60, follow_redirects=True) as resp:
            resp.raise_for_status()
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_bytes():
                    fh.write(chunk)
        if tmp.stat().st_size < min_bytes:
            tmp.unlink(missing_ok=True)
            raise ModelUnavailable(f"downloaded {filename} is implausibly small")
        os.replace(tmp, dest)
        logger.info("[VECTOR][mediapipe] downloaded {} ({} bytes)", filename, dest.stat().st_size)
        return dest
    except ModelUnavailable:
        raise
    except Exception as e:  # noqa: BLE001
        raise ModelUnavailable(f"{filename} unavailable and could not be downloaded: {type(e).__name__}: {e}") from e


def create_hand_landmarker(num_hands: int = 2):
    """A VIDEO-mode HandLandmarker (call detect_for_video with strictly increasing timestamps). Raises ImportError / ModelUnavailable."""
    import mediapipe as mp  # noqa: F401
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    path = ensure_model("hand_landmarker.task", HAND_MODEL_URL)
    options = vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(path)),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=num_hands,
        min_hand_detection_confidence=0.7,
        min_tracking_confidence=0.6,
    )
    return vision.HandLandmarker.create_from_options(options)
