"""
VECTOR MCP Client — Outbound MCP Consumer
Python port of UI-TARS-desktop/packages/agent-infra/mcp-client/src/index.ts

Allows VECTOR to CONNECT TO and USE external MCP servers.

NOTE: VECTOR's core/mcp_server.py is an MCP SERVER (exposes VECTOR's tools to
Claude Desktop). This is the opposite: an MCP CLIENT that lets VECTOR consume
tools from OTHER MCP servers (Claude Desktop plugins, community servers, etc.)

Transports:
  stdio — launch a local MCP server process (e.g. npx @modelcontextprotocol/server-filesystem)
  http  — connect to a remote MCP server via HTTP/SSE

Usage:
    client = MCPClient([
        {"name": "filesystem", "transport": "stdio",
         "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]},
        {"name": "my-server", "transport": "http",
         "url": "http://localhost:3001/mcp"},
    ])
    asyncio.run(client.connect())
    tools = asyncio.run(client.list_tools())
    result = asyncio.run(client.call_tool("filesystem/read_file", {"path": "/tmp/test.txt"}))
"""
from __future__ import annotations

__all__ = [
    "HttpTransport",
    "MCPClient",
    "StdioTransport",
]


import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from typing import Optional

from loguru import logger


# â”€â”€ MCP JSON-RPC protocol helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _make_request(method: str, params: dict | None = None, req_id: int = 1) -> str:
    msg: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg) + "\n"


def _parse_response(line: str) -> dict:
    return json.loads(line.strip())


# â”€â”€ Stdio transport â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class StdioTransport:
    """Launches a local MCP server subprocess and communicates over stdin/stdout."""

    def __init__(self, command: str, args: list[str], env: dict | None = None, cwd: str | None = None) -> None:
        self._cmd  = command
        self._args = args
        self._env  = {**os.environ, **(env or {})}
        self._cwd  = cwd
        self._proc: subprocess.Popen | None = None
        self._req_id = 0
        self._lock = threading.Lock()

    def connect(self) -> None:
        cmd = self._cmd
        # Windows: npx → npx.cmd
        if sys.platform == "win32" and self._cmd in ("npx", "node"):
            cmd = self._cmd + (".cmd" if self._cmd == "npx" else ".exe")
        self._proc = subprocess.Popen(
            [cmd] + self._args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._env,
            cwd=self._cwd,
            text=True,
            bufsize=1,
        )
        logger.debug("[VECTOR][mcp_client] stdio started: {} {}", cmd, self._args[:2])

    def disconnect(self) -> None:
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except Exception:
                self._proc.kill()
            self._proc = None

    def send(self, method: str, params: dict | None = None) -> dict:
        if not self._proc:
            raise RuntimeError("Not connected")
        with self._lock:
            self._req_id += 1
            msg = _make_request(method, params, self._req_id)
            self._proc.stdin.write(msg)  # type: ignore[union-attr]
            self._proc.stdin.flush()  # type: ignore[union-attr]
            # Read response line
            for _ in range(30):  # 3s timeout
                line = self._proc.stdout.readline()  # type: ignore[union-attr]
                if line.strip():
                    return _parse_response(line)
                time.sleep(0.1)
            raise TimeoutError(f"MCP server did not respond to {method}")


# â”€â”€ HTTP transport â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class HttpTransport:
    """Connects to a remote MCP server over HTTP."""

    def __init__(self, url: str, headers: dict | None = None) -> None:
        self._url     = url.rstrip("/")
        self._headers = {"Content-Type": "application/json", **(headers or {})}
        self._req_id  = 0

    def connect(self) -> None:
        logger.debug("[VECTOR][mcp_client] http transport → {}", self._url)

    def disconnect(self) -> None:
        logger.debug("[VECTOR][mcp_client] http transport disconnected → {}", self._url)

    def send(self, method: str, params: dict | None = None) -> dict:
        import urllib.request
        self._req_id += 1
        body = _make_request(method, params, self._req_id).encode()
        req = urllib.request.Request(
            self._url,
            data=body,
            headers=self._headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())


