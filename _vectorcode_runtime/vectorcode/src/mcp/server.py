"""VectorCode v3 MCP Server — expose tools, config, and memory via MCP protocol."""

import inspect
from typing import Any, Optional

class MCPTool:
    def __init__(self, name: str, description: str, handler: callable,
                 input_schema: Optional[dict] = None):
        self.name = name
        self.description = description
        self.handler = handler
        self.input_schema = input_schema or {"type": "object", "properties": {}}


class MCPServer:
    def __init__(self):
        self._tools: dict[str, MCPTool] = {}

    def register_tool(self, tool: MCPTool):
        self._tools[tool.name] = tool

    def list_tools(self) -> list[dict]:
        return [{"name": t.name, "description": t.description,
                 "input_schema": t.input_schema} for t in self._tools.values()]

    async def call_tool(self, name: str, args: dict) -> dict:
        tool = self._tools.get(name)
        if not tool: return {"error": f"Unknown tool: {name}"}
        try:
            result = tool.handler(**args)
            if inspect.isawaitable(result):
                result = await result
            return {"result": result}
        except Exception as e:
            return {"error": str(e)}

    def create_agent_tools(self, coordinator) -> list[MCPTool]:
        return [
            MCPTool("spawn_agent", "Spawn a new agent", coordinator.spawn_agent,
                    {"type": "object", "properties": {
                        "agent_type": {"type": "string", "description": "Type of agent to spawn"}}}),
            MCPTool("list_agents", "List all agents", coordinator.list_agents),
            MCPTool("get_swarm_status", "Get swarm status", coordinator.get_status),
        ]

    def create_memory_tools(self, backend) -> list[MCPTool]:
        return [
            MCPTool("memory_store", "Store a memory", backend.store,
                    {"type": "object", "properties": {
                        "namespace": {"type": "string"}, "key": {"type": "string"},
                        "value": {"type": "object"}}}),
            MCPTool("memory_get", "Get a memory", backend.get,
                    {"type": "object", "properties": {
                        "namespace": {"type": "string"}, "key": {"type": "string"}}}),
            MCPTool("memory_search", "Search memories", backend.search,
                    {"type": "object", "properties": {
                        "namespace": {"type": "string"}, "query": {"type": "string"}}}),
        ]
