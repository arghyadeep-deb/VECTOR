"""
MCP stdio kernel — JSON-RPC 2.0 over stdin/stdout for MCP tool servers.

Python equivalent of ruflo/src/mcp-bridge/mcp-stdio-kernel.js.
Enables Claude Code, Cursor, and other MCP clients to connect to VECTOR's
tools via the stdio transport (no HTTP/port needed — most secure mode).

Protocol: MCP (Model Context Protocol) over stdio.
Each line on stdin is a JSON-RPC 2.0 request.
Each line on stdout is a JSON-RPC 2.0 response.

Architecture:
  MCP Client (Claude Code) ──stdio──► this kernel ──► core/mcp_server.py tools
"""
from __future__ import annotations

__all__ = [
    "KERNEL_ID",
    "KERNEL_SECRET",
    "ensure_production_secret",
    "main",
    "run_stdio",
]


import sys
import json
import asyncio
import hashlib
import hmac
import os
import uuid
import time


from loguru import logger

_MIN_SECRET_LEN = 32
# A configured secret keeps signed requests valid across restarts/processes.
# Without one we fall back to an ephemeral per-process secret — fine for local
# dev, but it must NOT be used in production (signatures would break between
# the kernel and any other process). ensure_production_secret() fails closed.
_CONFIGURED_SECRET = os.environ.get("MCP_KERNEL_SECRET", "").strip()
KERNEL_SECRET = _CONFIGURED_SECRET or str(uuid.uuid4())
KERNEL_SECRET_EPHEMERAL = not _CONFIGURED_SECRET
KERNEL_ID = f"vector-mcp-{os.getpid()}"


def _is_hardened() -> bool:
    return os.environ.get("VECTOR_ENV", "").strip().lower() in {"prod", "production", "vector"}


