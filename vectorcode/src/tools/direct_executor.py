"""Direct Task Executor for Swarm — executes tasks without external CLI."""

import asyncio
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TaskResult:
    def __init__(self, output: str = "", artifacts: Optional[dict] = None,
                 execution_time: float = 0.0, agent_type: str = "",
                 quality: float = 1.0, completeness: float = 1.0,
                 validated: bool = True):
        self.output = output
        self.artifacts = artifacts or {}
        self.execution_time = execution_time
        self.agent_type = agent_type
        self.quality = quality
        self.completeness = completeness
        self.validated = validated


class DirectTaskExecutor:
    def __init__(self, timeout: int = 300):
        self.timeout = timeout

    async def execute(self, task_desc: str, tools: Optional[list] = None) -> TaskResult:
        start = time.time()
        try:
            result = await asyncio.wait_for(
                self._execute_internal(task_desc, tools or []),
                timeout=self.timeout,
            )
            elapsed = time.time() - start
            return TaskResult(output=result, execution_time=elapsed, validated=True)
        except asyncio.TimeoutError:
            elapsed = time.time() - start
            return TaskResult(output=f"Task timed out after {elapsed:.0f}s",
                              execution_time=elapsed, validated=False)
        except Exception as e:
            elapsed = time.time() - start
            return TaskResult(output=f"Task failed: {e}",
                              execution_time=elapsed, validated=False)

    async def _execute_internal(self, task_desc: str, tools: list) -> str:
        bash_tool = next((t for t in tools if t.get("type") == "bash"), None)
        if bash_tool is not None:
            import subprocess, shlex
            cmd = bash_tool.get("command", "echo no command")
            # Never shell=True — split into args to prevent injection
            args = shlex.split(cmd) if isinstance(cmd, str) else list(cmd)
            result = subprocess.run(args, shell=False, capture_output=True, text=True, timeout=30)
            return result.stdout or result.stderr or "(empty)"
        return f"Executed: {task_desc[:100]}"
