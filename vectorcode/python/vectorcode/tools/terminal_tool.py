"""Terminal tool — secure shell execution with local, Docker, and SSH backends."""

import asyncio
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_BACKGROUND_TASKS: dict[str, subprocess.Popen] = {}


async def run_command(
    command: str,
    *,
    backend: str = "local",
    workdir: Optional[Path] = None,
    timeout: int = 60,
    env: Optional[dict] = None,
) -> dict:
    """Execute a shell command. Supports local, Docker, and SSH backends."""
    if backend == "docker":
        return await _run_docker(command, workdir, timeout, env)
    elif backend == "ssh":
        return await _run_ssh(command, workdir, timeout, env)
    else:
        return await _run_local(command, workdir, timeout, env)


async def _run_local(command: str, workdir: Optional[Path], timeout: int, env: Optional[dict]) -> dict:
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(workdir or Path.cwd()),
            env={**os.environ, **(env or {})},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "output": stdout.decode(errors="replace")[:50000],
            "error": stderr.decode(errors="replace")[:50000],
            "exit_code": proc.returncode or 0,
        }
    except asyncio.TimeoutError:
        if proc: proc.kill()
        return {"output": "", "error": f"Timed out after {timeout}s", "exit_code": -1}
    except Exception as e:
        return {"output": "", "error": str(e), "exit_code": -1}


async def _run_docker(command: str, workdir: Optional[Path], timeout: int, env: Optional[dict]) -> dict:
    container = os.environ.get("VECTOR_DOCKER_IMAGE", "python:3.12-slim")
    docker_cmd = f"docker run --rm -i {container} sh -c {_sh_quote(command)}"
    return await _run_local(docker_cmd, workdir, timeout, env)


async def _run_ssh(command: str, workdir: Optional[Path], timeout: int, env: Optional[dict]) -> dict:
    host = os.environ.get("VECTOR_SSH_HOST", "")
    if not host:
        return {"output": "", "error": "VECTOR_SSH_HOST not set", "exit_code": -1}
    ssh_cmd = f"ssh {host} {_sh_quote(command)}"
    return await _run_local(ssh_cmd, workdir, timeout, env)


async def start_background(command: str, task_id: str) -> bool:
    """Start a long-running background process."""
    try:
        proc = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _BACKGROUND_TASKS[task_id] = proc
        return True
    except Exception as e:
        logger.warning(f"Background task failed: {e}")
        return False


async def stop_background(task_id: str) -> bool:
    proc = _BACKGROUND_TASKS.pop(task_id, None)
    if proc:
        proc.kill()
        return True
    return False


def _sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"
