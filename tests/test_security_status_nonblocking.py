"""/security/status must not freeze the event loop, and its process list must be honest (found 2026-09-26).

The handler did the ~8 s process scan inline inside an `async def`, so every cache miss stalled every other request (and the
autonomous loop, which lives in the same process) for its whole duration. It also reported the idle pseudo-process at
"2111 %" CPU and per-process CPU summed over cores.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest
from fastapi import FastAPI

from core.api import cache as cache_mod
from core.api.routers import security as sec


def _app(monkeypatch, scan_seconds=1.2, procs=None):
    monkeypatch.setattr(sec, "check_process_anomalies", lambda: (time.sleep(scan_seconds), [{"suspicious": False}])[1])
    procs = procs or [
        SimpleNamespace(info={"pid": 0, "name": "System Idle Process", "cpu_percent": 2100.0, "memory_percent": 0.0, "status": "running"}),
        SimpleNamespace(info={"pid": 10, "name": "python.exe", "cpu_percent": 400.0, "memory_percent": 3.0, "status": "running"}),
        SimpleNamespace(info={"pid": 11, "name": "node.exe", "cpu_percent": 50.0, "memory_percent": 1.0, "status": "running"}),
    ]
    monkeypatch.setattr(sec.psutil, "process_iter", lambda attrs=None: iter(procs))
    monkeypatch.setattr(sec.psutil, "cpu_count", lambda logical=True: 20)
    sec.security_cache.invalidate()  # never let a cached result from another test hide the behaviour under test
    app = FastAPI()
    app.include_router(sec.router)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_a_slow_scan_does_not_block_other_requests(monkeypatch):
    app = _app(monkeypatch, scan_seconds=1.5)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        slow = asyncio.create_task(c.get("/security/status"))
        await asyncio.sleep(0.2)
        t0 = time.monotonic()
        r = await c.get("/ping")
        ping_s = time.monotonic() - t0
        assert r.status_code == 200
        assert ping_s < 0.6, f"/ping waited {ping_s:.2f}s behind the security scan: the event loop is blocked"
        assert (await slow).status_code == 200


@pytest.mark.asyncio
async def test_process_list_excludes_idle_and_normalises_cpu(monkeypatch):
    app = _app(monkeypatch, scan_seconds=0.0)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        body = (await c.get("/security/status")).json()
    names = [p["name"] for p in body["processes"]]
    assert "System Idle Process" not in names
    by = {p["name"]: p["cpu"] for p in body["processes"]}
    assert by["python.exe"] == 20.0 and by["node.exe"] == 2.5          # 400/20 and 50/20: share of the whole machine
    assert all(0.0 <= p["cpu"] <= 100.0 for p in body["processes"])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
