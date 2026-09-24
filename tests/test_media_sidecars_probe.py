"""/media/sidecars -- the HUD asks the backend whether ComfyUI / Studio / Hyperframes are listening (the page's CSP
forbids probing those ports itself), so a panel can say "not running" instead of showing a blank iframe."""
from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.api.routers import media


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(media.router)
    return TestClient(app)


def test_reports_not_running_for_a_dead_port(client, monkeypatch):
    monkeypatch.setenv("COMFYUI_URL", f"http://127.0.0.1:{_free_port()}")
    body = client.get("/media/sidecars").json()
    assert set(body) == {"comfyui", "hyperframes", "studio"}
    assert body["comfyui"]["running"] is False


def test_reports_running_for_a_live_server(client, monkeypatch):
    class _H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    port = _free_port()
    srv = HTTPServer(("127.0.0.1", port), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("COMFYUI_URL", f"http://127.0.0.1:{port}")
        assert client.get("/media/sidecars").json()["comfyui"] == {"url": f"http://127.0.0.1:{port}", "running": True}
    finally:
        srv.shutdown()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
