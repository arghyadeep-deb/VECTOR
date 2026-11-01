# Ported from GitHub/vectorcode_vector/repo/vector/src/mcp-bridge/index.js
"""VectorCode MCP bridge — group-based tool routing to multiple MCP servers."""
import os
from typing import Any, Dict, List, Optional

from loguru import logger

# Tool group definitions (from VectorCode mcp-bridge/index.js)
TOOL_GROUPS: Dict[str, dict] = {
    "intelligence": {
        "enabled": os.environ.get("MCP_GROUP_INTELLIGENCE", "true") != "false",
        "description": "Self-learning intelligence — routing, memory, pattern training",
        "prefixes": ["hooks_"],
    },
    "agents": {
        "enabled": os.environ.get("MCP_GROUP_AGENTS", "true") != "false",
        "description": "Agent lifecycle, swarm coordination, task management",
        "prefixes": ["agent_", "swarm_", "task_", "session_", "workflow_", "coordination_"],
    },
    "memory": {
        "enabled": os.environ.get("MCP_GROUP_MEMORY", "true") != "false",
        "description": "Vector memory, AgentDB, embeddings, semantic search",
        "prefixes": ["memory_", "agentdb_", "embeddings_"],
    },
    "devtools": {
        "enabled": os.environ.get("MCP_GROUP_DEVTOOLS", "true") != "false",
        "description": "Hooks, code analysis, performance profiling, GitHub integration",
        "prefixes": ["hooks_", "analyze_", "performance_", "github_", "terminal_", "config_"],
    },
    "security": {
        "enabled": os.environ.get("MCP_GROUP_SECURITY", "false") == "true",
        "description": "AI defence, PII detection, claims management",
        "prefixes": ["aidefence_", "claims_", "transfer_"],
    },
    "browser": {
        "enabled": os.environ.get("MCP_GROUP_BROWSER", "false") == "true",
        "description": "Headless browser control",
        "prefixes": ["browser_"],
    },
    "neural": {
        "enabled": os.environ.get("MCP_GROUP_NEURAL", "false") == "true",
        "description": "Neural network operations, DAA",
        "prefixes": ["neural_", "daa_"],
    },
}


def get_group_for_tool(tool_name: str) -> Optional[str]:
    """Return the group name for a tool based on its prefix."""
    for group_name, group in TOOL_GROUPS.items():
        if not group["enabled"]:
            continue
        for prefix in group.get("prefixes", []):
            if tool_name.startswith(prefix):
                return group_name
    return None


def is_tool_enabled(tool_name: str) -> bool:
    """Return True if the tool's group is enabled."""
    group = get_group_for_tool(tool_name)
    if group is None:
        return True  # unknown group = allow
    return TOOL_GROUPS[group]["enabled"]


class MCPBridge:
    """Routes tool calls to the appropriate MCP server based on tool group.

    Ported from VectorCode mcp-bridge/index.js.
    """

    def __init__(self):
        self._clients: Dict[str, Any] = {}  # server_name → MCPClient

    def get_or_connect(self, server_name: str) -> Any:
        """Get or create an MCPClient for the given server name."""
        if server_name not in self._clients:
            from vectorcode.mcp_client.client import MCPClient
            self._clients[server_name] = MCPClient.get_or_create(server_name)
        return self._clients[server_name]

    def call_tool(self, tool_name: str, arguments: dict, server: Optional[str] = None) -> Any:
        """Route a tool call to the appropriate MCP server."""
        if not is_tool_enabled(tool_name):
            return {"error": f"Tool group for {tool_name!r} is disabled"}

        # Determine server from tool group if not specified
        if server is None:
            group = get_group_for_tool(tool_name)
            server = group or "default"

        try:
            client = self.get_or_connect(server)
            return client.call_tool(tool_name, arguments)
        except Exception as e:
            logger.error(f"MCPBridge.call_tool failed: {tool_name!r} on {server!r}: {e}")
            return {"error": str(e)}

    def list_all_tools(self) -> List[dict]:
        """List all tools from all connected servers."""
        tools = []
        for server_name, client in self._clients.items():
            try:
                server_tools = client.list_tools()
                for t in server_tools:
                    t["server"] = server_name
                    t["group"] = get_group_for_tool(t.get("name", ""))
                tools.extend(server_tools)
            except Exception as e:
                logger.warning(f"Failed to list tools from {server_name}: {e}")
        return tools


# Module-level singleton
_bridge: Optional[MCPBridge] = None


def get_bridge() -> MCPBridge:
    global _bridge
    if _bridge is None:
        _bridge = MCPBridge()
    return _bridge
