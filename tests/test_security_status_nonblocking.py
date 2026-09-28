"""/security/status must not freeze the API, and its process list must be honest (found 2026-09-26, root-caused 2026-09-27).

2026-09-26: the ~8 s process scan ran inline in an `async def`, freezing the event loop on every cache miss. It also reported
the idle pseudo-process at "2111 %" CPU and per-process CPU summed over cores.
2026-09-27: moving it to a worker thread was not enough. py-spy on the live API showed 67% of all GIL time inside psutil's
per-process cpu/memory/status calls (Windows: each call is a whole-system query that holds the GIL), and /agents stalled
15-27 s every ~30 s. The per-process table now comes from a child process (core/control/security/process_snapshot.py),
refreshed at most every two minutes and served stale-while-revalidate.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest
from fastapi import FastAPI

from core.api.routers import security as sec
from core.api.schemas import ProcessInfo


def _row(name="python.exe", cpu=20.0):
    return ProcessInfo(name=name, cpu=cpu, mem=3.0, status="running")


def _app(monkeypatch, snapshot=None):
    """`snapshot` returns the table rows (or None = the child failed); the fake wraps them as (anomalies, rows)."""
    calls = {"snapshot": 0}

    def fake_snapshot():
        calls["snapshot"] += 1
        rows = snapshot() if callable(snapshot) else (snapshot if snapshot is not None else [_row(), _row("node.exe", 2.5)])
        return None if rows is None else (1, rows)

    monkeypatch.setattr(sec, "_run_snapshot_blocking", fake_snapshot)
    monkeypatch.setitem(sec._table, "rows", [])
    monkeypatch.setitem(sec._table, "anomalies", 0)
    monkeypatch.setitem(sec._table, "at", 0.0)
    monkeypatch.setattr(sec, "_refresh_task", None)
    sec.security_cache.invalidate()  # never let a cached result from another test hide the behaviour under test
    app = FastAPI()
    app.include_router(sec.router)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return app, calls


def test_the_router_no_longer_calls_psutil_in_process():
    """The expensive per-process psutil calls hold the GIL; the API module must not import psutil at all."""
    assert not hasattr(sec, "psutil")


@pytest.mark.asyncio
async def test_a_slow_scan_does_not_block_other_requests(monkeypatch):
    app, _ = _app(monkeypatch, snapshot=lambda: (time.sleep(1.5), [_row()])[1])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        slow = asyncio.create_task(c.get("/security/status"))
        await asyncio.sleep(0.2)
        t0 = time.monotonic()
        r = await c.get("/ping")
        assert r.status_code == 200
        assert time.monotonic() - t0 < 0.6, "the event loop is blocked behind the security scan"
        assert (await slow).status_code == 200


@pytest.mark.asyncio
async def test_the_process_table_is_scanned_once_per_ttl_not_once_per_request(monkeypatch):
    app, calls = _app(monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        first = (await c.get("/security/status")).json()
        sec.security_cache.invalidate()  # the 15 s response cache expires; the table must NOT be rescanned
        second = (await c.get("/security/status")).json()
    assert calls["snapshot"] == 1
    assert [p["name"] for p in first["processes"]] == [p["name"] for p in second["processes"]] == ["python.exe", "node.exe"]


@pytest.mark.asyncio
async def test_a_stale_table_is_served_immediately_while_it_refreshes(monkeypatch):
    app, calls = _app(monkeypatch, snapshot=lambda: (time.sleep(0.8), [_row("fresh.exe")])[1])
    monkeypatch.setitem(sec._table, "rows", [_row("stale.exe")])
    monkeypatch.setitem(sec._table, "at", time.monotonic() - 10_000)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        t0 = time.monotonic()
        body = (await c.get("/security/status")).json()
        assert time.monotonic() - t0 < 0.5, "a stale table must not make the caller wait for the rescan"
        assert [p["name"] for p in body["processes"]] == ["stale.exe"]
        await asyncio.sleep(1.2)
    assert [r.name for r in sec._table["rows"]] == ["fresh.exe"] and calls["snapshot"] == 1


@pytest.mark.asyncio
async def test_a_failed_scan_gives_an_honest_empty_table_not_a_500(monkeypatch):
    app, _ = _app(monkeypatch, snapshot=lambda: None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/security/status")
    assert r.status_code == 200 and r.json()["processes"] == []


def test_the_router_does_not_import_psutil_or_enumerate_processes_itself():
    src = Path(sec.__file__).read_text(encoding="utf-8")
    assert "process_iter" not in src and "import psutil" not in src


def test_the_anomaly_scan_also_runs_in_a_child_process_and_agrees_with_the_in_process_one():
    from core.control.security import threat_detector as td

    rows = td.check_process_anomalies()          # child process by default
    assert rows and {"pid", "name", "exe", "suspicious", "reason"} <= set(rows[0])
    assert isinstance(json.dumps(rows), str)


def test_a_failed_child_scan_falls_back_to_the_in_process_scan(monkeypatch):
    from core.control.security import threat_detector as td

    def boom(*a, **k):
        raise OSError("cannot spawn")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(td, "scan_processes_inprocess", lambda: [{"pid": 1, "name": "x", "exe": "", "suspicious": False, "reason": ""}])
    assert td.check_process_anomalies()[0]["pid"] == 1


def test_the_child_process_really_returns_an_honest_table():
    """Real subprocess, real psutil (about 10 s on a 360-process machine): idle pseudo-process excluded, CPU in 0..100."""
    out = subprocess.run([sys.executable, str(sec._SNAPSHOT_SCRIPT), "table", "5"], capture_output=True, text=True,
                         timeout=120, check=True).stdout
    rows = json.loads(out)
    assert 0 < len(rows) <= 5
    assert "System Idle Process" not in [r["name"] for r in rows]
    assert all(0.0 <= r["cpu"] <= 100.0 and r["status"] for r in rows)
    assert [r["cpu"] for r in rows] == sorted((r["cpu"] for r in rows), reverse=True)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
