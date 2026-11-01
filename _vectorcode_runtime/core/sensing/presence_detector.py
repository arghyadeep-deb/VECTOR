"""Optional person detection/tracking seam for ambient camera presence."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["PresenceResult", "PresenceDetector"]


@dataclass
class PresenceResult:
    status: str
    person_count: int = 0
    tracked_ids: list[int] = field(default_factory=list)
    in_desk_zone: bool = False
    dwell_seconds: float = 0.0
    backend: str = "none"
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "person_count": self.person_count,
            "tracked_ids": self.tracked_ids,
            "in_desk_zone": self.in_desk_zone,
            "dwell_seconds": round(self.dwell_seconds, 2),
            "backend": self.backend,
            "error": self.error,
        }


class PresenceDetector:
    """Lazy optional supervision/YOLO adapter.

    If dependencies or model weights are absent, returns a neutral result and
    lets VECTOR fall back to its existing face detector.
    """

    def __init__(self, enabled: bool | None = None, model_name: str = "yolo11n.pt"):
        if enabled is None:
            try:
                from core.config import CONFIG
                enabled = bool((CONFIG.get("sensing", {}) or {}).get("object_detection_enabled", False))
            except Exception:
                enabled = False
        self.enabled = bool(enabled)
        self.model_name = model_name
        self._model = None
        self._tracker = None
        self._present_since: float | None = None

    def available(self) -> bool:
        if not self.enabled:
            return False
        try:
            import supervision  # noqa: F401
            import ultralytics  # noqa: F401
            return True
        except Exception:
            return False

    def _load(self):
        if not self.enabled:
            raise RuntimeError("presence object detection disabled")
        if self._model is None:
            from ultralytics import YOLO  # type: ignore
            import supervision as sv  # type: ignore

            self._model = YOLO(self.model_name)
            self._tracker = sv.ByteTrack()
        return self._model, self._tracker

    def detect(self, frame: Any | None = None, image_path: str | Path | None = None) -> PresenceResult:
        if not self.enabled:
            return PresenceResult(status="disabled", backend="face_detector_fallback")
        try:
            model, tracker = self._load()
            source = frame if frame is not None else str(image_path) if image_path else None
            if source is None:
                return PresenceResult(status="error", backend="supervision", error="frame or image_path is required")
            import supervision as sv  # type: ignore

            prediction = model(source, verbose=False)[0]
            detections = sv.Detections.from_ultralytics(prediction)
            if detections.class_id is not None:
                detections = detections[detections.class_id == 0]
            tracked = tracker.update_with_detections(detections)
            # supervision exposes tracker_id as a NumPy array.  Using it in a
            # boolean ``or`` expression raises for multi-person detections.
            tracker_ids = tracked.tracker_id if tracked.tracker_id is not None else []
            ids = [int(x) for x in tracker_ids if x is not None]
            count = len(tracked)
            now = time.time()
            if count > 0 and self._present_since is None:
                self._present_since = now
            if count == 0:
                self._present_since = None
            dwell = now - self._present_since if self._present_since else 0.0
            return PresenceResult(
                status="present" if count == 1 else "multiple" if count > 1 else "absent",
                person_count=count,
                tracked_ids=ids,
                in_desk_zone=count > 0,
                dwell_seconds=dwell,
                backend="supervision",
            )
        except Exception as exc:
            return PresenceResult(status="unavailable", backend="face_detector_fallback", error=str(exc))
