# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""MCP transport implementations."""

from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import socket
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, List, Mapping, Optional
from urllib.parse import urljoin, urlparse, urlunparse

from pydantic import SecretStr

from vectorcode.src.vc_mcp.protocol import MCPRequest, MCPResponse
from vectorcode.src.vc_security.ssrf import check_ssrf, is_private_ip

if TYPE_CHECKING:
    from vectorcode.src.vc_mcp.server import MCPServer

class MCPTransport(ABC):
    """Abstract transport layer for MCP communication."""

    @abstractmethod
    def send(self, request: MCPRequest) -> MCPResponse:
        """Send a request and return the response."""

    def send_notification(self, request: MCPRequest) -> None:
        """Send a JSON-RPC notification (no response expected).

        The default implementation delegates to :meth:`send` and discards the
        response.  Transports may override this when the server returns no
        body for notifications (e.g. HTTP 202 Accepted).
        """
        self.send(request)

    @abstractmethod
    def close(self) -> None:
        """Release transport resources."""

class InProcessTransport(MCPTransport):
    """Direct in-process transport for testing.

    Routes requests directly to an ``MCPServer`` instance without
    serialization overhead.
    """

    def __init__(self, server: MCPServer) -> None:
        self._server = server

    def send(self, request: MCPRequest) -> MCPResponse:
        """Dispatch request directly to the server."""
        response = self._server.handle(request)
        if response is None:
            raise RuntimeError("JSON-RPC notifications do not have responses")
        return response

    def send_notification(self, request: MCPRequest) -> None:
        """Dispatch a notification without manufacturing a response."""
        self._server.handle(request)

    def close(self) -> None:
        """No resources to release."""

