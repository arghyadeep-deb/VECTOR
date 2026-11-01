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
_cors_origins = [
    origin.strip()
    for origin in os.environ.get(
        "VECTOR_STUDIO_CORS_ORIGINS",
        "http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:5173,http://localhost:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

_project_dir: str = "."
_ws_clients: list[WebSocket] = []


def set_project_dir(path: str) -> None:
    global _project_dir
    _project_dir = str(Path(path).expanduser().resolve())


def _project_root() -> Path:
    return Path(_project_dir).expanduser().resolve()


def _resolve_composition_path(path: str) -> Path:
    requested = Path(path)
    if requested.is_absolute() or ".." in requested.parts:
        raise HTTPException(400, "Composition path must stay inside the project")
    full_path = (_project_root() / requested).resolve()
    try:
        full_path.relative_to(_project_root())
    except ValueError:
        raise HTTPException(400, "Composition path must stay inside the project")
    if full_path.suffix.lower() != ".html":
        raise HTTPException(400, "Only .html compositions supported")
    return full_path


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
                        "path": os.path.relpath(event.src_path, _project_root()),
                    }))

        observer = Observer()
        observer.schedule(_Handler(), str(_project_root()), recursive=True)
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
    root = _project_root()
    for html_path in root.rglob("*.html"):
        rel = str(html_path.relative_to(root)).replace("\\", "/")
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
    full_path = _resolve_composition_path(path)
    if not full_path.exists():
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
    full_path = _resolve_composition_path(path)
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

        composition_path = str(_resolve_composition_path(body.get("path", "index.html")))
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
    full_path = _resolve_composition_path(path)
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


# ── Content pipeline API ──────────────────────────────────────────────────────

@app.get("/api/content/queue")
async def content_queue() -> JSONResponse:
    """Active + pending video jobs."""
    try:
        from districts.content.video_pipeline import get_job_queue
        jobs = get_job_queue(limit=20)
        return JSONResponse({"jobs": jobs})
    except Exception as e:
        return JSONResponse({"jobs": [], "error": str(e)})


@app.get("/api/content/history")
async def content_history() -> JSONResponse:
    """Completed + failed video jobs."""
    try:
        from districts.content.video_pipeline import get_job_history
        jobs = get_job_history(limit=10)
        return JSONResponse({"jobs": jobs})
    except Exception as e:
        return JSONResponse({"jobs": [], "error": str(e)})


@app.post("/api/content/generate")
async def content_generate(body: dict) -> JSONResponse:
    """Trigger video creation. body: {topic?, platform?, niche?, dry_run?}"""
    topic    = body.get("topic")
    platform = body.get("platform", "both")
    niche    = body.get("niche", "AI")
    dry_run  = bool(body.get("dry_run", False))

    async def _run():
        from districts.content.video_pipeline import VideoPipelineAgent
        agent = VideoPipelineAgent()
        result = await agent.create_and_upload(
            topic=topic, platform=platform, niche=niche, dry_run=dry_run
        )
        await _broadcast({"type": "content_done", **result})

    asyncio.create_task(_run())
    return JSONResponse({"status": "started", "topic": topic or "auto", "niche": niche})


@app.delete("/api/content/cancel/{job_id}")
async def content_cancel(job_id: str) -> JSONResponse:
    """Cancel a pending upload within the safety window."""
    try:
        from districts.content.video_pipeline import cancel_job
        cancelled = cancel_job(job_id)
        await _broadcast({"type": "content_cancelled", "job_id": job_id})
        return JSONResponse({"cancelled": cancelled, "job_id": job_id})
    except Exception as e:
        return JSONResponse({"cancelled": False, "error": str(e)}, status_code=500)


