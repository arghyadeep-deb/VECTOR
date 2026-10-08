"""VectorCode v3 WorkflowEngine — task execution pipeline with lifecycle."""

import asyncio
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from core.loop.permission_gateway import PermissionGateway
from core.runtime_paths import get_data_root, get_project_root


_ALLOWED_EXECUTABLES = frozenset(
    {
        "git", "git.exe", "py", "py.exe", "pytest", "pytest.exe",
        "python", "python.exe", "python3", "python3.exe",
    }
)
_WINDOWS_ENV_KEYS = ("SystemRoot", "WINDIR", "PATHEXT")


class _WorkflowBlocked(RuntimeError):
    """Signal an expected permission denial without crashing the workflow."""


class WorkflowEngine:
    def __init__(self, permission_gateway: PermissionGateway | None = None):
        self._workflows: dict[str, dict] = {}
        self._permission_gateway = permission_gateway or PermissionGateway()

    async def execute(self, workflow: dict) -> dict:
        wf_id = workflow.get("id", f"wf-{id(workflow)}")
        steps = workflow.get("steps", [])
        results = []

        for i, step in enumerate(steps):
            try:
                result = await self._execute_step(step, i)
                results.append({"step": i, "status": "ok", "result": result})
            except _WorkflowBlocked as exc:
                results.append({"step": i, "status": "blocked", "reason": str(exc)})
                break
            except Exception as exc:
                results.append({"step": i, "status": "failed", "error": str(exc)})
                break

        if any(result["status"] == "failed" for result in results):
            overall = "failed"
        elif any(result["status"] == "blocked" for result in results):
            overall = "blocked"
        else:
            overall = "completed"
        self._workflows[wf_id] = {"status": overall, "results": results}
        return {"id": wf_id, "status": overall, "results": results}

    async def _execute_step(self, step: dict, index: int) -> Any:
        action = step.get("action", "")
        if action == "bash":
            return await self._execute_bash(step)
        if action == "llm":
            raise RuntimeError("LLM workflow steps are not implemented")
        if action == "delay":
            await asyncio.sleep(step.get("seconds", 1))
            return "delayed"
        raise ValueError(f"unknown workflow action: {action!r}")

    async def _execute_bash(self, step: dict) -> str:
        command = step["command"]
        args = shlex.split(command) if isinstance(command, str) else list(command)
        if not args:
            raise ValueError("workflow command must not be empty")

        cwd = self._resolve_cwd(step.get("cwd"))
        env = self._minimal_environment()
        args[0] = self._resolve_executable(str(args[0]), env["PATH"])

        try:
            gateway_result = await self._permission_gateway.evaluate_external(
                "workflow_bash_execute",
                {"command": args, "cwd": str(cwd)},
                "workflow_engine",
            )
        except Exception as exc:
            raise _WorkflowBlocked(f"Permission Gateway unavailable: {exc}") from None
        if not gateway_result.approved:
            reason = gateway_result.reason or "Permission Gateway denied workflow bash execution"
            raise _WorkflowBlocked(reason)

        result = subprocess.run(
            args, shell=False, capture_output=True, text=True, timeout=30,
            cwd=cwd, env=env,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[:5000]
            raise RuntimeError(
                f"workflow command exited with status {result.returncode}: {detail}"
            )
        return result.stdout[:5000]

    @staticmethod
    def _resolve_cwd(value: str | os.PathLike[str] | None) -> Path:
        project_root = get_project_root().resolve()
        data_root = get_data_root().resolve()
        candidate = project_root if value is None else Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = project_root / candidate
        candidate = candidate.resolve()
        if not any(
            candidate == root or candidate.is_relative_to(root)
            for root in (project_root, data_root)
        ):
            raise ValueError(f"workflow cwd is outside allowed roots: {candidate}")
        if not candidate.is_dir():
            raise ValueError(f"workflow cwd is not an existing directory: {candidate}")
        return candidate

    @staticmethod
    def _minimal_environment() -> dict[str, str]:
        env = {"PATH": os.environ.get("PATH", os.defpath)}
        for key in _WINDOWS_ENV_KEYS:
            if key in os.environ:
                env[key] = os.environ[key]
        return env

    @staticmethod
    def _resolve_executable(program: str, path: str) -> str:
        requested = Path(program)
        if requested.name.lower() not in _ALLOWED_EXECUTABLES:
            raise ValueError(f"workflow executable is not allowlisted: {program}")

        resolved = shutil.which(requested.name, path=path)
        if resolved is None:
            raise ValueError(f"workflow executable was not found on PATH: {program}")
        resolved_path = Path(resolved).resolve()
        if requested.parent != Path("."):
            requested_path = requested.resolve()
            python_path = Path(sys.executable).resolve()
            path_match = os.path.normcase(str(requested_path)) == os.path.normcase(
                str(resolved_path)
            )
            python_match = os.path.normcase(str(requested_path)) == os.path.normcase(
                str(python_path)
            )
            if not path_match and not python_match:
                raise ValueError(f"workflow executable path is not trusted: {program}")
            return str(requested_path)
        return str(resolved_path)
