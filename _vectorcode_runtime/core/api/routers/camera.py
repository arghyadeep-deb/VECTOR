"""VECTOR camera router — live webcam stream with YOLO object detection."""

__all__ = [
    "camera_snapshot",
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

from core.sensing.camera_coordinator import get_camera_coordinator

router = APIRouter(prefix="/camera", tags=["camera"])

_camera_active = False
_camera_index = 0


async def _gateway_decision(action_type: str, params: dict):
    """Route a camera state transition through the real PermissionGateway.

    FL-031: start_camera()/stop_camera() used to flip _camera_active
    directly -- the route had auth, but no governance decision gated the
    actual hardware activation. Matches the convention in
    core/api/routers/memory.py's restore_memory().
    """
    from core.loop.autonomous_loop import AutonomousLoop

    loop = AutonomousLoop.get_instance()
    gateway = (loop or AutonomousLoop())._get_gateway()
    return await gateway.evaluate_external(action_type, params, "api_camera")


@router.post("/start")
async def start_camera(index: int = 0):
    """Activate the webcam, gated by the PermissionGateway."""
    global _camera_active, _camera_index
    decision = await _gateway_decision("camera_activate", {"index": index})
    if not decision.approved:
        return {"status": "blocked", "reason": decision.reason, "level": decision.level}
    _camera_active = True
    _camera_index = index
    logger.info(f"[VECTOR][camera] Camera {index} activated")
    return {"status": "started", "index": index}


@router.post("/stop")
async def stop_camera():
    """Deactivate the webcam, gated by the PermissionGateway."""
    global _camera_active
    decision = await _gateway_decision("camera_deactivate", {})
    if not decision.approved:
        return {"status": "blocked", "reason": decision.reason, "level": decision.level}
    _camera_active = False
    logger.info("[VECTOR][camera] Camera stopped")
    return {"status": "stopped"}


@router.get("/status")
async def camera_status():
    return {"active": _camera_active, "index": _camera_index}


@router.post("/snapshot")
async def camera_snapshot(index: int = 0):
    """One-shot frame grab for in-process sensing callers.

    2026-10-25: core/sensing/camera.py's FaceDetector/FatigueMonitor (run
    from the autonomous loop -- a SEPARATE OS process) used to open their
    own cv2.VideoCapture directly, independent of this router's own device
    handle, which is what caused the HUD's live /camera/ws stream to die
    after one frame whenever the loop's 30s sense tick grabbed the webcam
    at the same moment. They now call this endpoint over loopback instead,
    which -- like /camera/ws -- goes through the single shared
    CameraCoordinator, so there is never more than one real device handle
    open at a time no matter how many consumers (this process's stream,
    the loop process's sensing) are active simultaneously. Deliberately
    ungated by the PermissionGateway: it carries the same trust level the
    direct VideoCapture call it replaces always had (unprompted background
    sensing, only runs when sensing.camera_enabled is already on).
    """
    import cv2

    coordinator = get_camera_coordinator()
    opened = await coordinator.acquire(index)
    if not opened:
        return {"status": "error", "error": f"camera {index} not available"}
    try:
        frame = await coordinator.read_frame()
        if frame is None:
            return {"status": "error", "error": "failed to read frame"}
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            return {"status": "error", "error": "failed to encode frame"}
        return {"status": "ok", "frame": base64.b64encode(buf.tobytes()).decode("ascii")}
    finally:
        await coordinator.release()


def _load_yolo_model():
    """Blocking YOLO weight load -- always called through asyncio.to_thread.

    2026-09-27: this used to run inline in the websocket coroutine, so every /camera/ws connection froze the whole
    API (the autonomous loop, every HUD request) for the model load and then for every frame's read + YOLO pass.
    Returns the loaded model, or None when ultralytics/the weights are unavailable (stream continues without detection).
    """
    try:
        from ultralytics import YOLO
        # yolo11n matches presence_detector so the repo carries ONE weight file
        model = YOLO("yolo11n.pt")
        logger.info("[VECTOR][camera] YOLO yolo11n loaded")
        return model
    except Exception as e:
        logger.warning(f"[VECTOR][camera] YOLO unavailable, streaming without detection: {e}")
        return None


def _encode_frame_payload(frame, model) -> str | None:
    """Blocking: run detection on an already-captured frame, encode. JSON text to send, "" to skip this frame."""
    import cv2

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
            await asyncio.wait_for(ws.receive_text(), timeout=0.5)
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
    from core.api.routers.websocket import require_auth_handshake
    if not await require_auth_handshake(ws):
        return
    logger.info("[VECTOR][camera] WebSocket client connected")
    coordinator = get_camera_coordinator()

    try:
        while True:
            await wait_until_active(ws, lambda: _camera_active)
            acquired = False
            try:
                model = await asyncio.to_thread(_load_yolo_model)
                acquired = await coordinator.acquire(_camera_index)
                if not acquired:
                    await ws.send_text(json.dumps({"error": "Camera not available"}))
                    return

                while _camera_active:
                    frame = await coordinator.read_frame()
                    if frame is None:
                        return
                    payload = await asyncio.to_thread(_encode_frame_payload, frame, model)
                    if payload:
                        await ws.send_text(payload)
                    await asyncio.sleep(1 / 15)  # ~15 fps
            finally:
                if acquired:
                    await coordinator.release()
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
