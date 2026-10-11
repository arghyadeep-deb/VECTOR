"""Opening the HUD must not switch on the webcam (found 2026-09-27).

The HUD connects /camera/ws and /gesture/ws as soon as it loads. The camera handler used to open the webcam and run YOLO at 15 fps for as
long as any HUD tab existed, and the gesture handler (once ported to the Tasks API) would have driven the HUD's fist-closes-a-widget /
fist+pinch-locks / swipe-toggles-workspace reactions from an always-on camera. Both now idle until switched on.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

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
        self.client = SimpleNamespace(host="testclient")

    async def accept(self):
        pass

    async def receive_json(self):
        from core.api.routers.websocket import WS_API_KEY
        return {"auth": f"Bearer {WS_API_KEY}"}

    async def close(self, code=None, reason=None):
        self.closed = (code, reason)

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


async def _auth_message(token):
    return {"auth": f"Bearer {token}"}


@pytest.mark.asyncio
@pytest.mark.parametrize("handler,module", [(cam.camera_ws, cam), (gesture.gesture_ws, gesture)])
async def test_camera_and_gesture_reject_an_invalid_auth_handshake(monkeypatch, handler, module):
    from core.api.routers import websocket

    monkeypatch.setattr(websocket, "get_secret", lambda _name: "expected-secret")
    monkeypatch.setattr(module, "_camera_active" if module is cam else "_gesture_active", False)
    ws = FakeWS(leave_after_s=0.1)
    ws.receive_json = lambda: _auth_message("wrong-secret")
    await handler(ws)
    assert ws.closed[0] == 1008 and ws.sent == []


def test_the_switches_and_their_status_endpoints(monkeypatch):
    import httpx
    from fastapi import FastAPI

    # FL-031: camera start/stop now route through the real PermissionGateway
    # (YELLOW tier). Approve both decisions here so this test can still
    # verify the toggle+status wiring end-to-end; the denied-decision path
    # is covered separately by test_camera_activation_gateway_gating.py.
    from core.loop.autonomous_loop import AutonomousLoop

    class _ApprovingGateway:
        async def evaluate_external(self, action_type, params, source):
            from core.loop.permission_gateway import GatewayResult
            return GatewayResult(True, "YELLOW", False, {}, "approved for test")

    monkeypatch.setattr(
        AutonomousLoop, "get_instance",
        staticmethod(lambda: SimpleNamespace(_get_gateway=lambda: _ApprovingGateway())),
    )

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


def test_camera_start_is_not_blocked_by_capability_layer(monkeypatch):
    """FL-032: api_camera passes RBAC even if another real gate blocks it."""
    import httpx
    from fastapi import FastAPI

    monkeypatch.setattr(cam, "_camera_active", False)

    app = FastAPI()
    app.include_router(cam.router)

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            resp = (await c.post("/camera/start")).json()
            assert "api_camera lacks generic.run" not in resp.get("reason", "")
            if resp["status"] == "blocked":
                assert (await c.get("/camera/status")).json()["active"] is False
            else:
                assert resp["status"] == "started"
                assert (await c.get("/camera/status")).json()["active"] is True

    asyncio.run(go())


def test_gesture_default_follows_the_environment(monkeypatch):
    import importlib

    monkeypatch.setenv("VECTOR_GESTURE_ENABLED", "1")
    assert importlib.reload(gesture)._gesture_active is True
    monkeypatch.delenv("VECTOR_GESTURE_ENABLED")
    assert importlib.reload(gesture)._gesture_active is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
