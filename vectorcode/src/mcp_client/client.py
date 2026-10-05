"""VectorCode MCP CLIENT — connects to external MCP servers via stdio.

Ports the MCP client side of VectorCode mcp_tool.py for VectorCode. The server
side already lives at core/mcp_server.py. This module gives VectorCode agents
the ability to discover and call tools exposed by external MCP servers
(filesystem, GitHub, Playwright, etc.).

Protocol: JSON-RPC 2.0 over stdin/stdout subprocess pipe.
Architecture: synchronous wrapper with a per-client background thread for
              reading server responses (no shared asyncio loop required).

Config (vector.toml):
    [[mcp_servers]]
    name    = "filesystem"
    command = "npx"
    args    = ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]

    [[mcp_servers]]
    name    = "github"
    command = "npx"
    args    = ["-y", "@modelcontextprotocol/server-github"]
    [mcp_servers.env]
    GITHUB_PERSONAL_ACCESS_TOKEN = "ghp_..."
"""

import sys
import json
import os
import re
import subprocess
import threading
import time
import uuid
from typing import Any, Dict, List, Optional


from loguru import logger

try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}

# ── Constants ─────────────────────────────────────────────────────────────────

_DEFAULT_TOOL_TIMEOUT = 30       # seconds per tool call
_DEFAULT_CONNECT_TIMEOUT = 15    # seconds for initial handshake
_JSON_RPC_VERSION = "2.0"

# Environment variables safe to pass to stdio subprocesses (security).
# User-specified env entries are always added on top.
_SAFE_ENV_KEYS = frozenset({
    "PATH", "HOME", "USER", "LANG", "LC_ALL", "TERM", "SHELL", "TMPDIR",
    "APPDATA", "LOCALAPPDATA", "PROGRAMFILES", "SYSTEMROOT", "TEMP", "TMP",
})

# Credential patterns — strip from error text before logging / returning to LLM
_CREDENTIAL_RE = re.compile(
    r"(?:ghp_[A-Za-z0-9_]{1,255}"
    r"|sk-[A-Za-z0-9_]{1,255}"
    r"|Bearer\s+\S+"
    r"|token=[^\s&,;\"']{1,255}"
    r"|key=[^\s&,;\"']{1,255}"
    r"|password=[^\s&,;\"']{1,255}"
    r"|secret=[^\s&,;\"']{1,255})",
    re.IGNORECASE,
)


def _sanitize_error(text: str) -> str:
    """Strip credential-like patterns from error strings."""
    return _CREDENTIAL_RE.sub("[REDACTED]", text)


