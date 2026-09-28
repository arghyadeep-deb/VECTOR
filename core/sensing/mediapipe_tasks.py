"""MediaPipe Tasks API helpers.

mediapipe >= 0.10.2x removed the legacy `mp.solutions.*` API; hand tracking now goes through `mediapipe.tasks.python.vision.HandLandmarker`,
which needs a model bundle. The bundle is fetched once from Google's public model bucket into models/mediapipe/ (gitignored) on first use.
"""
from __future__ import annotations

__all__ = ["HAND_MODEL_URL", "ModelUnavailable", "ensure_model", "create_hand_landmarker", "model_dir"]

import os
import hashlib
from pathlib import Path

from loguru import logger

HAND_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
HAND_MODEL_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"
_MIN_MODEL_BYTES = 1_000_000
_MAX_MODEL_BYTES = 16_000_000


class ModelUnavailable(RuntimeError):
    """The model bundle is missing and could not be downloaded."""


def model_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "models" / "mediapipe"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_model(
    filename: str,
    url: str,
    *,
    min_bytes: int = _MIN_MODEL_BYTES,
    max_bytes: int = _MAX_MODEL_BYTES,
    expected_sha256: str | None = None,
) -> Path:
    """Return a verified model, downloading atomically with strict size and optional SHA-256 checks."""
    dest = model_dir() / filename
    expected = (expected_sha256 or "").strip().lower()
    if dest.exists():
        size = dest.stat().st_size
        if min_bytes <= size <= max_bytes and (not expected or _sha256(dest) == expected):
            return dest
    try:
        import httpx

        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        digest = hashlib.sha256()
        total = 0
        try:
            with httpx.stream("GET", url, timeout=60, follow_redirects=True) as resp:
                resp.raise_for_status()
                content_length = resp.headers.get("content-length")
                if content_length and int(content_length) > max_bytes:
                    raise ModelUnavailable(f"downloaded {filename} exceeds the {max_bytes}-byte limit")
                with open(tmp, "wb") as fh:
                    for chunk in resp.iter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            raise ModelUnavailable(f"downloaded {filename} exceeds the {max_bytes}-byte limit")
                        digest.update(chunk)
                        fh.write(chunk)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        if total < min_bytes:
            tmp.unlink(missing_ok=True)
            raise ModelUnavailable(f"downloaded {filename} is implausibly small")
        actual = digest.hexdigest()
        if expected and actual != expected:
            tmp.unlink(missing_ok=True)
            raise ModelUnavailable(f"downloaded {filename} failed SHA-256 verification")
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

    path = ensure_model("hand_landmarker.task", HAND_MODEL_URL, expected_sha256=HAND_MODEL_SHA256)
    options = vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(path)),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=num_hands,
        min_hand_detection_confidence=0.7,
        min_tracking_confidence=0.6,
    )
    return vision.HandLandmarker.create_from_options(options)
