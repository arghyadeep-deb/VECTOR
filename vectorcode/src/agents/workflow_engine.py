"""VectorCode v3 WorkflowEngine — task execution pipeline with lifecycle."""

import asyncio
from typing import Any, Optional

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

        # Phantom success: the top-level status used to always say
        # "completed" even when a step failed and the loop broke early
        # (visible per-step as status="failed", but never surfaced at the
        # workflow level) -- same bug class fixed 50+ times this cycle.
        overall = "failed" if any(r["status"] == "failed" for r in results) else "completed"
        self._workflows[wf_id] = {"status": overall, "results": results}
        return {"id": wf_id, "status": overall, "results": results}

    async def _execute_step(self, step: dict, index: int) -> Any:
        action = step.get("action", "")
        if action == "bash":
            import subprocess, shlex
            cmd = step["command"]
            # Never shell=True — split into args to prevent injection
            args = shlex.split(cmd) if isinstance(cmd, str) else list(cmd)
            r = subprocess.run(args, shell=False, capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                detail = (r.stderr or r.stdout).strip()[:5000]
                raise RuntimeError(
                    f"workflow command exited with status {r.returncode}: {detail}"
                )
            return r.stdout[:5000]
        elif action == "llm":
            raise RuntimeError("LLM workflow steps are not implemented")
        elif action == "delay":
            await asyncio.sleep(step.get("seconds", 1))
            return "delayed"
        raise ValueError(f"unknown workflow action: {action!r}")
