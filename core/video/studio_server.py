"""
VECTOR Studio Server
Backend for the VECTOR Studio composition editor (dashboard/src/studio/).

Provides:
  - File watching + hot-reload WebSocket (for live composition preview)
  - Composition file read/write API
  - Lint-on-save integration
  - Render-from-studio endpoint

The studio React app connects to this server for:
  - GET  /compositions           — list .html composition files
  - GET  /compositions/{id}      — read composition HTML
  - PUT  /compositions/{id}      — save composition HTML (triggers lint)
  - POST /render                 — trigger a render job
  - WS   /ws                     — file change events for hot reload
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from core.video.composition_linter import lint_composition, LintResult


app = FastAPI(title="VECTOR Studio Server", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_project_dir: str = "."
_ws_clients: list[WebSocket] = []


def set_project_dir(path: str) -> None:
    global _project_dir
    _project_dir = path


# ── WebSocket for hot reload ───────────────────────────────────────────────────

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    _ws_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _ws_clients.remove(websocket)


async def _broadcast(event: dict) -> None:
    dead = []
    for ws in _ws_clients:
        try:
            await ws.send_text(json.dumps(event))
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.remove(ws)


# ── File watcher ───────────────────────────────────────────────────────────────

async def _watch_files() -> None:
    """Watch project dir for HTML changes and broadcast to studio."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler, FileModifiedEvent

        class _Handler(FileSystemEventHandler):
            def on_modified(self, event):
                if not event.is_directory and event.src_path.endswith(".html"):
                    asyncio.create_task(_broadcast({
                        "type": "file_changed",
                        "path": os.path.relpath(event.src_path, _project_dir),
                    }))

        observer = Observer()
        observer.schedule(_Handler(), _project_dir, recursive=True)
        observer.start()
        logger.info("[VECTOR][studio_server] watching: {}", _project_dir)
        while True:
            await asyncio.sleep(1)
    except ImportError:
        logger.warning("[VECTOR][studio_server] watchdog not installed — hot reload disabled")


# ── REST API ───────────────────────────────────────────────────────────────────

@app.get("/compositions")
async def list_compositions() -> JSONResponse:
    """List all .html composition files in the project."""
    files = []
    for html_path in Path(_project_dir).rglob("*.html"):
        rel = str(html_path.relative_to(_project_dir)).replace("\\", "/")
        files.append({
            "id": rel,
            "name": html_path.stem,
            "path": rel,
            "size": html_path.stat().st_size,
        })
    return JSONResponse({"compositions": files})


@app.get("/compositions/{path:path}")
async def get_composition(path: str) -> JSONResponse:
    """Read a composition file."""
    full_path = Path(_project_dir) / path
    if not full_path.exists() or not full_path.suffix == ".html":
        raise HTTPException(404, f"Composition not found: {path}")
    html = full_path.read_text(encoding="utf-8")
    lint = lint_composition(html, file_path=path)
    return JSONResponse({
        "path": path,
        "html": html,
        "lint": {
            "ok": lint.ok,
            "errors": lint.error_count,
            "warnings": lint.warning_count,
            "findings": [
                {"code": f.code, "severity": f.severity, "message": f.message,
                 "fix_hint": f.fix_hint}
                for f in lint.findings
            ],
        },
    })


@app.put("/compositions/{path:path}")
async def save_composition(path: str, body: dict) -> JSONResponse:
    """Save a composition file and return lint results."""
    full_path = Path(_project_dir) / path
    if not path.endswith(".html"):
        raise HTTPException(400, "Only .html compositions supported")
    full_path.parent.mkdir(parents=True, exist_ok=True)
    html = body.get("html", "")
    full_path.write_text(html, encoding="utf-8")

    lint = lint_composition(html, file_path=path)
    await _broadcast({"type": "file_saved", "path": path,
                      "lint_ok": lint.ok, "errors": lint.error_count})

    logger.info("[VECTOR][studio_server] saved {}: lint={}", path, lint.summary())
    return JSONResponse({
        "saved": True,
        "path": path,
        "lint": {
            "ok": lint.ok,
            "errors": lint.error_count,
            "warnings": lint.warning_count,
            "findings": [
                {"code": f.code, "severity": f.severity, "message": f.message,
                 "fix_hint": f.fix_hint}
                for f in lint.findings
            ],
        },
    })