# â”€â”€ MCP Client â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class MCPClient:
    """
    VECTOR's outbound MCP client — connects to external MCP servers and calls their tools.

    Server config dicts:
      Stdio: {"name": str, "transport": "stdio", "command": str, "args": list,
               "env": dict, "cwd": str}
      HTTP:  {"name": str, "transport": "http",  "url": str, "headers": dict}
    """

    def __init__(
        self,
        servers: list[dict],
        debug: bool = False,
        default_timeout: int = 60,
    ) -> None:
        self._servers   = servers
        self._debug     = debug
        self._timeout   = default_timeout
        self._transports: dict[str, StdioTransport | HttpTransport] = {}
        self._tools_cache: dict[str, list[dict]] = {}  # server_name → tools
        self._connected  = False

    async def connect(self) -> None:
        """Connect to all configured MCP servers."""
        loop = asyncio.get_event_loop()
        for srv in self._servers:
            name = srv.get("name", "unknown")
            transport_type = srv.get("transport", "stdio")
            try:
                if transport_type == "stdio":
                    t = StdioTransport(
                        command=srv.get("command", "npx"),
                        args=srv.get("args", []),
                        env=srv.get("env"),
                        cwd=srv.get("cwd"),
                    )
                    await loop.run_in_executor(None, t.connect)
                    # Initialize MCP protocol
                    await loop.run_in_executor(None, t.send, "initialize", {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "VECTOR", "version": "1.0.0"},
                    })
                    await loop.run_in_executor(None, t.send, "notifications/initialized", None)
                    self._transports[name] = t
                    logger.info("[VECTOR][mcp_client] connected to {} (stdio)", name)

                elif transport_type in ("http", "sse", "streamable-http"):
                    t = HttpTransport(url=srv["url"], headers=srv.get("headers"))
                    await loop.run_in_executor(None, t.connect)
                    self._transports[name] = t
                    logger.info("[VECTOR][mcp_client] connected to {} (http)", name)

            except Exception as e:
                logger.warning("[VECTOR][mcp_client] failed to connect to {}: {}", name, e)

        self._connected = True

    async def disconnect(self) -> None:
        """Disconnect from all MCP servers."""
        loop = asyncio.get_event_loop()
        for name, transport in self._transports.items():
            try:
                await loop.run_in_executor(None, transport.disconnect)
                logger.debug("[VECTOR][mcp_client] disconnected from {}", name)
            except Exception as e:
                logger.warning("[VECTOR][mcp_client] disconnect from {} failed: {}", name, e)
        self._transports.clear()
        self._tools_cache.clear()
        self._connected = False

    async def list_tools(self, server_name: str | None = None) -> list[dict]:
        """List all tools from all servers (or a specific server)."""
        loop = asyncio.get_event_loop()
        all_tools: list[dict] = []
        targets = {server_name: self._transports[server_name]} if server_name and server_name in self._transports else self._transports

        for name, transport in targets.items():
            if name in self._tools_cache:
                all_tools.extend(self._tools_cache[name])
                continue
            try:
                resp = await loop.run_in_executor(None, transport.send, "tools/list", None)
                tools = (resp.get("result") or {}).get("tools", [])
                # Tag each tool with server name
                tagged = [{"name": f"{name}/{t['name']}", "server": name,
                           "description": t.get("description", ""),
                           "inputSchema": t.get("inputSchema", {})} for t in tools]
                self._tools_cache[name] = tagged
                all_tools.extend(tagged)
                if self._debug:
                    logger.debug("[VECTOR][mcp_client] {} tools from {}", len(tagged), name)
            except Exception as e:
                logger.warning("[VECTOR][mcp_client] list_tools {} failed: {}", name, e)

        return all_tools

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """
        Call a tool on an MCP server.
        tool_name format: "server_name/tool_name" or just "tool_name" (searches all servers).
        """
        loop = asyncio.get_event_loop()

        # Resolve server
        if "/" in tool_name:
            server_name, actual_tool = tool_name.split("/", 1)
        else:
            # Search all servers' tool lists
            server_name = None
            actual_tool = tool_name
            tools = await self.list_tools()
            for t in tools:
                if t["name"].endswith(f"/{tool_name}") or t["name"] == tool_name:
                    server_name, actual_tool = t["name"].split("/", 1)
                    break

        if not server_name or server_name not in self._transports:
            raise ValueError(f"Tool not found or server not connected: {tool_name}")

        transport = self._transports[server_name]
        try:
            resp = await loop.run_in_executor(
                None, transport.send, "tools/call",
                {"name": actual_tool, "arguments": arguments}
            )
            result = resp.get("result") or {}
            if resp.get("error"):
                raise RuntimeError(f"MCP error: {resp['error']}")
            logger.debug("[VECTOR][mcp_client] called {}/{}: OK", server_name, actual_tool)
            return result
        except Exception as e:
            logger.error("[VECTOR][mcp_client] call_tool {}/{} failed: {}", server_name, actual_tool, e)
            raise

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *_):
        await self.disconnect()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        # Init with no servers — should not crash
        client = MCPClient(servers=[], debug=True)
        assert not client._connected
        await client.connect()
        assert client._connected
        tools = await client.list_tools()
        assert isinstance(tools, list)
        await client.disconnect()
        print("OK mcp/client.py — MCPClient init, connect/disconnect, list_tools OK")
        print(f"  transports={len(client._transports)} tools={len(tools)}")
        print(f"  Use: MCPClient([{{name: 'fs', transport: 'stdio', command: 'npx', args: [...]}}])")

    asyncio.run(_smoke())
