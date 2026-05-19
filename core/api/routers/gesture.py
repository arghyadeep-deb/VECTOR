"""VECTOR gesture router — MediaPipe hand tracking WebSocket."""
import sys
import asyncio
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

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
            max_num_hands=1,
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

        swipe_history: list[float] = []

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(frame_rgb)

            payload: dict = {"hand_visible": False, "gesture": "", "confidence": 0.0, "fingertip_x": 0.5, "fingertip_y": 0.5}

            if results.multi_hand_landmarks:
                lm = results.multi_hand_landmarks[0].landmark
                payload["hand_visible"] = True

                # Index fingertip position (normalized)
                payload["fingertip_x"] = lm[8].x
                payload["fingertip_y"] = lm[8].y

                gesture, confidence = _classify_gesture(lm)

                # Swipe detection: track wrist x movement
                wrist_x = lm[0].x
                swipe_history.append(wrist_x)
                if len(swipe_history) > 8:
                    swipe_history.pop(0)
                if len(swipe_history) >= 6:
                    delta = swipe_history[-1] - swipe_history[0]
                    if abs(delta) > 0.15:
                        gesture = "swipe_left" if delta < 0 else "swipe_right"
                        confidence = 0.85
                        swipe_history.clear()

                payload["gesture"] = gesture
                payload["confidence"] = confidence
            else:
                swipe_history.clear()

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
