"""
Module: core/sensing/camera.py
FaceDetector: identifies known faces via face_recognition library.
FatigueMonitor: real-time fatigue scoring via mediapipe EAR.
RULE 5 — all camera data stays local, never leaves device.

2026-10-25: this module runs in the autonomous loop process, a SEPARATE OS
process from the FastAPI API process that owns core/api/routers/camera.py's
live /camera/ws stream. Both used to call cv2.VideoCapture(cam_index)
independently, so whichever one read the device second got starved --
exactly what killed the HUD Vision Feed panel's stream after one frame.
Owner decision: single shared camera access for everything. The API
process is now the only one that ever opens the physical device (via
core/sensing/camera_coordinator.py's CameraCoordinator); _grab_shared_frame()
below fetches a frame over loopback HTTP from its /camera/snapshot endpoint
instead, so this process and the HUD panel always go through the same
ref-counted device handle rather than fighting over two separate ones.
"""

import sys

__all__ = [
    "FaceDetector",
    "FatigueMonitor",
]

import base64
import os
from pathlib import Path

import numpy as np
from loguru import logger

from core.config import CONFIG

from typing import Optional


def _grab_shared_frame(cam_index: int):
    """Fetch one frame from the API process's shared CameraCoordinator via
    POST /camera/snapshot, decode it with cv2, and return a BGR numpy array
    (or None on any failure -- network, auth, device unavailable). Never
    raises; callers already treat a missing frame as "no camera this tick".
    """
    import httpx
    import cv2

    base_url = CONFIG.get("sensing", {}).get(
        "camera_api_base_url", "http://127.0.0.1:8010"
    )
    api_key = os.environ.get("VECTOR_API_KEY", "")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    try:
        resp = httpx.post(
            f"{base_url}/camera/snapshot",
            params={"index": cam_index},
            headers=headers,
            timeout=5.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.debug(f"[VECTOR][camera] shared snapshot request failed: {exc}")
        return None

    if data.get("status") != "ok":
        logger.debug(f"[VECTOR][camera] shared snapshot unavailable: {data.get('error')}")
        return None

    try:
        jpg_bytes = base64.b64decode(data["frame"])
        frame = cv2.imdecode(np.frombuffer(jpg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        return frame
    except Exception as exc:
        logger.warning(f"[VECTOR][camera] failed to decode shared snapshot: {exc}")
        return None


class FaceDetector:
    """Detects and identifies faces using the face_recognition library.

    Known face encodings are loaded lazily on first call from
    CONFIG["sensing"]["known_faces_dir"]. Each sub-directory name is treated as
    the person's name; every image inside is loaded as an encoding.
    """

    def __init__(self) -> None:
        self._known_encodings: list = []
        self._known_names: list[str] = []
        self._loaded: bool = False
        self._fr = None          # face_recognition module, lazy
        self._cv2 = None         # cv2 module, lazy

    # ── private helpers ───────────────────────────────────────────────────────

    def _ensure_libs(self) -> bool:
        """Lazy-import heavy vision libs. Returns True if all available."""
        try:
            if self._fr is None:
                import face_recognition as fr
                self._fr = fr
            if self._cv2 is None:
                import cv2
                self._cv2 = cv2
            return True
        except ImportError as exc:
            logger.warning(f"[VECTOR][camera] FaceDetector lib unavailable: {exc}")
            return False

    def _load_known_faces(self) -> None:
        """Load known face encodings from the configured directory."""
        if self._loaded:
            return
        self._loaded = True  # set early — avoid retry loops on partial load

        if not self._ensure_libs():
            return

        known_faces_dir = Path(
            CONFIG.get("sensing", {}).get("known_faces_dir", "./data/known_faces")
        )

        if not known_faces_dir.exists():
            logger.info(
                f"[VECTOR][camera] known_faces_dir not found: {known_faces_dir} "
                f"— running in unknown-only mode"
            )
            return

        cache_file = known_faces_dir / "faces_cache.json"
        if cache_file.exists():
            try:
                import json
                with open(cache_file, "r") as f:
                    data = json.load(f)
                self._known_names = data.get("names", [])
                self._known_encodings = [np.array(e) for e in data.get("encodings", [])]
                logger.info(f"[VECTOR][camera] Loaded {len(self._known_names)} encodings from cache")
                return
            except Exception as exc:
                logger.warning(f"[VECTOR][camera] Cache load failed: {exc}")

        loaded = 0
        for person_dir in known_faces_dir.iterdir():
            if not person_dir.is_dir():
                continue
            name = person_dir.name
            for img_path in person_dir.iterdir():
                if img_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                    continue
                try:
                    img = self._fr.load_image_file(str(img_path))
                    encs = self._fr.face_encodings(img)
                    if encs:
                        self._known_encodings.append(encs[0])
                        self._known_names.append(name)
                        loaded += 1
                except Exception as exc:
                    logger.warning(
                        f"[VECTOR][camera] Failed to encode {img_path}: {exc}"
                    )

        try:
            import json
            with open(cache_file, "w") as f:
                json.dump({
                    "names": self._known_names,
                    "encodings": [e.tolist() for e in self._known_encodings]
                }, f)
        except Exception as exc:
            logger.warning(f"[VECTOR][camera] Cache save failed: {exc}")

        logger.info(
            f"[VECTOR][camera] Loaded {loaded} known face encoding(s) "
            f"for {len(set(self._known_names))} person(s)"
        )

    # ── public API ─────────────────────────────────────────────────────────────

    def scan_frame(self, frame_bgr: np.ndarray) -> list[dict]:
        """Detect and identify faces in a BGR frame.

        Returns a list of dicts:
            {name: str, confidence: float, bbox: (top, right, bottom, left)}
        Unknown faces are labelled "unknown" with confidence 0.0.
        """
        try:
            if not self._ensure_libs():
                return []
            self._load_known_faces()

            # face_recognition expects RGB
            frame_rgb = self._cv2.cvtColor(frame_bgr, self._cv2.COLOR_BGR2RGB)
            locations = self._fr.face_locations(frame_rgb, model="hog")
            if not locations:
                return []

            encodings = self._fr.face_encodings(frame_rgb, locations)
            results: list[dict] = []

            for enc, loc in zip(encodings, locations):
                name = "unknown"
                confidence = 0.0

                if self._known_encodings:
                    distances = self._fr.face_distance(self._known_encodings, enc)
                    best_idx = int(np.argmin(distances))
                    best_dist = float(distances[best_idx])
                    if best_dist < 0.6:  # threshold: lower = stricter
                        name = self._known_names[best_idx]
                        confidence = round(1.0 - best_dist, 3)

                results.append({
                    "name": name,
                    "confidence": confidence,
                    "bbox": loc,          # (top, right, bottom, left)
                })

            logger.debug(
                f"[VECTOR][camera] scan_frame: {len(results)} face(s) detected"
            )
            return results

        except Exception as exc:
            logger.error(f"[VECTOR][camera] scan_frame error: {exc}")
            return []

    def capture_and_scan(self) -> list[dict]:
        """Capture a single frame from the webcam and run scan_frame on it.

        Returns [] gracefully if no camera is available.
        """
        try:
            if not self._ensure_libs():
                return []

            cam_index = CONFIG.get("sensing", {}).get("camera_index", 0)
            frame = _grab_shared_frame(cam_index)

            if frame is None:
                logger.warning("[VECTOR][camera] Failed to capture frame (shared camera)")
                return []

            return self.scan_frame(frame)

        except Exception as exc:
            logger.error(f"[VECTOR][camera] capture_and_scan error: {exc}")
            return []


class FatigueMonitor:
    """Real-time fatigue scoring (0-10) using mediapipe Face Mesh EAR.

    Eye Aspect Ratio (EAR) thresholds:
        EAR < 0.20  -> fatigue 8-10   (heavy drooping / closing)
        EAR 0.20-0.25 -> fatigue 4-7  (moderate tiredness)
        EAR > 0.25  -> fatigue 0-3    (alert)
    """

    # Mediapipe landmark indices for left / right eye
    _LEFT_EYE  = [362, 385, 387, 263, 373, 380]   # p1..p6
    _RIGHT_EYE = [33,  160, 158, 133, 153, 144]

    def __init__(self) -> None:
        self._mp = None             # mediapipe module, lazy
        self._face_mesh = None      # instantiated FaceLandmarker, lazy
        self._cv2 = None
        self._ts_ms = 0

    # ── private ───────────────────────────────────────────────────────────────

    def _ensure_libs(self) -> bool:
        try:
            from core.sensing.mediapipe_tasks import ModelUnavailable, create_face_landmarker

            if self._mp is None:
                import mediapipe as mp
                self._mp = mp
            if self._face_mesh is None:
                self._face_mesh = create_face_landmarker()
            if self._cv2 is None:
                import cv2
                self._cv2 = cv2
            return True
        except ImportError as exc:
            logger.warning(f"[VECTOR][camera] FatigueMonitor lib unavailable: {exc}")
            return False
        except ModelUnavailable as exc:
            logger.warning(f"[VECTOR][camera] FatigueMonitor model unavailable: {exc}")
            return False
        except Exception as exc:
            logger.warning(f"[VECTOR][camera] FatigueMonitor init failed: {exc}")
            return False

    @staticmethod
    def _ear(landmarks, indices: list[int], w: int, h: int) -> float:
        """Compute Eye Aspect Ratio from 6 landmark indices."""
        pts = [(landmarks[i].x * w, landmarks[i].y * h) for i in indices]
        v1 = np.linalg.norm(np.array(pts[1]) - np.array(pts[5]))
        v2 = np.linalg.norm(np.array(pts[2]) - np.array(pts[4]))
        h_dist = np.linalg.norm(np.array(pts[0]) - np.array(pts[3]))
        if h_dist < 1e-6:
            return 0.25  # default neutral
        return float((v1 + v2) / (2.0 * h_dist))

    @staticmethod
    def _ear_to_fatigue(ear: float) -> float:
        """Map EAR to fatigue score 0-10."""
        if ear < 0.15:
            return 10.0
        if ear < 0.20:
            return round(8.0 + (0.20 - ear) / (0.20 - 0.15) * 2.0, 1)
        if ear < 0.25:
            return round(4.0 + (0.25 - ear) / (0.25 - 0.20) * 3.0, 1)
        return round(max(0.0, 3.0 - (ear - 0.25) / (0.35 - 0.25) * 3.0), 1)

    # ── public API ─────────────────────────────────────────────────────────────

    def score_frame(self, frame_bgr: np.ndarray) -> float:
        """Compute fatigue score from a BGR frame. Returns 5.0 on any error."""
        try:
            if not self._ensure_libs():
                return 5.0

            h, w = frame_bgr.shape[:2]
            frame_rgb = self._cv2.cvtColor(frame_bgr, self._cv2.COLOR_BGR2RGB)
            self._ts_ms += 67  # ~15 fps; VIDEO mode needs strictly increasing timestamps
            image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=frame_rgb)
            results = self._face_mesh.detect_for_video(image, self._ts_ms)

            if not results.face_landmarks:
                logger.debug("[VECTOR][camera] No face landmarks detected for EAR")
                return 5.0

            lm = results.face_landmarks[0]
            ear_left  = self._ear(lm, self._LEFT_EYE,  w, h)
            ear_right = self._ear(lm, self._RIGHT_EYE, w, h)
            avg_ear   = (ear_left + ear_right) / 2.0
            score     = self._ear_to_fatigue(avg_ear)

            logger.debug(
                f"[VECTOR][camera] EAR={avg_ear:.3f} -> fatigue={score}"
            )
            return score

        except Exception as exc:
            logger.error(f"[VECTOR][camera] score_frame error: {exc}")
            return 5.0

    def get_fatigue_score(self) -> float:
        """Capture a webcam frame and return the fatigue score. Returns 5.0 on error."""
        try:
            if not self._ensure_libs():
                return 5.0

            cam_index = CONFIG.get("sensing", {}).get("camera_index", 0)
            frame = _grab_shared_frame(cam_index)

            if frame is None:
                logger.warning("[VECTOR][camera] No frame captured for fatigue check (shared camera)")
                return 5.0

            return self.score_frame(frame)

        except Exception as exc:
            logger.error(f"[VECTOR][camera] get_fatigue_score error: {exc}")
            return 5.0


# ── smoke test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    ok = True

    try:
        face_det = FaceDetector()
        faces = face_det.capture_and_scan()
        assert isinstance(faces, list), "capture_and_scan must return a list"
        logger.info(f"[VECTOR][camera] FaceDetector OK — {len(faces)} face(s) found")
    except Exception as exc:
        logger.error(f"[VECTOR][camera] FaceDetector smoke test FAILED: {exc}")
        ok = False

    try:
        fatigue_mon = FatigueMonitor()
        dummy = np.zeros((480, 640, 3), dtype=np.uint8)
        score = fatigue_mon.score_frame(dummy)
        assert isinstance(score, float), "score_frame must return float"
        live_score = fatigue_mon.get_fatigue_score()
        assert isinstance(live_score, float), "get_fatigue_score must return float"
        logger.info(
            f"[VECTOR][camera] FatigueMonitor OK — dummy={score}, live={live_score}"
        )
    except Exception as exc:
        logger.error(f"[VECTOR][camera] FatigueMonitor smoke test FAILED: {exc}")
        ok = False

    print("camera.py OK" if ok else "camera.py FAILED")
