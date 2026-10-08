# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""MCP Server — wraps VectorCode tools as MCP-discoverable tools."""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from core.runtime_paths import get_data_root, get_project_root
from vectorcode.src.vc_core.types import ToolCall
from vectorcode.src.vc_mcp.protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    MCPRequest,
    MCPResponse,
)
from vectorcode.src.vc_tools._abc import BaseTool, ToolExecutor
from vectorcode.src.vc_tools.apply_patch import ApplyPatchTool
from vectorcode.src.vc_tools.file_read import FileReadTool
from vectorcode.src.vc_tools.file_write import FileWriteTool

# Tool annotation hints per MCP spec 2025-11-25
_TOOL_ANNOTATIONS: Dict[str, Dict[str, Any]] = {
    "memory_store": {"destructiveHint": True, "readOnlyHint": False},
    "memory_retrieve": {"readOnlyHint": True, "destructiveHint": False},
    "memory_search": {"readOnlyHint": True, "destructiveHint": False},
    "memory_index": {"destructiveHint": True, "readOnlyHint": False},
    "calculator": {"readOnlyHint": True, "destructiveHint": False},
    "think": {"readOnlyHint": True, "destructiveHint": False},
    "retrieval": {"readOnlyHint": True, "destructiveHint": False},
    "llm": {"readOnlyHint": False, "destructiveHint": False},
    "file_read": {"readOnlyHint": True, "destructiveHint": False},
    "web_search": {"readOnlyHint": True, "destructiveHint": False},
    "code_interpreter": {"destructiveHint": True, "readOnlyHint": False},
    "repl": {"destructiveHint": True, "readOnlyHint": False},
    "channel_send": {"destructiveHint": True, "readOnlyHint": False},
    "channel_list": {"readOnlyHint": True, "destructiveHint": False},
    "channel_status": {"readOnlyHint": True, "destructiveHint": False},
}


def _inject_file_tool_allowed_dirs(tool: BaseTool) -> BaseTool:
    """Confine production file tools without changing generic constructors."""
    if isinstance(tool, (ApplyPatchTool, FileReadTool, FileWriteTool)):
        tool._allowed_dirs = [
            get_project_root().resolve(),
            get_data_root().resolve(),
        ]
    return tool


