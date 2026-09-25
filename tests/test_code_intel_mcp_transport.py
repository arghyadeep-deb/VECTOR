"""The code-intelligence agent's MCP transport (districts/coding/code_intel_agent.py).

Found 2026-09-25 while installing code intelligence: `_mcp_call` sent a bare `tools/call` with no MCP handshake, so a real
server ignored it and every call would have timed out; it also set variable names the server never reads
(VECTORCODE_QDRANT_MODE ...), so the server fell back to "managed" mode and demanded Docker; and it ran a blocking
subprocess inside an async method, freezing the event loop for up to five minutes.

A fake MCP server (a few lines of Node) proves the handshake and result/error parsing without needing Qdrant or Ollama;
the live test at the bottom runs the real server and skips itself when Qdrant/Ollama are not running.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import socket
import textwrap
import urllib.request

import pytest

from districts.coding import code_intel_agent as cia

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")

_FAKE_SERVER = textwrap.dedent(
    """
    // Minimal MCP stdio server: replies only AFTER the initialize handshake, like a real one.
    const rl = require("readline").createInterface({ input: process.stdin });
    let initialized = false;
    const send = (o) => process.stdout.write(JSON.stringify(o) + "\\n");
    rl.on("line", (line) => {
      let m; try { m = JSON.parse(line); } catch { return; }
      if (m.method === "initialize") {
        send({ jsonrpc: "2.0", id: m.id, result: { protocolVersion: "2024-11-05", capabilities: {}, serverInfo: { name: "fake" } } });
      } else if (m.method === "notifications/initialized") {
        initialized = true;
      } else if (m.method === "tools/call") {
        if (!initialized) return;                       // a real server ignores calls sent without the handshake
        const t = m.params.name;
        if (t === "boom") send({ jsonrpc: "2.0", id: m.id, result: { isError: true, content: [{ type: "text", text: "kaboom" }] } });
        else if (t === "down") send({ jsonrpc: "2.0", id: m.id, result: { isError: true, content: [{ type: "text", text: "Could not connect to Qdrant." }] } });
        else if (t === "pid") send({ jsonrpc: "2.0", id: m.id, result: { content: [{ type: "text", text: String(process.pid) }] } });
        else if (Array.isArray((m.params.arguments || {}).extraExtensions)) send({ jsonrpc: "2.0", id: m.id, error: { code: -32602, message: "Expected string, received array" } });
        else if (Object.values(m.params.arguments || {}).some((v) => v === null)) send({ jsonrpc: "2.0", id: m.id, error: { code: -32602, message: "Expected string, received null" } });
        else send({ jsonrpc: "2.0", id: m.id, result: { content: [{ type: "text", text: "hello " + JSON.stringify(m.params.arguments) }] } });
      }
    });
    """
)


@pytest.fixture()
def fake_server(monkeypatch, tmp_path):
    script = tmp_path / "fake_mcp.js"
    script.write_text(_FAKE_SERVER, encoding="utf-8")
    monkeypatch.setattr(cia, "_DIST", script)
    cia._SESSION.close()          # never reuse a server process started for another script
    yield script
    cia._SESSION.close()


def test_mcp_call_performs_the_handshake_and_returns_the_tool_text(fake_server):
    r = cia._mcp_call("vc_search", {"query": "governor"}, timeout=30)
    assert r == {"text": 'hello {"query":"governor"}'}


def test_the_server_process_is_shared_so_background_index_jobs_survive_between_calls(fake_server):
    """vc_index returns at once and keeps indexing inside the server; a fresh process per call killed every job."""
    a = cia._mcp_call("pid", {}, timeout=30)["text"]
    b = cia._mcp_call("pid", {}, timeout=30)["text"]
    assert a == b


def test_a_dead_server_is_restarted_on_the_next_call(fake_server):
    a = cia._mcp_call("pid", {}, timeout=30)["text"]
    cia._SESSION._proc.kill()
    cia._SESSION._proc.wait()
    b = cia._mcp_call("pid", {}, timeout=30)["text"]
    assert a != b


def test_a_tool_error_is_reported_as_an_error(fake_server):
    r = cia._mcp_call("boom", {}, timeout=30)
    assert r == {"error": "kaboom"}


def test_a_missing_backend_service_is_marked_unavailable(fake_server):
    r = cia._mcp_call("down", {}, timeout=30)
    assert r.get("unavailable") is True and "Qdrant" in r["error"]
    assert "start_code_intel.bat" in r["error"], "the error must say how to start it"


def test_server_environment_uses_the_variable_names_the_server_reads(monkeypatch):
    env = cia._mcp_env()
    assert env["QDRANT_MODE"] == "external" and env["QDRANT_URL"].startswith("http")
    assert env["OLLAMA_MODE"] == "external" and env["OLLAMA_URL"].startswith("http")
    assert env["EMBEDDING_PROVIDER"] == "ollama" and env["EMBEDDING_MODEL"]
    assert "VECTORCODE_QDRANT_MODE" not in env


def test_a_call_does_not_block_the_event_loop(fake_server):
    async def go():
        ticks = 0

        async def ticker():
            nonlocal ticks
            for _ in range(20):
                await asyncio.sleep(0.05)
                ticks += 1

        t = asyncio.create_task(ticker())
        r = await cia._amcp("vc_search", {"query": "x"}, 30)
        await t
        return r, ticks

    r, ticks = asyncio.run(go())
    assert "hello" in r["text"] and ticks == 20


def _up(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=2)
        return True
    except Exception:
        return False


@pytest.mark.skipif(not (cia._DIST.exists() and _up("http://127.0.0.1:6333/healthz") and _up("http://127.0.0.1:11434/api/tags")),
                    reason="needs the built server, a local Qdrant (scripts/start_code_intel.bat) and Ollama")
def test_live_health_reports_qdrant_and_the_embedding_model():
    r = cia._mcp_call("vc_health", {}, timeout=90)
    assert "error" not in r, r
    assert "Qdrant" in r["text"] and "MISSING" not in r["text"], r["text"]


def test_the_server_path_points_inside_this_repo():
    """_CODEBASE_ROOT was one parent too high, so _DIST pointed outside the repo and the built server was never found."""
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    assert cia._CODEBASE_ROOT == repo
    assert cia._DIST == repo / "vectorcode" / "code_intel" / "dist" / "index.js"


def test_none_valued_arguments_are_omitted_because_the_server_schema_rejects_null(fake_server):
    """vc_search / vc_index were rejected live with 'Expected string, received null' for every optional argument left None."""
    r = cia._mcp_call("vc_search", {"query": "x", "fileFilter": None, "languageFilter": None}, timeout=30)
    assert r == {"text": 'hello {"query":"x"}'}, r


def test_extra_extensions_list_becomes_one_comma_separated_string_and_empty_is_omitted(fake_server):
    """vc_index rejected the agent's list with 'Expected string, received array'."""
    r = cia._mcp_call("vc_index", {"projectPath": "p", "extraExtensions": [".vue", ".svelte"]}, timeout=30)
    assert r == {"text": 'hello {"projectPath":"p","extraExtensions":".vue,.svelte"}'}, r
    r = cia._mcp_call("vc_index", {"projectPath": "p", "extraExtensions": []}, timeout=30)
    assert r == {"text": 'hello {"projectPath":"p"}'}, r


def test_a_successful_search_is_returned_and_noted_in_episodic_memory(fake_server, monkeypatch):
    """Every successful vc_search used to come back as an error: the agent called EpisodicMemory.store(metadata=...)."""
    agent = cia.CodeIntelAgent()
    calls = []

    class _Mem:
        def store(self, event_type, content, tags=None, context=None, source="vector"):
            calls.append((event_type, content, tags, context, source))

    monkeypatch.setattr(agent, "_memory", _Mem())
    out = asyncio.run(agent.run({"type": "vc_search", "params": {"query": "governor", "project_path": "p"}}))
    assert out["status"] == "ok", out
    assert calls and calls[0][0] == "code_intel_search" and calls[0][3] == {"query": "governor"}


def test_a_failing_episodic_note_does_not_break_the_query(fake_server, monkeypatch):
    agent = cia.CodeIntelAgent()

    class _Broken:
        def store(self, *a, **k):
            raise RuntimeError("db locked")

    monkeypatch.setattr(agent, "_memory", _Broken())
    out = asyncio.run(agent.run({"type": "vc_search", "params": {"query": "x", "project_path": "p"}}))
    assert out["status"] == "ok", out
