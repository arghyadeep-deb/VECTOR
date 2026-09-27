"""VECTOR gesture router — MediaPipe hand tracking WebSocket (MediaPipe Tasks API)."""

__all__ = [
    "gesture_ws",
    "router",
]

import asyncio
import json
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

router = APIRouter(prefix="/gesture", tags=["gesture"])

# Hand control is OPT-IN. The HUD closes the top widget on a fist, locks on fist+pinch and toggles the workspace on a swipe, and this socket
# opens the webcam, so it must never run merely because a HUD tab is open. Switch on with POST /gesture/start or VECTOR_GESTURE_ENABLED=1.
_gesture_active = os.environ.get("VECTOR_GESTURE_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


@router.post("/start")
async def start_gesture():
    global _gesture_active
    _gesture_active = True
    logger.info("[VECTOR][gesture] hand control switched on")
    return {"status": "started"}


@router.post("/stop")
async def stop_gesture():
    global _gesture_active
    _gesture_active = False
    logger.info("[VECTOR][gesture] hand control switched off")
    return {"status": "stopped"}


@router.get("/status")
async def gesture_status():
    return {"active": _gesture_active}


def _classify_gesture(landmarks) -> tuple[str, float]:
    """Classify hand gesture from MediaPipe landmarks. Returns (gesture, confidence)."""
    # Tip landmark indices: thumb=4, index=8, middle=12, ring=16, pinky=20
    # MCP (knuckle) indices: thumb=2, index=5, middle=9, ring=13, pinky=17
    tips = [4, 8, 12, 16, 20]
    mcps = [2, 5, 9, 13, 17]

    def tip_above_mcp(tip_i, mcp_i):
        return landmarks[tip_i].y < landmarks[mcp_i].y

    fingers_up = [tip_above_mcp(tips[i], mcps[i]) for i in range(5)]
    count_up = sum(fingers_up)

    # Fist: all fingers down
    if count_up == 0:
        return ("fist", 0.9)

    # Open palm: all 5 up
    if count_up == 5:
        return ("open_palm", 0.9)

    # Pinch: thumb and index close together, others down
    if not fingers_up[2] and not fingers_up[3] and not fingers_up[4]:
        dx = abs(landmarks[4].x - landmarks[8].x)
        dy = abs(landmarks[4].y - landmarks[8].y)
        dist = (dx**2 + dy**2) ** 0.5
        if dist < 0.05:
            return ("pinch", 0.85)

    # Point: only index up
    if fingers_up[1] and not fingers_up[2] and not fingers_up[3] and not fingers_up[4]:
        return ("point", 0.85)

    return ("unknown", 0.3)


class _HandTracker:
    """Camera + HandLandmarker (MediaPipe Tasks API). Every method here BLOCKS -- call them through asyncio.to_thread.

    2026-09-27: ported off the removed legacy `mp.solutions.hands` API, and off the event loop (the device open, the model load and every
    frame's read + inference used to run inline in the websocket coroutine and froze the whole API while a client was connected).
    """

    def __init__(self, cv2, mp, cap, landmarker) -> None:
        self.cv2, self.mp, self.cap, self.landmarker = cv2, mp, cap, landmarker
        self.swipe_x: list[float] = []
        self.swipe_y: list[float] = []
        self._ts_ms = 0

    @classmethod
    def open(cls, camera_index: int = 0) -> "_HandTracker":
        import cv2
        import mediapipe as mp

        if not hasattr(mp, "tasks"):
            raise ImportError(f"mediapipe {getattr(mp, '__version__', '?')} has no Tasks API (mediapipe.tasks.python.vision)")
        from core.sensing.mediapipe_tasks import create_hand_landmarker

        landmarker = create_hand_landmarker(num_hands=2)
        cap = cv2.VideoCapture(camera_index)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 15)
        else:
            cap.release()
            cap = None
        return cls(cv2, mp, cap, landmarker)

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
        try:
            self.landmarker.close()
        except Exception:  # noqa: BLE001
            logger.debug("[VECTOR][gesture] landmarker close failed", exc_info=True)

    def next_payload(self) -> dict | None:
        """One frame -> payload dict, or None when the stream ended."""
        ret, frame = self.cap.read()
        if not ret:
            return None
        rgb = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
        self._ts_ms += 67                                     # ~15 fps; VIDEO mode needs strictly increasing timestamps
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
        return self.payload_from(self.landmarker.detect_for_video(image, self._ts_ms).hand_landmarks)

    def payload_from(self, hands_lm) -> dict:
        """Build the websocket payload from a list of per-hand landmark lists (each landmark has .x / .y)."""
        payload: dict = {
            "hand_visible": False, "gesture": "", "confidence": 0.0,
            "fingertip_x": 0.5, "fingertip_y": 0.5,
            "hand_count": 0, "hands": [],
        }
        if not hands_lm:
            self.swipe_x.clear()
            self.swipe_y.clear()
            return payload

        payload["hand_count"] = len(hands_lm)
        payload["hand_visible"] = True
        for idx, lm in enumerate(hands_lm):
            gesture, confidence = _classify_gesture(lm)

            # Swipe detection on the primary (first) hand
            if idx == 0:
                self.swipe_x.append(lm[0].x)
                self.swipe_y.append(lm[0].y)
                if len(self.swipe_x) > 8:
                    self.swipe_x.pop(0)
                    self.swipe_y.pop(0)
                if len(self.swipe_x) >= 6:
                    dx = self.swipe_x[-1] - self.swipe_x[0]
                    dy = self.swipe_y[-1] - self.swipe_y[0]
                    if abs(dx) > abs(dy) and abs(dx) > 0.15:
                        gesture = "swipe_left" if dx < 0 else "swipe_right"
                        confidence = 0.85
                        self.swipe_x.clear()
                        self.swipe_y.clear()
                    elif abs(dy) > abs(dx) and abs(dy) > 0.15:
                        gesture = "swipe_up" if dy < 0 else "swipe_down"
                        confidence = 0.82
                        self.swipe_x.clear()
                        self.swipe_y.clear()

            payload["hands"].append({
                "index":       idx,
                "gesture":     gesture,
                "confidence":  confidence,
                "fingertip_x": lm[8].x,
                "fingertip_y": lm[8].y,
                "wrist_x":     lm[0].x,
                "wrist_y":     lm[0].y,
            })

        # Inter-hand distance for two-hand gestures (zoom, clap, bilateral)
        if len(payload["hands"]) == 2:
            h0, h1 = payload["hands"]
            dx = h0["wrist_x"] - h1["wrist_x"]
            dy = h0["wrist_y"] - h1["wrist_y"]
            payload["hand_distance"] = round((dx ** 2 + dy ** 2) ** 0.5, 4)

        # Back-compat: flat fields from primary hand
        primary = payload["hands"][0]
        payload["gesture"]     = primary["gesture"]
        payload["confidence"]  = primary["confidence"]
        payload["fingertip_x"] = primary["fingertip_x"]
        payload["fingertip_y"] = primary["fingertip_y"]
        return payload