@app.get("/api/content/status")
async def content_status() -> JSONResponse:
    """Platform credential status."""
    from core.config import CONFIG
    keys = CONFIG.get("api_keys", {})
    return JSONResponse({
        "youtube":   bool(keys.get("google_credentials_path")),
        "instagram": bool(keys.get("instagram_access_token")),
        "elevenlabs": bool(keys.get("elevenlabs_key")),
        "niche":     CONFIG.get("content_niche", "AI"),
        "upload_delay_min": CONFIG.get("video_upload_delay_minutes", 30),
    })


# ── Generative Studio API ─────────────────────────────────────────────────────

_media_history: list[dict] = []


@app.post("/api/media/generate")
async def media_generate(body: dict) -> JSONResponse:
    """Dispatch a media generation task (image, video, lipsync, animate)."""
    try:
        from core.media.generative_studio import GenerativeStudio
        studio = GenerativeStudio()
        result = await studio.generate({"params": body})
        if "error" in result:
            return JSONResponse({"error": result["error"]}, status_code=400)
        import time, uuid
        entry = {**result, "id": str(uuid.uuid4()), "action": body.get("action", ""),
                 "created_at": __import__("datetime").datetime.utcnow().isoformat()}
        _media_history.insert(0, entry)
        if len(_media_history) > 50:
            _media_history.pop()
        return JSONResponse(entry)
    except Exception as e:
        logger.error("[VECTOR][studio_server] media_generate error: {}", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/media/history")
async def media_history() -> JSONResponse:
    """Recent generation results (in-memory, last 50)."""
    return JSONResponse(_media_history[:20])


@app.get("/api/media/balance")
async def media_balance() -> JSONResponse:
    """Local-only studio — no cloud credits/billing to report."""
    return JSONResponse({"balance": 0.0, "configured": False, "mode": "local_only"})


@app.get("/api/media/models")
async def media_models() -> JSONResponse:
    """Model catalog grouped by category."""
    from core.media.models import list_by_category
    return JSONResponse({
        cat: [{"id": m.id, "name": m.name, "category": m.category,
               "aspect_ratios": m.aspect_ratios, "max_images": m.max_images}
              for m in list_by_category(cat)]
        for cat in ("t2i", "i2i", "t2v", "i2v", "lipsync", "v2v")
    })


@app.get("/api/media/status")
async def media_status() -> JSONResponse:
    """Backend availability: Wan2GP + local sd.cpp (local-only)."""
    try:
        from core.media.generative_studio import GenerativeStudio
        studio = GenerativeStudio()
        return JSONResponse(await studio.status())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Workflow API ───────────────────────────────────────────────────────────────

_workflows: dict[str, dict] = {}


@app.get("/api/workflows")
async def list_workflows() -> JSONResponse:
    return JSONResponse(list(_workflows.values()))


@app.get("/api/workflows/{workflow_id}")
async def get_workflow(workflow_id: str) -> JSONResponse:
    wf = _workflows.get(workflow_id)
    if not wf:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(wf)


@app.post("/api/workflows")
async def create_workflow(body: dict) -> JSONResponse:
    import uuid, datetime
    wf_id = str(uuid.uuid4())[:8]
    now = datetime.datetime.utcnow().isoformat()
    wf = {**body, "id": wf_id, "created_at": now, "updated_at": now}
    _workflows[wf_id] = wf
    return JSONResponse(wf)


@app.put("/api/workflows/{workflow_id}")
async def update_workflow(workflow_id: str, body: dict) -> JSONResponse:
    import datetime
    wf = _workflows.get(workflow_id)
    if not wf:
        return JSONResponse({"error": "not found"}, status_code=404)
    updated = {**wf, **body, "id": workflow_id, "updated_at": datetime.datetime.utcnow().isoformat()}
    _workflows[workflow_id] = updated
    return JSONResponse(updated)


@app.post("/api/workflows/{workflow_id}/run")
async def run_workflow(workflow_id: str) -> JSONResponse:
    """Execute a workflow sequentially — each node feeds into the next."""
    wf = _workflows.get(workflow_id)
    if not wf:
        return JSONResponse({"error": "not found"}, status_code=404)
    try:
        from core.media.generative_studio import GenerativeStudio
        studio = GenerativeStudio()
        nodes = wf.get("nodes", [])
        edges = wf.get("edges", [])

        # Real topological order (Kahn's algorithm) -- a prior version just
        # split nodes into "no incoming edge" vs "has incoming edge" and kept
        # each bucket's original array order within itself. That only works
        # for a 2-level graph: a 3+ node chain (A -> B -> C) with C appearing
        # before B in the raw `nodes` array (the data model gives no ordering
        # guarantee) ran C before B had produced output, so C's upstream_url
        # lookup silently got "" instead of B's real result.
        by_id = {n["id"]: n for n in nodes}
        indegree = {n["id"]: 0 for n in nodes}
        adj: dict[str, list[str]] = {n["id"]: [] for n in nodes}
        for e in edges:
            if e["source"] in adj and e["target"] in indegree:
                adj[e["source"]].append(e["target"])
                indegree[e["target"]] += 1
        queue = [nid for nid, d in indegree.items() if d == 0]
        ordered_ids: list[str] = []
        while queue:
            nid = queue.pop(0)
            ordered_ids.append(nid)
            for nxt in adj.get(nid, []):
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)
        # A cycle leaves some nodes with indegree > 0 forever -- append them
        # in original order rather than silently dropping them.
        ordered_ids += [nid for nid in by_id if nid not in ordered_ids]
        ordered = [by_id[nid] for nid in ordered_ids]

        results = []
        node_outputs: dict[str, str] = {}  # node_id → output URL

        for node in ordered:
            nid = node["id"]
            ntype = node["type"]
            params = node.get("params", {})

            # Resolve inputs from connected source node
            src_edge = next((e for e in edges if e["target"] == nid), None)
            upstream_url = node_outputs.get(src_edge["source"], "") if src_edge else ""

            try:
                if ntype == "text_input":
                    node_outputs[nid] = params.get("text", "")
                    results.append({"node_id": nid, "status": "done", "url": ""})
                elif ntype == "image_gen":
                    prompt = params.get("text") or upstream_url or params.get("prompt", "")
                    r = await studio.generate_image(prompt, model=params.get("model", "flux-dev"))
                    url = r.get("url") or r.get("image_path") or ""
                    node_outputs[nid] = url
                    results.append({"node_id": nid, "status": "done", "url": url})
                elif ntype == "video_gen":
                    prompt = params.get("text") or upstream_url or params.get("prompt", "")
                    r = await studio.generate_video(prompt, model=params.get("model", "ltx-video"))
                    url = r.get("url") or ""
                    node_outputs[nid] = url
                    results.append({"node_id": nid, "status": "done", "url": url})
                elif ntype == "lipsync":
                    portrait = params.get("portrait", "")
                    audio = upstream_url or params.get("audio", "")
                    r = await studio.lipsync(portrait, audio, model=params.get("model", "infinite-talk"))
                    url = r.get("url") or ""
                    node_outputs[nid] = url
                    results.append({"node_id": nid, "status": "done", "url": url})
                elif ntype == "output":
                    # Every other node type writes its resolved value into
                    # node_outputs so a downstream node can read it -- this
                    # branch didn't, so an "output" node used as a
                    # pass-through (a normal workflow shape, not just a
                    # terminal node) silently broke any node chained after it.
                    node_outputs[nid] = upstream_url
                    results.append({"node_id": nid, "status": "done", "url": upstream_url})
                else:
                    results.append({"node_id": nid, "status": "done", "url": ""})
            except Exception as node_err:
                results.append({"node_id": nid, "status": "error", "error": str(node_err)})

        return JSONResponse({"workflow_id": workflow_id, "results": results})
    except Exception as e:
        logger.error("[VECTOR][studio_server] workflow run error: {}", e)
        return JSONResponse({"error": str(e)}, status_code=500)


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
