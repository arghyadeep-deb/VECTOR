"""Regression for vectorcode/src/api/server.py's streaming endpoints:

both _handle_chat (stream=True) and _handle_run_events sent
"Content-Type: text/event-line" -- not a real MIME type. The correct
Server-Sent-Events type is "text/event-stream"; a real SSE client (or any
strict HTTP client) would not recognize the response as a stream.

Dormant today (zero real callers anywhere in the repo, confirmed via
grep), fixed anyway per this cycle's established bar.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

aiohttp = pytest.importorskip("aiohttp")
from aiohttp.test_utils import TestClient, TestServer

from api.server import APIServer


@pytest.mark.asyncio
async def test_chat_stream_uses_event_stream_content_type():
    server = APIServer()
    # Build the aiohttp app the same way start() does, without binding a real socket.
    from aiohttp import web
    app = web.Application()
    app.router.add_post("/v1/chat/completions", server._handle_chat)
    app.router.add_get("/v1/runs/{run_id}/events", server._handle_run_events)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}], "stream": True})
        assert resp.headers["Content-Type"].split(";")[0] == "text/event-stream"
        await resp.release()

        server._runs["run-1"] = {"status": "running", "events": [{"type": "created", "timestamp": 0}]}
        resp2 = await client.get("/v1/runs/run-1/events")
        assert resp2.headers["Content-Type"].split(";")[0] == "text/event-stream"
        await resp2.release()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
