"""
Module: integrations/opencli/tool_registry.py
CLI tool registry - commands available to the VECTOR CLI.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.config import CONFIG
from loguru import logger
import asyncio
import subprocess
import json
import uuid
import shlex
from typing import List, Dict, Any, Optional, Callable


class ToolRegistry:
    """Registry for CLI tools available to VECTOR CLI."""

    def __init__(self):
        self.opencli_config = CONFIG.get("opencli", {})
        self.tools: Dict[str, Dict[str, Any]] = {}
        self.execution_history: List[Dict[str, Any]] = []
        self._load_default_tools()
        logger.info(f"[OpenCLI] Tool registry initialized with {len(self.tools)} tools")

    def _load_default_tools(self):
        """Load default tools from config."""
        default_tools = self.opencli_config.get("tools", [])

        for tool in default_tools:
            self.register_tool(
                name=tool.get("name", ""),
                command=tool.get("command", ""),
                description=tool.get("description", ""),
            )

    def register_tool(
        self,
        name: str,
        command: str,
        description: str = "",
    ) -> Dict[str, Any]:
        """
        Register a CLI tool.

        Args:
            name: Unique name for the tool
            command: The command to execute (can include args)
            description: Human-readable description

        Returns:
            Dict with registration status
        """
        if name in self.tools:
            logger.warning(f"[OpenCLI] Tool {name} already registered, updating")

        tool_id = f"tool_{uuid.uuid4().hex[:8]}"
        self.tools[name] = {
            "id": tool_id,
            "name": name,
            "command": command,
            "description": description,
            "registered_at": self._get_timestamp(),
            "executions": 0,
            "last_executed": None,
        }

        logger.info(f"[OpenCLI] Registered tool: {name} -> {command}")
        return {"success": True, "tool_id": tool_id, "name": name}

    async def execute_tool(
        self,
        name: str,
        args: Optional[List[str]] = None,
        timeout: int = 30,
        env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a registered CLI tool.

        Args:
            name: Name of the tool to execute
            args: Optional arguments to pass to the command
            timeout: Execution timeout in seconds
            env: Optional environment variables

        Returns:
            Dict with execution results
        """
        if name not in self.tools:
            logger.error(f"[OpenCLI] Tool not found: {name}")
            return {"success": False, "error": f"Tool not found: {name}"}

        tool = self.tools[name]
        base_command = tool["command"]

        if args:
            args_str = " ".join(shlex.quote(str(arg)) for arg in args)
            full_command = f"{base_command} {args_str}"
        else:
            full_command = base_command

        logger.info(f"[OpenCLI] Executing: {full_command}")

        execution_id = f"exec_{uuid.uuid4().hex[:12]}"
        start_time = self._get_timestamp()

        try:
            process = await asyncio.create_subprocess_shell(
                full_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return {
                    "success": False,
                    "execution_id": execution_id,
                    "error": f"Execution timeout after {timeout}s",
                    "tool": name,
                }

            stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

            tool["executions"] += 1
            tool["last_executed"] = start_time

            result = {
                "success": process.returncode == 0,
                "execution_id": execution_id,
                "tool": name,
                "command": full_command,
                "return_code": process.returncode,
                "stdout": stdout_str,
                "stderr": stderr_str,
                "started_at": start_time,
                "completed_at": self._get_timestamp(),
            }

            self.execution_history.append(result)
            if len(self.execution_history) > 100:
                self.execution_history = self.execution_history[-100:]

            logger.info(f"[OpenCLI] Tool {name} executed with code {process.returncode}")
            return result

        except Exception as e:
            logger.error(f"[OpenCLI] Execution failed: {e}")
            return {
                "success": False,
                "execution_id": execution_id,
                "tool": name,
                "error": str(e),
            }

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        List all registered tools.

        Returns:
            List of tool info dicts
        """
        return [
            {
                "name": tool["name"],
                "description": tool["description"],
                "command": tool["command"],
                "executions": tool["executions"],
                "last_executed": tool["last_executed"],
            }
            for tool in self.tools.values()
        ]

    def remove_tool(self, name: str) -> Dict[str, Any]:
        """
        Unregister a tool.

        Args:
            name: Name of the tool to remove

        Returns:
            Dict with removal status
        """
        if name not in self.tools:
            logger.warning(f"[OpenCLI] Tool not found: {name}")
            return {"success": False, "error": "Tool not found"}

        del self.tools[name]
        logger.info(f"[OpenCLI] Removed tool: {name}")
        return {"success": True, "name": name}

    def get_tool(self, name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific tool."""
        return self.tools.get(name)

    def get_execution_history(
        self,
        tool_name: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Get execution history.

        Args:
            tool_name: Optional filter by tool name
            limit: Maximum number of records

        Returns:
            List of execution records
        """
        history = self.execution_history
        if tool_name:
            history = [h for h in history if h.get("tool") == tool_name]
        return history[-limit:]

    def get_tool_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics about tool usage."""
        total_executions = sum(t["executions"] for t in self.tools.values())
        successful = sum(
            1 for h in self.execution_history if h.get("success")
        )
        failed = len(self.execution_history) - successful

        return {
            "total_tools": len(self.tools),
            "total_executions": total_executions,
            "successful_executions": successful,
            "failed_executions": failed,
            "success_rate": successful / len(self.execution_history) if self.execution_history else 0,
        }

    def _get_timestamp(self) -> str:
        """Get current ISO timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()


class ToolRunner:
    """Higher-level tool execution with chaining support."""

    def __init__(self):
        self.registry = ToolRegistry()
        self._custom_handlers: Dict[str, Callable] = {}

    def register_handler(self, name: str, handler: Callable):
        """Register a custom handler for a tool."""
        self._custom_handlers[name] = handler
        logger.info(f"[OpenCLI] Registered custom handler: {name}")

    async def run_chain(
        self,
        tool_sequence: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Run a sequence of tools, passing output to input.

        Args:
            tool_sequence: List of {'tool': name, 'args': [...]} dicts

        Returns:
            List of execution results
        """
        results = []
        context = {}

        for step in tool_sequence:
            tool_name = step.get("tool")
            args = step.get("args", [])

            if args and isinstance(args[0], str) and args[0].startswith("$"):
                var_name = args[0][1:]
                if var_name in context:
                    args = [context[var_name]] + args[1:]

            result = await self.registry.execute_tool(tool_name, args)
            results.append(result)

            if result.get("success") and result.get("stdout"):
                context[f"{tool_name}_output"] = result["stdout"]

        return results


async def main():
    """Test the tool registry."""
    registry = ToolRegistry()

    registry.register_tool(
        name="echo",
        command="echo",
        description="Print text to stdout",
    )

    registry.register_tool(
        name="list_dir",
        command="ls -la",
        description="List directory contents",
    )

    print("Tools:", registry.list_tools())

    result = await registry.execute_tool("echo", ["Hello from VECTOR!"])
    print(f"Echo result: {result}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
    print("✅ tool_registry.py OK")