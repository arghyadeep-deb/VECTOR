"""
VECTOR × VectorCode Bridge

Connects VECTOR's autonomous loop to VectorCode for coding tasks.
VectorCode handles: code generation, review, debugging, git ops, file ops.
VECTOR handles: goals, scheduling, memory, permissions, notifications.

Usage from VECTOR's coding district:
    from districts.coding.vectorcode_bridge import VectorCodeBridge
    bridge = VectorCodeBridge()
    result = await bridge.run_task("Fix the bug in core/memory/episodic.py")
"""
import os
import sys
import asyncio
import subprocess
import threading
from pathlib import Path

from loguru import logger
from core.config import CONFIG

_VC_ROOT = Path(__file__).resolve().parent.parent.parent / "vectorcode"
_VC_ENTRY = _VC_ROOT / "vector.py"


class VectorCodeBridge:
    """
    Bridge between VECTOR's autonomous loop and VectorCode.
    All coding tasks route through here — VECTOR never calls LLMs for code directly.
    """

    def __init__(self):
        self._vc_available = _VC_ENTRY.exists()
        if self._vc_available:
            logger.info(f"[VectorCode] Bridge ready — entry: {_VC_ENTRY}")
        else:
            logger.warning(f"[VectorCode] Entry not found at {_VC_ENTRY}")

    def is_available(self) -> bool:
        return self._vc_available

    async def run_task(self, task: str, mode: str = "run", timeout: int = 300) -> dict:
        if not self._vc_available:
            return {"status": "unavailable", "output": "VectorCode not found", "exit_code": -1, "task": task}

        if not isinstance(task, str) or not task.strip():
            return {"status": "error", "output": "Empty or invalid task", "exit_code": -1, "task": ""}
        task = task.strip().replace('\x00', '')

        if mode not in ("run", "auto", "hybrid"):
            mode = "run"

        import json
        payload = json.dumps({"task": task, "mode": mode}).encode("utf-8")
        cmd = [sys.executable, str(_VC_ENTRY), "run", "--ipc"]

        logger.info(f"[VectorCode] Running: {mode} — {task[:60]}...")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(Path(__file__).resolve().parent.parent.parent),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(payload), timeout=timeout)
        except asyncio.TimeoutError:
            return {"status": "timeout", "output": f"Task timed out after {timeout}s", "exit_code": -1, "task": task}
        except Exception as e:
            logger.error(f"[VectorCode] Bridge error: {e}")
            return {"status": "error", "output": str(e), "exit_code": -1, "task": task}

        err = stderr.decode("utf-8", errors="replace").strip()
        try:
            result = json.loads(stdout.decode("utf-8", errors="replace").strip())
        except json.JSONDecodeError:
            return {"status": "error", "output": err or stdout.decode(), "exit_code": -1, "task": task}

        if result.get("exit_code") == 0:
            output = result.get("output", "")
            logger.info(f"[VectorCode] Task completed: {task[:40]}")
            try:
                from core.memory.episodic import EpisodicMemory
                mem = EpisodicMemory()
                mem.store(
                    event_type="vectorcode_task",
                    content=f"Task: {task[:100]}\nResult: {output[:200]}",
                    tags=["vectorcode", "coding", mode],
                    source="vectorcode_bridge",
                )
            except Exception as e:
                logger.warning(f"[VectorCode] Memory store failed: {e}")
            return {"status": "ok", "output": output, "exit_code": 0, "task": task}
        else:
            logger.warning(f"[VectorCode] Task failed: {err[:100]}")
            return {"status": "error", "output": err or result.get("output", ""), "exit_code": result.get("exit_code", -1), "task": task}

    async def start_mcp_server(self, port: int = 9001) -> subprocess.Popen:
        """Start VectorCode's MCP server as a background process."""
        if not self._vc_available:
            logger.warning("[VectorCode] Cannot start MCP server — not available")
            return None
        try:
            log_dir = Path(os.path.expanduser("~")) / ".vector_ca" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "mcp_server.log"
            stderr_log = open(log_path, "a", encoding="utf-8")
            proc = subprocess.Popen(
                [sys.executable, str(_VC_ENTRY), "mcp", "--sse", "--port", str(port)],
                cwd=str(_VC_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=stderr_log,
            )
            logger.info(f"[VectorCode] MCP server started on port {port} (pid={proc.pid})")
            return proc
        except Exception as e:
            logger.error(f"[VectorCode] MCP server start failed: {e}")
            return None

    def get_status(self) -> dict:
        """Check VectorCode availability and version."""
        if not self._vc_available:
            return {"available": False, "path": str(_VC_ENTRY)}
        try:
            result = subprocess.run(
                [sys.executable, str(_VC_ENTRY), "status"],
                capture_output=True, text=True, timeout=10,
                cwd=str(_VC_ROOT),
            )
            return {
                "available": True,
                "path": str(_VC_ENTRY),
                "output": result.stdout.strip()[:200],
                "exit_code": result.returncode,
            }
        except Exception as e:
            return {"available": True, "path": str(_VC_ENTRY), "error": str(e)}


# Singleton
_bridge: VectorCodeBridge | None = None
_bridge_lock = threading.Lock()

def get_bridge() -> VectorCodeBridge:
    global _bridge
    if _bridge is None:
        with _bridge_lock:
            if _bridge is None:  # double-check after acquiring lock
                _bridge = VectorCodeBridge()
    return _bridge


if __name__ == "__main__":
    import asyncio
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        bridge = get_bridge()
        print(f"Available: {bridge.is_available()}")
        status = bridge.get_status()
        print(f"Status: {status}")

    asyncio.run(_smoke())
    print("✅ vectorcode_bridge.py OK")