def _build_safe_env(user_env: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Build a filtered env dict for stdio subprocesses.

    Only passes baseline safe vars plus any keys the caller explicitly
    provides. This prevents leaking API keys / session tokens to child
    processes spawned for MCP servers.
    """
    env: Dict[str, str] = {}
    for key, value in os.environ.items():
        if key in _SAFE_ENV_KEYS or key.startswith("XDG_"):
            env[key] = value
    if user_env:
        env.update(user_env)
    return env


def _make_request(method: str, params: Any, req_id: str) -> bytes:
    """Serialise a JSON-RPC 2.0 request as a newline-terminated bytes object."""
    payload = {
        "jsonrpc": _JSON_RPC_VERSION,
        "id": req_id,
        "method": method,
        "params": params,
    }
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode()


def _make_notification(method: str, params: Any) -> bytes:
    """Serialise a JSON-RPC 2.0 notification (no id) as a newline-terminated bytes object."""
    payload = {
        "jsonrpc": _JSON_RPC_VERSION,
        "method": method,
        "params": params,
    }
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode()


# ── StdioMCPClient ─────────────────────────────────────────────────────────────

class StdioMCPClient:
    """MCP client that talks to a server subprocess over stdin/stdout.

    Each instance owns exactly one subprocess. Calls are serialised through a
    threading.Lock so concurrent callers do not interleave writes, and
    responses are dispatched via a per-request Event + shared response dict.

    Gracefully handles the case where the server command is not installed
    (FileNotFoundError on start()) — all subsequent call_tool() calls return
    an error string rather than raising.
    """

    def __init__(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        tool_timeout: float = _DEFAULT_TOOL_TIMEOUT,
        connect_timeout: float = _DEFAULT_CONNECT_TIMEOUT,
    ) -> None:
        self.name = name
        self._command = command
        self._args: List[str] = args or []
        self._user_env = env
        self.tool_timeout = tool_timeout
        self.connect_timeout = connect_timeout

        self._proc: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._write_lock = threading.Lock()
        self._pending: Dict[str, threading.Event] = {}
        self._responses: Dict[str, Any] = {}
        self._tools: List[Dict[str, Any]] = []
        self._started = False
        self._error: Optional[str] = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Spawn the MCP server process and perform the initialize handshake.

        Returns True on success, False if the server could not be started
        (missing executable, handshake timeout, etc.).  Always safe to call
        even when the server program is not installed.
        """
        if self._started:
            return True

        safe_env = _build_safe_env(self._user_env)
        cmd = [self._command] + self._args

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=safe_env,
            )
        except FileNotFoundError as exc:
            self._error = (
                f"MCP server '{self.name}': command not found — {_sanitize_error(str(exc))}. "
                "Ensure the server package is installed."
            )
            logger.warning(f"[VECTOR][mcp] {self._error}")
            return False
        except Exception as exc:
            self._error = f"MCP server '{self.name}': failed to start — {_sanitize_error(str(exc))}"
            logger.error(f"[VECTOR][mcp] {self._error}")
            return False

        # Start background reader thread
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name=f"mcp-reader-{self.name}",
            daemon=True,
        )
        self._reader_thread.start()

        # JSON-RPC initialize handshake
        try:
            result = self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "vectorcode", "version": "1.0"},
                },
                timeout=self.connect_timeout,
            )
            if result is None:
                raise TimeoutError("initialize handshake timed out")
        except Exception as exc:
            self._error = (
                f"MCP server '{self.name}': handshake failed — "
                f"{_sanitize_error(str(exc))}"
            )
            logger.error(f"[VECTOR][mcp] {self._error}")
            self._terminate_proc()
            return False

        # Send initialized notification (no response expected)
        self._send_notification("notifications/initialized", {})

        self._started = True
        logger.info(f"[VECTOR][mcp] server '{self.name}' started OK")
        return True

    def stop(self) -> None:
        """Kill the subprocess and clean up resources."""
        self._started = False
        self._terminate_proc()
        logger.info(f"[VECTOR][mcp] server '{self.name}' stopped")

    def _terminate_proc(self) -> None:
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception as _sve:
                try:
                    self._proc.kill()
                except Exception as _sve:
                    logger.debug(
                        "[VECTOR][mcp_client.client] failed to kill subprocess: {}",
                        _sve,
                    )
            self._proc = None

    # ── I/O ──────────────────────────────────────────────────────────────────

    def _reader_loop(self) -> None:
        """Background thread: reads newline-delimited JSON from server stdout."""
        try:
            for raw in self._proc.stdout:
                try:
                    msg = json.loads(raw.decode("utf-8", errors="replace").strip())
                except json.JSONDecodeError:
                    continue

                req_id = str(msg.get("id", ""))
                if req_id and req_id in self._pending:
                    self._responses[req_id] = msg
                    self._pending[req_id].set()
        except Exception as exc:
            logger.debug(f"[VECTOR][mcp] reader loop '{self.name}' exited: {exc}")

    def _send_notification(self, method: str, params: Any) -> None:
        """Send a notification (fire-and-forget, no response expected)."""
        if self._proc is None or self._proc.stdin is None:
            return
        payload = _make_notification(method, params)
        try:
            with self._write_lock:
                self._proc.stdin.write(payload)
                self._proc.stdin.flush()
        except Exception as exc:
            logger.debug(f"[VECTOR][mcp] notification write failed: {exc}")

    def _send_request(
        self, method: str, params: Any, timeout: Optional[float] = None
    ) -> Optional[Any]:
        """Send a JSON-RPC request and block until response or timeout.

        Returns the parsed result dict on success, or raises on error/timeout.
        """
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError(f"MCP server '{self.name}' is not running")

        req_id = str(uuid.uuid4())
        event = threading.Event()
        self._pending[req_id] = event

        payload = _make_request(method, params, req_id)
        try:
            with self._write_lock:
                self._proc.stdin.write(payload)
                self._proc.stdin.flush()
        except Exception as exc:
            self._pending.pop(req_id, None)
            raise RuntimeError(
                f"MCP server '{self.name}': write failed — {_sanitize_error(str(exc))}"
            ) from exc

        wait_timeout = timeout if timeout is not None else self.tool_timeout
        if not event.wait(timeout=wait_timeout):
            self._pending.pop(req_id, None)
            raise TimeoutError(
                f"MCP server '{self.name}': request '{method}' timed out "
                f"after {wait_timeout}s"
            )

        self._pending.pop(req_id, None)
        response = self._responses.pop(req_id, None)
        if response is None:
            raise RuntimeError(f"MCP server '{self.name}': empty response for '{method}'")

        if "error" in response:
            err = response["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise RuntimeError(
                f"MCP server '{self.name}': RPC error — {_sanitize_error(msg)}"
            )

        return response.get("result")

    # ── Tool discovery ────────────────────────────────────────────────────────

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return tool descriptors from the server, cached after first call.

        Each descriptor: {name: str, description: str, inputSchema: dict}.
        Returns [] if the server is unavailable.
        """
        if not self._started:
            if self._error:
                logger.debug(f"[VECTOR][mcp] list_tools skipped: {self._error}")
            return []

        if self._tools:
            return self._tools

        try:
            result = self._send_request("tools/list", {}, timeout=self.tool_timeout)
            raw_tools = (result or {}).get("tools", []) if isinstance(result, dict) else []
            self._tools = [
                {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "inputSchema": t.get("inputSchema", {}),
                }
                for t in raw_tools
                if t.get("name")
            ]
            logger.info(
                f"[VECTOR][mcp] server '{self.name}': "
                f"discovered {len(self._tools)} tools"
            )
        except Exception as exc:
            logger.warning(
                f"[VECTOR][mcp] list_tools failed for '{self.name}': "
                f"{_sanitize_error(str(exc))}"
            )
            self._tools = []

        return self._tools

    # ── Tool execution ────────────────────────────────────────────────────────

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool on the MCP server and return the result as a string.

        Returns an error string (never raises) so the agent loop can surface
        the failure as a tool result rather than an unhandled exception.
        """
        if not self._started:
            msg = self._error or f"MCP server '{self.name}' is not running"
            logger.warning(f"[VECTOR][mcp] call_tool skipped: {msg}")
            return f"[MCP error] {_sanitize_error(msg)}"

        try:
            result = self._send_request(
                "tools/call",
                {"name": name, "arguments": arguments},
                timeout=self.tool_timeout,
            )
        except TimeoutError as exc:
            logger.error(f"[VECTOR][mcp] tool call timeout: {exc}")
            return f"[MCP timeout] {_sanitize_error(str(exc))}"
        except Exception as exc:
            logger.error(
                f"[VECTOR][mcp] tool call '{name}' on '{self.name}' failed: "
                f"{_sanitize_error(str(exc))}"
            )
            return f"[MCP error] {_sanitize_error(str(exc))}"

        # Flatten result to string
        if result is None:
            return ""
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            # MCP spec: result has 'content' list of {type, text} blocks
            content = result.get("content", [])
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text", "")
                        if text:
                            parts.append(str(text))
                if parts:
                    return "\n".join(parts)
            # isError flag
            if result.get("isError"):
                err_msg = str(content) if content else "unknown MCP error"
                return f"[MCP tool error] {_sanitize_error(err_msg)}"
            return json.dumps(result)
        return str(result)


