"""VECTOR gesture router — MediaPipe hand tracking WebSocket."""

__all__ = [
    "gesture_ws",
    "router",
]

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

router = APIRouter(prefix="/gesture", tags=["gesture"])


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


@router.websocket("/ws")
async def gesture_ws(ws: WebSocket):
    """Stream hand tracking data and gesture classifications."""
    await ws.accept()
    logger.info("[VECTOR][gesture] WebSocket client connected")

    cap = None
    hands = None
    prev_wrist_x = None

    try:
        import cv2
        import mediapipe as mp

        mp_hands = mp.solutions.hands
        hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.6,
        )

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            await ws.send_text(json.dumps({"error": "Camera not available for gesture tracking"}))
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 15)

        swipe_x_history: list[float] = []
        swipe_y_history: list[float] = []

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(frame_rgb)

            payload: dict = {
                "hand_visible": False, "gesture": "", "confidence": 0.0,
                "fingertip_x": 0.5, "fingertip_y": 0.5,
                "hand_count": 0, "hands": [],
            }

            if results.multi_hand_landmarks:
                payload["hand_count"] = len(results.multi_hand_landmarks)
                payload["hand_visible"] = True

                for idx, hand_lm in enumerate(results.multi_hand_landmarks):
                    lm = hand_lm.landmark
                    gesture, confidence = _classify_gesture(lm)

                    # Swipe detection on the primary (first) hand
                    if idx == 0:
                        wrist_x = lm[0].x
                        wrist_y = lm[0].y
                        swipe_x_history.append(wrist_x)
                        swipe_y_history.append(wrist_y)
                        if len(swipe_x_history) > 8:
                            swipe_x_history.pop(0)
                            swipe_y_history.pop(0)
                        if len(swipe_x_history) >= 6:
                            dx = swipe_x_history[-1] - swipe_x_history[0]
                            dy = swipe_y_history[-1] - swipe_y_history[0]
                            if abs(dx) > abs(dy) and abs(dx) > 0.15:
                                gesture = "swipe_left" if dx < 0 else "swipe_right"
                                confidence = 0.85
                                swipe_x_history.clear()
                                swipe_y_history.clear()
                            elif abs(dy) > abs(dx) and abs(dy) > 0.15:
                                gesture = "swipe_up" if dy < 0 else "swipe_down"
                                confidence = 0.82
                                swipe_x_history.clear()
                                swipe_y_history.clear()

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
            else:
                swipe_x_history.clear()
                swipe_y_history.clear()

            await ws.send_text(json.dumps(payload))
            await asyncio.sleep(1 / 15)

    except WebSocketDisconnect:
        logger.info("[VECTOR][gesture] Client disconnected")
    except ImportError as e:
        logger.warning(f"[VECTOR][gesture] mediapipe/cv2 not installed: {e}")
        await ws.send_text(json.dumps({"error": f"MediaPipe not installed: {e}"}))
    except Exception as e:
        logger.error(f"[VECTOR][gesture] Error: {e}")
    finally:
        if cap is not None:
            cap.release()
        if hands is not None:
            hands.close()


if __name__ == "__main__":
    print("gesture.py OK")