class MCPServer:
    """MCP server that exposes VectorCode tools via JSON-RPC.

    Parameters
    ----------
    tools:
        List of ``BaseTool`` instances to expose.  If ``None``, auto-discovers
        all registered tools from ``ToolRegistry``.
    """

    SERVER_NAME = "vector"
    SERVER_VERSION = "0.1.0"
    PROTOCOL_VERSION = "2025-11-25"

    def __init__(
        self,
        tools: Optional[List[BaseTool]] = None,
        *,
        capability_policy: Any = None,
        boundary_guard: Any = None,
        authorize_action: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
        agent_id: str = "mcp-unauthenticated",
    ) -> None:
        if tools is None:
            tools = self._auto_discover_tools()
        if capability_policy is None:
            from vectorcode.src.vc_security.capabilities import CapabilityPolicy

            capability_policy = CapabilityPolicy(default_deny=True)
        if boundary_guard is None:
            from vectorcode.src.vc_security.boundary import BoundaryGuard
            from vectorcode.src.vc_security.scanner import PIIScanner, SecretScanner

            boundary_guard = BoundaryGuard(
                mode="block", scanners=[SecretScanner(), PIIScanner()]
            )
        self._tools: Dict[str, BaseTool] = {t.spec.name: t for t in tools}
        self._authorize_action = authorize_action
        self._agent_id = agent_id
        self._executor = ToolExecutor(
            tools,
            capability_policy=capability_policy,
            agent_id=agent_id,
            boundary_guard=boundary_guard,
        )

    @staticmethod
    def _auto_discover_tools() -> List[BaseTool]:
        """Auto-discover all built-in tools by direct import.

        Does not rely on ToolRegistry state — imports each tool class
        directly and attempts instantiation with no arguments.
        """
        tools: List[BaseTool] = []
        _tool_classes: List[type] = []

        # Built-in API tools
        try:
            from vectorcode.src.vc_tools.calculator import CalculatorTool

            _tool_classes.append(CalculatorTool)
        except ImportError:
            logger.opt(exception=True).debug("[VECTOR] suppressed exception")
        try:
            from vectorcode.src.vc_tools.think import ThinkTool

            _tool_classes.append(ThinkTool)
        except ImportError:
            logger.opt(exception=True).debug("[VECTOR] suppressed exception")
        try:
            from vectorcode.src.vc_tools.file_read import FileReadTool

            _tool_classes.append(FileReadTool)
        except ImportError:
            logger.opt(exception=True).debug("[VECTOR] suppressed exception")
        try:
            from vectorcode.src.vc_tools.web_search import WebSearchTool

            _tool_classes.append(WebSearchTool)
        except ImportError:
            logger.opt(exception=True).debug("[VECTOR] suppressed exception")
        try:
            from vectorcode.src.vc_tools.code_interpreter import CodeInterpreterTool

            _tool_classes.append(CodeInterpreterTool)
        except ImportError:
            logger.opt(exception=True).debug("[VECTOR] suppressed exception")
        try:
            from vectorcode.src.vc_tools.repl import ReplTool

            _tool_classes.append(ReplTool)
        except ImportError:
            logger.opt(exception=True).debug("[VECTOR] suppressed exception")

        # Storage MCP tools
        try:
            from vectorcode.src.vc_tools.storage_tools import (
                MemoryIndexTool,
                MemoryRetrieveTool,
                MemorySearchTool,
                MemoryStoreTool,
            )

            _tool_classes.extend(
                [
                    MemoryStoreTool,
                    MemoryRetrieveTool,
                    MemorySearchTool,
                    MemoryIndexTool,
                ]
            )
        except ImportError:
            logger.opt(exception=True).debug("[VECTOR] suppressed exception")

        # Channel MCP tools
        try:
            from vectorcode.src.vc_tools.channel_tools import (
                ChannelListTool,
                ChannelSendTool,
                ChannelStatusTool,
            )

            _tool_classes.extend(
                [
                    ChannelSendTool,
                    ChannelListTool,
                    ChannelStatusTool,
                ]
            )
        except ImportError:
            logger.opt(exception=True).debug("[VECTOR] suppressed exception")

        # LM tool (needs engine/model — instantiate with None)
        try:
            from vectorcode.src.vc_tools.llm_tool import LLMTool

            _tool_classes.append(LLMTool)
        except ImportError:
            logger.opt(exception=True).debug("[VECTOR] suppressed exception")

        # Retrieval tool (needs backend — instantiate with None)
        try:
            from vectorcode.src.vc_tools.retrieval import RetrievalTool

            _tool_classes.append(RetrievalTool)
        except ImportError:
            logger.opt(exception=True).debug("[VECTOR] suppressed exception")

        for cls in _tool_classes:
            try:
                tool = cls()
                if isinstance(tool, BaseTool):
                    tools.append(_inject_file_tool_allowed_dirs(tool))
            except Exception as exc:
                logger.warning("Failed to instantiate tool from {!r}: {}", cls, exc)

        # Also check ToolRegistry for any user-registered tools
        try:
            from vectorcode.src.vc_core.registry import ToolRegistry

            known_names = {t.spec.name for t in tools}
            for key in ToolRegistry.keys():
                if key not in known_names:
                    try:
                        tool = ToolRegistry.create(key)
                        if isinstance(tool, BaseTool):
                            tools.append(_inject_file_tool_allowed_dirs(tool))
                    except Exception as exc:
                        logger.warning("Failed to register user tool: {}", exc)
        except Exception as exc:
            logger.warning("Failed to discover tools from registry: {}", exc)

        return tools

    def get_tools(self) -> List[BaseTool]:
        """Return all tool instances (for use by SystemBuilder)."""
        return list(self._tools.values())

    def handle(self, request: MCPRequest) -> Optional[MCPResponse]:
        """Dispatch an MCP request and return a response."""
        if request.id is None:
            self._handle_notification(request)
            return None
        if request.method == "initialize":
            return self._handle_initialize(request)
        elif request.method == "tools/list":
            return self._handle_tools_list(request)
        elif request.method == "tools/call":
            return self._handle_tools_call(request)
        else:
            return MCPResponse.error_response(
                request.id,
                METHOD_NOT_FOUND,
                f"Unknown method: {request.method}",
            )

    def _handle_notification(self, request: MCPRequest) -> None:
        """Process supported notifications without ever creating a response."""
        if request.method == "notifications/initialized":
            return
        logger.debug("[VECTOR][mcp] Ignoring unknown notification {}", request.method)

    def _handle_initialize(self, req: MCPRequest) -> MCPResponse:
        """Handle the initialize handshake."""
        return MCPResponse(
            result={
                "protocolVersion": self.PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": True},
                },
                "serverInfo": {
                    "name": self.SERVER_NAME,
                    "version": self.SERVER_VERSION,
                    "title": "VectorCode Tool Server",
                },
            },
            id=req.id,
        )

    def _handle_tools_list(self, req: MCPRequest) -> MCPResponse:
        """Handle tools/list — return specs for all registered tools."""
        tool_list = []
        for tool in self._tools.values():
            s = tool.spec
            entry: Dict[str, Any] = {
                "name": s.name,
                "description": s.description,
                "inputSchema": s.parameters,
            }
            # Add annotations if available (MCP spec 2025-11-25)
            annotations = _TOOL_ANNOTATIONS.get(s.name)
            if annotations:
                entry["annotations"] = annotations
            tool_list.append(entry)
        return MCPResponse(result={"tools": tool_list}, id=req.id)

    def _handle_tools_call(self, req: MCPRequest) -> MCPResponse:
        """Handle tools/call — execute a tool and return the result."""
        tool_name = req.params.get("name")
        arguments = req.params.get("arguments", {})

        if not tool_name:
            return MCPResponse.error_response(
                req.id,
                INVALID_PARAMS,
                "Missing required parameter: name",
            )

        if tool_name not in self._tools:
            return MCPResponse.error_response(
                req.id,
                INVALID_PARAMS,
                f"Unknown tool: {tool_name}",
            )

        tool = self._tools[tool_name]
        annotation = _TOOL_ANNOTATIONS.get(tool_name, {})
        consequential = bool(tool.spec.required_capabilities) or not annotation.get(
            "readOnlyHint", False
        )
        if consequential:
            if self._authorize_action is None:
                logger.warning(
                    "[VECTOR][mcp] Refused consequential tool {} for {}: "
                    "Permission Gateway authorization is not configured",
                    tool_name,
                    self._agent_id,
                )
                return MCPResponse.error_response(
                    req.id,
                    INVALID_PARAMS,
                    "Tool authorization unavailable; request refused",
                )
            try:
                authorized = self._authorize_action(tool_name, arguments)
            except Exception:
                logger.opt(exception=True).error(
                    "[VECTOR][mcp] Permission Gateway authorization failed for {}",
                    tool_name,
                )
                authorized = False
            if not authorized:
                return MCPResponse.error_response(
                    req.id,
                    INVALID_PARAMS,
                    "Tool authorization denied",
                )

        try:
            import json

            tool_call = ToolCall(
                id=f"mcp-{req.id}",
                name=tool_name,
                arguments=json.dumps(arguments),
            )
            result = self._executor.execute(tool_call)
            if not result.success:
                from vectorcode.src.utils.redact import redact

                correlation_id = uuid.uuid4().hex
                logger.error(
                    "[VECTOR][mcp] Tool returned failure correlation_id={} error={}",
                    correlation_id,
                    redact(result.content, preserve_urls=False, preserve_emails=False),
                )
                return MCPResponse(
                    result={
                        "content": [{"type": "text", "text": "Tool execution failed"}],
                        "isError": True,
                        "correlation_id": correlation_id,
                    },
                    id=req.id,
                )
            return MCPResponse(
                result={
                    "content": [
                        {"type": "text", "text": result.content},
                    ],
                    "isError": not result.success,
                },
                id=req.id,
            )
        except Exception as exc:
            from vectorcode.src.utils.redact import redact

            correlation_id = uuid.uuid4().hex
            logger.error(
                "[VECTOR][mcp] Tool execution failed correlation_id={} error={}",
                correlation_id,
                redact(str(exc), preserve_urls=False, preserve_emails=False),
            )
            return MCPResponse.error_response(
                req.id,
                INTERNAL_ERROR,
                "Tool execution failed",
                data={"correlation_id": correlation_id},
            )

__all__ = ["MCPServer"]
