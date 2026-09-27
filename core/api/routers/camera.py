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


def _open_camera(index: int):
    """Blocking setup (cv2 import, YOLO weights, device open) -- always called through asyncio.to_thread.

    2026-09-27: all of this used to run inline in the websocket coroutine, so every /camera/ws connection froze the whole
    API (the autonomous loop, every HUD request) for the model load and then for every frame's read + YOLO pass.
    Returns (cv2, cap, model); cap is None when the camera cannot be opened.
    """
    import cv2

    model = None
    try:
        from ultralytics import YOLO
        # yolo11n matches presence_detector so the repo carries ONE weight file
        model = YOLO("yolo11n.pt")
        logger.info("[VECTOR][camera] YOLO yolo11n loaded")
    except Exception as e:
        logger.warning(f"[VECTOR][camera] YOLO unavailable, streaming without detection: {e}")

    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        return cv2, None, model
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 15)
    return cv2, cap, model


def _next_frame_payload(cv2, cap, model) -> str | None:
    """Blocking: grab one frame, run detection, encode. JSON text to send, "" to skip this frame, None when the stream ended."""
    ret, frame = cap.read()
    if not ret:
        return None

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

    # Encode frame to JPEG -> base64
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    if not ok:
        return ""
    return json.dumps({
        "frame": base64.b64encode(buf.tobytes()).decode("ascii"),
        "detections": detections,
        "width": w,
        "height": h,
    })


async def wait_until_active(ws: WebSocket, is_active) -> None:
    """Hold an idle socket open (sending nothing) until `is_active()` turns true; a client that leaves raises WebSocketDisconnect."""
    while not is_active():
        try:
            await asyncio.wait_for(ws.receive_text(), timeout=0.5)     # the HUD's auth handshake arrives here; ignored
        except asyncio.TimeoutError:
            pass


@router.websocket("/ws")
async def camera_ws(ws: WebSocket):
    """Stream webcam frames with YOLO detections as JSON over WebSocket -- ONLY while the camera is switched on (POST /camera/start).

    2026-09-27: the HUD opens this socket as soon as it loads, and the handler used to open the webcam and run YOLO at 15 fps for as long as
    any HUD tab was open, whether or not anyone had asked for the camera. It now idles (camera off, no GPU work) until /camera/start, and
    releases the device again on /camera/stop.
    """
    await ws.accept()
    logger.info("[VECTOR][camera] WebSocket client connected")

    try:
        while True:
            await wait_until_active(ws, lambda: _camera_active)
            cap = None
            try:
                cv2, cap, model = await asyncio.to_thread(_open_camera, _camera_index)
                if cap is None:
                    await ws.send_text(json.dumps({"error": "Camera not available"}))
                    return

                while _camera_active:
                    payload = await asyncio.to_thread(_next_frame_payload, cv2, cap, model)
                    if payload is None:
                        return
                    if payload:
                        await ws.send_text(payload)
                    await asyncio.sleep(1 / 15)  # ~15 fps
            finally:
                if cap is not None:
                    cap.release()
                    logger.info("[VECTOR][camera] Camera released")

    except WebSocketDisconnect:
        logger.info("[VECTOR][camera] WebSocket client disconnected")
    except Exception as e:
        logger.error(f"[VECTOR][camera] Stream error: {e}")
        try:
            await ws.send_text(json.dumps({"error": str(e)}))
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)


if __name__ == "__main__":
    print("camera.py OK")