@router.websocket("/ws")
async def gesture_ws(ws: WebSocket):
    """Stream hand tracking data and gesture classifications -- only while hand control is switched on."""
    await ws.accept()
    from core.api.routers.websocket import require_auth_handshake
    if not await require_auth_handshake(ws):
        return
    logger.info("[VECTOR][gesture] WebSocket client connected")

    tracker: _HandTracker | None = None

    try:
        from core.api.routers.camera import wait_until_active
        from core.sensing.mediapipe_tasks import ModelUnavailable

        while True:
            await wait_until_active(ws, lambda: _gesture_active)
            try:
                tracker = await asyncio.to_thread(_HandTracker.open)
            except ModelUnavailable as e:
                await ws.send_text(json.dumps({"type": "unavailable", "error": f"hand model unavailable: {e}"}))
                return
            if tracker.cap is None:
                await ws.send_text(json.dumps({"error": "Camera not available for gesture tracking"}))
                return

            try:
                while _gesture_active:
                    payload = await asyncio.to_thread(tracker.next_payload)
                    if payload is None:
                        return
                    await ws.send_text(json.dumps(payload))
                    await asyncio.sleep(1 / 15)
            finally:
                tracker.close()
                tracker = None

    except WebSocketDisconnect:
        logger.info("[VECTOR][gesture] Client disconnected")
    except ImportError as e:
        logger.warning(f"[VECTOR][gesture] mediapipe/cv2 not installed: {e}")
        await ws.send_text(json.dumps({"type": "unavailable", "error": f"MediaPipe not available: {e}"}))
    except Exception as e:
        logger.error(f"[VECTOR][gesture] Error: {e}")
        try:
            await ws.send_text(json.dumps({"type": "error", "error": str(e)}))
        except Exception:
            logger.debug("[VECTOR][gesture] could not report error to client", exc_info=True)
    finally:
        if tracker is not None:
            tracker.close()


if __name__ == "__main__":
    print("gesture.py OK")
