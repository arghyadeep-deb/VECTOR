"""Sandbox router — /sandbox/status."""

import sys

__all__ = [
    "router",
    "sandbox_status",
]

import asyncio
import subprocess

from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/sandbox", tags=["sandbox"])

@router.get("/status")
async def sandbox_status():
    """Check Docker availability for sandboxed execution."""
    try:
        # blocking (up to 10 s): keep it off the event loop
        result = await asyncio.to_thread(
            subprocess.run, ["docker", "info"], capture_output=True, text=True, timeout=10,
        )
        available = result.returncode == 0
        return {"docker_available": available, "status": "ok" if available else "unavailable"}
    except FileNotFoundError:
        return {"docker_available": False, "status": "not_installed"}
    except subprocess.TimeoutExpired:
        return {"docker_available": False, "status": "timeout"}
    except Exception as e:
        logger.warning(f"[VECTOR][api][sandbox] status failed: {e}")
        return {"docker_available": False, "status": "error"}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ sandbox.py OK")