# ── MCPClientRegistry ─────────────────────────────────────────────────────────

class MCPClientRegistry:
    """Registry of MCP server connections for VectorCode.

    Manages lifecycle (start/stop) of multiple StdioMCPClient instances and
    provides a unified tool namespace with '{server_name}__{tool_name}'
    prefixing to avoid collisions between servers.
    """

    def __init__(self) -> None:
        self._clients: Dict[str, StdioMCPClient] = {}
        self._lock = threading.Lock()

    def add_server(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        tool_timeout: float = _DEFAULT_TOOL_TIMEOUT,
        connect_timeout: float = _DEFAULT_CONNECT_TIMEOUT,
    ) -> None:
        """Register a single MCP server config. Does not start the server yet."""
        with self._lock:
            if name in self._clients:
                logger.debug(f"[VECTOR][mcp] registry: '{name}' already registered, skipping")
                return
            self._clients[name] = StdioMCPClient(
                name=name,
                command=command,
                args=args,
                env=env,
                tool_timeout=tool_timeout,
                connect_timeout=connect_timeout,
            )
        logger.debug(f"[VECTOR][mcp] registry: registered server '{name}'")

    def add_from_config(self, config_list: List[Dict[str, Any]]) -> None:
        """Bulk-register servers from a list of config dicts.

        Each dict must have 'name' and 'command'. Optional: 'args', 'env',
        'timeout' (tool_timeout), 'connect_timeout'.

        Typical source: vector.toml [[mcp_servers]] table.
        """
        for entry in config_list:
            name = entry.get("name", "").strip()
            command = entry.get("command", "").strip()
            if not name or not command:
                logger.warning(
                    f"[VECTOR][mcp] add_from_config: skipping entry missing "
                    f"'name' or 'command': {entry}"
                )
                continue
            self.add_server(
                name=name,
                command=command,
                args=entry.get("args"),
                env=entry.get("env"),
                tool_timeout=float(entry.get("timeout", _DEFAULT_TOOL_TIMEOUT)),
                connect_timeout=float(
                    entry.get("connect_timeout", _DEFAULT_CONNECT_TIMEOUT)
                ),
            )

    def start_all(self) -> Dict[str, bool]:
        """Start all registered servers. Returns {name: success} map."""
        results: Dict[str, bool] = {}
        with self._lock:
            clients = dict(self._clients)

        for name, client in clients.items():
            try:
                ok = client.start()
                results[name] = ok
            except Exception as exc:
                logger.error(
                    f"[VECTOR][mcp] start_all: exception for '{name}': "
                    f"{_sanitize_error(str(exc))}"
                )
                results[name] = False

        started = sum(1 for v in results.values() if v)
        logger.info(
            f"[VECTOR][mcp] start_all: {started}/{len(results)} servers started"
        )
        return results

    def stop_all(self) -> None:
        """Stop all running servers."""
        with self._lock:
            clients = dict(self._clients)

        for name, client in clients.items():
            try:
                client.stop()
            except Exception as exc:
                logger.debug(f"[VECTOR][mcp] stop_all: error stopping '{name}': {exc}")

        logger.info("[VECTOR][mcp] stop_all: all servers stopped")

    def get_all_tools(self) -> List[Dict[str, Any]]:
        """Return all tools from all started servers with prefixed names.

        Format: [{name: '{server}__{tool}', description: str, server_name: str}]
        """
        all_tools: List[Dict[str, Any]] = []
        with self._lock:
            clients = dict(self._clients)

        for server_name, client in clients.items():
            for tool in client.list_tools():
                all_tools.append({
                    "name": f"{server_name}__{tool['name']}",
                    "description": tool.get("description", ""),
                    "inputSchema": tool.get("inputSchema", {}),
                    "server_name": server_name,
                    "_original_name": tool["name"],
                })
        return all_tools

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool by its prefixed name ('{server}__{tool}').

        Also accepts bare tool names when unambiguous across all servers.
        Returns an error string if routing fails.
        """
        # Try prefix routing first: 'server__tool'
        if "__" in tool_name:
            server_name, bare_name = tool_name.split("__", 1)
            with self._lock:
                client = self._clients.get(server_name)
            if client is None:
                return f"[MCP error] unknown server '{server_name}'"
            return client.call_tool(bare_name, arguments)

        # Bare name: search all servers for a unique match
        matches: List[tuple[str, StdioMCPClient]] = []
        with self._lock:
            clients = dict(self._clients)

        for server_name, client in clients.items():
            for tool in client.list_tools():
                if tool["name"] == tool_name:
                    matches.append((tool_name, client))
                    break

        if not matches:
            return f"[MCP error] tool '{tool_name}' not found in any server"
        if len(matches) > 1:
            server_names = [m[1].name for m in matches]
            return (
                f"[MCP error] tool '{tool_name}' is ambiguous — "
                f"found in: {server_names}. Use '{server_names[0]}__{tool_name}' syntax."
            )
        _, client = matches[0]
        return client.call_tool(tool_name, arguments)

    def get_client(self, server_name: str) -> Optional[StdioMCPClient]:
        """Return the client for a named server, or None."""
        with self._lock:
            return self._clients.get(server_name)


# ── Singleton ─────────────────────────────────────────────────────────────────

_registry_instance: Optional[MCPClientRegistry] = None
_registry_lock = threading.Lock()


def get_mcp_registry() -> MCPClientRegistry:
    """Return the process-wide MCPClientRegistry singleton.

    On first call, attempts to auto-configure from vector.toml [[mcp_servers]]
    if available. The registry is NOT automatically started — call start_all()
    when ready (typically at agent startup).
    """
    global _registry_instance
    with _registry_lock:
        if _registry_instance is None:
            _registry_instance = MCPClientRegistry()
            _auto_configure_from_config(_registry_instance)
    return _registry_instance


def _auto_configure_from_config(registry: MCPClientRegistry) -> None:
    """Load [[mcp_servers]] from vector.toml into the registry if present."""
    try:
        # CONFIG from core.config may have mcp_servers list
        mcp_servers = CONFIG.get("mcp_servers", [])
        if mcp_servers and isinstance(mcp_servers, list):
            registry.add_from_config(mcp_servers)
            logger.debug(
                f"[VECTOR][mcp] auto-configured {len(mcp_servers)} "
                "servers from CONFIG['mcp_servers']"
            )
    except Exception as exc:
        logger.debug(f"[VECTOR][mcp] auto-configure skipped: {exc}")


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    # Test 1: Registry instantiation
    reg = get_mcp_registry()
    assert isinstance(reg, MCPClientRegistry), "get_mcp_registry() must return MCPClientRegistry"

    # Test 2: add_server / get_client
    reg.add_server(
        name="test_nonexistent",
        command="this_command_does_not_exist_12345",
        args=[],
    )
    client = reg.get_client("test_nonexistent")
    assert client is not None, "get_client should return registered client"

    # Test 3: start fails gracefully when binary missing
    ok = client.start()
    assert ok is False, "start() must return False for missing command"
    assert client._error is not None, "error should be recorded"

    # Test 4: call_tool returns error string (not raises)
    result = client.call_tool("some_tool", {"arg": "value"})
    assert "[MCP" in result, f"Expected MCP error string, got: {result!r}"

    # Test 5: list_tools returns [] when not started
    tools = client.list_tools()
    assert tools == [], f"Expected [], got {tools}"

    # Test 6: get_all_tools returns list
    all_tools = reg.get_all_tools()
    assert isinstance(all_tools, list), "get_all_tools must return list"

    # Test 7: call_tool with unknown server prefix
    result = reg.call_tool("unknown_server__some_tool", {})
    assert "[MCP error]" in result, f"Expected routing error, got: {result!r}"

    print("OK")
