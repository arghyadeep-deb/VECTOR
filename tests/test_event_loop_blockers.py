"""Blocking work inside async handlers freezes the whole API (the autonomous loop and the HUD share one event loop).

Found 2026-09-27 with py-spy on the live backend: /camera/ws did the model load, the device open and every frame's read + YOLO
pass inline, and /system, /health/system and /sensing/system slept on psutil.cpu_percent(interval=...) inline. Each test here
measures the event loop's own responsiveness (a heartbeat that must keep ticking) while the handler runs.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import WebSocketDisconnect

from core.api.routers import camera as cam


async def _max_loop_lag(work) -> float:
    """Run `work` (a coroutine) while a heartbeat measures how late the loop wakes it; returns the worst lag in seconds."""
    lag = 0.0
    stop = asyncio.Event()

    async def beat():
        nonlocal lag
        while not stop.is_set():
            t = time.monotonic()
            await asyncio.sleep(0.02)
            lag = max(lag, time.monotonic() - t - 0.02)

    hb = asyncio.create_task(beat())
    try:
        await work
    finally:
        stop.set()
        await hb
    return lag


class _FakeWS:
    def __init__(self, frames):
        self.sent, self._left = [], frames

    async def accept(self):
        pass

    async def receive_json(self):
        from core.api.routers.websocket import WS_API_KEY
        return {"auth": f"Bearer {WS_API_KEY}"}

    async def send_text(self, text):
        if self._left <= 0:
            raise WebSocketDisconnect()
        self._left -= 1
        self.sent.append(text)


class _FakeCap:
    released = False

    def release(self):
        _FakeCap.released = True


@pytest.mark.asyncio
async def test_camera_stream_does_not_block_the_event_loop(monkeypatch):
    monkeypatch.setattr(cam, "_camera_active", True)
    def slow_open(index):
        time.sleep(0.5)                       # model load + device open
        return object(), _FakeCap(), object()

    def slow_frame(cv2, cap, model):
        time.sleep(0.4)                       # read + YOLO + encode
        return '{"frame": "x"}'

    monkeypatch.setattr(cam, "_open_camera", slow_open)
    monkeypatch.setattr(cam, "_next_frame_payload", slow_frame)
    ws = _FakeWS(frames=2)
    lag = await _max_loop_lag(cam.camera_ws(ws))
    assert len(ws.sent) == 2 and _FakeCap.released
    assert lag < 0.25, f"the event loop stalled {lag:.2f}s while the camera streamed"


@pytest.mark.asyncio
async def test_camera_reports_an_unavailable_device_without_blocking(monkeypatch):
    monkeypatch.setattr(cam, "_camera_active", True)
    monkeypatch.setattr(cam, "_open_camera", lambda i: (time.sleep(0.4), (object(), None, None))[1])
    ws = _FakeWS(frames=5)
    lag = await _max_loop_lag(cam.camera_ws(ws))
    assert ws.sent and "Camera not available" in ws.sent[0]
    assert lag < 0.25


@pytest.mark.asyncio
async def test_a_stream_that_ends_stops_cleanly(monkeypatch):
    monkeypatch.setattr(cam, "_camera_active", True)
    monkeypatch.setattr(cam, "_open_camera", lambda i: (object(), _FakeCap(), None))
    monkeypatch.setattr(cam, "_next_frame_payload", lambda cv2, cap, model: None)   # no frame -> the stream is over
    ws = _FakeWS(frames=5)
    await cam.camera_ws(ws)
    assert ws.sent == [] and _FakeCap.released


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["status.system_metrics", "health.system_health", "sensing.sensing_system"])
async def test_system_metric_endpoints_do_not_sleep_on_the_event_loop(monkeypatch, endpoint):
    import importlib
    import psutil

    mod_name, fn_name = endpoint.split(".")
    mod = importlib.import_module(f"core.api.routers.{mod_name}")
    real_cpu = psutil.cpu_percent

    def slow_cpu(interval=None, percpu=False):
        time.sleep(0.4)                       # what interval=0.3 does: it sleeps the calling thread
        return 1.0

    if mod_name == "health":
        from core.api import cache as cache_mod, ssl_cache
        ssl_cache.install()                       # app.py does this at startup; the endpoint builds an httpx client per call
        await mod.system_health()                 # warm-up: the first call pays one-time import costs, which are not blocking work
        cache_mod.health_cache.invalidate()
    monkeypatch.setattr(psutil, "cpu_percent", slow_cpu)
    try:
        lag = await _max_loop_lag(getattr(mod, fn_name)())
    finally:
        monkeypatch.setattr(psutil, "cpu_percent", real_cpu)
    assert lag < 0.25, f"{endpoint} stalled the event loop {lag:.2f}s"


# ── subprocess calls inside async handlers / cron jobs ──────────────────────

class _Done:
    returncode, stdout, stderr = 0, "", ""


@pytest.mark.asyncio
async def test_sandbox_status_does_not_run_docker_on_the_event_loop(monkeypatch):
    import subprocess

    from core.api.routers import sandbox

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (time.sleep(0.5), _Done())[1])
    result = None

    async def call():
        nonlocal result
        result = await sandbox.sandbox_status()

    lag = await _max_loop_lag(call())
    assert result["docker_available"] is True
    assert lag < 0.25, f"docker info stalled the event loop {lag:.2f}s"


@pytest.mark.asyncio
async def test_sensing_gpu_query_does_not_run_on_the_event_loop(monkeypatch):
    import subprocess

    from core.api.routers import sensing

    class Smi(_Done):
        stdout = "40, 1000, 12000"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (time.sleep(0.5), Smi())[1])
    lag = await _max_loop_lag(sensing.sensing_system())
    assert lag < 0.25, f"nvidia-smi stalled the event loop {lag:.2f}s"


@pytest.mark.asyncio
async def test_the_nightly_selfcheck_does_not_freeze_the_event_loop(monkeypatch):
    """compileall (up to 600 s) and the smoke run (up to 300 s) used to run inline in this async cron job."""
    import subprocess

    from core.loop import cron_jobs

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (time.sleep(0.4), _Done())[1])
    result = None

    async def call():
        nonlocal result
        result = await cron_jobs.job_nightly_selfcheck()

    lag = await _max_loop_lag(call())
    assert result["status"] == "ok"
    assert lag < 0.25, f"the selfcheck stalled the event loop {lag:.2f}s"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