@app.post("/render")
async def trigger_render(body: dict) -> JSONResponse:
    """Trigger a render job from the studio."""
    try:
        from core.video.vector_composer import VectorComposer, ComposerJob
        from core.video.composition_types import Fps

        composition_path = str(Path(_project_dir) / body.get("path", "index.html"))
        output_path = body.get("output", "renders/studio_render.mp4")
        duration = float(body.get("duration", 10.0))
        fps_val = body.get("fps", 30)

        job = ComposerJob(
            composition_path=composition_path,
            output_path=output_path,
            fps=Fps.from_value(fps_val),
            duration_seconds=duration,
            variables=body.get("variables", {}),
        )
        composer = VectorComposer(
            on_progress=lambda p, m: asyncio.create_task(
                _broadcast({"type": "render_progress", "pct": p, "msg": m})
            )
        )
        result = await composer.render(job)
        await _broadcast({"type": "render_complete", "output": result.output_path,
                          "size": result.file_size_bytes})
        return JSONResponse({"status": "ok", "output": result.output_path,
                             "size": result.file_size_bytes, "ms": result.total_ms})
    except Exception as e:
        logger.error("[VECTOR][studio_server] render failed: {}", e)
        await _broadcast({"type": "render_error", "error": str(e)})
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


@app.get("/lint/{path:path}")
async def lint_endpoint(path: str) -> JSONResponse:
    """Lint a composition file on demand."""
    full_path = Path(_project_dir) / path
    if not full_path.exists():
        raise HTTPException(404, f"File not found: {path}")
    html = full_path.read_text(encoding="utf-8")
    lint = lint_composition(html, file_path=path)
    return JSONResponse({
        "ok": lint.ok,
        "error_count": lint.error_count,
        "warning_count": lint.warning_count,
        "info_count": lint.info_count,
        "findings": [
            {"code": f.code, "severity": f.severity, "message": f.message,
             "element_id": f.element_id, "fix_hint": f.fix_hint, "snippet": f.snippet}
            for f in lint.findings
        ],
    })


# ── Entry point ────────────────────────────────────────────────────────────────

def start_studio_server(
    project_dir: str = ".",
    host: str = "127.0.0.1",
    port: int = 51200,
) -> None:
    """Start the VECTOR Studio server. Blocks until Ctrl+C."""
    import uvicorn
    set_project_dir(project_dir)

    @app.on_event("startup")
    async def _startup():
        asyncio.create_task(_watch_files())

    logger.info("[VECTOR][studio_server] starting at http://{}:{}", host, port)
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    import sys, tempfile
    sys.stdout.reconfigure(encoding="utf-8")

    # Smoke test: FastAPI app exists and lint endpoint works
    from fastapi.testclient import TestClient
    client = TestClient(app)

    with tempfile.TemporaryDirectory() as tmp:
        set_project_dir(tmp)
        # Create a test composition
        test_html = """<!DOCTYPE html>
<html><body>
  <div data-composition-id="test-001" data-width="1920" data-height="1080">
    <div id="title" data-start="0" data-track-index="0">VECTOR</div>
  </div>
</body></html>"""
        (Path(tmp) / "test.html").write_text(test_html, encoding="utf-8")

        resp = client.get("/compositions")
        assert resp.status_code == 200
        assert len(resp.json()["compositions"]) == 1

        resp2 = client.get("/compositions/test.html")
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["lint"]["ok"] is True
        assert data["html"] == test_html

        resp3 = client.get("/lint/test.html")
        assert resp3.status_code == 200
        assert resp3.json()["ok"] is True

    print("OK studio_server.py")