class StdioTransport(MCPTransport):
    """JSON-RPC over stdin/stdout subprocess transport.

    Launches a subprocess and communicates via JSON lines on
    stdin/stdout.
    """

    def __init__(
        self,
        command: List[str],
        *,
        request_timeout: float = 60.0,
        max_response_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        self._command = command
        self._request_timeout = request_timeout
        self._max_response_bytes = max_response_bytes
        loop_factory = getattr(asyncio, "ProactorEventLoop", None)
        self._runner = asyncio.Runner(loop_factory=loop_factory)
        self._process: Optional[asyncio.subprocess.Process] = None
        self._stderr_task: Optional[asyncio.Task[None]] = None
        self._runner.run(self._start())

    async def _start(self) -> None:
        """Start the subprocess."""
        self._process = await asyncio.create_subprocess_exec(
            *self._command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=self._max_response_bytes + 1,
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())

    async def _drain_stderr(self) -> None:
        """Continuously drain child stderr so its pipe cannot deadlock."""
        proc = self._process
        if proc is None or proc.stderr is None:
            return
        while await proc.stderr.read(64 * 1024):
            pass

    async def _send(self, request: MCPRequest) -> MCPResponse:
        proc = self._process
        if proc is None or proc.stdin is None or proc.stdout is None:
            raise RuntimeError("Transport process is not running")
        if proc.returncode is not None:
            raise RuntimeError("Transport subprocess has exited")

        proc.stdin.write((request.to_json() + "\n").encode("utf-8"))
        try:
            await asyncio.wait_for(proc.stdin.drain(), timeout=self._request_timeout)
            response_line = await asyncio.wait_for(
                proc.stdout.readline(), timeout=self._request_timeout
            )
        except TimeoutError as exc:
            await self._close()
            raise TimeoutError(
                f"MCP subprocess did not respond within {self._request_timeout:g} seconds"
            ) from exc
        except ValueError as exc:
            raise RuntimeError(
                f"MCP subprocess response exceeded {self._max_response_bytes} bytes"
            ) from exc

        if not response_line:
            raise RuntimeError("No response from subprocess")
        if len(response_line) > self._max_response_bytes:
            raise RuntimeError(
                f"MCP subprocess response exceeded {self._max_response_bytes} bytes"
            )
        return MCPResponse.from_json(response_line.decode("utf-8").strip())

    def send(self, request: MCPRequest) -> MCPResponse:
        """Write request as JSON line, read response line."""
        return self._runner.run(self._send(request))

    async def _send_notification(self, request: MCPRequest) -> None:
        proc = self._process
        if proc is None or proc.stdin is None or proc.returncode is not None:
            raise RuntimeError("Transport process is not running")
        proc.stdin.write((request.to_json() + "\n").encode("utf-8"))
        try:
            await asyncio.wait_for(proc.stdin.drain(), timeout=self._request_timeout)
        except TimeoutError as exc:
            await self._close()
            raise TimeoutError(
                f"MCP subprocess write timed out after {self._request_timeout:g} seconds"
            ) from exc

    def send_notification(self, request: MCPRequest) -> None:
        """Write a notification without waiting for a forbidden response."""
        self._runner.run(self._send_notification(request))

    async def _close(self) -> None:
        proc = self._process
        self._process = None
        if proc is not None and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except TimeoutError:
                proc.kill()
                await asyncio.wait_for(proc.wait(), timeout=5)
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            await asyncio.gather(self._stderr_task, return_exceptions=True)
            self._stderr_task = None

    def close(self) -> None:
        """Terminate the subprocess, force-killing it if it won't exit."""
        runner = getattr(self, "_runner", None)
        if runner is None:
            return
        try:
            runner.run(self._close())
        finally:
            runner.close()
            self._runner = None

class StreamableHTTPTransport(MCPTransport):
    """MCP Streamable HTTP transport (JSON-RPC over HTTP).

    Uses a persistent ``httpx.Client`` session, tracks the
    ``Mcp-Session-Id`` header, and sends the ``Accept`` header
    required by the MCP Streamable HTTP specification.
    """

    def __init__(
        self,
        url: str,
        *,
        connect_timeout: float = 10.0,
        request_timeout: float = 60.0,
        bearer_token: SecretStr | str | None = None,
        max_redirects: int = 5,
    ) -> None:
        import httpx

        self._url = url
        self._session_id: Optional[str] = None
        self._bearer_token = (
            bearer_token
            if isinstance(bearer_token, SecretStr)
            else SecretStr(bearer_token or "")
        )
        self._max_redirects = max_redirects
        self._client = httpx.Client(
            timeout=httpx.Timeout(
                connect=connect_timeout,
                read=request_timeout,
                write=request_timeout,
                pool=connect_timeout,
            ),
            follow_redirects=False,
            trust_env=False,
        )

    def _safe_url(self) -> str:
        """Return scheme://host:port without path or query (avoids leaking tokens)."""
        parsed = urlparse(self._url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _build_headers(self) -> dict:
        """Build common request headers."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id is not None:
            headers["Mcp-Session-Id"] = self._session_id
        token = self._bearer_token.get_secret_value()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _origin(url: str) -> tuple[str, str, int | None]:
        parsed = urlparse(url)
        return parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port

    @staticmethod
    def _pin_destination(url: str) -> tuple[str, str, str]:
        """Resolve once, validate every address, and return an IP-pinned URL."""
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise RuntimeError("MCP endpoint must use HTTP or HTTPS with a hostname")
        if parsed.username is not None or parsed.password is not None:
            raise RuntimeError("MCP endpoint URLs must not contain credentials")

        hostname = parsed.hostname
        try:
            literal = ipaddress.ip_address(hostname)
            addresses = [str(literal)]
        except ValueError:
            try:
                addresses = list(
                    dict.fromkeys(
                        item[4][0]
                        for item in socket.getaddrinfo(
                            hostname, parsed.port, socket.AF_UNSPEC, socket.SOCK_STREAM
                        )
                    )
                )
            except socket.gaierror as exc:
                raise RuntimeError("MCP endpoint hostname could not be resolved safely") from exc
        if not addresses or any(is_private_ip(address) for address in addresses):
            raise RuntimeError("MCP endpoint resolved to a private or reserved address")

        selected = addresses[0]
        pinned_host = f"[{selected}]" if ":" in selected else selected
        netloc = pinned_host if parsed.port is None else f"{pinned_host}:{parsed.port}"
        pinned_url = urlunparse(parsed._replace(netloc=netloc))
        host_header = hostname if parsed.port is None else f"{hostname}:{parsed.port}"
        return pinned_url, host_header, hostname

    @staticmethod
    def bearer_token_from_config(config: Mapping[str, Any]) -> SecretStr | None:
        """Resolve a bearer token from an environment-backed MCP config.

        Supports ``bearer_token_env`` and the existing VectorCode MCP format
        ``headers.Authorization = \"Bearer ${ENV_VAR}\"``. Secret values are
        never read from or persisted in the ordinary config mapping.
        """
        env_name = config.get("bearer_token_env")
        if env_name is None:
            headers = config.get("headers")
            authorization = headers.get("Authorization") if isinstance(headers, Mapping) else None
            if isinstance(authorization, str):
                match = re.fullmatch(r"Bearer\s+\$\{([A-Za-z_][A-Za-z0-9_]*)\}", authorization)
                if match:
                    env_name = match.group(1)
        if env_name is None:
            return None
        if not isinstance(env_name, str) or not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*", env_name
        ):
            raise ValueError("MCP bearer_token_env must be a valid environment variable name")
        token = os.environ.get(env_name, "").strip()
        if not token:
            raise RuntimeError(f"MCP bearer token environment variable {env_name!r} is not set")
        return SecretStr(token)

    def _post(self, request: MCPRequest) -> Any:
        """Post a request and return the raw httpx response."""
        import httpx

        headers = self._build_headers()
        current_url = self._url
        try:
            for redirect_count in range(self._max_redirects + 1):
                ssrf_error = check_ssrf(current_url)
                if ssrf_error is not None:
                    raise RuntimeError(f"Blocked unsafe MCP endpoint: {ssrf_error}")
                pinned_url, host_header, sni_hostname = self._pin_destination(current_url)
                request_headers = {**headers, "Host": host_header}
                response = self._client.post(
                    pinned_url,
                    json=request.to_dict(),
                    headers=request_headers,
                    follow_redirects=False,
                    extensions={"sni_hostname": sni_hostname},
                )
                if response.status_code not in {301, 302, 303, 307, 308}:
                    break
                location = response.headers.get("location")
                if not location:
                    raise RuntimeError("MCP server returned a redirect without a Location header")
                if redirect_count >= self._max_redirects:
                    raise RuntimeError("MCP server exceeded the redirect limit")
                next_url = urljoin(current_url, location)
                if self._origin(next_url) != self._origin(current_url):
                    raise RuntimeError("MCP server attempted a cross-origin redirect")
                current_url = next_url
            response.raise_for_status()
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Failed to connect to MCP server at {self._safe_url()}: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"Timeout communicating with MCP server at {self._safe_url()}: {exc}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"MCP server at {self._safe_url()} returned HTTP "
                f"{exc.response.status_code}"
            ) from exc

        # Track session id from the first response
        new_session_id = response.headers.get("mcp-session-id")
        if new_session_id is not None:
            self._session_id = new_session_id
        return response

    @staticmethod
    def _extract_json_from_sse(text: str) -> str:
        """Extract JSON payload from an SSE response body.

        MCP Streamable HTTP servers may respond with ``text/event-stream``
        instead of ``application/json``.  In that case the body looks like::

            event: message
            data: {"jsonrpc":"2.0", ...}

        This helper finds the last ``data:`` line and returns its content,
        which is the actual JSON-RPC response.
        """
        last_data = ""
        for line in text.splitlines():
            if line.startswith("data:"):
                last_data = line[len("data:") :].strip()
        if not last_data:
            raise RuntimeError(
                "SSE response contained no 'data:' lines"
                " — cannot extract JSON-RPC payload"
            )
        return last_data

    def send(self, request: MCPRequest) -> MCPResponse:
        """Send request via HTTP POST following the MCP Streamable HTTP spec.

        Handles both ``application/json`` and ``text/event-stream`` responses
        as allowed by the MCP Streamable HTTP specification.
        """
        response = self._post(request)
        content_type = response.headers.get("content-type", "")
        body = response.text
        if "text/event-stream" in content_type or body.lstrip().startswith("event:"):
            body = self._extract_json_from_sse(body)
        return MCPResponse.from_json(body)

    def send_notification(self, request: MCPRequest) -> None:
        """Send a notification — accept any 2xx, don't parse the body."""
        # Track session id but don't try to parse a JSON-RPC response.
        # Servers may return 202 Accepted with an empty body.
        self._post(request)

    def close(self) -> None:
        """Close the underlying httpx client."""
        self._client.close()

# Backward-compatible alias
SSETransport = StreamableHTTPTransport

__all__ = [
    "InProcessTransport",
    "MCPTransport",
    "SSETransport",
    "StdioTransport",
    "StreamableHTTPTransport",
]
