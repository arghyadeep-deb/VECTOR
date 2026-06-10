"""VECTOR camera router — live webcam stream with YOLO object detection."""

__all__ = [
    "camera_status",
    "camera_ws",
    "router",
    "start_camera",
    "stop_camera",
]

import asyncio
import base64
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from loguru import logger

router = APIRouter(prefix="/camera", tags=["camera"])

_camera_active = False
_camera_index = 0


@router.post("/start")
async def start_camera(index: int = 0):
    """Activate the webcam."""
    global _camera_active, _camera_index
    _camera_active = True
    _camera_index = index
    logger.info(f"[VECTOR][camera] Camera {index} activated")
    return {"status": "started", "index": index}


@router.post("/stop")
async def stop_camera():
    """Deactivate the webcam."""
    global _camera_active
    _camera_active = False
    logger.info("[VECTOR][camera] Camera stopped")
    return {"status": "stopped"}


@router.get("/status")
async def camera_status():
    return {"active": _camera_active, "index": _camera_index}


@router.websocket("/ws")
async def camera_ws(ws: WebSocket):
    """Stream webcam frames with YOLO detections as JSON over WebSocket."""
    await ws.accept()
    logger.info("[VECTOR][camera] WebSocket client connected")

    cap = None
    model = None

    try:
        import cv2

        # Try to load YOLO — gracefully skip if not available
        try:
            from ultralytics import YOLO
            model = YOLO("yolov8n.pt")
            logger.info("[VECTOR][camera] YOLO yolov8n loaded")
        except Exception as e:
            logger.warning(f"[VECTOR][camera] YOLO unavailable, streaming without detection: {e}")

        cap = cv2.VideoCapture(_camera_index)
        if not cap.isOpened():
            await ws.send_text(json.dumps({"error": "Camera not available"}))
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 15)

        encode_params = [cv2.IMWRITE_JPEG_QUALITY, 70]

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            detections = []
            h, w = frame.shape[:2]

            # Run YOLO detection if available
            if model is not None:
                try:
                    results = model(frame, verbose=False, conf=0.4)
                    for r in results:
                        for box in r.boxes:
                            x1, y1, x2, y2 = box.xyxy[0].tolist()
                            cls = int(box.cls[0])
                            conf = float(box.conf[0])
                            label = model.names.get(cls, str(cls))
                            detections.append({
                                "label": label,
                                "confidence": round(conf, 2),
                                "bbox": [round(x1), round(y1), round(x2 - x1), round(y2 - y1)],
                            })
                except Exception as e:
                    logger.warning(f"[VECTOR][camera] Detection error: {e}")

            # Encode frame to JPEG → base64
            ok, buf = cv2.imencode(".jpg", frame, encode_params)
            if not ok:
                continue

            frame_b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            payload = json.dumps({
                "frame": frame_b64,
                "detections": detections,
                "width": w,
                "height": h,
            })

            await ws.send_text(payload)
            await asyncio.sleep(1 / 15)  # ~15 fps

    except WebSocketDisconnect:
        logger.info("[VECTOR][camera] WebSocket client disconnected")
    except Exception as e:
        logger.error(f"[VECTOR][camera] Stream error: {e}")
        try:
            await ws.send_text(json.dumps({"error": str(e)}))
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
    finally:
        if cap is not None:
            cap.release()
        logger.info("[VECTOR][camera] Camera released")


if __name__ == "__main__":
    print("camera.py OK")
