"""Opening the HUD must not switch on the webcam (found 2026-09-27).

The HUD connects /camera/ws and /gesture/ws as soon as it loads. The camera handler used to open the webcam and run YOLO at 15 fps for as
long as any HUD tab existed, and the gesture handler (once ported to the Tasks API) would have driven the HUD's fist-closes-a-widget /
fist+pinch-locks / swipe-toggles-workspace reactions from an always-on camera. Both now idle until switched on.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import WebSocketDisconnect

from core.api.routers import camera as cam
from core.api.routers import gesture


class FakeWS:
    """accept/receive_text/send_text; `disconnect_after` sends before the client 'leaves'."""

    def __init__(self, disconnect_after=None, leave_after_s=None):
        self.sent, self.disconnect_after, self._start = [], disconnect_after, asyncio.get_event_loop().time()
        self.leave_after_s = leave_after_s

    async def accept(self):
        pass

    async def receive_text(self):
        if self.leave_after_s is not None and asyncio.get_event_loop().time() - self._start > self.leave_after_s:
            raise WebSocketDisconnect()
        await asyncio.sleep(3600)

    async def send_text(self, text):
        if self.disconnect_after is not None and len(self.sent) >= self.disconnect_after:
            raise WebSocketDisconnect()
        self.sent.append(text)


@pytest.mark.asyncio
async def test_camera_stays_off_and_silent_until_started(monkeypatch):
    opened = []
    monkeypatch.setattr(cam, "_camera_active", False)
    monkeypatch.setattr(cam, "_open_camera", lambda i: opened.append(i) or (object(), None, None))
    ws = FakeWS(leave_after_s=1.2)
    await cam.camera_ws(ws)                      # the client leaves after ~1 s; nothing was requested
    assert opened == [] and ws.sent == []


@pytest.mark.asyncio
async def test_camera_streams_only_while_active_and_releases_the_device(monkeypatch):
    class Cap:
        released = 0

        def release(self):
            Cap.released += 1

    frames = iter(range(100))

    def next_frame(cv2, cap, model):
        n = next(frames)
        if n == 1:
            cam._camera_active = False          # the owner presses stop
        return '{"frame": "x"}'

    monkeypatch.setattr(cam, "_camera_active", True)
    monkeypatch.setattr(cam, "_open_camera", lambda i: (object(), Cap(), object()))
    monkeypatch.setattr(cam, "_next_frame_payload", next_frame)
    ws = FakeWS(leave_after_s=2.5)
    await cam.camera_ws(ws)
    assert 1 <= len(ws.sent) <= 2 and Cap.released == 1


@pytest.mark.asyncio
async def test_gesture_stays_off_by_default_and_never_opens_the_camera(monkeypatch):
    opened = []
    monkeypatch.setattr(gesture, "_gesture_active", False)
    monkeypatch.setattr(gesture._HandTracker, "open", classmethod(lambda cls, idx=0: opened.append(idx)))
    ws = FakeWS(leave_after_s=1.2)
    await gesture.gesture_ws(ws)
    assert opened == [] and ws.sent == []


def test_the_switches_and_their_status_endpoints():
    import httpx
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(cam.router)
    app.include_router(gesture.router)

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            assert (await c.get("/gesture/status")).json() == {"active": gesture._gesture_active}
            await c.post("/gesture/start")
            assert (await c.get("/gesture/status")).json() == {"active": True}
            await c.post("/gesture/stop")
            assert (await c.get("/gesture/status")).json() == {"active": False}
            await c.post("/camera/start")
            assert (await c.get("/camera/status")).json()["active"] is True
            await c.post("/camera/stop")
            assert (await c.get("/camera/status")).json()["active"] is False

    asyncio.run(go())


def test_gesture_default_follows_the_environment(monkeypatch):
    import importlib

    monkeypatch.setenv("VECTOR_GESTURE_ENABLED", "1")
    assert importlib.reload(gesture)._gesture_active is True
    monkeypatch.delenv("VECTOR_GESTURE_ENABLED")
    assert importlib.reload(gesture)._gesture_active is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
