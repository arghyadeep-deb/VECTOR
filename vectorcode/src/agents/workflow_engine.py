"""VectorCode v3 WorkflowEngine — task execution pipeline with lifecycle."""

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

class WorkflowEngine:
    def __init__(self):
        self._workflows: dict[str, dict] = {}

    async def execute(self, workflow: dict) -> dict:
        wf_id = workflow.get("id", f"wf-{id(workflow)}")
        steps = workflow.get("steps", [])
        results = []

        for i, step in enumerate(steps):
            try:
                result = await self._execute_step(step, i)
                results.append({"step": i, "status": "ok", "result": result})
            except Exception as e:
                results.append({"step": i, "status": "failed", "error": str(e)})
                break

        self._workflows[wf_id] = {"status": "completed", "results": results}
        return {"id": wf_id, "status": "completed", "results": results}

    async def _execute_step(self, step: dict, index: int) -> Any:
        action = step.get("action", "")
        if action == "bash":
            import subprocess, shlex
            cmd = step["command"]
            # Never shell=True — split into args to prevent injection
            args = shlex.split(cmd) if isinstance(cmd, str) else list(cmd)
            r = subprocess.run(args, shell=False, capture_output=True, text=True, timeout=30)
            return r.stdout[:5000] or r.stderr[:5000]
        elif action == "llm":
            return f"[LLM call: {step.get('prompt', '')[:100]}]"
        elif action == "delay":
            await asyncio.sleep(step.get("seconds", 1))
            return "delayed"
        return f"executed: {action}"