def ensure_production_secret() -> None:
    """Fail closed in production when MCP_KERNEL_SECRET is missing or too weak.

    No-op in development (the ephemeral fallback is acceptable for local use).
    Raises RuntimeError so the stdio kernel refuses to start unsafely.
    """
    if not _is_hardened():
        return
    if KERNEL_SECRET_EPHEMERAL:
        raise RuntimeError(
            "MCP_KERNEL_SECRET is required in production: signed MCP requests use "
            "an ephemeral per-process secret that breaks across restarts. Set "
            "MCP_KERNEL_SECRET to at least "
            f"{_MIN_SECRET_LEN} random characters."
        )
    if len(KERNEL_SECRET) < _MIN_SECRET_LEN:
        raise RuntimeError(
            f"MCP_KERNEL_SECRET is too weak for production (need >= {_MIN_SECRET_LEN} "
            "characters). Generate one with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )

# Tool registry cache (1 min TTL)
_tool_cache: dict | None = None
_tool_cache_time: float = 0.0
_CACHE_TTL = 60.0


def _sign_request(payload: dict) -> dict:
    """HMAC-SHA256 request signing — mirrors ruflo's CRYPTO_SEG."""
    timestamp = int(time.time() * 1000)
    nonce = str(uuid.uuid4())
    data = f"{timestamp}:{nonce}:{json.dumps(payload, separators=(',', ':'))}"
    sig = hmac.new(KERNEL_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()
    return {"timestamp": timestamp, "nonce": nonce, "signature": sig, "kernelId": KERNEL_ID}


def _make_response(req_id, result=None, error=None) -> dict:
    resp: dict = {"jsonrpc": "2.0", "id": req_id}
    if error:
        resp["error"] = error
    else:
        resp["result"] = result
    return resp


def _list_tools() -> list[dict]:
    """Return VECTOR's available MCP tools from core/mcp_server.py."""
    global _tool_cache, _tool_cache_time
    now = time.time()
    if _tool_cache is not None and (now - _tool_cache_time) < _CACHE_TTL:
        return _tool_cache

    tools = []
    try:
        from core.mcp_server import create_mcp_server
        server = create_mcp_server()
        # Enumerate registered tools
        for tool in getattr(server, "_tools", {}).values():
            tools.append({
                "name": getattr(tool, "name", str(tool)),
                "description": getattr(tool, "description", ""),
                "inputSchema": getattr(tool, "input_schema", {"type": "object", "properties": {}}),
            })
    except Exception as e:
        logger.debug("[VECTOR][mcp_stdio] tool registry unavailable: {}", e)
        # Return basic VECTOR tools as fallback
        tools = [
            {"name": "dispatch_task", "description": "Dispatch a task to a VECTOR district agent",
             "inputSchema": {"type": "object", "properties": {"type": {"type": "string"}, "params": {"type": "object"}}}},
            {"name": "query_memory", "description": "Query VECTOR's episodic memory",
             "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}}},
            {"name": "get_status", "description": "Get VECTOR system status",
             "inputSchema": {"type": "object", "properties": {}}},
        ]

    _tool_cache = tools
    _tool_cache_time = now
    return tools


async def _call_tool(name: str, arguments: dict) -> dict:
    """Execute a VECTOR MCP tool call."""
    try:
        if name == "dispatch_task":
            from core.city.governor import Governor
            gov = Governor()
            result = await gov.dispatch({"type": arguments.get("type", "status"),
                                         "params": arguments.get("params", {})})
            return {"content": [{"type": "text", "text": json.dumps(result)}]}

        elif name == "query_memory":
            from core.memory.episodic import EpisodicMemory
            mem = EpisodicMemory()
            events = mem.recall(arguments.get("query", ""), limit=arguments.get("limit", 10))
            return {"content": [{"type": "text", "text": json.dumps(events)}]}

        elif name == "get_status":
            from core.city.governor import Governor
            gov = Governor()
            summary = gov.get_district_summary()
            return {"content": [{"type": "text", "text": json.dumps({"status": "ok", "districts": summary})}]}

        else:
            # Try calling through the full MCP server
            from core.mcp_server import create_mcp_server
            server = create_mcp_server()
            result = await server.call_tool(name, arguments)
            return result

    except Exception as e:
        logger.error("[VECTOR][mcp_stdio] tool call failed {}: {}", name, e)
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}


async def _handle_request(req: dict) -> dict:
    """Route a JSON-RPC request to the correct handler."""
    req_id = req.get("id")
    method = req.get("method", "")
    params = req.get("params", {})

    if method == "initialize":
        return _make_response(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "VECTOR MCP Server", "version": "1.0.0"},
        })

    elif method == "tools/list":
        tools = _list_tools()
        return _make_response(req_id, {"tools": tools})

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        result = await _call_tool(tool_name, arguments)
        return _make_response(req_id, result)

    elif method == "ping":
        return _make_response(req_id, {"status": "ok", "kernel": KERNEL_ID})

    else:
        return _make_response(req_id, error={
            "code": -32601, "message": f"Method not found: {method}"
        })


async def run_stdio():
    """Main stdio loop — read JSON-RPC from stdin, write responses to stdout."""
    logger.info("[VECTOR][mcp_stdio] kernel {} starting", KERNEL_ID)
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    loop = asyncio.get_event_loop()
    await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)

    writer_transport, writer_protocol = await loop.connect_write_pipe(
        asyncio.BaseProtocol, sys.stdout.buffer
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, loop)

    while True:
        try:
            line = await reader.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            req = json.loads(line)
            response = await _handle_request(req)
            out = json.dumps(response) + "\n"
            writer.write(out.encode())
            await writer.drain()
        except json.JSONDecodeError as e:
            err = json.dumps(_make_response(None, error={"code": -32700, "message": f"Parse error: {e}"}))
            writer.write((err + "\n").encode())
            await writer.drain()
        except Exception as e:
            logger.error("[VECTOR][mcp_stdio] loop error: {}", e)


def main():
    """Entry point for stdio MCP server."""
    # Disable loguru output to stdout to avoid mixing with JSON-RPC
    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    ensure_production_secret()  # fail closed in production without a stable secret
    asyncio.run(run_stdio())


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")
    # Smoke test: verify tool list works without stdin
    tools = _list_tools()
    print(f"[OK] mcp_stdio: {len(tools)} tools available")
    print(f"[OK] kernel_id: {KERNEL_ID}")
    req = {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}
    result = asyncio.run(_handle_request(req))
    print(f"[OK] ping: {result.get('result', {}).get('status')}")
    print("mcp_server_stdio.py OK")
